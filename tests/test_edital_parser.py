import json

from conftest import FIXTURES
from edital_parser import canonical_section, cross_check, extract_hints, load_default, validate_edital


def hints_for_sample():
    return extract_hints((FIXTURES / "edital_sample.md").read_text(encoding="utf-8"))


def test_hints_capture_ranges_and_maxima():
    h = {(x["kind"], x["value"]): x for x in hints_for_sample()}
    assert h[("words", 500)]["bound"] == "range" and h[("words", 500)]["min"] == 250
    assert h[("keywords", 5)]["min"] == 3
    assert h[("characters_with_spaces", 12000)]["bound"] == "max"
    assert h[("pages", 4)]["bound"] == "max"
    assert h[("figures", 2)]["bound"] == "max"
    assert h[("references", 10)]["bound"] == "max"
    assert ("words", 5) not in h  # "palavras-chave" is not a word limit


def test_hints_english_and_without_spaces():
    h = extract_hints("Abstracts must not exceed 300 words. Maximum of 2,500 characters without spaces.")
    kinds = {(x["kind"], x["value"], x["bound"]) for x in h}
    assert ("words", 300, "max") in kinds
    assert ("characters_without_spaces", 2500, "max") in kinds


def test_sample_edital_validates_and_normalizes(edital_rules):
    assert edital_rules["formats"]["simple"]["required_sections"] == ["introduction", "objectives", "methods", "results", "conclusion"]
    assert edital_rules["formats"]["simple"]["figures"]["allowed"] is False
    assert [t["code"] for t in edital_rules["tracks"]] == ["biotecnologia_ambiental", "bioinformatica", "biotecnologia_em_saude"]
    assert edital_rules["rubric"]["approval_cutoff"] == 6.0
    assert edital_rules["decisions"] == ["approved", "rejected"]


def test_cross_check_is_silent_when_everything_is_captured(edital_rules):
    assert cross_check(edital_rules, hints_for_sample()) == []


def test_cross_check_warns_on_missing_limit(edital_rules):
    edital_rules["formats"]["simple"]["limits"]["words"] = {"min": None, "max": 400}
    warnings = cross_check(edital_rules, hints_for_sample())
    assert any("words=500" in w for w in warnings)


def test_default_rules_are_valid_and_advisory(default_rules):
    assert default_rules["enforcement"] == "advisory"
    assert default_rules["rubric"]["approval_cutoff"] == 6.0
    assert default_rules["rubric"]["approval_min_scores"] == {}


def test_errors_reported():
    data = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    data["formats"]["simple"]["limits"]["words"] = {"min": 600, "max": 500}
    data["formats"]["simple"]["required_sections"].append("Seção inventada")
    data["rubric"]["approval_cutoff"] = 12
    _, errors, _ = validate_edital(data)
    text = " ".join(errors)
    assert "min (600) > max (500)" in text
    assert "unknown section" in text
    assert "approval_cutoff: 12 outside the score range" in text


def test_missing_rubric_falls_back_to_default_with_warning():
    data = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    del data["rubric"]
    rules, errors, warnings = validate_edital(data)
    assert not errors
    assert rules["rubric"]["source"] == "default"
    assert any("barema" in w for w in warnings)


def test_no_cutoff_means_committee_decides():
    data = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    data["rubric"].pop("approval_cutoff")
    rules, errors, warnings = validate_edital(data)
    assert not errors
    assert rules["rubric"]["approval_cutoff"] is None
    assert any("committee decides on approval" in w for w in warnings)


def test_missing_rubric_does_not_invent_a_cutoff():
    data = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    del data["rubric"]
    rules, errors, _ = validate_edital(data)
    assert not errors
    assert rules["rubric"]["source"] == "default" and rules["rubric"]["approval_cutoff"] is None


def test_legacy_modality_cutoffs_become_approval_cutoff():
    data = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    data["modalities"] = ["oral", "poster", "rejected"]
    data["rubric"].pop("approval_cutoff")
    data["rubric"]["cutoffs"] = {"oral": 8.0, "poster": 6.0}
    data["rubric"]["oral_min_scores"] = {"results": 7.0}
    rules, errors, warnings = validate_edital(data)
    assert not errors
    assert rules["rubric"]["approval_cutoff"] == 6.0 and rules["rubric"]["approval_min_scores"] == {}
    assert "modalities" not in rules and rules["decisions"] == ["approved", "rejected"]
    text = " ".join(warnings)
    assert "modalities ignored" in text and "replaced by approval_cutoff = 6" in text and "oral_min_scores ignored" in text


def test_canonical_section_aliases():
    assert canonical_section("Material e Métodos") == "methods"
    assert canonical_section("Considerações finais") == "conclusion"
    assert canonical_section("Keywords") == "keywords"
    assert canonical_section("Resultados e Discussão") == "results_discussion"


def test_default_file_roundtrip():
    assert load_default()["event"]["source"] == "default"
