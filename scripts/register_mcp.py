#!/usr/bin/env python3
"""Add or update the claude-rag MCP server entry in ~/.claude.json.

Idempotent: re-running just refreshes the entry. Backs up the original first.
"""
import json
import os
import shutil
import sys
from pathlib import Path

CLAUDE_JSON = Path.home() / ".claude.json"
SERVER_NAME = "claude-rag"
REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_command() -> str | None:
    """Resolve the claude-rag-server binary path.

    Priority:
      1. $CLAUDE_RAG_SERVER_BIN (explicit override)
      2. <repo>/.venv/bin/claude-rag-server (alongside this script)
      3. shutil.which("claude-rag-server") (PATH lookup)
    """
    override = os.environ.get("CLAUDE_RAG_SERVER_BIN")
    if override:
        return override if Path(override).exists() else None

    local_venv = REPO_ROOT / ".venv" / "bin" / "claude-rag-server"
    if local_venv.exists():
        return str(local_venv)

    on_path = shutil.which("claude-rag-server")
    if on_path:
        return on_path
    return None


def main() -> int:
    if not CLAUDE_JSON.exists():
        print(f"error: {CLAUDE_JSON} not found", file=sys.stderr)
        return 1

    command = resolve_command()
    if not command:
        print("error: claude-rag-server binary not found.", file=sys.stderr)
        print("       tried: $CLAUDE_RAG_SERVER_BIN, "
              f"{REPO_ROOT}/.venv/bin/claude-rag-server, $PATH", file=sys.stderr)
        print("       run `uv pip install -e .` in the repo root, "
              "or set CLAUDE_RAG_SERVER_BIN to a custom path.", file=sys.stderr)
        return 1

    backup = CLAUDE_JSON.with_suffix(".json.bak-claude-rag")
    shutil.copy2(CLAUDE_JSON, backup)
    print(f"backup: {backup}")

    data = json.loads(CLAUDE_JSON.read_text())
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_NAME] = {
        "type": "stdio",
        "command": command,
        "args": [],
        "env": {},
    }

    CLAUDE_JSON.write_text(json.dumps(data, indent=2))
    print(f"registered MCP server '{SERVER_NAME}' -> {command}")
    print("restart Claude Code to pick up the change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
