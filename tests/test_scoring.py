from conftest import fake_review
from scoring import aggregate, apply_overrides, decide, disagreements, escalation_reasons, parse_review, parse_synthesis, total_score

CLEAN = {"summary": {"advisory": False, "failed": []}}
NO_PROMISES = {"promises": [], "data_density": {}}


def scores(rel, met, res, wri):
    return {"relevance": rel, "methods": met, "results": res, "writing": wri}


def parsed(rules, code="omega", **kw):
    return parse_review(fake_review(code, scores(*kw.pop("s")), kw.pop("decision", "approved"), **kw), rules["rubric"], rules["decisions"], [t["code"] for t in rules["tracks"]])


def test_parse_valid_review(edital_rules):
    r = parsed(edital_rules, s=(8, 7, 9, 6))
    assert r["valid"] and r["scores"]["results"] == 9.0 and r["track"] == "bioinformatica"
    assert r["decision"] == "approved"
    assert r["feedback"] == "Parecer de omega."


def test_parse_rejects_out_of_range_and_missing(edital_rules):
    md = fake_review("omega", {"relevance": 11, "methods": 5}, "approved")
    r = parse_review(md, edital_rules["rubric"], edital_rules["decisions"], [])
    assert not r["valid"]
    assert any("outside" in e for e in r["errors"]) and any("results" in e for e in r["errors"])


def test_presentation_modality_is_not_a_decision(edital_rules):
    r = parsed(edital_rules, s=(8, 8, 8, 8), decision="poster")
    assert not r["valid"] and r["decision"] is None


def test_weighted_total(edital_rules):
    assert total_score(scores(8, 8, 8, 7.5), edital_rules["rubric"]) == 7.9


def test_cutoff_decides_approval(edital_rules):
    assert decide(6.0, scores(6, 6, 6, 6), edital_rules, CLEAN, NO_PROMISES, {})["decision"] == "approved"
    d = decide(5.9, scores(6, 6, 6, 6), edital_rules, CLEAN, NO_PROMISES, {})
    assert d["decision"] == "rejected" and d["margin_to_cutoff"] == 0.1
    assert any("nota mínima para aprovação" in r for r in d["reasons"])


def test_criterion_minimums_block_approval(default_rules):
    rules = {**default_rules, "rubric": {**default_rules["rubric"], "approval_min_scores": {"results": 7.0}}}
    s = {"relevance": 10, "originality": 10, "objectives": 10, "methods": 10, "results": 6, "conclusion": 10, "writing": 10}
    total = total_score(s, rules["rubric"])
    d = decide(total, s, rules, {"summary": {"advisory": True, "failed": []}}, NO_PROMISES, {})
    assert total >= 6 and d["decision"] == "rejected"
    assert any("mínimas" in r for r in d["reasons"])


def test_high_promise_blocks_approval(edital_rules):
    content = {"promises": [{"severity": "high"}], "data_density": {}}
    d = decide(9.0, scores(9, 9, 9, 9), edital_rules, CLEAN, content, {})
    assert d["decision"] == "rejected"
    assert any("prometidos" in r for r in d["reasons"])


def test_no_cutoff_leaves_decision_to_committee(edital_rules):
    rules = {**edital_rules, "rubric": {**edital_rules["rubric"], "approval_cutoff": None}}
    d = decide(7.0, scores(7, 7, 7, 7), rules, CLEAN, NO_PROMISES, {})
    assert d["decision"] is None and d["margin_to_cutoff"] is None
    assert any("comissão decide" in r for r in d["reasons"])


def test_compliance_and_integrity_flags(edital_rules):
    metrics = {"summary": {"advisory": False, "failed": ["limit_words"]}}
    d = decide(7.0, scores(7, 7, 7, 7), edital_rules, metrics, NO_PROMISES, {"is_clean": False})
    assert d["decision"] == "approved"
    assert set(d["flags"]) == {"compliance_hold", "integrity"}


def test_escalation_borderline_lowconf_and_not_compliance(edital_rules):
    r = parsed(edital_rules, s=(6, 6, 6, 6), decision="approved")
    d = decide(6.0, r["scores"], edital_rules, CLEAN, NO_PROMISES, {})
    assert any("limítrofe" in x for x in escalation_reasons(r, d, edital_rules, NO_PROMISES))
    r2 = parsed(edital_rules, s=(3, 3, 3, 3), decision="rejected")
    d2 = decide(3.0, r2["scores"], edital_rules, {"summary": {"advisory": False, "failed": ["limit_words"]}}, NO_PROMISES, {})
    assert escalation_reasons(r2, d2, edital_rules, NO_PROMISES) == []
    r3 = parsed(edital_rules, s=(3, 3, 3, 3), decision="rejected", confidence="low")
    assert escalation_reasons(r3, d2, edital_rules, NO_PROMISES) == ["avaliador com baixa confiança"]


def test_escalation_when_evaluator_disagrees_with_score(edital_rules):
    r = parsed(edital_rules, s=(3, 3, 3, 3), decision="approved")
    d = decide(3.0, r["scores"], edital_rules, CLEAN, NO_PROMISES, {})
    assert any("a nota dá" in x for x in escalation_reasons(r, d, edital_rules, NO_PROMISES))


def test_median_aggregation_and_disagreement(edital_rules):
    rs = [parsed(edital_rules, code=c, s=s, decision=m) for c, s, m in (("alfa", (8, 7, 8, 6), "approved"), ("beta", (7, 8, 9, 7), "approved"), ("gamma", (9, 8, 2, 8), "rejected"))]
    agg = aggregate(rs, edital_rules["rubric"])
    assert agg["scores"] == {"relevance": 8.0, "methods": 8.0, "results": 8.0, "writing": 7.0}
    dis = disagreements(rs, edital_rules["rubric"])
    res_name = next(c["name"] for c in edital_rules["rubric"]["criteria"] if c["id"] == "results")
    assert f"{res_name}: 2–9" in dis and any(d.startswith("decisão") for d in dis)


def test_overrides_need_reason_and_are_clamped(edital_rules):
    new, applied = apply_overrides({"writing": 6.0}, [{"criterion": "writing", "score": 12, "reason": "quote"}, {"criterion": "methods", "score": 9}], edital_rules["rubric"])
    assert new["writing"] == 10.0 and len(applied) == 1


def test_parse_synthesis():
    md = "## Committee assessment\nOk.\n\n## Feedback to the authors\nTexto.\n\n```json SYNTHESIS_JSON\n{\"overrides\": [], \"decision\": \"rejected\", \"decision_note\": \"x\", \"compliance_hold\": true}\n```\n"
    s = parse_synthesis(md)
    assert s["valid"] and s["decision"] == "rejected" and s["decision_note"] == "x" and s["compliance_hold"] and s["feedback"] == "Texto."


def test_final_scores_have_two_decimals():
    from i18n import score
    assert score(7.0, "pt") == "7,00" and score(5.4, "pt") == "5,40" and score(5.413, "en") == "5.41"
    assert score(None, "pt") == "—"


def test_decision_reason_uses_two_decimals(edital_rules):
    d = decide(7.0, scores(7, 7, 7, 7), edital_rules, CLEAN, NO_PROMISES, {})
    assert any("nota 7,00" in r and "6,00" in r for r in d["reasons"])
