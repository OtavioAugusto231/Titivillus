"""Configuração: .env, modelos, chaves, constantes e parâmetros da execução."""

import os
import pathlib
from dataclasses import dataclass

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent


def carregar_env(caminho):
    """Carrega KEY=VALOR de um .env simples (sem dependências).
    Variáveis já exportadas no shell têm prioridade."""
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


carregar_env(BASE_DIR / ".env")

PASTA_CAPAS = BASE_DIR / "capas"
ARQUIVO_EXCEL = BASE_DIR / "livros.xlsx"

MODELO = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
MODELO_FAIXA = os.environ.get("GEMINI_MODEL_FAIXA", "").strip() or MODELO
MODELO_FAIXA_FALLBACK = os.environ.get(
    "GEMINI_MODEL_FAIXA_FALLBACK", "gemini-2.5-flash"
).strip()

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Sem chave, a cota anônima do Google Books estoura (429) quase sempre.
# Crie em console.cloud.google.com (ative "Books API") e coloque no .env:
#   GOOGLE_BOOKS_API_KEY=sua_chave
GOOGLE_BOOKS_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()

_client = None


def get_client():
    """Cliente Gemini criado sob demanda; None se não houver chave."""
    global _client
    if _client is None and API_KEY:
        from google import genai

        _client = genai.Client(api_key=API_KEY)
    return _client


EXTENSOES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

CODIGOS_RETENTAVEIS = {429, 500, 502, 503, 504}
ESPERAS_GEMINI = (5, 15, 30)
ESPERAS_BOOKS = (5, 15, 40)
ESPERAS_BOOKS_SEM_CHAVE = (5,)  # sem chave, insistir só desperdiça tempo
GB_INTERVALO = 1.2
GB_COOLDOWN_COM_CHAVE = 120  # s sem consultar o Google Books após esgotar retries
GB_COOLDOWN_SEM_CHAVE = 900
LIMITE_NOME_ARQUIVO = 80

LIMIAR_TITULO = 0.70
LIMIAR_AUTOR = 0.65
LIMIAR_TITULO_SEM_AUTOR = 0.85
LIMIAR_PARCIAL = 0.92  # só título: sugere, mas NÃO valida nem renomeia

FAIXAS = ["Livre", "7+", "10+", "12+", "14+", "16+", "18+"]

# Quando renomear a foto
MODO_VALIDADOS = "validados"
MODO_VALIDADOS_E_INCONCLUSIVOS = "validados_inconclusivos"
MODO_NUNCA = "nunca"


@dataclass
class Settings:
    """Parâmetros de uma execução (a GUI preenche; o CLI usa os padrões)."""

    pasta_capas: pathlib.Path = PASTA_CAPAS
    arquivo_excel: pathlib.Path = ARQUIVO_EXCEL
    modo_renomear: str = MODO_VALIDADOS_E_INCONCLUSIVOS
