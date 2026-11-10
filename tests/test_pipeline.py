import json
import shutil
import sys
from types import SimpleNamespace

import congress_review as cr
from conftest import FIXTURES, fake_review


def _prepare(tmp_path, edital_rules, panel="default", files=None, audience="default", language="pt", track=None, kind=None):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps(edital_rules), encoding="utf-8")
    src = tmp_path / "in"
    src.mkdir()
    for f in files or ["simple_pt_structured.md", "simple_en_block_promises.txt", "expanded_pt.md"]:
        shutil.copy(FIXTURES / "submissions" / f, src / f)
    out = tmp_path / "out"
    args = SimpleNamespace(input=str(src), rules=str(rules_file), output_dir=str(out), panel=panel, format="auto",
                           language=language, submissions_csv=None, no_blind=False, audience=audience,
                           track=track, kind=kind)
    assert cr.cmd_prepare(args) == 0
    return out


def _tasks(out):
    return json.loads((out / ".tasks" / "manifest.json").read_text(encoding="utf-8"))["tasks"]


def _write(out, sub, code, s, decision, **kw):
    (out / sub / f"review_{code}.md").write_text(fake_review(code, dict(zip(["relevance", "methods", "results", "writing"], s, strict=True)), decision, **kw), encoding="utf-8")


def test_batch_defaults_to_auto_and_plans_omega(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules)
    assert json.loads((out / "batch_config.json").read_text())["panel"] == "auto"
    assert sorted(t["id"] for t in _tasks(out)) == ["expanded-pt:omega", "simple-en-block-promises:omega", "simple-pt-structured:omega"]


def test_single_file_defaults_to_full_panel(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["expanded_pt.md"])
    assert sorted(t["codename"] for t in _tasks(out)) == ["alfa", "beta", "gamma"]


def test_prompts_are_blind_and_sandboxed(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["simple_pt_structured.md"], panel="lite")
    prompt = (out / ".tasks" / "simple-pt-structured__omega.md").read_text(encoding="utf-8")
    assert "Ana Souza" not in prompt and "ana.souza@umc.br" not in prompt
    assert "[Authors and affiliations withheld from evaluators]" in prompt
    assert prompt.count("\n<UNTRUSTED_ABSTRACT_CONTENT>\n") == 1  # one data block (the tag is also named in the rules)
    assert "{" + "abstract_text}" not in prompt
    assert '"relevance": 0' in prompt


def test_auto_escalation_synthesis_and_compile(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules)
    _write(out, "simple-pt-structured", "omega", (9, 9, 9, 8), "approved")
    _write(out, "simple-en-block-promises", "omega", (6, 3, 1, 6), "rejected")
    _write(out, "expanded-pt", "omega", (6, 6, 6, 6), "approved", confidence="medium")  # at the cutoff: borderline
    cr.plan(out)
    assert sorted(t["id"] for t in _tasks(out)) == ["expanded-pt:alfa", "expanded-pt:beta", "expanded-pt:gamma"]
    for code, s, m in (("alfa", (8, 7, 8, 6), "approved"), ("beta", (7, 8, 9, 7), "approved"), ("gamma", (9, 8, 7, 8), "approved")):
        _write(out, "expanded-pt", code, s, m)
    cr.plan(out)
    assert [t["id"] for t in _tasks(out)] == ["expanded-pt:synthesis"]
    (out / "expanded-pt" / "committee_synthesis.md").write_text(
        "## Committee assessment\nBom.\n\n## Feedback to the authors\nInclua palavras-chave.\n\n## Confidential comments to the committee\nNone.\n\n"
        '```json SYNTHESIS_JSON\n{"overrides": [{"criterion": "writing", "score": 7.5, "reason": "texto claro"}], "decision": "approved", '
        '"decision_note": "", "track": "biotecnologia_ambiental", "compliance_hold": false, "integrity_flag": false}\n```\n', encoding="utf-8")
    assert cr.plan(out)["count"] == 0

    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=True, no_ai_disclosure=False)) == 0
    res = {d: json.loads((out / d / "evaluation_summary.json").read_text()) for d in ("expanded-pt", "simple-pt-structured", "simple-en-block-promises")}
    exp = res["expanded-pt"]
    assert exp["total"] == 7.9 and exp["decision"] == "approved" and "escalated" in exp["flags"]
    assert exp["track"] == "biotecnologia_ambiental" and exp["feedback"] == "Inclua palavras-chave."
    assert res["simple-pt-structured"]["decision"] == "approved" and res["simple-pt-structured"]["rank_overall"] == 1
    assert res["simple-en-block-promises"]["decision"] == "rejected"
    csv_text = (out / "committee_scores.csv").read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0].startswith("rank,rank_eixo,id")
    assert "Assistência de IA".lower() in (out / "committee_report.md").read_text(encoding="utf-8").lower()


def test_invalid_review_is_replanned(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["expanded_pt.md"], panel="lite")
    (out / "expanded-pt" / "review_omega.md").write_text("## Summary\nsem JSON\n", encoding="utf-8")
    assert [t["id"] for t in _tasks(out)] == ["expanded-pt:omega"]
    assert [t["id"] for t in cr.plan(out)["tasks"]] == ["expanded-pt:omega"]


def test_unreadable_file_does_not_stop_batch(tmp_path, edital_rules):
    out = _prepare(tmp_path, edital_rules, files=["expanded_pt.md"])
    assert json.loads((out / "batch_submissions.json").read_text())["failures"] == []
    src = tmp_path / "in2"
    src.mkdir()
    (src / "bom.md").write_text((FIXTURES / "submissions" / "expanded_pt.md").read_text(encoding="utf-8"), encoding="utf-8")
    (src / "ruim.pdf").write_bytes(b"not a pdf")
    out2 = tmp_path / "out2"
    args = SimpleNamespace(input=str(src), rules=str(tmp_path / "rules.json"), output_dir=str(out2), panel="lite", format="auto",
                           language="pt", submissions_csv=None, no_blind=False, audience="default")
    assert cr.cmd_prepare(args) == 0
    batch = json.loads((out2 / "batch_submissions.json").read_text())
    assert len(batch["submissions"]) == 1 and batch["failures"][0]["file"] == "ruim.pdf"


def test_render_is_single_pass():
    assert cr.render("{a} {b}", {"a": "{b}", "b": "x"}) == "{b} x"


def test_runner_command_is_sandboxed():
    sys.modules.pop("runners", None)
    from runners import build_cli_cmd, build_sanitized_env

    assert build_cli_cmd("claude", None, None) == ["claude", "-p", "--allowedTools", "Read"]
    assert build_cli_cmd("agy", None, None)[-1] == "-p"
    import os

    os.environ["SOME_API_KEY"] = "x"
    try:
        assert "SOME_API_KEY" not in build_sanitized_env("claude")
    finally:
        del os.environ["SOME_API_KEY"]


def test_pdf_sheet_is_built(tmp_path, edital_rules):
    import pytest
    pytest.importorskip("reportlab")
    out = _prepare(tmp_path, edital_rules, panel="lite", files=["simple_pt_structured.md"])
    _write(out, "simple-pt-structured", "omega", (8, 7, 8, 7), "approved")
    assert cr.cmd_compile(SimpleNamespace(output_dir=str(out), no_pdf=False, no_ai_disclosure=False)) == 0
    pdf = out / "simple-pt-structured" / "congress_evaluation_sheet.pdf"
    assert pdf.exists() and pdf.read_bytes()[:4] == b"%PDF"
