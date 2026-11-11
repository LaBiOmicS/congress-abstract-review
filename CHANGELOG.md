# Changelog

Todas as mudanças relevantes deste plugin. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o [SemVer](https://semver.org/lang/pt-BR/).

## [0.1.1] — 2026-11-11

### Alterado
- Marketplace único `labiomics`: o `marketplace.json` lista os três plugins LaBiOmicS, e
  `congress-abstract-review@labiomics` substitui `congress-abstract-review@labiomics-congress` (READMEs, página do
  projeto e `install.sh`).

## [0.1.0] — 2026-11-04

### Adicionado
- Primeira versão, derivada da proposta técnica do academic-peer-review (`docs/PROPOSAL_CONGRESS_ABSTRACT_REVIEW.md`).
- Audiência independente das regras (`--audience`): comissão científica (descumprimento de norma sinalizado para a comissão, `compliance_hold`) ou autor antes de submeter, com ou sem edital (descumprimento vira item obrigatório da lista "Antes de submeter", `fix_before_submission`; plano de revisão numerado sem dados inventados). Sem edital vale o barema de boas práticas, só com recomendações.
- Categorias de avaliação com níveis definidos: cada critério do barema é pontuado por níveis do edital, de uma categoria global (`templates/criteria_catalog.json`: relevância, originalidade, objetivos, metodologia, resultados, conclusão, redação; `based_on` no `edital.json`) ou genéricos; métricas automáticas por critério; limites aplicados por código (resultados prometidos ou sem números, texto repetido), desligáveis com `apply_caps: false`.
- Relatórios no idioma do resumo (português, inglês ou espanhol; outros idiomas em inglês), com `--language` para forçar; no lote, planilha e relatório no idioma mais frequente.
- Reavaliação segura: repetir o `prepare` depois de mudar o resumo, o edital, o eixo, o formato ou a área/abordagem move as avaliações antigas para `superseded/` em vez de reaproveitá-las.
- O eixo declarado pelos autores prevalece; se os avaliadores o situariam em outro, a ficha registra a sugestão.
- Área e abordagem de cada resumo identificadas pelo texto (`area_profiles.py`, adaptado do academic-peer-review para textos curtos): seis áreas e oito abordagens, com nível de confiança e pedido de confirmação quando baixo; `--area`, `--approach` e colunas no CSV forçam a classificação. Nos eixos de pesquisa, os níveis de Metodologia e Resultados seguem a abordagem (qualitativa, documental, mista, revisão, ensaio teórico, relato), e o teto de "resultados sem números" só vale para trabalhos quantitativos e computacionais. Alerta `ethics_check` quando há pessoas ou animais sem menção a CEP/CAAE ou CEUA. Ficha e planilha mostram área e abordagem.
- Barema conforme a natureza do eixo (`tracks[].kind`): pesquisa, inovação ou extensão. Sem barema no edital, cada natureza tem o seu barema padrão, com categorias próprias (inovação: problema, solução e estágio de desenvolvimento, diferencial, viabilidade, impacto; extensão: comunidade, ação, resultados e impacto social, interação e formação), para que um produto ou uma ação de extensão não seja avaliado como estudo. Um eixo pode ter barema próprio (`tracks[].rubric`); `--track` e `--kind` escolhem o barema quando não há CSV.
- Resumo simples e resumo expandido, com detecção automática do formato e opção de forçá-lo.
- `edital_parser.py`: extração por regex dos limites citados no edital, com o trecho de origem; validação e normalização do `edital.json` escrito pelo agente; comparação entre os dois.
- `abstract_metrics.py`: contagens como no editor de texto sobre os componentes que o edital manda contar, seções obrigatórias em PT/EN/ES, figuras, tabelas, referências, palavras-chave, autores, idioma e anonimato.
- `content_audit.py`: promessas de dados futuros com gravidade, densidade de dados nos resultados (valores distintos), texto repetido, objetivo × conclusão, statcheck; no expandido, figuras e tabelas × legendas e DOIs.
- Painel alfa (conformidade e forma), beta (dados e rigor) e gama (eixo e impacto), com síntese da comissão; avaliador único omega; modo `auto` que escala ao painel completo só os casos limítrofes, de baixa confiança, com alerta de integridade ou incoerentes.
- Nota, decisão (aprovado ou indeferido) e sinalizações calculadas por código (mediana, pesos, nota mínima para aprovação, notas mínimas por critério, indeferimento com resultados prometidos); correções na síntese da comissão só com justificativa. A ferramenta avalia só o resumo: a modalidade de apresentação fica com a comissão, e o pôster é avaliado no evento.
- Modo lote: uma pasta de submissões, CSV opcional com id e eixo declarado, planilha da comissão (CSV + XLSX) com ranking geral e por eixo, relatório da comissão.
- Execução por subagentes nativos ou headless (`claude -p`, `agy -p`, `gemini -p`) com paralelismo, retentativas e piloto (`--limit`).
- Avaliação cega por padrão (autores e afiliações ocultos aos avaliadores); varredura de conteúdo oculto e de instruções embutidas herdada do academic-peer-review.
- Ficha de avaliação em MD e PDF, parecer aos autores pronto para o sistema de submissão, `evaluation_summary.json`.
- Página do projeto (`site/`, publicada no GitHub Pages por `.github/workflows/pages.yml`) em português, inglês e espanhol, com guia passo a passo para iniciantes e prompts prontos; READMEs com visão geral, fluxo, parâmetros e citação.
