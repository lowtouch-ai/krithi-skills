#!/usr/bin/env python3
"""Validate a generated plan-builder prompt. Usage: check_prompt.py PROMPT.md. Exit 1 on errors."""
import re, sys
from pathlib import Path

REQUIRED = ["Objective", "Ticket details", "Key terms", "Repository context", "Supporting artifacts", "Expected behavior", "Implied requirements", "Investigation tasks",
            "Planning requirements", "Constraints", "Open questions", "Deliverable"]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_prompt.py PROMPT.md")
        return 2
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"ERROR: {p} not found")
        return 1
    text = p.read_text(encoding="utf-8")
    errors, warns = [], []
    lines = [l for l in text.splitlines() if l.strip()]

    if not lines or not re.search(r"PLAN MODE ONLY", lines[0], re.I):
        errors.append("first line must carry the PLAN MODE ONLY clause")
    if not re.search(r"PLAN MODE ONLY", lines[-1] if lines else "", re.I):
        errors.append("last line must carry the PLAN MODE ONLY clause")
    if len(re.findall(r"do not (?:modify|create, edit)", text, re.I)) < 1:
        errors.append("no explicit 'do not modify/edit files' instruction")

    m = re.search(r"^# ([A-Za-z0-9][A-Za-z0-9_-]*-\d+|[A-Za-z0-9_-]+):\s*\S", text, re.M)
    if not m:
        errors.append("missing '# <TICKET>: <title>' heading")

    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    for r in REQUIRED:
        if not any(h.startswith(r.lower()) for h in heads):
            errors.append(f"missing section: {r}")

    for ph in sorted(set(re.findall(r"\{[A-Za-z][^{}\n]{0,60}\}", text))):
        errors.append(f"unresolved placeholder: {ph}")
    if re.search(r"\b(TODO|TBD|FIXME)\b", text):
        errors.append("TODO/TBD/FIXME left in prompt")

    sec = re.search(r"^## Supporting artifacts\s*$(.*?)(?=^## )", text, re.M | re.S)
    if sec:
        for path in re.findall(r"`([^`\n]+)`", sec.group(1)):
            if "/" not in path and "\\" not in path:
                continue
            if not (path.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", path)):
                errors.append(f"artifact path is not absolute: {path}")
            elif not Path(path).exists():
                errors.append(f"artifact path does not exist: {path}")
    else:
        errors.append("could not parse Supporting artifacts section")

    if re.search(r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*\S{6,}", text):
        warns.append("possible secret value in prompt; mask it")
    if len(text) > 40000:
        warns.append("prompt is very long (>40 KB); consider trimming")

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
