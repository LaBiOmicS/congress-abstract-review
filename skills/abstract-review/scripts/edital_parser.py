#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf>=4.0.0",
#     "pdfplumber>=0.11.0",
#     "python-docx>=1.1.0",
# ]
# ///
"""Congress call-for-papers (edital / CFP) rules: deterministic hints, validation and normalization.

Reading an edital is a language task (rules are scattered across prose, tables and annexes), so
the agent fills `edital.json` following references/edital_format.md. This script does the parts
that must be exact:

  default   write the best-practice ruleset used when there is no edital (Mode 2)
  hints     regex scan of the edital text for numeric limits (words, characters, pages, keywords,
            figures, references), each with the quoted snippet it came from
  validate  check and normalize edital.json (types, ranges, canonical section names, rubric
            weights/approval cutoff) and cross-check its limits against the hints

Exit codes: 0 ok, 1 invalid edital.json (errors printed), 2 usage / unreadable input.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import criteria as criteria_mod  # noqa: E402
from extract_abstract import SECTION_HEADINGS, read_submission  # noqa: E402
from security import sanitize_and_scan  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_RULES = TEMPLATES_DIR / "barema_default.json"

FORMATS = ("simple", "expanded")
# The plugin decides only approval; the presentation modality (oral, poster) is the committee's.
DECISIONS = ("approved", "rejected")
# Nature of a track: research reports results; innovation reports a project or product; extension
# reports an action with a community. Without a barema in the edital, each kind gets its own default.
KINDS = ("research", "innovation", "extension")
LIMIT_KEYS = ("words", "characters_with_spaces", "characters_without_spaces", "pages")
COMPONENTS = ("title", "front_matter", "body", "keywords", "references", "funding")
CANONICAL_SECTIONS = tuple(name for name, _ in SECTION_HEADINGS) + ("discussion",)
LANGUAGES = ("pt", "en", "es")


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def load_default() -> dict[str, Any]:
    return json.loads(DEFAULT_RULES.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Hints
# ---------------------------------------------------------------------------

_N = r"(\d{1,3}(?:[.,]\d{3})+|\d+)"
_RANGE = rf"(?:(?:entre|de|between|from|entre)\s+{_N}\s+(?:e|a|and|to|y)\s+)?"
_MAX_WORDS = r"(?:m[áa]ximo\s+de|no\s+m[áa]ximo|at[ée]|limite\s+de|up\s+to|maximum\s+of|max(?:imum)?\.?|no\s+more\s+than|not\s+exceed(?:ing)?|hasta|como\s+m[áa]ximo)"
_MIN_WORDS = r"(?:m[íi]nimo\s+de|no\s+m[íi]nimo|at\s+least|minimum\s+of|min(?:imum)?\.?|al\s+menos)"

HINT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("keywords", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:palavras?[-\s]chave|key\s?words?|palabras\s+clave|descritores)")),
    ("characters_with_spaces", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:caracteres|characters|caracteres)\s*\(?\s*(?:com|incluindo|including|with|con|incluyendo)\s+(?:os\s+)?(?:espa[çc]os|spaces|espacios)")),
    ("characters_without_spaces", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:caracteres|characters)\s*\(?\s*(?:sem|excluindo|excluding|without|sin)\s+(?:os\s+)?(?:espa[çc]os|spaces|espacios)")),
    ("characters", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:caracteres|characters)(?!\s*\(?\s*(?:com|sem|incluindo|excluindo|including|excluding|with|without|con|sin|incluyendo)\b)")),
    ("words", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:palavras|words|palabras)(?![-\s]*(?:chave|clave))")),
    ("pages", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:p[áa]ginas|pages|laudas)")),
    ("figures", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:figuras?|figures?|imagens|images|ilustra[çc][õo]es)")),
    ("tables", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:tabelas?|tables?|tablas?)")),
    ("references", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:refer[êe]ncias|references|referencias|cita[çc][õo]es)")),
    ("authors", re.compile(rf"(?i){_RANGE}{_N}\s*(?:\(\w+\)\s*)?(?:autores|authors|coautores|co-?authors)")),
]


def _to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    return int(re.sub(r"[.,]", "", raw))


def extract_hints(text: str) -> list[dict[str, Any]]:
    """Numeric limits stated in an edital, each with its kind, bound and quoted snippet."""
    hints: list[dict[str, Any]] = []
    taken: list[tuple[int, int]] = []
    for kind, pat in HINT_PATTERNS:
        for m in pat.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue  # a more specific pattern (e.g. "caracteres com espaços") already matched here
            low, value = _to_int(m.group(1)), _to_int(m.group(2))
            before = text[max(0, m.start() - 40): m.start()]
            if low is not None:
                bound = "range"
            elif re.search(_MIN_WORDS + r"\s*$", before, re.IGNORECASE):
                bound = "min"
            elif re.search(_MAX_WORDS + r"\s*$", before, re.IGNORECASE):
                bound = "max"
            else:
                bound = "unspecified"
            if value is None or value == 0 and kind not in ("figures", "tables", "references"):
                continue
            snippet = " ".join(text[max(0, m.start() - 80): m.end() + 60].split())
            hints.append({"kind": kind, "bound": bound, "min": low, "value": value, "snippet": snippet})
            taken.append((m.start(), m.end()))
    hints.sort(key=lambda h: (h["kind"], h["value"]))
    return hints


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_SECTION_ALIASES = [(name, re.compile(rf"(?i)^\s*(?:{alt})\s*$")) for name, alt in SECTION_HEADINGS]


def canonical_section(name: str) -> str | None:
    key = name.strip().lower().replace(" ", "_")
    if key in CANONICAL_SECTIONS:
        return key
    for canon, pat in _SECTION_ALIASES:
        if pat.match(name):
            return canon
    return None


def _num_or_none(value: Any, path: str, errors: list[str], *, integer: bool = True) -> Any:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path}: expected a number or null, got {value!r}")
        return None
    if value < 0:
        errors.append(f"{path}: must be >= 0")
    return int(value) if integer and float(value).is_integer() else value


def _range(obj: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if obj is None:
        return {"min": None, "max": None}
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        obj = {"min": None, "max": obj}
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected {{'min': .., 'max': ..}}")
        return {"min": None, "max": None}
    lo = _num_or_none(obj.get("min"), f"{path}.min", errors)
    hi = _num_or_none(obj.get("max"), f"{path}.max", errors)
    if lo is not None and hi is not None and lo > hi:
        errors.append(f"{path}: min ({lo}) > max ({hi})")
    return {"min": lo, "max": hi}


def _allowance(obj: Any, path: str, errors: list[str], *, with_min: bool = False) -> dict[str, Any]:
    obj = obj if isinstance(obj, dict) else {}
    allowed = obj.get("allowed")
    if allowed is not None and not isinstance(allowed, bool):
        errors.append(f"{path}.allowed: expected true/false/null")
        allowed = None
    out = {"allowed": allowed, "max": _num_or_none(obj.get("max"), f"{path}.max", errors)}
    if with_min:
        out["min"] = _num_or_none(obj.get("min"), f"{path}.min", errors)
    if out["allowed"] is False and out["max"]:
        errors.append(f"{path}: allowed=false but max={out['max']}")
    if out["allowed"] is None and out["max"] == 0:
        out["allowed"] = False
    return out


def normalize_format(fmt: str, spec: Any, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    p = f"formats.{fmt}"
    if not isinstance(spec, dict):
        errors.append(f"{p}: expected an object")
        spec = {}
    limits_in = spec.get("limits") or {}
    limits = {k: _range(limits_in.get(k), f"{p}.limits.{k}", errors) for k in LIMIT_KEYS}
    scope = limits_in.get("count_scope")
    if scope is None:
        if any(limits[k]["max"] or limits[k]["min"] for k in LIMIT_KEYS if k != "pages"):
            warnings.append(f"{p}.limits.count_scope not given: assuming only the body counts (title, authors, keywords and references excluded). Check the edital.")
        scope = ["body"]
    bad = [c for c in scope if c not in COMPONENTS]
    if bad:
        errors.append(f"{p}.limits.count_scope: unknown components {bad}; use {list(COMPONENTS)}")
    limits["count_scope"] = [c for c in scope if c in COMPONENTS] or ["body"]

    title_in = spec.get("title") or {}
    title = {
        "max_words": _num_or_none(title_in.get("max_words"), f"{p}.title.max_words", errors),
        "max_characters": _num_or_none(title_in.get("max_characters"), f"{p}.title.max_characters", errors),
    }

    def sections(key: str) -> list[str]:
        out = []
        for name in spec.get(key) or []:
            canon = canonical_section(str(name))
            if canon is None:
                errors.append(f"{p}.{key}: unknown section {name!r}; use one of {list(CANONICAL_SECTIONS)}")
            elif canon not in out:
                out.append(canon)
        return out

    return {
        "limits": limits,
        "title": title,
        "required_sections": sections("required_sections"),
        "forbidden_sections": sections("forbidden_sections"),
        "figures": _allowance(spec.get("figures"), f"{p}.figures", errors),
        "tables": _allowance(spec.get("tables"), f"{p}.tables", errors),
        "references": _allowance(spec.get("references"), f"{p}.references", errors, with_min=True),
        "keywords": _range(spec.get("keywords"), f"{p}.keywords", errors),
        "max_authors": _num_or_none(spec.get("max_authors"), f"{p}.max_authors", errors),
    }


def normalize_rubric(rubric: Any, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    if not rubric:
        warnings.append("rubric not given: the edital has no barema, so the default best-practice barema is used. Say so in the evaluation sheet.")
        rubric = copy.deepcopy(load_default()["rubric"])
        rubric["source"] = "default"
        # An edital without barema has no minimum score either: the default one would be invented.
        rubric.pop("approval_cutoff", None)
        rubric.pop("approval_min_scores", None)
    out: dict[str, Any] = {"source": rubric.get("source", "edital"), "kind": rubric.get("kind") if rubric.get("kind") in KINDS else None}
    scale = rubric.get("scale") or {"min": 0, "max": 10}
    lo, hi = scale.get("min", 0), scale.get("max", 10)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lo, hi)) or lo >= hi:
        errors.append(f"rubric.scale: need numeric min < max, got {scale}")
        lo, hi = 0, 10
    out["scale"] = {"min": lo, "max": hi}
    agg = rubric.get("aggregation", "weighted_mean")
    if agg not in ("weighted_mean", "sum"):
        errors.append(f"rubric.aggregation: {agg!r} must be 'weighted_mean' or 'sum'")
        agg = "weighted_mean"
    out["aggregation"] = agg

    criteria, seen = [], set()
    for i, c in enumerate(rubric.get("criteria") or []):
        cid = str(c.get("id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", cid):
            errors.append(f"rubric.criteria[{i}].id: {cid!r} must be snake_case")
            continue
        if cid in seen:
            errors.append(f"rubric.criteria: duplicate id {cid!r}")
            continue
        seen.add(cid)
        weight = c.get("weight", 1.0)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            errors.append(f"rubric.criteria[{cid}].weight must be > 0")
            weight = 1.0
        cmax = c.get("max_score")
        if cmax is not None and (isinstance(cmax, bool) or not isinstance(cmax, (int, float)) or cmax <= lo):
            errors.append(f"rubric.criteria[{cid}].max_score must be a number > scale.min")
            cmax = None
        criteria.append(criteria_mod.resolve(c, {
            "id": cid,
            "name": str(c.get("name") or cid),
            "description": str(c.get("description") or ""),
            "weight": float(weight),
            "max_score": cmax if cmax is not None else hi,
        }, lo, errors, warnings))
    if not criteria:
        errors.append("rubric.criteria: at least one criterion is required")
    out["criteria"] = criteria
    if out["source"] != "default":
        for c in criteria:  # the edital's criterion names are the event's own: never translated
            c["name_i18n"] = {}
    out["apply_caps"] = rubric.get("apply_caps", True) is not False
    generic = [c["id"] for c in criteria if c["anchors_source"] == "generic"]
    if generic and out["source"] != "default":
        warnings.append(f"rubric.criteria {generic}: no anchors in the edital and no matching global category; generic score levels are used. "
                        f"Add \"based_on\": one of {list(criteria_mod.catalog()['categories'])} when the meaning matches, or copy the edital's levels into \"anchors\".")

    # Score range of the aggregate, used to check cutoffs.
    if agg == "sum":
        top = sum(c["max_score"] for c in criteria) if criteria else hi
    else:
        top = hi
    out["total_range"] = {"min": lo if agg == "weighted_mean" else lo * len(criteria), "max": top}

    # The plugin decides approval only; the presentation modality (oral, poster) is the committee's.
    cutoff = rubric.get("approval_cutoff")
    legacy = rubric.get("cutoffs")
    if cutoff is None and isinstance(legacy, dict) and legacy:
        nums = [v for v in legacy.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums:
            cutoff = min(nums)
            warnings.append(f"rubric.cutoffs per modality {legacy} replaced by approval_cutoff = {cutoff:g} (the lowest one): "
                            "the plugin decides approval only, the presentation modality is the committee's.")
    if cutoff is not None and (isinstance(cutoff, bool) or not isinstance(cutoff, (int, float)) or not (out["total_range"]["min"] <= cutoff <= top)):
        errors.append(f"rubric.approval_cutoff: {cutoff!r} outside the score range {out['total_range']}")
        cutoff = None
    if cutoff is None:
        warnings.append("rubric.approval_cutoff not given: the committee decides on approval; the sheet ranks and shows the evaluators' recommendation.")
    out["approval_cutoff"] = float(cutoff) if cutoff is not None else None

    if rubric.get("oral_min_scores"):
        warnings.append("rubric.oral_min_scores ignored: the plugin does not choose the presentation modality. Use approval_min_scores for minimums the edital sets for approval.")
    mins = {}
    for cid, val in (rubric.get("approval_min_scores") or {}).items():
        if cid not in seen:
            errors.append(f"rubric.approval_min_scores: unknown criterion {cid!r}")
        elif isinstance(val, bool) or not isinstance(val, (int, float)):
            errors.append(f"rubric.approval_min_scores.{cid}: expected a number")
        else:
            mins[cid] = float(val)
    out["approval_min_scores"] = mins
    tb = [t for t in rubric.get("tie_breakers") or [] if t in seen]
    if len(tb) != len(rubric.get("tie_breakers") or []):
        errors.append("rubric.tie_breakers: every entry must be a criterion id")
    out["tie_breakers"] = tb
    return out


def validate_edital(data: Any) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return (normalized rules, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {}, ["edital.json must be a JSON object"], []
    event = data.get("event") or {}
    source = event.get("source") or "edital"
    enforcement = data.get("enforcement") or ("advisory" if source == "default" else "strict")
    if enforcement not in ("strict", "advisory"):
        errors.append("enforcement must be 'strict' or 'advisory'")
    if not event.get("name"):
        warnings.append("event.name is empty")

    formats_in = data.get("formats") or {}
    unknown = [k for k in formats_in if k not in FORMATS]
    if unknown:
        errors.append(f"formats: unknown keys {unknown}; use 'simple' and/or 'expanded'")
    formats = {k: normalize_format(k, v, errors, warnings) for k, v in formats_in.items() if k in FORMATS}
    if not formats:
        errors.append("formats: describe at least one of 'simple' / 'expanded'")

    langs = [str(x).lower()[:2] for x in data.get("languages") or []]
    bad_langs = [x for x in langs if x not in LANGUAGES]
    if bad_langs:
        warnings.append(f"languages: {bad_langs} have no language detector; only pt/en/es are checked automatically")

    if data.get("modalities"):
        warnings.append("modalities ignored: the plugin decides approval only (approved / rejected); the presentation modality is the committee's, "
                        "and posters are evaluated at the event.")

    tracks, track_rubrics_in = [], {}
    for i, t in enumerate(data.get("tracks") or []):
        if isinstance(t, str):
            t = {"code": slugify(t), "name": t}
        if not isinstance(t, dict) or not t.get("name"):
            errors.append(f"tracks[{i}]: need at least a name")
            continue
        kind = str(t.get("kind") or "research").strip().lower()
        if kind not in KINDS:
            errors.append(f"tracks[{i}].kind: {kind!r} must be one of {list(KINDS)}")
            kind = "research"
        code = str(t.get("code") or f"t{i + 1}")
        tracks.append({"code": code, "name": str(t["name"]), "description": str(t.get("description") or ""), "kind": kind})
        if t.get("rubric"):
            track_rubrics_in[code] = t["rubric"]

    provenance = data.get("provenance") or {}
    if enforcement == "strict" and not provenance:
        warnings.append("provenance is empty: quote the edital passage behind each rule so the committee can check it")

    normalized = {
        "event": {"name": event.get("name") or "", "year": event.get("year"), "url": event.get("url"), "source": source},
        "enforcement": enforcement,
        "languages": [x for x in langs if x in LANGUAGES] + [x for x in langs if x not in LANGUAGES],
        "anonymized": bool(data.get("anonymized", False)),
        "formats": formats,
        "tracks": tracks,
        "decisions": list(DECISIONS),
        "rubric": normalize_rubric(data.get("rubric"), errors, warnings),
        "notes": str(data.get("notes") or ""),
        "provenance": provenance,
    }
    attach_track_rubrics(normalized, data, track_rubrics_in, errors, warnings)
    return normalized, errors, warnings


def attach_track_rubrics(rules: dict[str, Any], data: dict[str, Any], track_rubrics_in: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    """Pick the barema of every track and of every kind.

    Precedence: the track's own barema (`tracks[].rubric`) → the edital's barema (`rubric`) for every
    track → without a barema in the edital, the default barema of the track's kind (research,
    innovation, extension). `rules["rubric"]` stays the main barema; `rules["rubrics"]` holds the others."""
    main = rules["rubric"]
    rubrics: dict[str, dict[str, Any]] = {}
    if main["source"] == "default":
        main["kind"] = "research"
        for kind, rub in (load_default().get("rubrics_by_kind") or {}).items():
            sub_err: list[str] = []
            r = normalize_rubric({**rub, "approval_cutoff": main.get("approval_cutoff")}, sub_err, [])
            r["approval_min_scores"] = {}
            errors.extend(f"default barema '{kind}': {e}" for e in sub_err)
            rubrics[kind] = r
    for code, rub_in in track_rubrics_in.items():
        sub_err = []
        rub_in = {**rub_in, "source": "edital"}
        if "approval_cutoff" not in rub_in and main.get("approval_cutoff") is not None:
            rub_in["approval_cutoff"] = main["approval_cutoff"]
        rubrics[f"track:{code}"] = normalize_rubric(rub_in, sub_err, [])
        errors.extend(f"tracks[{code}].rubric: {e}" for e in sub_err)
    for tr in rules["tracks"]:
        if f"track:{tr['code']}" in rubrics:
            tr["rubric_key"] = f"track:{tr['code']}"
        elif tr["kind"] in rubrics:
            tr["rubric_key"] = tr["kind"]
        else:
            tr["rubric_key"] = "main"
    kinds = {tr["kind"] for tr in rules["tracks"]}
    if main["source"] != "default" and kinds - {"research"} and not track_rubrics_in:
        warnings.append(f"tracks of kinds {sorted(kinds)} share the edital's barema; give a track its own `rubric` if the edital scores it differently.")
    rules["rubrics"] = rubrics


def rubric_key(rules: dict[str, Any], track: str | None = None, kind: str | None = None) -> str:
    """Barema of a submission: its declared track's, else its declared kind's, else the main one."""
    for tr in rules.get("tracks", []):
        if track and tr["code"] == track:
            return tr.get("rubric_key", "main")
    if kind and kind in (rules.get("rubrics") or {}):
        return kind
    return "main"


def rubric_of(rules: dict[str, Any], key: str | None) -> dict[str, Any]:
    return (rules.get("rubrics") or {}).get(key or "main") or rules["rubric"]


_HINT_TO_LIMIT = {
    "words": [("limits", "words")],
    "characters_with_spaces": [("limits", "characters_with_spaces")],
    "characters_without_spaces": [("limits", "characters_without_spaces")],
    "characters": [("limits", "characters_with_spaces"), ("limits", "characters_without_spaces")],
    "pages": [("limits", "pages")],
    "keywords": [("keywords",)],
    "figures": [("figures",)],
    "tables": [("tables",)],
    "references": [("references",)],
}


def cross_check(rules: dict[str, Any], hints: list[dict[str, Any]]) -> list[str]:
    """Warn for every number the edital states that edital.json does not carry anywhere."""
    out = []
    for h in hints:
        paths = _HINT_TO_LIMIT.get(h["kind"])
        if not paths:
            if h["kind"] == "authors" and not any(f.get("max_authors") == h["value"] for f in rules.get("formats", {}).values()):
                out.append(f"edital mentions {h['value']} authors but no format has max_authors={h['value']}: \"{h['snippet']}\"")
            continue
        values: set[int] = set()
        for fmt in rules.get("formats", {}).values():
            for path in paths:
                node: Any = fmt
                for key in path:
                    node = node.get(key, {}) if isinstance(node, dict) else {}
                if isinstance(node, dict):
                    values.update(v for v in (node.get("min"), node.get("max")) if v is not None)
        wanted = {h["value"]} | ({h["min"]} if h["min"] is not None else set())
        if not wanted & values:
            out.append(f"edital mentions {h['kind']}={h['value']} ({h['bound']}) but edital.json has no such limit: \"{h['snippet']}\"")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_json(path: str, data: Any) -> None:
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Congress edital / CFP rules: default ruleset, hints, validation.")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("default", help="Write the best-practice ruleset (no edital).")
    d.add_argument("--output", required=True)
    h = sub.add_parser("hints", help="Extract numeric limits with quoted snippets from an edital file.")
    h.add_argument("edital_file", help="Edital as .pdf, .docx, .md, .txt, .html …")
    h.add_argument("--output-text", required=True, help="Where to write the edital's cleaned text (for the agent to read).")
    h.add_argument("--output-json", required=True)
    v = sub.add_parser("validate", help="Validate and normalize an edital.json written by the agent.")
    v.add_argument("--edital", required=True, help="edital.json to validate.")
    v.add_argument("--output", required=True, help="Where to write the normalized rules (rules.json).")
    v.add_argument("--hints", help="hints.json from the `hints` command, for cross-checking.")
    args = p.parse_args()

    if args.cmd == "default":
        rules, errors, warnings = validate_edital(load_default())
        assert not errors, errors
        _write_json(args.output, rules)
        print(json.dumps({"status": "ok", "source": "default", "warnings": warnings}, ensure_ascii=False))
        return 0

    if args.cmd == "hints":
        try:
            raw, _meta, hidden = read_submission(Path(args.edital_file).resolve())
        except (ValueError, RuntimeError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        text, scan = sanitize_and_scan(raw)
        hints = extract_hints(text)
        Path(args.output_text).resolve().parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_text).resolve().write_text(text, encoding="utf-8")
        _write_json(args.output_json, {"hints": hints, "security_scan": scan, "hidden_findings": len(hidden)})
        print(json.dumps({"status": "ok", "hints": len(hints), "kinds": sorted({x["kind"] for x in hints}), "security_is_clean": scan["is_clean"]}, ensure_ascii=False))
        return 0

    try:
        data = json.loads(Path(args.edital).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: cannot read {args.edital}: {e}", file=sys.stderr)
        return 2
    rules, errors, warnings = validate_edital(data)
    if args.hints:
        hints = json.loads(Path(args.hints).read_text(encoding="utf-8")).get("hints", [])
        warnings += cross_check(rules, hints)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors, "warnings": warnings}, indent=2, ensure_ascii=False))
        return 1
    rules["validation_warnings"] = warnings
    _write_json(args.output, rules)
    print(json.dumps({"status": "ok", "formats": list(rules["formats"]), "criteria": len(rules["rubric"]["criteria"]), "warnings": warnings}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
