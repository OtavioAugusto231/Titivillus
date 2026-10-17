"""Comparação entre o que o Gemini leu e os candidatos das fontes."""

from .config import (
    LIMIAR_AUTOR,
    LIMIAR_PARCIAL,
    LIMIAR_TITULO,
    LIMIAR_TITULO_SEM_AUTOR,
)
from .textos import similaridade, texto_seguro


def _extrair(item):
    """Devolve (titulo_api, [autores_api]) ou None se o item for inválido."""
    if not isinstance(item, dict):
        return None
    volume = item.get("volumeInfo", {})
    if not isinstance(volume, dict):
        return None
    titulo_api = texto_seguro(volume.get("title"))
    if not titulo_api:
        return None
    autores = volume.get("authors", [])
    if not isinstance(autores, list):
        autores = []
    return titulo_api, [a for a in map(texto_seguro, autores) if a]


def escolher_melhor(itens, titulo, autor):
    """Match completo: título E autor (quando há autor)."""
    melhor = None
    melhor_pontuacao = 0.0

    for item in itens:
        extraido = _extrair(item)
        if not extraido:
            continue
        titulo_api, autores_api = extraido

        pontuacao_titulo = similaridade(titulo, titulo_api)

        if autor:
            if not autores_api:
                continue
            pontuacao_autor = max(similaridade(autor, nome) for nome in autores_api)
            if pontuacao_titulo < LIMIAR_TITULO or pontuacao_autor < LIMIAR_AUTOR:
                continue
            pontuacao = 0.70 * pontuacao_titulo + 0.30 * pontuacao_autor
        else:
            if pontuacao_titulo < LIMIAR_TITULO_SEM_AUTOR:
                continue
            pontuacao = pontuacao_titulo

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = {"titulo": titulo_api, "autor": ", ".join(autores_api) or None}

    return melhor


def escolher_parcial(itens, titulo):
    """Título quase idêntico, autor divergente/ausente. Serve de SUGESTÃO para
    revisão humana (ex.: autor lido errado no OCR); nunca valida nem renomeia."""
    melhor = None
    melhor_pontuacao = 0.0
    for item in itens:
        extraido = _extrair(item)
        if not extraido:
            continue
        titulo_api, autores_api = extraido
        pontuacao = similaridade(titulo, titulo_api)
        if pontuacao >= LIMIAR_PARCIAL and pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = {"titulo": titulo_api, "autor": ", ".join(autores_api) or None}
    return melhor
