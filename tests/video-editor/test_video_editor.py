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

# ---- cuts are placed on real silence (no ffmpeg needed) ----
_sp2 = _iu.spec_from_file_location("vlib_t2", str(scripts / "_vlib.py")); _vl2 = _iu.module_from_spec(_sp2); _sp2.loader.exec_module(_vl2)
lv = _vl2.Levels({"t0": 0.0, "step": 0.1, "threshold_db": -40, "db": [-10] * 50 + [-80] * 20 + [-10] * 5 + [-80] * 40 + [-10] * 10})
run_ = lv.longest_quiet_run(0.0, 12.5)
expect(run_ and abs(run_[0] - 7.5) < 0.11 and abs(run_[1] - 11.5) < 0.11, f"longest quiet run wrong (a loud burst must split a gap): {run_}")
expect(lv.loud(2.0) and not lv.loud(6.0), "loud()/quiet detection wrong")
expect(lv.next_quiet(4.0, 10.0) is not None and abs(lv.next_quiet(4.0, 10.0) - 5.0) < 0.11, "next_quiet wrong")
lvf = write("levels_t.json", {"t0": 0.0, "step": 0.05, "threshold_db": -40, "db": [-10] * 100 + [-80] * 100})
cl_l = write("cut_levels.json", {"version": 1, "source": {"duration": 10.0}, "keep": [{"start": 0.0, "end": 4.0}, {"start": 6.0, "end": 10.0}],
                                 "cuts": [{"start": 4.0, "end": 6.0, "kind": "pause", "reason": "r"}]})
jl = json.loads(run("validate_cutlist.py", cl_l, "--levels", lvf).stdout)
expect(jl["ok"] and any("still going just after it" in w for w in jl["warnings"]), f"cut landing in sound not warned: {jl}")

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

# ---- unreliable stretches: detection and repair (no model needed) ----
_spx = _iu.spec_from_file_location("vlib_t4", str(scripts / "_vlib.py")); _vl3 = _iu.module_from_spec(_spx); _spx.loader.exec_module(_vl3)
import types as _ty
_w2 = lambda t_, s_, e_, p_=0.9: {"word": t_, "start": s_, "end": e_, "probability": p_}
_good = [_w2("one", 0, .4), _w2("two", .5, .9), _w2("three", 1.0, 1.4)]
_bad = [_w2("thank", 5.0, 5.8, 0.0)] + [_w2(f"w{k}", 5.8, 5.8, 0.1) for k in range(6)]
_tail = [_w2("four", 9.0, 9.4), _w2("five", 9.5, 9.9)]
expect(_vl3.unreliable_spans(_good + _tail) == [], "healthy words should not be flagged")
_sp = _vl3.unreliable_spans(_good + _bad + _tail, before=1)
expect(len(_sp) == 1 and _sp[0][0] <= 3 and _sp[0][1] >= 3 + 6, f"a run of zero-length words should be flagged: {_sp}")
_lowc = [_w2(f"x{k}", k * 0.5, k * 0.5 + 0.4, 0.2) for k in range(8)]
expect(len(_vl3.unreliable_spans(_lowc)) == 1, "a long run of low-confidence words should be flagged")
sys.path.insert(0, str(scripts))
import transcribe as _tr


def _seg(words):
    return {"start": words[0]["start"], "end": words[-1]["end"], "text": " ".join(w["word"] for w in words), "words": words}


_segs = [_seg(_good), _seg(_bad), _seg(_tail)]
_mk = lambda t_, s_, e_, p_=0.95: _ty.SimpleNamespace(word=" " + t_, start=s_, end=e_, probability=p_)
_fix = lambda chunk: [_ty.SimpleNamespace(start=0.0, end=4.0, words=[_mk("real", 2.6, 3.0), _mk("words", 3.1, 3.6), _mk("here", 3.7, 4.2)])]
_notes = []
_audio = [0.0] * (16000 * 12)
_out = _tr.repair_unreliable(None, _audio, 0.0, _segs, _fix, None, _notes)
expect(_notes and _notes[0]["status"] == "repaired" and any("real" in sg["text"] for sg in _out) and not any("thank" in sg["text"] for sg in _out),
       f"a healthier re-decode should replace the broken stretch: {_notes} {[sg['text'] for sg in _out]}")
_still = lambda chunk: [_ty.SimpleNamespace(start=0.0, end=1.0, words=[_mk(f"z{k}", 3.0, 3.0, 0.1) for k in range(5)])]
_notes2 = []
_out2 = _tr.repair_unreliable(None, _audio, 0.0, _segs, _still, None, _notes2)
expect(_notes2 and _notes2[0]["status"] == "still unreliable" and any("thank" in sg["text"] for sg in _out2), f"a repair that is still broken must keep the original: {_notes2}")

# the checker: words over silence, collapsed stretches, and --drop
chk_t = write("chk_tr.json", {"engine": "t", "granularity": "word", "language": "en", "segments": [{"start": 0, "end": 30, "text": "x", "words": [
    _w2("hello", 0.2, 0.8), _w2("there", 0.9, 1.5), _w2("thank", 22.0, 22.4), _w2("you", 22.5, 22.9), _w2("so", 23.0, 23.3), _w2("much", 23.4, 23.8),
    _w2("later", 8.5, 9.5)] + [_w2(f"real{k}", 10.0 + k * 1.0, 10.8 + k * 1.0) for k in range(7)]}]})

# ---- review fixes (no ffmpeg needed) ----
sys.path.insert(0, str(scripts))
import check_env as _ce
_none = lambda c: None
_only = lambda *names: (lambda c: "/usr/bin/" + c if c in names else None)
expect(_ce.transcriber_status(True, _none) == (True, "faster-whisper"), "faster-whisper should pass the transcriber check")
_ok_c, _msg_c = _ce.transcriber_status(False, _only("whisper-cli"))
expect(_ok_c is False and "whisper.cpp" in _msg_c and "cannot use" in _msg_c, f"whisper.cpp alone must not pass the check: {_ok_c} {_msg_c}")
expect(_ce.transcriber_status(False, _only("whisper"))[0] is False, "the openai-whisper CLI alone must not pass the check")
expect(_ce.transcriber_status(False, _none) == (False, "none found"), "no transcriber should say so")

ch_cut = {"version": 1, "source": {"duration": 100.0}, "keep": [{"start": 0.0, "end": 20.0}, {"start": 30.0, "end": 60.0}, {"start": 65.0, "end": 100.0}],
          "cuts": [{"start": 20.0, "end": 30.0, "kind": "false_start", "reason": "r"}, {"start": 60.0, "end": 65.0, "kind": "pause", "reason": "r"}]}
str_ch = write("cut_strch.json", {**ch_cut, "chapters": [{"at": "0:00", "title": "Intro"}, {"at": "0:30", "title": "Pricing"}, {"at": "1:10", "title": "Wrap up"}]})
r_sc = run("validate_cutlist.py", str_ch)
j_sc = json.loads(r_sc.stdout)
expect(r_sc.returncode == 0 and j_sc["ok"] and [c["at_out"] for c in j_sc["chapters_out"]] == [0, 20, 55], f"chapter times given as mm:ss should work: {r_sc.stdout[:300]}")
for bad_at in ("soon", None):
    r_b = run("validate_cutlist.py", write("cut_badat.json", {**ch_cut, "chapters": [{"at": bad_at, "title": "X"}]}))
    expect(r_b.returncode == 1 and "Traceback" not in r_b.stderr and json.loads(r_b.stdout)["ok"] is False, f"a bad chapter time must give an error, not a traceback: {r_b.stdout[:200]} {r_b.stderr[-200:]}")
r_bc = run("validate_cutlist.py", write("cut_badcut.json", {**ch_cut, "cuts": [{"start": "abc", "end": 30, "kind": "pause", "reason": "r"}]}))
expect("Traceback" not in r_bc.stderr, f"a bad cut time must not crash: {r_bc.stderr[-200:]}")

# caption and lower-third text cannot inject ASS override tags
import render_long as _rl
_brand, _res = _rl.load_brand(str(_rl.DEFAULT_BRAND))
_ass = _rl.build_ass(_brand, _res, 1920, 1080, [[{"word": "{\\b1}hello", "start": 1.0, "end": 1.5}, {"word": "back\\slash", "start": 1.5, "end": 2.0}]],
                     [{"start": 1.0, "end": 4.0, "name": "A{\\i1}B", "title": "C}D"}], 0.0)
expect("{\\b1}" not in _ass and "{\\i1}" not in _ass and "C}D" not in _ass, "braces or backslashes in text must not become ASS override tags")

# ---- transcript corrections (no ffmpeg needed) ----
_sp3 = _iu.spec_from_file_location("vlib_t3", str(scripts / "_vlib.py")); _vl3 = _iu.module_from_spec(_sp3); _sp3.loader.exec_module(_vl3)
_w = lambda t_, s_, e_: {"word": t_, "start": s_, "end": e_, "probability": 0.9}
fixed, lg = _vl3.apply_corrections([_w("some", 0, .3), _w("are", .3, .5), _w("most", .5, .9), _w("Chat", 1, 1.2), _w("bots.", 1.2, 1.6), _w("lotage", 2, 2.4)],
                                    {"some are most": "some or most", "chat bots": "chatbots", "lotage": "lowtouch"})
expect([x["word"] for x in fixed] == ["some", "or", "most", "chatbots.", "lowtouch"] or False, f"corrections wrong: {[x['word'] for x in fixed]}")
expect(len(lg) == 3 and fixed[3]["start"] == 1 and fixed[3]["end"] == 1.6, f"corrected word should span the original words' time: {fixed[3]}")
spread, _ = _vl3.apply_corrections([_w("x", 0, 1)], {"x": "a b"})
expect(len(spread) == 2 and abs(spread[0]["end"] - 0.5) < 1e-6, f"one word to two should spread the time: {spread}")
ct = write("corr_tr.json", {"engine": "t", "granularity": "word", "language": "en", "segments": [{"start": 0, "end": 3, "text": "x", "words": [
    _w("in", 0, .2), _w("lotage", .3, .7), _w(".ai", .72, 1.0), _w("we", 1.1, 1.2), _w("have", 1.3, 1.5)]}]})
cr = json.loads(run("correct_transcript.py", ct, "--replace", "lotage.ai=lowtouch.ai").stdout)
cdata = json.loads(Path(ct).read_text())
expect(cr["ok"] and cr["changes"] == 1 and [w["word"] for w in cdata["segments"][0]["words"]] == ["in", "lowtouch.ai", "we", "have"], f"correct_transcript wrong: {cr} {[w['word'] for w in cdata['segments'][0]['words']]}")
expect((tmp / "transcript.original.json").is_file() and (tmp / "transcript.edits.json").is_file() and (tmp / "transcript.md").is_file(), "original, edits log and transcript.md should be written")
sj_ = json.loads(run("correct_transcript.py", ct, "--suspects", "--below", "0.95").stdout)
expect(sj_["ok"] and len(sj_["suspects"]) >= 1 and all(x["word"].lower() not in ("in", "we", "have", "the") for x in sj_["suspects"]),
       f"suspects should list content words, not function words: {sj_}")
expect(json.loads(run("correct_transcript.py", ct, "--replace", "bad").stdout)["ok"] is False, "a malformed --replace should fail")

# ---- caption boxes stay on their word, even for a very wide group ----
sys.path.insert(0, str(scripts))
from fontmetrics import Font as _Font
import render_shorts as _rs
_F = _Font(str(root / "skills/video-editor/assets/brand/fonts/Poppins-Bold.ttf"))
_events = []
_ev = lambda layer, a_, b_, style, text: _events.append((layer, a_, b_, style, text))
_g = [{"word": "interfaces.", "start": 0.0, "end": 0.5}, {"word": "extraordinarily", "start": 0.5, "end": 1.0}, {"word": "unmistakable", "start": 1.0, "end": 1.6}]
_rs.caption_box_events(_ev, _F, 540, 960, [_g], int(960 * 0.072), "&HFFFFFF&", "&HFF47FB&", lambda t_: t_)
_txt = [e for e in _events if e[3] == "CapW"]
_fs = int(__import__("re").search(r"\\fs(\d+)", _txt[0][4]).group(1))
_line_w = _F.width("interfaces. extraordinarily unmistakable", _fs)
expect(_line_w <= 540 * 0.91 and "\\q2" in _txt[0][4], f"a wide caption must shrink to fit the frame and never wrap (width {_line_w:.0f} px at size {_fs})")
expect(len(_txt) == 3 and len([e for e in _events if e[3] == "Shape"]) == 3, "one box and one text event per word")

# ---- keyword cards (no ffmpeg needed) ----
sys.path.insert(0, str(scripts))
from fontmetrics import Font as _Font
_fw = _Font(str(root / "skills/video-editor/assets/brand/fonts/Poppins-Bold.ttf")).width("Domain knowledge", 100)
expect(560 <= _fw <= 570, f"font metrics should match libass drawing (about 565 px at size 100): {_fw}")


def card_check(cards, *extra, with_transcript=True):
    clip = {**good["clips"][0], "cards": cards}
    args = ["validate_clips.py", write("clips_cards.json", {"clips": [clip]}), "--sentences", str(tmp / "sentences.json")]
    if with_transcript:
        args += ["--transcript", st]
    return json.loads(run(*args, *extra).stdout)


ok_card = [{"label": "Why pilots stall", "items": [{"text": "Nobody owns it", "say": "nobody owns"}, {"text": "The workflow", "say": "the workflow"}]}]
cj = card_check(ok_card)
expect(cj["ok"] and cj["resolved"][0]["cards"], f"valid card rejected: {cj}")
if cj.get("ok") and cj["resolved"][0]["cards"]:
    it = cj["resolved"][0]["cards"][0]["items"]
    expect(abs(it[0]["at"] - 1.2) < 0.01 and it[1]["at"] > it[0]["at"], f"card item times should come from the spoken words: {it}")
    expect(cj["resolved"][0]["cards"][0]["label"] == "WHY PILOTS STALL", "card label should be upper-cased")
    expect(all("clip_at" in i for i in it) and "clip_start" in cj["resolved"][0]["cards"][0], "resolved cards should give times in the finished clip")
expect(not card_check([{"label": "L", "items": [{"text": "X", "say": "never said this"}]}])["ok"], "a pill whose words are not spoken was accepted")
oo = card_check([{"label": "L", "items": [{"text": "A", "say": "the workflow"}, {"text": "B", "say": "nobody owns"}]}])
expect(not oo["ok"] and any("only spoken earlier" in e for e in oo["errors"]), f"items out of spoken order should say the words were only spoken earlier: {oo['errors']}")
# a word said before AND after the previous item must resolve to the later one
rep_words = mk_words("alpha coding bravo charlie delta " + " ".join(["filler"] * 50) + " foxtrot coding golf. " + " ".join(["more"] * 10) + " end.", 0.0)
rep_tr = write("rep_tr.json", {"segments": [{"words": rep_words}]})
run("sentences.py", rep_tr, "--out", str(tmp / "rep_sent.json"))
rep_clip = {"id": 1, "from": 0, "to": 0, "title": "Repeated word", "caption": "A caption.", "reason": "r", "hook": "alpha coding bravo",
            "cards": [{"label": "L", "items": [{"text": "Delta", "say": "delta"}, {"text": "Coding", "say": "coding"}]}]}
rj_ = json.loads(run("validate_clips.py", write("rep_clips.json", {"clips": [rep_clip]}), "--sentences", str(tmp / "rep_sent.json"), "--transcript", rep_tr).stdout)
expect(rj_["ok"] and rj_["resolved"][0]["cards"][0]["items"][1]["at"] > 15, f"a repeated word should resolve to the one spoken after the previous item: {rj_}")
expect(not card_check([{"label": "L", "items": [{"text": "50% faster", "say": "nobody owns"}]}])["ok"], "a number that is not in the clip was accepted")
expect(not card_check([{"label": "L", "items": [{"text": str(k), "say": "nobody owns"} for k in range(5)]}])["ok"], "more than 4 items accepted")
expect(not card_check([{"label": "one two three four five six seven eight", "items": [{"text": "X", "say": "nobody owns"}]}])["ok"], "an overlong label was accepted")
expect(not card_check([{"label": "Unlock growth", "items": [{"text": "X", "say": "nobody owns"}]}])["ok"], "banned copy accepted in a card label")
expect(not card_check(ok_card, with_transcript=False)["ok"], "cards without a transcript should be refused")

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
        tw = write("t3.json", {"segments": [{"words": [w("a", 0.0, 2.0), w("b", 2.2, 4.0), w("c", 10.0, 20.0)]}]})  # tone really ends at 20 s, then silence
        aj2 = json.loads(run("analyse.py", str(src), "--transcript", tw).stdout)
        expect(aj2["basis"] == "transcript" and any(c["kind"] == "pause" and abs(c["gap"][0] - 4.0) < 0.01 for c in aj2["candidates"]),
               f"transcript gap not found: {aj2.get('candidates')}")
        expect(any(c["kind"] == "tail_out" for c in aj2["candidates"]), "tail after the last word not reported")
        # Whisper's word ends 0.5 s early (4.5 s) but the tone really ends at 5.0 s: the cut must start after 5.0, never inside the sound
        tw6 = write("t6.json", {"segments": [{"words": [w("a", 0.0, 2.0), w("b", 2.2, 4.5), w("c", 8.1, 29.0)]}]})
        aj6 = json.loads(run("analyse.py", str(src), "--transcript", tw6).stdout)
        g6 = [c for c in aj6["candidates"] if c["kind"] == "pause" and abs(c["gap"][0] - 4.5) < 0.01]
        expect(g6 and g6[0]["cut"][0] >= 5.0 and g6[0]["cut"][1] <= 8.0, f"cut not snapped to the real silence (5.0 to 8.0): {g6}")
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
        r3 = render("r_full", "--captions", "srt")
        r3j = json.loads(r3.stdout)
        expect(r3j.get("ok") and abs(r3j["measured_seconds"] - 27.3) < 0.3, f"full render length wrong: {r3.stdout[:300]}")
        # the video starts with a 3 s intro, so the sidecar captions must start 3 s later than the words (first word at 0.5 s)
        srt_full = (tmp / "r_full" / "long.srt").read_text()
        expect("00:00:03,500 --> " in srt_full, f"long.srt must include the 3 s intro offset (first cue at 3.5 s):\n{srt_full[:200]}")
        srt_prev = (tmp / "r_plain" / "long.srt") if (tmp / "r_plain" / "long.srt").exists() else None


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
            # the default cover is the staggered reveal; the plain static cover still renders too
            sa = run("render_shorts.py", "--source", str(src), "--clips", sclips, "--transcript", rt, "--out-dir", str(tmp / "shorts_static"), "--preview", "--cover", "static")
            saj = json.loads(sa.stdout)
            expect(sa.returncode == 0 and saj["ok"] and abs(saj["clips"][0]["measured_seconds"] - 15.0) < 0.4, f"static cover render failed: {sa.stdout[:400]} {sa.stderr[-300:]}")
            expect((tmp / "shorts_static" / Path(c1["video"]).parent.name / "cover.png").is_file(), "static render should also write cover.png")

        # words placed over the silent stretch (22 to 24 s) have no sound behind them; real words over the tone do
        cw = json.loads(run("check_words.py", "--source", str(src), "--transcript", chk_t).stdout)
        expect(cw["ok"] and cw["unvoiced_words"] == 4 and cw["spans"] and "thank you so much" in cw["spans"][0]["text"], f"words over silence not found: {cw}")
        cw2 = json.loads(run("check_words.py", "--source", str(src), "--transcript", chk_t, "--drop").stdout)
        left = [w["word"] for sg in json.loads(Path(chk_t).read_text())["segments"] for w in sg["words"]]
        expect(cw2["dropped"] == 4 and left == ["hello", "there", "later"] + [f"real{k}" for k in range(7)], f"--drop should remove only the words with no sound: {left}")

        # keyword cards render, and the lower third steps aside for them
        cclips = write("card_clips.json", {"version": 1, "clips": [{
            "id": 1, "title": "Test clip", "start": 0.0, "end": 12.0, "at": "00:00:00", "seconds": 12.0, "effective_seconds": 12.0,
            "caption": "A caption.", "reason": "A reason.", "hook": "Welcome",
            "cards": [{"label": "PRICING", "chain": True, "start": 8.0, "end": 11.5,
                       "items": [{"text": "Talk", "say": "talk", "at": 8.95}, {"text": "Pricing", "say": "pricing", "at": 9.35}]}]}]})
        cr = run("render_shorts.py", "--source", str(src), "--clips", cclips, "--transcript", rt, "--out-dir", str(tmp / "shorts_cards"), "--preview", "--speaker", "Alex Doe|Head")
        crj = json.loads(cr.stdout)
        expect(cr.returncode == 0 and crj["ok"] and any("lower third shown from" in w for w in crj["clips"][0]["warnings"]),
               f"with room before the first card (8 s) the name tag should show until the card: {cr.stdout[:500]} {cr.stderr[-300:]}")
        early = write("card_early.json", {"version": 1, "clips": [{
            "id": 1, "title": "Test clip", "start": 0.0, "end": 12.0, "at": "00:00:00", "seconds": 12.0, "effective_seconds": 12.0,
            "caption": "A caption.", "reason": "A reason.", "hook": "Welcome",
            "cards": [{"label": "EARLY", "chain": False, "start": 4.0, "end": 8.0, "items": [{"text": "Welcome", "say": "welcome", "at": 4.4}]}]}]})
        er = run("render_shorts.py", "--source", str(src), "--clips", early, "--transcript", rt, "--out-dir", str(tmp / "shorts_early"), "--preview", "--speaker", "Alex Doe|Head")
        erj = json.loads(er.stdout)
        expect(er.returncode == 0 and erj["ok"] and any("lower third skipped" in w and "less than 3 s" in w for w in erj["clips"][0]["warnings"]),
               f"a first card at 4 s leaves under 3 s, so the name tag should be skipped: {er.stdout[:500]}")

        # one clip failing must not stop the others, and the report must list every clip
        import os as _os
        _os.environ["VE_REEXEC"] = "1"  # never re-launch this test process inside the virtualenv
        import reframe as _rf2
        _real_detect, _calls = _rf2.detect, [0]

        def _flaky(video, ranges, *a_, **k_):
            _calls[0] += 1
            if _calls[0] == 1:
                raise RuntimeError("face model missing (test)")
            # a stand-in face plan (the system Python running the tests has no OpenCV): a centred 9:16 crop of the 320x240 test media
            return {"source_size": [320, 240], "pieces": [{"range": [x0, x1], "crop": {"x": 90, "y": 0, "w": 134, "h": 240}, "faces_found": 1, "samples": 1, "flag": None} for x0, x1 in ranges]}

        _rf2.detect = _flaky
        two = write("two_clips.json", {"version": 1, "clips": [
            {"id": 1, "title": "First", "start": 0.0, "end": 12.0, "at": "00:00:00", "effective_seconds": 12.0, "caption": "c", "reason": "r", "hook": "Welcome"},
            {"id": 2, "title": "Second", "start": 0.0, "end": 12.0, "at": "00:00:00", "effective_seconds": 12.0, "caption": "c", "reason": "r", "hook": "Welcome"}]})
        import io as _io, contextlib as _cl
        _buf = _io.StringIO()
        _argv = sys.argv
        sys.argv = ["render_shorts.py", "--source", str(src), "--clips", two, "--transcript", rt, "--out-dir", str(tmp / "shorts_two"), "--preview", "--no-lower-third"]
        try:
            with _cl.redirect_stdout(_buf):
                _code = _rs.main()
        finally:
            sys.argv = _argv
            _rf2.detect = _real_detect
        _rep = json.loads(_buf.getvalue())
        expect(_code == 1 and len(_rep["clips"]) == 2 and _rep["clips"][0]["ok"] is False and "face detection failed" in _rep["clips"][0]["error"] and _rep["clips"][1]["ok"] is True,
               f"a failing clip must be recorded while the next one still renders: {_rep}")

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
