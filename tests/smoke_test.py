#!/usr/bin/env python3
"""Scan the source fixtures and check the main rule families fire, and that failures are readable. Run: python tests/smoke_test.py"""
import json, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
scan = str(root / "skills/wave-a11y-scan/scripts/scan.py")
fixtures = root / "tests" / "fixtures"
out = Path(tempfile.mkdtemp())


def sc(*args):
    return subprocess.run([sys.executable, scan, *args], capture_output=True, text=True)


problems = []
r = sc(str(fixtures), "--out", str(out / "ok"))
if r.returncode != 0:
    problems.append(f"scan failed: {r.stderr[-300:]}")
res = json.loads((out / "ok/results.json").read_text())["results"] if (out / "ok/results.json").exists() else {}
by_file = {}
for cat in res.values():
    for rid, inst in cat.items():
        for i in inst:
            by_file.setdefault(i["file"], set()).add(rid)
expect = {
    "violations.html": {"title_invalid", "language_missing", "alt_missing", "alt_suspicious", "link_suspicious", "link_empty", "button_empty",
                        "label_missing", "label_orphaned", "contrast", "text_small", "table_layout", "aria_reference_broken",
                        "heading_skipped", "region_missing", "link_internal_broken", "h1_missing"},
    "violations.jsx": {"alt_missing", "alt_suspicious", "link_empty", "link_suspicious", "button_empty", "label_missing", "contrast",
                       "text_small", "heading_skipped", "tabindex"},
    "axe.html": {"video_captions_missing", "id_duplicate", "aria_role_invalid", "aria_attr_invalid", "aria_required_attr", "aria_name_missing",
                 "aria_hidden_focusable", "nested_interactive", "input_button_name_missing", "role_img_alt_missing", "label_in_name_mismatch",
                 "scope_attr_invalid", "main_multiple", "inline_spacing_important"},
    "checklist.html": {"viewport_zoom_blocked", "focus_outline_removed", "h1_multiple", "iframe_title_missing", "media_autoplay", "dialog_name_missing"},
    "wcag22.jsx": {"target_size_small", "focus_obscured_risk", "auth_autocomplete_off", "auth_paste_blocked", "captcha_present", "dragging_alternative",
                   "autocomplete_missing", "text_spacing_clipped", "hover_without_focus", "orientation_locked", "reduced_motion_missing",
                   "click_no_keyboard", "icon_button_name_missing", "status_role_missing", "datagrid_review", "dialog_name_missing"},
}
for f, rules in expect.items():
    miss = rules - by_file.get(f, set())
    if miss:
        problems.append(f"{f}: missing {sorted(miss)}")
jsx = [(c, rid, i["line"]) for c, cat in res.items() for rid, inst in cat.items() for i in inst if i["file"] == "violations.jsx"]
if sum(1 for c, rid, ln in jsx if rid == "button_empty") != 2:
    problems.append("violations.jsx: expected 2 empty buttons (the icon-only <X/> button, and the empty <button>), not the one with a title")
if any(i["file"] == "violations.jsx" and "bg-primary" in (i["html"] or "") for i in res.get("contrast", {}).get("contrast", [])):
    problems.append("violations.jsx: a Tailwind bg-primary button must not be reported for contrast")
if any(rid == "event_handler" for c, rid, ln in jsx):
    problems.append("violations.jsx: a custom <Button> component must not get event_handler")
# values only known at runtime must never be reported: violations.jsx line 13 is <img src={src} alt={desc}>
for cat in ("error", "alert", "contrast"):
    for inst in res.get(cat, {}).values():
        if any(i["file"] == "violations.jsx" and i["line"] == 13 for i in inst):
            problems.append("violations.jsx:13 has a runtime alt and must not be reported")
# Mass.gov checklist fixture: exact counts so false positives show up
cl = [(rid, i["line"]) for cat in res.values() for rid, inst in cat.items() for i in inst if i["file"] == "checklist.html"]
for rid, want in (("focus_outline_removed", 1), ("iframe_title_missing", 1), ("dialog_name_missing", 1), ("h1_multiple", 1)):
    got = sum(1 for r, _ in cl if r == rid)
    if got != want:
        problems.append(f"checklist.html: expected {want} x {rid}, got {got} (button:focus has a box-shadow, the titled iframe and named dialog are fine)")
ax = [(rid, i["line"]) for cat in res.values() for rid, inst in cat.items() for i in inst if i["file"] == "axe.html"]
for rid, want in (("aria_name_missing", 2), ("aria_hidden_focusable", 1), ("input_button_name_missing", 1), ("role_img_alt_missing", 1),
                  ("label_in_name_mismatch", 1), ("video_captions_missing", 1), ("aria_required_attr", 1), ("nested_interactive", 1)):
    got = sum(1 for r, _ in ax if r == rid)
    if got != want:
        problems.append(f"axe.html: expected {want} x {rid}, got {got} (the labelled, tabindex=-1, titled and captioned variants are fine)")
w22 = [rid for cat in res.values() for rid, inst in cat.items() for i in inst if i["file"] == "wcag22.jsx"]
for rid, want in (("target_size_small", 1), ("click_no_keyboard", 1), ("icon_button_name_missing", 1), ("dialog_name_missing", 1),
                  ("autocomplete_missing", 1), ("status_role_missing", 1), ("auth_autocomplete_off", 1)):
    if w22.count(rid) != want:
        problems.append(f"wcag22.jsx: expected {want} x {rid}, got {w22.count(rid)} (the 44px button, keyboard div, labelled IconButton, named Dialog, autocomplete=email and role=status variants are fine)")
report = (out / "ok/report.md").read_text(encoding="utf-8") if (out / "ok/report.md").exists() else ""
if "## Mass.gov Web Testing Checklist" not in report or len(__import__("re").findall(r"^\| M\d\d \|", report, __import__("re").M)) != 50:
    problems.append("report.md must hold the Mass.gov checklist section with all 50 items")
if "## Additional WCAG 2.2, WCAG 2.1 and React checks" not in report or len(__import__("re").findall(r"^\| W\d\d \|", report, __import__("re").M)) != 21:
    problems.append("report.md must hold the additional WCAG 2.2 section with all 21 items")
if "webaim.org/resources/contrastchecker/?fcolor=" not in report or "| Open source |" not in report:
    problems.append("report.md must hold WebAIM verify links for contrast errors and the tools table with an Open source column")
print("OK" if not problems else "PROBLEMS: " + "; ".join(problems))

# error handling: readable failures, bad options rejected
r = sc(str(out / "does-not-exist"))
if r.returncode != 3 or "Traceback" in r.stderr:
    problems.append("a missing path must exit 3 with a one-line message")
empty = out / "empty"
empty.mkdir()
(empty / "a.txt").write_text("nothing")
r = sc(str(empty), "--out", str(out / "none"))
if r.returncode != 3 or "Traceback" in r.stderr or (out / "none/report.md").exists():
    problems.append("when no markup is found: exit 3, a one-line message, no report")
if sc(str(fixtures), "--format", "pdf").returncode != 2:
    problems.append("an unknown --format must be rejected")
print("OK (error handling)" if len(problems) == 0 else "PROBLEMS: " + "; ".join(problems))
sys.exit(1 if problems else 0)
