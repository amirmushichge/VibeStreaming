# How To Get The Google OAuth JSON

This JSON file lets the app create YouTube Live broadcasts on behalf of the connected Google account. It is not an API key and it is not the stream key from YouTube Studio. You need an OAuth client JSON from Google Cloud.

The app uses this local callback:

```text
http://127.0.0.1:8765/oauth2callback
```

For this project, create an OAuth Client of type `Web application` and add that callback to `Authorized redirect URIs`.

## Requirements

- A Google account that owns or manages the target YouTube channel.
- Live streaming enabled on that YouTube channel.
- Access to Google Cloud Console.
- The local app running at `http://127.0.0.1:8765`.

If the channel is new, YouTube may not enable Live immediately. First-time activation can require a waiting period.

## 1. Create A Google Cloud Project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Use the project selector in the top bar.
3. Click `New project`.
4. Name it, for example:

```text
YouTube Live Local
```

5. Click `Create`.
6. Make sure the new project is selected in the top bar.

## 2. Enable YouTube Data API v3

1. Open [YouTube Data API v3 in Google Cloud](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
2. Check that the correct project is selected.
3. Click `Enable`.

If the button says `Manage`, the API is already enabled.

## 3. Configure The OAuth Consent Screen

In the newer Google UI this can be called `Google Auth Platform`. In the older UI the path is usually `APIs & Services` -> `OAuth consent screen`.

1. Open `OAuth consent screen` or `Google Auth Platform`.
2. If Google asks for user type:
   - choose `External` for a normal Google account;
   - choose `Internal` only for a Google Workspace app limited to your organization.
3. Fill the basic fields:
   - `App name`: `YouTube Live Local`
   - `User support email`: your email
   - `Developer contact information`: your email
4. In `Audience`, keep `Testing` if the app is only for you or a small team.
5. In `Test users`, add the email of the Google account that will connect the YouTube channel.

If the YouTube channel is a Brand Account, add the Google account email that manages the Brand Account. Do not add the channel handle.

## 4. Add The YouTube Scope

If Google Cloud asks for scopes, add this YouTube Data API scope:

```text
https://www.googleapis.com/auth/youtube.force-ssl
```

This scope lets the app create live broadcasts, create live streams, upload thumbnails, and complete broadcasts.

If the interface does not ask for scopes during setup, that is fine. The app requests the needed scope during the Google sign-in flow.

## 5. Create The OAuth Client

1. Open `Google Auth Platform` -> `Clients`.
2. In the older UI, open `APIs & Services` -> `Credentials`.
3. Click `Create client` or `Create credentials` -> `OAuth client ID`.
4. For `Application type`, choose:

```text
Web application
```

5. In `Name`, enter:

```text
YouTube Live Local localhost
```

6. In `Authorized JavaScript origins`, you can add:

```text
http://127.0.0.1:8765
```

7. In `Authorized redirect URIs`, add exactly:

```text
http://127.0.0.1:8765/oauth2callback
```

8. Click `Create`.

Do not add a trailing slash. The URI must end with `/oauth2callback`.

## 6. Download The JSON

After creating the OAuth Client:

1. Open the client in the list.
2. Click `Download JSON`.
3. Save the file on your computer.

The file name can look like this:

```text
client_secret_1234567890-abcdefg.apps.googleusercontent.com.json
```

Inside, it should look similar to this:

```json
{
  "web": {
    "client_id": "...apps.googleusercontent.com",
    "project_id": "...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_secret": "...",
    "redirect_uris": [
      "http://127.0.0.1:8765/oauth2callback"
    ]
  }
}
```

If the root key is `"installed"` instead of `"web"`, the JSON is from a `Desktop app` client. A desktop client can work for installed-app flows, but this local app uses a fixed localhost callback, so `Web application` is the recommended client type.

## 7. Upload The JSON In The App

1. Run the app through `start.bat`.
2. Open:

```text
http://127.0.0.1:8765
```

3. In the `OAuth JSON` field, choose the downloaded JSON file.
4. Click `>upload_json`.
5. After upload, click `>add_channel`.
6. Sign in with the Google account that manages the target YouTube channel.
7. Allow access.
8. Return to the app and choose the channel in the `Channel` field.

The app stores the OAuth client JSON locally here:

```text
.\data\client_secret.json
```

Connected channel tokens are stored locally here:

```text
.\data\tokens
```

Do not publish the `data` folder to GitHub.

## Common Errors

### redirect_uri_mismatch

The OAuth Client does not contain the app redirect URI, or the client type is wrong.

Check:

```text
Application type: Web application
Authorized redirect URIs: http://127.0.0.1:8765/oauth2callback
```

After changing Google Cloud settings, wait a few minutes, download the JSON again, and upload the new JSON in the app.

### App has not completed verification

For personal use, this is usually expected. If the project is in `Testing`, Google shows an unverified app warning. Continue only if you created this Google Cloud project yourself.

If Google does not let you continue, add your email in `Test users` on the OAuth consent screen.

### access_denied

This usually means access was denied on the Google screen, or the current Google account is not listed in `Test users`.

Check `Test users` and click `>add_channel` again.

### liveStreamingNotEnabled

Live streaming is not enabled on the selected YouTube channel. Open YouTube Studio and enable live streaming for that channel. New channels may require a waiting period before Live becomes available.

### NoLinkedYouTubeAccount

The selected Google account does not have a YouTube channel, or the wrong Google account was selected. Sign in with the account that owns or manages the target channel.

### JSON Is Loaded But Google Opens The Wrong Account

Click `>add_channel` again and choose another account on the Google screen. If the browser automatically selects the wrong account, open Google in the browser, sign out of extra accounts, or use the account chooser in the OAuth flow.

## What You Do Not Need

This app does not need:

- an `API key`;
- a `Service account`;
- a YouTube Studio stream key;
- an OAuth client of type Android, iOS, or Chrome Extension.

It needs an OAuth Client JSON of type `Web application`.
