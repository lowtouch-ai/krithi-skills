#!/usr/bin/env python3
"""Compute the five-factor weighted review score and the recommendation, and render the scorecard table.

Usage:
  python3 scorecard.py ratings.json [--markdown]

ratings.json:
  {
    "factors": {
      "functional":    {"rating": 4, "evidence": "...", "reasoning": "..."},
      "quality":       {"rating": 3, ...},
      "testing":       {"rating": 3, ...},
      "process":       {"rating": 2, ...},
      "documentation": {"rating": 4, ...}
    },
    "findings": [{"id": "F1", "severity": "High", "status": "Confirmed", "title": "..."}, ...]
  }

rating is an integer 1-5, or null when there is not enough evidence to rate the factor.
finding status: Confirmed | Likely | Needs verification | Withdrawn.

The score never overrides blockers: a confirmed Critical or High finding means Request Changes whatever
the score; an unverified Critical/High candidate or an unrated factor means Needs Further Verification.

Exit codes: 0 ok, 2 invalid input.
"""
import argparse, json, sys
from pathlib import Path

FACTORS = [
    ("functional", "Functional correctness and requirements coverage", 0.30),
    ("quality", "Code quality, security and accessibility", 0.25),
    ("testing", "Testing and validation", 0.20),
    ("process", "Development process compliance", 0.15),
    ("documentation", "PR documentation and review readiness", 0.10),
]
SEVERITIES = ("Critical", "High", "Medium", "Low")
STATUSES = ("Confirmed", "Likely", "Needs verification", "Withdrawn")
APPROVE_MIN = 3.5          # weighted score needed to approve
FACTOR_FLOOR = 3           # no factor may be below this for Approve


def validate(data):
    errs = []
    factors = data.get("factors") or {}
    for key, _, _ in FACTORS:
        f = factors.get(key)
        if f is None:
            errs.append(f"factor '{key}' is missing")
            continue
        r = f.get("rating")
        if r is not None and (not isinstance(r, int) or isinstance(r, bool) or not 1 <= r <= 5):
            errs.append(f"factor '{key}': rating must be an integer 1-5 or null, got {r!r}")
        if r is not None and not (f.get("evidence") or "").strip():
            errs.append(f"factor '{key}': a rating needs evidence")
    for f in data.get("findings") or []:
        if f.get("severity") not in SEVERITIES:
            errs.append(f"finding {f.get('id')}: severity must be one of {SEVERITIES}")
        if f.get("status") not in STATUSES:
            errs.append(f"finding {f.get('id')}: status must be one of {STATUSES}")
    return errs


def recommend(ratings, findings, score):
    """Return (recommendation, reasons). Blockers first, then evidence gaps, then the score."""
    live = [f for f in findings if f.get("status") != "Withdrawn"]
    blockers = [f for f in live if f["status"] == "Confirmed" and f["severity"] in ("Critical", "High")]
    unverified = [f for f in live if f["status"] in ("Likely", "Needs verification") and f["severity"] in ("Critical", "High")]
    unrated = [k for k, r in ratings.items() if r is None]
    low = [k for k, r in ratings.items() if r is not None and r < FACTOR_FLOOR]

    if blockers:
        return "Request Changes", [f"confirmed {f['severity']} finding {f.get('id')}: {f.get('title', '')}".strip() for f in blockers]
    if unverified or unrated:
        return "Needs Further Verification", (
            [f"{f['severity']} finding {f.get('id')} is {f['status'].lower()}, not confirmed" for f in unverified]
            + [f"factor '{k}' could not be rated from the available evidence" for k in unrated])
    if score < APPROVE_MIN or low:
        return "Request Changes", ([f"weighted score {score:.2f} is below {APPROVE_MIN}"] if score < APPROVE_MIN else []) + [
            f"factor '{k}' rated {ratings[k]} (below {FACTOR_FLOOR})" for k in low]
    return "Approve", [f"weighted score {score:.2f}, no blocking findings, every factor {FACTOR_FLOOR} or above"]


def compute(data):
    factors = data["factors"]
    ratings = {k: factors[k].get("rating") for k, _, _ in FACTORS}
    rated = [(k, w) for k, _, w in FACTORS if ratings[k] is not None]
    wsum = sum(w for _, w in rated)
    # Unrated factors are excluded and the remaining weights re-normalised, so the score stays on the
    # 1-5 scale; the recommendation still becomes Needs Further Verification.
    score = round(sum(ratings[k] * w for k, w in rated) / wsum, 2) if wsum else None
    rec, reasons = recommend(ratings, data.get("findings") or [], score or 0.0)
    rows = [{"key": k, "factor": name, "weight": w, "rating": ratings[k],
             "weighted": round(ratings[k] * w, 2) if ratings[k] is not None else None,
             "evidence": factors[k].get("evidence", ""), "reasoning": factors[k].get("reasoning", "")}
            for k, name, w in FACTORS]
    counts = {s: sum(1 for f in data.get("findings") or [] if f.get("severity") == s and f.get("status") == "Confirmed") for s in SEVERITIES}
    return {"rows": rows, "weighted_score": score, "score_note": None if len(rated) == len(FACTORS) else
            f"{len(FACTORS) - len(rated)} factor(s) unrated; score re-normalised over rated factors",
            "recommendation": rec, "reasons": reasons, "confirmed_findings": counts}


def cell(s):
    return " ".join(str(s or "").split()).replace("|", "\\|")


def markdown(res):
    out = ["| Factor | Weight | Rating (1-5) | Weighted | Evidence and reasoning |", "|---|---:|---:|---:|---|"]
    for r in res["rows"]:
        rating = "n/a" if r["rating"] is None else str(r["rating"])
        weighted = "n/a" if r["weighted"] is None else f"{r['weighted']:.2f}"
        why = cell(r["evidence"]) + (f" *Reasoning:* {cell(r['reasoning'])}" if r["reasoning"] else "")
        out.append(f"| {r['factor']} | {int(r['weight'] * 100)}% | {rating} | {weighted} | {why} |")
    score = "n/a" if res["weighted_score"] is None else f"**{res['weighted_score']:.2f} / 5**"
    out.append(f"| **Overall (weighted)** | 100% | | {score} | {cell(res['score_note'] or '')} |")
    out.append("")
    out.append(f"**Recommendation: {res['recommendation']}**. " + "; ".join(res["reasons"]) + ".")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ratings")
    ap.add_argument("--markdown", action="store_true", help="print the Markdown scorecard instead of JSON")
    a = ap.parse_args()
    try:
        data = json.loads(Path(a.ratings).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(json.dumps({"error": f"cannot read {a.ratings}: {e}"}))
        return 2
    errs = validate(data)
    if errs:
        print(json.dumps({"error": "invalid ratings", "problems": errs}, indent=2))
        return 2
    res = compute(data)
    print(markdown(res) if a.markdown else json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
