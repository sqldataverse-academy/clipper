"""Clipper - local web app. Run:  python app.py   then open http://localhost:8000"""
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from clipper import config, db, pipeline

app = FastAPI(title="Clipper")
WEB = Path(__file__).parent / "web"
app.mount("/media", StaticFiles(directory=config.CLIPS_DIR), name="media")


class JobIn(BaseModel):
    url: str
    num_clips: int = config.DEFAULT_NUM_CLIPS


class ClipEdit(BaseModel):
    title: str | None = None
    caption: str | None = None
    hashtags: str | None = None


class Approve(BaseModel):
    platforms: list[str]


def _public_clip(c: dict) -> dict:
    rel = lambda p: "/media/" + Path(p).relative_to(config.CLIPS_DIR).as_posix() if p else ""
    return {**c, "file": rel(c["file"]), "thumb": rel(c["thumb"])}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status():
    return config.platform_status()


@app.post("/api/jobs")
def create_job(job: JobIn):
    if "youtu" not in job.url:
        raise HTTPException(400, "Please paste a YouTube link.")
    n = max(1, min(job.num_clips, 20))
    return {"id": pipeline.submit(job.url.strip(), n)}


@app.get("/api/jobs")
def jobs():
    return db.list_jobs()


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    db.update_job(job_id, status="queued", error="", stage="")
    pipeline._wake.set()
    return {"ok": True}


@app.get("/api/clips")
def clips(job_id: int | None = None):
    return [_public_clip(c) for c in db.list_clips(job_id)]


@app.patch("/api/clips/{clip_id}")
def edit_clip(clip_id: int, edit: ClipEdit):
    if not db.get_clip(clip_id):
        raise HTTPException(404)
    db.update_clip(clip_id, **{k: v for k, v in edit.model_dump().items() if v is not None})
    return _public_clip(db.get_clip(clip_id))


@app.post("/api/clips/{clip_id}/approve")
def approve_clip(clip_id: int, body: Approve):
    clip = db.get_clip(clip_id)
    if not clip or not clip["file"]:
        raise HTTPException(400, "Clip is not ready.")
    pipeline.approve(clip_id, body.platforms)
    return _public_clip(db.get_clip(clip_id))


@app.post("/api/clips/{clip_id}/reject")
def reject_clip(clip_id: int):
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(404)
    db.update_clip(clip_id, status="rejected")
    pipeline.delete_clip_files(clip)
    db.update_clip(clip_id, file="", thumb="")
    return {"ok": True}


@app.on_event("startup")
def _startup():
    pipeline.start_workers()


if __name__ == "__main__":
    print(f"\n  Clipper is running:  http://localhost:{config.PORT}\n")
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")
