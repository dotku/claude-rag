"""Walk ~/.claude/projects/ and (re)index changed JSONL files into Chroma."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import (
    CHUNK_OVERLAP_CHARS,
    DATA_DIR,
    MAX_CHUNK_CHARS,
    PROJECTS_DIR,
    STATE_FILE,
)
from .jsonl import chunk_text, iter_records
from .store import Store

BATCH_SIZE = 64


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"files": {}}


def _save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _project_name(cwd: str) -> str:
    """Last two path components: '/Users/wlin/dev/sienovo' -> 'wlin/sienovo'? No — just last component."""
    if not cwd:
        return ""
    return Path(cwd).name


def index_file(store: Store, path: Path) -> int:
    """Re-index a single JSONL file. Returns number of chunks added."""
    source = str(path)
    store.delete_by_source(source)

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    added = 0

    for rec in iter_records(path):
        text = rec["text"]
        chunks = chunk_text(text, MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS)
        for ci, chunk in enumerate(chunks):
            ids.append(f"{rec['uuid'] or rec['session_id']}:{rec['line_no']}:{ci}")
            docs.append(chunk)
            metas.append(
                {
                    "source_path": source,
                    "session_id": rec["session_id"],
                    "cwd": rec["cwd"],
                    "project": _project_name(rec["cwd"]),
                    "role": rec["role"],
                    "timestamp": rec["timestamp"],
                    "uuid": rec["uuid"],
                    "chunk_idx": ci,
                    "n_chunks": len(chunks),
                }
            )
            if len(ids) >= BATCH_SIZE:
                store.upsert(ids, docs, metas)
                added += len(ids)
                ids, docs, metas = [], [], []

    if ids:
        store.upsert(ids, docs, metas)
        added += len(ids)
    return added


def run(force: bool = False, verbose: bool = True) -> None:
    if not PROJECTS_DIR.exists():
        print(f"No projects dir at {PROJECTS_DIR}", file=sys.stderr)
        sys.exit(1)

    store = Store()
    state = _load_state()
    files_state: dict = state.setdefault("files", {})

    files = sorted(PROJECTS_DIR.rglob("*.jsonl"))
    total = len(files)
    started = time.time()
    indexed_files = 0
    indexed_chunks = 0
    skipped = 0

    for i, path in enumerate(files, 1):
        try:
            stat = path.stat()
        except OSError:
            continue
        key = str(path)
        prev = files_state.get(key)
        sig = {"size": stat.st_size, "mtime": stat.st_mtime}
        if not force and prev == sig:
            skipped += 1
            continue

        added = index_file(store, path)
        files_state[key] = sig
        indexed_files += 1
        indexed_chunks += added

        if verbose:
            elapsed = time.time() - started
            print(
                f"[{i}/{total}] {path.parent.name}/{path.name} "
                f"+{added} chunks  (total: {indexed_chunks} chunks, "
                f"{indexed_files} files, {elapsed:.1f}s)",
                flush=True,
            )

        if i % 25 == 0:
            _save_state(state)

    _save_state(state)
    if verbose:
        elapsed = time.time() - started
        print(
            f"\nDone. Indexed {indexed_chunks} chunks from {indexed_files} files "
            f"({skipped} unchanged, {elapsed:.1f}s). "
            f"Collection size: {store.count()} chunks.",
            flush=True,
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Index Claude Code conversations into Chroma.")
    p.add_argument("--force", action="store_true", help="Reindex everything, ignoring state.")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    run(force=args.force, verbose=not args.quiet)


if __name__ == "__main__":
    main()
