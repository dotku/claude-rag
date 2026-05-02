"""Parse Claude Code JSONL transcripts into clean (role, text, metadata) records."""
import json
import re
from pathlib import Path
from typing import Iterator, Optional

# IDE/system noise we want to strip from user messages before indexing.
_NOISE_TAGS = (
    "ide_opened_file",
    "ide_selection",
    "system-reminder",
    "command-message",
    "command-name",
    "command-args",
    "local-command-stdout",
    "local-command-stderr",
)
_NOISE_RE = re.compile(
    r"<(" + "|".join(_NOISE_TAGS) + r")>.*?</\1>",
    re.DOTALL,
)


def clean_user_text(text: str) -> str:
    """Strip IDE wrappers and system reminders from a user message."""
    return _NOISE_RE.sub("", text).strip()


def extract_text(msg_obj: dict) -> tuple[str, str]:
    """Return (role, text). Empty text means nothing useful to index."""
    msg = msg_obj.get("message")
    if not isinstance(msg, dict):
        return "", ""
    role = msg.get("role") or msg_obj.get("type", "")
    content = msg.get("content")

    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            it.get("text", "")
            for it in content
            if isinstance(it, dict) and it.get("type") == "text"
        ]
        text = "\n".join(p for p in parts if p)
    else:
        text = ""

    if role == "user":
        text = clean_user_text(text)
    return role, text.strip()


def iter_records(path: Path) -> Iterator[dict]:
    """Yield normalized records from one JSONL file.

    Each record: {role, text, session_id, cwd, timestamp, uuid, line_no}
    Skips operational/queue/snapshot rows and empty messages.
    """
    try:
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") not in ("user", "assistant"):
                    continue
                role, text = extract_text(obj)
                if not text or len(text) < 20:
                    continue
                yield {
                    "role": role,
                    "text": text,
                    "session_id": obj.get("sessionId", ""),
                    "cwd": obj.get("cwd", ""),
                    "timestamp": obj.get("timestamp", ""),
                    "uuid": obj.get("uuid", ""),
                    "line_no": line_no,
                }
    except OSError:
        return


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Char-based chunker with overlap. Adequate for POC."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    step = max_chars - overlap
    i = 0
    while i < len(text):
        chunks.append(text[i : i + max_chars])
        if i + max_chars >= len(text):
            break
        i += step
    return chunks
