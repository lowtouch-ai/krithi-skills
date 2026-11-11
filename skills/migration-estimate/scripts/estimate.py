#!/usr/bin/env python3
"""Validate the migration-estimate PRDs, count stories and sprints, and write the estimate summary.

Usage:
  estimate.py [--dir docs/migration-estimate] [--inventory INVENTORY.json] [--write] [--review]

Reads (all under --dir, default docs/migration-estimate at the git top-level of the cwd):
  00-high-level-prd.md   lists every detailed PRD id (PRD-01, PRD-02, ...) under "## Detailed PRDs"
                         and excluded code paths under "## Out of scope"
  prd-NN-<slug>.md       one detailed PRD per file: "# PRD-NN: <title>", "## Source coverage" with
                         backticked code paths, "## Stories" with "### PRD-NN-SMM: <title>" per story

Rules (fixed; they mirror Krithi's sprint estimation):
  5 stories = 1 sprint, rounded up per PRD; total sprints = sum over PRDs.
  A sprint is 2 engineers. Human team: 10 working days per sprint. Krithi: 2 working days per sprint.
  5 working days = 1 week. Go-live allowance = 20% of each timeline, approximate, outside the estimate.

Checks: every PRD in the high-level list has a file and vice versa; every detailed PRD has stories;
story ids are unique and belong to their PRD; every story has acceptance criteria (warning); with
--inventory, every code module and integration found by inventory.py is covered by a PRD or listed
as out of scope. --write writes estimate-summary.md only when there are no errors. --review also
requires review.md with its sections, a "Final total sprints: N" line matching the computed total, and a
"Gap percentage (final): N" line of 30 or less (Kriti-REQ's quality-check rework threshold).
PRD sections follow Kriti-REQ's content contract; missing ones are errors.

Target architecture (references/target-architecture.md): the high-level PRD needs a "## Target architecture" section that
names each default layer (FastAPI, Next.js, PostgreSQL, Redis, Airflow) either as the target or in a stated deviation, and
every detailed PRD needs a "## Target design" section. With --inventory, the signals in inventory.json must be mapped:
AI agents -> agentomatic, file handling -> MinIO, multi-tenancy -> tenant handling (all named in Target architecture),
and scheduled or background jobs -> a DAG in some PRD. A PRD naming Open WebUI as a target gets a warning (not used).
Prints JSON; exit 1 on errors.
"""
import argparse, datetime, json, math, re, subprocess, sys
from pathlib import Path

STORIES_PER_SPRINT = 5
ENGINEERS = 2
HUMAN_DAYS_PER_SPRINT = 10
KRITHI_DAYS_PER_SPRINT = 2
DAYS_PER_WEEK = 5
GO_LIVE_ALLOWANCE = 0.20
NOT_IN_ESTIMATE = ["QA sign-off", "Production deployment", "Data migration"]

HIGH_LEVEL = "00-high-level-prd.md"
SUMMARY = "estimate-summary.md"
REVIEW = "review.md"
REVIEW_SECTIONS = ["Coverage against the codebase", "Implementation accuracy", "Architecture fit", "Stories and sprint count", "Gaps found and fixed", "Result"]
GAP_REWORK_THRESHOLD = 30  # Kriti-REQ's KRITI_REQ_QC_GAP_REWORK_THRESHOLD default

# Kriti-REQ PRD content contract (kriti_req _default_scan_prompt_body), plus the estimate's own sections.
HIGH_LEVEL_SECTIONS = ["Overview", "Use cases and feature areas", "Detailed PRDs", "Roles & Permissions Model", "Data Model Overview",
                       "Non-Functional Requirements", "Release / Versioning Scope", "Target architecture", "Out of scope", "Confidence & Open Questions"]
DETAIL_SECTIONS = ["Description", "Business Rules & Logic", "Roles & Permissions", "Key Data Involved", "Notable Constraints",
                   "Target design", "Source coverage", "Stories", "Confidence & Open Questions"]

# The default target stack. Each layer must be named in the high-level PRD's Target architecture section, as the
# target or in a stated deviation (a deviation that names the layer counts).
ARCH_LAYERS = {"FastAPI": ["fastapi"], "Next.js": ["next.js", "nextjs"], "PostgreSQL": ["postgresql", "postgres"],
               "Redis": ["redis"], "Airflow": ["airflow"]}
FOUNDATION_WORDS = re.compile(r"foundation|platform|scaffold|cross-cutting|shared|infrastructure", re.I)

PRD_ID = r"PRD-\d{2,}"
STORY_RE = re.compile(rf"^###\s+({PRD_ID})-S(\d{{2,}})\s*:\s*(.+?)\s*$", re.M)


def default_dir() -> Path:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=15)
        top = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path.cwd()
    except (OSError, subprocess.SubprocessError):
        top = Path.cwd()
    return top / "docs" / "migration-estimate"


def section(text: str, name: str) -> str:
    """Body of the first '## <name>...' section (up to the next level-2 heading), or ''."""
    m = re.search(rf"^##\s+{re.escape(name)}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def missing_sections(text: str, required) -> list:
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    return [r for r in required if not any(h.startswith(r.lower()) for h in heads)]


def unscored_items(text: str) -> int:
    """Confidence & Open Questions bullets without a 'Confidence: NN%' tag."""
    body = section(text, "Confidence & Open Questions")
    return sum(1 for b in re.findall(r"^\s*[-*]\s+(.+)$", body, re.M) if not re.search(r"confidence:?\s*\d{1,3}\s*%", b, re.I))


def code_paths(body: str):
    out = []
    for p in re.findall(r"`([^`\n]+)`", body):
        p = p.strip().strip("/")
        if p.startswith("./"):
            p = p[2:]
        if p and " " not in p:
            out.append(p)
    return out


def covers(covered: str, module: str) -> bool:
    return covered == module or covered.startswith(module + "/") or module.startswith(covered + "/")


def sprints_for(stories: int) -> int:
    """Sprints for one detailed PRD: 5 stories per sprint, a part-filled sprint counts as a full one."""
    return math.ceil(stories / STORIES_PER_SPRINT)


def timelines(total_sprints: int) -> dict:
    def tl(days_per_sprint):
        days = total_sprints * days_per_sprint
        weeks = days / DAYS_PER_WEEK
        allowance = weeks * GO_LIVE_ALLOWANCE
        return {"days_per_sprint": days_per_sprint, "working_days": days, "weeks": weeks,
                "engineer_weeks": weeks * ENGINEERS, "go_live_allowance_weeks": allowance,
                "go_live_allowance_rounded": int(allowance + 0.5), "weeks_with_allowance": weeks + int(allowance + 0.5)}
    h, k = tl(HUMAN_DAYS_PER_SPRINT), tl(KRITHI_DAYS_PER_SPRINT)
    return {"human": h, "krithi": k, "speedup": HUMAN_DAYS_PER_SPRINT / KRITHI_DAYS_PER_SPRINT}


def num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def parse(d: Path, inventory):
    errors, warns = [], []
    hl_path = d / HIGH_LEVEL
    hl = hl_path.read_text(encoding="utf-8") if hl_path.is_file() else ""
    if not hl:
        errors.append(f"missing {HIGH_LEVEL}")
    m = re.search(r"^#\s+(.+)$", hl, re.M)
    app_title = m.group(1).strip() if m else "Application"
    listed = list(dict.fromkeys(re.findall(PRD_ID, section(hl, "Detailed PRDs"))))
    if hl and not listed:
        errors.append(f"{HIGH_LEVEL}: no PRD ids found under '## Detailed PRDs'")
    out_of_scope = code_paths(section(hl, "Out of scope"))
    if hl:
        for s_ in missing_sections(hl, HIGH_LEVEL_SECTIONS):
            errors.append(f"{HIGH_LEVEL}: missing section '## {s_}'")
        if unscored_items(hl):
            warns.append(f"{HIGH_LEVEL}: {unscored_items(hl)} Confidence & Open Questions item(s) without 'Confidence: NN%'")

    arch = section(hl, "Target architecture").lower()
    if hl and arch:
        for layer, names in ARCH_LAYERS.items():
            if not any(n in arch for n in names):
                errors.append(f"{HIGH_LEVEL}: '## Target architecture' does not name {layer}; map the application onto it or record an architecture deviation that names it")
        if "open webui" in arch or "openwebui" in arch:
            warns.append(f"{HIGH_LEVEL}: Target architecture mentions Open WebUI; it is not part of the target (the Next.js UI is the front end)")

    prds, seen_story, all_text = {}, {}, hl
    for f in sorted(d.glob("prd-*.md")):
        text = f.read_text(encoding="utf-8")
        all_text += "\n" + text
        h = re.search(rf"^#\s+({PRD_ID})\s*:\s*(.+?)\s*$", text, re.M)
        if not h:
            errors.append(f"{f.name}: first heading must be '# PRD-NN: <title>'")
            continue
        pid, title = h.group(1), h.group(2)
        if pid in prds:
            errors.append(f"{f.name}: {pid} is also used by {prds[pid]['file']}")
            continue
        for s_ in missing_sections(text, DETAIL_SECTIONS):
            errors.append(f"{f.name}: missing section '## {s_}'")
        if unscored_items(text):
            warns.append(f"{f.name}: {unscored_items(text)} Confidence & Open Questions item(s) without 'Confidence: NN%'")
        stories = []
        body = section(text, "Stories")
        matches = list(STORY_RE.finditer(body))
        for i, s in enumerate(matches):
            sid = f"{s.group(1)}-S{s.group(2)}"
            block = body[s.end():matches[i + 1].start() if i + 1 < len(matches) else len(body)]
            if s.group(1) != pid:
                errors.append(f"{f.name}: story {sid} does not belong to {pid}")
            if sid in seen_story:
                errors.append(f"{f.name}: duplicate story id {sid} (also in {seen_story[sid]})")
            seen_story[sid] = f.name
            if not re.search(r"acceptance criteria", block, re.I):
                warns.append(f"{f.name}: story {sid} has no acceptance criteria")
            stories.append({"id": sid, "title": s.group(3)})
        stray = len(re.findall(r"^###\s+(?!PRD-)", body, re.M))
        if stray:
            errors.append(f"{f.name}: {stray} heading(s) under '## Stories' are not in '### {pid}-SNN: <title>' form and would not be counted")
        if not stories:
            errors.append(f"{f.name}: {pid} has no stories")
        cov = code_paths(section(text, "Source coverage"))
        if not cov:
            errors.append(f"{f.name}: '## Source coverage' lists no backticked code paths")
        prds[pid] = {"id": pid, "title": title, "file": f.name, "stories": len(stories),
                     "sprints": sprints_for(len(stories)), "story_ids": [s["id"] for s in stories], "coverage": cov}

    for pid in listed:
        if pid not in prds:
            errors.append(f"{pid} is listed in {HIGH_LEVEL} but has no prd-*.md file")
    for pid, p in prds.items():
        if pid not in listed:
            errors.append(f"{p['file']}: {pid} is not listed under '## Detailed PRDs' in {HIGH_LEVEL}")

    uncovered_modules, uncovered_integrations = [], []
    if inventory is not None:
        covered = [c for p in prds.values() for c in p["coverage"]] + out_of_scope
        for mod in inventory.get("modules", []):
            if not any(covers(c, mod["path"]) for c in covered):
                uncovered_modules.append(mod["path"])
        low = all_text.lower()
        for integ in inventory.get("integrations", []):
            names = [integ["name"]] + integ.get("aliases", [])
            if not any(n.lower() in low for n in names):
                uncovered_integrations.append(integ["name"])
        for m_ in uncovered_modules:
            errors.append(f"module not covered by any PRD or listed under Out of scope: {m_}")
        for i_ in uncovered_integrations:
            errors.append(f"integration not mentioned in any PRD: {i_}")

    unmapped_signals = []
    if inventory is not None:
        sig = inventory.get("target_signals") or {}
        low_all = all_text.lower()
        need = {"ai_agents": ("agentomatic", arch, "AI agents found: map them onto the AI stack (agentomatic) in Target architecture, or record a deviation naming it"),
                "file_storage": ("minio", arch, "file handling found: map it onto MinIO in Target architecture, or record a deviation naming it"),
                "multi_tenant": ("tenant", arch, "multi-tenancy found: describe the tenant handling in Target architecture, or record a deviation"),
                "background_jobs": ("dag", low_all, "scheduled or background jobs found: no PRD mentions an Airflow DAG; map each job to a DAG story or record a deviation")}
        for key, (word, where, msg) in need.items():
            if (sig.get(key) or {}).get("present") and word not in where:
                unmapped_signals.append(key)
                errors.append(msg)
    if prds and not any(FOUNDATION_WORDS.search(p["title"]) for p in prds.values()):
        warns.append("no detailed PRD looks like platform foundation work (scaffold, CI, schema, secrets, request-ID logging); see references/target-architecture.md section 8")

    ordered = [prds[k] for k in sorted(prds, key=lambda x: int(x.split("-")[1]))]
    total_stories = sum(p["stories"] for p in ordered)
    total_sprints = sum(p["sprints"] for p in ordered)
    return {"app_title": app_title, "prds": ordered, "total_stories": total_stories, "total_sprints": total_sprints,
            "timelines": timelines(total_sprints), "out_of_scope": out_of_scope,
            "uncovered_modules": uncovered_modules, "uncovered_integrations": uncovered_integrations, "unmapped_signals": unmapped_signals,
            "errors": errors, "warnings": warns}


def render(r: dict, inventory_used: bool) -> str:
    h, k = r["timelines"]["human"], r["timelines"]["krithi"]
    today = datetime.date.today().isoformat()
    app = re.sub(r"^High-level PRD\s*:\s*", "", r["app_title"], flags=re.I)
    L = [f"# Migration estimate: {app}", "",
         f"Generated {today} by `estimate.py` from the PRDs in this folder. Do not edit the numbers by hand; change the PRDs and re-run the script.", "",
         "## Headline", "",
         f"**{r['total_sprints']} sprints** ({r['total_stories']} stories across {len(r['prds'])} detailed PRDs), two engineers throughout.", "",
         "| | Human team | With Krithi |", "|---|---:|---:|",
         f"| Engineers | {ENGINEERS} | {ENGINEERS} |",
         f"| Sprints | {r['total_sprints']} | {r['total_sprints']} |",
         f"| Working days per sprint | {h['days_per_sprint']} | {k['days_per_sprint']} |",
         f"| Working days | {h['working_days']} | {k['working_days']} |",
         f"| **Duration (development and testing)** | **{num(h['weeks'])} weeks** | **{num(k['weeks'])} weeks** |",
         f"| Effort | {num(h['engineer_weeks'])} engineer-weeks | {num(k['engineer_weeks'])} engineer-weeks |", "",
         f"Krithi runs the same sprints {num(r['timelines']['speedup'])}x faster: {k['days_per_sprint']} working days per sprint instead of {h['days_per_sprint']}.", "",
         "## Breakdown by detailed PRD", "",
         "| PRD | Title | Stories | Sprints | Human weeks | Krithi weeks |", "|---|---|---:|---:|---:|---:|"]
    for p in r["prds"]:
        L.append(f"| [{p['id']}]({p['file']}) | {p['title']} | {p['stories']} | {p['sprints']} | "
                 f"{num(p['sprints'] * HUMAN_DAYS_PER_SPRINT / DAYS_PER_WEEK)} | {num(p['sprints'] * KRITHI_DAYS_PER_SPRINT / DAYS_PER_WEEK)} |")
    L += [f"| **Total** | | **{r['total_stories']}** | **{r['total_sprints']}** | **{num(h['weeks'])}** | **{num(k['weeks'])}** |", "",
          "## How the estimate is calculated", "",
          f"1. The codebase is described in a [high-level PRD]({HIGH_LEVEL}), which is broken into the detailed PRDs above.",
          "2. Each detailed PRD is converted into stories.",
          f"3. {STORIES_PER_SPRINT} stories make one sprint. Sprints are counted per PRD and rounded up, so a PRD with 6 stories is 2 sprints.",
          f"4. A sprint is {ENGINEERS} engineers. A human team takes {HUMAN_DAYS_PER_SPRINT} working days (two weeks) per sprint; with Krithi the same sprint takes {KRITHI_DAYS_PER_SPRINT} working days.",
          "5. Sprints run one after another, so duration = total sprints x working days per sprint.",
          f"6. The target is Krithi's standard architecture: FastAPI, PostgreSQL, Redis, Next.js and Airflow, with Vault for secrets, MinIO when files are stored and the AI stack when the application has AI agents. Deviations are listed in the [high-level PRD]({HIGH_LEVEL}#target-architecture).", "",
          "## Not included in this estimate", "",
          "The estimate covers **development and testing only**. These activities are not included:", ""]
    L += [f"- {x}" for x in NOT_IN_ESTIMATE]
    L += ["", "### Go-live allowance (approximate)", "",
          f"As a rough allowance for the items above, add about {int(GO_LIVE_ALLOWANCE * 100)}% of the development and testing duration. "
          "**This is an approximation, not part of the core estimate**; confirm it once the client's QA, release and data-migration needs are known.", "",
          "| | Human team | With Krithi |", "|---|---:|---:|",
          f"| Development and testing (core estimate) | {num(h['weeks'])} weeks | {num(k['weeks'])} weeks |",
          f"| Go-live allowance, ~{int(GO_LIVE_ALLOWANCE * 100)}% (approximate) | ~{h['go_live_allowance_rounded']} weeks | ~{k['go_live_allowance_rounded']} weeks |",
          f"| Indicative total to go-live | ~{num(h['weeks_with_allowance'])} weeks | ~{num(k['weeks_with_allowance'])} weeks |", ""]
    if r["out_of_scope"]:
        L += ["## Code excluded from the PRDs", "", f"Listed with reasons in the [high-level PRD]({HIGH_LEVEL}#out-of-scope): " +
              ", ".join(f"`{p}`" for p in r["out_of_scope"]) + ".", ""]
    L += ["## Review", "", f"Coverage and counts were checked{' against the codebase inventory' if inventory_used else ''}; see [review.md]({REVIEW}).", ""]
    return "\n".join(L)


def check_review(d: Path, total: int, errors: list):
    p = d / REVIEW
    if not p.is_file():
        errors.append(f"missing {REVIEW}")
        return
    text = p.read_text(encoding="utf-8")
    heads = [x.strip().lower() for x in re.findall(r"^##\s+(.+)$", text, re.M)]
    for s in REVIEW_SECTIONS:
        if not any(h.startswith(s.lower()) for h in heads):
            errors.append(f"{REVIEW}: missing section '## {s}'")
    m = re.search(r"Final total sprints:\s*\**\s*(\d+)", text, re.I)
    if not m:
        errors.append(f"{REVIEW}: no 'Final total sprints: N' line")
    elif int(m.group(1)) != total:
        errors.append(f"{REVIEW}: says {m.group(1)} final sprints but the PRDs give {total}; re-run the estimate and update the review")
    g = re.search(r"Gap percentage \(final\):\s*\**\s*(\d+)", text, re.I)
    if not g:
        errors.append(f"{REVIEW}: no 'Gap percentage (final): N' line")
    elif int(g.group(1)) > GAP_REWORK_THRESHOLD:
        errors.append(f"{REVIEW}: final gap percentage {g.group(1)} is over {GAP_REWORK_THRESHOLD}; rework the PRDs and re-review")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="output folder (default: <repo>/docs/migration-estimate)")
    ap.add_argument("--inventory", help="inventory.json from inventory.py, for the coverage check")
    ap.add_argument("--write", action="store_true", help=f"write {SUMMARY} when there are no errors")
    ap.add_argument("--review", action="store_true", help=f"also require {REVIEW} matching the computed total")
    a = ap.parse_args()
    d = Path(a.dir).resolve() if a.dir else default_dir()
    if not d.is_dir():
        print(json.dumps({"ok": False, "errors": [f"folder not found: {d}"]}, indent=2))
        return 1
    inv = None
    if a.inventory:
        try:
            inv = json.loads(Path(a.inventory).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(json.dumps({"ok": False, "errors": [f"cannot read inventory: {e}"]}, indent=2))
            return 1
    r = parse(d, inv)
    if a.review:
        check_review(d, r["total_sprints"], r["errors"])
    if a.write and not r["errors"]:
        (d / SUMMARY).write_text(render(r, inv is not None), encoding="utf-8")
        r["written"] = str(d / SUMMARY)
    r["ok"] = not r["errors"]
    for p in r["prds"]:
        p.pop("coverage", None)
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
