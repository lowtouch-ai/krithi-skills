#!/usr/bin/env python3
"""Create and find validate-pr run folders, outside the application repository.

Every run gets its own folder, keyed by the identity GitHub reports for the PR (never by the local folder name),
so PR #12 of two different repositories, and two runs of the same PR, never share evidence:

  <artifacts>/<host>/<owner>/<repo>/pr-<n>/run-<YYYYMMDDTHHMMSSZ>-<sha12>/
      metadata.json   PR URL, repository URL, tested commit, timestamps, environment, app, tests, status
      history.jsonl   events: run created, steps, app start/stop, test runs, defects, reviews, commits, pushes
      results/ screenshots/ traces/ logs/ defects/ report/

<artifacts> is $VALIDATE_PR_ARTIFACTS, else ~/.krithi/validate-pr-artifacts. <host> is "github" for github.com,
otherwise the GitHub Enterprise host name. Owner and repo are lower-cased (GitHub names are case-insensitive).

Usage:
  run_store.py init  --pr <URL | owner/repo#N | N> [--gh-repo owner/name] [--pr-json saved.json]
  run_store.py list  --pr <URL | owner/repo#N | N> [--gh-repo owner/name]
  run_store.py show  --run D
  run_store.py set   --run D --json '{"app": {"url": "http://127.0.0.1:3000"}}'   # deep-merge into metadata.json

`init` reads the PR with `gh pr view` (or a saved `gh pr view --json` file with --pr-json, for offline use) and prints
the run folder, the previous run of this PR (for retesting) and the PR facts. Exit codes: 0 ok, 2 usage error or the
PR could not be read.
"""
import argparse, json, platform, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RUN_SUBDIRS, artifacts_base, load_meta, log_event, merge_meta, now, out, run, run_dir, save_meta  # noqa: E402

PR_FIELDS = ("number,title,body,url,state,isDraft,author,baseRefName,headRefName,headRefOid,baseRefOid,files,"
             "closingIssuesReferences,headRepository,headRepositoryOwner,isCrossRepository,maintainerCanModify,"
             "additions,deletions,changedFiles")
URL_RE = re.compile(r"^https?://([^/]+)/([\w.-]+)/([\w.-]+)/pull/(\d+)")
SHORT_RE = re.compile(r"^([\w.-]+)/([\w.-]+)#(\d+)$")
NAME_RE = re.compile(r"^[\w.-]+$")


def parse_pr(spec, gh_repo=None):
    """-> (host, owner, repo, number); owner/repo may be None for a bare number (taken from the current repo)."""
    spec = (spec or "").strip()
    if m := URL_RE.match(spec):
        return m.group(1), m.group(2), re.sub(r"\.git$", "", m.group(3)), int(m.group(4))
    if m := SHORT_RE.match(spec):
        return "github.com", m.group(1), m.group(2), int(m.group(3))
    if spec.lstrip("#").isdigit():
        if gh_repo:
            owner, _, repo = gh_repo.partition("/")
            return "github.com", owner, repo, int(spec.lstrip("#"))
        return "github.com", None, None, int(spec.lstrip("#"))
    raise SystemExit(json.dumps({"error": f"cannot parse PR '{spec}': give a URL, owner/repo#N, or a number with --gh-repo"}))


def gh_pr(host, owner, repo, number):
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit(json.dumps({"error": "gh CLI not found; install it and run `gh auth login`"}))
    fields = PR_FIELDS.split(",")
    repo_arg = ["--repo", f"{host}/{owner}/{repo}" if host != "github.com" else f"{owner}/{repo}"] if owner else []
    while True:  # older gh versions lack some fields (e.g. closingIssuesReferences): drop them and retry
        code, so, se = run([gh, "pr", "view", str(number), "--json", ",".join(fields), *repo_arg])
        m = re.search(r'Unknown JSON field: "(\w+)"', se)
        if code != 0 and m and m.group(1) in fields:
            fields.remove(m.group(1))
            continue
        break
    if code != 0:
        raise SystemExit(json.dumps({"error": f"cannot read the PR: {se.strip()[-400:]}",
                                     "fix": "check `gh auth status`, the PR link, and that you have read access"}))
    pr = json.loads(so)
    if "closingIssuesReferences" not in pr:  # fall back to the closing keywords in the PR body
        base = (pr.get("url") or "").split("/pull/")[0]
        pr["closingIssuesReferences"] = [{"number": int(n), "url": f"{base}/issues/{n}"} for n in dict.fromkeys(
            re.findall(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", pr.get("body") or ""))]
    return pr


def identity(pr, host_hint):
    """Owner, repo and host from GitHub's own answer (the PR URL), never from the local folder name."""
    m = URL_RE.match(pr.get("url", ""))
    if not m:
        raise SystemExit(json.dumps({"error": f"PR data has no usable url: {pr.get('url')!r}"}))
    host, owner, repo, number = m.group(1), m.group(2), m.group(3), int(m.group(4))
    if not (NAME_RE.match(owner) and NAME_RE.match(repo)) or owner in (".", "..") or repo in (".", ".."):
        raise SystemExit(json.dumps({"error": f"unexpected owner/repo in PR url: {owner}/{repo}"}))
    return host or host_hint, owner, repo, number


def pr_root(host, owner, repo, number):
    host_seg = "github" if host.lower() == "github.com" else host.lower()
    return artifacts_base() / host_seg / owner.lower() / repo.lower() / f"pr-{int(number)}"


def runs_of(root):
    if not root.is_dir():
        return []
    rows = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("run-")):
        try:
            m = load_meta(d)
        except (OSError, ValueError):
            continue
        rows.append({"run_dir": str(d), "started_at": m.get("started_at"), "tested_commit_sha": m.get("tested_commit_sha"),
                     "validation_status": m.get("validation_status"), "previous_run": m.get("previous_run")})
    return sorted(rows, key=lambda r: (r["started_at"] or "", r["run_dir"]))


def cmd_init(a):
    host, owner, repo, number = parse_pr(a.pr, a.gh_repo)
    pr = json.loads(Path(a.pr_json).read_text(encoding="utf-8")) if a.pr_json else gh_pr(host, owner, repo, number)
    host, owner, repo, number = identity(pr, host)
    sha = pr.get("headRefOid") or ""
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        raise SystemExit(json.dumps({"error": f"PR head commit is missing or invalid: {sha!r}"}))
    root = pr_root(host, owner, repo, number)
    previous = runs_of(root)
    stamp = now().replace("-", "").replace(":", "")  # 20261118T153000Z
    d = root / f"run-{stamp}-{sha[:12]}"
    k = 2
    while d.exists():  # two runs in the same second
        d = root / f"run-{stamp}-{sha[:12]}-{k}"
        k += 1
    for sub in RUN_SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    head_repo = pr.get("headRepository") or {}
    head_owner = (pr.get("headRepositoryOwner") or {}).get("login")
    base_url = f"https://{host}/{owner}/{repo}"
    prev = previous[-1] if previous else None
    meta = {
        "schema_version": 1,
        "pr_url": pr.get("url"), "repository_url": base_url, "host": host, "owner": owner, "repository": repo,
        "pr_number": number, "pr_title": pr.get("title"), "pr_state": pr.get("state"), "is_draft": pr.get("isDraft"),
        "author": (pr.get("author") or {}).get("login"),
        "base_ref": pr.get("baseRefName"), "base_commit_sha": pr.get("baseRefOid"),
        "head_ref": pr.get("headRefName"), "tested_commit_sha": sha,
        "head_repository": {"owner": head_owner, "name": head_repo.get("name"),
                            "url": f"https://{host}/{head_owner}/{head_repo.get('name')}" if head_owner and head_repo.get("name") else base_url,
                            "is_fork": bool(pr.get("isCrossRepository")), "maintainer_can_modify": pr.get("maintainerCanModify")},
        "linked_issues": [i.get("url") for i in pr.get("closingIssuesReferences") or [] if i.get("url")],
        "changed_files": [f.get("path") for f in pr.get("files") or []],
        "size": {"additions": pr.get("additions"), "deletions": pr.get("deletions"), "changed_files": pr.get("changedFiles")},
        "started_at": now(), "finished_at": None,
        "validation_status": "in-progress",
        "previous_run": prev["run_dir"] if prev else None,
        "previous_tested_commit_sha": prev["tested_commit_sha"] if prev else None,
        "environment": {"os": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
                        "python": platform.python_version()},
        "worktree": None, "app": {}, "tests": {}, "committed_artifacts": {}, "defects": {},
    }
    (d / "pr.json").write_text(json.dumps(pr, indent=2), encoding="utf-8")
    save_meta(d, meta)
    log_event(d, {"event": "run_created", "pr_url": meta["pr_url"], "tested_commit_sha": sha, "previous_run": meta["previous_run"]})
    return out({"run_dir": str(d), "pr_url": meta["pr_url"], "repository_url": base_url, "owner": owner, "repository": repo,
                "pr_number": number, "tested_commit_sha": sha, "head_ref": meta["head_ref"], "base_ref": meta["base_ref"],
                "is_fork": meta["head_repository"]["is_fork"], "state": meta["pr_state"], "is_draft": meta["is_draft"],
                "previous_run": meta["previous_run"], "previous_tested_commit_sha": meta["previous_tested_commit_sha"],
                "earlier_runs": len(previous), "pr_json": str(d / "pr.json")})


def cmd_list(a):
    host, owner, repo, number = parse_pr(a.pr, a.gh_repo)
    if not owner:
        raise SystemExit(json.dumps({"error": "list needs owner/repo: give a URL, owner/repo#N, or --gh-repo"}))
    root = pr_root(host, owner, repo, number)
    return out({"pr_root": str(root), "runs": runs_of(root)})


def cmd_show(a):
    return out(load_meta(run_dir(a.run)))


def cmd_set(a):
    d = run_dir(a.run)
    patch = json.loads(a.json)
    if not isinstance(patch, dict):
        raise SystemExit(json.dumps({"error": "--json must be an object"}))
    for locked in ("pr_url", "repository_url", "owner", "repository", "pr_number", "tested_commit_sha", "started_at"):
        if locked in patch:
            raise SystemExit(json.dumps({"error": f"{locked} identifies the run and cannot be changed; start a new run"}))
    merge_meta(d, patch)
    log_event(d, {"event": "metadata_updated", "keys": sorted(patch)})
    return out({"run_dir": str(d), "updated": sorted(patch)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--pr", required=True); p.add_argument("--gh-repo"); p.add_argument("--pr-json")
    p = sub.add_parser("list"); p.add_argument("--pr", required=True); p.add_argument("--gh-repo")
    sub.add_parser("show").add_argument("--run", required=True)
    p = sub.add_parser("set"); p.add_argument("--run", required=True); p.add_argument("--json", required=True)
    a = ap.parse_args()
    return {"init": cmd_init, "list": cmd_list, "show": cmd_show, "set": cmd_set}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
