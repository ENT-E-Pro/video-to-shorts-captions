"""Whisper transcription + caption cue logic (shared with the video-to-captions Actor; keep in sync)."""
from __future__ import annotations
import json, math, os, subprocess
from dataclasses import dataclass, field

MODELS = ["tiny", "base", "small", "large-v3-turbo", "tiny.en", "base.en", "small.en"]
MAX_DURATION_DEFAULT = 3 * 3600


class TranscriptionError(Exception):
    pass


def probe(path: str) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptionError(f"Not a readable media file: {p.stderr.strip()[:300]}")
    d = json.loads(p.stdout)
    fmt = d.get("format", {})
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = fmt.get("duration")
    rot = 0
    if v:
        rot = next((sd.get("rotation") for sd in v.get("side_data_list") or [] if "rotation" in sd), None) or (v.get("tags") or {}).get("rotate") or 0
        try:
            rot = int(float(rot)) % 360
        except (TypeError, ValueError):
            rot = 0
    return {
        "format": fmt.get("format_name"),
        "duration": float(dur) if dur not in (None, "N/A") else None,
        "sizeBytes": int(fmt["size"]) if fmt.get("size") else None,
        "video": {"codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"), "rotation": rot} if v else None,
        "audio": {"codec": a.get("codec_name"), "sampleRate": int(a["sample_rate"]) if a.get("sample_rate") else None,
                  "channels": a.get("channels")} if a else None,
    }


def extract_audio(src: str, out_wav: str, start: float | None = None, duration: float | None = None, timeout: int = 1800) -> None:
    """Decode to 16 kHz mono PCM (Whisper's native input)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", src]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_wav]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0 or not os.path.exists(out_wav):
        raise TranscriptionError(f"ffmpeg audio extraction failed: {p.stderr.strip()[-400:]}")


# ---------------- caption formatting ----------------

def ts(seconds: float, sep: str = ",") -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def wrap(text: str, max_chars: int, max_lines: int) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars and len(lines) < max_lines - 1:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return "\n".join(l for l in lines if l)


def _fits(text: str, max_chars: int, max_lines: int) -> bool:
    return len(wrap(text, max_chars, 10**6).split("\n")) <= max_lines


def build_cues(segments: list[dict], max_chars: int = 42, max_lines: int = 2, max_cue_seconds: float = 6.0,
               words_per_cue: int | None = None) -> list[dict]:
    """Regroup Whisper segments into readable caption cues using word timestamps when available.
    words_per_cue (e.g. 1-4) gives short-form 'karaoke' style cues; otherwise cues fill up to max_chars*max_lines."""
    cues = []
    limit = max_chars * max_lines
    for seg in segments:
        words = seg.get("words") or []
        if not words:
            t = seg["text"].strip()
            if t:
                cues.append({"start": seg["start"], "end": seg["end"], "text": t})
            continue
        cur: list[dict] = []
        for w in words:
            cand = "".join(x["word"] for x in cur + [w]).strip()
            too_long = not _fits(cand, max_chars, max_lines) or (cur and w["end"] - cur[0]["start"] > max_cue_seconds)
            full = words_per_cue and len(cur) >= words_per_cue
            if cur and (too_long or full):
                cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip()})
                cur = []
            cur.append(w)
            # prefer breaking after sentence punctuation
            if not words_per_cue and w["word"].rstrip().endswith((".", "?", "!")) and len(cand) > limit * 0.4:
                cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip()})
                cur = []
        if cur:
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip()})
    # ensure monotonic, non-overlapping, min 0.3 s display time
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else None
        if c["end"] - c["start"] < 0.3:
            c["end"] = c["start"] + 0.3
        if nxt is not None and c["end"] > nxt:
            c["end"] = max(c["start"] + 0.05, nxt)
        c["text"] = wrap(c["text"], max_chars, max_lines)
    return [c for c in cues if c["text"]]


def to_srt(cues: list[dict]) -> str:
    return "\n".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n" for i, c in enumerate(cues, 1))


def to_vtt(cues: list[dict]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{ts(c['start'], '.')} --> {ts(c['end'], '.')}\n{c['text']}\n" for c in cues)


def to_txt(segments: list[dict], with_timestamps: bool = False) -> str:
    if with_timestamps:
        return "\n".join(f"[{ts(s['start'], '.')[:-4]}] {s['text'].strip()}" for s in segments) + "\n"
    # paragraphs: break on pauses > 2 s
    out, para, last_end = [], [], None
    for s in segments:
        if last_end is not None and s["start"] - last_end > 2.0 and para:
            out.append(" ".join(para)); para = []
        para.append(s["text"].strip()); last_end = s["end"]
    if para:
        out.append(" ".join(para))
    return "\n\n".join(out) + "\n"


# ---------------- transcription ----------------

_MODEL_CACHE: dict = {}


def cpu_threads() -> int:
    """Apify gives 1 CPU core per 4 GB of memory; os.cpu_count() reports the whole host."""
    mem = os.environ.get("ACTOR_MEMORY_MBYTES") or os.environ.get("APIFY_MEMORY_MBYTES")
    n = os.cpu_count() or 1
    if mem:
        n = min(n, max(1, round(int(mem) / 4096)))
    return n


def load_model(name: str):
    if name not in MODELS:
        raise TranscriptionError(f"Unknown model '{name}'. Use one of: {', '.join(MODELS)}")
    if name not in _MODEL_CACHE:
        from faster_whisper import WhisperModel
        _MODEL_CACHE[name] = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=cpu_threads(),
                                          download_root=os.environ.get("WHISPER_MODELS_DIR"))
    return _MODEL_CACHE[name]


@dataclass
class Transcript:
    language: str
    language_probability: float
    duration: float
    segments: list[dict] = field(default_factory=list)


def transcribe(wav: str, model: str = "small", language: str | None = None, task: str = "transcribe",
               vad_filter: bool = True, beam_size: int = 5, initial_prompt: str | None = None,
               word_timestamps: bool = True) -> Transcript:
    if task not in ("transcribe", "translate"):
        raise TranscriptionError("task must be 'transcribe' or 'translate' (to English)")
    m = load_model(model)
    lang = None if not language or language == "auto" else language.lower()
    try:
        segs, info = m.transcribe(wav, language=lang, task=task, vad_filter=vad_filter, beam_size=beam_size,
                                  word_timestamps=word_timestamps, initial_prompt=initial_prompt or None,
                                  condition_on_previous_text=False)
        out = []
        for s in segs:
            out.append({"id": s.id, "start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                        "avgLogprob": round(s.avg_logprob, 3), "noSpeechProb": round(s.no_speech_prob, 3),
                        "words": [{"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
                                   "probability": round(w.probability, 3)} for w in (s.words or [])]})
    except ValueError as e:  # e.g. invalid language code
        raise TranscriptionError(str(e)) from e
    return Transcript(info.language, round(info.language_probability, 3), round(info.duration, 3), out)


BILLING_TOLERANCE_SECONDS = 0.5


def billable_minutes(seconds: float | None) -> int:
    """Per started minute, minimum 1, ignoring up to 0.5 s of encoder/container padding."""
    if not seconds:
        return 1
    return max(1, math.ceil(max(0.0, seconds - BILLING_TOLERANCE_SECONDS) / 60))
