# claude-rag

Local RAG over your Claude Code conversation history, exposed as an MCP server so Claude can recall past sessions inside the IDE.

The transcripts Claude Code writes to `~/.claude/projects/**/*.jsonl` get parsed, chunked, embedded, and indexed into a local Chroma database. An MCP server then lets Claude query the index — solving the "Claude forgets last week's work" problem without sending anything to a cloud service.

## Requirements

- macOS or Linux
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- ~250 MB free disk: ~50 MB for the index after a few months of use, ~220 MB for the embedding model cache

Everything runs locally. No API keys.

## Install

```bash
git clone <this-repo> ~/dev/claude-rag   # or anywhere
cd ~/dev/claude-rag
uv venv
uv pip install -e .
```

This creates `.venv/` and installs two console entry points:

- `claude-rag-index` — (re)builds the index
- `claude-rag-server` — the MCP server

## First-time index

```bash
.venv/bin/claude-rag-index
```

The first run downloads the embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, ~220 MB, cached in `~/.cache/fastembed/`) and embeds every user/assistant turn under `~/.claude/projects/`. On a typical machine with ~6 months of history, expect 5–10 minutes on CPU.

Subsequent runs are incremental — only changed JSONL files get re-embedded. State is tracked in `~/.claude-rag/state.json`.

Force a full rebuild with `--force`.

## Register with Claude Code

```bash
.venv/bin/python scripts/register_mcp.py
```

This writes an `mcpServers.claude-rag` entry into `~/.claude.json` (a backup is left at `~/.claude.json.bak-claude-rag`). It auto-detects the server binary in this order:

1. `$CLAUDE_RAG_SERVER_BIN` if set
2. `<repo>/.venv/bin/claude-rag-server`
3. `claude-rag-server` on `$PATH`

Restart Claude Code (or run `/mcp` and reconnect) to pick up the new server.

## Usage in the IDE

Once registered, Claude has three new tools:

| Tool | What it does |
|---|---|
| `search_conversations(query, project?, limit?)` | Semantic search across all indexed turns |
| `get_session_window(session_id, around_timestamp?, radius?)` | Expand context around a hit |
| `reindex(force?)` | Trigger an incremental reindex from inside the IDE |

Just ask Claude things like "do you remember what we decided about X" or "回忆一下我之前是怎么处理 Y 的" — it should call `search_conversations` automatically.

## CLI usage

The same store can be queried directly without an MCP client:

```bash
.venv/bin/python -c "
from claude_rag.store import Store
for h in Store().query('your query here', limit=5):
    print(h['metadata']['timestamp'][:19], h['metadata']['project'], '-', h['text'][:120])
"
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `CLAUDE_RAG_DATA` | `~/.claude-rag` | Where the Chroma DB and `state.json` live |
| `CLAUDE_RAG_SERVER_BIN` | (auto-detect) | Override path to `claude-rag-server` for `register_mcp.py` |
| `CLAUDE_RAG_LOG` | `WARNING` | Server log level |

To change chunking or the embedding model, edit `src/claude_rag/config.py`.

## Where data lives

| Path | Contents | Sensitive? |
|---|---|---|
| `~/.claude/projects/` | Source: Claude Code's own JSONL transcripts | yes |
| `~/.claude-rag/chroma/` | Vector DB with full chunk text | **yes — never commit or sync** |
| `~/.claude-rag/state.json` | Per-file mtime/size for incremental indexing | low |
| `~/.cache/fastembed/` | ONNX embedding model | no |

The repo's `.gitignore` already covers `.chroma/` and `data/` as belt-and-suspenders, but by default the data lives outside the repo entirely.

## Architecture

```
~/.claude/projects/**/*.jsonl
        |
        v
   jsonl.py        strips IDE/system-reminder wrappers,
   (parse +        skips queue/snapshot/tool rows,
    chunk)         char-based chunks (1500/200 overlap)
        |
        v
   store.py        fastembed multilingual MiniLM (384 dim)
   (embed)         -> Chroma PersistentClient (cosine)
        |
        v
   server.py       MCP stdio server: 3 tools
                   <- Claude Code (in-IDE)
```

About 350 lines of Python total.

## Troubleshooting

**`claude-rag` doesn't show up in `/mcp`**: confirm the entry exists in `~/.claude.json` under `mcpServers.claude-rag` and that the `command` path points to an existing executable. Restart Claude Code.

**`Model ... is not supported`**: fastembed's supported model list changes between versions. Run `python -c "from fastembed import TextEmbedding; print(*[m['model'] for m in TextEmbedding.list_supported_models()], sep='\n')"` to see what's available, then update `EMBEDDING_MODEL` in `config.py`.

**Search recall is poor for very short queries**: the multilingual MiniLM model is decent but not state of the art. For better quality, swap in `intfloat/multilingual-e5-large` (2.2 GB, 1024 dim) — bigger model, better recall, slower index. Edit `EMBEDDING_MODEL` and run `claude-rag-index --force`.

**Reset everything**: `rm -rf ~/.claude-rag/`, then re-run `claude-rag-index`.
