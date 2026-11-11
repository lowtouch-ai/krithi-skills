#!/usr/bin/env python3
"""Smoke test for migration-estimate scripts. Run: python3 tests/migration-estimate/test_migration_estimate.py"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
inventory = str(root / "skills/migration-estimate/scripts/inventory.py")
estimate = str(root / "skills/migration-estimate/scripts/estimate.py")
fixture = root / "tests/migration-estimate/fixtures/shop-app"
tmp = Path(tempfile.mkdtemp())
env = {**os.environ, "KRITHI_HOME": str(tmp / "home" / ".krithi")}
problems = []


def run(script, *a):
    r = subprocess.run([sys.executable, script, *a], capture_output=True, text=True, env=env)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        problems.append(f"{Path(script).name} {a}: not JSON: {r.stdout[-300:]} {r.stderr[-300:]}")
        return r.returncode, {}


def expect(cond, msg):
    if not cond:
        problems.append(msg)


# --- inventory -------------------------------------------------------------------------------
rc, inv = run(inventory, str(fixture))
mods = {m["path"] for m in inv.get("modules", [])}
integ = {i["name"] for i in inv.get("integrations", [])}
expect(rc == 0, "inventory should succeed")
expect({"src/main/java/com/acme/orders", "src/main/java/com/acme/billing", "web/pages", "jobs"} <= mods,
       f"inventory modules wrong: {sorted(mods)}")
expect(not any(m.startswith(("tests", "node_modules")) for m in mods), f"test/vendor folders must be skipped: {sorted(mods)}")
expect({"PostgreSQL", "Stripe", "RabbitMQ"} <= integ, f"integrations missed: {sorted(integ)}")
inv_path = inv.get("inventory_path", "")
expect(inv_path.startswith(str(tmp / "home" / ".krithi" / "migration-estimate")) and Path(inv_path).is_file(),
       f"inventory must be saved under KRITHI_HOME: {inv_path}")


# --- estimate: build PRDs --------------------------------------------------------------------
def story(pid, n):
    return f"### {pid}-S{n:02d}: Story {n}\nAs a user, I want x.\n\n**Acceptance criteria**\n- works\n\n**Source:** `jobs`\n"


def prd(n, stories, cov, extra=""):
    pid = f"PRD-{n:02d}"
    body = "\n".join(story(pid, i) for i in range(1, stories + 1))
    req = "".join(f"## {h}\n- x `jobs`\n\n" for h in ["Description", "Business Rules & Logic", "Roles & Permissions", "Key Data Involved", "Notable Constraints"])
    return (f"# {pid}: Area {n}\n\n{req}## Integrations\n{extra or 'None.'}\n\n## Source coverage\n" + "\n".join(f"- `{c}`: code" for c in cov) +
            f"\n\n## Stories\n\n{body}\n## Dependencies\nNone.\n\n## Confidence & Open Questions\n- Rules verified. Confidence: 90%\n")


def write_set(d: Path, sizes, cov_for=None, listed=None, hl_extra=""):
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.md"):
        f.unlink()
    ids = [f"PRD-{i:02d}" for i in range(1, len(sizes) + 1)] if listed is None else listed
    rows = "\n".join(f"| {i} | t | s | `x` |" for i in ids)
    (d / "00-high-level-prd.md").write_text(
        f"# High-level PRD: Shop App\n\n## Detailed PRDs\n| ID | Title | Scope | Paths |\n|---|---|---|---|\n{rows}\n\n"
        "## Overview\nx\n\n## Use cases and feature areas\nx\n\n## Roles & Permissions Model\nx\n\n## Data Model Overview\nx\n\n"
        "## Non-Functional Requirements\nx\n\n## Release / Versioning Scope\nx\n\n"
        f"## Out of scope\n{hl_extra or 'None.'}\n\n## Confidence & Open Questions\n- PostgreSQL, Stripe and RabbitMQ are used. Confidence: 95%\n")
    for i, s in enumerate(sizes, 1):
        cov = (cov_for or {}).get(i, ["src/main/java/com/acme", "web", "jobs"])
        (d / f"prd-{i:02d}-area.md").write_text(prd(i, s, cov))


out = tmp / "repo" / "docs" / "migration-estimate"

# The brief's worked example: 40 sprints -> 80 weeks human, 16 weeks Krithi, allowance ~16 and ~3 weeks.
write_set(out, [25] * 8)
rc, r = run(estimate, "--dir", str(out), "--inventory", inv_path, "--write")
expect(rc == 0 and r.get("ok"), f"valid set should pass: {r.get('errors')}")
t = r.get("timelines", {})
expect(r.get("total_sprints") == 40 and r.get("total_stories") == 200, f"expected 40 sprints/200 stories, got {r.get('total_sprints')}/{r.get('total_stories')}")
expect(t.get("human", {}).get("weeks") == 80 and t.get("krithi", {}).get("weeks") == 16, f"weeks wrong: {t}")
expect(t.get("human", {}).get("go_live_allowance_rounded") == 16 and t.get("krithi", {}).get("go_live_allowance_rounded") == 3,
       f"go-live allowance wrong: {t}")
summary = (out / "estimate-summary.md").read_text() if (out / "estimate-summary.md").is_file() else ""
for needle in ["~96 weeks", "~19 weeks", "**80 weeks**", "**16 weeks**", "QA sign-off", "Production deployment", "Data migration",
               "approximation, not part of the core estimate", "~16 weeks", "~3 weeks", "[PRD-08](prd-08-area.md)"]:
    expect(needle in summary, f"summary missing {needle!r}")

# Per-PRD round-up: 6 stories -> 2 sprints, 1 story -> 1 sprint, 5 -> 1 (total 4, not ceil(12/5) = 3).
write_set(out, [6, 1, 5])
rc, r = run(estimate, "--dir", str(out))
expect([p["sprints"] for p in r.get("prds", [])] == [2, 1, 1] and r.get("total_sprints") == 4,
       f"per-PRD round-up wrong: {[p.get('sprints') for p in r.get('prds', [])]}")

# Errors: PRD without stories, PRD listed with no file, file not listed, mis-formed story heading.
write_set(out, [3, 0], listed=["PRD-01", "PRD-03"])
(out / "prd-01-area.md").write_text((out / "prd-01-area.md").read_text().replace("### PRD-01-S03: Story 3", "### Story three"))
rc, r = run(estimate, "--dir", str(out), "--write")
errs = "\n".join(r.get("errors", []))
expect(rc == 1 and not (out / "estimate-summary.md").exists(), "errors must fail and must not write the summary")
for needle in ["PRD-02 has no stories", "PRD-03 is listed", "PRD-02 is not listed", "not in '### PRD-01-SNN"]:
    expect(needle in errs, f"missing error {needle!r} in: {errs}")

# Kriti-REQ sections are required; unscored confidence items are warned.
write_set(out, [5])
f1 = out / "prd-01-area.md"
f1.write_text(f1.read_text().replace("## Business Rules & Logic", "## Rules").replace("Confidence: 90%", "probably"))
rc, r = run(estimate, "--dir", str(out))
expect(rc == 1 and any("missing section '## Business Rules & Logic'" in e for e in r.get("errors", [])), "missing REQ section must fail")
expect(any("without 'Confidence: NN%'" in w for w in r.get("warnings", [])), "unscored confidence item must warn")

# Coverage: a module and an integration left out are reported; Out of scope counts as covered.
write_set(out, [5], cov_for={1: ["src/main/java/com/acme/orders", "web"]})
(out / "00-high-level-prd.md").write_text((out / "00-high-level-prd.md").read_text().replace("RabbitMQ", "a queue"))
rc, r = run(estimate, "--dir", str(out), "--inventory", inv_path)
expect(set(r.get("uncovered_modules", [])) == {"src/main/java/com/acme/billing", "jobs"}, f"uncovered modules wrong: {r.get('uncovered_modules')}")
expect(r.get("uncovered_integrations") == ["RabbitMQ"], f"uncovered integrations wrong: {r.get('uncovered_integrations')}")
write_set(out, [5], cov_for={1: ["src/main/java/com/acme", "web"]}, hl_extra="- `jobs/`: retired, confirmed by client (RabbitMQ)")
rc, r = run(estimate, "--dir", str(out), "--inventory", inv_path)
expect(rc == 0, f"Out of scope path should count as covered: {r.get('errors')}")

# Review file must exist, have its sections and match the computed total.
rc, r = run(estimate, "--dir", str(out), "--review")
expect(rc == 1 and any("missing review.md" in e for e in r.get("errors", [])), "missing review.md must fail")
review = ("# Estimate review: Shop App\n\n## Coverage against the codebase\nx\n\n## Implementation accuracy\nNone found.\n\n"
          "## Stories and sprint count\n- Final total sprints: {n}\n\n## Gaps found and fixed\nNone found.\n\n"
          "- Gap percentage (final): {g}\n\n## Result\nComplete.\n")
(out / "review.md").write_text(review.format(n=1, g=45))
rc, r = run(estimate, "--dir", str(out), "--review")
expect(rc == 1 and any("over 30" in e for e in r.get("errors", [])), "final gap over 30 must fail (Kriti-REQ rework threshold)")
(out / "review.md").write_text(review.format(n=7, g=10))
rc, r = run(estimate, "--dir", str(out), "--review")
expect(rc == 1 and any("says 7" in e for e in r.get("errors", [])), "review total mismatch must fail")
(out / "review.md").write_text(review.format(n=1, g=10))
rc, r = run(estimate, "--dir", str(out), "--inventory", inv_path, "--write", "--review")
expect(rc == 0 and (out / "estimate-summary.md").is_file(), f"final check should pass: {r.get('errors')}")

print("OK" if not problems else "\n".join(problems))
sys.exit(1 if problems else 0)
