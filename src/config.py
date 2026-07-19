import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / "corpus"

EDGAR_IDENTITY = os.environ.get("EDGAR_IDENTITY", "jaynehete@gmail.com")
OLLAMA_MODEL = "llama3.2"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K_RESULTS = 5
