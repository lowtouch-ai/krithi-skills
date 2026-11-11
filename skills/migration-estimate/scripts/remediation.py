#!/usr/bin/env python3
"""Estimate the effort to FIX what the accessibility report and the security audit found.

Usage:
  remediation.py [--a11y docs/a11y-report/results.json] [--security docs/security-audit/security-audit_<stamp>.sarif]
                 [--out docs/remediation-estimate] [--include-alerts] [--include-unconfirmed] [--no-write]

Inputs (both optional; with neither flag the default locations under the git top-level are used):
  a11y      results.json written by wave-a11y-scan (default docs/a11y-report/results.json)
  security  SARIF written by appsec-static-audit's render_report.py (default: the newest
            docs/security-audit/security-audit_*.sarif). It holds the triaged result, so false positives and
            accepted risks (suppressed results) are already out.

How findings become stories (all numbers come from this script, nothing by hand):
  One story = the findings of ONE rule inside ONE top-level folder, split into more stories when there are more
  findings than the cap below. Plus one verification story per report (re-scan and manual re-test).
    Accessibility: errors and contrast errors only; up to 15 findings per story.
      Alerts need a person to confirm, so they are listed but not estimated unless --include-alerts.
    Security: confirmed findings only; up to 3 per story for Critical and High, 5 for Medium, 8 for Low.
      Unconfirmed leads are listed but not estimated unless --include-unconfirmed. Informational items are never estimated.
Sprints use the same fixed rules as estimate.py: 5 stories = 1 sprint (rounded up per report), 2 engineers,
10 working days per sprint for a human team, 2 with Krithi, go-live allowance about 20%. Sprints run one after another,
so the combined duration is the sum of both reports.

Writes (under --out, default <repo>/docs/remediation-estimate):
  a11y-remediation-estimate.md, security-remediation-estimate.md, remediation-summary.md, remediation.json
Prints the same numbers as JSON. Exit 1 when no input can be read.
"""
import argparse, datetime, glob, json, math, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from estimate import (DAYS_PER_WEEK, ENGINEERS, GO_LIVE_ALLOWANCE, HUMAN_DAYS_PER_SPRINT, KRITHI_DAYS_PER_SPRINT,  # noqa: E402
                      STORIES_PER_SPRINT, num, sprints_for, timelines)

A11Y_CAP = 15
SEC_CAP = {"Critical": 3, "High": 3, "Medium": 5, "Low": 8}
SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
A11Y_CATS = {"error": "Error", "contrast": "Contrast error", "alert": "Alert"}
NOT_IN_ESTIMATE = ["QA sign-off", "Production deployment",
                   "Fixes that need a product, design or content decision (for example rewriting link text, replacing a library with breaking changes)"]
OUT_NAME = "remediation-estimate"


def top(cwd=None):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=cwd, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def component(path):
    p = (path or "").replace("\\", "/").lstrip("./")
    return p.split("/", 1)[0] if "/" in p else "(root)"


def chunks(n, cap):
    return max(1, math.ceil(n / cap))


def load_titles():
    """Rule titles from the sibling wave-a11y-scan catalog when it is installed next to this skill."""
    p = Path(__file__).resolve().parents[2] / "wave-a11y-scan" / "references" / "wave-rule-catalog.json"
    try:
        return {r["name"]: r["title"] for r in json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError):
        return {}


# ------------------------------------------------------------------------------------------ accessibility
def a11y_stories(path, include_alerts):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    titles = load_titles()
    res = d.get("results") or {}
    groups, excluded = defaultdict(list), Counter()
    for cat, label in A11Y_CATS.items():
        for rule, inst in (res.get(cat) or {}).items():
            if cat == "alert" and not include_alerts:
                excluded["alerts (need a person to confirm)"] += len(inst)
                continue
            for i in inst:
                groups[(cat, rule, component(i.get("file")))].append(i)
    stories = []
    for (cat, rule, comp), inst in groups.items():
        n = len(inst)
        parts = chunks(n, A11Y_CAP)
        for k in range(parts):
            lo, hi = k * A11Y_CAP, min(n, (k + 1) * A11Y_CAP)
            files = sorted({i["file"] for i in inst[lo:hi]})
            stories.append({"severity": A11Y_CATS[cat], "rule": rule, "component": comp, "findings": hi - lo, "files": len(files),
                            "title": f"Fix {titles.get(rule, rule)}" + (f" (part {k + 1} of {parts})" if parts > 1 else "")})
    stories.sort(key=lambda s: (list(A11Y_CATS.values()).index(s["severity"]), -s["findings"], s["rule"], s["component"]))
    stories.append({"severity": "Verification", "rule": "-", "component": "(all)", "findings": 0, "files": 0,
                    "title": "Re-run the accessibility scan and run the manual checklist items (keyboard, screen reader, zoom) on the fixed pages"})
    for n, s in enumerate(stories, 1):
        s["id"] = f"A11Y-S{n:02d}"
    counted = sum(len(v) for v in groups.values())
    meta = {"source": str(path), "scanned_at": d.get("scanned_at", ""), "scan_root": d.get("root", ""),
            "files_scanned": d.get("files_scanned", 0), "findings_estimated": counted}
    by_cat = {label: sum(len(v) for v in (res.get(cat) or {}).values()) for cat, label in A11Y_CATS.items() if include_alerts or cat != "alert"}
    return stories, meta, dict(excluded), by_cat


# ------------------------------------------------------------------------------------------ security
def sec_stories(path, include_unconfirmed):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    run = (d.get("runs") or [{}])[0]
    titles = {r["id"]: (r.get("shortDescription") or {}).get("text", r["id"]) for r in (run.get("tool") or {}).get("driver", {}).get("rules", [])}
    groups, excluded, by_sev = defaultdict(list), Counter(), Counter()
    for r in run.get("results") or []:
        p = r.get("properties") or {}
        sev = p.get("severity") or {"error": "High", "warning": "Medium", "note": "Low"}.get(r.get("level"), "Medium")
        if r.get("suppressions"):
            excluded["false positives and accepted risks (suppressed)"] += 1
            continue
        if sev not in SEV_ORDER or sev == "Info":
            excluded["informational items"] += 1
            continue
        if not p.get("confirmed", True) and not include_unconfirmed:
            excluded["unconfirmed leads (could not be proved from source)"] += 1
            continue
        by_sev[sev + ("" if p.get("confirmed", True) else " (unconfirmed)")] += 1
        loc = ((r.get("locations") or [{}])[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri", "")
        groups[(sev, r.get("ruleId", "?"), component(loc))].append(r)
    stories = []
    for (sev, rule, comp), inst in groups.items():
        cap = SEC_CAP[sev]
        n, parts = len(inst), chunks(len(inst), cap)
        for k in range(parts):
            lo, hi = k * cap, min(n, (k + 1) * cap)
            files = {((x.get("locations") or [{}])[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri", "") for x in inst[lo:hi]}
            stories.append({"severity": sev, "rule": rule, "component": comp, "findings": hi - lo, "files": len(files),
                            "title": f"Fix {titles.get(rule, rule)}" + (f" (part {k + 1} of {parts})" if parts > 1 else "")})
    stories.sort(key=lambda s: (SEV_ORDER[s["severity"]], -s["findings"], s["rule"], s["component"]))
    stories.append({"severity": "Verification", "rule": "-", "component": "(all)", "findings": 0, "files": 0,
                    "title": "Re-run the security scan and independently re-check every Critical and High fix"})
    for n, s in enumerate(stories, 1):
        s["id"] = f"SEC-S{n:02d}"
    props = run.get("properties") or {}
    meta = {"source": str(path), "repository": props.get("repository", ""), "commit": props.get("commit", ""),
            "findings_estimated": sum(len(v) for v in groups.values())}
    return stories, meta, dict(excluded), dict(by_sev)


# ------------------------------------------------------------------------------------------ numbers and files
def numbers(stories):
    total = len(stories)
    sprints = sprints_for(total)
    return {"stories": total, "sprints": sprints, "timelines": timelines(sprints)}


def story_table(stories):
    L = ["| ID | Story | Severity | Rule | Folder | Findings | Files |", "|---|---|---|---|---|---:|---:|"]
    for s in stories:
        L.append(f"| {s['id']} | {s['title']} | {s['severity']} | `{s['rule']}` | `{s['component']}` | {s['findings'] or '-'} | {s['files'] or '-'} |")
    return L


def timeline_table(n):
    h, k = n["timelines"]["human"], n["timelines"]["krithi"]
    return ["| | Human team | With Krithi |", "|---|---:|---:|", f"| Engineers | {ENGINEERS} | {ENGINEERS} |",
            f"| Sprints | {n['sprints']} | {n['sprints']} |", f"| Working days | {h['working_days']} | {k['working_days']} |",
            f"| **Duration (fixing and re-testing)** | **{num(h['weeks'])} weeks** | **{num(k['weeks'])} weeks** |",
            f"| Effort | {num(h['engineer_weeks'])} engineer-weeks | {num(k['engineer_weeks'])} engineer-weeks |",
            f"| Go-live allowance, ~{int(GO_LIVE_ALLOWANCE * 100)}% (approximate) | ~{num(h['go_live_allowance_weeks'])} weeks | ~{num(k['go_live_allowance_weeks'])} weeks |"]


METHOD = [
    f"{STORIES_PER_SPRINT} stories make one sprint, rounded up. A sprint is {ENGINEERS} engineers: {HUMAN_DAYS_PER_SPRINT} working days for a human team, {KRITHI_DAYS_PER_SPRINT} with Krithi.",
    "A story is the findings of one rule inside one top-level folder, split when there are more findings than the cap. A verification story is added to every report.",
    "Sprints run one after another. The go-live allowance is an approximation and is not part of the core estimate.",
    "Findings come from a source-code scan. Runtime-only problems and anything the scan skipped are not in this count, so a clean re-scan will not mean zero work."]


def render_one(kind, title, stories, n, meta, excluded, counts, extra):
    today = datetime.date.today().isoformat()
    L = [f"# {title} remediation estimate", "",
         f"Generated {today} by `remediation.py` from `{Path(meta['source']).name}`. Do not edit the numbers by hand; re-run the script after a new report.", "",
         "## Headline", "",
         f"**{n['sprints']} sprint{'s' if n['sprints'] != 1 else ''}** ({n['stories']} stories covering {meta['findings_estimated']} findings), two engineers throughout.", ""]
    L += timeline_table(n) + ["", "## What is in the count", "", "| Finding type | Count |", "|---|---:|"]
    L += [f"| {k} | {v} |" for k, v in counts.items()] or ["| none | 0 |"]
    if excluded:
        L += ["", "Not estimated (listed so the gap is visible):", ""] + [f"- {v} {k}" for k, v in excluded.items()]
    if extra:
        L += [""] + extra
    L += ["", "## Stories", ""] + story_table(stories) + ["", "## How the estimate is calculated", ""] + [f"{i}. {m}" for i, m in enumerate(METHOD, 1)]
    L += ["", "## Not included", ""] + [f"- {x}" for x in NOT_IN_ESTIMATE] + [""]
    return "\n".join(L)


def render_summary(parts, combined):
    today = datetime.date.today().isoformat()
    L = ["# Remediation estimate summary", "", f"Generated {today} by `remediation.py`.", "", "## Headline", ""]
    if len(parts) == 2:
        c = combined
        L += [f"**{c['sprints']} sprint{'s' if c['sprints'] != 1 else ''} in total** ({c['stories']} stories): "
              f"{num(c['timelines']['human']['weeks'])} weeks for a human team, {num(c['timelines']['krithi']['weeks'])} weeks with Krithi, "
              "run one after the other with two engineers.", ""]
    L += ["| Report | Stories | Sprints | Human weeks | Krithi weeks |", "|---|---:|---:|---:|---:|"]
    for name, n, _f in parts:
        L.append(f"| [{name}]({_f}) | {n['stories']} | {n['sprints']} | {num(n['timelines']['human']['weeks'])} | {num(n['timelines']['krithi']['weeks'])} |")
    if len(parts) == 2:
        c = combined
        L.append(f"| **Total** | **{c['stories']}** | **{c['sprints']}** | **{num(c['timelines']['human']['weeks'])}** | **{num(c['timelines']['krithi']['weeks'])}** |")
        L += ["", timeline_table(c)[0]] + timeline_table(c)[1:]
    L += ["", "The two workstreams are counted one after the other. If separate teams fix accessibility and security in parallel, "
          "the calendar time is the longer of the two, and the effort stays the same.", "", "## How the estimate is calculated", ""]
    L += [f"{i}. {m}" for i, m in enumerate(METHOD, 1)]
    L += ["", "## Not included", ""] + [f"- {x}" for x in NOT_IN_ESTIMATE] + [""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a11y", help="results.json from wave-a11y-scan (default docs/a11y-report/results.json)")
    ap.add_argument("--security", help="security-audit_*.sarif from appsec-static-audit (default: newest in docs/security-audit)")
    ap.add_argument("--out", help=f"output folder (default <repo>/docs/{OUT_NAME})")
    ap.add_argument("--include-alerts", action="store_true", help="also estimate accessibility alerts (one story group per rule)")
    ap.add_argument("--include-unconfirmed", action="store_true", help="also estimate unconfirmed security leads")
    ap.add_argument("--no-write", action="store_true", help="print the numbers only")
    a = ap.parse_args()
    root = top()
    a11y_path = Path(a.a11y) if a.a11y else root / "docs" / "a11y-report" / "results.json"
    if a.security:
        sec_path = Path(a.security)
    else:
        found = sorted(glob.glob(str(root / "docs" / "security-audit" / "security-audit_*.sarif")))
        sec_path = Path(found[-1]) if found else None
    errors, parts, out = [], [], {}
    out_dir = Path(a.out) if a.out else root / "docs" / OUT_NAME
    files = {}
    if a11y_path.is_file():
        try:
            st, meta, ex, counts = a11y_stories(a11y_path, a.include_alerts)
            n = numbers(st)
            out["a11y"] = {"stories": st, "numbers": n, "meta": meta, "not_estimated": ex}
            files["a11y-remediation-estimate.md"] = render_one("a11y", "Accessibility", st, n, meta, ex, counts,
                                                              [f"Scanned {meta['files_scanned']} source files on {meta['scanned_at'][:10] or 'an unknown date'}."])
            parts.append(("Accessibility", n, "a11y-remediation-estimate.md"))
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append(f"cannot read the accessibility report {a11y_path}: {e}")
    elif a.a11y:
        errors.append(f"accessibility report not found: {a11y_path}")
    if sec_path and sec_path.is_file():
        try:
            st, meta, ex, counts = sec_stories(sec_path, a.include_unconfirmed)
            n = numbers(st)
            out["security"] = {"stories": st, "numbers": n, "meta": meta, "not_estimated": ex}
            files["security-remediation-estimate.md"] = render_one("security", "Security", st, n, meta, ex, counts,
                                                                  [f"Audit of `{meta['repository'] or 'the repository'}`" + (f" at commit `{meta['commit'][:10]}`." if meta["commit"] else ".")])
            parts.append(("Security", n, "security-remediation-estimate.md"))
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append(f"cannot read the security audit {sec_path}: {e}")
    elif a.security:
        errors.append(f"security audit not found: {sec_path}")
    if not parts:
        errors.append("nothing to estimate: run wave-a11y-scan (docs/a11y-report/results.json) and/or appsec-static-audit "
                      "(docs/security-audit/security-audit_*.sarif; run render_report.py with --emit-sarif to get it) first, or pass --a11y / --security")
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    combined = None
    if len(parts) == 2:
        total_stories = sum(p[1]["stories"] for p in parts)
        total_sprints = sum(p[1]["sprints"] for p in parts)
        combined = {"stories": total_stories, "sprints": total_sprints, "timelines": timelines(total_sprints)}
        out["combined"] = combined
    files["remediation-summary.md"] = render_summary(parts, combined)
    out["ok"] = not errors
    out["errors"] = errors
    out["rules"] = {"a11y_findings_per_story": A11Y_CAP, "security_findings_per_story": SEC_CAP, "stories_per_sprint": STORIES_PER_SPRINT,
                    "human_days_per_sprint": HUMAN_DAYS_PER_SPRINT, "krithi_days_per_sprint": KRITHI_DAYS_PER_SPRINT}
    if not a.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (out_dir / name).write_text(text, encoding="utf-8")
        (out_dir / "remediation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        out["written"] = str(out_dir)
    brief = {k: v for k, v in out.items() if k not in ("a11y", "security")}
    for k in ("a11y", "security"):
        if k in out:
            brief[k] = {"stories": out[k]["numbers"]["stories"], "sprints": out[k]["numbers"]["sprints"], "findings_estimated": out[k]["meta"]["findings_estimated"],
                        "not_estimated": out[k]["not_estimated"]}
    print(json.dumps(brief, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
