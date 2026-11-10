#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic content audit of a congress abstract (PT / EN / ES).

1. Future promises: results deferred to the event ("serão apresentados", "will be presented"),
   work still in progress, expectations stated as findings, and vague value claims without data.
   Future tense in a closing "perspectives" sentence is normal and only reported as info.
2. Data density: quantitative evidence (n, %, means ± SD, CI, p, test statistics, effect sizes,
   units) in the results, per 100 words; results with no numbers are flagged.
3. Objective <-> conclusion lexical link (a hint for reviewers, never a verdict).
4. Expanded abstracts only: statcheck (reported statistic vs p-value), DOI list (optionally checked
   live against OpenAlex / doi.org), and figure/table cross-references vs captions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n import num, report_language, section_label, t  # noqa: E402
from statcheck import run_statcheck  # noqa: E402

# (category, severity, pattern). Severity: high = results not in the abstract; moderate = work not
# done yet / expectation; low = vague claim without data.
PROMISE_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("deferred_results", "high", re.compile(
        r"(?i)\b(?:(?:os\s+)?resultados?|dados|achados|an[áa]lises?|conclus(?:ões|ão))\b[^.;]{0,60}?\bser(?:ão|á)\s+(?:apresentad|discutid|mostrad|divulgad|expost|detalhad|relatad)\w*"
        r"|\bser(?:ão|á)\s+(?:apresentad|discutid|mostrad|divulgad|detalhad)\w*\s+(?:no|durante\s+o|na|durante\s+a)\s+(?:evento|congresso|simp[óo]sio|apresenta[çc][ãa]o|encontro|semin[áa]rio|sess[ãa]o)"
        r"|\b(?:results?|data|findings|analys[ie]s|conclusions?)\b[^.;]{0,60}?\bwill\s+be\s+(?:presented|discussed|shown|reported|disclosed|detailed|available)"
        r"|\bwill\s+be\s+(?:presented|discussed|shown|reported)\s+(?:at|during)\s+(?:the\s+)?(?:conference|meeting|congress|symposium|presentation|session|poster)"
        r"|\b(?:resultados?|datos|hallazgos)\b[^.;]{0,60}?\bser(?:án|á)\s+(?:presentad|discutid|mostrad)\w*"
    )),
    ("ongoing_work", "moderate", re.compile(
        r"(?i)\b(?:em\s+andamento|em\s+curso|em\s+fase\s+(?:de|inicial|final)|est(?:á|ão)\s+sendo\s+(?:realizad|conduzid|analisad|coletad|desenvolvid|avaliad|processad|testad|validad|sequenciad)\w*"
        r"|(?:is|are)\s+(?:currently\s+)?being\s+(?:conducted|analy[sz]ed|collected|developed|evaluated|processed|tested|validated|sequenced|trained|performed)"
        r"|(?:is|are)\s+(?:still\s+)?(?:ongoing|in\s+progress|underway)|work\s+in\s+progress|we\s+are\s+(?:currently\s+)?(?:developing|analy[sz]ing|collecting|testing)"
        r"|en\s+curso|est(?:á|án)\s+siendo\s+(?:realizad|analizad|desarrollad|evaluad)\w*)\b"
    )),
    ("expectation", "moderate", re.compile(
        r"(?i)\b(?:espera-se\s+que|esperamos\s+que|pretende-se|pretendemos|acredita-se\s+que|ser(?:á|ão)\s+avaliad\w*|(?:este|o\s+presente)\s+(?:estudo|trabalho|projeto)\s+(?:ir[áa]|vai|pretende)"
        r"|(?:it\s+is|is)\s+expected\s+(?:that|to)|we\s+expect|we\s+(?:aim|plan|intend)\s+to\s+(?:show|demonstrate|evaluate|assess)|this\s+(?:study|work|project)\s+will"
        r"|se\s+espera\s+que|esperamos\s+que|este\s+(?:estudio|trabajo)\s+(?:evaluar[áa]|pretende))\b"
    )),
    ("vague_claim", "low", re.compile(
        r"(?i)\b(?:resultados?\s+(?:preliminares\s+)?(?:promissores|satisfat[óo]rios|interessantes|relevantes|significativos|positivos|animadores)"
        r"|(?:promising|interesting|encouraging|satisfactory|positive)\s+(?:preliminary\s+)?results|results\s+(?:are|were|look|seem)\s+(?:promising|encouraging|satisfactory)"
        r"|resultados\s+(?:prometedores|satisfactorios|interesantes))\b"
    )),
]

# Future tense that is fine in a closing sentence ("Futuros estudos...", "Next, we will...").
PERSPECTIVE_RE = re.compile(r"(?i)\b(?:futur[oa]s?|perspectivas?|pr[óo]ximos\s+passos|next\s+steps?|future\s+(?:work|studies|research)|em\s+seguida|posteriormente|subsequently)\b")

QUANT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sample_size", re.compile(r"(?i)\b[nN]\s*[=:]\s*\d+|\b\d+\s+(?:pacientes|participantes|indiv[íi]duos|amostras|animais|plantas|sujeitos|patients|participants|subjects|samples|individuals|animals|isolados|isolates|genomas|genomes|esp[ée]cies|species)\b")),
    ("percentage", re.compile(r"\d+(?:[.,]\d+)?\s?%")),
    ("dispersion", re.compile(r"(?i)±|\b(?:DP|SD|EP|SE|SEM|IQR|IIQ)\s*[=:]?\s*\d|\bdesvio[-\s]padr[ãa]o\b")),
    ("interval", re.compile(r"(?i)\b(?:IC|CI)\s?\d{2}\s?%|\b\d{2}\s?%\s*(?:IC|CI)\b|intervalo\s+de\s+confian[çc]a|confidence\s+interval")),
    ("p_value", re.compile(r"(?i)\bp\s*[<>=≤≥]\s*0?[.,]\d+")),
    ("test_statistic", re.compile(r"(?i)\b(?:t|F|χ2|χ²|chi2|z|r|U|H|W|R2|R²)\s*\(?\s*[\d,.\s]*\)?\s*=\s*-?\d")),
    ("effect_size", re.compile(r"(?i)\b(?:OR|RR|HR|d\s+de\s+Cohen|Cohen'?s\s+d|η2|η²|eta2|AUC|odds\s+ratio|risco\s+relativo)\s*[=:(]?\s*\d")),
    ("measurement", re.compile(
        r"(?i)\b\d+(?:[.,]\d+)?\s?(?:mg|g|kg|µg|ug|ng|mL|ml|L|µL|uL|mM|µM|nM|M|mol|cm|mm|nm|µm|m|km|ha|°C|ºC|K|h|min|s|dias|days|meses|months|anos|years|kDa|Da|bp|pb|kb|Mb|Gb|ppm|ppb|UFC|CFU|log)\b")),
    ("performance_metric", re.compile(r"(?i)\b(?:acur[áa]cia|accuracy|precis[ãa]o|precision|recall|sensibilidade|sensitivity|especificidade|specificity|F1|MCC|RMSE|MAE)\b[^.;]{0,25}?\d")),
]

STOP = set(
    "a o os as de da do das dos e em no na nos nas um uma para por com que se ao à às the of and to in for on with by an is are was were this that "
    "el la los las del y en con por para un una este esta estudo study trabajo trabalho work objetivo objective aim foi was ser be".split()
)


def sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9(])", flat) if s.strip()]


def _section_texts(structure: dict[str, Any], *names: str) -> str:
    return "\n".join(s["text"] for s in structure.get("sections", []) if s["name"] in names)


def detect_promises(structure: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    body_sections = [s for s in structure.get("sections", []) if s["name"] not in ("references", "keywords", "funding")]
    for sec in body_sections:
        sents = sentences(sec["text"])
        for i, sent in enumerate(sents):
            for category, severity, pat in PROMISE_PATTERNS:
                m = pat.search(sent)
                if not m:
                    continue
                sev = severity
                # A future-work sentence in the conclusion (or the last sentence of a block abstract) is normal.
                closing = sec["name"] == "conclusion" or (sec["name"] == "unlabelled" and i == len(sents) - 1)
                if category in ("expectation", "ongoing_work") and closing and PERSPECTIVE_RE.search(sent):
                    sev = "info"
                if category == "expectation" and sec["name"] in ("objectives", "introduction") and sev != "info":
                    sev = "moderate"
                found.append({"category": category, "severity": sev, "section": sec["name"], "match": m.group(0), "sentence": sent[:400]})
                break  # one finding per sentence (the strongest pattern listed first)
    return found


def data_density(structure: dict[str, Any]) -> dict[str, Any]:
    results = _section_texts(structure, "results", "results_discussion")
    scope = "results"
    if not results.strip():
        results = _section_texts(structure, "unlabelled", "discussion", "conclusion")
        scope = "body (no labelled results section)"
    # Do not count years, figure/table numbers or reference numbering as data.
    cleaned = re.sub(r"(?i)\b(?:fig(?:ura|ure)?\.?|tab(?:ela|le|la)?\.?|quadro)\s*\d+|\b(?:19|20)\d{2}\b|\[\d+(?:[,–-]\d+)*\]", " ", results)
    hits: dict[str, list[str]] = {}
    for kind, pat in QUANT_PATTERNS:
        # Distinct values only: a number repeated across copied paragraphs is one piece of evidence.
        ms = list(dict.fromkeys(" ".join(m.group(0).split()) for m in pat.finditer(cleaned)))
        if ms:
            hits[kind] = ms
    words = len(cleaned.split())
    total = sum(len(v) for v in hits.values())
    hits = {k: v[:8] for k, v in hits.items()}
    per100 = round(100 * total / words, 2) if words else 0.0
    inferential = bool({"p_value", "test_statistic", "interval", "effect_size"} & hits.keys())
    return {
        "scope": scope,
        "words": words,
        "quantitative_tokens": total,
        "per_100_words": per100,
        "kinds": {k: len(v) for k, v in hits.items()},
        "examples": hits,
        "has_inferential_statistics": inferential,
        "results_without_numbers": words > 0 and total == 0,
        "level": "none" if total == 0 else "low" if per100 < 2 else "adequate" if per100 < 6 else "high",
    }


def repetition(structure: dict[str, Any]) -> dict[str, Any]:
    """Sentences that appear more than once in the body (copy-paste errors or padding to reach a word count)."""
    body = [s for s in structure.get("sections", []) if s["name"] not in ("references", "keywords", "funding")]
    seen: dict[str, int] = {}
    original: dict[str, str] = {}
    total_words = 0
    for sec in body:
        for sent in sentences(sec["text"]):
            total_words += len(sent.split())
            key = re.sub(r"\W+", " ", sent.lower()).strip()
            if len(key) < 40:
                continue
            seen[key] = seen.get(key, 0) + 1
            original.setdefault(key, sent)
    dup = {k: n for k, n in seen.items() if n > 1}
    dup_words = sum((n - 1) * len(original[k].split()) for k, n in dup.items())
    share = round(dup_words / total_words, 3) if total_words else 0.0
    return {
        "repeated_sentences": len(dup),
        "extra_copies": sum(n - 1 for n in dup.values()),
        "duplicated_word_share": share,
        "examples": [{"times": n, "sentence": original[k][:200]} for k, n in sorted(dup.items(), key=lambda x: -x[1])[:5]],
        "significant": share >= 0.1,
    }


def _stems(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-záéíóúâêôãõçñü]{4,}", text.lower()) if w not in STOP}


def objective_conclusion_link(structure: dict[str, Any]) -> dict[str, Any]:
    obj = _section_texts(structure, "objectives")
    concl = _section_texts(structure, "conclusion")
    if not obj or not concl:
        # Block abstracts: first and last sentences stand in for objective and conclusion.
        sents = sentences(_section_texts(structure, "unlabelled", "introduction", "results", "discussion", "results_discussion", "conclusion"))
        aim = next((s for s in sents if re.search(r"(?i)\b(?:objetiv|aim|purpose|objective|goal|este\s+(?:estudo|trabalho)|this\s+(?:study|work))", s)), "")
        obj = obj or aim
        concl = concl or (sents[-1] if sents else "")
    a, b = _stems(obj), _stems(concl)
    if not a or not b:
        return {"available": False, "overlap": None, "shared_terms": [], "note": "objective or conclusion not found"}
    overlap = len(a & b) / min(len(a), len(b))
    return {
        "available": True,
        "overlap": round(overlap, 2),
        "shared_terms": sorted(a & b)[:15],
        "objective": obj[:300],
        "conclusion": concl[:300],
        "weak_link": overlap < 0.1,
    }


CAPTION_RE = re.compile(r"(?im)^\s*(?:\*\*)?(figura|figure|fig\.?|tabela|table|tabla|quadro)\s*(\d+)\s*(?:\*\*)?\s*[.:–—-]")


def cross_references(text: str) -> dict[str, Any]:
    captions = {(("table" if k.lower().startswith(("tab", "quad")) else "figure"), int(n)) for k, n in CAPTION_RE.findall(text)}
    mentions: set[tuple[str, int]] = set()
    for m in re.finditer(r"(?i)\b(figura|figure|fig\.?|tabela|table|tabla|quadro)\s*(\d+)", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if CAPTION_RE.match(text, line_start) and CAPTION_RE.match(text, line_start).start(1) == m.start(1):
            continue  # the caption itself
        kind = "table" if m.group(1).lower().startswith(("tab", "quad")) else "figure"
        mentions.add((kind, int(m.group(2))))
    return {
        "captions": sorted(f"{k} {n}" for k, n in captions),
        "mentioned_without_caption": sorted(f"{k} {n}" for k, n in mentions - captions),
        "caption_never_mentioned": sorted(f"{k} {n}" for k, n in captions - mentions),
    }


def audit(structure: dict[str, Any], text: str, fmt: str, *, verify_citations: bool = False) -> dict[str, Any]:
    promises = detect_promises(structure)
    out: dict[str, Any] = {
        "format": fmt,
        "promises": promises,
        "promise_summary": {sev: sum(1 for p in promises if p["severity"] == sev) for sev in ("high", "moderate", "low", "info")},
        "data_density": data_density(structure),
        "repetition": repetition(structure),
        "objective_conclusion": objective_conclusion_link(structure),
    }
    body = "\n".join(s["text"] for s in structure.get("sections", []) if s["name"] != "references")
    out["statcheck"] = run_statcheck(body)
    if fmt == "expanded":
        out["cross_references"] = cross_references(text)
        dois = structure.get("references", {}).get("dois", [])
        out["citations"] = {"dois": dois, "verified": None}
        if verify_citations and dois:
            from openalex_lookup import lookup_dois

            out["citations"]["verified"] = lookup_dois(dois, max_checks=40)
    return out


def to_markdown(a: dict[str, Any], lang: str = "pt") -> str:
    L = [f"## {t(lang, 'a_title')}", ""]
    ps = a["promise_summary"]
    L.append("### " + t(lang, "a_promises", h=ps["high"], m=ps["moderate"], lo=ps["low"]))
    L.append("")
    if a["promises"]:
        L += [t(lang, "a_prom_cols"), "|---|---|---|---|"]
        for p in a["promises"]:
            cat = t(lang, "cat_perspective") if p["severity"] == "info" else t(lang, f"cat_{p['category']}")
            L.append(f"| {t(lang, 'sev_' + p['severity'])} | {cat} | {section_label(p['section'], lang)} | {p['sentence'].replace('|', '/')} |")
    else:
        L.append(t(lang, "a_no_promises"))
    d = a["data_density"]
    scope = t(lang, "a_scope_results") if d["scope"] == "results" else t(lang, "a_scope_body")
    L += ["", f"### {t(lang, 'a_density')}", "",
          "- " + t(lang, "a_density_line", scope=scope, w=d["words"], n=d["quantitative_tokens"], p=num(float(d["per_100_words"]), lang), lvl=t(lang, "lvl_" + d["level"])),
          f"- {t(lang, 'a_kinds')}: {', '.join(f'{k} ({v})' for k, v in d['kinds'].items()) or t(lang, 'none_lc')}",
          f"- {t(lang, 'a_inferential')}: {t(lang, 'yes') if d['has_inferential_statistics'] else t(lang, 'no')}"]
    if d["results_without_numbers"]:
        L.append("- " + t(lang, "a_no_numbers"))
    rep = a.get("repetition") or {}
    if rep.get("repeated_sentences"):
        L += ["", f"### {t(lang, 'a_repeated')}", "",
              "- " + t(lang, "a_repeated_line", s=rep["repeated_sentences"], c=rep["extra_copies"], pct=round(100 * rep["duplicated_word_share"]))
              + (t(lang, "a_repeated_sig") if rep["significant"] else "")]
        for ex in rep["examples"][:3]:
            L.append(f"  - {ex['times']}×: {ex['sentence']}")
    oc = a["objective_conclusion"]
    L += ["", f"### {t(lang, 'a_obj')}", ""]
    if oc["available"]:
        L.append("- " + t(lang, "a_overlap", v=num(float(oc["overlap"]), lang)) + (t(lang, "a_overlap_weak") if oc["weak_link"] else ""))
        L.append(f"- {t(lang, 'a_shared')}: {', '.join(oc['shared_terms']) or '—'}")
    else:
        L.append("- " + t(lang, "a_obj_missing"))
    sc = a["statcheck"]
    if sc["tests_checked"]:
        L += ["", f"### {t(lang, 'a_stat')}", "", "- " + t(lang, "a_stat_line", n=sc["tests_checked"], i=sc["inconsistencies_count"], d=sc["decision_errors_count"])]
        for e in sc["inconsistencies"][:5]:
            L.append(f"  - `{e['raw']}` → {t(lang, 'a_stat_p')} = {e['recalculated_p_two_tailed']}")
    if a["format"] == "expanded":
        xr = a["cross_references"]
        L += ["", f"### {t(lang, 'a_figs')}", "", f"- {t(lang, 'a_captions')}: {', '.join(xr['captions']) or t(lang, 'none_f')}"]
        if xr["mentioned_without_caption"]:
            L.append(f"- {t(lang, 'a_no_caption')}: {', '.join(xr['mentioned_without_caption'])}")
        if xr["caption_never_mentioned"]:
            L.append(f"- {t(lang, 'a_never_cited')}: {', '.join(xr['caption_never_mentioned'])}")
        c = a["citations"]
        L += ["", f"### {t(lang, 'a_refs')}", "", f"- {t(lang, 'a_dois')}: {len(c['dois'])}"]
        v = c.get("verified")
        if v:
            L.append(f"- {t(lang, 'a_verified')}: {json.dumps({k: v[k] for k in v if k != 'results'}, ensure_ascii=False)[:600]}")
    return "\n".join(L) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Content audit of a congress abstract: promises, data density, statcheck.")
    p.add_argument("--structure", required=True)
    p.add_argument("--text", required=True, help="Cleaned text from extract_abstract.py")
    p.add_argument("--format", choices=["auto", "simple", "expanded"], default="auto")
    p.add_argument("--verify-citations", action="store_true", help="Check DOIs live against OpenAlex / doi.org (expanded only).")
    p.add_argument("--output-json", required=True)
    p.add_argument("--output-md")
    p.add_argument("--language", choices=["auto", "pt", "en", "es"], default="auto", help="Report language (auto = the abstract's language).")
    args = p.parse_args()
    structure = json.loads(Path(args.structure).read_text(encoding="utf-8"))
    lang = report_language(args.language, structure.get("language", {}).get("code"))
    text = Path(args.text).read_text(encoding="utf-8")
    fmt = structure["format"].get("effective", structure["format"]["detected"]) if args.format == "auto" else args.format
    a = audit(structure, text, fmt, verify_citations=args.verify_citations)
    Path(args.output_json).write_text(json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(to_markdown(a, lang), encoding="utf-8")
    print(json.dumps({"status": "ok", "format": fmt, "promises": a["promise_summary"], "data_level": a["data_density"]["level"],
                      "objective_conclusion_overlap": a["objective_conclusion"].get("overlap")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
