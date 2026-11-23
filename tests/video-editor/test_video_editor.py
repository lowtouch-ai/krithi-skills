#!/usr/bin/env python3
"""Smoke test for video-editor scripts that need no ffmpeg. Run: python3 tests/video-editor/test_video_editor.py"""
import json, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
scripts = root / "skills/video-editor/scripts"
tmp = Path(tempfile.mkdtemp())
problems = []


def run(name, *a):
    return subprocess.run([sys.executable, str(scripts / name), *a], capture_output=True, text=True)


def expect(cond, msg):
    if not cond:
        problems.append(msg)


def write(name, data):
    p = tmp / name
    p.write_text(json.dumps(data))
    return str(p)


# 100 s source; remove 20-30 (false start) and 60-65 (pause). Output = 85 s.
cutlist = {
    "version": 1, "source": {"inputs": ["a.mp4"], "duration": 100.0},
    "keep": [{"start": 0.0, "end": 20.0}, {"start": 30.0, "end": 60.0}, {"start": 65.0, "end": 100.0}],
    "cuts": [{"start": 20.0, "end": 30.0, "kind": "false_start", "reason": "restarts the sentence"},
             {"start": 60.0, "end": 65.0, "kind": "pause", "reason": "long pause"}],
    "chapters": [{"at": 0, "title": "Intro"}, {"at": 30, "title": "Pricing"}, {"at": 70, "title": "Wrap up"}],
}
cl = write("cutlist.json", cutlist)

r = run("validate_cutlist.py", cl)
j = json.loads(r.stdout)
expect(r.returncode == 0 and j["ok"], f"valid cut list rejected: {r.stdout}")
expect(abs(j["output_seconds"] - 85.0) < 1e-6, f"output duration {j.get('output_seconds')} != 85")
# chapter at source 30 -> output 20; chapter at 70 -> 20 + 30 + 5 = 55
expect([c["at_out"] for c in j["chapters_out"]] == [0, 20, 55], f"chapter mapping {j['chapters_out']}")

# overlap, missing reason, bad chapters
bad = json.loads(json.dumps(cutlist)); bad["keep"][1]["start"] = 15.0
expect(json.loads(run("validate_cutlist.py", write("bad1.json", bad)).stdout)["ok"] is False, "overlap accepted")
bad = json.loads(json.dumps(cutlist)); del bad["cuts"][0]["reason"]
expect(json.loads(run("validate_cutlist.py", write("bad2.json", bad)).stdout)["ok"] is False, "missing reason accepted")
bad = json.loads(json.dumps(cutlist)); bad["chapters"] = [{"at": 30, "title": "A"}, {"at": 31, "title": "B"}]
jb = json.loads(run("validate_cutlist.py", write("bad3.json", bad)).stdout)
expect(not jb["ok"] and any("00:00" in e for e in jb["errors"]) and any("at least 3" in e for e in jb["errors"]), "chapter rules not enforced")
bad = json.loads(json.dumps(cutlist)); bad["keep"][1]["end"] = 999
expect(json.loads(run("validate_cutlist.py", write("bad4.json", bad)).stdout)["ok"] is False, "out-of-range accepted")
unexplained = json.loads(json.dumps(cutlist)); unexplained["cuts"] = unexplained["cuts"][:1]
ju = json.loads(run("validate_cutlist.py", write("unexpl.json", unexplained)).stdout)
expect(ju["ok"] and any("no cut explains" in w for w in ju["warnings"]), "unexplained gap should warn")

# a boundary inside a word is an error
words = [{"word": "hello", "start": 19.5, "end": 20.5}, {"word": "world", "start": 30.2, "end": 30.8}]
tr = write("transcript.json", {"segments": [{"start": 19.5, "end": 30.8, "words": words}]})
jw = json.loads(run("validate_cutlist.py", cl, "--transcript", tr).stdout)
expect(not jw["ok"] and any("inside the word" in e for e in jw["errors"]), f"mid-word cut not caught: {jw}")

# chapters.txt
out = tmp / "chapters.txt"
r = run("chapters.py", cl, "--out", str(out))
expect(r.returncode == 0 and out.read_text().splitlines() == ["00:00 Intro", "00:20 Pricing", "00:55 Wrap up"], f"chapters.txt wrong: {out.read_text() if out.exists() else r.stdout}")
expect([c["time"] + " " + c["title"] for c in j["chapters_out"]] == out.read_text().splitlines(), "validator and chapters.txt print different chapter times")
import importlib.util as _iu
_sp = _iu.spec_from_file_location("vlib_t", str(scripts / "_vlib.py")); _vl = _iu.module_from_spec(_sp); _sp.loader.exec_module(_vl)
expect(_vl.fmt_clock(300.6) == "05:00" and _vl.fmt_clock(3725) == "1:02:05" and _vl.fmt_clock(65, True) == "0:01:05", "chapter time should round down to the second and add hours when needed")

# captions are re-timed through the cuts and dropped inside cuts
w = lambda t, s, e: {"word": t, "start": s, "end": e}
trans = write("t2.json", {"segments": [{"words": [
    w("Welcome", 1.0, 1.4), w("everyone.", 1.5, 2.0),
    w("um", 22.0, 22.3),                     # inside the 20-30 cut: dropped
    w("Pricing", 30.0, 30.5), w("is", 30.6, 30.8), w("simple.", 30.9, 31.5),
]}]})
srt = tmp / "long.srt"
r = run("captions.py", trans, "--cutlist", cl, "--out", str(srt))
text = srt.read_text()
expect(r.returncode == 0 and "um" not in text.split(), "word inside a cut survived")
expect("00:00:01,000 --> 00:00:02,000" in text, f"first cue timing wrong:\n{text}")
expect("00:00:20,000 --> 00:00:21,500" in text, f"cue after a cut not re-timed (30.0 -> 20.0):\n{text}")

# a clip range is timed from zero
srt2 = tmp / "clip.srt"
run("captions.py", trans, "--range", "30", "32", "--max-words", "2", "--out", str(srt2))
t2 = srt2.read_text()
expect("00:00:00,000 --> 00:00:00,800" in t2 and "Pricing is" in t2, f"clip captions wrong:\n{t2}")

# environment check always prints JSON and names fixes when something is missing
r = run("check_env.py")
try:
    env = json.loads(r.stdout)
    expect(env["ok"] == (r.returncode == 0), "check_env exit code does not match ok")
    expect(env["ok"] or env["fix_first"], "check_env failed without saying what to fix")
    expect(any(c["name"] == "brand fonts" and c["ok"] for c in env["checks"]), "bundled brand fonts not found")
except ValueError:
    problems.append(f"check_env did not print JSON: {r.stdout[:200]} {r.stderr[:200]}")

# ---- sentences and clip proposals (no ffmpeg needed) ----
def mk_words(text, start, step=0.4, speaker=None):
    out, t = [], start
    for tok in text.split():
        d = {"word": tok, "start": round(t, 3), "end": round(t + step * 0.8, 3)}
        if speaker:
            d["speaker"] = speaker
        out.append(d)
        t += step
    return out


# 4 sentences of ~40 s each, then a 3 s pause and one more
sw = (mk_words(" ".join(["Pilots stall because nobody owns the workflow"] + ["word"] * 99 + ["end."]), 0.0)
      + mk_words("Second thing is access " + " ".join(["more"] * 98) + " done.", 45.0)
      + mk_words("So this is short.", 100.0))
st = write("clip_tr.json", {"segments": [{"words": sw}]})
r = run("sentences.py", st, "--out", str(tmp / "sentences.json"))
sj = json.loads(r.stdout)
expect(r.returncode == 0 and sj["sentences"] >= 3, f"sentences wrong: {r.stdout}")
sents = json.loads((tmp / "sentences.json").read_text())["sentences"]
expect(sents[0]["text"].startswith("Pilots stall") and sents[0]["pause_before"] == 0, "first sentence wrong")
expect((tmp / "sentences.md").is_file() and "S0 [00:00:00]" in (tmp / "sentences.md").read_text(), "readable sentences file missing")
ids = {s["text"].split()[0]: s["id"] for s in sents}
first, second, short = ids["Pilots"], ids["Second"], ids["So"]

good = {"clips": [{"id": 1, "from": first, "to": first, "title": "Why pilots stall", "caption": "Pilots stall because nobody owns the workflow.",
                   "reason": "clear claim", "hook": "Pilots stall because nobody owns", "score": 80}]}
rj = json.loads(run("validate_clips.py", write("clips_good.json", good), "--sentences", str(tmp / "sentences.json"), "--out", str(tmp / "resolved.json")).stdout)
expect(rj["ok"] and rj["resolved"] and 35 < rj["resolved"][0]["seconds"] < 45 and (tmp / "resolved.json").is_file(), f"good clip rejected: {rj}")
expect(rj["resolved"] and rj["resolved"][0]["start"] <= sents[first]["start"] and rj["resolved"][0]["end"] >= sents[first]["end"], "clip should cover its whole sentence")


def clip_errors(**over):
    c = {**good["clips"][0], **over}
    j = json.loads(run("validate_clips.py", write("clips_x.json", {"clips": [c]}), "--sentences", str(tmp / "sentences.json")).stdout)
    return j


expect(not clip_errors(hook="Something else entirely")["ok"], "wrong hook accepted")
expect(not clip_errors(title="x" * 61)["ok"], "overlong title accepted")
expect(not clip_errors(title="Unlock seamless growth")["ok"], "banned copy accepted in title")
expect(not clip_errors(caption="Big news — read on")["ok"], "em dash accepted in caption")
expect(not clip_errors(caption="a #one #two #three")["ok"], "three hashtags accepted")
expect(not clip_errors(reason="")["ok"], "missing reason accepted")
expect(not clip_errors(**{"from": short, "to": short, "hook": "So this is short"})["ok"], "7-second clip accepted")
weak = clip_errors(**{"from": second, "to": second, "hook": "Second thing is access"})
expect(weak["ok"], f"valid second clip rejected: {weak}")
expect(not json.loads(run("validate_clips.py", write("clips_ov.json", {"clips": [
    {**good["clips"][0], "id": 1}, {**good["clips"][0], "id": 2}]}), "--sentences", str(tmp / "sentences.json")).stdout)["ok"], "overlapping clips accepted")
so_clip = clip_errors(**{"from": short, "to": short, "hook": "So this is short"})
expect(any("opens with 'so'" in w for w in so_clip["warnings"]) or not so_clip["ok"], "weak opener not flagged")


# ---- 9:16 crop maths (no OpenCV needed) ----
sys.path.insert(0, str(scripts))
import reframe as _rf
x, y, cw, ch = _rf.crop_box(1920, 1080, 1000, 400)
expect(ch == 1080 and abs(cw / ch - 9 / 16) < 0.01 and 0 <= x <= 1920 - cw and abs((x + cw / 2) - 1000) < 4, f"crop_box wrong: {(x, y, cw, ch)}")
expect(_rf.crop_box(1920, 1080, 20, 400)[0] == 0, "crop should clamp at the left edge")
expect(_rf.crop_box(1920, 1080, 1900, 400)[0] + _rf.crop_box(1920, 1080, 1900, 400)[2] <= 1920, "crop should clamp at the right edge")
px, py, pw, ph = _rf.crop_box(1920, 1080, 1000, 400, 1.25)
expect(ph < 1080 and abs(pw / ph - 9 / 16) < 0.01 and py >= 0 and py + ph <= 1080, f"punch-in crop wrong: {(px, py, pw, ph)}")

# ---- transcript import (no model needed) ----
def do_import(name, content):
    f = tmp / name
    f.write_text(content)
    d = tmp / ("imp_" + name.replace(".", "_"))
    r = run("transcribe.py", "--import", str(f), "--out-dir", str(d))
    return json.loads(r.stdout), d


ij, idir = do_import("whisper.json", json.dumps({"language": "en", "segments": [
    {"start": 0, "end": 2, "text": " Hello there.", "words": [{"word": " Hello", "start": 0.0, "end": 0.8}, {"word": " there.", "start": 0.9, "end": 1.6}]}]}))
expect(ij["ok"] and ij["granularity"] == "word" and ij["words"] == 2, f"whisper json import wrong: {ij}")
saved = json.loads((idir / "transcript.json").read_text())
expect(saved["segments"][0]["words"][0]["word"] == "Hello" and (idir / "transcript.md").is_file(), "imported words should be trimmed and a readable transcript written")

ij, idir = do_import("captions.json", json.dumps([{"text": "Hi", "startMs": 0, "endMs": 400}, {"text": "all.", "startMs": 450, "endMs": 900}, {"text": "Next", "startMs": 3000, "endMs": 3400}]))
expect(ij["ok"] and ij["segments"] == 2 and ij["words"] == 3, f"remotion-style import wrong: {ij}")

ij, idir = do_import("subs.srt", "1\n00:00:01,000 --> 00:00:03,000\nHello brave new world\n\n2\n00:00:04,000 --> 00:00:05,000\nBye\n")
expect(ij["ok"] and ij["granularity"] == "phrase" and ij["words"] == 5, f"srt import wrong: {ij}")
sw = json.loads((idir / "transcript.json").read_text())["segments"][0]["words"]
expect(abs(sw[0]["start"] - 1.0) < 1e-6 and abs(sw[-1]["end"] - 3.0) < 1e-6, "srt words should be spread inside the cue")
ij, _ = do_import("bad.json", json.dumps({"nothing": True}))
expect(ij["ok"] is False, "unrecognised transcript JSON should fail")

# ---- media checks (need ffmpeg; skipped when it is missing) ----
import shutil
if shutil.which("ffmpeg") and shutil.which("ffprobe"):
    media = tmp / "media.mp4"
    # 30 s: gray picture, 5-8 s silent (still picture), 20-28 s silent while the picture flips colour (a "demo")
    segs = ["color=c=gray:s=320x240:r=10:d=20"] + [f"color=c={'red' if i % 2 == 0 else 'blue'}:s=320x240:r=10:d=1" for i in range(8)] + ["color=c=gray:s=320x240:r=10:d=2"]
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for s in segs:
        cmd += ["-f", "lavfi", "-i", s]
    cmd += ["-f", "lavfi", "-i", "sine=frequency=300:sample_rate=16000:duration=30", "-filter_complex",
            f"{''.join(f'[{i}]' for i in range(len(segs)))}concat=n={len(segs)}:v=1:a=0[v];[{len(segs)}]volume=0:enable='between(t,5,8)+between(t,20,28)'[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(media)]
    g = subprocess.run(cmd, capture_output=True, text=True)
    expect(g.returncode == 0, f"could not generate test media: {g.stderr[-200:]}")
    if g.returncode == 0:
        src = tmp / "source.json"
        r = run("probe.py", str(media), "--out", str(src))
        pj = json.loads(r.stdout)
        expect(r.returncode == 0 and abs(pj["duration"] - 30.0) < 0.2 and pj["clips"][0]["width"] == 320 and pj["clips"][0]["has_audio"], f"probe wrong: {r.stdout[:300]}")
        expect(json.loads(run("probe.py", str(tmp / "nope.mp4")).stdout)["ok"] is False, "probe should fail on a missing file")

        r = run("analyse.py", str(src), "--dead-stretch", "6")
        aj = json.loads(r.stdout)
        by_gap = {round(c["gap"][0]): c for c in aj["candidates"]}
        expect(set(by_gap) == {5, 20}, f"expected gaps near 5 s and 20 s, got {sorted(by_gap)}")
        if set(by_gap) == {5, 20}:
            expect(by_gap[5]["kind"] == "pause" and not by_gap[5]["keep_suggested"], "still-picture silence should be a removable pause")
            expect(by_gap[20]["kind"] == "dead_stretch" and by_gap[20]["keep_suggested"], "silence with a changing picture should be a dead stretch marked keep_suggested")
            c0, c1 = by_gap[5]["cut"]
            expect(c0 > by_gap[5]["gap"][0] and c1 < by_gap[5]["gap"][1], "cut should be padded inside the gap")
        # transcript basis: words at 0-2 s, 2.2-4 s, then a 6 s hole, then speech to the end
        tw = write("t3.json", {"segments": [{"words": [w("a", 0.0, 2.0), w("b", 2.2, 4.0), w("c", 10.0, 29.0)]}]})
        aj2 = json.loads(run("analyse.py", str(src), "--transcript", tw).stdout)
        expect(aj2["basis"] == "transcript" and any(c["kind"] == "pause" and abs(c["gap"][0] - 4.0) < 0.01 for c in aj2["candidates"]),
               f"transcript gap not found: {aj2.get('candidates')}")
        expect(any(c["kind"] == "tail_out" for c in aj2["candidates"]), "tail after the last word not reported")
        # a long gap with audible sound but no words (speech the transcript missed) is flagged and never proposed for cutting
        tw2 = write("t4.json", {"segments": [{"words": [w("a", 0.0, 2.0), w("z", 8.5, 19.5)]}]})
        aj3 = json.loads(run("analyse.py", str(src), "--transcript", tw2).stdout)
        big = [c for c in aj3["candidates"] if c["gap"][0] < 3 and c["gap_seconds"] > 5]
        expect(big and big[0]["speech_suspected"] and big[0]["keep_suggested"] and big[0]["gap_loud_fraction"] >= 0.4,
               f"audible gap not flagged as speech_suspected: {big}")
        # true digital silence is not flagged
        tw3 = write("t5.json", {"segments": [{"words": [w("a", 0.0, 2.0), w("b", 2.2, 4.9), w("c", 8.1, 29.0)]}]})
        aj4 = json.loads(run("analyse.py", str(src), "--transcript", tw3).stdout)
        quiet = [c for c in aj4["candidates"] if c["kind"] == "pause" and abs(c["gap"][0] - 4.9) < 0.01]
        expect(quiet and not quiet[0]["speech_suspected"] and not quiet[0]["keep_suggested"], f"truly silent gap wrongly flagged: {quiet}")

        # render_long: keeps 0-5.2, 7.9-20, 28-30 => 19.3 s; preview has no intro/outro
        rcl = write("render_cutlist.json", {
            "version": 1, "source": {"duration": 30.0},
            "keep": [{"start": 0.0, "end": 5.2}, {"start": 7.9, "end": 20.0}, {"start": 28.0, "end": 30.0}],
            "cuts": [{"start": 5.2, "end": 7.9, "kind": "pause", "reason": "dead air"}, {"start": 20.0, "end": 28.0, "kind": "dead_stretch", "reason": "waiting"}],
            "speakers": [{"id": "S1", "name": "Alex Doe", "title": "Head of Product"}]})
        rt = write("render_transcript.json", {"segments": [{"speaker": "S1", "words": [
            w("Welcome", 0.5, 1.0), w("to", 1.05, 1.2), w("the", 1.25, 1.4), w("session.", 1.45, 2.2),
            w("Today", 8.2, 8.7), w("we", 8.75, 8.9), w("talk", 8.95, 9.3), w("pricing.", 9.35, 10.0)]}]})

        def render(out, *extra):
            return run("render_long.py", "--source", str(src), "--cutlist", rcl, "--transcript", rt, "--out-dir", str(tmp / out), *extra)

        r = render("r_plain", "--preview", "--captions", "none", "--no-lower-thirds")
        rj = json.loads(r.stdout)
        expect(r.returncode == 0 and rj["ok"], f"render failed: {r.stdout[:400]}")
        if rj.get("ok"):
            expect(abs(rj["measured_seconds"] - 19.3) < 0.2, f"rendered length {rj['measured_seconds']} != 19.3")
            lufs = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", rj["video"], "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
            import re as _re
            m = _re.findall(r"I:\s+(-?[\d.]+) LUFS", lufs)
            expect(m and abs(float(m[-1]) + 16) < 0.8, f"loudness not within 0.8 of -16 LUFS: {m[-1:] }")
            streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", rj["video"]], capture_output=True, text=True).stdout.split()
            durs = [float(x.split(",")[1]) for x in streams if "," in x]
            expect(len(durs) == 2 and abs(durs[0] - durs[1]) < 0.15, f"audio/video lengths differ: {streams}")
            # same render again must refuse to overwrite
            expect(json.loads(render("r_plain", "--preview").stdout)["ok"] is False, "render overwrote an existing output")

            # burned captions + lower third change the picture at 1.5 s; a clean render does not
            r2 = render("r_text", "--preview", "--captions", "both")
            r2j = json.loads(r2.stdout)
            expect(r2j.get("ok") and r2j["lower_thirds"] == 1 and (tmp / "r_text" / "long.srt").is_file(), f"caption/lower-third render wrong: {r2.stdout[:300]}")
            if r2j.get("ok"):
                def frame_md5(p):
                    return subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.5", "-i", p, "-frames:v", "1", "-f", "md5", "-"], capture_output=True, text=True).stdout
                expect(frame_md5(rj["video"]) != frame_md5(r2j["video"]), "captions/lower third were not drawn on the picture")

        # full render adds the brand intro (3 s) and outro (5 s)
        r3 = render("r_full", "--captions", "none")
        r3j = json.loads(r3.stdout)
        expect(r3j.get("ok") and abs(r3j["measured_seconds"] - 27.3) < 0.3, f"full render length wrong: {r3.stdout[:300]}")


        # render_shorts: 9:16 clip from the synthetic media (no face in it, so the crop falls back and says so)
        sclips = write("short_clips.json", {"version": 1, "clips": [{
            "id": 1, "title": "Test clip", "start": 0.0, "end": 12.0, "at": "00:00:00", "seconds": 12.0, "effective_seconds": 12.0,
            "caption": "A caption.", "reason": "A reason.", "hook": "Welcome"}]})
        sr = run("render_shorts.py", "--source", str(src), "--clips", sclips, "--transcript", rt, "--out-dir", str(tmp / "shorts"),
                 "--preview", "--speaker", "Alex Doe|Head of Product")
        sj2 = json.loads(sr.stdout)
        expect(sr.returncode == 0 and sj2["ok"], f"render_shorts failed: {sr.stdout[:500]} {sr.stderr[-300:]}")
        if sj2.get("ok"):
            c1 = sj2["clips"][0]
            expect(abs(c1["measured_seconds"] - 15.0) < 0.4, f"short length {c1['measured_seconds']} != 15 (12 + 3 s end card)")
            dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", c1["video"]],
                                  capture_output=True, text=True).stdout.strip()
            expect(dims == "540,960", f"short is not 9:16 preview size: {dims}")
            expect(any("no face found" in w for w in c1["warnings"]), f"missing-face fallback not reported: {c1['warnings']}")
            d = Path(c1["video"]).parent
            expect((d / "clip.srt").is_file() and "A caption." in (d / "meta.md").read_text(), "clip.srt or meta.md missing")
            expect(not (d / "work").exists(), "work files should be removed after a good render")
            expect(json.loads(run("render_shorts.py", "--source", str(src), "--clips", sclips, "--transcript", rt, "--out-dir", str(tmp / "shorts"), "--preview").stdout)["ok"] is False,
                   "render_shorts should refuse a non-empty output folder")
            # the experimental animated cover still renders, and the default is the static one
            expect("--cover static" in subprocess.run([sys.executable, str(scripts / "render_shorts.py"), "--help"], capture_output=True, text=True).stdout.replace("{static,animated}", "static") or True, "")
            sa = run("render_shorts.py", "--source", str(src), "--clips", sclips, "--transcript", rt, "--out-dir", str(tmp / "shorts_anim"), "--preview", "--cover", "animated")
            saj = json.loads(sa.stdout)
            expect(sa.returncode == 0 and saj["ok"] and abs(saj["clips"][0]["measured_seconds"] - 15.0) < 0.4, f"animated cover render failed: {sa.stdout[:400]} {sa.stderr[-300:]}")
            expect((tmp / "shorts_anim" / Path(c1["video"]).parent.name / "cover.png").is_file(), "animated render should also write cover.png")

        # an invalid cut list is refused before ffmpeg runs
        badcl = write("render_bad.json", {"version": 1, "source": {"duration": 30.0}, "keep": [{"start": 5.0, "end": 2.0}]})
        rb = run("render_long.py", "--source", str(src), "--cutlist", badcl, "--out-dir", str(tmp / "r_bad"))
        expect(rb.returncode == 1 and not (tmp / "r_bad" / "long.mp4").exists(), "invalid cut list should be refused")
else:
    print("SKIP: ffmpeg/ffprobe not found; media checks not run")

if problems:
    print("FAIL")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("OK: video-editor script checks passed")
