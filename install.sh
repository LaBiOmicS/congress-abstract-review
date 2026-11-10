#!/usr/bin/env bash
# ==============================================================================
# congress-abstract-review: Script de Instalação e Sincronização via uv
# LaBiOmicS / UMC - Prof. Dr. Fabiano Bezerra Menegidio
# ==============================================================================
set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> [1/4] Verificando ambiente e instalador uv..."

if ! command -v uv &> /dev/null; then
    echo "Aviso: 'uv' não encontrado no PATH. Instalando via script oficial Astral..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

echo "✔ uv detectado: $(uv --version)"

echo "==> [2/4] Sincronizando dependências Python via uv (PEP 621)..."
cd "$PLUGIN_DIR"
# --all-extras: pypdf/python-docx (extração de PDF/DOCX) e reportlab (PDF fallback)
uv sync --all-extras

copy_plugin_files() {
    local target_dir="$1"
    mkdir -p "$target_dir"
    if command -v rsync &> /dev/null; then
        rsync -a --delete --exclude='.git' --exclude='.venv' "$PLUGIN_DIR/" "$target_dir/"
    else
        rm -rf "${target_dir:?}"/*
        find "$PLUGIN_DIR" -maxdepth 1 ! -name '.git' ! -name '.venv' ! -name "$(basename "$PLUGIN_DIR")" -exec cp -r {} "$target_dir/" \;
    fi
}

# Ferramentas em que o plugin foi registrado pelo próprio CLI, e avisos para o resumo final.
INSTALLED=()
NOTES=()

echo "==> [3/4] Instalando e ativando no Antigravity CLI (Gemini)..."
if command -v agy &> /dev/null; then
    agy plugin install "$PLUGIN_DIR"
    agy plugin enable congress-abstract-review || true
    echo "✔ Plugin validado no Antigravity CLI:"
    agy plugin validate "$PLUGIN_DIR" --strict
    INSTALLED+=("Antigravity CLI")
else
    echo "Aviso: 'agy' CLI não encontrado no PATH. Copiando para diretórios padrão de plugins..."
    copy_plugin_files "$HOME/.gemini/antigravity-cli/plugins/congress-abstract-review"
    copy_plugin_files "$HOME/.gemini/extensions/congress-abstract-review"
    NOTES+=("Antigravity/Gemini: arquivos copiados para ~/.gemini, sem validação nem ativação ('agy' não está no PATH).")
fi

echo "==> [4/4] Instalando no Claude Code (marketplace local 'labiomics-congress')..."
if command -v claude &> /dev/null; then
    # Copiar arquivos para ~/.claude/plugins não registra o plugin; o caminho suportado é
    # registrar este diretório como marketplace e instalar a partir dele.
    claude plugin validate "$PLUGIN_DIR"
    # Se o repositório mudou de lugar, o marketplace continua apontando para o caminho antigo e o
    # plugin deixa de carregar ("cache-miss"). Nesse caso o registro é refeito no caminho atual.
    REGISTERED_PATH="$(claude plugin marketplace list --json 2>/dev/null | uv run --no-project python -c '
import json, sys
for m in json.load(sys.stdin):
    if m.get("name") == "labiomics-congress":
        print(m.get("path") or m.get("installLocation") or "")
' 2>/dev/null || true)"
    if [ -n "$REGISTERED_PATH" ] && [ "$REGISTERED_PATH" != "$PLUGIN_DIR" ]; then
        echo "Aviso: marketplace 'labiomics-congress' registrado em $REGISTERED_PATH. Registrando de novo em $PLUGIN_DIR..."
        claude plugin marketplace remove labiomics-congress
    fi
    if [ "$REGISTERED_PATH" = "$PLUGIN_DIR" ]; then
        claude plugin marketplace update labiomics-congress
    else
        # Sem o caminho registrado (ex.: CLI sem --json), cai no comportamento anterior.
        claude plugin marketplace add "$PLUGIN_DIR" || claude plugin marketplace update labiomics-congress
    fi
    claude plugin install congress-abstract-review@labiomics-congress
    echo "✔ Plugin instalado no Claude Code (reinicie a sessão para carregá-lo)."
    INSTALLED+=("Claude Code")
else
    echo "Aviso: 'claude' CLI não encontrado no PATH. Pulando integração com Claude Code."
    NOTES+=("Claude Code: não instalado, 'claude' não está no PATH (rode este script de novo depois de instalá-lo).")
fi

echo ""
echo "================================================================================"
if [ ${#INSTALLED[@]} -gt 0 ]; then
    JOINED="$(printf '%s, ' "${INSTALLED[@]}")"
    echo "✔ Plugin congress-abstract-review registrado em: ${JOINED%, }"
else
    echo "Aviso: o plugin congress-abstract-review não foi registrado em nenhum CLI."
fi
for note in "${NOTES[@]}"; do
    echo "  - $note"
done
echo "  - Ambiente virtual uv: $PLUGIN_DIR/.venv"
echo "  - Para testar: uv run skills/abstract-review/scripts/congress_review.py --help"
echo "================================================================================"
