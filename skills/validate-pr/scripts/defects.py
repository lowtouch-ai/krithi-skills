#!/usr/bin/env python3
"""Defect register for a validation run: record, challenge, list and compare defects across runs.

Every entry is classified, because only some failures say anything about the PR:
  application       the application does not meet a requirement (a real defect in the PR or what it touches)
  test-automation   the generated test is wrong (bad locator, wrong assumption, race); fix the test, not the app
  environment       the run could not exercise the behaviour (missing service, credentials, browser, port)

Status: open, fixed (a test-automation/environment issue resolved in this run; the record stays), withdrawn.
Confidence: confirmed (reproduced, evidence shows it), likely, needs-verification. Only open, confirmed
application defects can fail a validation (verdict.py).

Required fields: title, classification, confidence, test_case (or "none" with a reason in actual), expected, actual,
steps (list), evidence (paths relative to the run folder, which must exist). Application defects also need severity
(Critical | High | Medium | Low) and requirement.

Usage:
  defects.py add     --run D --file defect.json          # one object or a list; IDs D-1, D-2... are assigned
  defects.py update  --run D --id D-2 --set '{"severity": "Medium"}' --reason "..." [--by reviewer|skill]

Optional: "pre_existing": true for an application defect the PR did not introduce (also seen on the base commit or on
pages the PR does not change; say where in notes). It is reported, but it does not fail the PR (verdict.py).
  defects.py list    --run D [--markdown]
  defects.py compare --run D --previous P [--markdown]   # retest: Resolved / Still open / Needs verification / New

Writes defects/defects.json, defects/D-<n>.md and (compare) defects/retest-comparison.json.
Exit codes: 0 ok, 2 invalid defect or usage error.
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SECRET_RE, log_event, merge_meta, now, out, run_dir  # noqa: E402

CLASSES = ("application", "test-automation", "environment")
SEVERITIES = ("Critical", "High", "Medium", "Low")
CONFIDENCE = ("confirmed", "likely", "needs-verification")
STATES = ("open", "fixed", "withdrawn")  # fixed: a test-automation or environment issue resolved during the run
SEV_ORDER = {s: k for k, s in enumerate(SEVERITIES)}


def load(d):
    p = d / "defects" / "defects.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []


def save(d, items):
    (d / "defects").mkdir(exist_ok=True)
    (d / "defects" / "defects.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
    for x in items:
        (d / "defects" / f"{x['id']}.md").write_text(render(x), encoding="utf-8")
    opened = [x for x in items if x["status"] == "open"]
    merge_meta(d, {"defects": {
        "total": len(items), "open": len(opened),
        "application_confirmed_open": sum(1 for x in opened if x["classification"] == "application" and x["confidence"] == "confirmed"),
        "pre_existing_open": sum(1 for x in opened if x.get("pre_existing")),
        "by_severity": {s: sum(1 for x in opened if x["classification"] == "application" and x.get("severity") == s) for s in SEVERITIES},
        "test_automation_open": sum(1 for x in opened if x["classification"] == "test-automation"),
        "environment_open": sum(1 for x in opened if x["classification"] == "environment")}})


def validate(d, x):
    errs = []
    for f in ("title", "classification", "confidence", "test_case", "expected", "actual", "steps", "evidence"):
        if not x.get(f):
            errs.append(f"missing {f}")
    if x.get("classification") not in CLASSES:
        errs.append(f"classification must be one of {CLASSES}")
    if x.get("confidence") not in CONFIDENCE:
        errs.append(f"confidence must be one of {CONFIDENCE}")
    if x.get("classification") == "application":
        if x.get("severity") not in SEVERITIES:
            errs.append(f"an application defect needs severity, one of {SEVERITIES}")
        if not x.get("requirement"):
            errs.append("an application defect needs the requirement it breaks (R<n>/AC<n>)")
    elif x.get("severity") not in (None, "", *SEVERITIES):
        errs.append(f"severity must be one of {SEVERITIES}")
    if x.get("test_case") and x["test_case"] != "none" and not re.fullmatch(r"TC-\d{1,4}", x["test_case"]):
        errs.append("test_case must be TC-<n> or 'none'")
    if not isinstance(x.get("steps"), list) or not all(isinstance(s, str) and s.strip() for s in x.get("steps") or []):
        errs.append("steps must be a list of reproduction steps")
    for p in x.get("evidence") or []:
        if not (d / p).exists():
            errs.append(f"evidence {p} does not exist in the run folder")
    if "pre_existing" in x and not isinstance(x["pre_existing"], bool):
        errs.append("pre_existing must be true or false")
    if x.get("pre_existing") and not (x.get("notes") or "").strip():
        errs.append("a pre-existing defect needs notes saying where it was also observed (base commit or unchanged pages)")
    if SECRET_RE.search(json.dumps(x)):
        errs.append("the defect text appears to contain a secret; remove it")
    return errs


def fingerprint(x):
    return f"{x.get('classification')}|{x.get('test_case')}|{re.sub(r'[^a-z0-9]+', ' ', x.get('title', '').lower()).strip()[:60]}"


def render(x):
    ev = "\n".join(f"- [{p}](../{p})" for p in x.get("evidence") or [])
    steps = "\n".join(f"{k}. {s}" for k, s in enumerate(x.get("steps") or [], 1))
    hist = "\n".join(f"- {h['at']} ({h.get('by', 'skill')}): {h['change']}. Reason: {h.get('reason', '')}" for h in x.get("history") or [])
    return (f"# {x['id']}: {x['title']}\n\n"
            f"| Field | Value |\n|---|---|\n| Classification | {x['classification']} |\n| Severity | {x.get('severity') or 'n/a'} |\n"
            f"| Confidence | {x['confidence']} |\n| Status | {x['status']} |\n| Test case | {x['test_case']} |\n"
            f"| Requirement | {x.get('requirement') or 'n/a'} |\n| Pre-existing (not introduced by this PR) | {'yes' if x.get('pre_existing') else 'no'} |\n"
            f"| Tested commit | {x.get('tested_commit_sha', '')} |\n\n"
            f"## Expected\n\n{x['expected']}\n\n## Actual\n\n{x['actual']}\n\n## Steps to reproduce\n\n{steps}\n\n"
            f"## Evidence\n\n{ev}\n" + (f"\n## Notes\n\n{x['notes']}\n" if x.get("notes") else "") +
            (f"\n## History\n\n{hist}\n" if hist else ""))


def cmd_add(a):
    d = run_dir(a.run)
    new = json.loads(Path(a.file).read_text(encoding="utf-8"))
    new = new if isinstance(new, list) else [new]
    items = load(d)
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    problems = {}
    for k, x in enumerate(new):
        if errs := validate(d, x):
            problems[x.get("title") or f"item {k}"] = errs
    if problems:
        return out({"error": "invalid defects; nothing was recorded", "problems": problems}, 2)
    nxt = 1 + max([int(x["id"][2:]) for x in items] or [0])
    ids = []
    for x in new:
        x = {**x, "id": f"D-{nxt}", "status": "open", "created_at": now(), "tested_commit_sha": meta.get("tested_commit_sha"),
             "fingerprint": fingerprint(x), "history": []}
        items.append(x)
        ids.append(x["id"])
        log_event(d, {"event": "defect_added", "id": x["id"], "classification": x["classification"], "severity": x.get("severity"),
                      "test_case": x["test_case"]})
        nxt += 1
    save(d, items)
    return out({"added": ids, "register": str(d / "defects" / "defects.json")})


def cmd_update(a):
    d = run_dir(a.run)
    items = load(d)
    x = next((i for i in items if i["id"] == a.id), None)
    if not x:
        return out({"error": f"no defect {a.id}"}, 2)
    if not (a.reason or "").strip():
        return out({"error": "--reason is required: record why the defect changed (the reviewer's argument and the evidence re-checked)"}, 2)
    patch = json.loads(a.set)
    allowed = {"title", "classification", "severity", "confidence", "status", "expected", "actual", "steps", "evidence", "requirement", "notes", "test_case", "pre_existing"}
    if set(patch) - allowed:
        return out({"error": f"cannot change {sorted(set(patch) - allowed)}"}, 2)
    if "status" in patch and patch["status"] not in STATES:
        return out({"error": f"status must be one of {STATES}"}, 2)
    cand = {**x, **patch}
    if errs := validate(d, cand):
        return out({"error": "the change would make the defect invalid", "problems": errs}, 2)
    change = ", ".join(f"{k}: {x.get(k)!r} -> {v!r}" for k, v in patch.items() if x.get(k) != v) or "no field changed"
    cand["history"] = x.get("history", []) + [{"at": now(), "by": a.by, "change": change, "reason": a.reason}]
    cand["fingerprint"] = fingerprint(cand)
    items[items.index(x)] = cand
    save(d, items)
    log_event(d, {"event": "defect_updated", "id": a.id, "by": a.by, "change": change, "reason": a.reason})
    return out({"updated": a.id, "change": change})


def table(items, pre="../"):
    rows = ["| ID | Severity | Class | Confidence | Status | Test case | Requirement | Title |", "|---|---|---|---|---|---|---|---|"]
    key = lambda x: (x["status"] != "open", CLASSES.index(x["classification"]), SEV_ORDER.get(x.get("severity"), 9), int(x["id"][2:]))
    for x in sorted(items, key=key):
        rows.append(f"| [{x['id']}]({pre}defects/{x['id']}.md) | {x.get('severity') or 'n/a'} | {x['classification']}{' (pre-existing)' if x.get('pre_existing') else ''} | {x['confidence']} | "
                    f"{x['status']} | {x['test_case']} | {x.get('requirement') or ''} | {x['title'].replace('|', '/')} |")
    return "\n".join(rows) if items else "No defects recorded."


def cmd_list(a):
    d = run_dir(a.run)
    items = load(d)
    if a.markdown:
        print(table(items, a.link_prefix))
        return 0
    return out(items)


def cmd_compare(a):
    d, p = run_dir(a.run), run_dir(a.previous)
    cur, prev = load(d), load(p)
    sp = d / "results" / "summary.json"
    tcs = json.loads(sp.read_text(encoding="utf-8")).get("test_cases", {}) if sp.is_file() else {}
    rows, matched = [], set()
    for x in prev:
        if x["status"] != "open" or x["classification"] != "application":
            continue
        same = next((c for c in cur if c["status"] == "open" and c["id"] not in matched and
                     (c["fingerprint"] == x["fingerprint"] or (c["classification"] == "application" and c["test_case"] == x["test_case"] != "none"))), None)
        outcome = tcs.get(x["test_case"])
        if same:
            matched.add(same["id"])
            state, why = "Still open", f"re-observed as {same['id']} in this run"
        elif outcome == "passed":
            state, why = "Resolved", f"{x['test_case']} passed on the new commit"
        elif outcome in ("failed", "blocked", "flaky"):
            state, why = "Needs verification", f"{x['test_case']} is {outcome} but no defect has been matched to it yet"
        else:
            state, why = "Needs verification", f"{x['test_case']} was not executed in this run" if x["test_case"] != "none" else "no test case covers it"
        rows.append({"previous_id": x["id"], "title": x["title"], "severity": x.get("severity"), "test_case": x["test_case"],
                     "state": state, "why": why, "current_id": same["id"] if same else None})
    for c in cur:
        if c["status"] == "open" and c["classification"] == "application" and c["id"] not in matched:
            rows.append({"previous_id": None, "title": c["title"], "severity": c.get("severity"), "test_case": c["test_case"],
                         "state": "New", "why": "not reported in the previous run", "current_id": c["id"]})
    pm = json.loads((p / "metadata.json").read_text(encoding="utf-8"))
    cm = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    res = {"previous_run": str(p), "previous_commit": pm.get("tested_commit_sha"), "current_commit": cm.get("tested_commit_sha"),
           "rows": rows, "counts": {s: sum(1 for r in rows if r["state"] == s) for s in ("Resolved", "Still open", "Needs verification", "New")}}
    (d / "defects" / "retest-comparison.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    merge_meta(d, {"retest": {"previous_run": str(p), "previous_commit": res["previous_commit"], **res["counts"]}})
    log_event(d, {"event": "retest_compared", "previous_run": str(p), **res["counts"]})
    if a.markdown:
        print(f"Retest of `{res['current_commit'][:12]}` against `{(res['previous_commit'] or '')[:12]}` "
              f"({', '.join(f'{k}: {v}' for k, v in res['counts'].items())})\n")
        print("| Previous | Current | Severity | Test case | State | Why | Title |\n|---|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['previous_id'] or '—'} | {r['current_id'] or '—'} | {r['severity'] or ''} | {r['test_case']} | **{r['state']}** | {r['why']} | {r['title']} |")
        return 0
    return out(res)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("--run", required=True); p.add_argument("--file", required=True)
    p = sub.add_parser("update"); p.add_argument("--run", required=True); p.add_argument("--id", required=True)
    p.add_argument("--set", required=True); p.add_argument("--reason"); p.add_argument("--by", default="reviewer", choices=("reviewer", "skill"))
    p = sub.add_parser("list"); p.add_argument("--run", required=True); p.add_argument("--markdown", action="store_true")
    p.add_argument("--link-prefix", default="../", help="prefix for defect links; ../ suits report/validation-report.md")
    p = sub.add_parser("compare"); p.add_argument("--run", required=True); p.add_argument("--previous", required=True)
    p.add_argument("--markdown", action="store_true")
    a = ap.parse_args()
    return {"add": cmd_add, "update": cmd_update, "list": cmd_list, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
