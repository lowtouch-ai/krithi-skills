#!/usr/bin/env python3
"""Smoke test for plan-builder scripts. Run: python3 tests/plan-builder/test_plan_builder.py"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
save = str(root / "skills/plan-builder/scripts/save_artifacts.py")
check = str(root / "skills/plan-builder/scripts/check_prompt.py")
tmp = Path(tempfile.mkdtemp())
problems = []


def run(script, *a, cwd=None):
    return subprocess.run([sys.executable, script, *a], capture_output=True, text=True, cwd=cwd)


def expect(cond, msg):
    if not cond:
        problems.append(msg)


repo = tmp / "repo"; (repo / "src").mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(repo)])
src = tmp / "evidence.log"; src.write_text("ERROR something failed\n")

home = tmp / "home"
env = {**os.environ, "KRITHI_HOME": str(home / ".krithi")}


def run_save(*a, cwd):
    return subprocess.run([sys.executable, save, *a], capture_output=True, text=True, cwd=cwd, env=env)


# artifacts go to ~/.krithi/<TICKET>/ (outside the repo); prompt path is under the repo's docs/
r = run_save("--ticket", "ABC-1", str(src), str(tmp / "missing.png"), cwd=repo / "src")
j = json.loads(r.stdout)
expect(r.returncode == 1 and len(j["saved"]) == 1 and len(j["failed"]) == 1, "save should report 1 saved + 1 failed")
saved = j["saved"][0]["path"]
expect(saved == str((home / ".krithi" / "ABC-1" / "evidence.log").resolve()), f"unexpected artifact path {saved}")
expect(Path(saved).is_file() and not saved.startswith(str(repo)), "artifact must exist and be outside the repo")
expect(j["prompt_path"] == "docs/plan-prompts/ABC-1-codex-plan-prompt.md", "prompt path must be under docs/plan-prompts")
expect(Path(j["repo_root"]) == repo.resolve(), "repo root must be the git top-level even from a subfolder")
j2 = json.loads(run_save("--ticket", "ABC-1", str(src), cwd=repo).stdout)
expect(j2["saved"][0]["path"] != saved, "collision must not overwrite")
expect(run_save("--ticket", "../x", cwd=repo).returncode == 2, "bad ticket id must be rejected")
r3 = subprocess.run([sys.executable, save, "--ticket", "ABC-2", "--base", str(repo / "art"), str(src)], capture_output=True, text=True, cwd=repo)
expect(r3.returncode == 2 and "git work tree" in r3.stdout, "artifact base inside a repo must be refused")

good = f"""> **PLAN MODE ONLY.** Do not create, edit or delete any file.

# ABC-1: Example title

## Objective
x
## Ticket details
x
## Key terms
x
## Repository context
x
## Supporting artifacts
- `{saved}`: log
## Expected behavior
x
## Implied requirements and hazards
x
## Investigation tasks
x
## Planning requirements
x
## Constraints
x
## Open questions from the ticket
None identified.
## Deliverable
x

> **PLAN MODE ONLY.** Do not modify any code.
"""
pg = repo / j["prompt_path"]; pg.write_text(good)
expect(run(check, str(pg)).returncode == 0, "valid prompt should pass: " + run(check, str(pg)).stdout)
bad = good.replace(saved, "relative/evidence.log").replace("## Deliverable", "## Other").replace("x\n## Ticket", "{oops}\n## Ticket")
pb = repo / "docs/plan-prompts/bad.md"; pb.write_text(bad)
out = run(check, str(pb)).stdout
expect("not absolute" in out and "missing section: Deliverable" in out and "placeholder" in out, "bad prompt errors not all reported")
pn = repo / "docs/plan-prompts/missing.md"; pn.write_text(good.replace(saved, str(home / ".krithi" / "ABC-1" / "nope.png")))
expect("does not exist" in run(check, str(pn)).stdout, "missing artifact must be reported")
inrepo = repo / "src" / "shot.png"; inrepo.write_text("x")
pi = repo / "docs/plan-prompts/inrepo.md"; pi.write_text(good.replace(saved, str(inrepo)))
expect("inside the repository" in run(check, str(pi)).stdout, "artifact inside the repo must be reported")

print("OK" if not problems else "\n".join(problems))
sys.exit(1 if problems else 0)
