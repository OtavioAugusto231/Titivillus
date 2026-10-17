"""Utilitários de texto: normalização, similaridade e nomes de arquivo."""

import re
import unicodedata
from difflib import SequenceMatcher

from .config import LIMITE_NOME_ARQUIVO


def texto_seguro(valor):
    """Converte valores em texto sem chamar métodos em listas."""
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    if isinstance(valor, list):
        partes = [texto_seguro(item) for item in valor]
        partes = [parte for parte in partes if parte]
        return ", ".join(partes) or None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return str(valor)
    return None


def normalizar(texto):
    """Sem acentos, pontuação e caixa."""
    texto = texto_seguro(texto) or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto.casefold())
    return " ".join(texto.split())


def similaridade(a, b):
    """Similaridade 0..1, tolerante a subtítulo e a ordem de tokens."""
    a = normalizar(a)
    b = normalizar(b)
    if not a or not b:
        return 0.0

    direta = SequenceMatcher(None, a, b).ratio()
    ordenada = SequenceMatcher(
        None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))
    ).ratio()
    menor, maior = sorted((a, b), key=len)
    contido = 0.9 if len(menor) >= 5 and menor in maior else 0.0

    return max(direta, ordenada, contido)


def limpar_nome(texto):
    """Remove caracteres proibidos em nomes de arquivos."""
    texto = texto_seguro(texto) or ""
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)
    texto = " ".join(texto.split())
    texto = texto[:LIMITE_NOME_ARQUIVO].strip().rstrip(". ")

    reservados = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if texto.upper() in reservados:
        texto = f"_{texto}"
    return texto
