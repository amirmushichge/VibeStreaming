from __future__ import annotations

from html import escape
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from googleapiclient.errors import HttpError

from .settings import (
    APP_HOST,
    APP_PORT,
    CLIENT_SECRET_FILE,
    DATA_DIR,
    THUMBNAILS_DIR,
    UPLOADS_DIR,
    ensure_dirs,
)
from .stream_manager import (
    StreamAlreadyRunningError,
    StreamManager,
    build_ffmpeg_command,
    build_rtmp_output_url,
    wait_then_go_live,
)
from .youtube_live import (
    YouTubeLiveService,
    YouTubeSetupError,
    active_channel_id,
    clear_token,
    finish_auth,
    get_auth_url,
    has_client_secret,
    has_token,
    http_error_message,
    http_error_reason,
    ingestion_url,
    list_channel_profiles,
    set_active_channel,
)

ensure_dirs()

app = FastAPI(title="YouTube Live Local")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
stream_manager = StreamManager()


def error_page(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    return HTMLResponse(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{escape(title)}</title></head><body>"
            f"<h1>{escape(title)}</h1>"
            f"<p>{escape(message)}</p>"
            "<p><a href='/'>Back</a></p>"
            "</body></html>"
        ),
        status_code=status_code,
    )


def safe_filename(filename: str) -> str:
    source = Path(filename or "upload.bin").name
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in source)
    return safe[:120] or "upload.bin"


def save_upload(upload: UploadFile, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_filename(upload.filename)}"
    with target.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return target


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "client_secret_path": str(CLIENT_SECRET_FILE),
            "data_dir": str(DATA_DIR),
            "app_url": f"http://{APP_HOST}:{APP_PORT}",
        },
    )


@app.get("/api/status")
def api_status():
    channel_error = None
    channels = []
    active_id = None
    authorized = False
    try:
        channels = list_channel_profiles()
        active_id = active_channel_id()
        authorized = has_token()
    except Exception as exc:
        channel_error = str(exc)
    return {
        "client_secret": has_client_secret(),
        "authorized": authorized,
        "channels": channels,
        "active_channel_id": active_id,
        "channel_error": channel_error,
        "features": {"multistream": True, "version": 4},
        "stream": stream_manager.status(),
    }


@app.post("/api/client-secret")
def upload_client_secret(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="OAuth client JSON file is required.")
    with CLIENT_SECRET_FILE.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return {"ok": True, "path": str(CLIENT_SECRET_FILE)}


@app.get("/auth/login")
def auth_login():
    try:
        return RedirectResponse(get_auth_url())
    except YouTubeSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/oauth2callback", response_class=HTMLResponse)
def oauth2callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return error_page("Google OAuth error", error)
    if not code:
        return error_page("Missing OAuth code", "Google did not return an OAuth code.")
    try:
        channel = finish_auth(code, state)
    except YouTubeSetupError as exc:
        return error_page("Could not connect Google", str(exc))
    except Exception as exc:
        return error_page("Could not connect Google", str(exc))
    title = channel.get("title") or channel.get("id") or "YouTube"
    handle = f" ({channel.get('customUrl')})" if channel.get("customUrl") else ""
    return HTMLResponse(
        f"<h1>YouTube connected</h1><p>Channel: {escape(title + handle)}</p><p><a href='/'>Open app</a></p>"
    )


@app.post("/api/logout")
def logout():
    clear_token()
    return {"ok": True}


@app.post("/api/active-channel")
def active_channel(channel_id: str = Form(...)):
    try:
        set_active_channel(channel_id)
    except YouTubeSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "active_channel_id": channel_id}


@app.post("/api/start")
def start_stream(
    video: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    privacy: str = Form("unlisted"),
    save_recording: bool = Form(True),
    channel_id: str = Form(""),
    enable_twitch: bool = Form(False),
    twitch_url: str = Form(""),
    twitch_key: str = Form(""),
    enable_x: bool = Form(False),
    x_url: str = Form(""),
    x_key: str = Form(""),
    thumbnail: UploadFile | None = File(None),
):
    if stream_manager.is_running():
        raise HTTPException(status_code=409, detail="Stream is already running.")
    if privacy not in {"private", "unlisted", "public"}:
        raise HTTPException(status_code=400, detail="Invalid privacy setting.")
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title is required.")
    selected_channel_id = channel_id or active_channel_id()
    if not has_client_secret() or not selected_channel_id or not has_token(selected_channel_id):
        raise HTTPException(status_code=400, detail="Connect Google OAuth first.")

    try:
        extra_outputs: list[dict[str, str]] = []
        if enable_twitch:
            extra_outputs.append(
                {
                    "id": "twitch",
                    "label": "Twitch",
                    "url": build_rtmp_output_url(twitch_url, twitch_key),
                    "key": twitch_key.strip(),
                }
            )
        if enable_x:
            extra_outputs.append(
                {
                    "id": "x",
                    "label": "X/Twitter",
                    "url": build_rtmp_output_url(x_url, x_key),
                    "key": x_key.strip(),
                }
            )

        set_active_channel(selected_channel_id)
        video_path = save_upload(video, UPLOADS_DIR)
        thumbnail_path = None
        if thumbnail and thumbnail.filename:
            thumbnail_path = save_upload(thumbnail, THUMBNAILS_DIR)

        service = YouTubeLiveService(selected_channel_id)
        recording_forced = False
        try:
            broadcast = service.create_broadcast(title.strip(), description, privacy, save_recording)
        except HttpError as exc:
            if not save_recording and http_error_reason(exc) == "disableRecordingNotAllowed":
                save_recording = True
                recording_forced = True
                broadcast = service.create_broadcast(title.strip(), description, privacy, save_recording)
            else:
                raise
        stream = service.create_stream(title.strip(), description)
        service.bind(broadcast["id"], stream["id"])
        if thumbnail_path:
            try:
                service.upload_thumbnail(broadcast["id"], thumbnail_path)
            except Exception as exc:
                stream_manager.append_log(f"Thumbnail upload failed: {exc}")

        output_url = ingestion_url(stream)
        outputs = [
            {"id": "youtube", "label": "YouTube", "url": output_url},
            *extra_outputs,
        ]
        commands = {
            output["id"]: build_ffmpeg_command(video_path, output["url"])
            for output in outputs
        }
        redactions = [output["url"] for output in outputs] + [
            output["key"] for output in extra_outputs if output.get("key")
        ]
        broadcast_url = f"https://www.youtube.com/watch?v={broadcast['id']}"

        metadata = {
            "title": title.strip(),
            "description": description,
            "privacy": privacy,
            "save_recording": save_recording,
            "broadcast_id": broadcast["id"],
            "stream_id": stream["id"],
            "broadcast_url": broadcast_url,
            "channel_id": selected_channel_id,
            "outputs": [
                {
                    "id": output["id"],
                    "label": output["label"],
                    "enabled": True,
                }
                for output in outputs
            ],
            "video_path": str(video_path),
            "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
        }

        def complete_on_ffmpeg_exit(_code: int | None) -> None:
            if not has_token(selected_channel_id):
                return
            try:
                YouTubeLiveService(selected_channel_id).transition(broadcast["id"], "complete")
                stream_manager.append_log("YouTube broadcast completed after ffmpeg stopped.")
            except Exception as exc:
                stream_manager.append_log(f"YouTube auto-complete failed: {exc}")

        stream_manager.start(commands, metadata, on_exit=complete_on_ffmpeg_exit, redactions=redactions)
        if recording_forced:
            stream_manager.append_log("YouTube did not allow recording to be disabled; broadcast started with recording enabled.")
        threading.Thread(
            target=wait_then_go_live,
            args=(stream_manager, broadcast["id"], stream["id"], lambda: YouTubeLiveService(selected_channel_id), "youtube"),
            daemon=True,
        ).start()
        return {
            "ok": True,
            "broadcast_url": broadcast_url,
            "outputs": [{"id": output["id"], "label": output["label"]} for output in outputs],
        }
    except StreamAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HttpError as exc:
        raise HTTPException(status_code=400, detail=http_error_message(exc)) from exc
    except YouTubeSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stop")
def stop_stream():
    status = stream_manager.status()
    current = status.get("current") or {}
    broadcast_id = current.get("broadcast_id")
    channel_id = current.get("channel_id")

    if broadcast_id and channel_id and has_token(channel_id):
        try:
            YouTubeLiveService(channel_id).transition(broadcast_id, "complete")
            stream_manager.append_log("YouTube broadcast complete command sent.")
        except Exception as exc:
            stream_manager.append_log(f"YouTube complete command failed: {exc}")

    stream_manager.stop()
    return {"ok": True}


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
