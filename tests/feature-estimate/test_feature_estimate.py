#!/usr/bin/env python3
"""Tests and parity check for feature-estimate. Run: python3 tests/feature-estimate/test_feature_estimate.py

Proves feature-estimate reuses migration-estimate: identical PRDs give identical JSON and an identical summary
(apart from the title word), the wrappers hold no estimation logic, and the traceability check works.
"""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
ME, FE = root / "skills/migration-estimate/scripts", root / "skills/feature-estimate/scripts"
fixture_repo = root / "tests/migration-estimate/fixtures/shop-app"
example = Path(__file__).resolve().parent / "fixtures/example"
tmp = Path(tempfile.mkdtemp())
env = {**os.environ, "KRITHI_HOME": str(tmp / "home")}
problems, parity = [], []


def run(script, *a):
    r = subprocess.run([sys.executable, str(script), *a], capture_output=True, text=True, env=env)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        problems.append(f"{script.name} {a}: not JSON: {r.stdout[-200:]} {r.stderr[-300:]}")
        return r.returncode, {}


def expect(cond, msg):
    if not cond:
        problems.append(msg)


def check(name, cond):
    parity.append((name, "same" if cond else "DIFFERENT"))
    expect(cond, f"parity failed: {name}")


# inventory: same content, only the saved location differs
rc, inv_m = run(ME / "inventory.py", str(fixture_repo))
rc2, inv_f = run(FE / "inventory.py", str(fixture_repo))
expect(rc == 0 and rc2 == 0, "both inventories should succeed")
expect("feature-estimate" in inv_f.get("inventory_path", "") and "migration-estimate" in inv_m.get("inventory_path", ""), "inventory paths wrong")
strip = lambda d: {k: v for k, v in d.items() if k != "inventory_path"}
check("inventory (modules, integrations, target signals)", strip(inv_m) == strip(inv_f))

# the same PRD set through both estimators
fe, me = tmp / "docs/feature-estimate", tmp / "docs/migration-estimate"
shutil.copytree(example, fe)
shutil.copytree(example, me)
for f in ("00-requirements.md",):
    (me / f).unlink()
shutil.rmtree(me / "inputs")
rc, rm = run(ME / "estimate.py", "--dir", str(me), "--inventory", inv_m["inventory_path"], "--write")
rc2, rf = run(FE / "estimate.py", "--dir", str(fe), "--inventory", inv_f["inventory_path"], "--write")
expect(rc == 0 and rm.get("ok"), f"migration estimate on example failed: {rm.get('errors')}")
expect(rc2 == 0 and rf.get("ok"), f"feature estimate on example failed: {rf.get('errors')}")
norm = lambda d: {k: v for k, v in d.items() if k != "written"}
check("estimate JSON (stories, sprints, timelines, errors, warnings)", norm(rm) == norm(rf))
check("sprint rules (5 stories/sprint, 2 engineers, 10 vs 2 days, 20% allowance)", rm.get("timelines") == rf.get("timelines"))
sm = (me / "estimate-summary.md").read_text()
sf = (fe / "estimate-summary.md").read_text()
check("summary file apart from title word and date line", sm.replace("Migration estimate:", "Feature estimate:") == sf)
expect(sf.startswith("# Feature estimate: Shop App"), "summary title should be 'Feature estimate: ...'")
expect(rf.get("total_stories") == 6 and rf.get("total_sprints") == 3, f"example should be 6 stories / 3 sprints: {rf.get('total_stories')}/{rf.get('total_sprints')}")
expect(rf["timelines"]["human"]["weeks"] == 6 and rf["timelines"]["krithi"]["weeks"] == 1.2, f"timelines wrong: {rf['timelines']}")

# review thresholds: same errors from both
review = ("# Estimate review: Shop App\n\n## Coverage against the codebase\nx\n\n## Implementation accuracy\nNone found.\n\n## Architecture fit\nx\n\n"
          "## Stories and sprint count\n- Final total sprints: {n}\n\n## Gaps found and fixed\nNone found.\n\n- Gap percentage (final): {g}\n\n## Result\nx\n")
for n, g in ((3, 45), (9, 10), (3, 10)):
    for d in (me, fe):
        (d / "review.md").write_text(review.format(n=n, g=g))
    _, a = run(ME / "estimate.py", "--dir", str(me), "--review")
    _, b = run(FE / "estimate.py", "--dir", str(fe), "--review")
    check(f"review check (final sprints {n}, gap {g}): errors", a.get("errors") == b.get("errors"))
    if (n, g) == (3, 45):
        expect(any("over 30" in e for e in b.get("errors", [])), "gap over 30 must fail in feature-estimate")

# no estimation logic duplicated in the feature-estimate scripts
banned = re.compile(r"STORIES_PER_SPRINT|HUMAN_DAYS|KRITHI_DAYS|GO_LIVE_ALLOWANCE|math\.ceil|GAP_REWORK_THRESHOLD\s*=|ARCH_LAYERS\s*=")
for f in FE.glob("*.py"):
    expect(not banned.search(f.read_text()), f"{f.name} must not duplicate migration-estimate's estimation logic")
parity.append(("estimation logic copied into feature-estimate", "none (wrappers only)"))

# --- requirements traceability ---------------------------------------------------------------
(fe / "review.md").write_text(review.format(n=3, g=10) + "\n## Requirements coverage\n- 3 of 3 covered.\n")
rc, r = run(FE / "requirements.py", "--dir", str(fe), "--review")
expect(rc == 0 and r.get("ok") and r.get("requirements") == 4 and r.get("covered") == 3 and r.get("exempt") == 1,
       f"example traceability should pass: {r}")
expect(any("REQ-0" in w and "Question" in w for w in r.get("warnings", [])) is False, "no question warnings expected in the example")


def mutate(path, old, new):
    p = fe / path
    p.write_text(p.read_text().replace(old, new))


def errs():
    rc, r = run(FE / "requirements.py", "--dir", str(fe))
    return rc, "\n".join(r.get("errors", []))


shutil.copy(fe / "prd-03-order-filter.md", tmp / "prd3.bak")
mutate("prd-03-order-filter.md", "`REQ-03`", "`REQ-03x`")
(fe / "prd-03-order-filter.md").write_text((fe / "prd-03-order-filter.md").read_text().replace("REQ-03x", "REQ-09"))
rc, e = errs()
expect(rc == 1 and "REQ-03 is not cited by any story" in e and "cites REQ-09" in e, f"uncovered requirement and unknown id must fail: {e}")
shutil.copy(tmp / "prd3.bak", fe / "prd-03-order-filter.md")
mutate("00-requirements.md", "IN-01: \"filter by order status\"", "\"filter by order status\"")
rc, e = errs()
expect(rc == 1 and "REQ-03 cites no customer input" in e, f"requirement without source must fail: {e}")
mutate("00-requirements.md", "\"filter by order status\" | Clear", "IN-07 | Clear")
rc, e = errs()
expect("IN-07, which is not under" in e, f"unknown input id must fail: {e}")
mutate("00-requirements.md", "IN-07 | Clear", "IN-01 | Maybe")
rc, e = errs()
expect("status 'Maybe'" in e, f"bad status must fail: {e}")
mutate("00-requirements.md", "IN-01 | Maybe", "IN-01 | Clear")
(fe / "inputs/01-email.md").unlink()
rc, e = errs()
expect("not in feature-estimate/" in e, f"missing input file must fail: {e}")
(fe / "review.md").write_text(review.format(n=3, g=10))
(fe / "inputs").mkdir(exist_ok=True)
shutil.copy(example / "inputs/01-email.md", fe / "inputs/01-email.md")
rc, r = run(FE / "requirements.py", "--dir", str(fe), "--review")
expect(rc == 1 and any("Requirements coverage" in e for e in r.get("errors", [])), "review without Requirements coverage must fail")

print("Parity with migration-estimate (same PRDs through both):")
for n, v in parity:
    print(f"  {v:>22}  {n}")
print("\n".join(problems) if problems else "OK")
sys.exit(1 if problems else 0)
