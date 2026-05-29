# YouTube Live Local

Local Windows app for launching looped video files as YouTube Live streams through Google OAuth and `ffmpeg`.

The app runs locally in a browser at `http://127.0.0.1:8765`. It is not a cloud service. OAuth files, channel tokens, uploaded videos, thumbnails, run history, and logs are stored on your own computer.

## Continuous Runtime

The stream runs only while the computer, this app, and the `ffmpeg` process are running. If you close the app window, shut down the PC, put the PC to sleep, lose internet, or stop the process, YouTube will stop receiving the stream.

For a 24/7 stream, use one of these options:

1. Keep the local computer powered on, prevent sleep mode, and use a stable internet connection.
2. Rent a server or VPS and run the app plus `ffmpeg` there continuously.

For testing and alpha releases, a local PC is enough. For production-like continuous streaming, a server is the safer choice.

## Current Features

- Connect a YouTube account through Google OAuth.
- Connect multiple YouTube channels and choose the active channel before launch.
- Create a YouTube Live broadcast from the app.
- Set title, description, and privacy: private, unlisted, or public.
- Upload a video file and send it to YouTube as a live stream.
- Loop the video indefinitely.
- Upload a broadcast thumbnail.
- Choose whether the broadcast recording should be saved, when YouTube allows it.
- Automatically transition the broadcast to live after YouTube detects the incoming stream.
- Automatically reconnect `ffmpeg` after temporary RTMP/RTMPS failures.
- Add a silent audio track when the source video has no audio.
- Show a clickable YouTube watch link after launch.

## Twitch And X/Twitter Status

The UI already reserves space for Twitch and X/Twitter, but in the current alpha they are marked `SOON` and disabled. This keeps the alpha focused on YouTube while the multistream UI remains visible.

The internal RTMP architecture already supports multiple outputs, but the public alpha is YouTube-first.

## First Run On Windows

Double-click:

```text
start.bat
```

On first run, the setup script checks and prepares dependencies:

- finds Python 3.10+;
- tries to install Python through `winget` if Python is missing;
- creates the local `.venv` environment;
- installs Python packages from `requirements.txt`;
- skips reinstalling packages on later runs unless `requirements.txt` changed or packages are missing;
- checks `ffmpeg` and `ffprobe`;
- tries to install `ffmpeg` through `winget` if it is missing;
- opens the app in the browser;
- starts the local server at `127.0.0.1:8765`.

If `winget` is unavailable or automatic installation fails, install these manually:

- [Python 3.10+](https://www.python.org/downloads/)
- [ffmpeg](https://ffmpeg.org/download.html)

Then run `start.bat` again.

## Manual Run

Use this only if you do not want to use `start.bat`:

```powershell
cd path\to\youtube-live-local
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## Google Cloud OAuth

Detailed setup guide: [GOOGLE_SETUP.md](GOOGLE_SETUP.md)

Short version:

1. Create a project in Google Cloud Console.
2. Enable YouTube Data API v3.
3. Create an OAuth Client of type `Web application`.
4. Add this authorized redirect URI:

```text
http://127.0.0.1:8765/oauth2callback
```

5. Download the OAuth client JSON.
6. Upload the JSON in the app.
7. Click `>add_channel`.
8. Sign in with the Google account that owns or manages the YouTube channel.
9. If the account has multiple channels, choose the needed channel in the app before launch.

The YouTube channel must have live streaming enabled. For new channels, YouTube may require a waiting period before Live becomes available.

## Launching A Broadcast

1. Run `start.bat`.
2. Open `http://127.0.0.1:8765` if the browser did not open automatically.
3. Upload the Google OAuth JSON.
4. Click `>add_channel` and connect the channel.
5. Choose the channel in the channel selector.
6. Choose a video file.
7. Enter title and description.
8. Choose privacy.
9. Upload a thumbnail if needed.
10. Click `>run`.

The app creates the YouTube broadcast, starts sending the video, and shows the watch link.

## Privacy Modes

- `Unlisted`: the stream should not appear in search, recommendations, or the channel page, but anyone with the link can open it.
- `Private`: only explicitly allowed Google accounts can open it.
- `Public`: visible to everyone.

## Local Data

All local data is stored in:

```text
.\data
```

This folder may contain:

- OAuth client JSON;
- connected channel tokens;
- uploaded videos;
- thumbnails;
- run history;
- `ffmpeg` logs.

Do not publish the `data` folder. It can contain tokens, private files, and local run history.

## Connection Drops

If `ffmpeg` exits because of a temporary RTMP/RTMPS network failure, the app tries to reconnect automatically. The YouTube broadcast is completed only when you click `>stop`; an unexpected `ffmpeg` exit does not automatically send a YouTube complete command.

Auto-reconnect helps with short network failures, but it does not replace a stable internet connection and an always-on machine.

## GitHub Metadata

Suggested repository description:

```text
Local Windows app for launching looped video files as YouTube Live streams through Google OAuth and ffmpeg.
```

Suggested topics:

```text
youtube-live, ffmpeg, fastapi, livestream, local-app, windows, oauth2
```

## Alpha Limitations

- YouTube is the main working platform.
- Twitch and X/Twitter are displayed as `SOON`.
- The app must run on the machine that sends the stream.
- If the computer shuts down or sleeps, the stream does not continue.
- Use a server for 24/7 streaming.
