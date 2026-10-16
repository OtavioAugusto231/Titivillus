"""Schemas do Gemini, constantes de status e estrutura do registro."""

from typing import Optional

from pydantic import BaseModel

from .config import MODO_NUNCA, MODO_VALIDADOS, MODO_VALIDADOS_E_INCONCLUSIVOS

CAMPOS = [
    "titulo",
    "volume",
    "autor",
    "faixa_etaria",
    "titulo_google_books",
    "autor_google_books",
    "validado",
    "status",
    "fonte_validacao",
    "arquivo",
    "erro",
]

STATUS_VALIDADO = "validado"
STATUS_PARCIAL = "parcial (conferir autor)"
STATUS_SEM_MATCH = "sem correspondência"
STATUS_INCONCLUSIVO = "inconclusivo (fonte indisponível)"
STATUS_ERRO = "erro"

# Status que liberam a renomeação, por modo.
STATUS_POR_MODO = {
    MODO_VALIDADOS: {STATUS_VALIDADO},
    MODO_VALIDADOS_E_INCONCLUSIVOS: {STATUS_VALIDADO, STATUS_INCONCLUSIVO},
    MODO_NUNCA: set(),
}


class Capa(BaseModel):
    titulo: Optional[str] = None
    volume: Optional[str] = None
    autor: Optional[str] = None


class Autor(BaseModel):
    autor: Optional[str] = None


class FaixaEtaria(BaseModel):
    faixa_etaria: Optional[str] = None


def resultado_vazio(arquivo, erro):
    return {
        "titulo": None,
        "volume": None,
        "autor": None,
        "faixa_etaria": None,
        "titulo_google_books": None,
        "autor_google_books": None,
        "validado": False,
        "status": STATUS_ERRO,
        "fonte_validacao": None,
        "arquivo": arquivo,
        "erro": erro,
    }
