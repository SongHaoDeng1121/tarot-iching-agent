"""Deployment data paths; unset environment preserves the local layout."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def knowledge_path(relative):
    base = Path(os.environ.get("KNOWLEDGE_ROOT", str(ROOT))).expanduser().resolve()
    return base / relative


def chroma_path():
    return knowledge_path("storage/chroma")


def runtime_root():
    return Path(os.environ.get("APP_RUNTIME_DIR", str(ROOT / "data/readings"))).resolve()


def session_history_dir(session_id):
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", session_id):
        raise ValueError("Invalid session identifier")
    destination = runtime_root() / "sessions" / session_id
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    return destination
