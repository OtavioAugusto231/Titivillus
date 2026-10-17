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
STATUS_FICHA_LIDA = "lida"
STATUS_FICHA_NAO_IDENTIFICADA = "ficha não identificada"

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


class Ficha(BaseModel):
    """Tudo o que se lê na página de créditos / ficha catalográfica."""

    titulo: Optional[str] = None
    subtitulo: Optional[str] = None
    titulo_original: Optional[str] = None
    autores: Optional[list[str]] = None
    tradutor: Optional[str] = None
    ilustrador: Optional[str] = None
    organizador: Optional[str] = None
    editora: Optional[str] = None
    cidade: Optional[str] = None
    ano_publicacao: Optional[str] = None
    edicao: Optional[str] = None
    isbn: Optional[str] = None
    paginas: Optional[str] = None
    serie_colecao: Optional[str] = None
    volume: Optional[str] = None
    idioma: Optional[str] = None
    cdd: Optional[str] = None
    cdu: Optional[str] = None
    assuntos: Optional[list[str]] = None
    bibliotecario_crb: Optional[str] = None
    ficha_catalografica: Optional[str] = None
    outras_informacoes: Optional[str] = None


CAMPOS_FICHA = ["arquivo", *Ficha.model_fields, "status", "erro"]


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


def resultado_vazio_ficha(arquivo, erro):
    registro = {campo: None for campo in CAMPOS_FICHA}
    registro.update(arquivo=arquivo, status=STATUS_ERRO, erro=erro)
    return registro
