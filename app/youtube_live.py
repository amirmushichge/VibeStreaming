from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .settings import (
    CLIENT_SECRET_FILE,
    OAUTH_STATE_FILE,
    PROFILE_INDEX_FILE,
    REDIRECT_URI,
    TOKEN_FILE,
    TOKENS_DIR,
    YOUTUBE_SCOPES,
)


class YouTubeSetupError(RuntimeError):
    pass


RETRYABLE_GOOGLE_ERROR_MARKERS = (
    "ssl",
    "tls",
    "unexpected_eof",
    "eof occurred",
    "connection reset",
    "connection aborted",
    "remote host closed",
    "timed out",
    "timeout",
    "winerror 10054",
)

YOUTUBE_API_CLIENT_OPTIONS = {"api_endpoint": "https://www.googleapis.com/"}


def has_client_secret() -> bool:
    return CLIENT_SECRET_FILE.exists()


def _empty_profile_index() -> dict[str, Any]:
    return {"active_channel_id": None, "channels": []}


def _read_profile_index() -> dict[str, Any]:
    if not PROFILE_INDEX_FILE.exists():
        return _empty_profile_index()
    try:
        data = json.loads(PROFILE_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_profile_index()
    if not isinstance(data, dict):
        return _empty_profile_index()
    data.setdefault("active_channel_id", None)
    data.setdefault("channels", [])
    if not isinstance(data["channels"], list):
        data["channels"] = []
    return data


def _write_profile_index(data: dict[str, Any]) -> None:
    PROFILE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_channel_id(channel_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", channel_id)
    if not safe:
        raise YouTubeSetupError("Invalid YouTube channel ID.")
    return safe


def _token_path_for_channel(channel_id: str) -> Path:
    return TOKENS_DIR / f"{_safe_channel_id(channel_id)}.json"


def _credentials_from_file(path: Path) -> Credentials:
    credentials = Credentials.from_authorized_user_file(str(path), YOUTUBE_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        path.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        raise YouTubeSetupError("The YouTube token is invalid. Connect the channel again.")
    return credentials


def _build_client_with_credentials(credentials: Credentials):
    return build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
        client_options=YOUTUBE_API_CLIENT_OPTIONS,
    )


def _looks_retryable_google_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in RETRYABLE_GOOGLE_ERROR_MARKERS)


def _google_network_error_message(action: str, exc: Exception) -> str:
    return (
        f"Google connection failed while {action}: {exc}. "
        "This usually means the server network, firewall, proxy, antivirus, or TLS inspection closed the HTTPS "
        "connection to Google. Try again once. If it repeats, check outbound HTTPS access to accounts.google.com, "
        "oauth2.googleapis.com, and youtube.googleapis.com, then restart the app."
    )


def _run_google_request_with_retry(action: str, callback):
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            return callback()
        except Exception as exc:
            last_exc = exc
            if not _looks_retryable_google_error(exc) or attempt == 3:
                break
            time.sleep(attempt)

    if last_exc and "invalid_grant" in f"{type(last_exc).__name__}: {last_exc}".lower():
        raise YouTubeSetupError(
            "Google rejected the OAuth code. This can happen if the one-time code was already used after a "
            "network retry. Go back to the app and click >add_channel again."
        ) from last_exc
    if last_exc and _looks_retryable_google_error(last_exc):
        raise YouTubeSetupError(_google_network_error_message(action, last_exc)) from last_exc
    if last_exc:
        raise last_exc
    raise YouTubeSetupError(f"Google connection failed while {action}.")


def _fetch_channels_for_credentials(credentials: Credentials) -> list[dict[str, Any]]:
    youtube = _build_client_with_credentials(credentials)
    response = youtube.channels().list(part="id,snippet,status", mine=True).execute()
    channels = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        status = item.get("status", {})
        channels.append(
            {
                "id": item.get("id"),
                "title": snippet.get("title") or item.get("id"),
                "customUrl": snippet.get("customUrl"),
                "privacyStatus": status.get("privacyStatus"),
            }
        )
    return channels


def _upsert_profile(channel: dict[str, Any], credentials_json: str, make_active: bool = True) -> None:
    channel_id = channel.get("id")
    if not channel_id:
        raise YouTubeSetupError("YouTube did not return a channel ID for the connected account.")

    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token_path = _token_path_for_channel(channel_id)
    token_path.write_text(credentials_json, encoding="utf-8")

    data = _read_profile_index()
    profile = {
        "id": channel_id,
        "title": channel.get("title") or channel_id,
        "customUrl": channel.get("customUrl"),
        "privacyStatus": channel.get("privacyStatus"),
        "token_file": str(token_path),
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    channels = [item for item in data["channels"] if item.get("id") != channel_id]
    channels.append(profile)
    channels.sort(key=lambda item: (item.get("title") or "").lower())
    data["channels"] = channels
    if make_active or not data.get("active_channel_id"):
        data["active_channel_id"] = channel_id
    _write_profile_index(data)


def migrate_legacy_token() -> None:
    data = _read_profile_index()
    if data["channels"] or not TOKEN_FILE.exists():
        return

    credentials = _credentials_from_file(TOKEN_FILE)
    channels = _fetch_channels_for_credentials(credentials)
    if not channels:
        return
    _upsert_profile(channels[0], credentials.to_json(), make_active=True)


def list_channel_profiles() -> list[dict[str, Any]]:
    migrate_legacy_token()
    data = _read_profile_index()
    profiles = []
    for profile in data["channels"]:
        token_file = profile.get("token_file")
        if token_file and Path(token_file).exists():
            profiles.append(
                {
                    "id": profile.get("id"),
                    "title": profile.get("title"),
                    "customUrl": profile.get("customUrl"),
                    "privacyStatus": profile.get("privacyStatus"),
                    "active": profile.get("id") == data.get("active_channel_id"),
                }
            )
    return profiles


def active_channel_id() -> str | None:
    migrate_legacy_token()
    data = _read_profile_index()
    active_id = data.get("active_channel_id")
    profiles = {profile.get("id") for profile in data["channels"]}
    if active_id in profiles:
        return active_id
    if data["channels"]:
        first_id = data["channels"][0].get("id")
        data["active_channel_id"] = first_id
        _write_profile_index(data)
        return first_id
    return None


def set_active_channel(channel_id: str) -> None:
    migrate_legacy_token()
    data = _read_profile_index()
    if channel_id not in {profile.get("id") for profile in data["channels"]}:
        raise YouTubeSetupError("This YouTube channel is not connected yet.")
    data["active_channel_id"] = channel_id
    _write_profile_index(data)


def has_token(channel_id: str | None = None) -> bool:
    migrate_legacy_token()
    if channel_id:
        path = _token_path_for_channel(channel_id)
        return path.exists()
    return bool(active_channel_id())


def get_auth_url() -> str:
    if not has_client_secret():
        raise YouTubeSetupError("Upload client_secret.json from Google Cloud first.")

    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET_FILE), scopes=YOUTUBE_SCOPES)
    flow.redirect_uri = REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent select_account",
    )
    OAUTH_STATE_FILE.write_text(state, encoding="utf-8")
    return auth_url


def finish_auth(code: str, state: str | None) -> dict[str, Any]:
    expected_state = OAUTH_STATE_FILE.read_text(encoding="utf-8").strip() if OAUTH_STATE_FILE.exists() else None
    if expected_state and state != expected_state:
        raise YouTubeSetupError("OAuth state mismatch. Repeat Google connection.")

    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET_FILE), scopes=YOUTUBE_SCOPES)
    flow.redirect_uri = REDIRECT_URI
    _run_google_request_with_retry("exchanging OAuth code for a token", lambda: flow.fetch_token(code=code))

    credentials = flow.credentials
    channels = _run_google_request_with_retry("reading YouTube channels", lambda: _fetch_channels_for_credentials(credentials))
    if not channels:
        raise YouTubeSetupError("No YouTube channel was found for the selected Google account.")

    # In normal YouTube OAuth, Google binds the token to the channel selected in
    # the consent flow, so this list usually contains one channel.
    channel = channels[0]
    _upsert_profile(channel, credentials.to_json(), make_active=True)

    if TOKEN_FILE.exists():
        backup = TOKEN_FILE.with_suffix(".legacy.json")
        if not backup.exists():
            shutil.copy2(TOKEN_FILE, backup)
    return channel


def clear_token(channel_id: str | None = None) -> None:
    migrate_legacy_token()
    data = _read_profile_index()
    target_id = channel_id or data.get("active_channel_id")
    if not target_id:
        return

    token_path = _token_path_for_channel(target_id)
    if token_path.exists():
        token_path.unlink()

    data["channels"] = [profile for profile in data["channels"] if profile.get("id") != target_id]
    if data.get("active_channel_id") == target_id:
        data["active_channel_id"] = data["channels"][0].get("id") if data["channels"] else None
    _write_profile_index(data)

    if not data["channels"] and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def get_credentials(channel_id: str | None = None) -> Credentials:
    migrate_legacy_token()
    target_id = channel_id or active_channel_id()
    if not target_id:
        raise YouTubeSetupError("No YouTube channel is connected yet.")

    token_path = _token_path_for_channel(target_id)
    if not token_path.exists():
        raise YouTubeSetupError("Token for the selected YouTube channel was not found. Connect the channel again.")

    return _credentials_from_file(token_path)


def build_youtube_client(channel_id: str | None = None):
    return _build_client_with_credentials(get_credentials(channel_id))


def http_error_message(error: HttpError) -> str:
    try:
        payload = json.loads(error.content.decode("utf-8"))
        details = payload.get("error", {}).get("errors", [])
        if details:
            reason = details[0].get("reason", "")
            message = details[0].get("message", "")
            if reason == "liveStreamingNotEnabled":
                return (
                    "Live streaming is not enabled for this YouTube channel yet. "
                    "Open YouTube Studio -> Create -> Go live, verify the channel, "
                    "and enable Live. YouTube may require up to 24 hours for first-time activation."
                )
            return f"{reason}: {message}".strip(": ")
        return payload.get("error", {}).get("message", str(error))
    except Exception:
        return str(error)


def http_error_reason(error: HttpError) -> str | None:
    try:
        payload = json.loads(error.content.decode("utf-8"))
        details = payload.get("error", {}).get("errors", [])
        if details:
            return details[0].get("reason")
    except Exception:
        return None
    return None


class YouTubeLiveService:
    def __init__(self, channel_id: str | None = None) -> None:
        self.channel_id = channel_id or active_channel_id()
        self.youtube = build_youtube_client(self.channel_id)

    def connected_channels(self) -> list[dict[str, Any]]:
        return _fetch_channels_for_credentials(get_credentials(self.channel_id))

    def create_broadcast(
        self,
        title: str,
        description: str,
        privacy_status: str,
        save_recording: bool,
    ) -> dict[str, Any]:
        scheduled_start = datetime.now(timezone.utc) + timedelta(seconds=30)
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": scheduled_start.isoformat(),
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "monitorStream": {"enableMonitorStream": False},
                "enableAutoStart": True,
                "enableAutoStop": False,
                "enableDvr": True,
                "recordFromStart": save_recording,
            },
        }
        return (
            self.youtube.liveBroadcasts()
            .insert(part="snippet,status,contentDetails", body=body)
            .execute()
        )

    def create_stream(self, title: str, description: str) -> dict[str, Any]:
        stream_title = f"{title[:112]} - local stream"
        body = {
            "snippet": {
                "title": stream_title[:128],
                "description": description[:10000],
            },
            "cdn": {
                "ingestionType": "rtmp",
                "resolution": "variable",
                "frameRate": "variable",
            },
            "contentDetails": {"isReusable": False},
        }
        return self.youtube.liveStreams().insert(part="snippet,cdn,contentDetails", body=body).execute()

    def bind(self, broadcast_id: str, stream_id: str) -> dict[str, Any]:
        return (
            self.youtube.liveBroadcasts()
            .bind(id=broadcast_id, streamId=stream_id, part="id,contentDetails,status")
            .execute()
        )

    def transition(self, broadcast_id: str, status: str) -> dict[str, Any]:
        return (
            self.youtube.liveBroadcasts()
            .transition(id=broadcast_id, broadcastStatus=status, part="id,status,contentDetails")
            .execute()
        )

    def get_broadcast_status(self, broadcast_id: str) -> dict[str, Any] | None:
        response = self.youtube.liveBroadcasts().list(part="id,status,snippet", id=broadcast_id).execute()
        items = response.get("items", [])
        return items[0] if items else None

    def get_stream_status(self, stream_id: str) -> dict[str, Any] | None:
        response = self.youtube.liveStreams().list(part="id,status", id=stream_id).execute()
        items = response.get("items", [])
        return items[0] if items else None

    def upload_thumbnail(self, broadcast_id: str, thumbnail_path: Path) -> dict[str, Any]:
        media = MediaFileUpload(str(thumbnail_path), resumable=False)
        return self.youtube.thumbnails().set(videoId=broadcast_id, media_body=media).execute()


def ingestion_url(stream: dict[str, Any]) -> str:
    info = stream.get("cdn", {}).get("ingestionInfo", {})
    address = info.get("rtmpsIngestionAddress") or info.get("ingestionAddress")
    stream_name = info.get("streamName")
    if not address or not stream_name:
        raise YouTubeSetupError("YouTube did not return an RTMP/RTMPS ingestion URL for the stream.")
    return f"{address.rstrip('/')}/{stream_name}"
