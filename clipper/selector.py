"""Asks Claude to pick the most viral moments from the transcript."""
import anthropic
from pydantic import BaseModel, Field

from . import config


class ClipIdea(BaseModel):
    start: float = Field(description="Clip start, in seconds from the beginning of the stream")
    end: float = Field(description="Clip end, in seconds from the beginning of the stream")
    score: int = Field(description="Predicted virality 1-100")
    hook: str = Field(description="The first line/idea that grabs attention in the first 2 seconds")
    reason: str = Field(description="One sentence on why this moment will perform well")
    title: str = Field(description="Short punchy title, max 70 characters, no hashtags")
    caption: str = Field(description="Post caption for Instagram/Facebook, 1-3 short lines")
    hashtags: list[str] = Field(description="5-8 relevant hashtags without the # sign")


class ClipPlan(BaseModel):
    clips: list[ClipIdea]


SYSTEM = """You are an expert short-form video editor who finds viral moments in long live streams \
for YouTube Shorts, Instagram Reels and Facebook Reels.

What makes a moment work:
- A strong hook in the first 2 seconds (a bold claim, question, surprise, conflict, punchline set-up).
- Self-contained: understandable without watching the rest of the stream.
- Emotion: funny, shocking, inspiring, controversial, wholesome, or highly useful/insightful.
- A payoff or resolution before the clip ends - never cut mid-sentence or mid-punchline.
- Peaks in YouTube's "Most Replayed" data are strong evidence viewers loved that part.

Rules:
- Start a clip exactly where the hook begins (no slow lead-in) and end right after the payoff.
- Clips must not overlap each other.
- Skip intros, "waiting for chat", sponsor reads, and technical difficulties.
- Rank by real viral potential; give honest scores."""


def _heatmap_text(heatmap, duration: float) -> str:
    if not heatmap:
        return "Not available for this video."
    top = sorted(heatmap, key=lambda h: h.get("value", 0), reverse=True)[:15]
    top.sort(key=lambda h: h["start_time"])
    return "\n".join(
        f"- {h['start_time']:.0f}s to {h['end_time']:.0f}s (replay intensity {h['value']:.2f})" for h in top
    )


def pick_clips(title: str, duration: float, transcript: str, heatmap, num_clips: int) -> list[ClipIdea]:
    client = anthropic.Anthropic()
    user = f"""Stream title: {title}
Stream length: {duration:.0f} seconds

YouTube "Most Replayed" peaks:
{_heatmap_text(heatmap, duration)}

Transcript (each line starts with [seconds since start]; timings are approximate):
<transcript>
{transcript}
</transcript>

Pick the {num_clips} best moments. Each clip must be between {config.MIN_CLIP_SECONDS} and \
{config.MAX_CLIP_SECONDS} seconds long. Write titles, captions and hashtags in {config.POST_LANGUAGE}."""

    response = client.beta.messages.parse(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=ClipPlan,
        output_config={"effort": "high"},
        # If the main model declines, the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this transcript.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("Claude's answer was cut off; try asking for fewer clips.")

    usage = response.usage
    print(f"[claude] input tokens={usage.input_tokens} output tokens={usage.output_tokens}")
    return _clean(response.parsed_output.clips, duration)


def _clean(clips: list[ClipIdea], duration: float) -> list[ClipIdea]:
    """Clamp lengths, drop overlaps, sort by score."""
    out: list[ClipIdea] = []
    for c in sorted(clips, key=lambda c: c.score, reverse=True):
        start = max(0.0, c.start)
        end = c.end if not duration else min(c.end, duration)
        if end - start < config.MIN_CLIP_SECONDS:
            end = start + config.MIN_CLIP_SECONDS
        if end - start > config.MAX_CLIP_SECONDS:
            end = start + config.MAX_CLIP_SECONDS
        if duration and end > duration:
            continue
        if any(start < o.end and end > o.start for o in out):
            continue
        out.append(c.model_copy(update={"start": start, "end": end}))
    return out
