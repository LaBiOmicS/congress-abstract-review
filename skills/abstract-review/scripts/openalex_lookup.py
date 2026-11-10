#!/usr/bin/env python3
# Vendored from academic-peer-review (skills/paper-review/scripts/openalex_lookup.py, commit 71fb74c).
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Batched DOI lookup against the OpenAlex Works API (shared by the audit and compile steps).

Uses the `doi:` OR-filter (up to 50 DOIs per request) with a minimal `select=` projection,
so large author lists never inflate the response. A DOI is reported as *unresolvable* only
when a request succeeded and OpenAlex did not return it; DOIs whose request failed are
reported as *unchecked* instead of being wrongly accused of being fabricated.

OpenAlex does not index every registered DOI (e.g. JMIR preprints, many DataCite DOIs), so a DOI
missing from OpenAlex is confirmed against the doi.org handle registry before it is called
unresolvable; registered DOIs are returned as found with ``registry_only: True``.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "academic-peer-review/1.3.3 (LaBiOmicS - UMC; mailto:fabianomenegidio@umc.br)"
BATCH_SIZE = 50
MAX_REGISTRY_CHECKS = 30  # one request per DOI; the rest stay unchecked rather than accused
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
STRICT_DOI_REGEX = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
SELECT_FIELDS = "doi,title,publication_year,is_retracted,cited_by_count"


def normalize_doi(doi: str) -> str | None:
    """Return a lowercase bare DOI (no URL prefix, no trailing punctuation) or None if invalid."""
    d = doi.strip()
    d = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.IGNORECASE)
    d = d.rstrip(".,;)]}").lower()
    return d if STRICT_DOI_REGEX.match(d) else None


def _get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace"))


def _lookup_single(doi: str, timeout: float) -> tuple[str, dict[str, Any] | None]:
    """Return ("found", work) | ("missing", None) | ("error", None)."""
    url = (
        f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe='')}"
        f"?select={SELECT_FIELDS}"
    )
    try:
        return "found", _get_json(url, timeout)
    except urllib.error.HTTPError as e:
        return ("missing", None) if e.code == 404 else ("error", None)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return "error", None


def _doi_registered(doi: str, timeout: float) -> bool | None:
    """Ask the doi.org handle registry (all registration agencies): True/False, or None on failure."""
    url = f"https://doi.org/api/handles/{urllib.parse.quote(doi, safe='/')}"
    try:
        data = _get_json(url, timeout)
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    code = data.get("responseCode") if isinstance(data, dict) else None
    if code == 1:
        return True
    return False if code in (100, 200) else None


def lookup_dois(dois: list[str], *, max_checks: int = 200, timeout: float = 10.0) -> dict[str, Any]:
    """Look up DOIs in OpenAlex, confirming the missing ones against the doi.org registry.

    Returns ``{"found": {doi: work}, "unresolvable": [doi], "unchecked": [doi], "invalid": [raw]}``.
    ``unresolvable`` holds only DOIs that neither OpenAlex nor doi.org knows; registered DOIs that
    OpenAlex lacks go to ``found`` with ``registry_only: True``.
    """
    ordered: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in dois:
        d = normalize_doi(raw)
        if d is None:
            invalid.append(raw)
        elif d not in seen:
            seen.add(d)
            ordered.append(d)
    targets = ordered[:max_checks]

    found: dict[str, dict[str, Any]] = {}
    unresolvable: list[str] = []
    unchecked: list[str] = list(ordered[max_checks:])

    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i : i + BATCH_SIZE]
        # "|" and "," are filter syntax in OpenAlex; such DOIs are looked up one by one.
        batchable = [d for d in batch if "|" not in d and "," not in d]
        singles = [d for d in batch if d not in batchable]
        if batchable:
            params = urllib.parse.urlencode({
                "filter": "doi:" + "|".join(batchable),
                "per-page": BATCH_SIZE,
                "select": SELECT_FIELDS,
            })
            try:
                data = _get_json(f"https://api.openalex.org/works?{params}", timeout)
                returned: dict[str, dict[str, Any]] = {}
                for work in data.get("results") or []:
                    nd = normalize_doi(work.get("doi") or "")
                    if nd:
                        returned[nd] = work
                for d in batchable:
                    if d in returned:
                        found[d] = returned[d]
                    else:
                        unresolvable.append(d)
            except (urllib.error.URLError, TimeoutError, ValueError, OSError):
                singles.extend(batchable)
        for d in singles:
            status, work = _lookup_single(d, timeout)
            if status == "found" and work is not None:
                found[d] = work
            elif status == "missing":
                unresolvable.append(d)
            else:
                unchecked.append(d)

    confirmed_missing: list[str] = []
    for i, d in enumerate(unresolvable):
        registered = _doi_registered(d, timeout) if i < MAX_REGISTRY_CHECKS else None
        if registered:
            found[d] = {"doi": f"https://doi.org/{d}", "title": None, "publication_year": None, "registry_only": True}
        elif registered is None:
            unchecked.append(d)
        else:
            confirmed_missing.append(d)

    return {"found": found, "unresolvable": confirmed_missing, "unchecked": unchecked, "invalid": invalid}
