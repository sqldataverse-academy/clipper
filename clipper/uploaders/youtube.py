"""Uploads a reel to YouTube as a Short using the official YouTube Data API v3."""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .. import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_credentials(interactive: bool = True) -> Credentials:
    creds = None
    if config.YOUTUBE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_FILE), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not interactive:
            raise RuntimeError("YouTube is not connected yet. Run: python connect_youtube.py")
        if not config.YOUTUBE_CLIENT_SECRETS.exists():
            raise RuntimeError(f"Missing {config.YOUTUBE_CLIENT_SECRETS}. See SETUP.md, step 3.")
        flow = InstalledAppFlow.from_client_secrets_file(str(config.YOUTUBE_CLIENT_SECRETS), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
    config.YOUTUBE_TOKEN_FILE.write_text(creds.to_json())
    return creds


def upload(file: Path, title: str, description: str, tags: list[str]) -> dict:
    creds = get_credentials(interactive=False)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    if "#shorts" not in (title + description).lower():
        description = f"{description}\n\n#Shorts".strip()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:15],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": config.YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(file), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    try:
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=5)
    except HttpError as e:
        reason = e.reason or str(e)
        if e.resp.status == 403 and "quota" in str(e).lower():
            reason = "YouTube daily upload quota reached; it resets at midnight Pacific time."
        raise RuntimeError(f"YouTube: {reason}") from e
    vid = response["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}
