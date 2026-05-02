import os
from pathlib import Path

HOME = Path.home()
PROJECTS_DIR = HOME / ".claude" / "projects"
DATA_DIR = Path(os.environ.get("CLAUDE_RAG_DATA", HOME / ".claude-rag"))
CHROMA_DIR = DATA_DIR / "chroma"
STATE_FILE = DATA_DIR / "state.json"

COLLECTION_NAME = "claude_conversations"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

MAX_CHUNK_CHARS = 1500
CHUNK_OVERLAP_CHARS = 200
