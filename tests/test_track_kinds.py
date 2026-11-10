import json
from types import SimpleNamespace

import congress_review as cr
from conftest import FIXTURES, fake_review
from edital_parser import rubric_key, rubric_of, validate_edital
from scoring import decide
from test_pipeline import _prepare, _tasks

INNOVATION_IDS = ["problem", "solution_stage", "differential", "feasibility", "impact", "writing"]
EXTENSION_IDS = ["community", "action", "outcomes", "dialogue", "writing"]


def _summit_like(with_rubric=False):
    d = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    d["tracks"] = [{"code": "pesquisa", "name": "Pesquisa"}, {"code": "inovacao", "name": "Inovação", "kind": "innovation"},
                   {"code": "extensao", "name": "Extensão", "kind": "extension"}]
    if not with_rubric:
        del d["rubric"]
    rules, errors, warnings = validate_edital(d)
    assert not errors, errors
    return rules, warnings


def test_without_barema_each_kind_gets_its_default():
    rules, _ = _summit_like()
    assert [c["id"] for c in rubric_of(rules, rubric_key(rules, "inovacao"))["criteria"]] == INNOVATION_IDS
    assert [c["id"] for c in rubric_of(rules, rubric_key(rules, "extensao"))["criteria"]] == EXTENSION_IDS
    assert rubric_of(rules, rubric_key(rules, "pesquisa"))["kind"] == "research"
    assert rubric_of(rules, rubric_key(rules, "inovacao"))["approval_cutoff"] is None  # no invented minimum
    sol = next(c for c in rubric_of(rules, "innovation")["criteria"] if c["id"] == "solution_stage")
    assert sol["anchors_source"] == "global" and sol["name"] == "Solução e estágio de desenvolvimento"
    assert [k["when"] for k in sol["caps"]] == ["promises_high"]  # no "results without numbers" cap


def test_edital_barema_applies_to_every_track_unless_track_has_its_own():
    rules, warnings = _summit_like(with_rubric=True)
    assert rubric_key(rules, "inovacao") == "main" and any("share the edital's barema" in w for w in warnings)
    d = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    d["tracks"] = [{"code": "inovacao", "name": "Inovação", "kind": "innovation",
                    "rubric": {"criteria": [{"id": "produto", "name": "Produto", "weight": 1, "based_on": "solution_stage"}]}}]
    rules, errors, _ = validate_edital(d)
    assert not errors
    assert rubric_key(rules, "inovacao") == "track:inovacao"
    assert rubric_of(rules, "track:inovacao")["approval_cutoff"] == 6.0  # inherits the edital's minimum


def test_bad_kind_is_an_error():
    d = json.loads((FIXTURES / "edital_sample.json").read_text(encoding="utf-8"))
    d["tracks"] = [{"code": "x", "name": "X", "kind": "teaching"}]
    _, errors, _ = validate_edital(d)
    assert any("kind" in e for e in errors)


def test_default_rules_offer_kinds_without_tracks(default_rules):
    assert rubric_key(default_rules, None, "extension") == "extension"
    assert rubric_key(default_rules, None, None) == "main"


def test_innovation_prompt_uses_its_barema_and_note(tmp_path):
    rules, _ = _summit_like()
    out = _prepare(tmp_path, rules, files=["simple_pt_structured.md"], panel="lite", track="inovacao")
    info = json.loads((out / "simple-pt-structured" / "submission.json").read_text())
    assert (info["rubric_key"], info["track_kind"]) == ("innovation", "innovation")
    prompt = (out / ".tasks" / "simple-pt-structured__omega.md").read_text()
    assert "This is an innovation track" in prompt and '"solution_stage": 0' in prompt and '"results": 0' not in prompt


def test_no_numbers_flag_only_for_research():
    rules, _ = _summit_like()
    content = {"promises": [], "data_density": {"results_without_numbers": True}}
    metrics = {"summary": {"advisory": False, "failed": []}}
    research = cr.rules_for(rules, {"rubric_key": "main", "track_kind": "research"})
    innovation = cr.rules_for(rules, {"rubric_key": "innovation", "track_kind": "innovation"})
    assert "no_quantitative_results" in decide(6.0, {}, research, metrics, content, {})["flags"]
    assert "no_quantitative_results" not in decide(6.0, {}, innovation, metrics, content, {})["flags"]


def test_mixed_batch_merges_criteria_columns(tmp_path):
    rules, _ = _summit_like()
    csv_path = tmp_path / "subs.csv"
    csv_path.write_text("file,id,track\nsimple_pt_structured.md,a,inovacao\nexpanded_pt.md,b,extensao\n", encoding="utf-8")
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps(rules), encoding="utf-8")
    src = tmp_path / "in"
    src.mkdir()
    for f in ("simple_pt_structured.md", "expanded_pt.md"):
        (src / f).write_text((FIXTURES / "submissions" / f).read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "out"
    assert cr.cmd_prepare(SimpleNamespace(input=str(src), rules=str(rules_file), output_dir=str(out), panel="lite", format="auto", language="pt",
                                          submissions_csv=str(csv_path), no_blind=False, audience="committee", track=None, kind=None)) == 0
    for t in _tasks(out):
        sub = t["submission"]
        ids = INNOVATION_IDS if sub == "a" else EXTENSION_IDS
        scores = dict.fromkeys(ids, 7)
        payload = fake_review("omega", scores, "approved", track="inovacao" if sub == "a" else "extensao")
        open(t["output_file"], "w", encoding="utf-8").write(payload)
    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=True, no_ai_disclosure=False)) == 0
    header = (out / "committee_scores.csv").read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert set(INNOVATION_IDS + EXTENSION_IDS) <= set(header)
    res = json.loads((out / "simple-pt-structured" / "evaluation_summary.json").read_text())
    assert res["total"] == 7.0 and res["rubric_key"] == "innovation"
    sheet = (out / "simple-pt-structured" / "congress_evaluation_sheet.md").read_text()
    assert "Solução e estágio de desenvolvimento" in sheet and "barema padrão de inovação" in sheet


def test_declared_track_wins_over_evaluators_suggestion(tmp_path):
    rules, _ = _summit_like()
    out = _prepare(tmp_path, rules, files=["simple_pt_structured.md"], panel="lite", track="inovacao")
    sub = out / "simple-pt-structured"
    prompt = (out / ".tasks" / "simple-pt-structured__omega.md").read_text()
    assert '"track": "inovacao"' in prompt  # the skeleton suggests the declared track
    (sub / "review_omega.md").write_text(fake_review("omega", dict.fromkeys(INNOVATION_IDS, 7), "approved", track="pesquisa"), encoding="utf-8")
    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=True, no_ai_disclosure=False)) == 0
    res = json.loads((sub / "evaluation_summary.json").read_text())
    assert res["track"] == "inovacao" and any("sugerem o eixo Pesquisa" in r for r in res["reasons"])


def test_gitignore_keeps_test_fixtures():
    import subprocess
    root = FIXTURES.parent.parent
    r = subprocess.run(["git", "check-ignore", "-q", "tests/fixtures/submissions/simple_pt_structured.md"], cwd=root, capture_output=True)
    assert r.returncode == 1  # 1 = not ignored
