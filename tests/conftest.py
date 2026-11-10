from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "skills" / "abstract-review" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must be hermetic: any real HTTP request fails loudly."""

    def _blocked(*args, **kwargs):
        raise AssertionError("Network access attempted during tests")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


@pytest.fixture
def edital_rules():
    from edital_parser import validate_edital

    rules, errors, _ = validate_edital(json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8")))
    assert not errors, errors
    return rules


@pytest.fixture
def default_rules():
    from edital_parser import load_default, validate_edital

    rules, errors, _ = validate_edital(load_default())
    assert not errors, errors
    return rules


def fake_review(code: str, scores: dict, decision: str, confidence: str = "high", track: str | None = "bioinformatica") -> str:
    payload = {"codename": code, "scores": scores, "decision": decision, "track": track, "track_fit": "good", "confidence": confidence, "blocking_issues": []}
    return (
        "## Summary\nResumo.\n\n## Strengths\n- Algo.\n\n## Problems\n- **[Minor]** Algo.\n\n## Scores\n| Criterion | Score | Justification |\n|---|---|---|\n\n"
        f"## Recommended decision\n{decision}\n\n## Feedback to the authors\nParecer de {code}.\n\n"
        "## Confidential comments to the committee\nNone.\n\n"
        f"```json SCORES_JSON\n{json.dumps(payload)}\n```\n"
    )
