"""Turns a moment of the stream into a finished 9:16 reel with animated captions."""
import os
import statistics
import subprocess
from pathlib import Path

import cv2

from . import transcript as tr
from .transcript import Word

OUT_W, OUT_H = 1080, 1920
CAPTION_FONT = os.getenv("CAPTION_FONT", "Arial")


# ---------------------------------------------------------------- timing

def snap_to_words(start: float, end: float, words: list[Word]) -> tuple[float, float]:
    """Move Claude's approximate times onto real word boundaries."""
    if not words:
        return start, end
    first = next((w for w in words if w.start >= start - 1.0), None)
    if first and first.start - start < 3:
        start = first.start
    last = None
    for w in words:
        if w.end <= end + 2.0:
            last = w
        else:
            break
    if last and last.end > start + 5:
        end = last.end
    return max(0.0, start - 0.15), end + 0.4


# ---------------------------------------------------------------- framing

def probe_size(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split("\n")[0].split("x")
    return int(w), int(h)


_cascade = None


def _faces(frame):
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h = gray.shape[0]
    return _cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(h // 12, h // 12))


def face_track(video: Path, start: float, end: float, step: float = 1.0):
    """Sample a frame every `step` seconds; return [(t_rel, face_center_x or None, face_width)]."""
    cap = cv2.VideoCapture(str(video))
    samples = []
    t = start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        faces = _faces(frame)
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])  # biggest face = main speaker
            samples.append((t - start, x + w / 2, w))
        else:
            samples.append((t - start, None, 0))
        t += step
    cap.release()
    return samples


def choose_layout(samples, src_w: int, src_h: int) -> dict:
    """'face' = crop around the speaker; 'fit' = full frame over a blurred background."""
    if src_w / src_h <= 9 / 16 + 0.01:
        return {"mode": "vertical"}
    found = [s for s in samples if s[1] is not None]
    if not samples or len(found) / len(samples) < 0.5:
        return {"mode": "fit"}
    median_w = statistics.median(s[2] for s in found)
    if median_w < src_w * 0.07:
        # Tiny face, e.g. a facecam in the corner of gameplay: keep the whole frame.
        return {"mode": "fit"}

    crop_w = int(src_h * 9 / 16) // 2 * 2
    # Fill gaps, smooth, then move the virtual camera only on big shifts (no jitter).
    xs, last = [], found[0][1]
    for t, cx, _ in samples:
        last = cx if cx is not None else last
        xs.append((t, last))
    smooth = []
    for i in range(len(xs)):
        win = [x for _, x in xs[max(0, i - 2): i + 3]]
        smooth.append((xs[i][0], statistics.median(win)))
    keys, cam = [], smooth[0][1]
    keys.append((0.0, cam))
    for t, x in smooth[1:]:
        if abs(x - cam) > src_w * 0.08:
            cam = x
            keys.append((t, cam))

    def left(cx):
        return int(min(max(cx - crop_w / 2, 0), src_w - crop_w))

    return {"mode": "face", "crop_w": crop_w, "keys": [(t, left(x)) for t, x in keys]}


def _x_expr(keys) -> str:
    """ffmpeg expression for crop x: glide 0.5s between camera positions."""
    expr = str(keys[-1][1])
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        glide = f"{x0}+({x1}-{x0})*min(1,(t-{t1:.2f})/0.5)"
        expr = f"if(lt(t,{t1:.2f}),{x0},if(lt(t,{t1 + 0.5:.2f}),{glide},{expr}))"
    return expr


def video_filter(layout: dict, src_h: int) -> str:
    if layout["mode"] == "face":
        x = _x_expr(layout["keys"]).replace(",", r"\,")
        return f"crop={layout['crop_w']}:{src_h}:{x}:0,scale={OUT_W}:{OUT_H},setsar=1"
    if layout["mode"] == "vertical":
        return f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return (
        f"split[a][b];[a]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
        f"boxblur=25:3,eq=brightness=-0.08[bg];[b]scale={OUT_W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


# ---------------------------------------------------------------- captions

def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words: list[Word], path: Path, layout_mode: str, max_words: int = 3, max_chars: int = 18) -> None:
    """Word-by-word captions: groups of up to 3 words, current word highlighted yellow."""
    margin_v = 560 if layout_mode == "face" else 420
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{CAPTION_FONT},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    groups, cur = [], []
    for w in words:
        too_long = len(" ".join(x.text for x in cur + [w])) > max_chars
        gap = cur and w.start - cur[-1].end > 0.6
        if cur and (len(cur) >= max_words or too_long or gap):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)

    lines = []
    for gi, g in enumerate(groups):
        g_end = g[-1].end
        if gi + 1 < len(groups):
            g_end = min(max(g_end, g[-1].end), groups[gi + 1][0].start)
        for i, w in enumerate(g):
            s = w.start if i else g[0].start
            e = g[i + 1].start if i + 1 < len(g) else g_end
            if e <= s:
                e = s + 0.05
            parts = []
            for j, x in enumerate(g):
                t = _esc(x.text.upper())
                parts.append(r"{\c&H00E6FF&\fscx108\fscy108}" + t + r"{\r}" if j == i else t)
            pop = r"{\fad(60,0)}" if i == 0 else ""
            lines.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- render

def clip_words(video: Path, start: float, end: float, work: Path, fallback_words: list[Word], log=print) -> list[Word]:
    """Accurate words for the clip via local Whisper; YouTube captions if Whisper is unavailable."""
    audio = work / "clip_audio.wav"
    try:
        tr.extract_audio(video, audio, start, end)
        return tr.whisper_words(audio)
    except Exception as e:
        log(f"Whisper unavailable ({e.__class__.__name__}: {e}); using YouTube captions for this clip.")
        return [Word(w.start - start, w.end - start, w.text)
                for w in fallback_words if w.start >= start and w.end <= end + 0.3]
    finally:
        audio.unlink(missing_ok=True)


def render_clip(video: Path, start: float, end: float, out_dir: Path, all_words: list[Word], log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    src_w, src_h = probe_size(video)

    log("Tracking faces")
    try:
        layout = choose_layout(face_track(video, start, end), src_w, src_h)
    except Exception as e:
        log(f"Face tracking failed ({e}); using full-frame layout.")
        layout = {"mode": "fit"}

    log("Transcribing clip for captions")
    words = clip_words(video, start, end, out_dir, all_words, log)
    build_ass(words, out_dir / "captions.ass", layout["mode"])

    log(f"Rendering ({layout['mode']} layout)")
    vf = video_filter(layout, src_h) + ",ass=captions.ass,fps=30,format=yuv420p"
    out = out_dir / "reel.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(video.resolve()),
        "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-movflags", "+faststart", "reel.mp4",
    ]
    # Run inside the clip folder so the captions path needs no escaping (Windows-safe).
    r = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")

    thumb = out_dir / "thumb.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", "reel.mp4", "-frames:v", "1",
                    "-vf", "scale=360:-2", "thumb.jpg"], cwd=out_dir, check=True)
    return {"file": str(out), "thumb": str(thumb), "start": start, "end": end, "layout": layout["mode"]}
