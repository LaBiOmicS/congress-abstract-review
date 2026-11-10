"""Fixed texts of the deliverables in Portuguese, English and Spanish.

The report language follows the language of each abstract (`report_language`): a submission in
English gets its sheet, checks and feedback in English. Unsupported languages fall back to English.
`--language pt|en|es` in `congress_review.py prepare` forces one language for every submission.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

LANGS = ("pt", "en", "es")
FALLBACK = "en"


def report_language(requested: str | None, detected: str | None) -> str:
    """Explicit pt/en/es wins; otherwise ('auto' or None) the abstract's own language."""
    if requested in LANGS:
        return requested
    return detected if detected in LANGS else FALLBACK


def batch_language(requested: str | None, detected: list[str]) -> str:
    """Language of the batch-level outputs: the requested one, else the most common among the submissions."""
    if requested in LANGS:
        return requested
    langs = [report_language(None, d) for d in detected]
    return Counter(langs).most_common(1)[0][0] if langs else FALLBACK


# key: (pt, en, es)
M: dict[str, tuple[str, str, str]] = {
    # --- scoring reasons -------------------------------------------------------------------
    "score_to_decision": ("nota {total} → {decision} (nota mínima para aprovação: {cutoff})", "score {total} → {decision} (minimum score for approval: {cutoff})",
                          "nota {total} → {decision} (nota mínima para aprobación: {cutoff})"),
    "min_unmet": ("notas mínimas por critério não atingidas: {items}", "minimum criterion scores not met: {items}", "notas mínimas por criterio no alcanzadas: {items}"),
    "approval_blocked_promises": ("aprovação bloqueada: há resultados só prometidos para o evento", "approval blocked: results are only promised for the event",
                                  "aprobación bloqueada: hay resultados solo prometidos para el evento"),
    "no_cutoffs": ("o edital não define nota mínima: a comissão decide a aprovação", "the edital sets no minimum score: the committee decides on approval",
                   "la convocatoria no define nota mínima: el comité decide la aprobación"),
    "breach_committee": ("descumprimento de normas a decidir pela comissão: {items}", "rule breaches for the committee to decide on: {items}",
                         "incumplimiento de normas a decidir por el comité: {items}"),
    "breach_author": ("normas do edital a corrigir antes de submeter: {items}", "edital rules to fix before submitting: {items}",
                      "normas de la convocatoria a corregir antes de enviar: {items}"),
    "integrity": ("possível tentativa de manipular a avaliação (conteúdo oculto ou instruções embutidas)",
                  "possible attempt to manipulate the evaluation (hidden content or embedded instructions)",
                  "posible intento de manipular la evaluación (contenido oculto o instrucciones incrustadas)"),
    "repeated": ("texto repetido: {pct} % das palavras do corpo são cópias", "repeated text: {pct} % of the body words are copies",
                 "texto repetido: el {pct} % de las palabras del cuerpo son copias"),
    "chair_recommends": ("síntese da comissão recomenda {decision}: {note}", "the committee synthesis recommends {decision}: {note}", "la síntesis del comité recomienda {decision}: {note}"),
    "panel_recommends": ("síntese do painel recomenda {decision}: {note}", "the panel synthesis recommends {decision}: {note}",
                         "la síntesis del panel recomienda {decision}: {note}"),
    "esc_invalid": ("avaliação única inválida", "invalid single evaluation", "evaluación única inválida"),
    "esc_margin": ("nota a {margin} da nota mínima (limítrofe)", "score {margin} from the minimum score (borderline)", "nota a {margin} de la nota mínima (limítrofe)"),
    "esc_low_conf": ("avaliador com baixa confiança", "evaluator with low confidence", "evaluador con baja confianza"),
    "esc_mismatch": ("avaliador recomendou {a}, a nota dá {b}", "evaluator recommended {a}, the score gives {b}", "el evaluador recomendó {a}, la nota da {b}"),
    "esc_integrity": ("alerta de integridade", "integrity alert", "alerta de integridad"),
    "esc_promises": ("resultados prometidos, mas avaliador recomendou aprovar", "results only promised, but the evaluator recommended approval",
                     "resultados prometidos, pero el evaluador recomendó aprobar"),
    "decision_word": ("decisão", "decision", "decisión"),
    "conf_synthesis": ("Síntese da comissão", "Committee synthesis", "Síntesis del comité"),
    "conf_high": ("alta", "high", "alta"),
    "conf_medium": ("média", "medium", "media"),
    "conf_low": ("baixa", "low", "baja"),
    # --- decisions and flags -----------------------------------------------------------------
    "dec_approved": ("Aprovado", "Approved", "Aprobado"),
    "dec_rejected": ("Indeferido", "Rejected", "Rechazado"),
    "dec_undecided": ("a definir pela comissão", "to be decided by the committee", "a definir por el comité"),
    "flag_compliance_hold": ("Normas do edital: decisão da comissão", "Edital rules: committee decision", "Normas de la convocatoria: decisión del comité"),
    "flag_fix_before_submission": ("Normas do edital: corrigir antes de submeter", "Edital rules: fix before submitting",
                                   "Normas de la convocatoria: corregir antes de enviar"),
    "flag_integrity": ("Alerta de integridade", "Integrity alert", "Alerta de integridad"),
    "flag_no_quantitative_results": ("Resultados sem dados numéricos", "Results without numerical data", "Resultados sin datos numéricos"),
    "flag_ethics_check": ("Verificar aprovação ética (CEP/CEUA)", "Check ethics approval (IRB/animal ethics)", "Verificar aprobación ética (comité de ética)"),
    "ethics_check": ("o trabalho envolve pessoas ou animais e o resumo não menciona aprovação ética (CEP/CAAE ou CEUA): a comissão verifica",
                     "the work involves people or animals and the abstract does not mention an ethics approval: the committee checks",
                     "el trabajo involucra personas o animales y el resumen no menciona aprobación ética: el comité verifica"),
    "page": ("página", "page", "página"),
    "track_suggested": ("os avaliadores sugerem o eixo {track}; a submissão foi avaliada no eixo declarado",
                        "the evaluators suggest the track {track}; the submission was evaluated in the declared track",
                        "los evaluadores sugieren el eje {track}; el trabajo se evaluó en el eje declarado"),
    "profile": ("Área e abordagem", "Area and approach", "Área y enfoque"),
    "profile_low_conf": ("classificação automática com baixa confiança", "automatic classification, low confidence", "clasificación automática con baja confianza"),
    "area_none": ("área não identificada", "area not identified", "área no identificada"),
    "area_biologicas": ("Ciências Biológicas e Agrárias", "Biological and agricultural sciences", "Ciencias Biológicas y Agrarias"),
    "area_saude": ("Ciências da Saúde", "Health sciences", "Ciencias de la Salud"),
    "area_exatas": ("Ciências Exatas e da Computação", "Exact sciences and computing", "Ciencias Exactas y de la Computación"),
    "area_engenharias": ("Engenharias", "Engineering", "Ingenierías"),
    "area_humanas": ("Ciências Humanas e Educação", "Humanities and education", "Ciencias Humanas y Educación"),
    "area_sociais_aplicadas": ("Ciências Sociais Aplicadas", "Applied social sciences", "Ciencias Sociales Aplicadas"),
    "app_quantitative": ("pesquisa quantitativa", "quantitative research", "investigación cuantitativa"),
    "app_qualitative": ("pesquisa qualitativa", "qualitative research", "investigación cualitativa"),
    "app_documentary": ("pesquisa documental", "documentary research", "investigación documental"),
    "app_mixed": ("métodos mistos", "mixed methods", "métodos mixtos"),
    "app_review": ("revisão de literatura", "literature review", "revisión de literatura"),
    "app_theoretical": ("estudo teórico", "theoretical study", "estudio teórico"),
    "app_computational": ("estudo computacional", "computational study", "estudio computacional"),
    "app_case_report": ("relato de caso ou de experiência", "case or experience report", "relato de caso o de experiencia"),
    "flag_repeated_text": ("Texto repetido (cópia ou enchimento)", "Repeated text (copy-paste or padding)", "Texto repetido (copia o relleno)"),
    "flag_escalated": ("Avaliado pelo painel completo", "Evaluated by the full panel", "Evaluado por el panel completo"),
    "flag_chair_override": ("Decisão alterada na síntese da comissão", "Decision changed in the committee synthesis", "Decisión cambiada en la síntesis del comité"),
    "flag_incomplete": ("Avaliação incompleta", "Incomplete evaluation", "Evaluación incompleta"),
    # --- evaluation sheet ----------------------------------------------------------------------
    "ai_committee": (
        "Rascunho elaborado com assistência de IA. Um membro humano da comissão científica deve conferir, editar e assinar esta avaliação "
        "antes de qualquer uso; a responsabilidade pela decisão é da comissão.",
        "Draft prepared with AI assistance. A human member of the scientific committee must check, edit and sign this evaluation before any use; "
        "the committee is responsible for the decision.",
        "Borrador elaborado con asistencia de IA. Un miembro humano del comité científico debe revisar, editar y firmar esta evaluación antes de "
        "cualquier uso; la responsabilidad de la decisión es del comité.",
    ),
    "ai_author": (
        "Pré-avaliação elaborada com assistência de IA. Estima como a comissão avaliaria o resumo hoje; não substitui a avaliação do evento nem "
        "garante aceite. Confira cada sugestão antes de aplicá-la.",
        "Pre-submission check prepared with AI assistance. It estimates how the committee would score the abstract today; it does not replace the "
        "event's evaluation or guarantee acceptance. Check every suggestion before applying it.",
        "Preevaluación elaborada con asistencia de IA. Estima cómo el comité evaluaría el resumen hoy; no sustituye la evaluación del evento ni "
        "garantiza la aceptación. Revise cada sugerencia antes de aplicarla.",
    ),
    "congress": ("Congresso", "Congress", "Congreso"),
    "sheet_title_committee": ("Ficha de avaliação", "Evaluation sheet", "Ficha de evaluación"),
    "sheet_title_author": ("Pré-avaliação do resumo", "Pre-submission check", "Preevaluación del resumen"),
    "submission": ("Submissão", "Submission", "Envío"),
    "file": ("arquivo", "file", "archivo"),
    "title": ("Título", "Title", "Título"),
    "format": ("Formato", "Format", "Formato"),
    "fmt_simple": ("resumo simples", "abstract", "resumen simple"),
    "fmt_expanded": ("resumo expandido", "expanded abstract", "resumen extendido"),
    "track": ("Eixo temático", "Thematic track", "Eje temático"),
    "evaluation": ("Avaliação", "Evaluation", "Evaluación"),
    "norm_ref": ("Referência normativa", "Rules", "Referencia normativa"),
    "norm_edital": ("edital do evento", "the event's edital", "convocatoria del evento"),
    "norm_default": ("boas práticas (sem edital)", "best practices (no edital)", "buenas prácticas (sin convocatoria)"),
    "norm_default_barema_innovation": (" · barema padrão de inovação (o edital não traz barema)", " · default innovation barema (the edital has none)",
                                       " · baremo predeterminado de innovación (la convocatoria no tiene baremo)"),
    "norm_default_barema_extension": (" · barema padrão de extensão (o edital não traz barema)", " · default extension barema (the edital has none)",
                                      " · baremo predeterminado de extensión (la convocatoria no tiene baremo)"),
    "norm_kind_innovation": ("barema de inovação", "innovation barema", "baremo de innovación"),
    "norm_kind_extension": ("barema de extensão", "extension barema", "baremo de extensión"),
    "norm_default_barema": (" · barema padrão (o edital não traz barema)", " · default barema (the edital has none)",
                            " · baremo por defecto (la convocatoria no trae baremo)"),
    "report_language": ("Idioma do relatório", "Report language", "Idioma del informe"),
    "lang_pt": ("português", "Portuguese", "portugués"),
    "lang_en": ("inglês", "English", "inglés"),
    "lang_es": ("espanhol", "Spanish", "español"),
    "result": ("Resultado", "Result", "Resultado"),
    "result_author": ("Resultado estimado", "Estimated result", "Resultado estimado"),
    "final_score": ("Nota final", "Final score", "Nota final"),
    "estimated_score": ("Nota estimada", "Estimated score", "Nota estimada"),
    "scale": ("escala", "scale", "escala"),
    "suggested_decision": ("Decisão sugerida", "Suggested decision", "Decisión sugerida"),
    "likely_decision": ("Decisão provável", "Likely decision", "Decisión probable"),
    "evaluators_recommend": ("Recomendação dos avaliadores", "Evaluators' recommendation", "Recomendación de los evaluadores"),
    "flags": ("Sinalizações", "Flags", "Alertas"),
    "barema": ("Barema", "Barema (scoring rubric)", "Baremo"),
    "col_criterion": ("Critério", "Criterion", "Criterio"),
    "col_weight": ("Peso", "Weight", "Peso"),
    "col_score": ("Nota", "Score", "Nota"),
    "col_spread": ("Divergência entre avaliadores", "Spread among evaluators", "Divergencia entre evaluadores"),
    "col_evidence": ("Métricas automáticas", "Automated indicators", "Métricas automáticas"),
    "overrides": ("Correções na síntese da comissão:", "Corrections in the committee synthesis:", "Correcciones en la síntesis del comité:"),
    "overrides_author": ("Correções da síntese do painel:", "Corrections by the panel synthesis:", "Correcciones de la síntesis del panel:"),
    "escalated_because": ("Enviado ao painel completo porque: {reasons}.", "Sent to the full panel because: {reasons}.", "Enviado al panel completo porque: {reasons}."),
    "assessment": ("Avaliação consolidada", "Consolidated assessment", "Evaluación consolidada"),
    "disagreements": ("Divergências entre avaliadores", "Disagreements among evaluators", "Divergencias entre evaluadores"),
    "feedback_committee": ("Parecer aos autores", "Feedback to the authors", "Dictamen a los autores"),
    "feedback_author": ("Plano de revisão", "Revision plan", "Plan de revisión"),
    "no_feedback": ("_(sem parecer)_", "_(no feedback)_", "_(sin dictamen)_"),
    "confidential_committee": ("Comentários confidenciais à comissão", "Confidential comments to the committee", "Comentarios confidenciales al comité"),
    "confidential_author": ("Outros riscos antes de submeter", "Other risks before submitting", "Otros riesgos antes de enviar"),
    "individual": ("Avaliações individuais", "Individual evaluations", "Evaluaciones individuales"),
    "confidence": ("confiança", "confidence", "confianza"),
    "score_lc": ("nota", "score", "nota"),
    "checklist": ("Antes de submeter", "Before submitting", "Antes de enviar"),
    "checklist_none": ("Nenhuma pendência automática encontrada.", "No automated issue found.", "No se encontraron pendientes automáticos."),
    "prio_obrigatório": ("obrigatório", "must fix", "obligatorio"),
    "prio_recomendado": ("recomendado", "recommended", "recomendado"),
    "prio_conferir": ("conferir", "check", "verificar"),
    "panel_full": ("painel completo (alfa, beta, gama + síntese da comissão)", "full panel (alfa, beta, gamma + committee synthesis)", "panel completo (alfa, beta, gamma + síntesis del comité)"),
    "panel_full_author": ("painel completo (alfa, beta, gama + síntese)", "full panel (alfa, beta, gamma + synthesis)", "panel completo (alfa, beta, gamma + síntesis)"),
    "panel_escalated": (" — escalonado da avaliação única", " — escalated from the single evaluation", " — escalado desde la evaluación única"),
    "panel_single": ("avaliação única (omega)", "single evaluation (omega)", "evaluación única (omega)"),
    "feedback_doc_committee": ("Parecer", "Feedback", "Dictamen"),
    "work": ("Trabalho", "Submission", "Trabajo"),
    # --- pre-submission checklist ------------------------------------------------------------
    "ck_observed": ("observado {v}", "observed {v}", "observado {v}"),
    "ck_limit": ("limite {v}", "limit {v}", "límite {v}"),
    "ck_promises": ("Resultados prometidos para o evento", "Results promised for the event", "Resultados prometidos para el evento"),
    "ck_promises_d": ("{n} trecho(s), p. ex. “{q}”: apresente os resultados já obtidos", "{n} passage(s), e.g. “{q}”: report the results you already have",
                      "{n} pasaje(s), p. ej. “{q}”: presente los resultados ya obtenidos"),
    "ck_numbers": ("Resultados sem dados numéricos", "Results without numerical data", "Resultados sin datos numéricos"),
    "ck_numbers_d": ("informe n, magnitude do efeito e incerteza", "report n, effect size and uncertainty", "informe n, magnitud del efecto e incertidumbre"),
    "ck_repeated": ("Texto repetido", "Repeated text", "Texto repetido"),
    "ck_repeated_d": ("remova os trechos duplicados", "remove the duplicated passages", "elimine los pasajes duplicados"),
    "ck_hidden": ("Texto oculto ou instruções a avaliadores de IA", "Hidden text or instructions to AI evaluators", "Texto oculto o instrucciones a evaluadores de IA"),
    "ck_hidden_d": ("remova antes de submeter: comissões tratam isso como caso de integridade",
                    "remove it before submitting: committees treat it as an integrity case",
                    "elimínelo antes de enviar: los comités lo tratan como un caso de integridad"),
    # --- batch -------------------------------------------------------------------------------
    "batch_title_committee": ("Relatório da comissão", "Committee report", "Informe del comité"),
    "batch_title_author": ("Relatório de pré-avaliação", "Pre-submission report", "Informe de preevaluación"),
    "batch_evaluated": ("Submissões avaliadas", "Submissions evaluated", "Envíos evaluados"),
    "batch_failed": ("Submissões não processadas: **{n}** (ver ao final)", "Submissions not processed: **{n}** (see the end)",
                     "Envíos no procesados: **{n}** (ver al final)"),
    "col_decision": ("Decisão", "Decision", "Decisión"),
    "col_submissions": ("Submissões", "Submissions", "Envíos"),
    "undecided": ("a definir", "undecided", "a definir"),
    "for_committee": ("Para decisão da comissão", "For committee decision", "Para decisión del comité"),
    "for_author": ("Com pendências", "With pending issues", "Con pendientes"),
    "none": ("Nenhuma.", "None.", "Ninguna."),
    "col_id": ("Id", "Id", "Id"),
    "col_title": ("Título", "Title", "Título"),
    "col_suggested": ("Sugerida", "Suggested", "Sugerida"),
    "by_track": ("Classificação por eixo", "Ranking by track", "Clasificación por eje"),
    "no_track": ("Sem eixo", "No track", "Sin eje"),
    "not_processed": ("Não processadas", "Not processed", "No procesados"),
    "xlsx_scores": ("Notas", "Scores", "Notas"),
    "xlsx_cutoffs": ("nota mínima para aprovação", "minimum score for approval", "nota mínima para aprobación"),
    "xlsx_crit_header": ("id|critério|peso|nota máxima|descrição|âncoras", "id|criterion|weight|max score|description|anchors",
                         "id|criterio|peso|nota máxima|descripción|anclas"),
    "csv_header": (
        "rank|rank_eixo|id|arquivo|titulo|formato|idioma|eixo|nota_final|{crit}|decisao_sugerida|recomendacao_avaliadores|avaliacao|sinalizacoes|conformidade_falhas|promessas_altas|motivos|area|abordagem",
        "rank|rank_track|id|file|title|format|language|track|final_score|{crit}|suggested_decision|evaluators_recommendation|evaluation|flags|compliance_failures|high_promises|reasons|area|approach",
        "rank|rank_eje|id|archivo|titulo|formato|idioma|eje|nota_final|{crit}|decision_sugerida|recomendacion_evaluadores|evaluacion|alertas|incumplimientos|promesas_altas|motivos|area|enfoque",
    ),
    # --- compliance checks (abstract_metrics) --------------------------------------------------
    "m_title": ("Conformidade e métricas", "Compliance and metrics", "Conformidad y métricas"),
    "m_format": ("Formato avaliado", "Format evaluated", "Formato evaluado"),
    "m_ref": ("referência", "rules", "referencia"),
    "m_count": ("Contagem ({scope}): {w} palavras · {cw} caracteres com espaços · {cn} sem espaços",
                "Count ({scope}): {w} words · {cw} characters with spaces · {cn} without spaces",
                "Conteo ({scope}): {w} palabras · {cw} caracteres con espacios · {cn} sin espacios"),
    "m_result": ("Resultado: {p} OK · {f} falha(s) · {w} atenção · {u} a verificar", "Result: {p} OK · {f} failure(s) · {w} warning(s) · {u} to check",
                 "Resultado: {p} OK · {f} falla(s) · {w} atención · {u} a verificar"),
    "m_cols": ("| Item | Observado | Limite | Situação | Nota |", "| Item | Observed | Limit | Status | Note |", "| Ítem | Observado | Límite | Situación | Nota |"),
    "m_per_section": ("Palavras por seção", "Words per section", "Palabras por sección"),
    "m_sec_cols": ("| Seção | Palavras | Caracteres c/ espaços |", "| Section | Words | Characters incl. spaces |", "| Sección | Palabras | Caracteres c/ espacios |"),
    "yes": ("sim", "yes", "sí"),
    "no": ("não", "no", "no"),
    "st_pass": ("OK", "OK", "OK"),
    "st_fail": ("FALHA", "FAIL", "FALLA"),
    "st_warn": ("ATENÇÃO", "WARNING", "ATENCIÓN"),
    "st_unknown": ("VERIFICAR", "CHECK", "VERIFICAR"),
    "c_body": ("corpo", "body", "cuerpo"),
    "c_title": ("título", "title", "título"),
    "c_front_matter": ("autores e afiliações", "authors and affiliations", "autores y afiliaciones"),
    "c_keywords": ("palavras-chave", "keywords", "palabras clave"),
    "c_references": ("referências", "references", "referencias"),
    "c_funding": ("apoio", "funding", "financiación"),
    "s_introduction": ("Introdução", "Introduction", "Introducción"),
    "s_objectives": ("Objetivos", "Objectives", "Objetivos"),
    "s_methods": ("Métodos", "Methods", "Métodos"),
    "s_results": ("Resultados", "Results", "Resultados"),
    "s_discussion": ("Discussão", "Discussion", "Discusión"),
    "s_results_discussion": ("Resultados e Discussão", "Results and Discussion", "Resultados y Discusión"),
    "s_conclusion": ("Conclusão", "Conclusion", "Conclusión"),
    "s_keywords": ("Palavras-chave", "Keywords", "Palabras clave"),
    "s_funding": ("Apoio/Agradecimentos", "Funding/Acknowledgements", "Financiación/Agradecimientos"),
    "s_references": ("Referências", "References", "Referencias"),
    "s_unlabelled": ("Texto sem rótulo", "Unlabelled text", "Texto sin rótulo"),
    "k_format_allowed": ("Formato de resumo aceito pelo evento", "Abstract type accepted by the event", "Tipo de resumen aceptado por el evento"),
    "k_format_allowed_n": ("O edital só descreve {other}; a submissão parece um resumo '{fmt}'.", "The edital only describes {other}; the submission looks like a '{fmt}' abstract.",
                           "La convocatoria solo describe {other}; el envío parece un resumen '{fmt}'."),
    "k_words": ("Palavras", "Words", "Palabras"),
    "k_characters_with_spaces": ("Caracteres com espaços", "Characters with spaces", "Caracteres con espacios"),
    "k_characters_without_spaces": ("Caracteres sem espaços", "Characters without spaces", "Caracteres sin espacios"),
    "k_excess": ("Excede em {n}.", "{n} over.", "Excede en {n}."),
    "k_pages": ("Páginas", "Pages", "Páginas"),
    "k_pages_none": ("Formato sem paginação (TXT/MD): confira no PDF final.", "Format without pages (TXT/MD): check the final PDF.",
                     "Formato sin paginación (TXT/MD): verifique en el PDF final."),
    "k_pages_est": ("Estimado em ~500 palavras por página (DOCX).", "Estimated at ~500 words per page (DOCX).", "Estimado en ~500 palabras por página (DOCX)."),
    "k_title_words": ("Título (palavras)", "Title (words)", "Título (palabras)"),
    "k_title_chars": ("Título (caracteres)", "Title (characters)", "Título (caracteres)"),
    "k_required": ("Seção obrigatória: {s}", "Mandatory section: {s}", "Sección obligatoria: {s}"),
    "k_required_v": ("obrigatória", "required", "obligatoria"),
    "k_unlabelled_v": ("sem rótulos", "no labels", "sin rótulos"),
    "k_unlabelled_n": ("Resumo em bloco único: verifique se o conteúdo da seção está presente.", "Single-block abstract: check whether the section's content is present.",
                       "Resumen en bloque único: verifique si el contenido de la sección está presente."),
    "k_forbidden": ("Seção não permitida: {s}", "Section not allowed: {s}", "Sección no permitida: {s}"),
    "k_forbidden_v": ("proibida", "forbidden", "prohibida"),
    "k_figures": ("Figuras", "Figures", "Figuras"),
    "k_tables": ("Tabelas", "Tables", "Tablas"),
    "k_references": ("Referências", "References", "Referencias"),
    "k_not_allowed": ("{label} (não permitidas)", "{label} (not allowed)", "{label} (no permitidas)"),
    "k_keywords": ("Palavras-chave", "Keywords", "Palabras clave"),
    "k_authors": ("Número de autores", "Number of authors", "Número de autores"),
    "k_authors_none": ("Linha de autores não identificada.", "Author line not identified.", "Línea de autores no identificada."),
    "k_authors_heur": ("Contagem heurística a partir da linha de autoria.", "Heuristic count from the author line.", "Conteo heurístico a partir de la línea de autoría."),
    "k_language": ("Idioma", "Language", "Idioma"),
    "k_anon": ("Anonimato (avaliação cega)", "Anonymity (blind review)", "Anonimato (evaluación ciega)"),
    "k_anon_exposed": ("autoria visível", "authors visible", "autoría visible"),
    "k_anon_ok": ("sem autoria", "no authors", "sin autoría"),
    "k_anon_limit": ("sem identificação", "no identification", "sin identificación"),
    "k_anon_n": ("Nomes, afiliações ou e-mails aparecem no arquivo.", "Names, affiliations or e-mails appear in the file.",
                 "Nombres, afiliaciones o correos aparecen en el archivo."),
    "k_security": ("Conteúdo oculto / instruções embutidas", "Hidden content / embedded instructions", "Contenido oculto / instrucciones incrustadas"),
    "k_security_n": ("Verifique o relatório de segurança: possível tentativa de manipular a avaliação.",
                     "Check the security report: possible attempt to manipulate the evaluation.",
                     "Verifique el informe de seguridad: posible intento de manipular la evaluación."),
    # --- content audit -------------------------------------------------------------------------
    "a_title": ("Auditoria de conteúdo", "Content audit", "Auditoría de contenido"),
    "a_promises": ("Promessas e trabalho não concluído — {h} alta(s) · {m} média(s) · {lo} baixa(s)",
                   "Promises and unfinished work — {h} high · {m} moderate · {lo} low",
                   "Promesas y trabajo no concluido — {h} alta(s) · {m} media(s) · {lo} baja(s)"),
    "a_prom_cols": ("| Gravidade | Tipo | Seção | Trecho |", "| Severity | Type | Section | Passage |", "| Gravedad | Tipo | Sección | Pasaje |"),
    "a_no_promises": ("Nenhuma promessa de dados futuros encontrada.", "No promise of future data found.", "No se encontraron promesas de datos futuros."),
    "sev_high": ("ALTA", "HIGH", "ALTA"),
    "sev_moderate": ("MÉDIA", "MODERATE", "MEDIA"),
    "sev_low": ("BAIXA", "LOW", "BAJA"),
    "sev_info": ("info", "info", "info"),
    "cat_deferred_results": ("Resultados adiados para o evento", "Results deferred to the event", "Resultados aplazados para el evento"),
    "cat_ongoing_work": ("Trabalho em andamento", "Work in progress", "Trabajo en curso"),
    "cat_expectation": ("Expectativa no lugar de resultado", "Expectation instead of a result", "Expectativa en lugar de resultado"),
    "cat_vague_claim": ("Afirmação vaga sem dados", "Vague claim without data", "Afirmación vaga sin datos"),
    "cat_perspective": ("Perspectiva (não conta)", "Perspective (not counted)", "Perspectiva (no cuenta)"),
    "a_density": ("Densidade de dados", "Data density", "Densidad de datos"),
    "a_scope_results": ("resultados", "results", "resultados"),
    "a_scope_body": ("corpo (sem seção de resultados rotulada)", "body (no labelled results section)", "cuerpo (sin sección de resultados rotulada)"),
    "a_density_line": ("Escopo: {scope} ({w} palavras) · {n} elementos quantitativos · {p} por 100 palavras · nível **{lvl}**",
                       "Scope: {scope} ({w} words) · {n} quantitative items · {p} per 100 words · level **{lvl}**",
                       "Alcance: {scope} ({w} palabras) · {n} elementos cuantitativos · {p} por 100 palabras · nivel **{lvl}**"),
    "lvl_none": ("nenhum", "none", "ninguno"),
    "lvl_low": ("baixo", "low", "bajo"),
    "lvl_adequate": ("adequado", "adequate", "adecuado"),
    "lvl_high": ("alto", "high", "alto"),
    "a_kinds": ("Tipos", "Kinds", "Tipos"),
    "a_inferential": ("Estatística inferencial (p, teste, IC, tamanho de efeito)", "Inferential statistics (p, test, CI, effect size)",
                      "Estadística inferencial (p, prueba, IC, tamaño del efecto)"),
    "a_no_numbers": ("**Os resultados não trazem nenhum número.**", "**The results contain no numbers.**", "**Los resultados no traen ningún número.**"),
    "a_repeated": ("Texto repetido", "Repeated text", "Texto repetido"),
    "a_repeated_line": ("{s} frase(s) repetida(s), {c} cópia(s) a mais · {pct} % das palavras do corpo", "{s} repeated sentence(s), {c} extra cop(ies) · {pct} % of the body words",
                        "{s} frase(s) repetida(s), {c} copia(s) de más · {pct} % de las palabras del cuerpo"),
    "a_repeated_sig": (" — **contagens e densidade de dados ficam infladas; confira se é a versão correta**",
                       " — **counts and data density are inflated; check that this is the right version**",
                       " — **los conteos y la densidad de datos quedan inflados; verifique que sea la versión correcta**"),
    "a_obj": ("Objetivo × conclusão", "Objective × conclusion", "Objetivo × conclusión"),
    "a_overlap": ("Sobreposição lexical: {v}", "Lexical overlap: {v}", "Superposición léxica: {v}"),
    "a_overlap_weak": (" (fraca: confira se a conclusão responde ao objetivo)", " (weak: check that the conclusion answers the objective)",
                       " (débil: verifique que la conclusión responda al objetivo)"),
    "a_shared": ("Termos em comum", "Shared terms", "Términos en común"),
    "a_obj_missing": ("Objetivo ou conclusão não identificados no texto.", "Objective or conclusion not identified in the text.",
                      "Objetivo o conclusión no identificados en el texto."),
    "a_stat": ("Estatística (statcheck)", "Statistics (statcheck)", "Estadística (statcheck)"),
    "a_stat_line": ("Testes conferidos: {n} · inconsistências: {i} · erros de decisão (α = 0,05): {d}", "Tests checked: {n} · inconsistencies: {i} · decision errors (α = 0.05): {d}",
                    "Pruebas verificadas: {n} · inconsistencias: {i} · errores de decisión (α = 0,05): {d}"),
    "a_stat_p": ("p recalculado", "recomputed p", "p recalculado"),
    "a_figs": ("Figuras e tabelas", "Figures and tables", "Figuras y tablas"),
    "a_captions": ("Legendas encontradas", "Captions found", "Leyendas encontradas"),
    "a_no_caption": ("Citadas no texto sem legenda", "Mentioned in the text without a caption", "Citadas en el texto sin leyenda"),
    "a_never_cited": ("Com legenda, nunca citadas no texto", "Captioned but never mentioned in the text", "Con leyenda, nunca citadas en el texto"),
    "a_refs": ("Referências", "References", "Referencias"),
    "a_dois": ("DOIs encontrados", "DOIs found", "DOIs encontrados"),
    "a_verified": ("Verificados", "Verified", "Verificados"),
    "none_lc": ("nenhum", "none", "ninguno"),
    "none_f": ("nenhuma", "none", "ninguna"),
    # --- criteria indicators and caps ---------------------------------------------------------
    "cap_reason": ("nota de “{c}” limitada a {v}: {why}", "“{c}” score capped at {v}: {why}", "nota de “{c}” limitada a {v}: {why}"),
    "caps_title": ("Limites aplicados pelo código:", "Caps applied by code:", "Límites aplicados por el código:"),
    "i_overlap": ("objetivo × conclusão {v}", "objective × conclusion {v}", "objetivo × conclusión {v}"),
    "i_density": ("densidade de dados {lvl} ({p}/100 palavras)", "data density {lvl} ({p}/100 words)", "densidad de datos {lvl} ({p}/100 palabras)"),
    "i_inferential": ("estatística inferencial: {v}", "inferential statistics: {v}", "estadística inferencial: {v}"),
    "i_promises": ("promessas altas: {n}", "high-severity promises: {n}", "promesas altas: {n}"),
    "i_statcheck": ("statcheck: {i} inconsistência(s) em {n} teste(s)", "statcheck: {i} inconsistenc(ies) in {n} test(s)", "statcheck: {i} inconsistencia(s) en {n} prueba(s)"),
    "i_compliance": ("conformidade: {f} falha(s), {w} atenção", "compliance: {f} failure(s), {w} warning(s)", "conformidad: {f} falla(s), {w} atención"),
    "i_repetition": ("texto repetido: {pct} %", "repeated text: {pct} %", "texto repetido: {pct} %"),
    "anchors_src_edital": ("níveis do edital", "levels from the edital", "niveles de la convocatoria"),
    "anchors_src_global": ("categoria global", "global category", "categoría global"),
    "anchors_src_generic": ("níveis genéricos", "generic levels", "niveles genéricos"),
    "anchors_title": ("Níveis de pontuação por critério", "Score levels per criterion", "Niveles de puntuación por criterio"),
}


def t(lang: str, key: str, **kw: Any) -> str:
    texts = M[key]
    s = texts[LANGS.index(lang)] if lang in LANGS else texts[LANGS.index(FALLBACK)]
    return s.format(**kw) if kw else s


def has(key: str) -> bool:
    return key in M


def dec_label(d: str | None, lang: str) -> str:
    if not d:
        return t(lang, "dec_undecided")
    return t(lang, f"dec_{d}") if has(f"dec_{d}") else d


def score(v: Any, lang: str) -> str:
    """Final scores always with two decimals (7,00 · 5,41), so the ranking reads unambiguously."""
    if v is None:
        return "—"
    s = f"{float(v):.2f}"
    return s if lang == "en" else s.replace(".", ",")


def flag_label(f: str, lang: str) -> str:
    return t(lang, f"flag_{f}") if has(f"flag_{f}") else f


def section_label(name: str, lang: str) -> str:
    return t(lang, f"s_{name}") if has(f"s_{name}") else name


def num(v: Any, lang: str) -> str:
    """Numbers with a decimal comma in pt/es, a point in en."""
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return s if lang == "en" else s.replace(".", ",")
    return str(v)
