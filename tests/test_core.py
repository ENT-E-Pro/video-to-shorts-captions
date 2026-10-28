import os, subprocess, pytest
from src.captions import probe, extract_audio, transcribe
from src.core import (foreground_bottom, ass_color, resolve_style, build_ass, video_filter, plan_clip, render, billable_minutes,
                      ShortsError, STYLES, MODES)

SEGS = [{"start": 0.0, "end": 2.0, "text": "one two three four five", "words": [
    {"word": " " + w, "start": i * 0.4, "end": i * 0.4 + 0.35} for i, w in enumerate(["one", "two", "three", "four", "five"])]}]


ASSET = os.path.join(os.path.dirname(__file__), "assets", "speech.mp3")  # 9 s LibriVox (public domain) speech


@pytest.fixture(scope="module")
def talk(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("m") / "talk.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=9",
                    "-i", ASSET, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", p],
                   check=True)
    return p


@pytest.fixture(scope="module")
def silent_video(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("m") / "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=12",
                    "-c:v", "libx264", "-preset", "ultrafast", p], check=True)
    return p


def test_ass_color():
    assert ass_color("#FFE600") == "&H0000E6FF"
    assert ass_color("112233", 0x80) == "&H80332211"
    with pytest.raises(ShortsError):
        ass_color("yellow")


def test_resolve_style_overrides_and_validation():
    s = resolve_style("bold", {"font": "anton", "fontSize": 999, "uppercase": False, "position": None})
    assert s["font"] == "anton" and s["fontSize"] == 200 and s["uppercase"] is False and s["position"] == "auto"
    for bad in [("nope", {}), ("bold", {"font": "comic"}), ("bold", {"position": "left"}), ("bold", {"textColor": "x"})]:
        with pytest.raises(ShortsError):
            resolve_style(*bad)


def test_build_ass_word_highlight():
    script, cues = build_ass(SEGS, 1080, 1920, resolve_style("bold", None))
    assert "PlayResY: 1920" in script and "Poppins ExtraBold" in script
    dlg = [l for l in script.splitlines() if l.startswith("Dialogue:")]
    assert len(cues) == 2 and len(dlg) == 5  # one event per highlighted word
    assert dlg[0].endswith("{\\c&H0000E6FF}ONE{\\r} TWO THREE")
    assert "\\c&H0000E6FF" in dlg[1] and "TWO" in dlg[1]


def test_build_ass_plain_and_scaling():
    script, cues = build_ass(SEGS, 720, 1280, resolve_style("boxed", None))
    dlg = [l for l in script.splitlines() if l.startswith("Dialogue:")]
    assert len(dlg) == len(cues) == 1 and "one two three four five" in dlg[0]
    assert ",40," in script.split("Style: Cap,")[1][:40]  # 60px @1080 -> 40px @720


def test_plan_clip():
    info = {"video": {"width": 1920}, "duration": 300.0}
    assert plan_clip(info, 10, 40, 60).duration == 30
    assert plan_clip(info, 100, None, 60).duration == 60
    assert plan_clip(info, 0, None, 999).duration == 180  # hard cap
    assert plan_clip(info, 290, 400, 60).duration == 10
    for a in [(400, None), (50, 40), (-1, None)]:
        with pytest.raises(ShortsError):
            plan_clip(info, *a, 60)
    with pytest.raises(ShortsError):
        plan_clip({"video": None, "duration": 10}, 0, None, 60)


def test_billable_minutes():
    assert billable_minutes(30) == 1 and billable_minutes(61) == 2 and billable_minutes(None) == 1


@pytest.mark.parametrize("mode", MODES)
def test_render_modes(silent_video, tmp_path, mode):
    out = str(tmp_path / f"{mode}.mp4")
    plan = plan_clip(probe(silent_video), 2, 7, 60)
    render(silent_video, out, plan, video_filter(mode, 720, 1280, 0.3, 20, "#202020"), False)
    i = probe(out)
    assert (i["video"]["width"], i["video"]["height"]) == (720, 1280) and abs(i["duration"] - 5) < 0.2 and not i["audio"]


def test_end_to_end_burned_captions(talk, tmp_path):
    info = probe(talk)
    plan = plan_clip(info, 0, None, 60)
    wav = str(tmp_path / "a.wav")
    extract_audio(talk, wav, plan.start, plan.duration)
    t = transcribe(wav, "tiny", "en")
    script, cues = build_ass(t.segments, 720, 1280, resolve_style("bold", None))
    assert cues and "EXPRESS" in script
    ass = str(tmp_path / "s.ass"); open(ass, "w").write(script)
    out_c, out_n = str(tmp_path / "c.mp4"), str(tmp_path / "n.mp4")
    render(talk, out_c, plan, video_filter("blur", 720, 1280, ass_path=ass), True)
    render(talk, out_n, plan, video_filter("blur", 720, 1280), True)
    i = probe(out_c)
    assert i["audio"] and i["video"]["height"] == 1280
    # captions actually burned in: frames differ in the caption area
    def frame(p, at):
        return subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", p, "-frames:v", "1", "-vf", "crop=720:400:0:800",
                               "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    diffs = [sum(abs(x - y) > 40 for x, y in zip(frame(out_c, at), frame(out_n, at))) for at in (1.0, 2.0, 3.0, 4.0, 5.0)]
    assert max(diffs) > 2000, diffs


def test_auto_caption_position():
    land = {"video": {"width": 1920, "height": 1080, "rotation": 0}}
    vb = foreground_bottom("blur", land, 1080, 1920)
    assert vb == (1920 + 608) // 2
    assert foreground_bottom("crop", land, 1080, 1920) is None
    assert foreground_bottom("blur", {"video": {"width": 1920, "height": 1080, "rotation": 90}}, 1080, 1920) is None
    s = resolve_style("bold", None)
    script, _ = build_ass(SEGS, 1080, 1920, s, vb)
    style = script.split("Style: Cap,")[1].split("\n")[0].split(",")
    assert style[17] == "8" and int(style[20]) > vb  # top-aligned, below the video
    script, _ = build_ass(SEGS, 1080, 1920, s, None)
    style = script.split("Style: Cap,")[1].split("\n")[0].split(",")
    assert style[17] == "2" and style[20] == str(int(1920 * 0.28))
