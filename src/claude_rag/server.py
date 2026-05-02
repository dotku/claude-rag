"""MCP server exposing search over indexed Claude Code conversations."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .indexer import run as run_index
from .jsonl import iter_records
from .store import Store

logger = logging.getLogger("claude-rag")
server = Server("claude-rag")

_store: Store | None = None


def _get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def _format_hit(hit: dict) -> str:
    meta = hit["metadata"]
    ts = meta.get("timestamp", "")[:19]
    role = meta.get("role", "?")
    project = meta.get("project") or meta.get("cwd", "")
    session = meta.get("session_id", "")[:8]
    score = 1.0 - hit.get("distance", 0.0)
    header = f"[{ts}] {role} @ {project} (session {session}, score {score:.3f})"
    return f"{header}\n{hit['text']}"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_conversations",
            description=(
                "Search past Claude Code conversations by semantic similarity. "
                "Returns matching turns with timestamp, role, project, and session id. "
                "Use this when the user references prior work, asks 'do you remember', "
                "or you need context that the current session does not have."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query. Multilingual (CN/EN) ok.",
                    },
                    "project": {
                        "type": "string",
                        "description": "Optional. Project name (last path component of cwd, e.g. 'sienovo-intl') to restrict search.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 8).",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_session_window",
            description=(
                "Fetch a window of turns around a specific session+timestamp, "
                "to expand the context of a search hit."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "around_timestamp": {
                        "type": "string",
                        "description": "ISO timestamp; returns turns within +/- 5 around it.",
                    },
                    "radius": {"type": "integer", "default": 5},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="reindex",
            description="Trigger an incremental reindex of ~/.claude/projects/ JSONL files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {"type": "boolean", "default": False},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "search_conversations":
        query = arguments["query"]
        limit = int(arguments.get("limit", 8))
        project = arguments.get("project")
        where = {"project": project} if project else None
        hits = _get_store().query(query, limit=limit, where=where)
        if not hits:
            return [TextContent(type="text", text="(no matches)")]
        body = "\n\n---\n\n".join(_format_hit(h) for h in hits)
        return [TextContent(type="text", text=body)]

    if name == "get_session_window":
        session_id = arguments["session_id"]
        around = arguments.get("around_timestamp", "")
        radius = int(arguments.get("radius", 5))
        # Find the JSONL file containing this session by scanning index metadata.
        store = _get_store()
        # Query a single result for this session to discover its source path.
        result = store.query(query="x", limit=1, where={"session_id": session_id})
        if not result:
            return [TextContent(type="text", text=f"(session {session_id} not found in index)")]
        source_path = result[0]["metadata"].get("source_path", "")
        from pathlib import Path

        if not source_path or not Path(source_path).exists():
            return [TextContent(type="text", text="(source file missing)")]

        records = list(iter_records(Path(source_path)))
        records = [r for r in records if r["session_id"] == session_id]
        if not records:
            return [TextContent(type="text", text="(no records for session)")]

        if around:
            anchor = next(
                (i for i, r in enumerate(records) if r["timestamp"] >= around),
                len(records) - 1,
            )
        else:
            anchor = 0

        lo = max(0, anchor - radius)
        hi = min(len(records), anchor + radius + 1)
        window = records[lo:hi]
        body = "\n\n---\n\n".join(
            f"[{r['timestamp'][:19]}] {r['role']}:\n{r['text']}" for r in window
        )
        return [TextContent(type="text", text=body)]

    if name == "reindex":
        force = bool(arguments.get("force", False))
        # Run synchronously; report stats.
        await asyncio.to_thread(run_index, force, False)
        store = _get_store()
        return [
            TextContent(
                type="text",
                text=f"Reindex complete. Collection size: {store.count()} chunks.",
            )
        ]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _async_main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("CLAUDE_RAG_LOG", "WARNING"),
        stream=sys.stderr,
    )
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
