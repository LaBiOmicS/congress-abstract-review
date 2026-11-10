# Method

## Pipeline

1. **Extraction** (`extract_abstract.py`): text from PDF (PyMuPDF / pdftotext / pdfplumber / pypdf, the cleanest wins), DOCX (body order, tables, inline images) or plain text. Title = first line; authors/affiliations = the following short lines with names, superscripts, institutions or e-mails; sections = PT/EN/ES headings on their own line or opening a sentence followed by `:`. Hidden content (white or microscopic text, hidden DOCX runs, HTML/LaTeX comments) and prompt-injection patterns are scanned and redacted, as in academic-peer-review.
2. **Format detection**: a score from body length (≤ 600 words → simple, > 900 → expanded), reference list, figures/tables/images, pages and number of sections. `confidence: low` when the evidence is mixed: confirm the format.
3. **Compliance** (`abstract_metrics.py`): counts as text editors do (markup removed, whitespace runs = one space, paragraph breaks not counted), over the components in `count_scope`. Structured-abstract headings belong to the body. In an unlabelled block abstract, a mandatory section is `unknown` (the evaluators judge whether the content is there), not failed.
4. **Content audit** (`content_audit.py`):
   - *Promises*: results deferred to the event (high), work in progress or expectations stated as findings (moderate), vague value claims without data (low). Future-work sentences in the conclusion are info.
   - *Data density*: distinct quantitative elements in the results (n, %, ± / SD, CI, p, test statistics, effect sizes, units, performance metrics) per 100 words; years and figure numbers excluded.
   - *Repetition*: sentences that occur more than once in the body (copy-paste errors or padding to reach a word count); ≥ 10 % of the body words duplicated raises the `repeated_text` flag, because counts and data density are then inflated.
   - *Objective × conclusion*: lexical overlap of stems; below 0.1 is a hint, never a verdict.
   - *statcheck*: reported test statistics recomputed against the reported p (decimal commas accepted).
   - Expanded only: figure/table mentions vs captions, DOIs (live check optional).
5. **Area and approach** (`area_profiles.py`): six areas (biological and agricultural, health, exact sciences and computing, engineering, humanities and education, applied social sciences) and eight approaches, from weighted keywords and explicit design declarations ("estudo qualitativo", "revisão integrativa", "relato de experiência"), title and keywords counting more. Below 0.5 confidence the axis is listed for confirmation. The evaluators get the area's checks and the approach's guidance; work with people or animals that does not mention an ethics approval (CEP/CAAE, CEUA) raises `ethics_check` for the committee, never a score cap. Experience reports of teaching or extension activities are exempt (Res. CNS 510/2016).
6. **Evaluation**: each evaluator gets the rules, the barema with the score levels of every criterion, the automated indicators per criterion, the automated checks and the abstract (authors withheld by default), and returns prose plus a `SCORES_JSON` block. Each score is given in two steps: the level whose description matches the evidence, then a value inside that level's range; the justification starts with the level. Roles: alfa (compliance & form), beta (data & rigor), gamma (track & impact); omega covers the three angles alone.
7. **Escalation** (`auto` panel): omega's result goes to the full panel when the final score is within 5 % of the scale from the minimum score, omega's confidence is low, omega's recommended decision differs from the score's, the submission has an integrity flag, or omega recommends approval although results are only promised. Compliance failures alone do not escalate: waiving a rule is the committee's decision.
8. **Committee synthesis** (full panel): consolidated assessment and feedback; score corrections only with a quoted reason (`overrides`), recorded in the sheet.
9. **Track**: the track the authors declared (CSV or `--track`) is the one the submission competes in and whose barema scores it; when the evaluators would place it elsewhere, the sheet says so. Without a declared track, the evaluators' choice fills it in.
10. **Decision** (`scoring.py`, `criteria.py`, deterministic): per-criterion median → synthesis corrections → caps → weighted total → `approved` when it reaches `approval_cutoff`, `rejected` below it, when an `approval_min_scores` entry is not met, or when results are only promised; without `approval_cutoff` the decision is the committee's and the sheet shows the committee synthesis's (or the evaluators') recommendation. The plugin evaluates the abstract only: the presentation modality (oral, poster) is the committee's, and posters are judged at the event. Flags: `compliance_hold` (strict-mode failures, committee audience), `fix_before_submission` (the same failures, author audience), `integrity`, `no_quantitative_results` (quantitative or computational research only), `ethics_check`, `repeated_text`, `escalated`, `chair_override` (the committee synthesis recommended the other decision against the minimum score, with a reason), `incomplete`.

## Evaluation categories and score levels

Every barema criterion is scored against defined levels, never against a bare number:

| Source | When | Levels |
|---|---|---|
| `edital` | the edital's barema describes its levels (`anchors` in `edital.json`) | the edital's own |
| `global` | the criterion is one of the global categories of `templates/criteria_catalog.json` (same id, or `based_on`) | the category's five levels, rescaled to the criterion's range |
| `generic` | neither | five generic levels (exemplary, met, partly met, barely met, absent) |

Global categories, by nature of the work: research `relevance`, `originality`, `objectives`, `methods`, `results`, `conclusion`; innovation `problem`, `solution_stage`, `differential`, `feasibility`, `impact`; extension `community`, `action`, `outcomes`, `dialogue`; all of them `writing`. Without a barema in the edital, each track is scored with the default barema of its `kind`, so a product or an extension action is not judged as a study: the "results without numbers" cap belongs only to research `results`. Each category also carries:

- **Indicators**: automated measures shown to the evaluators and in the sheet next to the criterion (e.g. `results`: data density, inferential statistics, high-severity promises, statcheck; `objectives` and `conclusion`: section present, objective × conclusion overlap; `writing`: compliance failures, repeated text).
- **Variants by research approach** (research tracks only): the levels of `methods` and `results` follow the approach classified from the abstract (`area_profiles.py`, adapted from academic-peer-review for short texts). Quantitative and computational work keep the levels above; qualitative and documentary research are judged by corpus or participants and their selection, a named analysis procedure and findings supported by the material; mixed methods by both strands and their integration; literature reviews by the search strategy and the synthesis of the included studies; theoretical essays by framework, argument and conceptual contribution; case and experience reports by the description of what was done and concrete observations. The "results without numbers" cap applies only to quantitative and computational work. An edital's own levels are never replaced.
- **Caps**: upper bounds applied by code when a signal is present, whatever the evaluators wrote: `results` ≤ 3/10 when results are only promised for the event, ≤ 4/10 when the results contain no numbers; `writing` ≤ 5/10 when ≥ 10 % of the body is repeated. Caps are listed in the sheet and among the reasons. `"apply_caps": false` in the edital's rubric turns them off.

## Audience: committee or author

The audience is independent of the rules: an author can check an abstract against the event's edital before submitting (`--audience author`), or against best practices when there is no edital (the default for the no-edital ruleset).

| | committee | author |
|---|---|---|
| Evaluators' framing | committee members deciding on acceptance | the same evaluation, framed as a prediction for the authors |
| Edital breaches | `compliance_hold`: the committee decides whether to waive | `fix_before_submission`: listed first in the revision plan |
| Feedback | anonymous paragraph for the submission system | numbered revision plan, most impact first, placeholders for missing data |
| Sheet | evaluation sheet | pre-submission check with a "before submitting" checklist (must fix / recommended / check) |
| Batch report | committee report, ranking | pre-submission report (e.g. a supervisor checking a group's abstracts) |

## Report language

Each submission's sheet, checks, checklist and feedback are written in the abstract's own language (Portuguese, English or Spanish; other languages fall back to English). `--language pt|en|es` forces one language for every submission. Batch outputs (spreadsheet, committee report) use the most common language of the batch, unless forced.

## Why the scores are computed, not voted

Evaluators that share one underlying model share its blind spots, so three agreeing evaluators are not three independent opinions. The models are used for what they do well (reading, judging against criteria, writing feedback); aggregation, cutoffs and ranking are deterministic and reproducible, and every departure from them (synthesis corrections, synthesis decision) must carry a written reason that the committee can audit.

## Limitations

- Section and author detection are heuristics; check `structure.json` when a count looks wrong (the evaluators are told to correct the heuristics too).
- Page limits are reliable only for PDF.
- Lexical promise and data-density detection are language-dependent (PT/EN/ES).
- Reports are produced in Portuguese, English or Spanish; abstracts in other languages get English reports.
- No literature search: congress abstracts are judged on their own content.
