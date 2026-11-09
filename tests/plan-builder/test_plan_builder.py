#!/usr/bin/env python3
"""Smoke test for plan-builder scripts. Run: python3 tests/plan-builder/test_plan_builder.py"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
save = str(root / "skills/plan-builder/scripts/save_artifacts.py")
check = str(root / "skills/plan-builder/scripts/check_prompt.py")
tmp = Path(tempfile.mkdtemp())
problems = []


def run(script, *a, cwd=None, env=None):
    return subprocess.run([sys.executable, script, *a], capture_output=True, text=True, cwd=cwd, env=env)


def expect(cond, msg):
    if not cond:
        problems.append(msg)


src = tmp / "evidence.log"; src.write_text("ERROR something failed\n")
base = tmp / "out"

r = run(save, "--ticket", "ABC-1", "--base", str(base), str(src), str(tmp / "missing.png"))
j = json.loads(r.stdout)
expect(r.returncode == 1 and len(j["saved"]) == 1 and len(j["failed"]) == 1, "save should report 1 saved + 1 failed")
saved = j["saved"][0]["path"]
expect(os.path.isabs(saved) and Path(saved).is_file(), "saved path must be absolute and exist")
r2 = run(save, "--ticket", "ABC-1", "--base", str(base), str(src))
expect(json.loads(r2.stdout)["saved"][0]["path"] != saved, "collision must not overwrite")
expect(run(save, "--ticket", "../x", "--base", str(base)).returncode == 2, "bad ticket id must be rejected")

repo = tmp / "repo"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)])
r3 = run(save, "--ticket", "ABC-2", "--base", str(repo / "art"), str(src))
expect(r3.returncode == 2 and "git work tree" in r3.stdout, "destination inside a repo must be refused")
r4 = run(save, "--ticket", "ABC-3", "--init", cwd=str(repo), env={**os.environ, "PLAN_BUILDER_HOME": str(tmp / "home")})
expect(r4.returncode == 0 and str(tmp / "home" / "ABC-3") in r4.stdout, "PLAN_BUILDER_HOME must be honored")

good = f"""> **PLAN MODE ONLY.** Do not create, edit or delete any file.

# ABC-1: Example title

## Objective
x
## Ticket details
x
## Key terms
x
## Supporting artifacts
- `{saved}`: log
## Expected behavior
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
pg = tmp / "good.md"; pg.write_text(good)
expect(run(check, str(pg)).returncode == 0, "valid prompt should pass")
bad = good.replace(saved, "relative/evidence.log").replace("## Deliverable", "## Other").replace("x\n## Ticket", "{oops}\n## Ticket")
pb = tmp / "bad.md"; pb.write_text(bad)
out = run(check, str(pb)).stdout
expect("not absolute" in out and "missing section: Deliverable" in out and "placeholder" in out, "bad prompt errors not all reported")

print("OK" if not problems else "\n".join(problems))
sys.exit(1 if problems else 0)
