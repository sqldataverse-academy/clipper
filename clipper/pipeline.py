"""Background workers: one processes jobs (download -> pick -> render), one uploads approved clips."""
import queue
import shutil
import threading
import traceback
from pathlib import Path

from . import config, db, download, render, selector
from . import transcript as tr
from .uploaders import meta, youtube

PLATFORMS = ("youtube", "instagram", "facebook")
_wake = threading.Event()
_upload_q: "queue.Queue[tuple[int, str]]" = queue.Queue()


# ------------------------------------------------------------------ jobs

def submit(url: str, num_clips: int) -> int:
    job_id = db.create_job(url, num_clips)
    _wake.set()
    return job_id


def _process(job: dict) -> None:
    jid = job["id"]
    work = config.DOWNLOADS_DIR / f"job_{jid}"

    def stage(msg):
        print(f"[job {jid}] {msg}")
        db.update_job(jid, stage=msg)

    stage("Starting download")
    dl = download.download(job["url"], work, progress=stage)
    db.update_job(jid, title=dl.title)

    if dl.subtitle:
        stage("Reading YouTube captions")
        words = tr.from_youtube_json3(dl.subtitle)
    else:
        words = []
    if len(words) < 50:
        stage("No YouTube captions - transcribing with Whisper (slow on CPU)")
        words = tr.from_whisper_full(dl.video, work)
    if not words:
        raise RuntimeError("Could not get any speech from this video.")

    duration = dl.duration or words[-1].end
    stage("Claude is picking the best moments")
    ideas = selector.pick_clips(dl.title, duration, tr.to_prompt_lines(words), dl.heatmap, job["num_clips"])
    if not ideas:
        raise RuntimeError("Claude found no suitable moments.")

    for i, idea in enumerate(ideas, 1):
        start, end = render.snap_to_words(idea.start, idea.end, words)
        clip_id = db.create_clip(
            jid, start=start, end=end, score=idea.score, reason=idea.reason, hook=idea.hook,
            title=idea.title, caption=idea.caption, hashtags=" ".join("#" + h.lstrip("#") for h in idea.hashtags),
        )
        stage(f"Rendering clip {i}/{len(ideas)}")
        try:
            out = render.render_clip(dl.video, start, end, config.CLIPS_DIR / f"clip_{clip_id}", words,
                                     log=lambda m: stage(f"Clip {i}/{len(ideas)}: {m}"))
            db.update_clip(clip_id, file=out["file"], thumb=out["thumb"], status="review")
        except Exception as e:
            traceback.print_exc()
            db.update_clip(clip_id, status="failed", error=str(e)[:500])

    db.update_job(jid, status="done", stage=f"{len(ideas)} clips ready for review")
    # Source video is large; keep captions/info, delete the video.
    if dl.video.exists():
        dl.video.unlink()


def _job_worker():
    while True:
        job = db.next_queued_job()
        if not job:
            _wake.wait(timeout=5)
            _wake.clear()
            continue
        db.update_job(job["id"], status="running", error="")
        try:
            _process(job)
        except Exception as e:
            traceback.print_exc()
            db.update_job(job["id"], status="failed", stage="Failed", error=str(e)[:800])


# ------------------------------------------------------------------ uploads

def approve(clip_id: int, platforms: list[str]) -> None:
    clip = db.get_clip(clip_id)
    db.update_clip(clip_id, status="approved")
    for p in platforms:
        if p in PLATFORMS and clip["uploads"].get(p, {}).get("status") not in ("done", "uploading", "queued"):
            db.set_upload_status(clip_id, p, status="queued", error="")
            _upload_q.put((clip_id, p))


def _do_upload(clip: dict, platform: str) -> dict:
    file = Path(clip["file"])
    tags = [h.lstrip("#") for h in clip["hashtags"].split() if h.strip("#")]
    text = f"{clip['caption']}\n\n{clip['hashtags']}".strip()
    if platform == "youtube":
        return youtube.upload(file, clip["title"], text, tags)
    if platform == "instagram":
        return meta.upload_instagram(file, text)
    if platform == "facebook":
        return meta.upload_facebook(file, text, clip["title"])
    raise ValueError(platform)


def _upload_worker():
    while True:
        clip_id, platform = _upload_q.get()
        clip = db.get_clip(clip_id)
        db.set_upload_status(clip_id, platform, status="uploading")
        try:
            res = _do_upload(clip, platform)
            db.set_upload_status(clip_id, platform, status="done", error="", **res)
        except Exception as e:
            traceback.print_exc()
            db.set_upload_status(clip_id, platform, status="failed", error=str(e)[:500])
        clip = db.get_clip(clip_id)
        if clip["uploads"] and all(u.get("status") == "done" for u in clip["uploads"].values()):
            db.update_clip(clip_id, status="posted")


def requeue_pending_uploads():
    for clip in db.list_clips():
        for p, u in clip["uploads"].items():
            if u.get("status") == "queued":
                _upload_q.put((clip["id"], p))


def delete_clip_files(clip: dict) -> None:
    if clip.get("file"):
        shutil.rmtree(Path(clip["file"]).parent, ignore_errors=True)


def start_workers():
    db.init()
    requeue_pending_uploads()
    threading.Thread(target=_job_worker, daemon=True, name="jobs").start()
    threading.Thread(target=_upload_worker, daemon=True, name="uploads").start()
