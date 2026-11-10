"""Unicode sanitization and prompt-injection scanning for submitted abstracts.

Patterns vendored from academic-peer-review (skills/paper-review/scripts/area_profiles.py,
commit 71fb74c), with the abstract delimiter tag added.
"""

from __future__ import annotations

import re
from typing import Any

UNTRUSTED_TAG = "UNTRUSTED_ABSTRACT_CONTENT"

INVISIBLE_AND_BIDI_REGEX = re.compile(
    # Zero-width/bidi controls, C0 controls, and Unicode "tag" characters (U+E0000-E007F),
    # which can smuggle invisible ASCII instructions into text.
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\x00-\x08\x0b\x0c\x0e-\x1f\x7f\U000e0000-\U000e007f]"
)

PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions|disregard\s+(?:all\s+)?(?:previous|prior)\s+instructions|forget\s+all\s+previous\s+instructions|"
            r"ignor[ea]\s+(?:todas\s+)?as\s+instruções\s+(?:anteriores|acima)|desconsidere\s+(?:todas\s+)?as\s+instruções|"
            r"ignora\s+(?:todas\s+)?las\s+instrucciones\s+(?:anteriores|previas))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reviewer_verdict_manipulation",
        re.compile(
            r"\b(?:if\s+you\s+are\s+an?\s+(?:AI|LLM|language\s+model|automated)\s+reviewer|as\s+an?\s+(?:AI|LLM)\s+reviewer\s*,?\s*you\s+must|give\s+this\s+paper\s+a\s+strong\s+accept|output\s+only\s+the\s+verdict\s+accept|do\s+not\s+mention\s+any\s+weaknesses\s+or\s+flaws|"
            r"give\s+(?:a\s+)?positive\s+review(?:\s+only)?|do\s+not\s+highlight\s+any\s+negatives|"
            r"(?:dê|faça)\s+(?:uma\s+)?(?:avaliação|revisão|parecer)\s+positiv[ao]|"
            r"(?:da|haz)\s+(?:una\s+)?(?:evaluación|revisión)\s+positiva)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden_text_latex_or_css",
        re.compile(
            r"(?:\\textcolor\s*\{\s*white\s*\}|\\color\s*\{\s*white\s*\}|font-size\s*:\s*0(?:\.0+)?(?:px|pt|em)|opacity\s*:\s*0(?:\.0+)?\b|display\s*:\s*none)",
            re.IGNORECASE,
        ),
    ),
    (
        "delimiter_or_system_tag_spoofing",
        re.compile(
            r"(?:<\s*/?\s*UNTRUSTED_(?:MANUSCRIPT|ABSTRACT)_CONTENT\s*/?\s*>|<\s*/?\s*SYSTEM_INSTRUCTION\s*>|<\s*\|im_start\|\s*>|<\s*\|endoftext\|\s*>)",
            re.IGNORECASE,
        ),
    ),
]


def sanitize_and_scan(text: str) -> tuple[str, dict[str, Any]]:
    """Strip invisible/bidi control characters, neutralize delimiter spoofing, and scan for prompt injection."""
    invisible_hits = INVISIBLE_AND_BIDI_REGEX.findall(text)
    cleaned = INVISIBLE_AND_BIDI_REGEX.sub("", text)
    cleaned = re.sub(
        r"<\s*/?\s*UNTRUSTED_(?:MANUSCRIPT|ABSTRACT)_CONTENT\s*/?\s*>",
        "[REDACTED_DELIMITER_TAG]",
        cleaned,
        flags=re.IGNORECASE,
    )
    findings: list[dict[str, str]] = []
    smuggled = "".join(chr(ord(ch) - 0xE0000) for ch in invisible_hits if 0xE0020 <= ord(ch) <= 0xE007E)
    if smuggled.strip():
        findings.append({"category": "unicode_tag_smuggling", "matched_text": " ".join(smuggled.split())[:120]})
    for category, pat in PROMPT_INJECTION_PATTERNS:
        for m in pat.finditer(text):
            findings.append({"category": category, "matched_text": " ".join(m.group(0).split())[:120]})
    return cleaned, {
        "invisible_or_bidi_chars_stripped": len(invisible_hits),
        "suspicious_prompt_injection_count": len(findings),
        "suspicious_patterns": findings[:15],
        "is_clean": len(findings) == 0 and len(invisible_hits) < 20,
    }
