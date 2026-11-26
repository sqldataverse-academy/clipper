# ✂️ Clipper

Paste a YouTube live stream or video link. Clipper finds the most viral moments, turns each one into a
**vertical 9:16 reel (1080×1920) with animated captions**, and lets you review it. Approved clips
upload to **YouTube Shorts, Instagram Reels and Facebook Reels**.

Runs on your own computer. No GPU needed.

## How it works

1. **Download.** `yt-dlp` downloads the video, YouTube's auto-captions, and the "Most Replayed" heatmap.
   For a live stream that's still running, it records from the start until the stream ends.
2. **Pick moments.** Claude reads the transcript and the Most Replayed peaks, and picks the best
   25–60 second moments. Each gets a viral score, reason, title, caption and hashtags.
3. **Make reels**, for each moment:
   - **Vertical crop.** If a face is visible, the crop follows the speaker smoothly. Otherwise
     (gameplay, slides, a small facecam) the full frame sits on a blurred vertical background.
   - **Captions.** Local Whisper transcribes the clip for accurate word timing. Captions are bold and
     word-by-word, with the current word highlighted.
   - **Format.** Audio is normalised for mobile, encoded as H.264/AAC at 30 fps (the platforms' recommended format).
4. **Review** at http://localhost:8000. Watch each clip, edit the title, caption and hashtags, choose
   platforms, then **Approve & upload** or **Reject**.
5. **Upload** with the official APIs. Each platform's status and link shows on the clip card.
   A failed upload can be retried.

## Quick start

See **[SETUP.md](SETUP.md)** for the one-time setup. After that:

```
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate   (Mac)
python app.py
```
Open http://localhost:8000 and paste a link.

## Cost

| | |
|---|---|
| Claude API | about $0.10–0.30 per stream (₹8–25), depending on stream length |
| Everything else | Free |

## Processing time on a normal laptop (CPU only)

- Download: depends on your internet speed
- Claude picking moments: about 30–90 s
- Each clip: about 1–3 min (Whisper captions plus rendering)

For a 3-hour stream with 8 clips, expect roughly **15–30 minutes**, mostly unattended.

## Files

```
app.py                 web app + API (run this)
check_setup.py         checks your installation and keys
connect_youtube.py     one-time YouTube login
clipper/download.py    yt-dlp download, captions, heatmap
clipper/transcript.py  caption parsing + Whisper
clipper/selector.py    Claude picks the viral moments
clipper/render.py      face tracking, 9:16 crop, animated captions, FFmpeg
clipper/uploaders/     YouTube, Instagram, Facebook uploaders
clipper/pipeline.py    background job + upload workers
web/index.html         the review page
data/                  downloads, clips, database (created automatically)
secrets/               your Google OAuth file + token (never share)
```

## Notes

- The source video is deleted after its clips are made, to save disk space. Rejected clips are deleted too.
- Only clip streams you own or have permission to use. Platforms issue copyright strikes.
- If YouTube changes something and downloads fail, update yt-dlp: `pip install -U yt-dlp`
