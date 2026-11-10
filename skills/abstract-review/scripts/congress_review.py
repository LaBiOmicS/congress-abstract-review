#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf>=4.0.0",
#     "pdfplumber>=0.11.0",
#     "python-docx>=1.1.0",
#     "reportlab>=4.0.0",
#     "openpyxl>=3.1.0",
# ]
# ///
"""Congress abstract review pipeline, for one submission or a whole folder.

  prepare  extract + compliance metrics + content audit for every submission, then plan the first
           reviewer tasks (deterministic, no model calls)
  next     re-plan: list the reviewer / synthesis tasks still missing, given the reviews already
           written (auto panel: escalates borderline single-evaluator results to the full panel)
  run      execute the pending tasks headless (`claude -p`, `agy -p`, `gemini -p`), repeating
           `next` until nothing is pending (or use native subagents with the manifest instead)
  compile  aggregate scores, apply the approval cutoff, write each submission's evaluation sheet
           (MD + PDF), feedback to authors and summary JSON, plus the committee spreadsheet
           (CSV + XLSX) and report

Panels:
  full  alfa (compliance & form) + beta (data & rigor) + gamma (track & impact) + committee synthesis
  lite  omega, one evaluator with the combined checklist
  auto  omega first; the full panel only for borderline, low-confidence, flagged or inconsistent cases
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import abstract_metrics  # noqa: E402
import area_profiles  # noqa: E402
import content_audit  # noqa: E402
import criteria  # noqa: E402
import report  # noqa: E402
import scoring  # noqa: E402
from edital_parser import KINDS, rubric_key, rubric_of  # noqa: E402
from extract_abstract import PANDOC_FORMATS, PLAIN_TEXT_FORMATS, extract  # noqa: E402
from i18n import batch_language, report_language, t  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS = SKILL_DIR / "prompts"
SUPPORTED_SUFFIXES = {".pdf", ".docx"} | PLAIN_TEXT_FORMATS | PANDOC_FORMATS
PANEL = {
    "alfa": ("Compliance & form referee", "lens_compliance.md"),
    "beta": ("Data & rigor referee", "lens_data_rigor.md"),
    "gamma": ("Track & impact referee", "lens_track_impact.md"),
}
SINGLE = {"omega": ("Single evaluator (full committee checklist)", "lens_combined.md")}
LANG_NAME = {"pt": "Brazilian Portuguese", "en": "English", "es": "Spanish"}
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
KIND_NOTE = {
    "research": "",
    "innovation": (
        "**This is an innovation track.** The abstract reports a project or product (software, device, process, venture), not a research study. "
        "Judge the problem it addresses, what was actually built and at which stage (idea, specification, prototype, tested product), its advantage "
        "over what exists, its feasibility and its expected impact. Do not demand sample sizes, statistical tests or a research design; concrete "
        "deliverables count as results. Numbers that describe the deliverable (requirements specified, users tested, performance measured) still "
        "strengthen it, and claims beyond the declared stage are still overreach. Read your lens with this in mind."
    ),
    "extension": (
        "**This is an extension track.** The abstract reports an action carried out with a community, not a research study. Judge the community "
        "and its demand, the action (where, when, with whom, how), its outcomes for the community and for the students' training, and the "
        "engagement with the community. Qualitative evidence (testimonies, participants' assessment, people reached) counts as results; do not "
        "demand statistical tests or a research design. Outcomes only promised for the event are still not outcomes. Read your lens with this in mind."
    ),
}


def track_kind(rules: dict[str, Any], track: str | None, kind: str | None) -> str:
    for tr in rules.get("tracks", []):
        if track and tr["code"] == track:
            return tr.get("kind", "research")
    return kind if kind in KINDS else "research"


def rules_for(rules: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """The rules as one submission sees them: the barema of its track (or kind) as `rubric`, with the
    levels of methods/results matching its research approach (research tracks only)."""
    kind = info.get("track_kind", "research")
    profile = info.get("profile") or {}
    approach = profile.get("approach") if kind == "research" else None
    rubric = criteria.adapt_to_approach(rubric_of(rules, info.get("rubric_key")), approach)
    return {**rules, "rubric": rubric, "track_kind": kind, "approach": approach, "profile": profile}


def profile_note(rules: dict[str, Any]) -> str:
    """Area, approach and ethics guidance for the evaluators."""
    p = rules.get("profile") or {}
    if not p:
        return ""
    lines = []
    if p.get("area"):
        lines.append(f"**Area: {p['area']}.** {area_profiles.AREAS[p['area']]['guidance']}")
    if rules.get("approach"):
        lines.append(f"**Research approach: {p['approach']}.** {area_profiles.APPROACH_GUIDANCE[p['approach']]}")
    if p.get("low_confidence"):
        lines.append(f"(Automatic classification with low confidence for: {', '.join(p['low_confidence'])}. If the abstract shows otherwise, "
                     "judge it by what it actually is and say so in the confidential comments.)")
    if p.get("ethics_check"):
        lines.append("**Ethics:** the work involves people or animals and the abstract does not mention an ethics approval (CEP/CAAE, CEUA). "
                     "Many events require it; point it out to the authors and the committee. Do not lower scientific scores for it alone.")
    return "\n\n".join(lines)


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60] or "submission"


def render(template: str, values: dict[str, str]) -> str:
    """Single-pass placeholder rendering: substituted values are never re-scanned for placeholders."""
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def list_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith((".", "~$")))
    return files


def load_submissions_csv(path: Path | None) -> dict[str, dict[str, str]]:
    """Optional metadata: columns file (required), id, track."""
    if not path:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {row["file"].strip(): {k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh) if row.get("file")}


def prepare_submission(src: Path, sub_dir: Path, rules: dict[str, Any], fmt: str, meta: dict[str, str], panel: str, language: str = "auto",
                       track: str | None = None, kind: str | None = None, area: str | None = None, approach: str | None = None) -> dict[str, Any]:
    text, structure = extract(src, fmt=fmt)
    lang = report_language(language, structure["language"]["code"])
    (sub_dir / "abstract_text.txt").write_text(text, encoding="utf-8")
    write_json(sub_dir / "structure.json", structure)
    effective = structure["format"]["effective"]
    m = abstract_metrics.compute_metrics(structure, rules, effective, lang)
    write_json(sub_dir / "metrics.json", m)
    (sub_dir / "metrics.md").write_text(abstract_metrics.to_markdown(m), encoding="utf-8")
    a = content_audit.audit(structure, text, effective)
    write_json(sub_dir / "content_audit.json", a)
    (sub_dir / "content_audit.md").write_text(content_audit.to_markdown(a, lang), encoding="utf-8")
    info = {
        "id": meta.get("id") or sub_dir.name,
        "file": src.name,
        "source_path": str(src),
        "dir": sub_dir.name,
        "title": structure["title"],
        "format": effective,
        "format_needs_confirmation": structure["format"].get("needs_confirmation", False),
        "declared_track": meta.get("track") or track or "",
        "declared_kind": meta.get("kind") or kind or "",
        "language": structure["language"]["code"],
        "report_lang": lang,
        "panel": panel,
    }
    info["rubric_key"] = rubric_key(rules, info["declared_track"] or None, info["declared_kind"] or None)
    info["track_kind"] = track_kind(rules, info["declared_track"] or None, info["declared_kind"] or None)
    body = "\n".join(s.get("text", "") for s in structure.get("sections", []))
    info["profile"] = area_profiles.classify(structure.get("title", ""), body, "; ".join(structure.get("keywords") or []),
                                             area=meta.get("area") or area or None, approach=meta.get("approach") or approach or None)
    info["fingerprint"] = fingerprint(text, rules, info)
    info["superseded"] = supersede_stale(sub_dir, info["fingerprint"])
    write_json(sub_dir / "submission.json", info)
    return info


def fingerprint(text: str, rules: dict[str, Any], info: dict[str, Any]) -> str:
    """What the evaluations depend on: the abstract, the rules and barema it is judged by, its format and profile."""
    r = rules_for(rules, info)
    basis = {"text": text, "rubric": r["rubric"], "event": rules.get("event"), "limits": rules.get("limits"), "sections": rules.get("sections"),
             "format": info["format"], "kind": r["track_kind"], "profile": [info["profile"]["area"], info["profile"]["approach"]], "lang": info["report_lang"]}
    return hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def supersede_stale(sub_dir: Path, fp: str) -> int:
    """Evaluations written for another version of the abstract or the rules no longer apply: move them aside."""
    prev = sub_dir / "submission.json"
    old = [p for p in sub_dir.glob("review_*.md")] + [p for p in (sub_dir / "committee_synthesis.md",) if p.exists()]
    if not old or (prev.exists() and read_json(prev).get("fingerprint") == fp):
        return 0
    dest = sub_dir / "superseded" / time.strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for p in old:
        shutil.move(str(p), dest / p.name)
    return len(old)


def cmd_prepare(args: argparse.Namespace) -> int:
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rules = read_json(Path(args.rules))
    inputs = list_inputs(Path(args.input).resolve())
    if not inputs:
        print(f"Error: no supported submission files in {args.input}", file=sys.stderr)
        return 2
    csv_meta = load_submissions_csv(Path(args.submissions_csv) if args.submissions_csv else None)
    panel = args.panel if args.panel != "default" else ("auto" if len(inputs) > 1 else "full")
    audience = args.audience if args.audience != "default" else ("author" if rules.get("enforcement") == "advisory" else "committee")
    config = {
        "rules": str(Path(args.rules).resolve()),
        "panel": panel,
        "language": args.language,
        "blind": not args.no_blind,
        "format": args.format,
        "audience": audience,
    }
    write_json(out / "batch_config.json", config)
    write_json(out / "rules.json", rules)

    used: set[str] = set()
    submissions, failures = [], []
    for src in inputs:
        slug = slugify(src.stem)
        while slug in used:
            slug += "-x"
        used.add(slug)
        sub_dir = out / slug
        sub_dir.mkdir(parents=True, exist_ok=True)
        try:
            submissions.append(prepare_submission(src, sub_dir, rules, args.format, csv_meta.get(src.name, {}), panel, args.language,
                                                  getattr(args, "track", None), getattr(args, "kind", None),
                                                  getattr(args, "area", None), getattr(args, "approach", None)))
        except Exception as e:  # noqa: BLE001 - one unreadable file must not stop the batch
            failures.append({"file": src.name, "error": str(e)[:300]})
            print(f"[prepare] {src.name}: FAILED — {e}", file=sys.stderr)
    write_json(out / "batch_submissions.json", {"submissions": submissions, "failures": failures})
    manifest = plan(out)
    confirm = [s["id"] for s in submissions if s["format_needs_confirmation"]]
    # Tracks scored with different baremas: a submission without a declared track got the main one.
    keys = {tr.get("rubric_key", "main") for tr in rules.get("tracks", [])}
    track_confirm = [s["id"] for s in submissions if len(keys) > 1 and not s["declared_track"] and not s["declared_kind"]]
    print(json.dumps({
        "status": "ok",
        "submissions": len(submissions),
        "failures": len(failures),
        "panel": panel,
        "audience": audience,
        "report_languages": {lg: sum(1 for s in submissions if s["report_lang"] == lg) for lg in ("pt", "en", "es")},
        "formats": {f: sum(1 for s in submissions if s["format"] == f) for f in ("simple", "expanded")},
        "format_needs_confirmation": confirm,
        "track_needs_confirmation": track_confirm,
        "baremas": {s["id"]: f"{s['rubric_key']} ({s['track_kind']})" for s in submissions},
        "profiles": {s["id"]: f"{s['profile']['area'] or 'undetermined'} ({s['profile']['area_confidence']:.2f}) · {s['profile']['approach']} ({s['profile']['approach_confidence']:.2f})"
                     + (" · ethics_check" if s["profile"]["ethics_check"] else "") for s in submissions},
        # Low-confidence area or approach: confirm from the abstract and re-run with --area/--approach (or CSV columns).
        "profile_needs_confirmation": {s["id"]: s["profile"]["low_confidence"] for s in submissions if s["profile"]["low_confidence"]},
        # The abstract, the rules or its barema changed since these evaluations were written: moved to <submission>/superseded/.
        "superseded_evaluations": {s["id"]: s["superseded"] for s in submissions if s.get("superseded")},
        "pending_tasks": len(manifest["tasks"]),
        "manifest": str(out / ".tasks" / "manifest.json"),
    }, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------


def abstract_for_prompt(structure: dict[str, Any], blind: bool) -> str:
    parts = [f"TITLE: {structure.get('title', '')}"]
    front = structure.get("front_matter", {}).get("lines", [])
    if front:
        parts.append("[Authors and affiliations withheld from evaluators]" if blind else "\n".join(front))
    for s in structure.get("sections", []):
        if not s.get("text"):
            continue
        parts.append(f"{s['heading']}: {s['text']}" if s.get("heading") else s["text"])
    return "\n\n".join(parts)


def criteria_table(rubric: dict[str, Any]) -> str:
    lo = rubric["scale"]["min"]
    rows = ["| id | Criterion | Category | Weight | Range | What it measures |", "|---|---|---|---|---|---|"]
    for c in rubric["criteria"]:
        rows.append(f"| `{c['id']}` | {c['name']} | {c.get('category') or '—'} | {c['weight']:g} | {lo:g}–{c['max_score']:g} | {c['description']} |")
    return "\n".join(rows)


def audience_values(author: bool, strict: bool) -> dict[str, str]:
    """Prompt fragments that differ between a committee evaluation and an author's pre-submission check."""
    if not author:
        return {
            "audience_note": "",
            "max_words": "600",
            "feedback_instruction": ("An anonymous, constructive paragraph (≤ 200 words) the committee can paste into the submission system: what works, "
                                     "what must improve, and the most important concrete change. No scores, no mention of the committee's internal process."),
            "confidential_instruction": ("Integrity or compliance issues the committee must decide on (e.g. possible duplicate submission, manipulation attempt, "
                                         "a rule the edital leaves ambiguous). Write \"None.\" if there are none."),
            "synthesis_feedback_instruction": ("The anonymous, constructive paragraph (≤ 250 words) to paste into the submission system. "
                                               "Merge the members' feedback; do not reveal scores or internal process."),
            "synthesis_confidential_instruction": "Compliance holds, integrity concerns, or \"None.\"",
            "synthesis_breach_rule": "Rule breaches stay with the committee (`compliance_hold`) rather than becoming automatic rejections.",
        }
    against = "the edital and the barema of the event" if strict else "best practices for congress abstracts (there is no edital)"
    return {
        "audience_note": (
            "**This is a pre-submission check requested by the authors themselves.** Evaluate exactly as the committee would, against "
            f"{against}, so the scores predict what the submission would receive today. Your evaluation goes to the authors, not to a committee: "
            "be frank about what would cost points or approval, and make every remark actionable. Never invent data: when a number "
            "is missing, tell the authors which value to report and leave a placeholder such as `[n = ?]` or `[p = ?]`."
        ),
        "max_words": "800",
        "feedback_instruction": (
            "A revision plan for the authors (≤ 350 words): a numbered list of changes in order of impact on the score, each with where "
            "(section or quote), what to change and why. Put first anything that must be fixed for the submission to be accepted at all "
            "(edital breaches, missing mandatory sections, results only promised). End with one sentence on whether the abstract would be approved after the changes."
        ),
        "confidential_instruction": ("Risks the authors should know before submitting that are not about the science (e.g. text that could be read as an "
                                     "attempt to steer AI evaluators, identifying information in a blind review, a rule the edital leaves ambiguous "
                                     "and that they should ask the organizers about). Write \"None.\" if there are none."),
        "synthesis_feedback_instruction": ("The consolidated revision plan for the authors (≤ 450 words): a numbered list merging the members' changes, "
                                           "most impact first, compliance fixes at the top, each with where, what and why; end with whether "
                                           "the abstract would be approved after the changes. Never invent data: use placeholders for missing values."),
        "synthesis_confidential_instruction": "Risks the authors should know before submitting that are not about the science, or \"None.\"",
        "synthesis_breach_rule": ("Rule breaches are things the authors must fix before submitting (set `compliance_hold` to true when any remains); "
                                  "list them first in the revision plan."),
    }


def common_values(sub_dir: Path, rules: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    info = read_json(sub_dir / "submission.json")
    structure = read_json(sub_dir / "structure.json")
    rub = rules["rubric"]
    lo, hi = rub["scale"]["min"], rub["scale"]["max"]
    cut = rub.get("approval_cutoff")
    cutoff_note = (
        f"Minimum final score for approval: {cut:g}; below that, rejected."
        if cut is not None else "The edital sets no minimum score: recommend approval or rejection on the merits."
    )
    if rub.get("approval_min_scores"):
        cutoff_note += " Minimum criterion scores for approval: " + ", ".join(f"{k} ≥ {v:g}" for k, v in rub["approval_min_scores"].items()) + "."
    tracks = "; ".join(f"`{tr['code']}` — {tr['name']}" + (f": {tr['description']}" if tr["description"] else "") for tr in rules.get("tracks", [])) or "none (the event has no thematic tracks)"
    lang = info.get("report_lang") or report_language(config.get("language"), info.get("language"))
    author = config.get("audience") == "author"
    strict = rules["enforcement"] == "strict"
    if strict and author:
        enforcement_note = ("The edital is binding and the authors have not submitted yet: every breach must be fixed before submission, because many committees "
                            "return or reject non-compliant files without reading them. For each one, say exactly what to change (which words to cut, which section to add).")
    elif strict:
        enforcement_note = ("The edital is the normative ground truth: a breach is a compliance problem whose seriousness you assess for the committee; "
                            "never reject on a technicality the committee would usually waive.")
    else:
        enforcement_note = ("There is no edital: limits and sections are best-practice references, useful advice for the authors, "
                            "and never grounds for rejection on their own.")
    return {
        **audience_values(author, strict),
        "event_name": rules["event"]["name"] or "the congress",
        "format_label": "expanded abstract" if info["format"] == "expanded" else "abstract",
        "enforcement_note": enforcement_note,
        "output_language": LANG_NAME[lang],
        "rubric_source": "barema from the edital" if rub.get("source") != "default" else "default best-practice barema",
        "scale_min": f"{lo:g}", "scale_max": f"{hi:g}", "scale_mid": f"{(lo + hi) / 2:g}",
        "criteria_table": criteria_table(rub),
        "anchors_md": criteria.anchors_markdown(rub, "en"),
        "indicators_md": criteria.indicators_markdown(rub, read_json(sub_dir / "metrics.json"), read_json(sub_dir / "content_audit.json")),
        "decisions": ", ".join(rules["decisions"]),
        "cutoff_note": cutoff_note,
        "tracks": tracks,
        "declared_track": info.get("declared_track") or "not stated",
        "track_kind_note": KIND_NOTE.get(rules.get("track_kind", "research"), ""),
        "profile_note": profile_note(rules),
        "languages": ", ".join(rules.get("languages") or []) or "not restricted",
        "metrics_md": (sub_dir / "metrics.md").read_text(encoding="utf-8"),
        "content_md": (sub_dir / "content_audit.md").read_text(encoding="utf-8"),
        "abstract_text": abstract_for_prompt(structure, config.get("blind", True)),
    }


def reviewer_prompt(codename: str, role: tuple[str, str], values: dict[str, str], rules: dict[str, Any]) -> str:
    skeleton = {
        "codename": codename,
        "scores": {c["id"]: 0 for c in rules["rubric"]["criteria"]},
        "decision": "approved",
        "track": (values["declared_track"] if values.get("declared_track") in {tr["code"] for tr in rules.get("tracks", [])}
                  else (rules["tracks"][0]["code"] if rules.get("tracks") else None)),
        "track_fit": "good",
        "confidence": "medium",
        "blocking_issues": [],
    }
    lens = (PROMPTS / role[1]).read_text(encoding="utf-8")
    return render((PROMPTS / "reviewer_base.md").read_text(encoding="utf-8"), {
        **values, "codename": codename, "role_name": role[0], "lens": lens, "json_skeleton": json.dumps(skeleton, ensure_ascii=False),
    })


def synthesis_prompt(sub_dir: Path, values: dict[str, str], rules: dict[str, Any], provisional: dict[str, Any]) -> str:
    reviews = []
    for code in PANEL:
        reviews.append(f"### Member {code} ({PANEL[code][0]})\n\n" + (sub_dir / f"review_{code}.md").read_text(encoding="utf-8"))
    prov = [f"Provisional committee score: **{'—' if provisional['total'] is None else format(provisional['total'], '.2f')}** → **{provisional['decision'] or 'committee decides (no minimum score)'}**"]
    prov += [f"- {r}" for r in provisional["reasons"]]
    prov += [f"- cap applied by code: {k['criterion']} {k['from']:g} → {k['to']:g} ({criteria.CAP_WHY_EN[k['when']]})" for k in provisional.get("caps", [])]
    prov.append("Per-criterion medians: " + ", ".join(f"{k} = {v:g}" for k, v in provisional["scores"].items()))
    span = rules["rubric"]["scale"]["max"] - rules["rubric"]["scale"]["min"]
    return render((PROMPTS / "committee_synthesis.md").read_text(encoding="utf-8"), {
        **values, "provisional_md": "\n".join(prov), "reviews": "\n\n".join(reviews), "disagreement": f"{0.25 * span:g}",
    })


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------


def load_review(sub_dir: Path, code: str, rules: dict[str, Any]) -> dict[str, Any] | None:
    path = sub_dir / f"review_{code}.md"
    if not path.exists():
        return None
    r = scoring.parse_review(path.read_text(encoding="utf-8"), rules["rubric"], rules["decisions"], [tr["code"] for tr in rules.get("tracks", [])])
    r["total"] = scoring.total_score(r["scores"], rules["rubric"])
    return r


def submission_state(sub_dir: Path, rules: dict[str, Any]) -> dict[str, Any]:
    info = read_json(sub_dir / "submission.json")
    rules = rules_for(rules, info)
    metrics = read_json(sub_dir / "metrics.json")
    content = read_json(sub_dir / "content_audit.json")
    security = read_json(sub_dir / "structure.json").get("security_scan", {})
    panel = info["panel"]
    need: list[str] = []
    reviews: dict[str, dict[str, Any]] = {}
    escalation: list[str] = []

    if panel in ("lite", "auto"):
        omega = load_review(sub_dir, "omega", rules)
        if omega is not None:
            reviews["omega"] = omega
        if not omega or not omega["valid"]:
            need.append("omega")
        elif panel == "auto":
            lang = info.get("report_lang", "pt")
            capped, _ = criteria.apply_caps(omega["scores"], rules["rubric"], criteria.signals(metrics, content, rules.get("approach")), lang)
            dec = scoring.decide(scoring.total_score(capped, rules["rubric"]), capped, rules, metrics, content, security, lang=lang)
            escalation = scoring.escalation_reasons(omega, dec, rules, content, lang)
    full = panel == "full" or bool(escalation)
    synthesis = None
    if full:
        for code in PANEL:
            r = load_review(sub_dir, code, rules)
            if r is not None:
                reviews[code] = r
            if not r or not r["valid"]:
                need.append(code)
        if not need:
            path = sub_dir / "committee_synthesis.md"
            if path.exists():
                synthesis = scoring.parse_synthesis(path.read_text(encoding="utf-8"))
            if not synthesis or not synthesis["valid"]:
                need.append("synthesis")
    return {"info": info, "metrics": metrics, "content": content, "security": security, "reviews": reviews,
            "need": need, "escalation": escalation, "full": full, "synthesis": synthesis}


def plan(out: Path) -> dict[str, Any]:
    rules = read_json(out / "rules.json")
    config = read_json(out / "batch_config.json")
    batch = read_json(out / "batch_submissions.json")
    tasks_dir = out / ".tasks"
    tasks_dir.mkdir(exist_ok=True)
    os.chmod(tasks_dir, 0o700)
    tasks = []
    for info in batch["submissions"]:
        sub_dir = out / info["dir"]
        st = submission_state(sub_dir, rules)
        if not st["need"]:
            continue
        srules = rules_for(rules, read_json(sub_dir / "submission.json"))
        values = common_values(sub_dir, srules, config)
        for code in st["need"]:
            if code == "synthesis":
                panel_reviews = [st["reviews"][c] for c in PANEL]
                agg = scoring.aggregate(panel_reviews, srules["rubric"])
                capped, caps = criteria.apply_caps(agg["scores"], srules["rubric"], criteria.signals(st["metrics"], st["content"], srules.get("approach")), info.get("report_lang", "pt"))
                agg = {**agg, "scores": capped, "total": scoring.total_score(capped, srules["rubric"]), "caps": caps}
                dec = scoring.decide(agg["total"], agg["scores"], srules, st["metrics"], st["content"], st["security"],
                                     audience=config.get("audience", "committee"), lang=info.get("report_lang", "pt"))
                prompt = synthesis_prompt(sub_dir, values, srules, {**agg, **dec})
                output = sub_dir / "committee_synthesis.md"
            else:
                prompt = reviewer_prompt(code, (PANEL | SINGLE)[code], values, srules)
                output = sub_dir / f"review_{code}.md"
            pf = tasks_dir / f"{info['dir']}__{code}.md"
            pf.write_text(prompt, encoding="utf-8")
            tasks.append({
                "id": f"{info['dir']}:{code}",
                "submission": info["id"],
                "kind": "synthesis" if code == "synthesis" else "review",
                "codename": code,
                "prompt_file": str(pf),
                "output_file": str(output),
                "escalated": bool(st["escalation"]),
            })
    manifest = {"tasks": tasks, "count": len(tasks)}
    write_json(tasks_dir / "manifest.json", manifest)
    return manifest


def cmd_next(args: argparse.Namespace) -> int:
    out = Path(args.output_dir).resolve()
    manifest = plan(out)
    kinds: dict[str, int] = {}
    for task in manifest["tasks"]:
        kinds[task["codename"]] = kinds.get(task["codename"], 0) + 1
    print(json.dumps({"status": "ok", "pending_tasks": manifest["count"], "by_codename": kinds, "manifest": str(out / ".tasks" / "manifest.json")}, indent=2))
    return 0


def _valid_output(text: str) -> bool:
    return "SCORES_JSON" in text or "SYNTHESIS_JSON" in text


def cmd_run(args: argparse.Namespace) -> int:
    from runners import detect_runner, run_tasks

    out = Path(args.output_dir).resolve()
    try:
        runner = detect_runner(args.runner)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    rounds, failed_ids = 0, set()
    while rounds < args.max_rounds:
        rounds += 1
        tasks = [task for task in plan(out)["tasks"] if task["id"] not in failed_ids]
        if args.limit:
            tasks = tasks[: args.limit]
        if not tasks:
            break
        print(f"[run] round {rounds}: {len(tasks)} task(s) on {runner} (parallel={args.parallel})", file=sys.stderr)
        results = run_tasks(tasks, runner=runner, model=args.model, effort=args.effort, tool_permissions=args.tool_permissions,
                            parallel=args.parallel, timeout=args.timeout_seconds, retries=args.max_retries, validate=_valid_output,
                            log=lambda s: print(s, file=sys.stderr))
        failed_ids |= {r["id"] for r in results if r["status"] != "ok"}
        if args.limit:
            break
    pending = plan(out)["count"]
    print(json.dumps({"status": "ok" if not pending else "pending", "rounds": rounds, "failed_tasks": sorted(failed_ids), "pending_tasks": pending}, indent=2))
    return 0 if not pending else 3


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------


def pre_submission_checklist(metrics: dict[str, Any], content: dict[str, Any], security: dict[str, Any], rules: dict[str, Any],
                             lang: str = "pt") -> list[dict[str, str]]:
    """Deterministic to-do list for authors: what must be fixed and what to confirm before submitting.

    Priorities: `obrigatório` (edital breach, promised results, repeated or hidden text), `recomendado`
    (best-practice advice, or any breach when there is no edital), `conferir` (a heuristic a human should confirm)."""
    strict = rules["enforcement"] == "strict"
    items: list[dict[str, str]] = []
    for c in metrics.get("checks", []):
        prio = {"fail": "obrigatório", "warn": "recomendado", "unknown": "conferir"}.get(c["status"])
        if not prio:
            continue
        if prio == "obrigatório" and not strict:
            prio = "recomendado"
        detail = t(lang, "ck_observed", v=c["observed"]) + (", " + t(lang, "ck_limit", v=c["limit"]) if c.get("limit") is not None else "")
        items.append({"priority": prio, "item": c["label"], "detail": "; ".join(x for x in (detail, c.get("note") or "") if x)})
    high = [p for p in content.get("promises", []) if p["severity"] == "high"]
    if high:
        items.append({"priority": "obrigatório", "item": t(lang, "ck_promises"),
                      "detail": t(lang, "ck_promises_d", n=len(high), q=high[0].get("sentence", "")[:120])})
    if criteria.signals(metrics, content, rules.get("approach"))["results_without_numbers"] and rules.get("track_kind", "research") == "research":
        items.append({"priority": "recomendado", "item": t(lang, "ck_numbers"), "detail": t(lang, "ck_numbers_d")})
    if (content.get("repetition") or {}).get("significant"):
        items.append({"priority": "obrigatório", "item": t(lang, "ck_repeated"), "detail": t(lang, "ck_repeated_d")})
    if not security.get("is_clean", True):
        items.append({"priority": "obrigatório", "item": t(lang, "ck_hidden"), "detail": t(lang, "ck_hidden_d")})
    order = {"obrigatório": 0, "recomendado": 1, "conferir": 2}
    return sorted(items, key=lambda x: order[x["priority"]])


def compile_submission(sub_dir: Path, rules: dict[str, Any], *, pdf: bool, ai_disclosure: bool, audience: str = "committee") -> dict[str, Any]:
    st = submission_state(sub_dir, rules)
    rules = rules_for(rules, st["info"])
    info = st["info"]
    lang = info.get("report_lang", "pt")
    author = audience == "author"
    tracks = {tr["code"]: tr["name"] for tr in rules.get("tracks", [])}
    if st["full"]:
        used = [st["reviews"][c] for c in PANEL if c in st["reviews"]]
        panel_label = t(lang, "panel_full_author" if author else "panel_full") + (t(lang, "panel_escalated") if st["escalation"] else "")
    else:
        used = [st["reviews"]["omega"]] if "omega" in st["reviews"] else []
        panel_label = t(lang, "panel_single")
    agg = scoring.aggregate(used, rules["rubric"])
    scores, overrides = agg["scores"], []
    syn = st["synthesis"]
    if syn and syn["valid"]:
        scores, overrides = scoring.apply_overrides(scores, syn["overrides"], rules["rubric"])
    scores, caps = criteria.apply_caps(scores, rules["rubric"], criteria.signals(st["metrics"], st["content"], rules.get("approach")), lang)
    total = scoring.total_score(scores, rules["rubric"])
    dec = scoring.decide(total, scores, rules, st["metrics"], st["content"], st["security"], audience=audience, lang=lang)
    dec["reasons"][1:1] = [k["reason"] for k in caps]
    flags = list(dec["flags"])
    hold_flag = "fix_before_submission" if audience == "author" else "compliance_hold"
    if st["escalation"]:
        flags.append("escalated")
    if st["need"]:
        flags.append("incomplete")
    recommended = None
    decision = dec["decision"]
    if syn and syn["valid"]:
        recommended = syn["decision"] if syn["decision"] in rules["decisions"] else None
        if recommended and recommended != decision and syn["decision_note"].strip():
            # Without a minimum score there is nothing to override: the synthesis is the recommendation.
            if decision is not None:
                flags.append("chair_override")
            dec["reasons"].append(t(lang, "panel_recommends" if author else "chair_recommends", decision=report.dec_label(recommended, lang), note=syn["decision_note"]))
            decision = recommended
        if syn["compliance_hold"] and hold_flag not in flags:
            flags.append(hold_flag)
        if syn["integrity_flag"] and "integrity" not in flags:
            flags.append("integrity")
    elif used:
        votes = [r["decision"] for r in used if r.get("decision")]
        recommended = max(set(votes), key=votes.count) if votes else None

    suggested = (syn or {}).get("track") if syn and syn.get("track") in tracks else None
    if not suggested:
        votes = [r["track"] for r in used if r.get("track")]
        suggested = max(set(votes), key=votes.count) if votes else None
    # The track the authors declared is the one the submission competes in (and whose barema scored it);
    # the evaluators' choice only fills it in when none was declared, otherwise it is reported.
    declared = info.get("declared_track") if info.get("declared_track") in tracks else None
    track = declared or suggested
    if declared and suggested and suggested != declared:
        dec["reasons"].append(t(lang, "track_suggested", track=tracks[suggested]))
    feedback = (syn["feedback"] if syn and syn["valid"] else (used[0]["feedback"] if used else "")).strip()
    sources = ([(t(lang, "conf_synthesis"), syn["confidential"])] if syn else []) + [(c, r["confidential"]) for c, r in st["reviews"].items() if any(r is u for u in used)]
    confidential = [f"**{who}:** {x.strip()}" for who, x in sources
                    if x and x.strip().rstrip(".").lower() not in ("none", "nenhum", "nenhuma", "ninguno", "ninguna")]

    result = {
        "id": info["id"], "file": info["file"], "dir": info["dir"], "title": info["title"], "format": info["format"],
        "panel": info["panel"], "panel_label": panel_label, "escalation_reasons": st["escalation"],
        "track": track, "track_name": tracks.get(track or "", None),
        "rubric_key": info.get("rubric_key", "main"), "track_kind": info.get("track_kind", "research"), "profile": info.get("profile"),
        "scores": scores, "spread": agg["spread"], "total": total, "overrides": overrides, "caps": caps,
        "criteria_evidence": {c["id"]: criteria.indicators(c, st["metrics"], st["content"], lang) for c in rules["rubric"]["criteria"]},
        "decision": decision, "decision_by_score": dec["decision"], "recommended_decision": recommended,
        "reasons": dec["reasons"], "flags": sorted(set(flags)), "margin_to_cutoff": dec["margin_to_cutoff"],
        "disagreements": scoring.disagreements(used, rules["rubric"], lang),
        "assessment": (syn or {}).get("assessment", ""), "feedback": feedback, "confidential": confidential,
        "compliance_failed": st["metrics"]["summary"]["failed"], "high_promises": st["content"]["promise_summary"]["high"],
        "reviews": {c: {"decision": r.get("decision"), "confidence": r.get("confidence"), "total": r.get("total"), "valid": r["valid"], "errors": r["errors"]}
                    for c, r in st["reviews"].items()},
        "pending": st["need"],
        "audience": audience,
        "lang": lang,
        "checklist": pre_submission_checklist(st["metrics"], st["content"], st["security"], rules, lang) if author else [],
    }
    write_json(sub_dir / "evaluation_summary.json", result)
    sheet = report.evaluation_sheet(result, rules, (sub_dir / "metrics.md").read_text(encoding="utf-8"),
                                    (sub_dir / "content_audit.md").read_text(encoding="utf-8"), ai_disclosure)
    (sub_dir / "congress_evaluation_sheet.md").write_text(sheet, encoding="utf-8")
    (sub_dir / "feedback_to_authors.md").write_text(report.feedback_to_authors(result, rules), encoding="utf-8")
    if pdf:
        kind = t(lang, "sheet_title_author" if author else "sheet_title_committee")
        result["pdf"] = report.markdown_to_pdf(sheet, sub_dir / "congress_evaluation_sheet.pdf", f"{kind} — {info['id']}", lang)
    return result


def batch_rules(rules: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Rules for the batch outputs: the baremas actually used, criteria merged (one column per criterion)."""
    used = [rubric_of(rules, k) for k in dict.fromkeys(r.get("rubric_key", "main") for r in results)] or [rules["rubric"]]
    if len(used) == 1:
        return {**rules, "rubric": used[0]}
    seen: dict[str, Any] = {}
    for rub in used:
        for c in rub["criteria"]:
            seen.setdefault(c["id"], c)
    tie = list(dict.fromkeys(tb for rub in used for tb in rub.get("tie_breakers") or []))
    return {**rules, "rubric": {**used[0], "criteria": list(seen.values()), "tie_breakers": tie}}


def cmd_compile(args: argparse.Namespace) -> int:
    out = Path(args.output_dir).resolve()
    rules = read_json(out / "rules.json")
    batch = read_json(out / "batch_submissions.json")
    config = read_json(out / "batch_config.json")
    audience = config.get("audience", "committee")
    results = [compile_submission(out / s["dir"], rules, pdf=not args.no_pdf, ai_disclosure=not args.no_ai_disclosure, audience=audience)
               for s in batch["submissions"]]
    rules = batch_rules(rules, results)
    ranked = report.ranking(results, rules)
    lang = batch_language(config.get("language"), [s.get("language") for s in batch["submissions"]])
    header, rows = report.spreadsheet_rows(ranked, rules, lang)
    report.write_csv(out / "committee_scores.csv", header, rows)
    xlsx = report.write_xlsx(out / "committee_scores.xlsx", header, rows, rules, lang)
    (out / "committee_report.md").write_text(report.committee_report(ranked, rules, batch["failures"], not args.no_ai_disclosure, audience=audience, lang=lang), encoding="utf-8")
    for r in ranked:  # persist ranks
        write_json(out / r["dir"] / "evaluation_summary.json", r)
    incomplete = [r["id"] for r in ranked if r["pending"]]
    print(json.dumps({
        "status": "ok" if not incomplete else "incomplete",
        "submissions": len(ranked),
        "decisions": {d: sum(1 for r in ranked if r["decision"] == d) for d in rules["decisions"]},
        "undecided": sum(1 for r in ranked if r["decision"] is None),
        "flagged": sum(1 for r in ranked if r["flags"]),
        "incomplete": incomplete,
        "xlsx": xlsx,
        "committee_report": str(out / "committee_report.md"),
    }, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Congress abstract review pipeline (single submission or batch).")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare")
    pr.add_argument("--input", required=True, help="One submission file or a folder of submissions.")
    pr.add_argument("--rules", required=True, help="rules.json from edital_parser.py (validate or default).")
    pr.add_argument("--output-dir", required=True)
    pr.add_argument("--panel", choices=["default", "full", "lite", "auto"], default="default", help="default: full for one file, auto for a folder.")
    pr.add_argument("--format", choices=["auto", "simple", "expanded"], default="auto")
    pr.add_argument("--language", choices=["auto", "pt", "en", "es"], default="auto",
                    help="Language of the evaluations and reports. auto (default): each abstract's own language (pt, en or es; others → en).")
    pr.add_argument("--submissions-csv", help="Optional CSV with columns file,id,track (and optionally kind).")
    pr.add_argument("--track", help="Track code for every input (when there is no CSV): selects that track's barema.")
    pr.add_argument("--kind", choices=list(KINDS), help="Nature of the work when no track applies (e.g. without an edital): research, innovation or extension.")
    pr.add_argument("--area", choices=list(area_profiles.AREA_CODES), help="Force the area (default: classified from the abstract).")
    pr.add_argument("--approach", choices=list(area_profiles.APPROACH_CODES), help="Force the research approach (default: classified from the abstract).")
    pr.add_argument("--audience", choices=["default", "committee", "author"], default="default",
                    help="committee: evaluation for the scientific committee; author: pre-submission check for the authors, with or without an edital "
                         "(default: author for the no-edital ruleset, committee for an edital).")
    pr.add_argument("--no-blind", action="store_true", help="Show authors and affiliations to the evaluators (default: withheld).")
    nx = sub.add_parser("next")
    nx.add_argument("--output-dir", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("--output-dir", required=True)
    rn.add_argument("--runner", choices=["auto", "claude", "agy", "gemini"], default="auto")
    rn.add_argument("--model", default=None)
    rn.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default=None)
    rn.add_argument("--parallel", type=int, default=4)
    rn.add_argument("--timeout-seconds", type=float, default=600.0)
    rn.add_argument("--max-retries", type=int, default=1)
    rn.add_argument("--max-rounds", type=int, default=4, help="next→run rounds (omega → panel → synthesis needs 3).")
    rn.add_argument("--limit", type=int, default=0, help="Run at most N tasks (one round), e.g. to pilot a batch.")
    rn.add_argument("--tool-permissions", choices=["sandboxed", "none", "unsafe"], default="sandboxed")
    co = sub.add_parser("compile")
    co.add_argument("--output-dir", required=True)
    co.add_argument("--no-pdf", action="store_true")
    co.add_argument("--no-ai-disclosure", action="store_true")
    args = p.parse_args()
    return {"prepare": cmd_prepare, "next": cmd_next, "run": cmd_run, "compile": cmd_compile}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
