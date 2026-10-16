"""Reconhecimento da capa e faixa etária via Gemini."""

import json
import time

from google.genai import errors as genai_errors
from google.genai import types

from .config import (
    CODIGOS_RETENTAVEIS,
    ESPERAS_GEMINI,
    EXTENSOES,
    FAIXAS,
    MODELO,
    MODELO_FAIXA,
    MODELO_FAIXA_FALLBACK,
    get_client,
)
from .log import log
from .modelos import Autor, Capa, FaixaEtaria
from .prompts import PROMPT, PROMPT_AUTOR, PROMPT_FAIXA
from .textos import texto_seguro


def gerar_com_retry(modelo, contents, schema):
    """generate_content com backoff para 429/5xx. Levanta o erro final."""
    client = get_client()
    for tentativa in range(len(ESPERAS_GEMINI) + 1):
        try:
            return client.models.generate_content(
                model=modelo,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as erro:
            codigo = getattr(erro, "code", None)

            if codigo == 404:
                raise RuntimeError(
                    f"Modelo '{modelo}' não encontrado. Liste os disponíveis com "
                    "client.models.list() e defina GEMINI_MODEL com o ID exato."
                ) from erro

            if codigo in CODIGOS_RETENTAVEIS and tentativa < len(ESPERAS_GEMINI):
                espera = ESPERAS_GEMINI[tentativa]
                log(f"  API retornou {codigo}; nova tentativa em {espera}s...")
                time.sleep(espera)
                continue
            raise


def chamar_gemini(dados_imagem, mime, prompt=PROMPT, schema=Capa):
    return gerar_com_retry(
        MODELO,
        [types.Part.from_bytes(data=dados_imagem, mime_type=mime), prompt],
        schema,
    )


def ler_autor(path, mime):
    """Segunda leitura focada só no autor, usada quando a primeira vem vazia."""
    try:
        resposta = chamar_gemini(path.read_bytes(), mime, PROMPT_AUTOR, Autor)
        dados = json.loads(getattr(resposta, "text", None) or "{}")
        return texto_seguro(dados.get("autor")) if isinstance(dados, dict) else None
    except Exception as erro:
        log(f"  Segunda leitura do autor falhou: {erro}")
        return None


def ler_faixa_etaria(titulo, autor=None):
    """Chamada só de texto. Tenta o modelo principal e depois o fallback.
    Retorna uma das FAIXAS ou None."""
    if not titulo or get_client() is None:
        return None

    autor_txt = f", de {autor}" if autor else ""
    prompt = PROMPT_FAIXA.format(titulo=titulo, autor_txt=autor_txt)

    modelos = [MODELO_FAIXA]
    if MODELO_FAIXA_FALLBACK and MODELO_FAIXA_FALLBACK != MODELO_FAIXA:
        modelos.append(MODELO_FAIXA_FALLBACK)

    for modelo in modelos:
        try:
            resposta = gerar_com_retry(modelo, [prompt], FaixaEtaria)
        except Exception as erro:
            log(f"  Faixa etária falhou em {modelo}: {erro}")
            continue

        try:
            dados = json.loads(getattr(resposta, "text", None) or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        valor = (
            texto_seguro(dados.get("faixa_etaria")) if isinstance(dados, dict) else None
        )
        if not valor:
            return None  # "não sei"; fallback não muda isso
        valor = valor.replace(" ", "")
        return valor if valor in FAIXAS else None

    return None


def ler_capa(path):
    if get_client() is None:
        raise RuntimeError(
            "Chave Gemini ausente. Defina GEMINI_API_KEY (ambiente ou .env)."
        )

    mime = EXTENSOES.get(path.suffix.lower())
    if mime is None:
        raise ValueError("Formato de imagem não suportado.")

    resposta = chamar_gemini(path.read_bytes(), mime)

    texto_resposta = getattr(resposta, "text", None)
    if not texto_resposta:
        raise ValueError("O Gemini retornou uma resposta vazia.")

    try:
        dados = json.loads(texto_resposta)
    except (json.JSONDecodeError, TypeError) as erro:
        raise ValueError(
            f"O Gemini não retornou JSON válido: {texto_resposta!r}"
        ) from erro

    if not isinstance(dados, dict):
        raise ValueError(
            f"Formato inesperado do Gemini: esperado objeto JSON, "
            f"recebido {type(dados).__name__}."
        )

    autor = texto_seguro(dados.get("autor"))
    if not autor:
        autor = ler_autor(path, mime)
        if autor:
            log(f"  Autor recuperado na segunda leitura: {autor!r}")

    return {
        "titulo": texto_seguro(dados.get("titulo")),
        "volume": texto_seguro(dados.get("volume")),
        "autor": autor,
    }
