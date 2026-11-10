"""Deterministic scoring: parse reviewer JSON, aggregate, apply the approval cutoff, decide escalation.

The models write the evaluation and the per-criterion scores; everything after that (median,
weights, approval cutoff, criterion minimums, compliance holds, escalation to the full panel) is
computed here, so the same reviews always produce the same committee result.

The plugin decides only whether the abstract is approved or rejected. The presentation modality
(oral, poster) is the committee's, and posters are evaluated at the event, not here.
"""

from __future__ import annotations

import json
import re
from statistics import median
from typing import Any

from i18n import dec_label, num, score, t

SCORES_BLOCK_RE = re.compile(r"```json\s+SCORES_JSON\s*\n(.*?)\n```", re.S)
SYNTHESIS_BLOCK_RE = re.compile(r"```json\s+SYNTHESIS_JSON\s*\n(.*?)\n```", re.S)
REQUIRED_HEADINGS = ("## Summary", "## Scores", "## Feedback to the authors")
CONFIDENCE = ("high", "medium", "low")
TRACK_FIT = ("good", "partial", "poor")
DECISIONS = ("approved", "rejected")


def _last_json(block_re: re.Pattern[str], text: str) -> tuple[Any, str | None]:
    blocks = block_re.findall(text)
    if not blocks:
        return None, "JSON block not found"
    try:
        return json.loads(blocks[-1]), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"


def _num(v: float | None, lang: str = "pt") -> str:
    """Score as committees write it: 7,5 in pt/es, 7.5 in en."""
    return num(float(v) if v is not None else None, lang)


def section(md: str, heading: str) -> str:
    """Body of a level-2 Markdown section (heading text matched case-insensitively)."""
    m = re.search(rf"(?ims)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|^```json|\Z)", md)
    return m.group(1).strip() if m else ""


def parse_review(md: str, rubric: dict[str, Any], decisions: list[str], track_codes: list[str]) -> dict[str, Any]:
    data, err = _last_json(SCORES_BLOCK_RE, md)
    errors = [err] if err else []
    data = data if isinstance(data, dict) else {}
    lo = rubric["scale"]["min"]
    scores: dict[str, float] = {}
    raw = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    for c in rubric["criteria"]:
        v = raw.get(c["id"])
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"score for '{c['id']}' missing or not a number")
            continue
        if not lo <= v <= c["max_score"]:
            errors.append(f"score for '{c['id']}' = {v} outside {lo}–{c['max_score']}")
            continue
        scores[c["id"]] = float(v)
    decision = str(data.get("decision") or "").strip().lower() or None
    if decision and decision not in decisions:
        errors.append(f"decision '{decision}' not in {list(decisions)}")
        decision = None
    track = data.get("track")
    if track_codes and track not in track_codes and track is not None:
        track = None  # unknown track code: ignored, not an error
    confidence = data.get("confidence") if data.get("confidence") in CONFIDENCE else "medium"
    missing_headings = [h for h in REQUIRED_HEADINGS if h.lower() not in md.lower()]
    if missing_headings:
        errors.append(f"missing sections: {missing_headings}")
    return {
        "valid": not errors,
        "errors": errors,
        "scores": scores,
        "decision": decision,
        "track": track,
        "track_fit": data.get("track_fit") if data.get("track_fit") in TRACK_FIT else None,
        "confidence": confidence,
        "blocking_issues": [str(x) for x in data.get("blocking_issues") or []][:5],
        "feedback": section(md, "Feedback to the authors"),
        "confidential": section(md, "Confidential comments to the committee"),
        "summary": section(md, "Summary"),
    }


def parse_synthesis(md: str) -> dict[str, Any]:
    data, err = _last_json(SYNTHESIS_BLOCK_RE, md)
    data = data if isinstance(data, dict) else {}
    errors = [err] if err else []
    if "## feedback to the authors" not in md.lower():
        errors.append("missing section: ## Feedback to the authors")
    return {
        "valid": not errors,
        "errors": errors,
        "overrides": [o for o in data.get("overrides") or [] if isinstance(o, dict)],
        "decision": (str(data.get("decision") or "").strip().lower() or None),
        "decision_note": str(data.get("decision_note") or ""),
        "track": data.get("track"),
        "compliance_hold": bool(data.get("compliance_hold")),
        "integrity_flag": bool(data.get("integrity_flag")),
        "assessment": section(md, "Committee assessment"),
        "feedback": section(md, "Feedback to the authors"),
        "confidential": section(md, "Confidential comments to the committee"),
    }


def total_score(scores: dict[str, float], rubric: dict[str, Any]) -> float | None:
    crits = rubric["criteria"]
    if not crits or any(c["id"] not in scores for c in crits):
        return None
    if rubric["aggregation"] == "sum":
        return round(sum(scores[c["id"]] for c in crits), 2)
    # Weighted mean on the common scale; criteria with their own max are rescaled first.
    hi, lo = rubric["scale"]["max"], rubric["scale"]["min"]
    num = sum(c["weight"] * (lo + (scores[c["id"]] - lo) * (hi - lo) / (c["max_score"] - lo)) for c in crits)
    return round(num / sum(c["weight"] for c in crits), 2)


def aggregate(reviews: list[dict[str, Any]], rubric: dict[str, Any]) -> dict[str, Any]:
    valid = [r for r in reviews if r["valid"]]
    per: dict[str, float] = {}
    spread: dict[str, float] = {}
    for c in rubric["criteria"]:
        vals = [r["scores"][c["id"]] for r in valid if c["id"] in r["scores"]]
        if vals:
            per[c["id"]] = round(float(median(vals)), 2)
            spread[c["id"]] = round(max(vals) - min(vals), 2)
    return {"scores": per, "spread": spread, "total": total_score(per, rubric), "n_reviews": len(valid)}


def apply_overrides(scores: dict[str, float], overrides: list[dict[str, Any]], rubric: dict[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    out = dict(scores)
    applied = []
    limits = {c["id"]: (rubric["scale"]["min"], c["max_score"]) for c in rubric["criteria"]}
    for o in overrides:
        cid, val = o.get("criterion"), o.get("score")
        if cid in limits and isinstance(val, (int, float)) and not isinstance(val, bool) and str(o.get("reason") or "").strip():
            lo, hi = limits[cid]
            new = float(min(max(val, lo), hi))
            applied.append({"criterion": cid, "from": out.get(cid), "to": new, "reason": str(o["reason"])})
            out[cid] = new
    return out, applied


def decide(
    total: float | None,
    scores: dict[str, float],
    rules: dict[str, Any],
    metrics: dict[str, Any],
    content: dict[str, Any],
    security: dict[str, Any],
    *,
    audience: str = "committee",
    lang: str = "pt",
) -> dict[str, Any]:
    """Score → approved / rejected, with reasons and flags.

    Without an approval cutoff the decision is left to the committee (None) and the sheet shows the
    evaluators' recommendation. `audience="author"` (pre-submission check): edital breaches become
    `fix_before_submission` (the authors must fix them) instead of `compliance_hold` (the committee
    decides on them)."""
    rubric = rules["rubric"]
    cutoff = rubric.get("approval_cutoff")
    reasons: list[str] = []
    flags: list[str] = []

    decision = None
    if total is not None and cutoff is not None:
        decision = "approved" if total >= cutoff else "rejected"
        reasons.append(t(lang, "score_to_decision", total=score(total, lang), decision=dec_label(decision, lang), cutoff=score(cutoff, lang)))
        if decision == "approved":
            unmet = [f"{cid} {_num(scores.get(cid), lang)} < {_num(v, lang)}" for cid, v in (rubric.get("approval_min_scores") or {}).items() if scores.get(cid, 0) < v]
            high_promises = [p for p in content.get("promises", []) if p["severity"] == "high"]
            if unmet:
                reasons.append(t(lang, "min_unmet", items=", ".join(unmet)))
            if high_promises:
                reasons.append(t(lang, "approval_blocked_promises"))
            if unmet or high_promises:
                decision = "rejected"
    elif total is not None:
        reasons.append(t(lang, "no_cutoffs"))

    summary = metrics.get("summary", {})
    if not summary.get("advisory") and summary.get("failed"):
        labels = {c["id"]: c["label"] for c in metrics.get("checks", [])}
        items = ", ".join(labels.get(cid, cid) for cid in summary["failed"])
        if audience == "author":
            flags.append("fix_before_submission")
            reasons.append(t(lang, "breach_author", items=items))
        else:
            flags.append("compliance_hold")
            reasons.append(t(lang, "breach_committee", items=items))
    if not security.get("is_clean", True):
        flags.append("integrity")
        reasons.append(t(lang, "integrity"))
    if (content.get("data_density", {}).get("results_without_numbers") and rules.get("track_kind", "research") == "research"
            and rules.get("approach") in (None, "quantitative", "computational")):
        flags.append("no_quantitative_results")
    if (rules.get("profile") or {}).get("ethics_check"):
        flags.append("ethics_check")
        reasons.append(t(lang, "ethics_check"))
    if (content.get("repetition") or {}).get("significant"):
        flags.append("repeated_text")
        reasons.append(t(lang, "repeated", pct=round(100 * content["repetition"]["duplicated_word_share"])))

    margin = None
    if total is not None and cutoff is not None:
        margin = round(abs(total - cutoff), 2)
    return {"decision": decision, "reasons": reasons, "flags": flags, "margin_to_cutoff": margin}


def escalation_reasons(
    omega: dict[str, Any],
    decision: dict[str, Any],
    rules: dict[str, Any],
    content: dict[str, Any],
    lang: str = "pt",
) -> list[str]:
    """Why a single-evaluator (lite) result should go to the full three-member panel."""
    if not omega.get("valid"):
        return [t(lang, "esc_invalid")]
    rubric = rules["rubric"]
    span = rubric["total_range"]["max"] - rubric["total_range"]["min"]
    out = []
    if decision.get("margin_to_cutoff") is not None and decision["margin_to_cutoff"] <= 0.05 * span:
        out.append(t(lang, "esc_margin", margin=score(decision["margin_to_cutoff"], lang)))
    if omega.get("confidence") == "low":
        out.append(t(lang, "esc_low_conf"))
    if omega.get("decision") and decision.get("decision") and omega["decision"] != decision["decision"]:
        out.append(t(lang, "esc_mismatch", a=dec_label(omega["decision"], lang), b=dec_label(decision["decision"], lang)))
    # Compliance holds are not escalated: waiving a rule is the committee's call, and two more
    # evaluators would not settle it. They stay flagged in the sheet and the spreadsheet.
    if "integrity" in decision.get("flags", []):
        out.append(t(lang, "esc_integrity"))
    if any(p["severity"] == "high" for p in content.get("promises", [])) and omega.get("decision") == "approved":
        out.append(t(lang, "esc_promises"))
    return out


def disagreements(reviews: list[dict[str, Any]], rubric: dict[str, Any], lang: str = "pt") -> list[str]:
    valid = [r for r in reviews if r["valid"]]
    if len(valid) < 2:
        return []
    out = []
    for c in rubric["criteria"]:
        vals = [r["scores"][c["id"]] for r in valid if c["id"] in r["scores"]]
        if vals and max(vals) - min(vals) > 0.25 * (c["max_score"] - rubric["scale"]["min"]):
            name = (c.get("name_i18n") or {}).get(lang) or c.get("name") or c["id"]
            out.append(f"{name}: {_num(min(vals), lang)}–{_num(max(vals), lang)}")
    decs = {r["decision"] for r in valid if r["decision"]}
    if len(decs) > 1:
        out.append(f"{t(lang, 'decision_word')}: {', '.join(dec_label(d, lang) for d in sorted(decs))}")
    return out
