"""Evaluation categories: anchored score levels, automated indicators and caps per criterion.

Every barema criterion ends up with well-defined score levels (anchors), from one of three sources:

- `edital`  — the edital's barema describes its own levels (`anchors` in edital.json);
- `global`  — the criterion matches a category of `templates/criteria_catalog.json` (same id, or
  `"based_on": "<category>"`): it inherits the category's anchors, indicators and caps;
- `generic` — neither: generic levels (exemplary / met / partly / barely / absent) on its scale.

Indicators are deterministic measures shown next to each criterion (data density for results,
objective × conclusion overlap, compliance failures…). Caps are upper bounds applied by code when a
signal is present (e.g. results ≤ 3/10 when results are only promised), so the same evidence always
limits the score the same way, whatever the evaluators wrote.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from i18n import num, section_label, t

CATALOG_PATH = Path(__file__).resolve().parent.parent / "templates" / "criteria_catalog.json"
_CATALOG: dict[str, Any] | None = None


def catalog() -> dict[str, Any]:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return _CATALOG


def _rescale(x: float, lo: float, hi: float) -> float:
    return round(lo + x * (hi - lo) / 10, 2)


def _bands(mins: list[float], top: float) -> list[tuple[float, float]]:
    """Level minimums (descending) → (min, max) bands; the best band ends at the criterion maximum."""
    out, upper = [], top
    for m in mins:
        out.append((m, upper))
        upper = m
    return out


def text_of(d: dict[str, str] | str, lang: str) -> str:
    if isinstance(d, str):
        return d
    return d.get(lang) or d.get("en") or d.get("_") or next(iter(d.values()), "")


def resolve(c_in: dict[str, Any], c: dict[str, Any], scale_min: float, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    """Attach category, anchors, indicators and caps to a normalized criterion `c` (raw input `c_in`)."""
    cat_id = c_in.get("based_on") or (c["id"] if c["id"] in catalog()["categories"] else None)
    if cat_id and cat_id not in catalog()["categories"]:
        errors.append(f"rubric.criteria[{c['id']}].based_on: {cat_id!r} is not a global category ({', '.join(catalog()['categories'])})")
        cat_id = None
    cat = catalog()["categories"].get(cat_id) if cat_id else None
    lo, hi = scale_min, c["max_score"]
    levels = catalog()["levels"]
    c["category"] = cat_id
    if cat:
        # Translated names only for the best-practice barema (edital_parser clears them for an edital).
        c["name_i18n"] = cat["name"] if c_in.get("name") in (None, "", cat["name"].get("pt")) else {}
        if not c_in.get("name"):
            c["name"] = text_of(cat["name"], "pt")
        if not c["description"]:
            c["description"] = text_of(cat["description"], "en")
        c["indicators"] = list(cat["indicators"])
        c["caps"] = [{"when": k["when"], "max": _rescale(k["max"], lo, hi)} for k in cat["caps"]]
    else:
        c["name_i18n"] = {}
        c["indicators"] = []
        c["caps"] = []

    raw = c_in.get("anchors")
    if raw:
        anchors, ok = [], True
        for i, a in enumerate(raw):
            m, desc = (a.get("min"), a.get("descriptor")) if isinstance(a, dict) else (None, None)
            if isinstance(m, bool) or not isinstance(m, (int, float)) or not (lo <= m <= hi) or not desc:
                errors.append(f"rubric.criteria[{c['id']}].anchors[{i}]: need {{'min': number within {lo}–{hi}, 'descriptor': text}}")
                ok = False
                continue
            anchors.append((float(m), desc if isinstance(desc, dict) else {"_": str(desc)}))
        anchors.sort(key=lambda x: -x[0])
        if ok and anchors and anchors[-1][0] > lo:
            warnings.append(f"rubric.criteria[{c['id']}].anchors: lowest level starts at {anchors[-1][0]:g}, above the scale minimum {lo:g}")
        c["anchors"] = [{"min": b[0], "max": b[1], "descriptor": d} for (_, d), b in zip(anchors, _bands([a[0] for a in anchors], hi), strict=True)]
        c["anchors_source"] = "edital"
    else:
        descs = cat["anchors"] if cat else catalog()["generic_anchors"]
        mins = [_rescale(x, lo, hi) for x in levels]
        c["anchors"] = [
            {"min": b[0], "max": b[1], "descriptor": {lg: descs[lg][i] for lg in descs}}
            for i, b in enumerate(_bands(mins, hi))
        ]
        c["anchors_source"] = "global" if cat else "generic"
    return c


# Research approaches whose results are expected to carry numbers (mirrors area_profiles.NUMBERS_EXPECTED).
NUMBERS_EXPECTED = {"quantitative", "computational"}


def adapt_to_approach(rubric: dict[str, Any], approach: str | None) -> dict[str, Any]:
    """The rubric with the levels of `methods`/`results` matching the research approach.

    Only criteria that use the global category levels change (an edital's own levels are the
    edital's); a criterion that kept the category name gets the variant's name too. The
    "results without numbers" cap is dropped when numbers are not expected."""
    variants = catalog().get("approach_variants", {}).get(approach or "", {})
    numbers = approach in (None, "") or approach in NUMBERS_EXPECTED
    if not variants and numbers:
        return rubric
    out = copy.deepcopy(rubric)
    for c in out["criteria"]:
        var = variants.get(c.get("category") or "")
        if var and c.get("anchors_source") == "global":
            for a, i in zip(c["anchors"], range(5), strict=False):
                a["descriptor"] = {lg: var["anchors"][lg][i] for lg in var["anchors"]}
            if c.get("name_i18n"):
                c["name_i18n"] = var["name"]
                c["name"] = var["name"]["pt"]
                c["description"] = var["description"]["en"]
            c["approach_variant"] = approach
        if not numbers:
            c["caps"] = [k for k in c.get("caps", []) if k["when"] != "results_without_numbers"]
            if approach != "mixed":  # data density and test statistics say nothing about a qualitative or theoretical result
                c["indicators"] = [i for i in c.get("indicators", []) if i not in ("data_density", "inferential", "statcheck")]
    out["approach"] = approach
    return out


def crit_name(c: dict[str, Any], lang: str) -> str:
    return text_of(c["name_i18n"], lang) if c.get("name_i18n") else c["name"]


def anchors_markdown(rubric: dict[str, Any], lang: str = "en") -> str:
    """Anchor levels per criterion, for the evaluators' prompt."""
    L = []
    for c in rubric["criteria"]:
        src = {"edital": "from the edital", "global": f"global category `{c.get('category')}`", "generic": "generic levels"}[c.get("anchors_source", "generic")]
        L.append(f"**`{c['id']}` — {c['name']}** ({src})")
        for a in c.get("anchors", []):
            L.append(f"- {a['min']:g}–{a['max']:g}: {text_of(a['descriptor'], lang)}")
        if c.get("caps"):
            L.append("- Cap applied by code: " + "; ".join(f"≤ {k['max']:g} when {CAP_WHY_EN[k['when']]}" for k in c["caps"]))
        L.append("")
    return "\n".join(L).strip()


CAP_WHY_EN = {
    "promises_high": "results are only promised for the event",
    "results_without_numbers": "the results contain no numbers",
    "repeated_text": "more than 10 % of the body is repeated text",
}
CAP_WHY_KEY = {"promises_high": "ck_promises", "results_without_numbers": "ck_numbers", "repeated_text": "ck_repeated"}


def signals(metrics: dict[str, Any], content: dict[str, Any], approach: str | None = None) -> dict[str, bool]:
    numbers = approach in (None, "") or approach in NUMBERS_EXPECTED
    return {
        "promises_high": any(p["severity"] == "high" for p in content.get("promises", [])),
        "results_without_numbers": numbers and bool(content.get("data_density", {}).get("results_without_numbers")),
        "repeated_text": bool((content.get("repetition") or {}).get("significant")),
    }


def apply_caps(scores: dict[str, float], rubric: dict[str, Any], sig: dict[str, bool], lang: str = "pt") -> tuple[dict[str, float], list[dict[str, Any]]]:
    if rubric.get("apply_caps") is False:
        return scores, []
    out, applied = dict(scores), []
    for c in rubric["criteria"]:
        for k in c.get("caps", []):
            v = out.get(c["id"])
            if sig.get(k["when"]) and v is not None and v > k["max"]:
                applied.append({"criterion": c["id"], "from": v, "to": k["max"], "when": k["when"],
                                "reason": t(lang, "cap_reason", c=crit_name(c, lang), v=num(float(k["max"]), lang), why=t(lang, CAP_WHY_KEY[k["when"]]).lower())})
                out[c["id"]] = k["max"]
    return out, applied


def _present(metrics: dict[str, Any], name: str) -> bool:
    names = {s["name"] for s in metrics.get("per_section", [])}
    return name in names or (name in ("results", "discussion") and "results_discussion" in names)


def indicators(c: dict[str, Any], metrics: dict[str, Any], content: dict[str, Any], lang: str = "pt") -> str:
    """One line of automated measures relevant to criterion `c`."""
    out = []
    yes, no = t(lang, "yes"), t(lang, "no")
    for ind in c.get("indicators", []):
        if ind.startswith("section_"):
            sec = ind.removeprefix("section_")
            out.append(f"{section_label(sec, lang)}: {yes if _present(metrics, sec) else no}")
        elif ind == "objective_conclusion":
            oc = content.get("objective_conclusion", {})
            if oc.get("available"):
                out.append(t(lang, "i_overlap", v=num(float(oc["overlap"]), lang)) + (f" ({t(lang, 'lvl_low')})" if oc.get("weak_link") else ""))
        elif ind == "data_density":
            d = content.get("data_density", {})
            if d:
                out.append(t(lang, "i_density", lvl=t(lang, "lvl_" + d["level"]), p=num(float(d["per_100_words"]), lang)))
        elif ind == "inferential":
            out.append(t(lang, "i_inferential", v=yes if content.get("data_density", {}).get("has_inferential_statistics") else no))
        elif ind == "promises_high":
            out.append(t(lang, "i_promises", n=content.get("promise_summary", {}).get("high", 0)))
        elif ind == "statcheck":
            sc = content.get("statcheck", {})
            if sc.get("tests_checked"):
                out.append(t(lang, "i_statcheck", i=sc["inconsistencies_count"], n=sc["tests_checked"]))
        elif ind == "compliance":
            s = metrics.get("summary", {})
            out.append(t(lang, "i_compliance", f=s.get("n_fail", 0), w=s.get("n_warn", 0)))
        elif ind == "repetition":
            rep = content.get("repetition") or {}
            out.append(t(lang, "i_repetition", pct=round(100 * rep.get("duplicated_word_share", 0))))
    return " · ".join(out) or "—"


def indicators_markdown(rubric: dict[str, Any], metrics: dict[str, Any], content: dict[str, Any]) -> str:
    """Automated indicators per criterion, for the evaluators' prompt (English)."""
    rows = ["| Criterion | Automated indicators |", "|---|---|"]
    for c in rubric["criteria"]:
        rows.append(f"| `{c['id']}` | {indicators(c, metrics, content, 'en')} |")
    return "\n".join(rows)
