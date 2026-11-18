#!/usr/bin/env python3
"""Keep a PR review's versions, reviewer feedback and approval, outside the reviewed repository.

Layout (base: $KRITHI_HOME or ~/.krithi):
  reviews/<owner>__<repo>/PR-<n>/
      evidence.json            pr_evidence.py output
      report-v<k>.md           each version of the review report
      scorecard-v<k>.json      the ratings that produced it
      history.jsonl            one event per line: version saved, feedback, approval, publication
      comment.md               the GitHub comment (written by post_comment.py)
  review-pr/learning-log.jsonl every feedback event from every review, for improving the skill

Usage:
  review_log.py init     --gh-repo owner/name --pr N
  review_log.py save     --dir D --report report.md --scorecard ratings.json [--head-sha SHA] [--changes "what changed and why"]
  review_log.py feedback --dir D --kind KIND --text "..." [--finding F2] [--factor testing] [--area "..."]
  review_log.py approve  --dir D [--auto --reason "why the gate passed"]   # --auto: approved by the skill's quality gate, no reviewer
  review_log.py history  --dir D            # Markdown "Reviewer feedback history" for the report
  review_log.py status   --dir D            # JSON: latest version, approved?, published?

KIND: incorrect-finding | missing-context | rating-dispute | re-review | missing-finding | other

Exit codes: 0 ok, 2 usage error.
"""
import argparse, json, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
import os

KINDS = ("incorrect-finding", "missing-context", "rating-dispute", "re-review", "missing-finding", "other")


def base():
    return Path(os.environ.get("KRITHI_HOME") or Path.home() / ".krithi")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def events(d):
    p = d / "history.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def append(d, ev):
    ev = {"at": now(), **ev}
    with (d / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    return ev


def latest_version(d):
    vs = [int(m.group(1)) for p in d.glob("report-v*.md") if (m := re.match(r"report-v(\d+)\.md$", p.name))]
    return max(vs) if vs else 0


def review_dir(a):
    d = Path(a.dir).expanduser()
    if not (d / "history.jsonl").exists() and not d.is_dir():
        sys.exit(json.dumps({"error": f"no review folder at {d}; run init first"}))
    return d


def cmd_init(a):
    if not re.match(r"^[\w.-]+/[\w.-]+$", a.gh_repo or ""):
        sys.exit(json.dumps({"error": "--gh-repo must be owner/name"}))
    d = base() / "reviews" / a.gh_repo.replace("/", "__") / f"PR-{int(a.pr)}"
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "history.jsonl").exists():
        append(d, {"event": "init", "gh_repo": a.gh_repo, "pr": int(a.pr)})
    versions = [e for e in events(d) if e["event"] == "version"]
    return {"dir": str(d), "latest_version": latest_version(d), "previous_events": len(events(d)) - 1,
            "last_reviewed_head": versions[-1].get("head_sha") if versions else None}


def cmd_save(a):
    d = review_dir(a)
    v = latest_version(d) + 1
    if v > 1 and not (a.changes or "").strip():
        sys.exit(json.dumps({"error": "a revised version needs --changes explaining what changed and why"}))
    shutil.copyfile(a.report, d / f"report-v{v}.md")
    if a.scorecard:
        shutil.copyfile(a.scorecard, d / f"scorecard-v{v}.json")
    append(d, {"event": "version", "version": v, "changes": a.changes or "initial review", "head_sha": a.head_sha})
    return {"dir": str(d), "version": v, "report": str(d / f"report-v{v}.md")}


def cmd_feedback(a):
    d = review_dir(a)
    v = latest_version(d)
    ev = append(d, {"event": "feedback", "version": v, "kind": a.kind, "text": a.text,
                    "finding": a.finding, "factor": a.factor, "area": a.area})
    meta = next((e for e in events(d) if e["event"] == "init"), {})
    learn = base() / "review-pr" / "learning-log.jsonl"
    learn.parent.mkdir(parents=True, exist_ok=True)
    with learn.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**ev, "gh_repo": meta.get("gh_repo"), "pr": meta.get("pr"), "review_dir": str(d)}) + "\n")
    return {"recorded": ev, "learning_log": str(learn)}


def cmd_approve(a):
    d = review_dir(a)
    v = latest_version(d)
    if not v:
        sys.exit(json.dumps({"error": "nothing to approve: no report saved"}))
    if a.auto and not (a.reason or "").strip():
        sys.exit(json.dumps({"error": "--auto approval needs --reason (which gate checks passed)"}))
    return {"recorded": append(d, {"event": "approved", "version": v, "by": "auto" if a.auto else "reviewer",
                                   "reason": a.reason})}


def cmd_history(a):
    d = review_dir(a)
    rows = ["| When (UTC) | Version | Event | Detail |", "|---|---:|---|---|"]
    for e in events(d):
        if e["event"] == "init":
            continue
        if e["event"] == "version":
            detail = e.get("changes", "")
        elif e["event"] == "feedback":
            ref = ", ".join(x for x in (e.get("finding") and f"finding {e['finding']}", e.get("factor") and f"factor {e['factor']}", e.get("area")) if x)
            detail = f"**{e['kind']}**" + (f" ({ref})" if ref else "") + f": {e.get('text', '')}"
        elif e["event"] == "approved":
            detail = f"by {e.get('by', 'reviewer')}" + (f": {e['reason']}" if e.get("reason") else "")
        elif e["event"] == "published":
            detail = f"{e.get('status')}: {e.get('url') or e.get('error', '')}"
        else:
            detail = ""
        rows.append(f"| {e['at'].replace('T', ' ').rstrip('Z')} | {e.get('version', '')} | {e['event']} | {' '.join(str(detail).split()).replace('|', chr(92) + '|')} |")
    return "\n".join(rows) if len(rows) > 2 else "No reviewer feedback yet."


def cmd_status(a):
    d = review_dir(a)
    evs = events(d)
    v = latest_version(d)
    appr = [e for e in evs if e["event"] == "approved" and e.get("version") == v]
    approved = bool(appr)
    pubs = [e for e in evs if e["event"] == "published"]
    return {"dir": str(d), "latest_version": v, "approved": approved,
            "approved_by": appr[-1].get("by", "reviewer") if appr else None,
            "feedback_count": sum(1 for e in evs if e["event"] == "feedback"),
            "published": pubs[-1] if pubs else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--gh-repo", required=True); p.add_argument("--pr", required=True, type=int)
    p = sub.add_parser("save"); p.add_argument("--dir", required=True); p.add_argument("--report", required=True)
    p.add_argument("--scorecard"); p.add_argument("--changes"); p.add_argument("--head-sha")
    p = sub.add_parser("feedback"); p.add_argument("--dir", required=True); p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--text", required=True); p.add_argument("--finding"); p.add_argument("--factor"); p.add_argument("--area")
    p = sub.add_parser("approve"); p.add_argument("--dir", required=True)
    p.add_argument("--auto", action="store_true"); p.add_argument("--reason")
    for name in ("history", "status"):
        sub.add_parser(name).add_argument("--dir", required=True)
    a = ap.parse_args()
    res = {"init": cmd_init, "save": cmd_save, "feedback": cmd_feedback, "approve": cmd_approve,
           "history": cmd_history, "status": cmd_status}[a.cmd](a)
    print(res if isinstance(res, str) else json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
