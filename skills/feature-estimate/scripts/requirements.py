#!/usr/bin/env python3
"""Requirements traceability check for feature-estimate (the one check migration-estimate does not have).

Usage: requirements.py [--dir docs/feature-estimate] [--review]

Reads 00-requirements.md (customer inputs and the requirements register) and the detailed PRDs' stories.
Errors (exit 1): no requirements; requirement without a source input, with an unknown input id or a bad status;
an input file that does not exist; a requirement (not marked Out of scope or Deferred) that no story cites;
a story that cites a requirement id that does not exist. Warnings: stories citing no requirement
(use the Source line), requirements still open as Question. With --review, review.md must also have a
'## Requirements coverage' section. Story parsing and sprint maths are migration-estimate's own (imported, not copied).
"""
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base

REGISTER = "00-requirements.md"
STATUSES = ["clear", "assumption", "question", "out of scope", "deferred"]
EXEMPT = ("out of scope", "deferred")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir")
    ap.add_argument("--review", action="store_true")
    a = ap.parse_args()
    d = Path(a.dir).resolve() if a.dir else _base.repo_top() / _base.OUT_DIR
    est = _base.load("estimate")
    errors, warns = [], []
    reg = d / REGISTER
    if not reg.is_file():
        print(json.dumps({"ok": False, "errors": [f"missing {REGISTER}"]}, indent=2))
        return 1
    text = reg.read_text(encoding="utf-8")

    inputs = {}
    for row in re.findall(r"^\|\s*(IN-\d{2,})\s*\|(.*)$", est.section(text, "Customer inputs"), re.M):
        inputs[row[0]] = row[1]
        for p in re.findall(r"`([^`\n]+)`", row[1]):
            if not (d / p).is_file():
                errors.append(f"{REGISTER}: input {row[0]} points to `{p}`, which is not in {d.name}/")
    if not inputs:
        errors.append(f"{REGISTER}: no customer inputs (rows starting IN-01) under '## Customer inputs'")

    reqs = {}
    for rid, rest in re.findall(r"^\|\s*(REQ-\d{2,})\s*\|(.*)$", est.section(text, "Requirements"), re.M):
        cells = [c.strip() for c in rest.strip().rstrip("|").split("|")]
        if len(cells) < 4:
            errors.append(f"{REGISTER}: {rid} needs the columns Requirement | Type | Source | Status")
            continue
        _, _, source, status = cells[:4]
        refs = re.findall(r"IN-\d{2,}", source)
        if not refs:
            errors.append(f"{REGISTER}: {rid} cites no customer input (Source must name an IN-NN)")
        for r_ in refs:
            if r_ not in inputs:
                errors.append(f"{REGISTER}: {rid} cites {r_}, which is not under '## Customer inputs'")
        st = next((s for s in STATUSES if status.lower().startswith(s)), None)
        if not st:
            errors.append(f"{REGISTER}: {rid} status '{status}' must start with one of: Clear, Assumption, Question, Out of scope, Deferred")
        elif st == "question":
            warns.append(f"{rid} is still an open Question; its stories may change once answered")
        reqs[rid] = st
    if not reqs:
        errors.append(f"{REGISTER}: no requirements (rows starting REQ-01) under '## Requirements'")

    cited, uncited_stories, story_count = set(), [], 0
    for f in sorted(d.glob("prd-*.md")):
        body = est.section(f.read_text(encoding="utf-8"), "Stories")
        ms = list(est.STORY_RE.finditer(body))
        for i, m in enumerate(ms):
            story_count += 1
            block = body[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(body)]
            ids = set(re.findall(r"REQ-\d{2,}", block))
            cited |= ids
            for x in sorted(ids - set(reqs)):
                errors.append(f"{f.name}: story {m.group(1)}-S{m.group(2)} cites {x}, which is not in {REGISTER}")
            if not ids:
                uncited_stories.append(f"{m.group(1)}-S{m.group(2)}")
    uncovered = [r for r, s in reqs.items() if s not in EXEMPT and r not in cited]
    for r in uncovered:
        errors.append(f"{r} is not cited by any story (add a story with '**Source:** `{r}`', or mark it Out of scope or Deferred with a reason)")
    if uncited_stories:
        warns.append(f"{len(uncited_stories)} story(ies) cite no requirement: {', '.join(uncited_stories[:8])}{'...' if len(uncited_stories) > 8 else ''}")
    if a.review:
        rv = d / est.REVIEW
        if rv.is_file() and "requirements coverage" not in rv.read_text(encoding="utf-8").lower():
            errors.append(f"{est.REVIEW}: missing section '## Requirements coverage'")
    out = {"ok": not errors, "inputs": len(inputs), "requirements": len(reqs), "covered": sum(1 for r in reqs if r in cited),
           "exempt": sum(1 for s in reqs.values() if s in EXEMPT), "stories": story_count, "uncovered": uncovered,
           "stories_without_requirement": uncited_stories, "errors": errors, "warnings": warns}
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
