"""Deliverables: evaluation sheet (MD + PDF), feedback to authors, batch spreadsheet and committee report.

Every fixed text comes from `i18n.py` in the language of the result (`result["lang"]`, the abstract's
language unless forced). `audience="author"` turns the committee sheet into a pre-submission check.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from criteria import crit_name, text_of
from i18n import dec_label, flag_label, num, score, t

AI_DISCLOSURE = t("pt", "ai_committee")  # kept for callers that import it


def _fmt(v: Any, lang: str = "pt") -> str:
    return num(v, lang)


def ai_disclosure_text(lang: str, audience: str) -> str:
    return t(lang, "ai_author" if audience == "author" else "ai_committee")


def evaluation_sheet(result: dict[str, Any], rules: dict[str, Any], metrics_md: str, content_md: str, ai_disclosure: bool = True) -> str:
    lang = result.get("lang", "pt")
    author = result.get("audience") == "author"
    rub = rules["rubric"]
    event = rules["event"]["name"] or t(lang, "congress")
    strict = rules["enforcement"] == "strict"
    L = [
        f"# {t(lang, 'sheet_title_author' if author else 'sheet_title_committee')} — {event}",
        "",
        f"- **{t(lang, 'submission')}:** {result['id']} · {t(lang, 'file')} `{result['file']}`",
        f"- **{t(lang, 'title')}:** {result['title'] or '—'}",
        f"- **{t(lang, 'format')}:** {t(lang, 'fmt_expanded' if result['format'] == 'expanded' else 'fmt_simple')}",
        f"- **{t(lang, 'track')}:** {result.get('track_name') or result.get('track') or '—'}",
        *([f"- **{t(lang, 'profile')}:** {t(lang, 'area_' + (result['profile']['area'] or 'none'))}"
            + (f" · {t(lang, 'app_' + result['profile']['approach'])}" if result.get("track_kind", "research") == "research" else "")
            + (f" ({t(lang, 'profile_low_conf')})" if result['profile'].get('low_confidence') else "")] if result.get("profile") else []),
        f"- **{t(lang, 'evaluation')}:** {result['panel_label']}",
        f"- **{t(lang, 'norm_ref')}:** {t(lang, 'norm_edital' if strict else 'norm_default')}"
        + (t(lang, "norm_default_barema" + ("_" + rub["kind"] if rub.get("kind") in ("innovation", "extension") else "")) if rub.get("source") == "default" and strict else "")
        + (f" · {t(lang, 'norm_kind_' + rub['kind'])}" if rub.get("source") == "default" and not strict and rub.get("kind") in ("innovation", "extension") else ""),
        f"- **{t(lang, 'report_language')}:** {t(lang, 'lang_' + lang)}",
        "",
        f"## {t(lang, 'result_author' if author else 'result')}",
        "",
        f"- **{t(lang, 'estimated_score' if author else 'final_score')}:** {score(result['total'], lang)} "
        f"({t(lang, 'scale')} {_fmt(rub['total_range']['min'], lang)}–{_fmt(rub['total_range']['max'], lang)})",
        f"- **{t(lang, 'likely_decision' if author else 'suggested_decision')}:** **{dec_label(result['decision'], lang)}**",
    ]
    if result.get("recommended_decision") and result["recommended_decision"] != result["decision"]:
        L.append(f"- {t(lang, 'evaluators_recommend')}: {dec_label(result['recommended_decision'], lang)}")
    for r in result["reasons"]:
        L.append(f"- {r}")
    if result["flags"]:
        L.append(f"- **{t(lang, 'flags')}:** {'; '.join(flag_label(f, lang) for f in result['flags'])}")
    if author:
        L += ["", f"## {t(lang, 'checklist')}", ""]
        if result.get("checklist"):
            for it in result["checklist"]:
                L.append(f"- [ ] **{t(lang, 'prio_' + it['priority'])}** — {it['item']}" + (f": {it['detail']}" if it.get("detail") else ""))
        else:
            L.append(t(lang, "checklist_none"))
    evidence = result.get("criteria_evidence") or {}
    L += ["", f"## {t(lang, 'barema')}", ""]
    if evidence:
        L += [f"| {t(lang, 'col_criterion')} | {t(lang, 'col_weight')} | {t(lang, 'col_score')} | {t(lang, 'col_spread')} | {t(lang, 'col_evidence')} |", "|---|---|---|---|---|"]
    else:
        L += [f"| {t(lang, 'col_criterion')} | {t(lang, 'col_weight')} | {t(lang, 'col_score')} | {t(lang, 'col_spread')} |", "|---|---|---|---|"]
    for c in rub["criteria"]:
        row = f"| {crit_name(c, lang)} | {_fmt(c['weight'], lang)} | {_fmt(result['scores'].get(c['id']), lang)} | {_fmt(result['spread'].get(c['id']), lang)} |"
        if evidence:
            row += f" {evidence.get(c['id'], '—')} |"
        L.append(row)
    if result.get("overrides"):
        L += ["", t(lang, "overrides_author" if author else "overrides")]
        for o in result["overrides"]:
            name = next((crit_name(c, lang) for c in rub["criteria"] if c["id"] == o["criterion"]), o["criterion"])
            L.append(f"- {name}: {_fmt(o['from'], lang)} → {_fmt(o['to'], lang)} — {o['reason']}")
    if result.get("caps"):
        L += ["", t(lang, "caps_title")]
        L += [f"- {k['reason']} ({_fmt(float(k['from']), lang)} → {_fmt(float(k['to']), lang)})" for k in result["caps"]]
    if result.get("escalation_reasons"):
        L += ["", t(lang, "escalated_because", reasons="; ".join(result["escalation_reasons"]))]
    if result.get("assessment"):
        L += ["", f"## {t(lang, 'assessment')}", "", result["assessment"]]
    if result.get("disagreements"):
        L += ["", f"## {t(lang, 'disagreements')}", "", *[f"- {d}" for d in result["disagreements"]]]
    feedback_block = ["", f"## {t(lang, 'feedback_author' if author else 'feedback_committee')}", "", result["feedback"] or t(lang, "no_feedback")]
    checks_block = ["", metrics_md.strip(), "", content_md.strip()]
    # Authors read the revision plan first; the committee reads the checks before the feedback.
    L += feedback_block + checks_block if author else checks_block + feedback_block
    if result.get("confidential"):
        L += ["", f"## {t(lang, 'confidential_author' if author else 'confidential_committee')}", "", *result["confidential"]]
    L += ["", f"## {t(lang, 'individual')}", ""]
    for code, rev in result["reviews"].items():
        L.append(f"- **{code}**: {dec_label(rev.get('decision'), lang)} · {t(lang, 'confidence')} {t(lang, 'conf_' + rev['confidence']) if rev.get('confidence') in ('high', 'medium', 'low') else '—'} · "
                 f"{t(lang, 'score_lc')} {score(rev.get('total'), lang)} — `review_{code}.md`")
    if ai_disclosure:
        L += ["", "---", "", f"_{ai_disclosure_text(lang, result.get('audience', 'committee'))}_"]
    return "\n".join(L) + "\n"


def feedback_to_authors(result: dict[str, Any], rules: dict[str, Any]) -> str:
    lang = result.get("lang", "pt")
    author = result.get("audience") == "author"
    event = rules["event"]["name"] or t(lang, "congress")
    L = [
        f"# {t(lang, 'feedback_author' if author else 'feedback_doc_committee')} — {event}",
        "",
        f"**{t(lang, 'work')}:** {result['title'] or result['id']}",
        "",
        result["feedback"] or "",
        "",
    ]
    if author and result.get("checklist"):
        L += [f"## {t(lang, 'checklist')}", ""]
        L += [f"- [ ] **{t(lang, 'prio_' + it['priority'])}** — {it['item']}" + (f": {it['detail']}" if it.get("detail") else "") for it in result["checklist"]]
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# PDF (ReportLab, small Markdown subset)
# ---------------------------------------------------------------------------


def _inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])_(.+?)_(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return text


def markdown_to_pdf(md: str, out: Path, title: str, lang: str = "pt") -> bool:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return False
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=12.5)
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)
    h = {1: styles["Title"], 2: styles["Heading2"], 3: styles["Heading3"]}
    flow: list[Any] = []
    lines = md.splitlines()
    i = 0
    width = A4[0] - 3.6 * cm
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append([Paragraph(_inline(c), cell) for c in cells])
                i += 1
            if rows:
                ncol = max(len(r) for r in rows)
                rows = [r + [""] * (ncol - len(r)) for r in rows]
                tbl = Table(rows, colWidths=[width / ncol] * ncol, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                flow += [tbl, Spacer(1, 6)]
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", ln)
        if m:
            flow.append(Paragraph(_inline(m.group(2)), h[len(m.group(1))]))
        elif re.match(r"^\s*[-*]\s+", ln):
            indent = 18 if ln.startswith("  ") else 8
            flow.append(Paragraph(_inline(re.sub(r"^\s*[-*]\s+", "", ln)), ParagraphStyle("li", parent=body, leftIndent=indent, bulletIndent=indent - 8), bulletText="•"))
        elif ln.strip() == "---":
            flow.append(Spacer(1, 8))
        elif ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||\s*[-*]\s)", lines[i + 1]):
                i += 1
                para.append(lines[i])
            flow.append(Paragraph(_inline(" ".join(para)), body))
        else:
            flow.append(Spacer(1, 4))
        i += 1

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.8 * cm, 1.0 * cm, f"{title[:90]} — {t(lang, 'page')} {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm, title=title).build(
        flow, onFirstPage=footer, onLaterPages=footer
    )
    return True


# ---------------------------------------------------------------------------
# Batch outputs
# ---------------------------------------------------------------------------


def ranking(results: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    tb = rules["rubric"].get("tie_breakers") or []

    def key(r: dict[str, Any]) -> tuple:
        return (-(r["total"] if r["total"] is not None else -1e9), *(-(r["scores"].get(t) or 0) for t in tb), r["id"])

    ranked = sorted(results, key=key)
    by_track: dict[str, int] = {}
    for pos, r in enumerate(ranked, start=1):
        r["rank_overall"] = pos
        t = r.get("track") or "—"
        by_track[t] = by_track.get(t, 0) + 1
        r["rank_in_track"] = by_track[t]
    return ranked


def spreadsheet_rows(ranked: list[dict[str, Any]], rules: dict[str, Any], lang: str = "pt") -> tuple[list[str], list[list[Any]]]:
    crit = rules["rubric"]["criteria"]
    header = t(lang, "csv_header", crit="|".join(c["id"] for c in crit)).split("|")
    rows = []
    for r in ranked:
        rows.append([
            r.get("rank_overall"), r.get("rank_in_track"), r["id"], r["file"], r["title"], r["format"], r.get("lang", ""),
            r.get("track_name") or r.get("track") or "",
            round(r["total"], 2) if r["total"] is not None else None, *[r["scores"].get(c["id"]) for c in crit],
            dec_label(r["decision"], lang) if r["decision"] else "", dec_label(r.get("recommended_decision"), lang) if r.get("recommended_decision") else "",
            r["panel_label"], "; ".join(flag_label(f, lang) for f in r["flags"]),
            "; ".join(r.get("compliance_failed", [])), r.get("high_promises", 0), " | ".join(r["reasons"]),
            t(lang, "area_" + (r["profile"]["area"] or "none")) if r.get("profile") else "",
            t(lang, "app_" + r["profile"]["approach"]) if r.get("profile") and r.get("track_kind", "research") == "research" else "",
        ])
    return header, rows


SCORE_COL = 8  # final score column of spreadsheet_rows: always two decimals


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:  # BOM: Excel opens accents correctly
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            row = list(row)
            if isinstance(row[SCORE_COL], (int, float)):
                row[SCORE_COL] = f"{row[SCORE_COL]:.2f}"
            w.writerow(row)


def write_xlsx(path: Path, header: list[str], rows: list[list[Any]], rules: dict[str, Any], lang: str = "pt") -> bool:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return False
    wb = Workbook()
    ws = wb.active
    ws.title = t(lang, "xlsx_scores")
    ws.append(header)
    for row in rows:
        ws.append(row)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8EEF5")
    for cell in ws.iter_cols(min_col=SCORE_COL + 1, max_col=SCORE_COL + 1, min_row=2):
        for c in cell:
            c.number_format = "0.00"
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions
    wide = {header[4], header[-1]}
    for idx, name in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = 50 if name in wide else 14
    crit = wb.create_sheet(t(lang, "barema")[:31])
    crit.append(t(lang, "xlsx_crit_header").split("|"))
    for c in rules["rubric"]["criteria"]:
        anchors = "; ".join(f"{a['min']:g}–{a['max']:g}: {text_of(a['descriptor'], lang)}" for a in c.get("anchors") or [])
        crit.append([c["id"], crit_name(c, lang), c["weight"], c["max_score"], c["description"], anchors])
    crit.append([])
    crit.append([t(lang, "xlsx_cutoffs"), score(rules["rubric"].get("approval_cutoff"), lang)])
    wb.save(path)
    return True


def committee_report(ranked: list[dict[str, Any]], rules: dict[str, Any], failures: list[dict[str, Any]], ai_disclosure: bool = True,
                     *, audience: str = "committee", lang: str = "pt") -> str:
    author = audience == "author"
    decisions = rules["decisions"]
    event = rules["event"]["name"] or t(lang, "congress")
    L = [f"# {t(lang, 'batch_title_author' if author else 'batch_title_committee')} — {event}", "", f"{t(lang, 'batch_evaluated')}: **{len(ranked)}**"]
    if failures:
        L.append(t(lang, "batch_failed", n=len(failures)))
    counts = {m: sum(1 for r in ranked if r["decision"] == m) for m in decisions}
    undecided = sum(1 for r in ranked if r["decision"] is None)
    L += ["", f"| {t(lang, 'col_decision')} | {t(lang, 'col_submissions')} |", "|---|---|", *[f"| {dec_label(m, lang)} | {n} |" for m, n in counts.items()]]
    if undecided:
        L.append(f"| {t(lang, 'undecided')} | {undecided} |")
    flagged = [r for r in ranked if r["flags"]]
    L += ["", f"## {t(lang, 'for_author' if author else 'for_committee')} ({len(flagged)})", ""]
    if flagged:
        L += [f"| {t(lang, 'col_id')} | {t(lang, 'col_title')} | {t(lang, 'flags')} | {t(lang, 'col_score')} | {t(lang, 'col_suggested')} |", "|---|---|---|---|---|"]
        for r in flagged:
            L.append(f"| {r['id']} | {r['title'][:70]} | {'; '.join(flag_label(f, lang) for f in r['flags'])} | {score(r['total'], lang)} | {dec_label(r['decision'], lang)} |")
    else:
        L.append(t(lang, "none"))
    tracks: dict[str, list[dict[str, Any]]] = {}
    for r in ranked:
        tracks.setdefault(r.get("track_name") or r.get("track") or t(lang, "no_track"), []).append(r)
    L += ["", f"## {t(lang, 'by_track')}", ""]
    for tr, rs in tracks.items():
        L += [f"### {tr} ({len(rs)})", "", f"| # | {t(lang, 'col_id')} | {t(lang, 'col_title')} | {t(lang, 'col_score')} | {t(lang, 'col_decision')} |", "|---|---|---|---|---|"]
        for r in rs:
            L.append(f"| {r['rank_in_track']} | {r['id']} | {r['title'][:80]} | {score(r['total'], lang)} | {dec_label(r['decision'], lang)} |")
        L.append("")
    if failures:
        L += [f"## {t(lang, 'not_processed')}", "", *[f"- `{f['file']}`: {f['error']}" for f in failures], ""]
    if ai_disclosure:
        L += ["---", "", f"_{ai_disclosure_text(lang, audience)}_"]
    return "\n".join(L) + "\n"
