import json
import shutil
from types import SimpleNamespace

import pytest

import congress_review as cr
from area_profiles import classify
from conftest import FIXTURES, fake_review
from criteria import adapt_to_approach, apply_caps, signals
from extract_abstract import extract

AREAS = FIXTURES / "areas"
DEFAULT_IDS = ["relevance", "originality", "objectives", "methods", "results", "conclusion", "writing"]


def _profile(name):
    _, s = extract(AREAS / name)
    body = "\n".join(x.get("text", "") for x in s["sections"])
    return classify(s["title"], body, "; ".join(s.get("keywords") or []))


@pytest.mark.parametrize("name, area, approach, ethics", [
    ("quali_educacao.md", "humanas", "qualitative", True),
    ("saude_transversal.md", "saude", "quantitative", True),
    ("direito_teorico.md", "sociais_aplicadas", "theoretical", False),
    ("revisao_integrativa.md", "saude", "review", False),
    ("relato_experiencia.md", "saude", "case_report", False),   # experience report: no ethics committee needed
    ("computacao.md", "exatas", "computational", False),
    ("entrevistas_sem_cep.md", "saude", "qualitative", True),
    ("quali_educacion_es.md", "humanas", "qualitative", True),
    ("health_cross_sectional_en.md", "saude", "quantitative", True),
])
def test_classification(name, area, approach, ethics):
    p = _profile(name)
    assert (p["area"], p["approach"], p["ethics_check"]) == (area, approach, ethics)
    assert p["approach_confidence"] >= 0.5


def test_ethics_approval_stated_clears_the_check():
    p = classify("Ansiedade em estudantes", "Estudo transversal com 214 estudantes. Aprovado pelo CEP (CAAE 123456). Prevalência de 38%.")
    assert p["human_subjects"] and p["ethics_stated"] and not p["ethics_check"]


def test_thin_evidence_is_low_confidence_and_forcing_wins():
    p = classify("Um estudo", "Analisamos o tema.")
    assert set(p["low_confidence"]) == {"area", "approach"}
    f = classify("Um estudo", "Analisamos o tema.", area="humanas", approach="theoretical")
    assert (f["area"], f["approach"], f["low_confidence"]) == ("humanas", "theoretical", [])


def test_qualitative_levels_replace_quantitative_ones(default_rules):
    rub = adapt_to_approach(default_rules["rubric"], "qualitative")
    res = next(c for c in rub["criteria"] if c["id"] == "results")
    assert res["name"] == "Resultados sustentados pelo material" and res["approach_variant"] == "qualitative"
    assert "trechos, falas" in res["anchors"][0]["descriptor"]["pt"]
    assert [k["when"] for k in res["caps"]] == ["promises_high"]
    # the original rubric is untouched; quantitative keeps it as is
    assert next(c for c in default_rules["rubric"]["criteria"] if c["id"] == "results")["name"] == "Resultados com dados concretos"
    assert adapt_to_approach(default_rules["rubric"], "quantitative") is default_rules["rubric"]


def test_edital_levels_are_kept(edital_rules):
    rub = adapt_to_approach(edital_rules["rubric"], "qualitative")
    for c in rub["criteria"]:
        if c.get("anchors_source") == "edital":
            assert "approach_variant" not in c


def test_no_numbers_cap_only_when_numbers_expected(default_rules):
    content = {"promises": [], "data_density": {"results_without_numbers": True}}
    s = dict.fromkeys(DEFAULT_IDS, 8.0)
    capped, caps = apply_caps(s, default_rules["rubric"], signals({}, content, "quantitative"))
    assert capped["results"] == 4.0 and caps
    rub = adapt_to_approach(default_rules["rubric"], "qualitative")
    capped, caps = apply_caps(s, rub, signals({}, content, "qualitative"))
    assert capped["results"] == 8.0 and not caps


def _run(tmp_path, rules, name, approach=None):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps(rules), encoding="utf-8")
    src = tmp_path / "in"
    src.mkdir()
    shutil.copy(AREAS / name, src / name)
    out = tmp_path / "out"
    assert cr.cmd_prepare(SimpleNamespace(input=str(src), rules=str(rules_file), output_dir=str(out), panel="lite", format="auto", language="pt",
                                          submissions_csv=None, no_blind=False, audience="committee", track=None, kind=None,
                                          area=None, approach=approach)) == 0
    return out, out / name.removesuffix(".md").replace("_", "-")


def test_qualitative_prompt_and_sheet(tmp_path, default_rules):
    out, sub = _run(tmp_path, default_rules, "quali_educacao.md")
    info = json.loads((sub / "submission.json").read_text())
    assert info["profile"]["area"] == "humanas"
    prompt = next((out / ".tasks").glob("*__omega.md")).read_text()
    assert "Research approach: qualitative" in prompt and "Do not ask for statistics" in prompt
    assert "trechos, falas" not in prompt and "excerpts, quotes, cited documents" in prompt  # English levels for the evaluators
    assert "**Ethics:**" in prompt
    (sub / "review_omega.md").write_text(fake_review("omega", dict.fromkeys(DEFAULT_IDS, 7), "approved", track=None), encoding="utf-8")
    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=True, no_ai_disclosure=False)) == 0
    res = json.loads((sub / "evaluation_summary.json").read_text())
    assert "ethics_check" in res["flags"] and "no_quantitative_results" not in res["flags"]
    sheet = (sub / "congress_evaluation_sheet.md").read_text()
    assert "Ciências Humanas e Educação · pesquisa qualitativa" in sheet
    assert "Resultados sustentados pelo material" in sheet and "Verificar aprovação ética" in sheet
    header = (out / "committee_scores.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.endswith("area,abordagem")


def test_approach_is_ignored_outside_research_tracks(tmp_path, default_rules):
    out, sub = _run(tmp_path, default_rules, "quali_educacao.md")
    info = json.loads((sub / "submission.json").read_text())
    r = cr.rules_for(default_rules, {**info, "rubric_key": "extension", "track_kind": "extension"})
    assert r["approach"] is None and r["profile"]["area"] == "humanas"
    assert "Research approach" not in cr.profile_note(r) and "Area: humanas" in cr.profile_note(r)


def test_no_area_evidence_is_undetermined_not_a_guess():
    p = classify("Um estudo", "Analisamos o tema.")
    assert p["area"] is None and "area" in p["low_confidence"]
    assert cr.profile_note({"profile": p, "approach": None}).startswith("(Automatic classification")


def test_qualitative_drops_numeric_indicators(default_rules):
    res = next(c for c in adapt_to_approach(default_rules["rubric"], "qualitative")["criteria"] if c["id"] == "results")
    assert res["indicators"] == ["promises_high"]
    mixed = next(c for c in adapt_to_approach(default_rules["rubric"], "mixed")["criteria"] if c["id"] == "results")
    assert "data_density" in mixed["indicators"] and [k["when"] for k in mixed["caps"]] == ["promises_high"]


def test_author_checklist_does_not_ask_qualitative_work_for_numbers(default_rules):
    content = {"promises": [], "data_density": {"results_without_numbers": True}}
    metrics = {"checks": []}
    quali = cr.rules_for(default_rules, {"rubric_key": "main", "track_kind": "research", "profile": {"area": "humanas", "approach": "qualitative"}})
    quant = cr.rules_for(default_rules, {"rubric_key": "main", "track_kind": "research", "profile": {"area": "saude", "approach": "quantitative"}})
    assert not cr.pre_submission_checklist(metrics, content, {}, quali)
    assert cr.pre_submission_checklist(metrics, content, {}, quant)


def test_reprepare_with_another_approach_supersedes_old_evaluations(tmp_path, default_rules):
    out, sub = _run(tmp_path, default_rules, "quali_educacao.md")
    (sub / "review_omega.md").write_text(fake_review("omega", dict.fromkeys(DEFAULT_IDS, 7), "approved", track=None), encoding="utf-8")
    shutil.rmtree(tmp_path / "in")
    out, sub = _run(tmp_path, default_rules, "quali_educacao.md")  # same abstract, same rules: kept
    assert (sub / "review_omega.md").exists() and not (sub / "superseded").exists()
    shutil.rmtree(tmp_path / "in")
    out, sub = _run(tmp_path, default_rules, "quali_educacao.md", approach="quantitative")
    assert not (sub / "review_omega.md").exists()
    assert len(list((sub / "superseded").glob("*/review_omega.md"))) == 1
    assert [t["codename"] for t in json.loads((out / ".tasks" / "manifest.json").read_text())["tasks"]] == ["omega"]
