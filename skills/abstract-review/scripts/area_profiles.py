"""Area and research approach of a congress abstract, with confidence, plus ethics signals.

Adapted for short texts from academic-peer-review (skills/paper-review/scripts/area_profiles.py):
the same idea (weighted keyword and design-declaration signals, title and keywords counting more,
a confidence that falls when evidence is thin), with the areas split as Brazilian committees use
them (Humanas apart from Sociais Aplicadas) and the approaches common in congress abstracts
(literature review, case or experience report, documentary research).

- Area sets the context the evaluators read the work in and the field-specific checks.
- Approach sets the ruler for `methods` and `results` in research tracks (see `criteria.py`):
  a qualitative study is not scored as if it lacked statistics, a review is judged by its search
  and synthesis, a theoretical essay by its argument.
- Ethics: research with people or animals that does not mention an ethics approval is flagged for
  the committee to check (Res. CNS 466/2012 and 510/2016; CEUA for animals). Never a score cap.

Pure functions; no I/O.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

_ACRONYM_TOKEN = re.compile(r"\\b([A-Z][A-Z0-9]{1,6})\\b")


@cache
def _pat(p: str) -> re.Pattern[str]:
    """Case-insensitive pattern whose all-caps acronyms stay case-sensitive ("SUS" ≠ "sus")."""
    return re.compile(_ACRONYM_TOKEN.sub(r"(?-i:\\b\1\\b)", p), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Areas
# ---------------------------------------------------------------------------

AREAS: dict[str, dict[str, Any]] = {
    "biologicas": {
        "keywords": [
            r"\b(?:gen[ée]tic\w*|genom\w*|g[eê]nic\w*|genes?|transcript\w*|prote[ôo]m\w*|bioinform\w+|biologia\s+molecular|molecular\s+biology|biotecnol\w+|biotechnol\w+)\b",
            r"\b(?:ecolog\w+|biodivers\w+|esp[ée]cies?|species|taxonom\w+|filogen\w+|phylogen\w+|bot[âa]nic\w+|zoolog\w+|fauna|flora|bioma\w*)\b",
            r"\b(?:microbi\w+|bact[ée]ri\w+|fung\w+|v[íi]rus|virolog\w+|parasit\w+|PCR|qPCR|sequenciamento|sequencing|cultivo\s+celular|in\s+vitro)\b",
            r"\b(?:agron\w+|agr[íi]col\w+|cultivar\w*|plantas?|plants?|solos?|soils?|sementes?|zootec\w+|veterin[áa]ri\w+|bovin\w+|su[íi]n\w+|aves\b|pescado|aquicult\w+)\b",
        ],
        "guidance": "Biological, agricultural or omics work: committees look for controls and replicates (biological, not only technical), "
                    "identification of species, strains or cultivars, the sampling design in the field or lab, and ethics/biodiversity approvals "
                    "(CEUA for animals, SisGen for genetic heritage) when applicable.",
    },
    "saude": {
        "keywords": [
            r"\b(?:sa[úu]de|health|cl[íi]nic\w+|clinical|hospital\w*|pacientes?|patients?|SUS|aten[çc][ãa]o\s+(?:prim[áa]ria|b[áa]sica)|primary\s+care)\b",
            r"\b(?:doen[çc]as?|diseases?|enfermedad\w+|tratamentos?|treatments?|diagn[óo]stic\w+|diagnos\w+|progn[óo]stic\w+|sintomas?|symptoms?|terap\w+|therap\w+)\b",
            r"\b(?:preval[êe]nci\w+|prevalence|incid[êe]nci\w+|epidemiol\w+|morbi\w+|mortalid\w+|mortality|fatores?\s+de\s+risco|risk\s+factors?)\b",
            r"\b(?:enfermagem|nursing|odontol\w+|dentistry|fisioterap\w+|physiotherap\w+|nutri[çc][ãa]o|nutrition|farm[áa]c\w+|pharmac\w+|medicament\w+|f[áa]rmacos?|gestantes?|pregnan\w+)\b",
            r"\b(?:CAAE|CEP|CONEP|TCLE|prontu[áa]rios?|medical\s+records|IRB)\b",
            r"\b(?:idos[oa]s|older\s+adults|elderly|envelhecimento|aging|ageing|sono|sleep|atividade\s+f[íi]sica|physical\s+activity|exerc[íi]cio\s+f[íi]sico|"
            r"sa[úu]de\s+mental|mental\s+health|depress\w+|ansiedade|anxiety|obesidade|obesity|hipertens\w+|hypertension|diabetes|c[âa]ncer|cancer|"
            r"qualidade\s+de\s+vida|quality\s+of\s+life|IMC|BMI|vacina\w*|vaccin\w+|infec[çc]\w+|infection\w*|personas\s+mayores|adultos\s+mayores|salud)\b",
        ],
        "guidance": "Health work: committees look for the study design named (cross-sectional, cohort, trial, case report…), the population and "
                    "setting, outcomes with clinical relevance and not only p-values, confounding acknowledged, and the ethics approval (CEP/CAAE) "
                    "whenever people or their records are involved.",
    },
    "exatas": {
        "keywords": [
            r"\b(?:matem[áa]tic\w+|mathemat\w+|teorema\w*|theorem\w*|equa[çc][õo]es|equa[çc][ãa]o|equations?|estat[íi]stica\s+(?:aplicada|bayesiana)|probabilid\w+|probabilit\w+)\b",
            r"\b(?:f[íi]sic[ao]s?|physics|qu[íi]mic[ao]s?|chemistry|chemical|espectrosc\w+|spectroscop\w+|s[íi]ntese\s+qu[íi]mica|nanopart\w+|catalis\w+|cristal\w*)\b",
            r"\b(?:algoritm\w+|algorithms?|computa[çc][ãa]o|computer\s+science|ci[êe]ncia\s+da\s+computa[çc][ãa]o|aprendizado\s+de\s+m[áa]quina|machine\s+learning|redes?\s+neura\w+|neural\s+networks?|intelig[êe]ncia\s+artificial|artificial\s+intelligence)\b",
            r"\b(?:software|plataforma\s+(?:web|digital|online)|sistemas?\s+(?:web|de\s+informa[çc][ãa]o)|aplicativos?|apps?\b|aplica[çc][ãa]o\s+(?:web|m[óo]vel)|requisitos\s+(?:funcionais|n[ãa]o\s+funcionais)|"
            r"autentica[çc][ãa]o|HTTPS|front-?end|back-?end|API|engenharia\s+de\s+software|desenvolvimento\s+(?:web|de\s+sistemas))\b",
            r"\b(?:simula[çc][ãa]o|simulation|modelo\s+(?:matem[áa]tico|computacional)|computational\s+model|otimiza[çc][ãa]o|optimi[sz]ation|complexidade\s+computacional|grafos?|graphs?|banco\s+de\s+dados|database|seguran[çc]a\s+da\s+informa[çc][ãa]o|information\s+security|criptograf\w+)\b",
        ],
        "guidance": "Exact sciences or computing: committees look for formal correctness, a stated method or model, validation on data or "
                    "test cases, comparison with existing methods or a baseline, and performance or accuracy reported with the evaluation setup.",
    },
    "engenharias": {
        "keywords": [
            r"\b(?:engenharia\w*|engineering|prot[óo]tipos?|prototypes?|sensor\w*|arduino|circuit\w+|sistemas?\s+embarcados?|embedded\s+systems?|IoT|automa[çc][ãa]o|automation|rob[óo]tic\w+)\b",
            r"\b(?:concreto|concrete|estrutur\w+\s+(?:met[áa]lic\w+|de\s+concreto)|resist[êe]ncia\s+(?:mec[âa]nica|[àa]\s+compress[ãa]o)|ensaios?\s+(?:mec[âa]nicos?|de\s+tra[çc][ãa]o)|materiais?\s+comp[óo]sit\w+|pavimenta\w+)\b",
            r"\b(?:energia\s+(?:solar|e[óo]lica|renov[áa]vel|el[ée]trica)|renewable\s+energy|efici[êe]ncia\s+energ[ée]tica|motor\w*|turbin\w+|processos?\s+industri\w+|manufatura|manufacturing|linha\s+de\s+produ[çc][ãa]o|saneamento|tratamento\s+de\s+(?:[áa]gua|efluentes))\b",
        ],
        "guidance": "Engineering work: committees look for the problem in operational terms, the design or process described, tests or "
                    "measurements with their conditions, performance compared with a requirement, standard (ABNT/ISO) or existing solution, "
                    "and the limits of the tests.",
    },
    "humanas": {
        "keywords": [
            r"\b(?:educa[çc][ãa]o|education|ensino|teaching|aprendizagem|learning|escolas?|schools?|professor\w*|docentes?|teachers?|alunos?|estudantes?|students?|pedag[óo]g\w+|did[áa]tic\w+|curr[íi]culo\w*|forma[çc][ãa]o\s+docente)\b",
            r"\b(?:hist[óo]ri\w+|history|historiograf\w+|filosof\w+|philosoph\w+|psicolog\w+|psycholog\w+|sociolog\w+|antropolog\w+|anthropolog\w+|geograf\w+|teolog\w+|religi\w+)\b",
            r"\b(?:lingu[íi]stic\w+|linguistics|literatur\w+|literary|letras|discursos?|discourse|narrativas?|narratives?|cultur\w+|mem[óo]ria\s+(?:social|coletiva)|identidades?|identity|g[êe]nero\s+e\s+sexualidade|ra[çc]a|racism\w+|arte\w*|m[úu]sica\w*|patrim[ôo]nio\s+cultural)\b",
        ],
        "guidance": "Humanities or education: committees look for the theoretical framework and the authors in dialogue, the research question, "
                    "the corpus, participants or sources and how they were chosen, the analytical procedure, and interpretations grounded in the "
                    "material. Numbers are not expected; argument and evidence from the material are.",
    },
    "sociais_aplicadas": {
        "keywords": [
            r"\b(?:direito|law|jur[íi]dic\w+|legal|legisla[çc][ãa]o|legislation|leis?\b|constitu\w+|jurisprud[êe]ncia|tribunal|STF|STJ|LGPD|GDPR|regulat\w+|regula[çc][ãa]o)\b",
            r"\b(?:administra[çc][ãa]o|management|gest[ãa]o|empres\w+|companies|organiza[çc][õo]es|organizational|empreendedor\w*|entrepreneur\w*|marketing|consumidor\w*|consumers?|neg[óo]cios?|business)\b",
            r"\b(?:economia|economics|econ[ôo]mic\w+|cont[áa]bil\w*|accounting|finan[çc]\w+|finance|tribut\w+|or[çc]ament\w+|mercado\s+de\s+trabalho|labor\s+market)\b",
            r"\b(?:comunica[çc][ãa]o\s+social|jornalismo|journalism|publicidade|advertising|m[íi]dias?\s+sociais|social\s+media|servi[çc]o\s+social|social\s+work|pol[íi]ticas?\s+p[úu]blicas?|public\s+polic\w+|turismo|tourism|arquitetura|architecture|urbanismo|urban\s+planning|design|ci[êe]ncia\s+da\s+informa[çc][ãa]o|biblioteconomia|arquivolog\w+|cataloga[çc][ãa]o|catalogu?ing)\b",
        ],
        "guidance": "Applied social sciences (law, management, economics, communication, social work, architecture, information science): "
                    "committees look for the context and the practical or normative problem, the legal, theoretical or managerial framework, the "
                    "sources (legislation, case law, documents, organizations, data) and how they were analyzed, and applicability of the conclusions.",
    },
}
AREA_CODES = tuple(AREAS)

# ---------------------------------------------------------------------------
# Research approaches
# ---------------------------------------------------------------------------

APPROACHES: dict[str, dict[str, Any]] = {
    "quantitative": {
        "declarations": [r"\b(?:estudo|pesquisa|abordagem)\s+quantitativ\w+|\bquantitative\s+(?:study|research|approach)|\bestudio\s+cuantitativo",
                         r"\bestudo\s+(?:transversal|de\s+coorte|caso-controle|experimental|observacional|ecol[óo]gico)|\b(?:cross-sectional|cohort|case-control|experimental|observational)\s+(?:study|design)",
                         r"\bensaio\s+cl[íi]nico|\bclinical\s+trial|\bensayo\s+cl[íi]nico"],
        "patterns": [r"\b(?:estat[íi]stic\w+|statistic\w+|teste\s+(?:t|qui-quadrado|exato)|t-test|chi-square|ANOVA|Mann-Whitney|Kruskal|Wilcoxon|regress[ãa]o|regression|correla[çc][ãa]o|correlation)\b",
                     r"\b(?:m[ée]dia|mean|desvio[\s-]padr[ãa]o|standard\s+deviation|intervalo\s+de\s+confian[çc]a|confidence\s+interval|odds\s+ratio|raz[ãa]o\s+de\s+chances|preval[êe]ncia|prevalence)\b",
                     r"(?:\bp\s*[<=>≤]\s*0[,.]\d|\bn\s*=\s*\d|\b\d+[,.]?\d*\s*%)",
                     r"\b(?:amostra\s+de\s+\d+|sample\s+of\s+\d+|grupo\s+controle|control\s+group|in\s+vitro|in\s+vivo|tratamentos?\s+experimenta\w+|delineamento\s+(?:inteiramente\s+)?casualizado)\b"],
    },
    "qualitative": {
        "declarations": [r"\b(?:estudo|pesquisa|abordagem)\s+qualitativ\w+|\bqualitative\s+(?:study|research|approach)|\b(?:estudio|investigaci[óo]n|enfoque)\s+cualitativ\w+"],
        "patterns": [r"\b(?:entrevistas?\s+(?:semi-?estruturad\w+|em\s+profundidade|narrativ\w+)|semi-?structured\s+interviews?|entrevistas?|interviews?|grupos?\s+foca\w+|focus\s+groups?)\b",
                     r"\b(?:an[áa]lise\s+(?:de\s+conte[úu]do|tem[áa]tica|do\s+discurso|de\s+discurso|textual\s+discursiva)|content\s+analysis|thematic\s+analysis|discourse\s+analysis|Bardin|Minayo|IRaMuTeQ)\b",
                     r"\b(?:etnogr\w+|ethnograph\w+|observa[çc][ãa]o\s+participante|participant\s+observation|hist[óo]ria\s+oral|oral\s+history|fenomenol[óo]g\w+|phenomenolog\w+|hermen[êe]utic\w+|cartografia|grounded\s+theory|teoria\s+fundamentada|satura[çc][ãa]o|saturation|categorias?\s+(?:emergentes|de\s+an[áa]lise))\b"],
    },
    "documentary": {
        "declarations": [r"\b(?:pesquisa|an[áa]lise|estudo)\s+documental|\bdocumentary\s+(?:research|analysis)|\b(?:investigaci[óo]n|an[áa]lisis)\s+documental"],
        "patterns": [r"\b(?:jurisprud[êe]ncia|case\s+law|ac[óo]rd[ãa]os?|decis[õo]es\s+judiciais|an[áa]lise\s+(?:da\s+)?legisla[çc][ãa]o|fontes\s+prim[áa]rias|primary\s+sources|arquivos?\s+hist[óo]ric\w+|documentos\s+oficiais|official\s+documents)\b"],
    },
    "mixed": {
        "declarations": [r"\b(?:m[ée]todos?\s+mistos?|mixed[\s-]methods?|abordagem\s+mista|quali-?quantitativ\w+|quanti-?qualitativ\w+|qualiquantitativ\w+|quantiqualitativ\w+|cuali-?cuantitativ\w+)"],
        "patterns": [],
    },
    "review": {
        "declarations": [r"\brevis[ãa]o\s+(?:sistem[áa]tica|integrativa|de\s+(?:literatura|escopo)|bibliogr[áa]fica|narrativa)|\b(?:systematic|integrative|scoping|narrative|literature)\s+review|\brevisi[óo]n\s+(?:sistem[áa]tica|integradora|de\s+(?:la\s+)?literatura|bibliogr[áa]fica)|\bpesquisa\s+bibliogr[áa]fica|\bmeta-?an[áa]lis\w+|\bmeta-?analys\w+"],
        "patterns": [r"\b(?:PRISMA|PubMed|MEDLINE|SciELO|LILACS|BVS|Scopus|Web\s+of\s+Science|Google\s+(?:Scholar|Acad[êe]mico)|Embase|CAPES|DeCS|MeSH|descritores|descriptors)\b",
                     r"\b(?:artigos?\s+(?:selecionad|inclu[íi]d|analisad)\w*|estudos?\s+(?:selecionad|inclu[íi]d)\w*|(?:studies|articles)\s+(?:were\s+)?(?:included|selected)|crit[ée]rios\s+de\s+(?:inclus[ãa]o|elegibilidade)|inclusion\s+criteria|bases\s+de\s+dados)\b"],
    },
    "theoretical": {
        "declarations": [r"\b(?:ensaio|estudo|reflex[ãa]o|discuss[ãa]o|an[áa]lise)\s+te[óo]ric\w+|\btheoretical\s+(?:essay|study|reflection|discussion)|\bensayo\s+te[óo]rico|\b(?:pesquisa|estudo)\s+(?:conceitual|filos[óo]fic\w+)"],
        "patterns": [r"\b(?:referencial\s+te[óo]rico|marco\s+te[óo]rico|theoretical\s+framework|conceitos?\s+de|concept\s+of|perspectiva\s+(?:te[óo]rica|cr[íi]tica)|a\s+partir\s+(?:do\s+pensamento|da\s+obra|das?\s+contribui[çc][õo]es)\s+de)\b"],
    },
    "computational": {
        "declarations": [r"\b(?:estudo|abordagem|m[ée]todo)\s+computacional|\bcomputational\s+(?:study|approach|method)|\bin\s+silico\b|\bsimula[çc][ãa]o\s+computacional|\bcomputer\s+simulation"],
        "patterns": [r"\b(?:acur[áa]cia|accuracy|precis[ãa]o\s+e\s+revoca[çc][ãa]o|precision\s+and\s+recall|F1|AUC|RMSE|MAE|valida[çc][ãa]o\s+cruzada|cross-validation|conjunto\s+de\s+(?:dados|teste|treinamento)|(?:test|training)\s+set|dataset|benchmark|baseline|tempo\s+de\s+execu[çc][ãa]o|runtime)\b",
                     r"\b(?:algoritmo\s+(?:proposto|desenvolvido)|proposed\s+(?:algorithm|method|model)|modelo\s+(?:proposto|treinado)|trained\s+model|redes?\s+neura\w+|neural\s+networks?|aprendizado\s+de\s+m[áa]quina|machine\s+learning|deep\s+learning|random\s+forest|XGBoost)\b"],
    },
    "case_report": {
        "declarations": [r"\brelato\s+de\s+(?:caso|experi[êe]ncia)|\bcase\s+report|\bexperience\s+report|\brelato\s+de\s+(?:una\s+)?experiencia|\breporte\s+de\s+caso|\bestudo\s+de\s+caso|\bcase\s+study|\bestudio\s+de\s+caso"],
        "patterns": [r"\b(?:paciente\s+do\s+sexo|patient,?\s+(?:a\s+)?\d+[\s-]year|relatamos|we\s+report|vivenci\w+|experi[êe]ncia\s+(?:vivida|de\s+est[áa]gio|na\s+disciplina|docente)|est[áa]gio\s+supervisionado)\b"],
    },
}
APPROACH_CODES = tuple(APPROACHES)

# Approach guidance for the evaluators (English; the evaluation is written in the report language).
APPROACH_GUIDANCE = {
    "quantitative": "Quantitative research: results should carry numbers (n, magnitude, dispersion or uncertainty, test when inference is claimed).",
    "qualitative": "Qualitative research: judge the corpus or participants and how they were chosen, the named analysis procedure, and findings "
                   "(categories, themes) supported by the material (excerpts, quotes). Do not ask for statistics, sample-size calculation or p-values.",
    "documentary": "Documentary research (legislation, case law, archives, official documents): judge the sources and selection criteria, the "
                   "analysis procedure and findings grounded in the documents. Do not ask for statistics.",
    "mixed": "Mixed methods: judge both strands and whether they are integrated; numbers for the quantitative strand, evidence from the material "
             "for the qualitative one.",
    "review": "Literature review: judge the search (databases, descriptors, period), the inclusion criteria, how many studies were included and "
              "a synthesis of their findings with the gaps it shows. Do not ask for primary data or statistics unless it is a meta-analysis.",
    "theoretical": "Theoretical essay or conceptual study: judge the question, the framework and authors in dialogue, the line of argument and the "
                   "conceptual contribution. There are no empirical results to ask for; ask for a clear thesis and its support.",
    "computational": "Computational study: results should report performance on a stated evaluation setup (test set, cross-validation, "
                     "benchmark), compared with a baseline or existing method.",
    "case_report": "Case or experience report: judge the context, setting, period and participants, what was done, what was observed and learned, "
                   "and the limits of a single case or experience. Statistics are not expected; concrete observations are.",
}

# Approaches whose results are expected to carry numbers (the "results without numbers" flag and cap apply).
NUMBERS_EXPECTED = {"quantitative", "computational"}
# Approaches with no participants of their own: ethics approval is not expected.
NO_SUBJECTS = {"review", "theoretical", "documentary", "computational"}

HUMAN_SUBJECTS = re.compile(
    r"\b(?:entrevistas?\s+(?:semi-?estruturad\w+|em\s+profundidade|narrativ\w+|individua\w+)|entrevistad[oa]s|responderam|question[áa]rio|"
    r"invent[áa]rio\s+de|escala\s+de|grupos?\s+foca\w+|interviews?|surveyed|"
    r"(?:com|de|entre|a|con|with|of|among)\s+\d+\s+(?:pessoas|personas|people|estudantes|estudiantes|students|alunos|alunas|professor\w*|profesor\w*|teachers|docentes|"
    r"cuidador\w*|caregivers|mulheres|mujeres|women|homens|hombres|men|idos\w+|older\s+adults|crian[çc]as|ni[ñn]os|children|adolescentes|adolescents|gestantes|"
    r"trabalhador\w*|trabajador\w*|workers|profissionais|profesionales|professionals|usu[áa]ri\w+|users|moradores|residents|fam[íi]lias|families|familiares|"
    r"enfermeir\w+|enfermer\w+|nurses|m[ée]dic\w+|physicians)|"
    r"entrevistas?\s+semi-?estructurad\w+|encuestas?|cuestionarios?|grupos?\s+focales|"
    r"pacientes|participantes|volunt[áa]ri[oa]s|entrevistad[oa]s|sujeitos\s+da\s+pesquisa|question[áa]rios?\s+(?:aplicad|respondid)\w*|"
    r"aplica[çc][ãa]o\s+de\s+question[áa]rios?|grupos?\s+foca\w+|prontu[áa]rios|gestantes|pu[ée]rperas|"
    r"patients|participants|volunteers|interviewees|respondents|questionnaires?\s+(?:were\s+)?(?:applied|administered|answered)|focus\s+groups?|medical\s+records|"
    r"encuestad[oa]s|entrevistad[oa]s)\b",
    re.IGNORECASE,
)
ANIMAL_SUBJECTS = re.compile(
    r"\b(?:camundongos|ratos?\s+(?:wistar|machos|f[êe]meas)|ratas|Wistar|coelhos|c[ãa]es|gatos|animais\s+(?:de\s+laborat[óo]rio|experimentais)|"
    r"mice|rats|rabbits|laboratory\s+animals|zebrafish|peixe-zebra|ratones)\b",
    re.IGNORECASE,
)
ETHICS_STATED = re.compile(
    r"\b(?:CAAE|CEP|CONEP|CEUA|IRB|comit[êe]\s+de\s+[ée]tica|ethics\s+committee|comit[ée]\s+de\s+[ée]tica|parecer\s+(?:n[ºo°.]?\s*)?\d|"
    r"aprovad[oa]\s+pelo\s+comit[êe]|approved\s+by\s+the\s+(?:\w+\s+){0,3}(?:committee|board)|Plataforma\s+Brasil|TCLE|termo\s+de\s+consentimento|informed\s+consent)\b"
)


# Experience reports of teaching or extension activities do not need an ethics committee (Res. CNS 510/2016, art. 1).
EXPERIENCE_REPORT = re.compile(r"\b(?:relato\s+de\s+experi[êe]ncia|experience\s+report|relato\s+de\s+(?:una\s+)?experiencia)\b", re.IGNORECASE)


def _score(patterns: list[str], head: str, text: str) -> tuple[int, list[str]]:
    score, hits = 0, []
    for p in patterns:
        rx = _pat(p)
        found = rx.findall(text)
        score += len(rx.findall(head)) * 2 + len(found)
        for f in found[:2]:
            s = f if isinstance(f, str) else next((x for x in f if x), "")
            if s and s.lower() not in (h.lower() for h in hits):
                hits.append(s)
    return score, hits


AREA_MIN_EVIDENCE = 4
APPROACH_MIN_EVIDENCE = 4
AREA_CONFIDENCE_THRESHOLD = 0.5
APPROACH_CONFIDENCE_THRESHOLD = 0.5
DEFAULT_APPROACH = {"biologicas": "quantitative", "saude": "quantitative", "exatas": "computational", "engenharias": "quantitative",
                    "humanas": "qualitative", "sociais_aplicadas": "qualitative"}


def classify(title: str, body: str, keywords: str = "", *, area: str | None = None, approach: str | None = None) -> dict[str, Any]:
    """Area and approach of an abstract. `area`/`approach` force a value (confidence 1).

    Title and keywords count three times as much as the body. Confidence is the winner's share
    of all scores, scaled down when its own evidence is thin; below the threshold the axis is
    listed in `low_confidence` for the agent (or the user) to confirm."""
    head = f"{title}\n{keywords}"
    text = f"{title}\n{keywords}\n{body}"

    a_scores, a_hits = {}, {}
    for code, spec in AREAS.items():
        a_scores[code], a_hits[code] = _score(spec["keywords"], head, text)
    if area in AREAS:
        best_area, a_conf = area, 1.0
    elif not any(a_scores.values()):
        best_area, a_conf = None, 0.0  # no evidence at all: undetermined, never a guess
    else:
        best_area = max(a_scores, key=lambda k: a_scores[k])
        total = sum(a_scores.values())
        a_conf = round(a_scores[best_area] / total * min(1.0, a_scores[best_area] / AREA_MIN_EVIDENCE), 2)

    p_scores, p_hits = {}, {}
    for code, spec in APPROACHES.items():
        decl, dh = _score(spec["declarations"], head, text)
        pat, ph = _score(spec["patterns"], head, text)
        p_scores[code], p_hits[code] = decl * 6 + pat, dh + ph
    if approach in APPROACHES:
        best_app, p_conf = approach, 1.0
    elif any(p_scores.values()):
        best_app = max(p_scores, key=lambda k: p_scores[k])
        total = sum(p_scores.values())
        p_conf = round(p_scores[best_app] / total * min(1.0, p_scores[best_app] / APPROACH_MIN_EVIDENCE), 2)
    else:
        best_app, p_conf = DEFAULT_APPROACH.get(best_area, "quantitative"), 0.0

    humans = bool(HUMAN_SUBJECTS.search(text))
    animals = bool(ANIMAL_SUBJECTS.search(text))
    ethics_stated = bool(ETHICS_STATED.search(text))
    low = [ax for ax, c, th in (("area", a_conf, AREA_CONFIDENCE_THRESHOLD), ("approach", p_conf, APPROACH_CONFIDENCE_THRESHOLD)) if c < th]
    return {
        "area": best_area,
        "area_confidence": a_conf,
        "area_scores": a_scores,
        "area_signals": a_hits[best_area][:6] if best_area else [],
        "approach": best_app,
        "approach_confidence": p_conf,
        "approach_scores": p_scores,
        "approach_signals": p_hits.get(best_app, [])[:6],
        "human_subjects": humans,
        "animal_subjects": animals,
        "ethics_stated": ethics_stated,
        "ethics_check": (humans or animals) and not ethics_stated and best_app not in NO_SUBJECTS and not EXPERIENCE_REPORT.search(text),
        "low_confidence": low,
        "forced": {"area": area in AREAS, "approach": approach in APPROACHES},
    }
