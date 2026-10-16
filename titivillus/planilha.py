"""Ordenação alfabética e exportação para Excel."""

import re

import pandas as pd

from .modelos import CAMPOS
from .textos import normalizar


def _numero_volume(valor):
    if isinstance(valor, str):
        achado = re.search(r"\d+", valor)
        if achado:
            return int(achado.group())
    return 0


def exportar_excel(registros, caminho, campos=CAMPOS):
    df = pd.DataFrame(registros, columns=campos)

    df["_ordem"] = df["titulo"].map(normalizar)
    df["_sem_titulo"] = df["titulo"].map(
        lambda valor: not (isinstance(valor, str) and valor.strip())
    )
    df["_vol"] = df["volume"].map(_numero_volume)

    df = df.sort_values(by=["_sem_titulo", "_ordem", "_vol"], kind="stable").drop(
        columns=["_sem_titulo", "_ordem", "_vol"]
    )

    try:
        df.to_excel(caminho, index=False)
    except ModuleNotFoundError as erro:
        if "openpyxl" in str(erro):
            raise RuntimeError(
                "A biblioteca openpyxl não está instalada no ambiente virtual. "
                "Execute: pip install openpyxl"
            ) from erro
        raise
    except PermissionError as erro:
        raise RuntimeError(
            f"Sem permissão para gravar {caminho}. "
            "Feche a planilha se ela estiver aberta."
        ) from erro
