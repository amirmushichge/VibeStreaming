from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
LOGS_DIR = DATA_DIR / "logs"
TOKENS_DIR = DATA_DIR / "tokens"

CLIENT_SECRET_FILE = DATA_DIR / "client_secret.json"
TOKEN_FILE = DATA_DIR / "token.json"
PROFILE_INDEX_FILE = DATA_DIR / "channel_profiles.json"
OAUTH_STATE_FILE = DATA_DIR / "oauth_state.txt"
RUN_HISTORY_FILE = DATA_DIR / "runs.jsonl"

APP_HOST = "127.0.0.1"
APP_PORT = 8765
REDIRECT_URI = f"http://{APP_HOST}:{APP_PORT}/oauth2callback"

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOADS_DIR, THUMBNAILS_DIR, LOGS_DIR, TOKENS_DIR):
        path.mkdir(parents=True, exist_ok=True)
