from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .settings import RTMP_DESTINATIONS_FILE


PRESET_DESTINATIONS = [
    {
        "platform": "twitch",
        "label": "Twitch",
        "server_url": "rtmp://ingest.global-contribute.live-video.net/app",
    },
    {
        "platform": "kick",
        "label": "Kick",
        "server_url": "",
    },
    {
        "platform": "x",
        "label": "X / Twitter",
        "server_url": "",
    },
    {
        "platform": "facebook",
        "label": "Facebook Live",
        "server_url": "rtmps://live-api-s.facebook.com:443/rtmp",
    },
    {
        "platform": "linkedin",
        "label": "LinkedIn Live",
        "server_url": "",
    },
    {
        "platform": "instagram",
        "label": "Instagram Live",
        "server_url": "",
    },
    {
        "platform": "tiktok",
        "label": "TikTok Live",
        "server_url": "",
    },
    {
        "platform": "custom",
        "label": "Custom RTMP",
        "server_url": "",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {"version": 1, "destinations": []}


def _read_store() -> dict[str, Any]:
    if not RTMP_DESTINATIONS_FILE.exists():
        return _empty_store()
    try:
        data = json.loads(RTMP_DESTINATIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", 1)
    data.setdefault("destinations", [])
    if not isinstance(data["destinations"], list):
        data["destinations"] = []
    return data


def _write_store(data: dict[str, Any]) -> None:
    RTMP_DESTINATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RTMP_DESTINATIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_id(value: str | None = None) -> str:
    if value:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", value.strip())
        if safe:
            return safe[:64]
    return f"rtmp_{uuid.uuid4().hex[:12]}"


def _clean_text(value: str, max_length: int) -> str:
    return " ".join((value or "").strip().split())[:max_length]


def _validate_server_url(server_url: str) -> str:
    value = (server_url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"rtmp", "rtmps"} or not parsed.netloc:
        raise ValueError("RTMP server URL must start with rtmp:// or rtmps:// and include a host.")
    return value.rstrip("/")


def public_destination(destination: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": destination.get("id"),
        "platform": destination.get("platform") or "custom",
        "label": destination.get("label") or "Custom RTMP",
        "server_url": destination.get("server_url") or "",
        "enabled": bool(destination.get("enabled")),
        "has_stream_key": bool(destination.get("stream_key")),
        "created_at": destination.get("created_at"),
        "updated_at": destination.get("updated_at"),
    }


def list_presets() -> list[dict[str, str]]:
    return [dict(item) for item in PRESET_DESTINATIONS]


def list_destinations(public: bool = True) -> list[dict[str, Any]]:
    destinations = _read_store()["destinations"]
    if public:
        return [public_destination(item) for item in destinations]
    return [dict(item) for item in destinations]


def save_destination(payload: dict[str, Any]) -> dict[str, Any]:
    data = _read_store()
    destinations = data["destinations"]
    destination_id = _safe_id(payload.get("id"))
    existing = next((item for item in destinations if item.get("id") == destination_id), None)

    platform = _clean_text(str(payload.get("platform") or "custom").lower(), 40) or "custom"
    label = _clean_text(str(payload.get("label") or ""), 80)
    if not label:
        preset = next((item for item in PRESET_DESTINATIONS if item["platform"] == platform), None)
        label = preset["label"] if preset else "Custom RTMP"

    server_url = _validate_server_url(str(payload.get("server_url") or ""))
    stream_key = str(payload.get("stream_key") or "").strip()
    if not stream_key and existing:
        stream_key = str(existing.get("stream_key") or "")
    if not stream_key:
        raise ValueError("Stream key is required.")

    now = _now()
    destination = {
        "id": destination_id,
        "platform": platform,
        "label": label,
        "server_url": server_url,
        "stream_key": stream_key,
        "enabled": bool(payload.get("enabled")),
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }

    destinations = [item for item in destinations if item.get("id") != destination_id]
    destinations.append(destination)
    destinations.sort(key=lambda item: ((item.get("label") or "").lower(), item.get("id") or ""))
    data["destinations"] = destinations
    _write_store(data)
    return public_destination(destination)


def set_destination_enabled(destination_id: str, enabled: bool) -> dict[str, Any]:
    data = _read_store()
    safe_id = _safe_id(destination_id)
    for destination in data["destinations"]:
        if destination.get("id") == safe_id:
            destination["enabled"] = bool(enabled)
            destination["updated_at"] = _now()
            _write_store(data)
            return public_destination(destination)
    raise ValueError("RTMP destination was not found.")


def delete_destination(destination_id: str) -> None:
    data = _read_store()
    safe_id = _safe_id(destination_id)
    next_destinations = [item for item in data["destinations"] if item.get("id") != safe_id]
    if len(next_destinations) == len(data["destinations"]):
        raise ValueError("RTMP destination was not found.")
    data["destinations"] = next_destinations
    _write_store(data)


def enabled_destinations() -> list[dict[str, Any]]:
    return [
        destination
        for destination in list_destinations(public=False)
        if destination.get("enabled")
    ]
