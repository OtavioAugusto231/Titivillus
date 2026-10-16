"""Execução por linha de comando: python -m titivillus.cli"""

from .config import API_KEY, GOOGLE_BOOKS_KEY, MODELO, Settings
from .log import log
from .pipeline import executar, listar_imagens, resumo


def main():
    settings = Settings()

    if not API_KEY:
        print("Chave Gemini ausente. Defina GEMINI_API_KEY (ambiente ou .env).")
        return

    if not GOOGLE_BOOKS_KEY:
        log(
            "Aviso: GOOGLE_BOOKS_API_KEY ausente. Google Books será tentado com "
            "retry curto e pulado por 15 min se continuar em 429."
        )

    settings.pasta_capas.mkdir(parents=True, exist_ok=True)
    log(
        f"Imagens encontradas: {len(listar_imagens(settings.pasta_capas))} "
        f"(modelo: {MODELO})"
    )

    try:
        registros = executar(settings)
    except RuntimeError as erro:
        log(f"\nNão foi possível criar a planilha: {erro}")
        return

    if not registros:
        return

    r = resumo(registros)
    log("\n========== RESULTADO ==========")
    log(f"Imagens processadas: {r['processadas']}")
    log(f"Validados: {r['validados']}")
    log(f"Parciais (título bate, conferir autor): {r['parciais']}")
    log(f"Inconclusivos (fonte fora do ar): {r['inconclusivos']}")
    log(f"Erros de processamento: {r['erros']}")
    log(f"Faixa etária preenchida: {r['com_faixa']}")


if __name__ == "__main__":
    main()
