"""Linha de comando:
    python -m titivillus.cli          # capas (padrão)
    python -m titivillus.cli ficha    # fichas catalográficas
"""

import argparse

from .config import API_KEY, GOOGLE_BOOKS_KEY, MODELO, MODELO_FICHA, MODO_CAPA, MODO_FICHA, Settings
from .leitor_capa import QuotaEsgotada
from .log import log
from .pipeline import executar, listar_imagens, resumo, resumo_fichas


def main():
    parser = argparse.ArgumentParser(description="Titivillus")
    parser.add_argument(
        "modo",
        nargs="?",
        choices=[MODO_CAPA, MODO_FICHA],
        default=MODO_CAPA,
        help="o que ler: capa (padrão) ou ficha catalográfica",
    )
    args = parser.parse_args()
    ficha = args.modo == MODO_FICHA
    settings = Settings(modo=args.modo)

    if not API_KEY:
        print("Chave Gemini ausente. Defina GEMINI_API_KEY (ambiente ou .env).")
        return

    if not ficha and not GOOGLE_BOOKS_KEY:
        log(
            "Aviso: GOOGLE_BOOKS_API_KEY ausente. Google Books será tentado com "
            "retry curto e pulado por 15 min se continuar em 429."
        )

    pasta = settings.pasta_fichas if ficha else settings.pasta_capas
    pasta.mkdir(parents=True, exist_ok=True)
    log(
        f"Imagens encontradas: {len(listar_imagens(pasta))} "
        f"(modelo: {MODELO_FICHA if ficha else MODELO})"
    )

    try:
        registros = executar(settings)
    except QuotaEsgotada as erro:
        log(f"\n{erro}")
        return
    except RuntimeError as erro:
        log(f"\nNão foi possível criar a planilha: {erro}")
        return

    if not registros:
        return

    log("\n========== RESULTADO ==========")
    if ficha:
        r = resumo_fichas(registros)
        log(f"Fichas processadas: {r['processadas']}")
        log(f"Lidas: {r['lidas']}")
        log(f"Não identificadas: {r['nao_identificadas']}")
        log(f"Com ISBN: {r['com_isbn']}")
        log(f"Erros de processamento: {r['erros']}")
    else:
        r = resumo(registros)
        log(f"Imagens processadas: {r['processadas']}")
        log(f"Validados: {r['validados']}")
        log(f"Parciais (título bate, conferir autor): {r['parciais']}")
        log(f"Inconclusivos (fonte fora do ar): {r['inconclusivos']}")
        log(f"Erros de processamento: {r['erros']}")
        log(f"Faixa etária preenchida: {r['com_faixa']}")


if __name__ == "__main__":
    main()
