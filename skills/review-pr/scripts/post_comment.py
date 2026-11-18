#!/usr/bin/env python3
"""Prepare and post the approved review as a GitHub PR comment, posting exactly the text that was approved
(by the reviewer, or by the automatic quality gate in SKILL.md step 8).

  prepare: copy the comment into the review folder as comment.md and print its SHA-256 and size.
           Show the reviewer that file's exact content; the hash identifies what they approved.
  post:    post comment.md to the PR only if its SHA-256 still equals --sha256 (the approved text), the
           review's latest report is approved, and the PR is the one reviewed. Records the URL and status.

Usage:
  post_comment.py prepare --dir D --body draft.md
  post_comment.py post    --dir D --gh-repo owner/name --pr N --sha256 HASH [--reviewed-sha SHA] [--allow-new-commits]

Exit codes: 0 posted/prepared, 1 posting failed, 2 refused (hash mismatch, not approved, wrong PR, new commits).
"""
import argparse, hashlib, json, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

GITHUB_LIMIT = 65536


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def log(d, ev):
    ev = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **ev}
    with (Path(d) / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


def events(d):
    p = Path(d) / "history.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []


def out(obj, code):
    print(json.dumps(obj, indent=2))
    return code


def prepare(a):
    d = Path(a.dir).expanduser()
    text = Path(a.body).read_text(encoding="utf-8")
    if len(text) > GITHUB_LIMIT:
        return out({"error": f"comment is {len(text)} characters; GitHub allows {GITHUB_LIMIT}. Shorten it (link the full report instead)."}, 2)
    if re.search(r"\b(ghp|gho|ghs)_[A-Za-z0-9]{36,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{32,}", text):
        return out({"error": "the comment appears to contain a secret; remove it before preparing"}, 2)
    dest = d / "comment.md"
    if Path(a.body).resolve() != dest.resolve():
        shutil.copyfile(a.body, dest)
    h = sha(dest)
    log(d, {"event": "comment_prepared", "sha256": h, "chars": len(text)})
    return out({"comment": str(dest), "sha256": h, "chars": len(text)}, 0)


def post(a):
    d = Path(a.dir).expanduser()
    body = d / "comment.md"
    if not body.is_file():
        return out({"refused": "no comment.md; run prepare first"}, 2)
    if sha(body) != a.sha256:
        return out({"refused": "comment.md changed since it was approved (SHA-256 mismatch); show it again and get approval"}, 2)
    evs = events(d)
    versions = [e["version"] for e in evs if e["event"] == "version"]
    if not versions or not any(e["event"] == "approved" and e.get("version") == max(versions) for e in evs):
        return out({"refused": "the latest review version is not approved (by the reviewer or the automatic gate)"}, 2)
    init = next((e for e in evs if e["event"] == "init"), {})
    if init and (init.get("gh_repo") != a.gh_repo or init.get("pr") != a.pr):
        return out({"refused": f"this review is for {init.get('gh_repo')}#{init.get('pr')}, not {a.gh_repo}#{a.pr}"}, 2)
    if any(e["event"] == "published" and e.get("status") == "posted" and e.get("sha256") == a.sha256 for e in evs):
        return out({"refused": "this exact comment was already posted", "url": next(e.get("url") for e in reversed(evs) if e["event"] == "published" and e.get("status") == "posted")}, 2)

    gh = a.gh or shutil.which("gh")
    if not gh:
        return out({"refused": "gh CLI not installed; post manually or install gh and run `gh auth login`"}, 2)
    r = subprocess.run([gh, "pr", "view", str(a.pr), "--repo", a.gh_repo, "--json", "number,url,headRefOid,state"], capture_output=True, text=True)
    if r.returncode != 0:
        return out({"refused": f"cannot read {a.gh_repo}#{a.pr}: {r.stderr.strip()[-300:]}"}, 2)
    pr = json.loads(r.stdout)
    if a.reviewed_sha and not pr.get("headRefOid", "").startswith(a.reviewed_sha) and not a.allow_new_commits:
        return out({"refused": "the PR has new commits since the review", "reviewed": a.reviewed_sha,
                    "current": pr.get("headRefOid"), "hint": "re-review, or pass --allow-new-commits if the reviewer agrees"}, 2)

    r = subprocess.run([gh, "pr", "comment", str(a.pr), "--repo", a.gh_repo, "--body-file", str(body)], capture_output=True, text=True)
    url = next((m.group(0) for m in re.finditer(r"https://\S+#issuecomment-\d+", r.stdout + r.stderr)), None)
    if r.returncode != 0:
        log(d, {"event": "published", "status": "failed", "sha256": a.sha256, "error": r.stderr.strip()[-300:]})
        return out({"status": "failed", "error": r.stderr.strip()[-300:]}, 1)
    log(d, {"event": "published", "status": "posted", "sha256": a.sha256, "url": url, "pr_url": pr.get("url"),
            "head_sha": pr.get("headRefOid")})
    return out({"status": "posted", "url": url, "pr_url": pr.get("url")}, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--dir", required=True); p.add_argument("--body", required=True)
    p = sub.add_parser("post"); p.add_argument("--dir", required=True); p.add_argument("--gh-repo", required=True)
    p.add_argument("--pr", required=True, type=int); p.add_argument("--sha256", required=True)
    p.add_argument("--reviewed-sha"); p.add_argument("--allow-new-commits", action="store_true")
    p.add_argument("--gh", help=argparse.SUPPRESS)  # test hook: path to a fake gh
    a = ap.parse_args()
    return prepare(a) if a.cmd == "prepare" else post(a)


if __name__ == "__main__":
    sys.exit(main())
