from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .settings import LOGS_DIR, RUN_HISTORY_FILE


class StreamAlreadyRunningError(RuntimeError):
    pass


class StreamManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.current: dict[str, Any] | None = None
        self.logs: deque[str] = deque(maxlen=160)
        self._redactions: list[str] = []
        self._commands: dict[str, list[str]] = {}
        self._log_paths: dict[str, Path] = {}
        self._restart_counts: dict[str, int] = {}
        self._restart_on_failure = True
        self._max_restarts = 20
        self._stop_requested = False
        self._creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    def is_running(self) -> bool:
        with self._lock:
            return any(process.poll() is None for process in self.processes.values()) or (
                self.process is not None and self.process.poll() is None
            )

    def is_output_running(self, output_name: str) -> bool:
        with self._lock:
            process = self.processes.get(output_name)
            if process is None and output_name == "youtube":
                process = self.process
            return process is not None and process.poll() is None

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = any(process.poll() is None for process in self.processes.values()) or (
                self.process is not None and self.process.poll() is None
            )
            current = dict(self.current) if self.current else None
            if current:
                statuses = {}
                for name, process in self.processes.items():
                    statuses[name] = {
                        "running": process.poll() is None,
                        "returncode": process.poll(),
                        "restart_count": self._restart_counts.get(name, 0),
                    }
                if not statuses and self.process is not None:
                    statuses["youtube"] = {
                        "running": self.process.poll() is None,
                        "returncode": self.process.poll(),
                        "restart_count": self._restart_counts.get("youtube", 0),
                    }
                current["output_statuses"] = statuses
            return {
                "running": running,
                "current": current,
                "logs": list(self.logs)[-80:],
            }

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.logs.append(f"[{timestamp}] {message}")

    def start(
        self,
        command: list[str] | dict[str, list[str]],
        metadata: dict[str, Any],
        on_exit: Callable[[int | None], None] | None = None,
        redactions: list[str] | None = None,
        restart_on_failure: bool = True,
        max_restarts: int = 20,
    ) -> None:
        with self._lock:
            if any(process.poll() is None for process in self.processes.values()) or (
                self.process is not None and self.process.poll() is None
            ):
                raise StreamAlreadyRunningError("Stream is already running.")

            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            started_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            commands = {"youtube": command} if isinstance(command, list) else command
            log_paths = {
                name: LOGS_DIR / f"ffmpeg-{started_stamp}-{name}.log"
                for name in commands
            }
            metadata = {
                **metadata,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ffmpeg_logs": {name: str(path) for name, path in log_paths.items()},
            }
            if len(log_paths) == 1:
                metadata["ffmpeg_log"] = str(next(iter(log_paths.values())))

            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            self.process = None
            self.processes = {}
            self._commands = commands
            self._log_paths = log_paths
            self._restart_counts = {name: 0 for name in commands}
            self._restart_on_failure = restart_on_failure
            self._max_restarts = max_restarts
            self._stop_requested = False
            self._creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            self._redactions = sorted(
                {item for item in (redactions or []) if item and len(item) >= 4},
                key=len,
                reverse=True,
            )
            try:
                for name, item_command in commands.items():
                    self.processes[name] = self._popen(item_command, creation_flags)
                if len(self.processes) == 1:
                    self.process = next(iter(self.processes.values()))
            except Exception:
                for process in self.processes.values():
                    if process.poll() is None:
                        process.terminate()
                self.process = None
                self.processes = {}
                raise

            self.current = metadata
            self.logs.clear()
            output_names = ", ".join(commands)
            self.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ffmpeg started: {output_names}.")

        RUN_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with RUN_HISTORY_FILE.open("a", encoding="utf-8") as history:
            history.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        for name, process in self.processes.items():
            threading.Thread(target=self._read_stderr, args=(name, process, log_paths[name]), daemon=True).start()
            threading.Thread(target=self._wait_for_exit, args=(name, process, on_exit), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            processes = list(self.processes.values()) or ([self.process] if self.process else [])

        processes = [process for process in processes if process is not None and process.poll() is None]
        if not processes:
            self.append_log("ffmpeg is already stopped.")
            return

        self.append_log("Stopping ffmpeg.")
        for process in processes:
            try:
                if process.stdin:
                    process.stdin.write("q\n")
                    process.stdin.flush()
            except Exception:
                pass

        deadline = time.monotonic() + 15
        for process in processes:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.terminate()

        for process in processes:
            if process.poll() is None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

    def _redact(self, line: str) -> str:
        for value in self._redactions:
            line = line.replace(value, "[secret]")
        return line

    def _popen(self, command: list[str], creation_flags: int) -> subprocess.Popen[str]:
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )

    def _read_stderr(self, name: str, process: subprocess.Popen[str], log_path: Path) -> None:
        with log_path.open("a", encoding="utf-8") as log_file:
            if not process.stderr:
                return
            for raw_line in process.stderr:
                line = self._redact(raw_line.strip())
                if not line:
                    continue
                log_file.write(line + "\n")
                log_file.flush()
                with self._lock:
                    self.logs.append(f"{name}: {line}")

    def _wait_for_exit(
        self,
        name: str,
        process: subprocess.Popen[str],
        on_exit: Callable[[int | None], None] | None,
    ) -> None:
        code = process.wait()
        self.append_log(f"ffmpeg {name} exited with code {code}.")

        with self._lock:
            is_current = self.processes.get(name) is process
            stop_requested = self._stop_requested
            command = self._commands.get(name)
            log_path = self._log_paths.get(name)
            restart_count = self._restart_counts.get(name, 0)
            can_restart = (
                is_current
                and not stop_requested
                and code != 0
                and self._restart_on_failure
                and command is not None
                and log_path is not None
                and restart_count < self._max_restarts
            )
            if can_restart:
                self._restart_counts[name] = restart_count + 1

        if can_restart and command is not None and log_path is not None:
            delay = min(60, 5 + restart_count * 5)
            self.append_log(f"ffmpeg {name}: unexpected exit, reconnecting in {delay} seconds.")
            time.sleep(delay)
            with self._lock:
                if self._stop_requested or self.processes.get(name) is not process:
                    return
            try:
                new_process = self._popen(command, self._creation_flags)
            except Exception as exc:
                self.append_log(f"ffmpeg {name}: restart failed: {exc}")
                new_process = None
            with self._lock:
                if new_process is None:
                    return
                if self._stop_requested or self.processes.get(name) is not process:
                    if new_process.poll() is None:
                        new_process.terminate()
                    return
                self.processes[name] = new_process
                if len(self.processes) == 1:
                    self.process = new_process
            self.append_log(f"ffmpeg {name}: reconnect started.")
            threading.Thread(target=self._read_stderr, args=(name, new_process, log_path), daemon=True).start()
            threading.Thread(target=self._wait_for_exit, args=(name, new_process, on_exit), daemon=True).start()
            return

        should_call_exit = False
        with self._lock:
            if self.process is process:
                self.process = None
            should_call_exit = not any(item.poll() is None for item in self.processes.values())
        if on_exit and should_call_exit and self._stop_requested:
            on_exit(code)


def media_binary(name: str) -> str:
    if name == "ffmpeg":
        return os.environ.get("FFMPEG_BIN", "ffmpeg")
    if name == "ffprobe":
        explicit = os.environ.get("FFPROBE_BIN")
        if explicit:
            return explicit
        ffmpeg_bin = os.environ.get("FFMPEG_BIN")
        if ffmpeg_bin:
            sibling = Path(ffmpeg_bin).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
            if sibling.exists():
                return str(sibling)
        return "ffprobe"
    return name


def probe_has_audio(video_path: Path) -> bool:
    command = [
        media_binary("ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    return result.returncode == 0 and bool(result.stdout.strip())


def build_ffmpeg_command(video_path: Path, output_url: str) -> list[str]:
    has_audio = probe_has_audio(video_path)
    command = [
        media_binary("ffmpeg"),
        "-hide_banner",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        str(video_path),
    ]

    if has_audio:
        command += ["-map", "0:v:0", "-map", "0:a:0"]
    else:
        command += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]

    command += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-max_muxing_queue_size",
        "1024",
        "-f",
        "flv",
        output_url,
    ]
    return command


def build_rtmp_output_url(base_url: str, stream_key: str) -> str:
    base_url = base_url.strip()
    stream_key = stream_key.strip()
    if not base_url:
        raise ValueError("RTMP URL is required.")
    if not stream_key:
        raise ValueError("Stream key is required.")
    return f"{base_url.rstrip('/')}/{stream_key.lstrip('/')}"


def wait_then_go_live(
    manager: StreamManager,
    broadcast_id: str,
    stream_id: str,
    service_factory,
    output_name: str = "youtube",
) -> None:
    manager.append_log("Waiting for YouTube to detect the incoming stream.")
    inactive_checks = 0
    for _ in range(60):
        if not manager.is_output_running(output_name):
            inactive_checks += 1
            if inactive_checks >= 6:
                manager.append_log("Auto-transition canceled: ffmpeg is not running.")
                return
            time.sleep(5)
            continue
        inactive_checks = 0
        try:
            service = service_factory()
            stream = service.get_stream_status(stream_id)
            stream_status = (stream or {}).get("status", {}).get("streamStatus")
            if stream_status:
                manager.append_log(f"YouTube streamStatus: {stream_status}.")
            if stream_status == "active":
                try:
                    service.transition(broadcast_id, "live")
                    manager.append_log("Live transition command sent.")
                except Exception as exc:
                    manager.append_log(f"YouTube may already be auto-starting the stream: {exc}")
                return
        except Exception as exc:
            manager.append_log(f"YouTube status check failed: {exc}")
        time.sleep(5)
    manager.append_log("YouTube did not confirm an active stream within 5 minutes.")
