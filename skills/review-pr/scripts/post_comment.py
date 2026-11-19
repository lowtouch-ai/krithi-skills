#!/usr/bin/env python3
"""Prepare and post the approved review on a GitHub PR, posting exactly the text that was approved
(by the automatic quality gate in SKILL.md step 8, or by a reviewer who chose to).

  prepare: copy the summary into the review folder as comment.md and, with --inline, the line comments as
           inline.json ([{"path", "line", "start_line"?, "body"}]). Prints one SHA-256 over both; that hash
           identifies the approved text.
  post:    publish only if the hash still matches, the latest report version is approved, and the PR is the one
           reviewed at --reviewed-sha. With inline.json, posts ONE GitHub review (event COMMENT, never APPROVE or
           REQUEST_CHANGES): each line comment on its line in "Files changed", comment.md as the review summary.
           Line comments whose line is not in the PR's diff (GitHub rejects those) are moved into the summary.
           If GitHub refuses the review, falls back to one plain PR comment with everything in it.
           Without inline.json, posts comment.md as one plain PR comment. Records the URL and status.

Usage:
  post_comment.py prepare --dir D --body draft.md [--inline inline.json]
  post_comment.py post    --dir D --gh-repo owner/name --pr N --sha256 HASH [--reviewed-sha SHA] [--allow-new-commits]

Exit codes: 0 posted/prepared, 1 posting failed, 2 refused (hash mismatch, not approved, wrong PR, new commits, bad input).
"""
import argparse, hashlib, json, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

GITHUB_LIMIT = 65536


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def review_hash(d):
    """SHA-256 of comment.md alone, or of comment.md plus inline.json when line comments were prepared."""
    d = Path(d)
    inline = d / "inline.json"
    if not inline.is_file():
        return sha(d / "comment.md")
    return hashlib.sha256((d / "comment.md").read_bytes() + b"\0" + inline.read_bytes()).hexdigest()


def load_inline(path):
    """Validate line comments; returns (list, error)."""
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"cannot read inline comments: {e}"
    if not isinstance(items, list):
        return None, "inline comments must be a JSON list"
    clean = []
    for i, c in enumerate(items):
        if not (isinstance(c, dict) and isinstance(c.get("path"), str) and c["path"] and isinstance(c.get("line"), int)
                and c["line"] > 0 and isinstance(c.get("body"), str) and c["body"].strip()):
            return None, f"inline comment {i} needs path (str), line (positive int) and body (non-empty str)"
        path = c["path"]
        while path.startswith("./"):
            path = path[2:]
        item = {"path": path, "line": c["line"], "body": c["body"]}
        if isinstance(c.get("start_line"), int) and 0 < c["start_line"] < c["line"]:
            item["start_line"] = c["start_line"]
        clean.append(item)
    return clean, None


def diff_lines(patch):
    """Right-side (new file) line numbers that appear in a unified-diff patch: added and context lines."""
    lines, new = set(), None
    for row in (patch or "").splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
        if m:
            new = int(m.group(1)); continue
        if new is None or row.startswith("\\"):
            continue
        if row.startswith("-"):
            continue
        lines.add(new); new += 1
    return lines


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
    inline = None
    if a.inline:
        inline, err = load_inline(a.inline)
        if err:
            return out({"error": err}, 2)
    everything = text + "\n".join(c["body"] for c in inline or [])
    if re.search(r"\b(ghp|gho|ghs)_[A-Za-z0-9]{36,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{32,}", everything):
        return out({"error": "the comment appears to contain a secret; remove it before preparing"}, 2)
    dest = d / "comment.md"
    if Path(a.body).resolve() != dest.resolve():
        shutil.copyfile(a.body, dest)
    inline_path = d / "inline.json"
    if inline is not None:
        inline_path.write_text(json.dumps(inline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif inline_path.exists():
        inline_path.unlink()  # a previous version's line comments must not leak into this one
    h = review_hash(d)
    log(d, {"event": "comment_prepared", "sha256": h, "chars": len(text), "inline_comments": len(inline or [])})
    return out({"comment": str(dest), "inline": str(inline_path) if inline is not None else None,
                "inline_comments": len(inline or []), "sha256": h, "chars": len(text)}, 0)


def post(a):
    d = Path(a.dir).expanduser()
    body = d / "comment.md"
    if not body.is_file():
        return out({"refused": "no comment.md; run prepare first"}, 2)
    if review_hash(d) != a.sha256:
        return out({"refused": "comment.md or inline.json changed since it was approved (SHA-256 mismatch); re-run the quality gate, approve again, prepare again and post with the new hash. Do not ask the reviewer"}, 2)
    evs = events(d)
    versions = [e["version"] for e in evs if e["event"] == "version"]
    if not versions or not any(e["event"] == "approved" and e.get("version") == max(versions) for e in evs):
        return out({"refused": "the latest review version is not approved; run the quality gate (SKILL.md step 8) and `review_log.py approve --auto`, or leave the comment unposted. Do not ask the reviewer"}, 2)
    init = next((e for e in evs if e["event"] == "init"), {})
    if init and (init.get("gh_repo") != a.gh_repo or init.get("pr") != a.pr):
        return out({"refused": f"this review is for {init.get('gh_repo')}#{init.get('pr')}, not {a.gh_repo}#{a.pr}"}, 2)
    if any(e["event"] == "published" and str(e.get("status", "")).startswith("posted") and e.get("sha256") == a.sha256 for e in evs):
        return out({"refused": "this exact comment was already posted", "url": next(e.get("url") for e in reversed(evs) if e["event"] == "published" and str(e.get("status", "")).startswith("posted"))}, 2)

    gh = a.gh or shutil.which("gh")
    if not gh:
        return out({"refused": "gh CLI not installed; post manually or install gh and run `gh auth login`"}, 2)
    r = subprocess.run([gh, "pr", "view", str(a.pr), "--repo", a.gh_repo, "--json", "number,url,headRefOid,state"], capture_output=True, text=True)
    if r.returncode != 0:
        return out({"refused": f"cannot read {a.gh_repo}#{a.pr}: {r.stderr.strip()[-300:]}"}, 2)
    pr = json.loads(r.stdout)
    if a.reviewed_sha and not pr.get("headRefOid", "").startswith(a.reviewed_sha) and not a.allow_new_commits:
        return out({"refused": "the PR has new commits since the review", "reviewed": a.reviewed_sha,
                    "current": pr.get("headRefOid"), "hint": "re-run the review once on the new head (SKILL.md step 9), then post; do not ask the reviewer"}, 2)

    inline_path = d / "inline.json"
    if inline_path.is_file():
        return post_review(a, d, gh, pr, body, json.loads(inline_path.read_text(encoding="utf-8")))
    return post_plain(a, d, gh, pr, body)


def post_plain(a, d, gh, pr, body, status="posted", extra=None):
    r = subprocess.run([gh, "pr", "comment", str(a.pr), "--repo", a.gh_repo, "--body-file", str(body)], capture_output=True, text=True)
    url = next((m.group(0) for m in re.finditer(r"https://\S+#issuecomment-\d+", r.stdout + r.stderr)), None)
    if r.returncode != 0:
        log(d, {"event": "published", "status": "failed", "sha256": a.sha256, "error": r.stderr.strip()[-300:], **(extra or {})})
        return out({"status": "failed", "error": r.stderr.strip()[-300:], **(extra or {})}, 1)
    log(d, {"event": "published", "status": status, "kind": "comment", "sha256": a.sha256, "url": url, "pr_url": pr.get("url"),
            "head_sha": pr.get("headRefOid"), **(extra or {})})
    return out({"status": status, "kind": "comment", "url": url, "pr_url": pr.get("url"), **(extra or {})}, 0)


def outside_section(items):
    rows = [f"- `{c['path']}:{c['line']}`: " + c["body"].strip().replace("\n", "\n  ") for c in items]
    return "\n\n### Comments on lines outside this PR's diff\n" + "\n".join(rows) + "\n"


def post_review(a, d, gh, pr, body, inline):
    head = pr.get("headRefOid") or a.reviewed_sha
    if not head:
        return out({"refused": "line comments need the reviewed head commit; pass --reviewed-sha"}, 2)
    r = subprocess.run([gh, "api", f"repos/{a.gh_repo}/pulls/{a.pr}/files", "--paginate", "--jq", ".[] | {filename, patch}"],
                       capture_output=True, text=True)
    in_diff = {}
    if r.returncode == 0:
        for row in r.stdout.splitlines():
            if row.strip():
                f = json.loads(row)
                in_diff[f["filename"]] = diff_lines(f.get("patch"))
    on_line, outside = [], []
    for c in inline:
        ok = c["line"] in in_diff.get(c["path"], set())
        (on_line if ok else outside).append(c)
    summary = body.read_text(encoding="utf-8") + (outside_section(outside) if outside else "")
    comments = []
    for c in on_line:
        item = {"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["body"]}
        if c.get("start_line") and c["start_line"] in in_diff[c["path"]]:
            item.update(start_line=c["start_line"], start_side="RIGHT")
        comments.append(item)
    payload = {"commit_id": head, "event": "COMMENT", "body": summary, "comments": comments}
    payload_path = d / "review-payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {"inline_posted": len(comments), "moved_to_summary": len(outside)}

    r = subprocess.run([gh, "api", "-X", "POST", f"repos/{a.gh_repo}/pulls/{a.pr}/reviews", "--input", str(payload_path)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        try:
            resp = json.loads(r.stdout)
        except ValueError:
            resp = {}
        url = resp.get("html_url")
        log(d, {"event": "published", "status": "posted", "kind": "review", "sha256": a.sha256, "url": url,
                "review_id": resp.get("id"), "pr_url": pr.get("url"), "head_sha": head, **counts})
        return out({"status": "posted", "kind": "review", "url": url, "pr_url": pr.get("url"), **counts}, 0)

    # GitHub refused the review (for example a line it cannot resolve): nothing was posted, so post one plain comment instead.
    error = (r.stderr or r.stdout).strip()[-300:]
    fallback = d / "comment-fallback.md"
    fallback.write_text(body.read_text(encoding="utf-8") + outside_section(inline), encoding="utf-8")
    return post_plain(a, d, gh, pr, fallback, status="posted-fallback",
                      extra={"review_error": error, "inline_posted": 0, "moved_to_summary": len(inline)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--dir", required=True); p.add_argument("--body", required=True)
    p.add_argument("--inline", help="JSON list of line comments: [{path, line, start_line?, body}]")
    p = sub.add_parser("post"); p.add_argument("--dir", required=True); p.add_argument("--gh-repo", required=True)
    p.add_argument("--pr", required=True, type=int); p.add_argument("--sha256", required=True)
    p.add_argument("--reviewed-sha"); p.add_argument("--allow-new-commits", action="store_true")
    p.add_argument("--gh", help=argparse.SUPPRESS)  # test hook: path to a fake gh
    a = ap.parse_args()
    return prepare(a) if a.cmd == "prepare" else post(a)


if __name__ == "__main__":
    sys.exit(main())
