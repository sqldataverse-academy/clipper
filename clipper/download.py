"""Downloads the stream video, YouTube's auto-captions and 'Most Replayed' data with yt-dlp."""
import json
from pathlib import Path

import yt_dlp


class DownloadResult:
    def __init__(self, video: Path, info: dict, subtitle: Path | None):
        self.video = video
        self.info = info
        self.subtitle = subtitle
        self.title = info.get("title", "")
        self.duration = float(info.get("duration") or 0)
        # List of {"start_time", "end_time", "value"} with value 0..1, or None
        self.heatmap = info.get("heatmap")


def probe(url: str) -> dict:
    """Get video metadata without downloading."""
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
        return ydl.extract_info(url, download=False)


def download(url: str, out_dir: Path, progress=None) -> DownloadResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(url)
    is_live = info.get("live_status") == "is_live"

    lang = info.get("language") or "en"
    sub_langs = [lang, f"{lang}.*", "en", "en.*", "hi", "hi.*"]

    def hook(d):
        if progress and d.get("status") == "downloading":
            pct = d.get("_percent_str", "").strip()
            progress(f"Downloading video {pct}" if not is_live else "Recording live stream (waits until it ends)")

    opts = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": str(out_dir / "source.%(ext)s"),
        # 1080p max is plenty for vertical reels and keeps files smaller
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": sub_langs,
        "subtitlesformat": "json3",
        "progress_hooks": [hook],
        "ignoreerrors": False,
        "retries": 10,
        "fragment_retries": 10,
    }
    if is_live:
        # Record from the beginning of the live stream until it ends.
        opts["live_from_start"] = True
        opts["wait_for_video"] = (30, 300)

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            # Subtitle download failures shouldn't kill the job; retry without subs.
            if "subtitle" not in str(e).lower():
                raise
            opts.update(writeautomaticsub=False, writesubtitles=False)
            with yt_dlp.YoutubeDL(opts) as ydl2:
                info = ydl2.extract_info(url, download=True)

    video = next((p for p in out_dir.glob("source.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if not video:
        raise RuntimeError("Download finished but no video file was found.")

    subs = sorted(out_dir.glob("source.*.json3"))
    # Prefer the stream's own language
    subtitle = next((s for s in subs if f".{lang}" in s.name), subs[0] if subs else None)

    # Refresh info (VODs of finished streams may now include duration/heatmap)
    try:
        info = {**info, **{k: v for k, v in probe(url).items() if v}}
    except Exception:
        pass
    (out_dir / "info.json").write_text(json.dumps(
        {k: info.get(k) for k in ("id", "title", "duration", "heatmap", "language", "channel")}, indent=1))
    return DownloadResult(video, info, subtitle)
