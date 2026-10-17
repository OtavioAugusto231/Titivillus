#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

# Carrega o ambiente Rust/Cargo
if [[ -f "$HOME/.cargo/env" ]]; then
    source "$HOME/.cargo/env"
fi

# Verifica os arquivos necessários
if [[ ! -d ".venv" ]]; then
    echo "Erro: ambiente Python .venv não encontrado."
    exit 1
fi

if [[ ! -f "package.json" ]]; then
    echo "Erro: package.json não encontrado."
    exit 1
fi

source .venv/bin/activate

BACKEND_PID=""
if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Iniciando backend Python..."
.venv/bin/python -m uvicorn titivillus.api:app --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!

    for i in {1..30}; do
        if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
            break
        fi

        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "Erro ao iniciar o backend. Confira as mensagens acima."
            exit 1
        fi

        sleep 1
    done

    if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        echo "Erro: o backend não respondeu em 30 segundos."
        exit 1
    fi
else
    echo "Backend já está funcionando."
fi

cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "Iniciando interface do Titivillus..."
npm run tauri dev
