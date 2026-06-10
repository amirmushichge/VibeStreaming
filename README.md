# VibeStreaming

Local Windows app for launching looped video files as YouTube Live and multistream RTMP broadcasts through Google OAuth and `ffmpeg`.

The app runs locally in a browser at `http://127.0.0.1:8765`. It is not a cloud service. OAuth files, channel tokens, uploaded videos, thumbnails, run history, and logs are stored on your own computer.

## Creators

- Amir Mushich: [X / @AmirMushich](https://x.com/AmirMushich)
- Your AI Pulse: [X / @youraipulse](https://x.com/youraipulse)

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
- Upload a video file and send it to YouTube plus enabled RTMP destinations as live streams.
- Loop the video indefinitely.
- Upload a broadcast thumbnail.
- Choose whether the broadcast recording should be saved, when YouTube allows it.
- Automatically transition the broadcast to live after YouTube detects the incoming stream.
- Automatically reconnect `ffmpeg` after temporary RTMP/RTMPS failures.
- Add a silent audio track when the source video has no audio.
- Show a clickable YouTube watch link after launch.
- Add manual RTMP destinations for Twitch, Kick, X/Twitter, Facebook Live, LinkedIn Live, Instagram Live, TikTok Live, or any custom RTMP endpoint.
- Run each enabled destination in its own `ffmpeg` process so one platform can reconnect without stopping the others.

## Multistream Destinations

YouTube is still the primary automatic destination. Extra platforms are configured as manual RTMP destinations with a server URL and stream key.

Built-in presets are available for:

- Twitch
- Kick
- X/Twitter
- Facebook Live
- LinkedIn Live
- Instagram Live
- TikTok Live
- Custom RTMP

Some platforms provide permanent stream keys. Others generate temporary keys per event or require account eligibility, professional tools, subscriptions, or manual confirmation in their own live dashboard. VibeStreaming can send the video to any destination that gives you a valid RTMP or RTMPS URL plus stream key.

## First Run On Windows

Double-click:

```text
start.bat
```

On first run, the setup script checks and prepares dependencies:

- finds Python 3.10+;
- tries to install Python through `winget`, then Chocolatey, then a direct python.org installer, if Python is missing;
- creates the local `.venv` environment;
- installs Python packages from `requirements.txt`;
- skips reinstalling packages on later runs unless `requirements.txt` changed or packages are missing;
- checks `ffmpeg` and `ffprobe`;
- tries to install `ffmpeg` through `winget`, then Chocolatey, then a direct local download, if it is missing;
- opens the app in the browser;
- starts the local server at `127.0.0.1:8765`.

The first run needs internet access because it may download Python, `ffmpeg`, and Python packages.

If every automatic installation method fails, install these manually:

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
10. Add and enable RTMP destinations if you want to stream to more platforms.
11. Click `>run`.

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
- RTMP destination URLs and stream keys;
- run history;
- `ffmpeg` logs.

Do not publish the `data` folder. It can contain tokens, stream keys, private files, and local run history.

## Security For 24/7 Servers

When you run VibeStreaming on a rented Windows server or VPS, treat that server as the machine that owns the live stream session. The app is local, but the server still stores sensitive files in `.\data`.

Before running 24/7:

- Use a trusted VPS provider and a fresh Windows server image.
- Change the default RDP password immediately.
- Use a long unique administrator password.
- Keep Windows Firewall enabled.
- Do not expose port `8765` to the public internet.
- Open the app only inside the server session at `http://127.0.0.1:8765`.
- Do not upload `client_secret.json`, token files, RTMP stream keys, videos, thumbnails, or `.\data` to GitHub, chats, file-sharing links, or public storage.
- Do not run unknown cracked software, browser extensions, or untrusted scripts on the streaming server.
- Disable sleep mode and review Windows Update restart settings before long broadcasts.
- Keep enough disk space for uploaded videos, thumbnails, logs, and temporary files.

The most sensitive files are the connected channel tokens stored under `.\data\tokens` and RTMP stream keys stored in `.\data\rtmp_destinations.json`. They allow the app to manage YouTube Live broadcasts and publish video to configured platforms. If the server is compromised or you no longer trust it, stop the stream, delete the `.\data` folder on that server, reset RTMP keys on each platform, and revoke the app access from your Google Account security settings.

## OAuth Troubleshooting On VPS

If Google login returns an SSL error such as `UNEXPECTED_EOF_WHILE_READING`, the OAuth callback reached the app, but the server failed while making an outbound HTTPS request back to Google.

On the rented server, check that these URLs open in the browser:

```text
https://accounts.google.com
https://oauth2.googleapis.com
https://www.googleapis.com
https://youtube.googleapis.com
```

Then try:

- restart `start.bat` and repeat `>add_channel`;
- update Windows root certificates through Windows Update;
- disable or reconfigure antivirus HTTPS inspection if it is installed;
- make sure the provider, firewall, or proxy is not blocking outbound HTTPS to Google;
- try another VPS provider if Google HTTPS connections are unstable on that server.

VibeStreaming uses `www.googleapis.com` for YouTube Data API calls because some VPS networks fail TLS handshakes with `youtube.googleapis.com`.

For the same reason, the app prefers YouTube's plain `rtmp://` ingestion address when YouTube returns both RTMP and RTMPS addresses. Some rented Windows servers fail the RTMPS TLS connection to `a.rtmps.youtube.com:443`, while RTMP on port `1935` still works.

## Connection Drops

If `ffmpeg` exits because of a temporary RTMP/RTMPS network failure, the app tries to reconnect automatically. The YouTube broadcast is completed only when you click `>stop`; an unexpected `ffmpeg` exit does not automatically send a YouTube complete command.

Auto-reconnect helps with short network failures, but it does not replace a stable internet connection and an always-on machine.

## GitHub Metadata

Suggested repository description:

```text
Local Windows app for launching looped video files as YouTube Live and multistream RTMP broadcasts.
```

Suggested topics:

```text
youtube-live, multistream, rtmp, ffmpeg, fastapi, livestream, local-app, windows, oauth2
```

## Alpha Limitations

- YouTube is the main automatic platform.
- Extra platforms require you to provide a valid RTMP/RTMPS URL and stream key.
- The app must run on the machine that sends the stream.
- If the computer shuts down or sleeps, the stream does not continue.
- Use a server for 24/7 streaming.
