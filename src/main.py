"""Apify Actor entrypoint: Video to Vertical Shorts (9:16) with burned-in AI captions, pay-per-event."""
import asyncio, os, tempfile, uuid
import httpx
from apify import Actor
from .captions import probe, extract_audio, transcribe, to_srt, MODELS, TranscriptionError
from .core import (RESOLUTIONS, MODES, resolve_style, build_ass, video_filter, foreground_bottom, plan_clip, render, thumbnail,
                   billable_minutes, ShortsError)

MAX_DOWNLOAD = 4 * 1024**3
ITEM_KEYS = ["startSeconds", "endSeconds", "maxClipSeconds", "mode", "cropPosition", "blurStrength", "padColor",
             "resolution", "captions", "model", "language", "captionStyle", "font", "fontSize", "textColor",
             "highlightColor", "outlineColor", "outlineWidth", "captionBox", "uppercase", "wordsPerCaption",
             "highlightWords", "captionPosition", "quality"]
STYLE_MAP = {"font": "font", "fontSize": "fontSize", "textColor": "textColor", "highlightColor": "highlightColor",
             "outlineColor": "outlineColor", "outlineWidth": "outlineWidth", "captionBox": "box", "uppercase": "uppercase",
             "wordsPerCaption": "wordsPerCaption", "highlightWords": "highlightWords", "captionPosition": "position"}
CRF = {"high": 18, "standard": 21, "small": 25}


async def download(url: str, dest: str) -> None:
    if not str(url or "").startswith(("http://", "https://")):
        raise ShortsError("url must be an http(s) URL")
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            n = 0
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    n += len(chunk)
                    if n > MAX_DOWNLOAD:
                        raise ShortsError("File larger than 4 GB limit")
                    f.write(chunk)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        clips = list(inp.get("clips") or [])
        if inp.get("url"):
            clips.insert(0, {"url": inp["url"]})
        if not clips:
            raise ValueError("Provide 'url' or 'clips' [{url, startSeconds, endSeconds, ...}]")
        defaults = {"startSeconds": None, "endSeconds": None, "maxClipSeconds": 60, "mode": "blur", "cropPosition": 0.5,
                    "blurStrength": 20, "padColor": "#000000", "resolution": "1080x1920", "captions": True, "model": "small",
                    "language": "auto", "captionStyle": "bold", "quality": "standard"}
        defaults.update({k: inp[k] for k in ITEM_KEYS if inp.get(k) is not None})
        kvs = await Actor.open_key_value_store()
        for item in clips:
            item = item if isinstance(item, dict) else {"url": item}
            o = {**defaults, **{k: v for k, v in item.items() if v is not None and k in ITEM_KEYS}}
            url = item.get("url")
            row = {"sourceUrl": url, "startSeconds": o["startSeconds"] or 0, "mode": o["mode"], "resolution": o["resolution"]}
            with tempfile.TemporaryDirectory() as td:
                try:
                    if o["resolution"] not in RESOLUTIONS:
                        raise ShortsError(f"resolution must be one of {list(RESOLUTIONS)}")
                    if o["mode"] not in MODES:
                        raise ShortsError(f"mode must be one of {MODES}")
                    if o["captions"] and o["model"] not in MODELS:
                        raise ShortsError(f"Unknown model '{o['model']}'. Use one of: {', '.join(MODELS)}")
                    style = resolve_style(o["captionStyle"], {STYLE_MAP[k]: o.get(k) for k in STYLE_MAP if k in o}) if o["captions"] else None
                    w, h = RESOLUTIONS[o["resolution"]]
                    src = os.path.join(td, "input")
                    await download(url, src)
                    info = probe(src)
                    plan = plan_clip(info, o["startSeconds"], o["endSeconds"], o["maxClipSeconds"])
                    ass_path, srt, cues, lang = None, None, [], None
                    if o["captions"]:
                        if not info["audio"]:
                            row["warning"] = "No audio stream; rendered without captions"
                        else:
                            wav = os.path.join(td, "a.wav")
                            await asyncio.to_thread(extract_audio, src, wav, plan.start, plan.duration)
                            Actor.log.info(f"Transcribing {plan.duration:.0f}s with model={o['model']}")
                            t = await asyncio.to_thread(transcribe, wav, o["model"], o["language"], "transcribe", True, 5, None, True)
                            lang = t.language
                            script, cues = build_ass(t.segments, w, h, style, foreground_bottom(o["mode"], info, w, h))
                            ass_path = os.path.join(td, "subs.ass")
                            with open(ass_path, "w", encoding="utf-8") as f:
                                f.write(script)
                            srt = to_srt(cues)
                            if not cues:
                                row["warning"] = "No speech detected; rendered without captions"
                    vf = video_filter(o["mode"], w, h, o["cropPosition"], int(o["blurStrength"]), o["padColor"], ass_path)
                    out = os.path.join(td, "short.mp4")
                    Actor.log.info(f"Rendering {plan.duration:.1f}s from {plan.start:.1f}s -> {w}x{h} ({o['mode']})")
                    await asyncio.to_thread(render, src, out, plan, vf, bool(info["audio"]), CRF.get(o["quality"], 21))
                    base = uuid.uuid4().hex[:12]
                    with open(out, "rb") as f:
                        await kvs.set_value(f"{base}.mp4", f.read(), content_type="video/mp4")
                    row["videoUrl"] = await kvs.get_public_url(f"{base}.mp4")
                    thumb = os.path.join(td, "t.jpg")
                    await asyncio.to_thread(thumbnail, out, thumb, min(1.0, plan.duration / 2))
                    if os.path.exists(thumb):
                        with open(thumb, "rb") as f:
                            await kvs.set_value(f"{base}.jpg", f.read(), content_type="image/jpeg")
                        row["thumbnailUrl"] = await kvs.get_public_url(f"{base}.jpg")
                    if srt:
                        await kvs.set_value(f"{base}.srt", srt.encode("utf-8"), content_type="application/x-subrip")
                        row["captionsSrtUrl"] = await kvs.get_public_url(f"{base}.srt")
                    minutes = billable_minutes(plan.duration)
                    outp = probe(out)
                    row.update(status="ok", durationSeconds=round(outp["duration"] or plan.duration, 2),
                               endSeconds=round(plan.start + plan.duration, 3), width=w, height=h,
                               sizeBytes=os.path.getsize(out), captioned=bool(cues), captionStyle=o["captionStyle"] if cues else None,
                               language=lang, captionCount=len(cues), transcript=" ".join(c["text"].replace("\n", " ") for c in cues) or None,
                               sourceDurationSeconds=info["duration"], billedMinutes=minutes)
                    await Actor.charge(event_name="short-created", count=1)
                    r = await Actor.charge(event_name="clip-minute", count=minutes)
                    await Actor.push_data(row)
                    if getattr(r, "event_charge_limit_reached", False):
                        Actor.log.info("Spending limit reached; stopping.")
                        break
                except Exception as e:  # never-fail: error rows are free
                    row.update(status="error", error=str(e)[:500])
                    await Actor.push_data(row)
