#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf>=4.0.0",
#     "pdfplumber>=0.11.0",
#     "python-docx>=1.1.0",
# ]
# ///
"""Extract a congress abstract (simple or expanded) into clean text plus a structural JSON.

Splits the submission into components that congress rules count differently (title, authors and
affiliations, body sections, keywords, references, funding/acknowledgements), detects whether it is
a simple abstract (single block, ~150-600 words, no figures or references) or an expanded abstract
(2-5 pages, sections, figures/tables, references), detects the language, and runs the same
hidden-content and prompt-injection scan as academic-peer-review.

PDF/DOCX readers are vendored from academic-peer-review (extract_paper.py, commit 71fb74c), with a
lower minimum text length (abstracts are short) and no page markers in the counted text.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hidden_content import (  # noqa: E402
    merge_into_security_scan,
    missing_scan_dependencies,
    redact_hidden_text,
    scan_docx,
    scan_html,
    scan_markdown,
    scan_pdf,
    scan_tex,
)
from security import sanitize_and_scan  # noqa: E402

SUPPORTED_FORMATS = ("simple", "expanded")
PLAIN_TEXT_FORMATS = {".txt", ".md", ".markdown", ".tex", ".rst"}
PANDOC_FORMATS = {".odt", ".rtf", ".html", ".htm", ".epub"}
GOOD_GLUED_RATIO = 0.005
MIN_PDF_CHARS = 100

# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def glued_word_ratio(text: str) -> float:
    """Share of alphabetic tokens of 20+ letters: words whose separating spaces were lost."""
    words = re.findall(r"[A-Za-zÀ-ÿ]+", text)
    if not words:
        return 1.0
    return sum(1 for w in words if len(w) >= 20) / len(words)


def _read_pymupdf(path: Path) -> list[str]:
    import fitz  # type: ignore

    with fitz.open(str(path)) as doc:
        return [page.get_text("text") for page in doc]


def _read_pdftotext(path: Path) -> list[str]:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not installed")
    proc = subprocess.run(["pdftotext", "-enc", "UTF-8", "--", str(path), "-"], capture_output=True, text=True, check=True, timeout=60)
    pages = proc.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def _read_pdfplumber(path: Path) -> list[str]:
    import pdfplumber  # type: ignore

    with pdfplumber.open(str(path)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def _read_pypdf(path: Path) -> list[str]:
    from pypdf import PdfReader  # type: ignore

    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


_PDF_BACKENDS = (("pymupdf", _read_pymupdf), ("pdftotext", _read_pdftotext), ("pdfplumber", _read_pdfplumber), ("pypdf", _read_pypdf))


def _pdf_image_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore

        return sum(len(page.images) for page in PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001 - image count is advisory
        return None


def extract_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    candidates: list[tuple[str, str, int]] = []
    for backend, reader in _PDF_BACKENDS:
        try:
            pages = reader(path)
        except Exception:  # noqa: BLE001 - a missing or failing backend just yields no candidate
            continue
        text = "\n".join(pages)
        if len(text.strip()) < MIN_PDF_CHARS:
            continue
        candidates.append((backend, text, len(pages)))
        if glued_word_ratio(text) <= GOOD_GLUED_RATIO:
            break
    if not candidates:
        raise RuntimeError(f"Failed to extract text from PDF {path} (scanned/image-only PDF, or no PDF backend installed).")
    backend, text, pages = min(candidates, key=lambda c: glued_word_ratio(c[1]))
    return text, {"backend": backend, "pages": pages, "embedded_images": _pdf_image_count(path)}


def extract_docx(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        import docx  # type: ignore

        doc = docx.Document(str(path))
        parts: list[str] = []
        # Body order: paragraphs and tables interleaved as they appear in the document.
        table_idx = 0
        tables = list(doc.tables)
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                text = "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t"))
                if text.strip():
                    parts.append(text)
            elif tag == "tbl" and table_idx < len(tables):
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in tables[table_idx].rows]
                table_idx += 1
                parts.append("[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]")
        # Pages are not stored in DOCX: estimate at ~500 words per page.
        words = sum(len(p.split()) for p in parts)
        return "\n\n".join(parts), {
            "backend": "python-docx",
            "pages": max(1, round(words / 500)),
            "pages_estimated": True,
            "embedded_images": len(doc.inline_shapes),
            "docx_tables": len(tables),
        }
    except Exception:  # noqa: BLE001 - fall back to pandoc
        pass
    if shutil.which("pandoc"):
        proc = subprocess.run(["pandoc", "--sandbox", "-t", "plain", "--wrap=none", "--", str(path)], capture_output=True, text=True, check=True, timeout=60)
        return proc.stdout, {"backend": "pandoc", "pages": None}
    raise RuntimeError(f"Failed to extract DOCX {path}. Install python-docx or pandoc >= 2.15 (needs --sandbox).")


def extract_with_pandoc(path: Path) -> tuple[str, dict[str, Any]]:
    if not shutil.which("pandoc"):
        raise RuntimeError(f"Reading {path.suffix} files requires pandoc >= 2.15 (with --sandbox).")
    proc = subprocess.run(["pandoc", "--sandbox", "-t", "plain", "--wrap=none", "--", str(path)], capture_output=True, text=True, check=True, timeout=60)
    return proc.stdout, {"backend": "pandoc", "pages": None}


def read_submission(src: Path) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Return (raw text, backend meta, hidden-content findings). Raises ValueError for unsupported input."""
    ext = src.suffix.lower()
    if ext == ".pdf":
        raw, meta = extract_pdf(src)
    elif ext == ".docx":
        raw, meta = extract_docx(src)
    elif ext in PANDOC_FORMATS:
        raw, meta = extract_with_pandoc(src)
    elif ext in PLAIN_TEXT_FORMATS:
        raw = src.read_text(encoding="utf-8", errors="replace")
        meta = {"backend": "direct_read", "pages": None}
    else:
        raise ValueError(
            f"unsupported input format '{ext or src.name}'. Supported: .pdf, .docx, "
            f"{', '.join(sorted(PANDOC_FORMATS | PLAIN_TEXT_FORMATS))}. Convert .doc files to .docx or PDF first."
        )
    if "\x00" in raw[:65536]:
        raise ValueError(f"'{src.name}' looks like a binary file, not text.")

    findings: list[dict[str, Any]] = []
    if ext == ".pdf":
        findings = scan_pdf(src)
    elif ext == ".docx":
        findings = scan_docx(src)
    elif ext in (".html", ".htm"):
        findings = scan_html(src.read_text(encoding="utf-8", errors="replace"))
    elif ext in (".md", ".markdown"):
        raw, findings = scan_markdown(raw)
    elif ext == ".tex":
        raw, findings = scan_tex(raw)
    return raw, meta, findings


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

# Canonical section -> heading alternatives (PT / EN / ES). Order matters: longer phrases first.
SECTION_HEADINGS: list[tuple[str, str]] = [
    ("results_discussion", r"resultados\s+e\s+discuss(?:ão|ao)|results\s+and\s+discussion|resultados\s+y\s+discusi(?:ó|o)n"),
    ("methods", r"materia(?:l|is)\s+e\s+m(?:é|e)todos?|material\s+and\s+methods|materials\s+and\s+methods|materiales\s+y\s+m(?:é|e)todos"
     r"|metodologia|methodology|metodolog(?:í|i)a|m(?:é|e)todos?|methods?|procedimentos\s+metodol(?:ó|o)gicos"),
    ("introduction", r"introdu(?:ção|cao)|introduction|introducci(?:ó|o)n|background|contexto|context|fundamenta(?:ção|cao)\s+te(?:ó|o)rica|antecedentes"),
    ("objectives", r"objetivos?|objectives?|aims?|purpose|prop(?:ó|o)sito|goals?"),
    ("results", r"resultados|results|findings|achados"),
    ("discussion", r"discuss(?:ão|ao)|discussion|discusi(?:ó|o)n"),
    ("conclusion", r"conclus(?:ão|ões|ao|oes)|conclusions?|conclusi(?:ó|o)n(?:es)?|considera(?:ções|coes)\s+finais|final\s+(?:remarks|considerations)"),
    ("keywords", r"palavras?[-\s]chave|key\s?words?|palabras\s+clave|descritores|descriptors"),
    ("funding", r"apoio(?:\s+financeiro)?|financiamento|fomento|funding|financial\s+support|financiaci(?:ó|o)n|agradecimentos?|acknowledge?ments?|agradecimientos"),
    ("references", r"refer(?:ê|e)ncias(?:\s+bibliogr(?:á|a)ficas)?|references|bibliography|bibliografia|bibliograf(?:í|i)a|literature\s+cited|referencias"),
]

_HEADING_ALT = "|".join(f"(?P<{name}>{alt})" for name, alt in SECTION_HEADINGS)
# A heading is either alone on its line, or opens a line/sentence followed by ':' / '.' / dash.
HEADING_RE = re.compile(
    r"(?im)(?:^|(?<=[.!?])[ \t]+)[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?(?:\d+(?:\.\d+)*\.?[ \t]+)?"
    rf"(?:{_HEADING_ALT})"
    r"(?:\*\*|__)?(?:[ \t]*(?:[:.–—-])(?:\*\*|__)?[ \t]*|[ \t]*$)"
)
BACK_MATTER = {"keywords", "funding", "references"}

# Field labels of submission forms (Even3, the event's site) pasted along with the text: a line that
# is only "Título em Português", "Title", "Resumo", "Abstract"... is neither the title nor body text.
FORM_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*"
    r"(?:t(?:í|i)tulo(?:\s+do\s+trabalho)?(?:\s+(?:em|en)\s+(?:portugu(?:ê|e)s|ingl(?:ê|e)s|espanhol|espa(?:ñ|n)ol))?"
    r"|title(?:\s+in\s+(?:english|portuguese|spanish))?"
    r"|resumo(?:\s+(?:simples|expandido(?:\s+estruturado)?))?|abstract|resumen(?:\s+extendido)?)"
    r"[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*$"
)

AFFILIATION_RE = re.compile(
    r"(?i)\b(?:universi(?:dade|ty|dad)|instituto|institute|faculdade|faculty|facultad|departamento|department|laborat(?:ó|o)rio|laboratory"
    r"|escola|school|centro|center|centre|hospital|embrapa|fiocruz|programa\s+de\s+p(?:ó|o)s|graduate\s+program|campus|brasil|brazil)\b"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
FIGURE_RE = re.compile(r"(?i)\b(?:figura|figure|fig\.?|gr(?:á|a)fico|graph)\s*(\d+)")
TABLE_RE = re.compile(r"(?i)\b(?:tabela|table|tabla|quadro)\s*(\d+)")

STOPWORDS = {
    "pt": {"de", "da", "do", "das", "dos", "que", "não", "uma", "para", "com", "foram", "são", "pela", "pelo", "também", "este", "esta", "entre", "como", "em"},
    "en": {"the", "of", "and", "to", "in", "is", "was", "were", "that", "with", "for", "this", "by", "are", "from", "these", "which", "on", "an"},
    "es": {"el", "la", "los", "las", "del", "que", "y", "en", "con", "por", "para", "fueron", "una", "este", "esta", "entre", "como", "se", "su"},
}


def word_count(text: str) -> int:
    """Words as editors count them: whitespace-separated tokens containing a letter or digit."""
    return sum(1 for tok in text.split() if re.search(r"\w", tok))


def detect_language(text: str) -> dict[str, Any]:
    tokens = re.findall(r"[a-záéíóúâêôãõçñü]+", text.lower())
    scores = {lang: sum(1 for t in tokens if t in words) for lang, words in STOPWORDS.items()}
    # "de", "que", "en", "com"... overlap: language-exclusive markers break ties.
    scores["pt"] += 3 * sum(1 for t in tokens if t in {"não", "são", "foram", "também", "pelos", "ção", "nos", "às"} or t.endswith("ção") or t.endswith("ções"))
    scores["es"] += 3 * sum(1 for t in tokens if t in {"y", "fueron", "los", "del", "también"} or t.endswith("ción") or t.endswith("ciones"))
    total = sum(scores.values())
    if not total:
        return {"code": "unknown", "confidence": 0.0, "scores": scores}
    best = max(scores, key=scores.get)
    return {"code": best, "confidence": round(scores[best] / total, 2), "scores": scores}


def _clean_heading_body(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def find_headings(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, canonical_name, heading_text) for every recognized heading, in order."""
    found = []
    for m in HEADING_RE.finditer(text):
        name = next(k for k, v in m.groupdict().items() if v)
        heading = m.group(name)
        line_start = text.rfind("\n", 0, m.start(name)) + 1
        # A heading "alone on its line" must really be short: avoid sentences starting with "Results ...".
        line_end = text.find("\n", m.end(name))
        line = text[line_start: line_end if line_end != -1 else len(text)]
        followed_by_colon = bool(re.match(r"(?:\*\*|__)?[ \t]*[:.–—-]", text[m.end(name):]))
        if not followed_by_colon and len(line.strip(" \t#*_0123456789.")) > len(heading) + 2:
            continue
        # Section boundary = start of the heading markup (##, **, numbering), not of the word itself.
        # Numbering ("2.1 ") only counts at the start of the line: a heading that follows a sentence
        # on the same line must not swallow that sentence's final period.
        start = m.start(name)
        while start > line_start and text[start - 1] in " \t#*_":
            start -= 1
        if re.fullmatch(r"[ \t#*_]*\d+(?:\.\d+)*\.?[ \t#*_]*", text[line_start:m.start(name)]):
            start = line_start
        found.append((start, m.end(), name, heading))
    return found


def _is_front_line(ln: str) -> bool:
    """Author, affiliation or e-mail line of a byline block."""
    return len(ln) < 220 and bool(
        EMAIL_RE.search(ln)
        or AFFILIATION_RE.search(ln)
        or re.search(r"[A-ZÀ-Ý][a-zà-ÿ]+\s+[A-ZÀ-Ý]", ln) and ("," in ln or re.search(r"\d|[¹²³⁴⁵⁶⁷⁸⁹*]", ln)) and len(ln.split()) <= 30
        and not re.search(r"[.!?]\s+[A-Z]", ln)
    )


def split_front_matter(lines: list[str]) -> tuple[str, list[str], int]:
    """Return (title, author/affiliation lines, index in `lines` of the first body line)."""
    nonempty = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.strip()]
    if not nonempty:
        return "", [], 0
    title_parts = [nonempty[0][1].lstrip("#").strip().strip("*_").strip()]
    body_start = nonempty[0][0] + 1
    k = 1
    # A long title wraps over several lines in PDFs: short lines without a final period that come
    # right before the byline continue the title.
    while k < len(nonempty) and k <= 3:
        ln = nonempty[k][1]
        ahead = [x for _, x in nonempty[k + 1: k + 4]]
        if _is_front_line(ln) or len(ln) > 150 or ln.endswith((".", ":")) or not any(_is_front_line(x) for x in ahead):
            break
        title_parts.append(ln)
        body_start = nonempty[k][0] + 1
        k += 1
    front: list[str] = []
    for i, ln in nonempty[k:]:
        if not _is_front_line(ln):
            break
        front.append(ln)
        body_start = i + 1
    return " ".join(title_parts), front, body_start


def _count_references(text: str) -> int:
    if not text.strip():
        return 0
    entries = [ln for ln in text.splitlines() if ln.strip()]
    numbered = [ln for ln in entries if re.match(r"\s*(?:\[\d+\]|\d+[.)])\s", ln)]
    if numbered:
        return len(numbered)
    # ABNT/APA-style: one entry per line starting with SURNAME or Surname, followed by an initial or year.
    starts = [ln for ln in entries if re.match(r"\s*[A-ZÀ-Ý][A-Za-zÀ-ÿ'-]+,\s*[A-ZÀ-Ý]", ln)]
    return len(starts) or len(re.findall(r"\(\d{4}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\.", text))


def parse_abstract(text: str, *, pages: int | None = None, embedded_images: int | None = None) -> dict[str, Any]:
    """Structure of an abstract submission. Pure function of the text (plus optional reader hints)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = FORM_LABEL_RE.sub("", text)
    text = re.sub(r"\[TABLE\]\n.*?\n\[/TABLE\]", lambda m: m.group(0).replace("\n", " \n"), text, flags=re.S)
    headings = find_headings(text)

    # Front matter: everything before the first body heading, or the leading title/author block.
    first_body = next((h for h in headings if h[2] not in BACK_MATTER), None)
    lines = text.split("\n")
    if first_body:
        pre_lines = text[: first_body[0]].split("\n")
        title, front, consumed = split_front_matter(pre_lines)
        # Whatever is left before the first heading (e.g. an unlabelled opening paragraph) is body.
        lead_body = "\n".join(ln.strip() for ln in pre_lines[consumed:] if ln.strip())
        body_region_start = first_body[0]
    else:
        title, front, body_start = split_front_matter(lines)
        lead_body = ""
        body_region_start = len("\n".join(lines[:body_start])) + (1 if body_start else 0)

    sections: list[dict[str, Any]] = []
    if word_count(lead_body):
        sections.append({"name": "unlabelled", "heading": "", "text": lead_body})
    body_heads = [h for h in headings if h[0] >= body_region_start]
    if not body_heads:
        rest = text[body_region_start:]
        # Back matter can still be present without a heading match (rare); keep the block whole.
        sections.append({"name": "unlabelled", "heading": "", "text": _clean_heading_body(rest)})
    else:
        gap = text[body_region_start: body_heads[0][0]].strip()
        if word_count(gap):
            sections.append({"name": "unlabelled", "heading": "", "text": gap})
        for idx, (_start, end, name, heading) in enumerate(body_heads):
            stop = body_heads[idx + 1][0] if idx + 1 < len(body_heads) else len(text)
            sections.append({"name": name, "heading": heading.strip(), "text": _clean_heading_body(text[end:stop])})

    for s in sections:
        s["words"] = word_count(s["text"])

    def join(names: set[str], include: bool) -> str:
        return "\n\n".join(s["text"] for s in sections if (s["name"] in names) == include and s["text"])

    body = join(BACK_MATTER, False)
    references_text = join({"references"}, True)
    keywords_text = join({"keywords"}, True)
    funding_text = join({"funding"}, True)
    keywords = [k.strip(" .;") for k in re.split(r"[;,\n]|\s\|\s", keywords_text) if k.strip(" .;")][:15]

    figure_labels = sorted({int(n) for n in FIGURE_RE.findall(text)})
    table_labels = sorted({int(n) for n in TABLE_RE.findall(text)})
    table_blocks = text.count("[TABLE]")
    figures = max(len(figure_labels), 0)
    tables = max(len(table_labels), table_blocks)
    dois = sorted({d.rstrip(".,;)]") for d in DOI_RE.findall(text)})
    references = _count_references(references_text)

    body_words = word_count(body)
    fmt = detect_format(
        body_words=body_words,
        named_sections=sum(1 for s in sections if s["name"] not in BACK_MATTER | {"unlabelled"}),
        references=references,
        figures=figures,
        tables=tables,
        pages=pages,
        embedded_images=embedded_images,
    )

    front_text = "\n".join(front)
    return {
        "title": title,
        "front_matter": {
            "lines": front,
            "emails": len(EMAIL_RE.findall(front_text)),
            "affiliation_lines": sum(1 for ln in front if AFFILIATION_RE.search(ln)),
        },
        "sections": sections,
        "section_names": [s["name"] for s in sections],
        "components": {
            "title": title,
            "front_matter": front_text,
            "body": body,
            "keywords": keywords_text,
            "references": references_text,
            "funding": funding_text,
        },
        "keywords": keywords,
        "figures": {"count": figures, "labels": figure_labels, "embedded_images": embedded_images},
        "tables": {"count": tables, "labels": table_labels},
        "references": {"count": references, "dois": dois},
        "language": detect_language(body or text),
        "format": fmt,
        "pages": pages,
    }


def detect_format(
    *,
    body_words: int,
    named_sections: int,
    references: int,
    figures: int,
    tables: int,
    pages: int | None,
    embedded_images: int | None,
) -> dict[str, Any]:
    """Simple vs expanded abstract from evidence; positive score = expanded."""
    evidence: list[str] = []
    score = 0
    if body_words > 900:
        score += 3
        evidence.append(f"body has {body_words} words (> 900)")
    elif body_words > 600:
        score += 1
        evidence.append(f"body has {body_words} words (600-900)")
    else:
        score -= 2
        evidence.append(f"body has {body_words} words (<= 600)")
    if references >= 3:
        score += 2
        evidence.append(f"{references} reference entries")
    elif references == 0:
        score -= 1
        evidence.append("no reference list")
    if figures or tables or (embedded_images or 0) > 0:
        # Simple abstracts almost never carry figure/table captions or images.
        score += 3
        evidence.append(f"{figures} figure(s), {tables} table(s), {embedded_images or 0} embedded image(s)")
    if pages and pages >= 2:
        score += 2
        evidence.append(f"{pages} pages")
    if named_sections >= 4 and body_words > 600:
        score += 1
        evidence.append(f"{named_sections} named sections")
    detected = "expanded" if score > 0 else "simple"
    confidence = "high" if abs(score) >= 3 else "low"
    return {"detected": detected, "score": score, "confidence": confidence, "evidence": evidence}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def extract(src: Path, *, fmt: str = "auto", max_file_mb: float = 25.0) -> tuple[str, dict[str, Any]]:
    """Read, sanitize and parse one submission file. Raises ValueError/RuntimeError on unusable input."""
    if not src.is_file():
        raise ValueError(f"input path is not a regular file: {src}")
    size_mb = src.stat().st_size / (1024 * 1024)
    if size_mb > max_file_mb:
        raise ValueError(f"input file size ({size_mb:.1f} MB) exceeds the limit ({max_file_mb} MB)")
    raw, backend_meta, hidden = read_submission(src)
    raw, redacted = redact_hidden_text(raw, hidden)
    text, security_scan = sanitize_and_scan(raw)
    merge_into_security_scan(security_scan, hidden)
    if redacted:
        security_scan["hidden_text_redacted"] = redacted
    missing = missing_scan_dependencies(src.suffix.lower())
    if missing:
        security_scan["hidden_content_scan_incomplete"] = {"format": src.suffix.lower(), "missing_modules": missing}

    structure = parse_abstract(text, pages=backend_meta.get("pages"), embedded_images=backend_meta.get("embedded_images"))
    if fmt in SUPPORTED_FORMATS:
        structure["format"]["requested"] = fmt
        structure["format"]["effective"] = fmt
    else:
        structure["format"]["effective"] = structure["format"]["detected"]
    structure["format"]["needs_confirmation"] = fmt not in SUPPORTED_FORMATS and structure["format"]["confidence"] == "low"
    structure["source"] = {"file": src.name, "suffix": src.suffix.lower(), **backend_meta}
    structure["security_scan"] = security_scan
    structure["char_count"] = len(text)
    return text, structure


def main() -> int:
    p = argparse.ArgumentParser(description="Extract a congress abstract (simple or expanded) into text + structure JSON.")
    p.add_argument("input_path", help="Submission file: .pdf, .docx, .md, .txt, .tex (or .odt/.rtf/.html via pandoc).")
    p.add_argument("--output-text", required=True, help="Where to write the cleaned text.")
    p.add_argument("--output-meta", required=True, help="Where to write the structure JSON.")
    p.add_argument("--format", choices=["auto", *SUPPORTED_FORMATS], default="auto", help="Abstract format (default: auto-detect).")
    p.add_argument("--max-file-mb", type=float, default=25.0)
    args = p.parse_args()

    try:
        text, structure = extract(Path(args.input_path).resolve(), fmt=args.format, max_file_mb=args.max_file_mb)
    except (ValueError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for path, content in ((args.output_text, text), (args.output_meta, json.dumps(structure, indent=2, ensure_ascii=False))):
        out = Path(path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "title": structure["title"][:160],
        "format": structure["format"],
        "language": structure["language"]["code"],
        "sections": structure["section_names"],
        "body_words": sum(s["words"] for s in structure["sections"] if s["name"] not in BACK_MATTER),
        "figures": structure["figures"]["count"],
        "tables": structure["tables"]["count"],
        "references": structure["references"]["count"],
        "security_is_clean": structure["security_scan"].get("is_clean"),
    }, indent=2, ensure_ascii=False))
    if structure["security_scan"].get("hidden_content_scan_incomplete"):
        print("WARNING: hidden-content scan incomplete (run with `uv run` so its dependencies are installed).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
