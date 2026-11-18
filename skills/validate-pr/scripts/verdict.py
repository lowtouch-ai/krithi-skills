#!/usr/bin/env python3
"""Compute a validation run's final status from its recorded evidence, so the status is never a matter of wording.

  Passed                     required automated tests completed successfully, no unresolved blocking defects
  Failed                     confirmed application defects prevent acceptance
  Blocked                    validation could not be completed (environment, dependencies, credentials, app not reachable)
  Needs Manual Verification  automated testing completed, but important scenarios still need a person

Inputs, all from the run folder: metadata.json (app readiness, blocker, execution errors), results/summary.json
(outcome per test case), report/test-plan-parsed.json (Required / Automated / Manual cases, from test_plan.py check --run),
defects/defects.json (classification, confidence, severity, status).

Usage:
  verdict.py --run D [--markdown] [--dry-run]

Without --dry-run it writes report/verdict.json and sets metadata.json validation_status and finished_at.
Exit codes: 0 Passed, 10 Failed, 11 Blocked, 12 Needs Manual Verification, 2 usage error.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_meta, log_event, merge_meta, now, out, run_dir  # noqa: E402

EXIT = {"Passed": 0, "Failed": 10, "Blocked": 11, "Needs Manual Verification": 12}
BLOCKING_SEVERITIES = ("Critical", "High")


def read_json(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


def gather(d):
    """Collect the facts decide_status() needs. Pure reading; no judgement here."""
    meta = load_meta(d)
    summary = read_json(d / "results" / "summary.json", None)
    plan = read_json(d / "report" / "test-plan-parsed.json", {"cases": [], "errors": ["plan not checked (test_plan.py check --run)"]})
    defects = [x for x in read_json(d / "defects" / "defects.json", []) if x["status"] == "open"]
    outcomes = (summary or {}).get("test_cases", {})
    cases = plan.get("cases", [])
    req_auto = [c["id"] for c in cases if c["priority"] == "required" and c["execution"] == "automated"]
    by_tc = {}
    for x in defects:
        by_tc.setdefault(x["test_case"], []).append(x)
    return {
        "app_ready": bool(meta.get("app", {}).get("ready")),
        "app_blocker": (meta.get("app", {}).get("blocker") or {}).get("reason"),
        "setup_failures": [s["name"] for s in meta.get("app", {}).get("setup_steps", []) if not s.get("ok")],
        "tests_executed": bool(summary and summary.get("tests")),
        "execution_error": (meta.get("tests", {}).get("execution_error") or {}).get("reason"),
        "plan_errors": plan.get("errors", []),
        "required_automated": req_auto,
        "required_manual": [c["id"] for c in cases if c["priority"] == "required" and c["execution"] == "manual"],
        "outcomes": outcomes,                                            # TC -> passed | failed | blocked | flaky | skipped
        "required_without_result": [tc for tc in req_auto if tc not in outcomes],
        "required_not_passed": {tc: outcomes[tc] for tc in req_auto if tc in outcomes and outcomes[tc] != "passed"},
        "blocking_defects": [x["id"] for x in defects if x["classification"] == "application" and x["confidence"] == "confirmed"
                             and x.get("severity") in BLOCKING_SEVERITIES and not x.get("pre_existing")],
        "pre_existing_defects": [x["id"] for x in defects if x.get("pre_existing")],
        "confirmed_app_defects": [{"id": x["id"], "severity": x.get("severity"), "test_case": x["test_case"]} for x in defects
                                  if x["classification"] == "application" and x["confidence"] == "confirmed"],
        "unconfirmed_app_defects": [x["id"] for x in defects if x["classification"] == "application" and x["confidence"] != "confirmed"],
        "defects_by_test_case": {tc: [{"id": x["id"], "classification": x["classification"], "confidence": x["confidence"],
                                       "severity": x.get("severity"), "pre_existing": bool(x.get("pre_existing"))} for x in xs]
                                 for tc, xs in by_tc.items()},
    }


def decide_status(f):
    """Return (status, reasons) where status is one of EXIT's keys and reasons is a list of short sentences
    that the report quotes verbatim (each should name the TC / defect IDs it is based on).

    `f` is the dict from gather(). Order matters: decide which condition wins when several hold
    (e.g. a confirmed High defect AND an unreachable-in-part environment AND a Required manual case).

    Policy (precedence: Failed > Blocked > Needs Manual Verification > Passed):
      - A confirmed Critical/High application defect fails the PR even when the run is otherwise incomplete
        (e.g. a build failure recorded as Critical), because more testing cannot make it acceptable.
      - A Required test that failed with a confirmed application defect of ANY severity also fails it: Required
        cases are the acceptance gate, so "required tests completed successfully" is not true.
      - App not ready, tests not executed, or a Required case with no result / blocked / skipped, or one that
        failed with an open environment issue recorded against it -> Blocked.
      - A Required case that failed for any other reason (test-automation problem, unconfirmed defect, flaky),
        a Required Manual case, or a plan that fails traceability -> Needs Manual Verification: automation ran
        but a person must confirm what it could not.
      - Medium/Low defects on Optional cases do not block; they are listed in the reasons.
      - Pre-existing defects (not introduced by the PR) never fail it. A Required case that fails only on
        pre-existing defects -> Needs Manual Verification, so the reviewer decides whether to accept it.
    """
    reasons = []
    by_tc = f["defects_by_test_case"]
    confirmed_app_on = lambda tc: [x["id"] for x in by_tc.get(tc, []) if x["classification"] == "application"
                                   and x["confidence"] == "confirmed" and not x.get("pre_existing")]
    pre_on = lambda tc: [x["id"] for x in by_tc.get(tc, []) if x.get("pre_existing")]
    failing_required = {tc: confirmed_app_on(tc) for tc, o in f["required_not_passed"].items() if o == "failed" and confirmed_app_on(tc)}
    if f["blocking_defects"] or failing_required:
        if f["blocking_defects"]:
            reasons.append(f"Confirmed blocking (Critical/High) application defects: {', '.join(f['blocking_defects'])}.")
        for tc, ids in sorted(failing_required.items()):
            reasons.append(f"Required case {tc} failed with confirmed application defect(s) {', '.join(ids)}.")
        return "Failed", reasons
    if not f["app_ready"]:
        return "Blocked", [f"The application could not be launched: {f['app_blocker'] or 'no successful start recorded'}."] + \
            ([f"Setup steps failed: {', '.join(f['setup_failures'])}."] if f["setup_failures"] else [])
    if not f["tests_executed"]:
        return "Blocked", [f"The tests did not execute: {f['execution_error'] or 'no results recorded'}."]
    env_on = lambda tc: [x["id"] for x in by_tc.get(tc, []) if x["classification"] == "environment"]
    stuck = f["required_without_result"] + [tc for tc, o in f["required_not_passed"].items()
                                            if o in ("blocked", "skipped") or env_on(tc)]
    if stuck:
        return "Blocked", [f"Required cases without a usable result (not run, blocked or skipped): {', '.join(sorted(stuck))}."]
    other = sorted(tc for tc, o in f["required_not_passed"].items() if o not in ("blocked", "skipped") and not env_on(tc))
    for tc in [t for t in other if pre_on(t)]:
        reasons.append(f"Required case {tc} fails only on pre-existing defects {', '.join(pre_on(tc))} that this PR did not introduce; "
                       f"the reviewer decides whether to accept them.")
    rest = [t for t in other if not pre_on(t)]
    if rest:
        reasons.append(f"Required cases that did not pass for reasons other than a confirmed application defect "
                       f"(test-automation, unconfirmed defect or flaky); verify manually: {', '.join(rest)}.")
    if f["required_manual"]:
        reasons.append(f"Required manual cases still to verify: {', '.join(f['required_manual'])}.")
    if f["plan_errors"]:
        reasons.append(f"The test plan fails the traceability check ({len(f['plan_errors'])} errors): {f['plan_errors'][0]}")
    if reasons:
        return "Needs Manual Verification", reasons
    reasons.append(f"All {len(f['required_automated'])} Required automated cases passed; no unresolved blocking defects.")
    minor = [x["id"] for x in f["confirmed_app_defects"] if x["id"] not in f["blocking_defects"] and x["id"] not in f["pre_existing_defects"]]
    if f["pre_existing_defects"]:
        reasons.append(f"Pre-existing defects reported (not introduced by this PR): {', '.join(f['pre_existing_defects'])}.")
    if minor:
        reasons.append(f"Non-blocking defects remain open: {', '.join(minor)}.")
    if f["unconfirmed_app_defects"]:
        reasons.append(f"Unconfirmed defects to look at: {', '.join(f['unconfirmed_app_defects'])}.")
    return "Passed", reasons


def markdown(status, reasons, f):
    o = f["outcomes"]
    counts = {k: sum(1 for v in o.values() if v == k) for k in ("passed", "failed", "blocked", "flaky", "skipped")}
    lines = [f"## Overall validation status: **{status}**", "", *[f"- {r}" for r in reasons], "",
             "| Test cases | Passed | Failed | Blocked | Skipped | Flaky | Required automated | Required manual |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|",
             f"| {len(o)} | {counts['passed']} | {counts['failed']} | {counts['blocked']} | {counts['skipped']} | {counts['flaky']} | "
             f"{len(f['required_automated'])} | {len(f['required_manual'])} |"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True); ap.add_argument("--markdown", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = run_dir(a.run)
    f = gather(d)
    status, reasons = decide_status(f)
    if status not in EXIT:
        return out({"error": f"decide_status returned an unknown status {status!r}"}, 2)
    if not a.dry_run:
        (d / "report" / "verdict.json").write_text(json.dumps({"status": status, "reasons": reasons, "facts": f, "at": now()}, indent=2), encoding="utf-8")
        merge_meta(d, {"validation_status": status, "status_reasons": reasons, "finished_at": now()})
        log_event(d, {"event": "verdict", "status": status})
    if a.markdown:
        print(markdown(status, reasons, f))
    else:
        out({"status": status, "reasons": reasons, "facts": f})
    return EXIT[status]


if __name__ == "__main__":
    sys.exit(main())
