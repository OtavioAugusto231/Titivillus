"""Validação do livro lido contra Google Books e Open Library."""

import requests

from .fontes import buscar_google_books_duas_consultas, buscar_open_library
from .log import log
from .matching import escolher_melhor, escolher_parcial
from .modelos import (
    STATUS_INCONCLUSIVO,
    STATUS_PARCIAL,
    STATUS_SEM_MATCH,
    STATUS_VALIDADO,
)
from .textos import texto_seguro


def validar(d):
    d["titulo_google_books"] = None
    d["autor_google_books"] = None
    d["validado"] = False
    d["fonte_validacao"] = None
    d["status"] = STATUS_SEM_MATCH

    titulo = texto_seguro(d.get("titulo"))
    autor = texto_seguro(d.get("autor"))

    if not titulo:
        return d

    estrita = f'intitle:"{titulo}"'
    if autor:
        estrita += f' inauthor:"{autor}"'
    solta = f"{titulo} {autor}" if autor else titulo

    fontes = [
        (
            "Google Books",
            lambda: buscar_google_books_duas_consultas(estrita, solta, titulo, autor),
        ),
        ("Open Library", lambda: buscar_open_library(titulo, autor)),
    ]

    falhas = []
    todos = []  # (fonte, itens) das fontes que responderam

    for nome, buscar in fontes:
        try:
            itens = buscar()
        except (requests.RequestException, ValueError) as erro:
            falhas.append(f"{nome}: {erro}")
            log(f"  {nome} indisponível, tentando próxima fonte...")
            continue

        melhor = escolher_melhor(itens, titulo, autor)
        log(f"  {nome}: {len(itens)} candidato(s), match={'sim' if melhor else 'não'}")
        if melhor:
            d["titulo_google_books"] = melhor["titulo"]
            d["autor_google_books"] = melhor["autor"]
            d["validado"] = True
            d["status"] = STATUS_VALIDADO
            d["fonte_validacao"] = nome
            return d
        todos.append((nome, itens))

    # Sem match completo: procura sugestão por título (revisão humana).
    for nome, itens in todos:
        parcial = escolher_parcial(itens, titulo)
        if parcial:
            d["titulo_google_books"] = parcial["titulo"]
            d["autor_google_books"] = parcial["autor"]
            d["fonte_validacao"] = f"{nome} (só título)"
            d["status"] = STATUS_PARCIAL
            break

    # Fonte que falhou torna o "sem match" inconclusivo.
    if falhas:
        d["erro"] = "Validação incompleta: " + " | ".join(falhas)
        if d["status"] == STATUS_SEM_MATCH:
            d["status"] = STATUS_INCONCLUSIVO

    return d
