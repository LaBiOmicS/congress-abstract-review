from abstract_metrics import compute_metrics, count, plain
from conftest import FIXTURES
from content_audit import audit, cross_references, data_density, detect_promises
from extract_abstract import extract, parse_abstract


def test_count_like_text_editors():
    c = count("**Métodos:** Coletamos   24\namostras.")
    assert c == {"words": 4, "characters_with_spaces": 31, "characters_without_spaces": 28}
    assert plain("## Título\n\n- item") == "Título - item"


def test_strict_word_limit_failure(edital_rules):
    _, s = extract(FIXTURES / "submissions" / "simple_pt_structured.md")
    m = compute_metrics(s, edital_rules)
    assert m["summary"]["failed"] == ["limit_words"]
    words = next(c for c in m["checks"] if c["id"] == "limit_words")
    assert words["observed"] == m["counted"]["words"] and words["limit"] == "250–500"


def test_advisory_mode_never_fails(default_rules):
    _, s = extract(FIXTURES / "submissions" / "simple_en_block_promises.txt")
    m = compute_metrics(s, default_rules)
    assert m["summary"]["n_fail"] == 0 and m["summary"]["advisory"] is True


def test_unlabelled_block_sections_are_unknown_not_failed(edital_rules):
    _, s = extract(FIXTURES / "submissions" / "simple_en_block_promises.txt")
    m = compute_metrics(s, edital_rules)
    statuses = {c["id"]: c["status"] for c in m["checks"]}
    assert statuses["section_methods"] == "unknown"
    assert statuses["language"] == "fail"


def test_count_scope_includes_references_for_expanded(edital_rules):
    _, s = extract(FIXTURES / "submissions" / "expanded_pt.md")
    m = compute_metrics(s, edital_rules)
    assert m["counted_scope"] == ["body", "references"]
    assert m["counted"]["words"] > m["counts"]["body"]["words"]


def test_anonymized_event_flags_author_lines(edital_rules):
    edital_rules["anonymized"] = True
    _, s = extract(FIXTURES / "submissions" / "simple_pt_structured.md")
    m = compute_metrics(s, edital_rules)
    assert "anonymized" in m["summary"]["blocking_failures"]


def test_promises_detected_with_severity():
    _, s = extract(FIXTURES / "submissions" / "simple_en_block_promises.txt")
    p = detect_promises(s)
    assert sum(1 for x in p if x["severity"] == "high") == 2
    assert {x["category"] for x in p} >= {"deferred_results", "ongoing_work", "expectation"}


def test_portuguese_promises_and_perspective_sentence():
    s = parse_abstract(
        "Título\n\nResultados: Os dados estão sendo analisados e os resultados serão apresentados no congresso.\n\n"
        "Conclusão: O método reduziu o erro em 20%. Futuros estudos pretendemos ampliar a amostra."
    )
    p = detect_promises(s)
    sev = {(x["section"], x["severity"]) for x in p}
    assert ("results", "high") in sev
    assert ("conclusion", "info") in sev


def test_data_density_and_results_without_numbers():
    _, s = extract(FIXTURES / "submissions" / "simple_pt_structured.md")
    d = data_density(s)
    assert d["has_inferential_statistics"] and d["level"] == "high"
    s2 = parse_abstract("Título\n\nResultados: Os resultados foram muito bons e mostraram diferenças importantes entre os grupos em 2023.")
    assert data_density(s2)["results_without_numbers"] is True


def test_statcheck_runs_with_decimal_commas():
    s = parse_abstract("Título\n\nResultados: A riqueza diferiu (t(22) = 2,95, p = 0,07).")
    a = audit(s, "", "simple")
    assert a["statcheck"]["inconsistencies_count"] == 1


def test_cross_references():
    text = "Como na Figura 1 e na Figura 2.\n\nFigura 1. Legenda.\n\nTabela 1. Outra legenda.\n"
    xr = cross_references(text)
    assert xr["mentioned_without_caption"] == ["figure 2"]
    assert xr["caption_never_mentioned"] == ["table 1"]


def test_repeated_text_is_detected_and_does_not_inflate_density():
    _, s = extract(FIXTURES / "expanded_pt_repeated.md")
    a = audit(s, "", "expanded")
    assert a["repetition"]["significant"] and a["repetition"]["repeated_sentences"] >= 5
    assert a["data_density"]["quantitative_tokens"] == 4  # 62%, F, p, 3.450 kg/ha — counted once each


def test_clean_expanded_has_no_repetition_and_rich_data():
    _, s = extract(FIXTURES / "submissions" / "expanded_pt.md")
    a = audit(s, "", "expanded")
    assert a["repetition"]["repeated_sentences"] == 0
    assert a["data_density"]["level"] in ("adequate", "high")
    assert a["statcheck"]["tests_checked"] == 1 and a["statcheck"]["inconsistencies_count"] == 0


def test_repeated_text_flag(edital_rules):
    from scoring import decide

    content = {"promises": [], "data_density": {}, "repetition": {"significant": True, "duplicated_word_share": 0.79}}
    d = decide(7.0, {}, edital_rules, {"summary": {"advisory": False, "failed": []}}, content, {})
    assert "repeated_text" in d["flags"]
