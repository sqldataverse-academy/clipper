"""Uploads reels to Instagram and Facebook with the official Meta Graph API.

Both use Meta's resumable upload, so the video goes straight from your PC
(no public hosting needed).
"""
import time
from pathlib import Path

import requests

from .. import config


def _graph(path: str) -> str:
    return f"https://graph.facebook.com/{config.META_GRAPH_VERSION}/{path}"


def _check(r: requests.Response, what: str) -> dict:
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400 or "error" in data:
        msg = data.get("error", {}).get("message") or r.text[:300]
        raise RuntimeError(f"{what}: {msg}")
    return data


def _token() -> str:
    if not config.META_PAGE_ACCESS_TOKEN:
        raise RuntimeError("META_PAGE_ACCESS_TOKEN is not set in .env (see SETUP.md).")
    return config.META_PAGE_ACCESS_TOKEN


# ------------------------------------------------------------------ Instagram

def upload_instagram(file: Path, caption: str) -> dict:
    token, ig = _token(), config.INSTAGRAM_USER_ID
    if not ig:
        raise RuntimeError("INSTAGRAM_USER_ID is not set in .env.")

    # 1) Create a resumable Reels container
    data = _check(requests.post(_graph(f"{ig}/media"), data={
        "media_type": "REELS", "upload_type": "resumable",
        "caption": caption[:2200], "share_to_feed": "true", "access_token": token,
    }, timeout=60), "Instagram create container")
    container_id, upload_uri = data["id"], data["uri"]

    # 2) Send the file bytes
    size = file.stat().st_size
    with open(file, "rb") as f:
        _check(requests.post(upload_uri, data=f, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
        }, timeout=900), "Instagram upload")

    # 3) Wait for Instagram to process it
    for _ in range(90):  # up to ~15 minutes
        st = _check(requests.get(_graph(container_id), params={
            "fields": "status_code,status", "access_token": token}, timeout=30), "Instagram status")
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram took too long to process the video.")

    # 4) Publish
    pub = _check(requests.post(_graph(f"{ig}/media_publish"), data={
        "creation_id": container_id, "access_token": token}, timeout=60), "Instagram publish")
    media_id = pub["id"]
    link = ""
    try:
        link = requests.get(_graph(media_id), params={"fields": "permalink", "access_token": token},
                            timeout=30).json().get("permalink", "")
    except Exception:
        pass
    return {"id": media_id, "url": link}


# ------------------------------------------------------------------ Facebook

def upload_facebook(file: Path, description: str, title: str = "") -> dict:
    token, page = _token(), config.FACEBOOK_PAGE_ID
    if not page:
        raise RuntimeError("FACEBOOK_PAGE_ID is not set in .env.")

    # 1) Start
    start = _check(requests.post(_graph(f"{page}/video_reels"), data={
        "upload_phase": "start", "access_token": token}, timeout=60), "Facebook start")
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or \
        f"https://rupload.facebook.com/video-upload/{config.META_GRAPH_VERSION}/{video_id}"

    # 2) Upload bytes
    size = file.stat().st_size
    with open(file, "rb") as f:
        _check(requests.post(upload_url, data=f, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
        }, timeout=900), "Facebook upload")

    # 3) Finish & publish
    params = {"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
              "description": description[:5000], "access_token": token}
    if title:
        params["title"] = title[:250]
    _check(requests.post(_graph(f"{page}/video_reels"), params=params, timeout=60), "Facebook publish")
    return {"id": video_id, "url": f"https://www.facebook.com/reel/{video_id}"}
