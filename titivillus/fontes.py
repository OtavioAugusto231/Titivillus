"""Fontes externas de validação: Google Books e Open Library."""

import time

import requests

from .config import (
    CODIGOS_RETENTAVEIS,
    ESPERAS_BOOKS,
    ESPERAS_BOOKS_SEM_CHAVE,
    GB_COOLDOWN_COM_CHAVE,
    GB_COOLDOWN_SEM_CHAVE,
    GB_INTERVALO,
    GOOGLE_BOOKS_KEY,
)
from .log import log
from .matching import escolher_melhor

_gb_ultimo = 0.0  # instante da última requisição ao Google Books
_gb_bloqueado_ate = 0.0  # circuit breaker: não insiste enquanto em cooldown


class GoogleBooksIndisponivel(requests.RequestException):
    """Google Books em cooldown após esgotar as tentativas."""


def buscar_google_books(consulta):
    """Consulta ao Google Books com throttle, backoff e Retry-After.
    Esgotou as tentativas em 429/5xx? Entra em cooldown e as próximas
    imagens pulam o Google Books direto, em vez de perder ~1 min cada."""
    global _gb_ultimo, _gb_bloqueado_ate

    restante = _gb_bloqueado_ate - time.monotonic()
    if restante > 0:
        raise GoogleBooksIndisponivel(f"em cooldown por mais {int(restante)}s")

    params = {"q": consulta, "maxResults": 10, "printType": "books"}
    if GOOGLE_BOOKS_KEY:
        params["key"] = GOOGLE_BOOKS_KEY

    esperas = ESPERAS_BOOKS if GOOGLE_BOOKS_KEY else ESPERAS_BOOKS_SEM_CHAVE

    for tentativa in range(len(esperas) + 1):
        folga = GB_INTERVALO - (time.monotonic() - _gb_ultimo)
        if folga > 0:
            time.sleep(folga)

        resposta = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params,
            timeout=15,
        )
        _gb_ultimo = time.monotonic()

        if resposta.status_code not in CODIGOS_RETENTAVEIS:
            break
        if tentativa == len(esperas):
            cooldown = (
                GB_COOLDOWN_COM_CHAVE if GOOGLE_BOOKS_KEY else GB_COOLDOWN_SEM_CHAVE
            )
            _gb_bloqueado_ate = time.monotonic() + cooldown
            log(
                f"  Google Books segue em {resposta.status_code}; "
                f"pulando-o pelos próximos {cooldown // 60} min."
            )
            break

        espera = esperas[tentativa]
        retry_after = resposta.headers.get("Retry-After", "")
        if retry_after.isdigit():
            espera = max(espera, int(retry_after))
        log(f"  Google Books {resposta.status_code}; nova tentativa em {espera}s...")
        time.sleep(espera)

    resposta.raise_for_status()
    corpo = resposta.json()
    itens = corpo.get("items", []) if isinstance(corpo, dict) else []
    return itens if isinstance(itens, list) else []


def buscar_google_books_duas_consultas(estrita, solta, titulo, autor):
    """Estrita primeiro; a solta só se a estrita não deu match.
    Se a 2ª falhar mas a 1ª respondeu, aproveita o que já veio."""
    itens = []
    for i, consulta in enumerate((estrita, solta)):
        try:
            novos = buscar_google_books(consulta)
        except (requests.RequestException, ValueError):
            if i == 0:
                raise
            break
        itens.extend(novos)
        if escolher_melhor(itens, titulo, autor):
            break
    return itens


def _open_library_get(params):
    params = {**params, "limit": 20, "fields": "title,author_name"}
    resposta = None
    for tentativa in range(1, 3):
        try:
            resposta = requests.get(
                "https://openlibrary.org/search.json",
                params=params,
                headers={"User-Agent": "Titivillus/1.0 (catalogador de livros)"},
                timeout=40,
            )
            break
        except (requests.Timeout, requests.ConnectionError):
            if tentativa == 2:
                raise
            log("  Open Library lento; tentando de novo...")
    resposta.raise_for_status()
    corpo = resposta.json()
    docs = corpo.get("docs", []) if isinstance(corpo, dict) else []

    itens = []
    for doc in docs if isinstance(docs, list) else []:
        if isinstance(doc, dict):
            itens.append(
                {
                    "volumeInfo": {
                        "title": doc.get("title"),
                        "authors": doc.get("author_name", []),
                    }
                }
            )
    return itens


def buscar_open_library(titulo, autor):
    """Sem chave. 1ª consulta: só título (filtro de autor na API zera
    resultados). Se não casar e houver autor, 2ª consulta livre 'título autor'.
    O match de autor é feito localmente, com fuzzy."""
    itens = _open_library_get({"title": titulo})
    if autor and not escolher_melhor(itens, titulo, autor):
        try:
            itens = itens + _open_library_get({"q": f"{titulo} {autor}"})
        except (requests.RequestException, ValueError):
            pass  # aproveita o que a 1ª consulta trouxe
    return itens
