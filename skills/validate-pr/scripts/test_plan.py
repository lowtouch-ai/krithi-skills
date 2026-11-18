#!/usr/bin/env python3
"""Check a validate-pr test plan (Markdown, committed in the application repository) for traceability:

  requirement / acceptance criterion  ->  test case (TC-nn)  ->  Playwright test whose title contains TC-nn

The plan must contain the two tables from references/test-planning.md:
  | ID | Requirement / acceptance criterion | Source |
  | ID | Scenario | Category | Requirement | Priority | Execution | Spec |

Checks (errors fail the plan; warnings go in the report):
  error    a requirement no test case covers; an Automated test case with no spec, a missing spec file, or no test
           titled with its ID; a TC-nn used in a spec but missing from the plan; duplicate IDs; unknown column values
  warning  no negative or boundary case; UI changed (--ui-changed) but no accessibility case; a Required case that is Manual

Usage:
  test_plan.py check --plan <repo>/docs/test-plans/pr-12-test-plan.md --repo-dir <worktree> [--ui-changed] [--run D] [--markdown]

With --run, the plan's path and SHA-256 and the parsed cases are recorded in the run (metadata.json and
report/test-plan-parsed.json), so the report and verdict.py trace results back to the committed plan.
Exit codes: 0 plan is traceable, 1 errors found, 2 usage error.
"""
import argparse, hashlib, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import log_event, merge_meta, out, run_dir  # noqa: E402

CATEGORIES = {"positive", "negative", "boundary", "accessibility", "regression", "security", "performance"}
PRIORITIES = {"required", "optional"}
EXECUTIONS = {"automated", "manual"}
TC_RE = re.compile(r"\bTC-\d{1,4}\b")
REQ_RE = re.compile(r"\b(?:R|AC|REQ)-?\d+(?:\.\d+)?\b|\bR\d+\b", re.I)


def tables(md):
    """Yield (header cells, rows) for every Markdown pipe table."""
    lines = md.splitlines()
    i = 0
    while i < len(lines) - 1:
        if lines[i].strip().startswith("|") and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            head = [c.strip().lower() for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            yield head, rows
            i = j
        else:
            i += 1


def parse(md):
    reqs, cases = [], []
    for head, rows in tables(md):
        if head[:1] == ["id"] and any("requirement" in h or "criterion" in h for h in head[1:2]):
            for r in rows:
                if r and r[0]:
                    reqs.append({"id": r[0].strip("* `"), "text": r[1] if len(r) > 1 else "", "source": r[2] if len(r) > 2 else ""})
        elif head[:1] == ["id"] and "scenario" in head:
            col = {h: k for k, h in enumerate(head)}

            def get(r, name):
                k = next((v for h, v in col.items() if h.startswith(name)), None)
                return r[k].strip() if k is not None and k < len(r) else ""
            for r in rows:
                if r and TC_RE.search(r[0]):
                    spec = get(r, "spec").strip("` ")
                    cases.append({"id": TC_RE.search(r[0]).group(0), "scenario": get(r, "scenario"), "category": get(r, "category").lower(),
                                  "requirements": [x.upper() for x in REQ_RE.findall(get(r, "requirement"))],
                                  "priority": get(r, "priority").lower(), "execution": get(r, "execution").lower(),
                                  "spec": None if spec in ("", "-", "—", "n/a", "N/A") else spec})
    return reqs, cases


def spec_ids(repo, files):
    found = {}
    for f in files:
        try:
            text = (repo / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for tc in set(TC_RE.findall(text)):
            found.setdefault(tc, set()).add(f)
    return found


def check(plan_path, repo, ui_changed):
    md = plan_path.read_text(encoding="utf-8")
    reqs, cases = parse(md)
    errors, warnings = [], []
    if not reqs:
        errors.append("no requirements table (| ID | Requirement / acceptance criterion | Source |)")
    if not cases:
        errors.append("no test-case table (| ID | Scenario | Category | Requirement | Priority | Execution | Spec |)")
    for kind, ids in (("requirement", [r["id"].upper() for r in reqs]), ("test case", [c["id"] for c in cases])):
        dup = sorted({x for x in ids if ids.count(x) > 1})
        if dup:
            errors.append(f"duplicate {kind} IDs: {', '.join(dup)}")
    for c in cases:
        for field, allowed in (("category", CATEGORIES), ("priority", PRIORITIES), ("execution", EXECUTIONS)):
            if c[field] not in allowed:
                errors.append(f"{c['id']}: {field} '{c[field]}' is not one of {sorted(allowed)}")
        if not c["requirements"]:
            errors.append(f"{c['id']}: names no requirement (use R<n>/AC<n> IDs from the requirements table)")
    req_ids = {r["id"].upper() for r in reqs}
    for c in cases:
        for rid in c["requirements"]:
            if rid not in req_ids:
                errors.append(f"{c['id']}: requirement {rid} is not in the requirements table")
    coverage = {}
    for r in reqs:
        rid = r["id"].upper()
        tcs = [c for c in cases if rid in c["requirements"]]
        coverage[rid] = {"text": r["text"], "test_cases": [c["id"] for c in tcs],
                         "automated": [c["id"] for c in tcs if c["execution"] == "automated"],
                         "manual": [c["id"] for c in tcs if c["execution"] == "manual"]}
        if not tcs:
            errors.append(f"requirement {rid} is not covered by any test case")
    spec_files = sorted({c["spec"] for c in cases if c["spec"]})
    for f in spec_files:
        if not (repo / f).is_file():
            errors.append(f"spec file {f} named in the plan does not exist in the repository")
    ids_in_specs = spec_ids(repo, spec_files)
    for c in cases:
        if c["execution"] == "automated":
            if not c["spec"]:
                errors.append(f"{c['id']}: Automated but no spec file is named")
            elif c["id"] not in ids_in_specs or c["spec"] not in ids_in_specs[c["id"]]:
                errors.append(f"{c['id']}: no test in {c['spec']} has '{c['id']}' in its title")
        elif c["priority"] == "required":
            warnings.append(f"{c['id']}: Required but Manual: the verdict will be at best Needs Manual Verification until it is verified")
    plan_ids = {c["id"] for c in cases}
    for tc, fs in sorted(ids_in_specs.items()):
        if tc not in plan_ids:
            errors.append(f"{tc} is used in {', '.join(sorted(fs))} but is not in the plan")
    cats = {c["category"] for c in cases}
    for need in ("negative", "boundary"):
        if need not in cats:
            warnings.append(f"no {need} test case")
    if ui_changed and "accessibility" not in cats:
        warnings.append("UI files changed but there is no accessibility test case")
    return {"plan": str(plan_path), "sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(), "requirements": reqs, "cases": cases,
            "coverage": coverage, "errors": errors, "warnings": warnings,
            "counts": {"requirements": len(reqs), "cases": len(cases), "automated": sum(c["execution"] == "automated" for c in cases),
                       "manual": sum(c["execution"] == "manual" for c in cases),
                       "required": sum(c["priority"] == "required" for c in cases)}}


def markdown(res):
    rows = ["| Requirement | Test cases | Automated | Manual |", "|---|---|---|---|"]
    for rid, v in res["coverage"].items():
        rows.append(f"| {rid}: {v['text'][:90].replace('|', '/')} | {', '.join(v['test_cases']) or '**none**'} | "
                    f"{', '.join(v['automated']) or '—'} | {', '.join(v['manual']) or '—'} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--plan", required=True); p.add_argument("--repo-dir", required=True)
    p.add_argument("--ui-changed", action="store_true"); p.add_argument("--run"); p.add_argument("--markdown", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo_dir).expanduser().resolve()
    plan = Path(a.plan).expanduser()
    plan = plan if plan.is_absolute() else repo / plan
    if not plan.is_file():
        return out({"error": f"no plan at {plan}"}, 2)
    res = check(plan.resolve(), repo, a.ui_changed)
    if a.run:
        d = run_dir(a.run)
        try:
            rel_plan = plan.resolve().relative_to(repo).as_posix()
        except ValueError:
            rel_plan = str(plan)
        (d / "report" / "test-plan-parsed.json").write_text(json.dumps({**res, "plan": rel_plan}, indent=2), encoding="utf-8")
        merge_meta(d, {"committed_artifacts": {"test_plan": rel_plan, "test_plan_sha256": res["sha256"]},
                       "plan_check": {"errors": len(res["errors"]), "warnings": len(res["warnings"]), **res["counts"]}})
        log_event(d, {"event": "plan_checked", "plan": rel_plan, "errors": len(res["errors"])})
    if a.markdown:
        print(markdown(res))
        for e in res["errors"]:
            print(f"- ERROR: {e}")
        for w in res["warnings"]:
            print(f"- warning: {w}")
        return 1 if res["errors"] else 0
    return out(res, 1 if res["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
