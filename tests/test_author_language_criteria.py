import json
from types import SimpleNamespace

import pytest

import congress_review as cr
import criteria
from conftest import FIXTURES
from edital_parser import validate_edital
from test_pipeline import _prepare, _tasks, _write

SYNTH = ("## Committee assessment\nOk.\n\n## Feedback to the authors\n1. Report the results.\n\n## Confidential comments to the committee\nNone.\n\n"
         '```json SYNTHESIS_JSON\n{{"overrides": [], "decision": "{m}", "decision_note": "", "track": null, "compliance_hold": {hold}, "integrity_flag": false}}\n```\n')


def _compile(out):
    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=True, no_ai_disclosure=False)) == 0


def test_report_language_follows_each_abstract(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["simple_pt_structured.md", "simple_en_block_promises.txt"], language="auto")
    pt = json.loads((out / "simple-pt-structured" / "submission.json").read_text())
    en = json.loads((out / "simple-en-block-promises" / "submission.json").read_text())
    assert (pt["report_lang"], en["report_lang"]) == ("pt", "en")
    assert "## Compliance and metrics" in (out / "simple-en-block-promises" / "metrics.md").read_text()
    assert "## Content audit" in (out / "simple-en-block-promises" / "content_audit.md").read_text()
    assert "## Conformidade e métricas" in (out / "simple-pt-structured" / "metrics.md").read_text()
    prompt = (out / ".tasks" / "simple-en-block-promises__omega.md").read_text()
    assert "Write the whole evaluation in **English**" in prompt
    _write(out, "simple-pt-structured", "omega", (9, 9, 9, 8), "approved")
    _write(out, "simple-en-block-promises", "omega", (6, 3, 1, 6), "rejected")
    _compile(out)
    sheet_en = (out / "simple-en-block-promises" / "congress_evaluation_sheet.md").read_text()
    assert sheet_en.startswith("# Evaluation sheet") and "Suggested decision" in sheet_en and "Rejected" in sheet_en
    assert (out / "simple-pt-structured" / "congress_evaluation_sheet.md").read_text().startswith("# Ficha de avaliação")


def test_forced_language_overrides_detection(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["simple_en_block_promises.txt"], language="es")
    assert "## Conformidad y métricas" in (out / "simple-en-block-promises" / "metrics.md").read_text()


def test_author_mode_with_edital(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["simple_en_block_promises.txt"], audience="author", language="auto")
    assert json.loads((out / "batch_config.json").read_text())["audience"] == "author"
    tasks = _tasks(out)
    assert sorted(t["codename"] for t in tasks) == ["alfa", "beta", "gamma"]
    prompt = (out / ".tasks" / "simple-en-block-promises__beta.md").read_text()
    assert "pre-submission check requested by the authors" in prompt
    assert "every breach must be fixed before submission" in prompt
    assert "A revision plan for the authors" in prompt
    for code in ("alfa", "beta", "gamma"):
        _write(out, "simple-en-block-promises", code, (7, 6, 8, 6), "approved")
    cr.plan(out)
    (out / "simple-en-block-promises" / "committee_synthesis.md").write_text(SYNTH.format(m="rejected", hold="true"), encoding="utf-8")
    _compile(out)
    res = json.loads((out / "simple-en-block-promises" / "evaluation_summary.json").read_text())
    assert "fix_before_submission" in res["flags"] and "compliance_hold" not in res["flags"]
    assert res["scores"]["results"] == 3.0  # capped: results only promised
    must = [i for i in res["checklist"] if i["priority"] == "obrigatório"]
    assert any(i["item"] == "Results promised for the event" for i in must)
    sheet = (out / "simple-en-block-promises" / "congress_evaluation_sheet.md").read_text()
    assert sheet.startswith("# Pre-submission check") and "## Before submitting" in sheet and "**must fix**" in sheet
    assert "## Revision plan" in sheet and "does not replace the event's evaluation" in sheet
    assert (out / "simple-en-block-promises" / "feedback_to_authors.md").read_text().startswith("# Revision plan")
    assert "Pre-submission report" in (out / "committee_report.md").read_text()


def test_no_edital_defaults_to_author(tmp_path, default_rules):
    out = _prepare(tmp_path, default_rules, files=["simple_pt_structured.md"])
    assert json.loads((out / "batch_config.json").read_text())["audience"] == "author"


def test_committee_mode_keeps_compliance_hold(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["simple_en_block_promises.txt"], panel="lite")
    prompt = (out / ".tasks" / "simple-en-block-promises__omega.md").read_text()
    assert "pre-submission check" not in prompt
    _write(out, "simple-en-block-promises", "omega", (7, 6, 8, 6), "approved")
    _compile(out)
    res = json.loads((out / "simple-en-block-promises" / "evaluation_summary.json").read_text())
    assert res["checklist"] == [] and "fix_before_submission" not in res["flags"]
    assert res["caps"] and res["caps"][0]["criterion"] == "results"


def test_every_criterion_has_anchor_levels(edital_rules, default_rules):
    for rules in (edital_rules, default_rules):
        for c in rules["rubric"]["criteria"]:
            assert c["anchors_source"] == "global" and len(c["anchors"]) == 5
            assert c["anchors"][0]["max"] == c["max_score"] and c["anchors"][-1]["min"] == rules["rubric"]["scale"]["min"]
    results = next(c for c in edital_rules["rubric"]["criteria"] if c["id"] == "results")
    assert {k["when"] for k in results["caps"]} == {"promises_high", "results_without_numbers"}


def _edital_with(criteria_list, scale=None):
    d = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    d["rubric"]["criteria"] = criteria_list
    d["rubric"]["tie_breakers"] = []
    if scale:
        d["rubric"]["scale"] = scale
        d["rubric"]["approval_cutoff"] = 3.0
    return validate_edital(d)


def test_edital_anchors_based_on_and_generic():
    rules, errors, warnings = _edital_with([
        {"id": "metodo", "name": "Método", "weight": 1, "based_on": "methods"},
        {"id": "impacto", "name": "Impacto social", "weight": 1},
        {"id": "apresentacao", "name": "Apresentação", "weight": 1, "max_score": 5,
         "anchors": [{"min": 4, "descriptor": "Excelente"}, {"min": 2, "descriptor": "Regular"}, {"min": 0, "descriptor": "Fraca"}]},
    ], scale={"min": 0, "max": 5})
    assert not errors, errors
    by = {c["id"]: c for c in rules["rubric"]["criteria"]}
    assert by["metodo"]["anchors_source"] == "global" and by["metodo"]["anchors"][0]["min"] == 4.5  # 9/10 of 0–5
    assert by["impacto"]["anchors_source"] == "generic" and any("impacto" in w for w in warnings)
    assert by["apresentacao"]["anchors_source"] == "edital"
    assert [(a["min"], a["max"]) for a in by["apresentacao"]["anchors"]] == [(4.0, 5), (2.0, 4.0), (0.0, 2.0)]


def test_unknown_category_is_an_error():
    _, errors, _ = _edital_with([{"id": "x", "name": "X", "weight": 1, "based_on": "nonexistent"}])
    assert any("based_on" in e for e in errors)


@pytest.mark.parametrize("sig,expected", [({"promises_high": True}, 3.0), ({"results_without_numbers": True}, 4.0), ({}, 8.0)])
def test_caps(edital_rules, sig, expected):
    scores, applied = criteria.apply_caps({"results": 8.0, "methods": 8.0}, edital_rules["rubric"], sig, "en")
    assert scores["results"] == expected and scores["methods"] == 8.0
    assert bool(applied) == (expected != 8.0)


def test_caps_can_be_disabled(edital_rules):
    rubric = {**edital_rules["rubric"], "apply_caps": False}
    assert criteria.apply_caps({"results": 8.0}, rubric, {"promises_high": True})[0]["results"] == 8.0


def test_prompt_has_levels_and_indicators(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["expanded_pt.md"], panel="lite")
    prompt = (out / ".tasks" / "expanded-pt__omega.md").read_text()
    assert "### Score levels" in prompt and "global category `results`" in prompt
    assert "Cap applied by code" in prompt and "data density" in prompt


def test_edital_criterion_names_are_kept_default_names_translated(edital_rules, default_rules):
    assert all(c["name_i18n"] == {} for c in edital_rules["rubric"]["criteria"])
    results = next(c for c in default_rules["rubric"]["criteria"] if c["id"] == "results")
    assert criteria.crit_name(results, "en") == "Results with concrete data"
