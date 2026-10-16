"""Leitura da ficha catalográfica / página de créditos via Gemini."""

from .config import EXTENSOES, MODELO_FICHA, get_client
from .leitor_capa import chamar_gemini, json_da_resposta
from .modelos import Ficha
from .prompts import PROMPT_FICHA
from .textos import texto_seguro


def ler_ficha(path):
    """Devolve um dict com todos os campos de Ficha (texto ou None).
    Campos de lista (autores, assuntos) viram 'a; b; c'."""
    if get_client() is None:
        raise RuntimeError(
            "Chave Gemini ausente. Defina GEMINI_API_KEY (ambiente ou .env)."
        )

    mime = EXTENSOES.get(path.suffix.lower())
    if mime is None:
        raise ValueError("Formato de imagem não suportado.")

    resposta = chamar_gemini(
        path.read_bytes(), mime, PROMPT_FICHA, Ficha, modelo=MODELO_FICHA
    )
    dados = json_da_resposta(resposta)

    registro = {}
    for campo in Ficha.model_fields:
        valor = dados.get(campo)
        if isinstance(valor, list):
            partes = [texto_seguro(item) for item in valor]
            registro[campo] = "; ".join(p for p in partes if p) or None
        else:
            registro[campo] = texto_seguro(valor)
    return registro
