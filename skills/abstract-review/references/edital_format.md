# `edital.json` — congress rules

The agent writes `edital.json` from the edital (call for papers); `edital_parser.py validate` checks
it and writes the normalized `rules.json` used by every other script. **Copy what the edital says.
A rule the edital does not state is `null` (or omitted), never a guess.**

```json
{
  "event": {"name": "XV Simpósio de Biotecnologia", "year": 2026, "url": null, "source": "edital"},
  "enforcement": "strict",
  "languages": ["pt"],
  "anonymized": false,
  "formats": {
    "simple": {
      "limits": {
        "words": {"min": 250, "max": 500},
        "characters_with_spaces": {"min": null, "max": null},
        "characters_without_spaces": {"min": null, "max": null},
        "pages": {"min": null, "max": null},
        "count_scope": ["body"]
      },
      "title": {"max_words": null, "max_characters": 200},
      "required_sections": ["introduction", "objectives", "methods", "results", "conclusion"],
      "forbidden_sections": [],
      "figures": {"allowed": false, "max": 0},
      "tables": {"allowed": false, "max": 0},
      "references": {"allowed": false, "min": null, "max": 0},
      "keywords": {"min": 3, "max": 5},
      "max_authors": 8
    },
    "expanded": { "...": "same fields" }
  },
  "tracks": [{"code": "bioinfo", "name": "Bioinformática", "description": "", "kind": "research"}],
  "rubric": {
    "scale": {"min": 0, "max": 10},
    "aggregation": "weighted_mean",
    "criteria": [
      {"id": "relevance", "name": "Relevância", "description": "…", "weight": 2},
      {"id": "metodologia", "name": "Metodologia", "description": "…", "weight": 3, "based_on": "methods"},
      {"id": "apresentacao", "name": "Apresentação", "weight": 1, "max_score": 2,
       "anchors": [{"min": 2, "descriptor": "Clara e completa"}, {"min": 1, "descriptor": "Parcial"}, {"min": 0, "descriptor": "Ausente"}]}
    ],
    "approval_cutoff": 6.0,
    "approval_min_scores": {"methods": 5.0},
    "tie_breakers": ["methods", "relevance"]
  },
  "notes": "",
  "provenance": {
    "formats.simple.limits.words": "Os resumos devem ter entre 250 e 500 palavras, sem contar título, autores e afiliações"
  }
}
```

## Fields

| Field | Meaning |
|---|---|
| `event.source` | `edital` (rules from an edital) or `default` (best-practice ruleset). |
| `enforcement` | `strict`: breaches are compliance failures for the committee. `advisory`: breaches are advice. Default: `strict` for an edital. |
| `languages` | Accepted languages (`pt`, `en`, `es`; others are kept but not detected automatically). Empty = not restricted. |
| `anonymized` | `true` when the edital requires submissions without author identification (blind review): any author line or e-mail in the file fails. |
| `formats` | `simple` and/or `expanded`. Describe only the formats the event accepts: a submission in another format fails `format_allowed`. |
| `limits.*` | `{"min", "max"}`; a bare number means `max`. |
| `limits.count_scope` | Which parts enter the word/character limits: `body` (sections, headings included), `title`, `front_matter` (authors and affiliations), `keywords`, `references`, `funding`. Read the edital carefully ("sem contar título e autores", "incluindo referências"). If the edital is silent, leave it out: the validator assumes `["body"]` and warns. |
| `pages` | Checked on PDFs only; DOCX pages are estimated (~500 words/page) and only warned. |
| `required_sections` | Canonical names: `introduction`, `objectives`, `methods`, `results`, `discussion`, `results_discussion`, `conclusion`, `keywords`, `funding`, `references`. Portuguese/English/Spanish headings are accepted and normalized ("Metodologia" → `methods`). `results_discussion` in the text satisfies both `results` and `discussion`. |
| `figures` / `tables` / `references` | `allowed` (`true`/`false`/`null`), `max`, and for references `min`. |
| `keywords` | `{"min", "max"}` number of keywords. |
| `max_authors` | Maximum number of authors (checked heuristically from the byline). |
| `tracks` | Thematic tracks (eixos). Strings are accepted and turned into `{code, name}`. |
| `tracks[].kind` | `research` (default), `innovation` or `extension`: the nature of the work the track receives. Without a barema in the edital, each kind gets its own default barema (`templates/barema_default.json`, `rubrics_by_kind`): research scores objectives, methods and results with data; innovation scores problem, solution and stage of development, advantage over existing solutions, feasibility and impact; extension scores community and demand, action, outcomes (qualitative evidence counts) and engagement. |
| `tracks[].rubric` | The track's own barema, same fields as `rubric`, when the edital scores that track differently. It inherits the edital's `approval_cutoff` unless it sets one. Precedence: track barema → edital barema → default barema of the track's kind. |
| `rubric` | The barema. Omit it when the edital has none: the default barema is used and the sheet says so. |
| `rubric.aggregation` | `weighted_mean` (score on the scale) or `sum` (points; use `max_score` per criterion when criteria have different maxima, e.g. "0 a 2 pontos"). |
| `rubric.criteria[].based_on` | The global category whose meaning the criterion matches: `relevance`, `originality`, `objectives`, `methods`, `results`, `conclusion`, `writing` (see `templates/criteria_catalog.json`). Not needed when the `id` already is one of them. The criterion inherits the category's score levels, automated indicators and caps. |
| `rubric.criteria[].anchors` | The score levels the edital itself describes for the criterion ("0 = ausente; 1 = parcial; 2 = completo"): `{"min": <lowest score of the level>, "descriptor": "<text>"}`, in the criterion's own scale. They take precedence over the category's levels. |
| `rubric.apply_caps` | `false` turns off the caps of the global categories (e.g. results ≤ 3/10 when only promised). Default `true`. |
| `rubric.approval_cutoff` | Minimum final score for approval; below it, the abstract is rejected. Omit when the edital leaves approval to the committee. When the edital only gives cutoffs per presentation modality ("≥ 8 oral, 6 a 7,9 pôster"), the lowest one is the approval cutoff: the plugin decides approval only, and the modality is the committee's. |
| `rubric.approval_min_scores` | Minimum scores on given criteria for approval (e.g. "serão indeferidos trabalhos com nota inferior a 5 em metodologia"). Minimums that only apply to one presentation modality do not belong here. |
| `rubric.tie_breakers` | Criteria used, in order, to break ties in the ranking (often stated as "critérios de desempate"). |
| `provenance` | Field path → quote from the edital. Strongly recommended: it lets the committee check each rule. |

## Decisions

The plugin evaluates the abstract only and decides **approved** or **rejected**. It does not choose the presentation modality (oral, poster): that is the committee's, and posters and talks are evaluated at the event. An old `edital.json` with `modalities`, per-modality `cutoffs` or `oral_min_scores` still validates: `modalities` and `oral_min_scores` are ignored with a warning, and the lowest cutoff becomes `approval_cutoff`.

## Reading an edital: checklist

- Limits are often different per modality (resumo simples × expandido) and sometimes per category (graduação × pós-graduação): if categories differ, ask the user which one applies or run one batch per category.
- Look for what is excluded from the count ("não serão contabilizados título, autores, afiliações e palavras-chave").
- "Até 3.000 caracteres" without "com/sem espaços": put the value in `characters_with_spaces` (editors' default) and say so in `notes`.
- Barema tables in annexes: copy every criterion with its weight or maximum points.
- Map every criterion to a global category with `based_on` when the meaning matches (e.g. "Metodologia adequada" → `methods`, "Apresentação dos resultados" → `results`, "Clareza e correção da linguagem" → `writing`). Copy the edital's level descriptions into `anchors` when it has them. A criterion with neither gets generic levels and a validation warning.
- Rules that are not checkable from the file (submission deadline, registration fee, presenting author registered) do not belong in `edital.json`; mention them in `notes`.
