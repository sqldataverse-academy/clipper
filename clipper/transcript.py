"""Builds a timestamped transcript: YouTube captions first, local Whisper as fallback."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class Word:
    start: float
    end: float
    text: str


def from_youtube_json3(path: Path) -> list[Word]:
    """Parse YouTube's json3 caption format into timed words."""
    data = json.loads(path.read_text(encoding="utf-8"))
    words: list[Word] = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or ev.get("aAppend"):
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        for i, s in enumerate(segs):
            text = (s.get("utf8") or "").replace("\n", " ").strip()
            if not text:
                continue
            start = t0 + s.get("tOffsetMs", 0) / 1000
            nxt = segs[i + 1].get("tOffsetMs") if i + 1 < len(segs) else None
            end = t0 + nxt / 1000 if nxt is not None else t0 + dur
            for w in text.split():
                words.append(Word(start, max(end, start + 0.1), w))
    words.sort(key=lambda w: w.start)
    # Manual subtitles can repeat lines; drop exact consecutive duplicates
    dedup: list[Word] = []
    for w in words:
        if dedup and dedup[-1].text == w.text and abs(dedup[-1].start - w.start) < 0.05:
            continue
        dedup.append(w)
    return dedup


_model = None


def whisper_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        compute = "float16" if config.WHISPER_DEVICE == "cuda" else "int8"
        _model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE, compute_type=compute)
    return _model


def extract_audio(video: Path, out: Path, start: float | None = None, end: float | None = None) -> Path:
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None and start is not None:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(out)]
    subprocess.run(cmd, check=True)
    return out


def whisper_words(audio: Path, model=None) -> list[Word]:
    model = model or whisper_model()
    segments, _ = model.transcribe(
        str(audio), language=config.CAPTION_LANGUAGE, word_timestamps=True, vad_filter=True
    )
    out = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                out.append(Word(w.start, w.end, t))
    return out


def from_whisper_full(video: Path, work: Path) -> list[Word]:
    """Fallback when YouTube has no captions. Slow on CPU for long streams."""
    audio = extract_audio(video, work / "full_audio.wav")
    try:
        # A smaller model is fine for *finding* moments; clip captions use WHISPER_MODEL.
        from faster_whisper import WhisperModel
        compute = "float16" if config.WHISPER_DEVICE == "cuda" else "int8"
        fast = WhisperModel("base", device=config.WHISPER_DEVICE, compute_type=compute)
        return whisper_words(audio, fast)
    finally:
        audio.unlink(missing_ok=True)


def to_prompt_lines(words: list[Word], chunk_seconds: float = 8.0) -> str:
    """Compact transcript for Claude: one line per ~8 seconds, '[seconds] text'."""
    lines, buf, t0 = [], [], None
    for w in words:
        if t0 is None:
            t0 = w.start
        if w.start - t0 >= chunk_seconds and buf:
            lines.append(f"[{t0:.0f}] {' '.join(buf)}")
            buf, t0 = [], w.start
        buf.append(w.text)
    if buf:
        lines.append(f"[{t0:.0f}] {' '.join(buf)}")
    return "\n".join(lines)
