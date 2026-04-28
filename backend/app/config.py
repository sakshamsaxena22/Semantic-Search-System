"""
Central application config — reads from environment / .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Always resolve .env relative to the project root
_ROOT = Path(__file__).resolve().parents[3]   # SemanticSearchSystem/
load_dotenv(dotenv_path=_ROOT / ".env", override=True)


class Config:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    DATA_DIR: str = str(_ROOT / "backend" / "data")
    CHROMA_DIR: str = str(_ROOT / "backend" / "data" / "chroma_db")
    MAX_UPLOAD_BYTES: int = 16 * 1024 * 1024   # 16 MB
    CHUNK_SIZE: int = 500                        # characters per chunk