"""Pure vertical-short rendering logic (no Apify dependency) so it is unit-testable."""
from __future__ import annotations
import math, os, re, subprocess
from dataclasses import dataclass

from .captions import probe, build_cues, TranscriptionError

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
FONTS = {  # input value -> ASS font name (files bundled in ./fonts)
    "poppins": "Poppins ExtraBold", "anton": "Anton", "bebas": "Bebas Neue", "luckiest": "Luckiest Guy",
    "archivo": "Archivo Black", "dejavu": "DejaVu Sans",
}
RESOLUTIONS = {"1080x1920": (1080, 1920), "720x1280": (720, 1280)}
MODES = ("crop", "blur", "pad")
POSITIONS = ("auto", "bottom", "center", "top")
# caption style presets; any explicit option overrides
STYLES = {
    "bold":    {"font": "poppins", "fontSize": 88, "textColor": "#FFFFFF", "highlightColor": "#FFE600", "outlineColor": "#000000",
                "outlineWidth": 6, "box": False, "uppercase": True, "wordsPerCaption": 3, "highlightWords": True, "position": "auto"},
    "pop":     {"font": "luckiest", "fontSize": 100, "textColor": "#FFFFFF", "highlightColor": "#3DFF5A", "outlineColor": "#000000",
                "outlineWidth": 7, "box": False, "uppercase": True, "wordsPerCaption": 2, "highlightWords": True, "position": "auto"},
    "boxed":   {"font": "dejavu", "fontSize": 60, "textColor": "#FFFFFF", "highlightColor": "#FFE600", "outlineColor": "#000000",
                "outlineWidth": 0, "box": True, "uppercase": False, "wordsPerCaption": 6, "highlightWords": False, "position": "bottom"},
    "minimal": {"font": "anton", "fontSize": 80, "textColor": "#FFFFFF", "highlightColor": "#FFFFFF", "outlineColor": "#000000",
                "outlineWidth": 3, "box": False, "uppercase": False, "wordsPerCaption": 4, "highlightWords": False, "position": "bottom"},
}
MAX_CLIP_LIMIT = 180


class ShortsError(Exception):
    pass


def ass_color(hex_color: str, alpha: int = 0) -> str:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(hex_color or "").strip())
    if not m:
        raise ShortsError(f"Invalid color '{hex_color}'. Use hex like #FFE600")
    h = m.group(1)
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def resolve_style(style: str | None, overrides: dict | None) -> dict:
    name = (style or "bold").lower()
    if name not in STYLES:
        raise ShortsError(f"Unknown captionStyle '{name}'. Use one of: {', '.join(STYLES)}")
    s = dict(STYLES[name])
    s.update({k: v for k, v in (overrides or {}).items() if v is not None and k in s})
    if s["font"] not in FONTS:
        raise ShortsError(f"Unknown font '{s['font']}'. Use one of: {', '.join(FONTS)}")
    if s["position"] not in POSITIONS:
        raise ShortsError(f"captionPosition must be one of {POSITIONS}")
    s["fontSize"] = int(min(max(int(s["fontSize"]), 20), 200))
    s["outlineWidth"] = float(min(max(float(s["outlineWidth"]), 0), 20))
    s["wordsPerCaption"] = int(min(max(int(s["wordsPerCaption"]), 1), 12))
    for k in ("textColor", "highlightColor", "outlineColor"):
        ass_color(s[k])
    return s


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _t(sec: float) -> str:
    cs = int(round(max(0.0, sec) * 100))
    h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(segments: list[dict], width: int, height: int, s: dict, video_bottom: int | None = None) -> tuple[str, list[dict]]:
    """Return (ASS script, cues). Font size is specified for 1080-wide output and scaled.
    video_bottom: y (px) where the letterboxed foreground ends (blur/pad modes); 'auto' places captions just below it."""
    scale = width / 1080
    fs = round(s["fontSize"] * scale)
    max_chars = max(8, int(width * 0.86 / (fs * 0.55)))
    cues = build_cues(segments, max_chars=max_chars, max_lines=2 if s["wordsPerCaption"] <= 4 else 3,
                      max_cue_seconds=4.0, words_per_cue=s["wordsPerCaption"])
    pos = s["position"]
    if pos == "auto":
        if video_bottom and height - video_bottom > 2.6 * fs + height * 0.20:
            align, margin_v = 8, int(video_bottom + height * 0.03)  # in the free area under the video
        else:
            align, margin_v = 2, int(height * 0.28)  # lower third, above the platform UI
    else:
        align = {"bottom": 2, "center": 5, "top": 8}[pos]
        margin_v = {"bottom": int(height * 0.20), "center": 0, "top": int(height * 0.14)}[pos]
    border_style, back = (3, ass_color("#000000", 0x60)) if s["box"] else (1, ass_color("#000000", 0x80))
    outline = max(1.0, 10 * scale) if s["box"] else s["outlineWidth"] * scale
    shadow = 0 if s["box"] else round(2 * scale, 1)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONTS[s['font']]},{fs},{ass_color(s['textColor'])},{ass_color(s['highlightColor'])},{ass_color(s['outlineColor']) if not s['box'] else back},{back},0,0,0,0,100,100,0,0,{border_style},{outline},{shadow},{align},{int(width*0.07)},{int(width*0.07)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hl = ass_color(s["highlightColor"])
    # map cue text back to its words for per-word highlighting
    all_words = [w for seg in segments for w in (seg.get("words") or [])]
    lines = []
    for c in cues:
        text = c["text"].upper() if s["uppercase"] else c["text"]
        ws = [w for w in all_words if w["start"] >= c["start"] - 1e-3 and w["end"] <= c["end"] + 1e-3]
        if not (s["highlightWords"] and ws):
            lines.append(f"Dialogue: 0,{_t(c['start'])},{_t(c['end'])},Cap,,0,0,0,,{_esc(text)}")
            continue
        toks = [(w["word"].strip().upper() if s["uppercase"] else w["word"].strip()) for w in ws]
        for i, w in enumerate(ws):
            st = c["start"] if i == 0 else w["start"]
            en = ws[i + 1]["start"] if i + 1 < len(ws) else c["end"]
            if en <= st:
                continue
            parts = [(f"{{\\c{hl}}}{_esc(t)}{{\\r}}" if j == i else _esc(t)) for j, t in enumerate(toks)]
            lines.append(f"Dialogue: 0,{_t(st)},{_t(en)},Cap,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(lines) + "\n", cues


def foreground_bottom(mode: str, info: dict, w: int, h: int) -> int | None:
    """Bottom edge (px) of the fitted video in blur/pad modes, None when it fills the frame."""
    v = info.get("video") or {}
    if mode == "crop" or not v.get("width") or not v.get("height"):
        return None
    sw, sh = v["width"], v["height"]
    if v.get("rotation") in (90, 270):
        sw, sh = sh, sw
    fh = min(h, round(w * sh / sw))
    return None if fh >= h - 4 else (h + fh) // 2


def video_filter(mode: str, w: int, h: int, crop_position: float = 0.5, blur: int = 20, pad_color: str = "#000000",
                 ass_path: str | None = None) -> str:
    if mode not in MODES:
        raise ShortsError(f"mode must be one of {MODES}")
    cp = min(max(float(crop_position), 0.0), 1.0)
    if mode == "crop":
        v = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:(iw-{w})*{cp}:(ih-{h})/2,setsar=1"
    elif mode == "blur":
        sw, sh = max(2, w // 8 // 2 * 2), max(2, h // 8 // 2 * 2)  # blur at 1/8 size: fast and smooth
        sigma = max(1, int(blur) // 4)
        v = (f"[0:v]split=2[a][b];[a]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
             f"gblur=sigma={sigma},eq=brightness=-0.08,scale={w}:{h}[bg];"
             f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    else:
        ass_color(pad_color)  # validates
        hexc = re.fullmatch(r"#?([0-9a-fA-F]{6})", pad_color.strip()).group(1)
        v = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{hexc},setsar=1"
    v += ",fps=30"
    if ass_path:
        v += f",ass='{ass_path}':fontsdir='{FONTS_DIR}'"
    return v + ",format=yuv420p[v]"


@dataclass
class ClipPlan:
    start: float
    duration: float
    source_duration: float | None


def plan_clip(info: dict, start: float | None, end: float | None, max_clip: float) -> ClipPlan:
    if not info.get("video"):
        raise ShortsError("Input has no video stream")
    max_clip = float(min(max(max_clip or 60, 5), MAX_CLIP_LIMIT))
    dur = info.get("duration")
    st = float(start or 0)
    if st < 0 or (dur and st >= dur):
        raise ShortsError(f"startSeconds={st} is outside the video (duration {dur:.1f}s)" if dur else "Invalid startSeconds")
    en = float(end) if end else (dur if dur else st + max_clip)
    if dur:
        en = min(en, dur)
    if en <= st:
        raise ShortsError("endSeconds must be greater than startSeconds")
    return ClipPlan(st, round(min(en - st, max_clip), 3), dur)


def render(src: str, out: str, plan: ClipPlan, vf: str, has_audio: bool, crf: int = 21, timeout: int = 3600) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", str(plan.start), "-t", str(plan.duration), "-i", src,
           "-filter_complex", vf, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-profile:v", "high", "-movflags", "+faststart", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        raise ShortsError(f"ffmpeg render failed: {p.stderr.strip()[-500:]}")


def thumbnail(video: str, out: str, at: float = 1.0) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", video, "-frames:v", "1", "-q:v", "3", out],
                   capture_output=True, timeout=120)


BILLING_TOLERANCE_SECONDS = 0.5


def billable_minutes(seconds: float | None) -> int:
    """Per started minute, minimum 1, ignoring up to 0.5 s of encoder/container padding."""
    if not seconds:
        return 1
    return max(1, math.ceil(max(0.0, seconds - BILLING_TOLERANCE_SECONDS) / 60))
