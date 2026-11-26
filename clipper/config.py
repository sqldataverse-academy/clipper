"""Loads settings from the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-opus-5-5")

DEFAULT_NUM_CLIPS = int(_get("DEFAULT_NUM_CLIPS", "8"))
MIN_CLIP_SECONDS = int(_get("MIN_CLIP_SECONDS", "25"))
MAX_CLIP_SECONDS = int(_get("MAX_CLIP_SECONDS", "60"))

WHISPER_MODEL = _get("WHISPER_MODEL", "small")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "cpu")
CAPTION_LANGUAGE = _get("CAPTION_LANGUAGE") or None
POST_LANGUAGE = _get("POST_LANGUAGE", "English")

YOUTUBE_CLIENT_SECRETS = _path(_get("YOUTUBE_CLIENT_SECRETS", "secrets/client_secret.json"))
YOUTUBE_TOKEN_FILE = ROOT / "secrets" / "youtube_token.json"
YOUTUBE_PRIVACY = _get("YOUTUBE_PRIVACY", "public")

META_PAGE_ACCESS_TOKEN = _get("META_PAGE_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = _get("FACEBOOK_PAGE_ID")
INSTAGRAM_USER_ID = _get("INSTAGRAM_USER_ID")
META_GRAPH_VERSION = _get("META_GRAPH_VERSION", "v21.0")

DATA_DIR = _path(_get("DATA_DIR", "data"))
DOWNLOADS_DIR = DATA_DIR / "downloads"
CLIPS_DIR = DATA_DIR / "clips"
DB_PATH = DATA_DIR / "clipper.db"
PORT = int(_get("PORT", "8000"))

for d in (DATA_DIR, DOWNLOADS_DIR, CLIPS_DIR, ROOT / "secrets"):
    d.mkdir(parents=True, exist_ok=True)


def platform_status() -> dict:
    """Which upload targets are configured."""
    return {
        "youtube": YOUTUBE_CLIENT_SECRETS.exists(),
        "instagram": bool(META_PAGE_ACCESS_TOKEN and INSTAGRAM_USER_ID),
        "facebook": bool(META_PAGE_ACCESS_TOKEN and FACEBOOK_PAGE_ID),
        "claude": bool(os.getenv("ANTHROPIC_API_KEY")),
    }
