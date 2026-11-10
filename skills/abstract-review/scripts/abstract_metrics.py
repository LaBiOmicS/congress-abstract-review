#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Exact size and compliance checks of an abstract against congress rules.

Counts the way text editors do (Word / LibreOffice / Google Docs): markup stripped, every run of
whitespace counted as one space, paragraph breaks not counted as characters. Only the components
listed in the rules' `count_scope` (body, title, front_matter, keywords, references, funding) enter
the limit; section headings of a structured abstract ("Métodos:") are part of the body, as they are
in the editor.

Each check gets a status:
  pass / fail      rule stated by the edital and verified
  warn             advisory mode (no edital) or a heuristic count that a human should confirm
  unknown          the rule exists but the submission does not allow a deterministic answer
In `strict` mode a fail is a compliance problem for the committee to judge; this script never
rejects a submission by itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_abstract import BACK_MATTER  # noqa: E402
from i18n import report_language, section_label, t  # noqa: E402

MARKUP_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*|\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)|`|^\s*>\s?|\[/?TABLE\]")


def plain(text: str) -> str:
    """Text as an editor shows it: no Markdown markers, whitespace runs collapsed to one space."""
    return " ".join(MARKUP_RE.sub("", text).split())


def count(text: str) -> dict[str, int]:
    flat = plain(text)
    return {
        "words": sum(1 for tok in flat.split() if re.search(r"\w", tok)),
        "characters_with_spaces": len(flat),
        "characters_without_spaces": sum(1 for ch in flat if not ch.isspace()),
    }


def component_texts(structure: dict[str, Any]) -> dict[str, str]:
    comps = dict(structure.get("components") or {})
    # Body as the editor counts it: headings included.
    comps["body"] = "\n\n".join(
        (f"{s['heading']}: " if s.get("heading") else "") + s["text"]
        for s in structure.get("sections", [])
        if s["name"] not in BACK_MATTER and s.get("text")
    )
    for name in ("keywords", "funding", "references"):
        sec = [s for s in structure.get("sections", []) if s["name"] == name]
        if sec:
            comps[name] = "\n\n".join(f"{s['heading']}: {s['text']}" if s.get("heading") else s["text"] for s in sec)
    return comps


def estimate_authors(front_lines: list[str]) -> int | None:
    """Authors in the first byline (comma / ';' / ' e ' / ' and ' separated). None when there is no byline."""
    for ln in front_lines:
        if "@" in ln:
            continue
        if re.search(r"(?i)universi|institut|departa|faculdade|laborat|embrapa|hospital", ln):
            continue
        names = [n for n in re.split(r",|;|\s+(?:e|and|y|&)\s+", re.sub(r"[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]+", "", ln)) if n.strip()]
        if names:
            return len(names)
    return None




def _check(cid: str, label: str, status: str, observed: Any, limit: Any = None, severity: str = "minor", note: str = "") -> dict[str, Any]:
    return {"id": cid, "label": label, "status": status, "observed": observed, "limit": limit, "severity": severity, "note": note}


def _bounds(observed: int | None, rng: dict[str, Any]) -> str | None:
    if observed is None:
        return None
    lo, hi = rng.get("min"), rng.get("max")
    if lo is None and hi is None:
        return None
    if (lo is not None and observed < lo) or (hi is not None and observed > hi):
        return "fail"
    return "pass"


def _fmt_range(rng: dict[str, Any]) -> str:
    lo, hi = rng.get("min"), rng.get("max")
    if lo is not None and hi is not None:
        return f"{lo}–{hi}"
    return f"≤ {hi}" if hi is not None else f"≥ {lo}"


def compute_metrics(structure: dict[str, Any], rules: dict[str, Any], fmt: str | None = None, lang: str = "pt") -> dict[str, Any]:
    fmt = fmt or structure.get("format", {}).get("effective") or structure.get("format", {}).get("detected") or "simple"
    advisory = rules.get("enforcement") == "advisory"
    spec = (rules.get("formats") or {}).get(fmt)
    comps = component_texts(structure)
    counts = {name: count(text) for name, text in comps.items()}
    per_section = [{"name": s["name"], "heading": s.get("heading", ""), **count(s.get("text", ""))} for s in structure.get("sections", [])]

    checks: list[dict[str, Any]] = []
    out: dict[str, Any] = {
        "format": fmt,
        "enforcement": rules.get("enforcement"),
        "lang": lang,
        "counts": counts,
        "per_section": per_section,
        "checks": checks,
    }
    if spec is None:
        other = [k for k in (rules.get("formats") or {})]
        checks.append(_check("format_allowed", t(lang, "k_format_allowed"), "fail" if not advisory else "warn",
                             fmt, other, "blocking", t(lang, "k_format_allowed_n", other=other, fmt=fmt)))
        return _summarize(out, advisory)

    def add(cid: str, label: str, status: str | None, observed: Any, limit: Any, severity: str, note: str = "") -> None:
        if status is None:
            return
        if advisory and status == "fail":
            status = "warn"
        checks.append(_check(cid, label, status, observed, limit, severity, note))

    # Size limits over the components in scope.
    scope = spec["limits"].get("count_scope", ["body"])
    scoped = count("\n\n".join(comps.get(c, "") for c in scope))
    out["counted_scope"] = scope
    out["counted"] = scoped
    for key in ("words", "characters_with_spaces", "characters_without_spaces"):
        label = t(lang, f"k_{key}")
        rng = spec["limits"].get(key) or {}
        status = _bounds(scoped[key], rng)
        if status:
            excess = scoped[key] - rng["max"] if rng.get("max") is not None and scoped[key] > rng["max"] else 0
            note = t(lang, "k_excess", n=excess) if excess else ""
            add(f"limit_{key}", f"{label} ({scope_label(scope, lang)})", status, scoped[key], _fmt_range(rng), "major", note)

    pages = structure.get("pages")
    prng = spec["limits"].get("pages") or {}
    if prng.get("max") is not None or prng.get("min") is not None:
        if pages is None:
            add("limit_pages", t(lang, "k_pages"), "unknown", None, _fmt_range(prng), "major", t(lang, "k_pages_none"))
        else:
            st = _bounds(pages, prng)
            if structure.get("source", {}).get("pages_estimated") and st == "fail":
                st = "warn"
            add("limit_pages", t(lang, "k_pages"), st, pages, _fmt_range(prng), "major",
                t(lang, "k_pages_est") if structure.get("source", {}).get("pages_estimated") else "")

    title = structure.get("title", "")
    tcount = count(title)
    for key, label in (("max_words", "words"), ("max_characters", "characters_with_spaces")):
        lim = (spec.get("title") or {}).get(key)
        if lim is not None:
            add(f"title_{key}", t(lang, "k_title_words" if key == "max_words" else "k_title_chars"),
                "fail" if tcount[label] > lim else "pass", tcount[label], f"≤ {lim}", "minor")

    # Sections.
    names = set(structure.get("section_names") or [])
    if "results_discussion" in names:
        names |= {"results", "discussion"}
    labelled = names - {"unlabelled"} - BACK_MATTER
    for sec in spec.get("required_sections", []):
        label = t(lang, "k_required", s=section_label(sec, lang))
        if sec in names:
            add(f"section_{sec}", label, "pass", True, t(lang, "k_required_v"), "major")
        elif sec in BACK_MATTER or labelled:
            add(f"section_{sec}", label, "fail", False, t(lang, "k_required_v"), "major")
        else:
            # Unstructured block: the content may be there without a label; the panel judges it.
            add(f"section_{sec}", label, "unknown", t(lang, "k_unlabelled_v"), t(lang, "k_required_v"), "major", t(lang, "k_unlabelled_n"))
    for sec in spec.get("forbidden_sections", []):
        if sec in names:
            add(f"forbidden_{sec}", t(lang, "k_forbidden", s=section_label(sec, lang)), "fail", True, t(lang, "k_forbidden_v"), "major")

    # Figures, tables, references, keywords, authors.
    for key, label, observed in (
        ("figures", t(lang, "k_figures"), max(structure["figures"]["count"], structure["figures"].get("embedded_images") or 0)),
        ("tables", t(lang, "k_tables"), structure["tables"]["count"]),
        ("references", t(lang, "k_references"), structure["references"]["count"]),
    ):
        rule = spec.get(key) or {}
        if rule.get("allowed") is False:
            add(f"{key}_allowed", t(lang, "k_not_allowed", label=label), "fail" if observed else "pass", observed, 0, "major")
        else:
            rng = {"min": rule.get("min"), "max": rule.get("max")}
            st = _bounds(observed, rng)
            if st:
                add(f"{key}_count", label, st, observed, _fmt_range(rng), "minor")
    kw = len(structure.get("keywords") or [])
    st = _bounds(kw, spec.get("keywords") or {})
    if st:
        add("keywords_count", t(lang, "k_keywords"), st if kw or "keywords" in names else "fail", kw, _fmt_range(spec["keywords"]), "minor")

    authors = estimate_authors(structure.get("front_matter", {}).get("lines", []))
    out["authors_estimated"] = authors
    if spec.get("max_authors") is not None:
        if authors is None:
            add("max_authors", t(lang, "k_authors"), "unknown", None, f"≤ {spec['max_authors']}", "minor", t(lang, "k_authors_none"))
        else:
            st = "pass" if authors <= spec["max_authors"] else "warn"
            add("max_authors", t(lang, "k_authors"), st, authors, f"≤ {spec['max_authors']}", "minor", t(lang, "k_authors_heur"))

    detected = structure.get("language", {})
    if rules.get("languages"):
        ok = detected.get("code") in rules["languages"]
        st = "pass" if ok else ("warn" if detected.get("confidence", 0) < 0.6 else "fail")
        add("language", t(lang, "k_language"), st, detected.get("code"), ", ".join(rules["languages"]), "blocking" if not ok else "minor")

    if rules.get("anonymized"):
        front = structure.get("front_matter", {})
        exposed = bool(front.get("lines")) or front.get("emails", 0) > 0
        add("anonymized", t(lang, "k_anon"), "fail" if exposed else "pass",
            t(lang, "k_anon_exposed") if exposed else t(lang, "k_anon_ok"), t(lang, "k_anon_limit"), "blocking",
            t(lang, "k_anon_n") if exposed else "")

    sec = structure.get("security_scan") or {}
    if not sec.get("is_clean", True) or sec.get("hidden_content_high_count"):
        checks.append(_check("security", t(lang, "k_security"), "warn", sec.get("suspicious_prompt_injection_count", 0), 0, "blocking", t(lang, "k_security_n")))
    return _summarize(out, advisory)


def _summarize(out: dict[str, Any], advisory: bool) -> dict[str, Any]:
    checks = out["checks"]
    by = {s: [c["id"] for c in checks if c["status"] == s] for s in ("pass", "fail", "warn", "unknown")}
    out["summary"] = {
        **{f"n_{k}": len(v) for k, v in by.items()},
        "failed": by["fail"],
        "blocking_failures": [c["id"] for c in checks if c["status"] == "fail" and c["severity"] == "blocking"],
        "compliant": not by["fail"],
        "advisory": advisory,
    }
    return out


def scope_label(scope: list[str], lang: str = "pt") -> str:
    return " + ".join(t(lang, f"c_{c}") if c in ("body", "title", "front_matter", "keywords", "references", "funding") else c for c in scope)


def to_markdown(m: dict[str, Any]) -> str:
    lang = m.get("lang", "pt")
    s = m["summary"]
    mode = t(lang, "norm_default") if s["advisory"] else t(lang, "norm_edital")
    fmt = t(lang, "fmt_expanded" if m["format"] == "expanded" else "fmt_simple")
    lines = [f"## {t(lang, 'm_title')}", "", f"- {t(lang, 'm_format')}: **{fmt}** · {t(lang, 'm_ref')}: {mode}"]
    if "counted" in m:
        c = m["counted"]
        lines.append("- " + t(lang, "m_count", scope=scope_label(m["counted_scope"], lang), w=c["words"], cw=c["characters_with_spaces"], cn=c["characters_without_spaces"]))
    lines.append("- " + t(lang, "m_result", p=s["n_pass"], f=s["n_fail"], w=s["n_warn"], u=s["n_unknown"]))
    lines += ["", t(lang, "m_cols"), "|---|---|---|---|---|"]
    for c in m["checks"]:
        obs = t(lang, "yes") if c["observed"] is True else t(lang, "no") if c["observed"] is False else ("—" if c["observed"] is None else c["observed"])
        lines.append(f"| {c['label']} | {obs} | {c['limit'] if c['limit'] is not None else '—'} | {t(lang, 'st_' + c['status'])} | {c['note']} |")
    lines += ["", f"### {t(lang, 'm_per_section')}", "", t(lang, "m_sec_cols"), "|---|---|---|"]
    for sec in m["per_section"]:
        lines.append(f"| {sec['heading'] or section_label(sec['name'], lang)} | {sec['words']} | {sec['characters_with_spaces']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Size and compliance checks of an abstract against congress rules.")
    p.add_argument("--structure", required=True, help="structure.json from extract_abstract.py")
    p.add_argument("--rules", required=True, help="rules.json from edital_parser.py (validate or default)")
    p.add_argument("--format", choices=["auto", "simple", "expanded"], default="auto")
    p.add_argument("--output-json", required=True)
    p.add_argument("--output-md")
    p.add_argument("--language", choices=["auto", "pt", "en", "es"], default="auto", help="Report language (auto = the abstract's language).")
    args = p.parse_args()
    structure = json.loads(Path(args.structure).read_text(encoding="utf-8"))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    lang = report_language(args.language, structure.get("language", {}).get("code"))
    m = compute_metrics(structure, rules, None if args.format == "auto" else args.format, lang)
    Path(args.output_json).write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(to_markdown(m), encoding="utf-8")
    print(json.dumps({"status": "ok", "format": m["format"], "counted": m.get("counted"), **m["summary"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
