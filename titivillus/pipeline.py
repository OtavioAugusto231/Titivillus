"""Orquestração: processa cada foto e exporta a planilha.
Usado igualmente pelo CLI e pela GUI."""

from .arquivos import renomear_foto
from .config import EXTENSOES, MODO_CAPA, MODO_FICHA
from .leitor_capa import QuotaEsgotada, ler_capa, ler_faixa_etaria
from .leitor_ficha import ler_ficha
from .log import log
from .modelos import (
    STATUS_ERRO,
    STATUS_FICHA_LIDA,
    STATUS_FICHA_NAO_IDENTIFICADA,
    STATUS_INCONCLUSIVO,
    STATUS_PARCIAL,
    STATUS_POR_MODO,
    STATUS_VALIDADO,
    resultado_vazio,
    resultado_vazio_ficha,
)
from .planilha import exportar_excel
from .validacao import validar


def listar_imagens(pasta):
    if not pasta.is_dir():
        return []
    return sorted(
        p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSOES
    )


def processar_imagem(path, modo_renomear):
    log(f"\nProcessando: {path.name}")

    # A lista é tirada no início da execução; se o arquivo sumiu depois
    # (renomeado/movido por outra execução, sync, explorador de arquivos...),
    # falha com mensagem clara em vez de estourar Errno 2 lá no meio.
    if not path.exists():
        msg = (
            "Arquivo não existe mais (renomeado ou movido depois da listagem; "
            "há outra execução do script ou sincronização mexendo na pasta?)"
        )
        log(f"  Pulado: {msg}")
        return resultado_vazio(path.name, msg)

    try:
        dados = ler_capa(path)
        dados["erro"] = None
        dados["arquivo"] = path.name
        dados = validar(dados)

        # Título/autor canônicos validados têm prioridade para a faixa etária.
        titulo_faixa = (
            dados.get("titulo_google_books") if dados["validado"] else None
        ) or dados.get("titulo")
        autor_faixa = (
            dados.get("autor_google_books") if dados["validado"] else None
        ) or dados.get("autor")
        dados["faixa_etaria"] = ler_faixa_etaria(titulo_faixa, autor_faixa)

        log(
            f"  Lido: {dados.get('titulo')!r} | vol {dados.get('volume')!r} "
            f"| {dados.get('autor')!r} | faixa {dados.get('faixa_etaria')!r}"
        )
        log(f"  Status: {dados['status']}")
        if dados["validado"]:
            log(
                f"  Validado ({dados['fonte_validacao']}): "
                f"{dados['titulo_google_books']!r}"
            )
        elif dados["status"] == STATUS_PARCIAL:
            log(
                f"  Sugestão ({dados['fonte_validacao']}): "
                f"{dados['titulo_google_books']!r} de {dados['autor_google_books']!r}"
            )
        elif dados.get("erro"):
            log(f"  Fonte com falha: {dados['erro']}")

        if dados["status"] in STATUS_POR_MODO[modo_renomear] and dados.get("titulo"):
            dados["arquivo"] = renomear_foto(
                path,
                dados.get("titulo"),
                dados.get("autor"),
                dados.get("volume"),
            )

        return dados

    except QuotaEsgotada:
        raise
    except Exception as erro:
        log(f"  Erro: {erro}")
        return resultado_vazio(path.name, f"Falha no processamento: {erro}")


def processar_ficha(path):
    log(f"\nProcessando ficha: {path.name}")

    if not path.exists():
        msg = "Arquivo não existe mais (renomeado ou movido depois da listagem)."
        log(f"  Pulado: {msg}")
        return resultado_vazio_ficha(path.name, msg)

    try:
        dados = ler_ficha(path)
        dados["arquivo"] = path.name
        dados["erro"] = None
        identificada = bool(dados.get("titulo") or dados.get("isbn"))
        dados["status"] = (
            STATUS_FICHA_LIDA if identificada else STATUS_FICHA_NAO_IDENTIFICADA
        )
        log(
            f"  Lido: {dados.get('titulo')!r} | {dados.get('autores')!r} | "
            f"{dados.get('editora')!r} | {dados.get('ano_publicacao')!r} | "
            f"ISBN {dados.get('isbn')!r}"
        )
        log(f"  Status: {dados['status']}")
        return dados
    except QuotaEsgotada:
        raise
    except Exception as erro:
        log(f"  Erro: {erro}")
        return resultado_vazio_ficha(path.name, f"Falha no processamento: {erro}")


def resumo_fichas(registros):
    return {
        "processadas": len(registros),
        "lidas": sum(1 for r in registros if r["status"] == STATUS_FICHA_LIDA),
        "nao_identificadas": sum(
            1 for r in registros if r["status"] == STATUS_FICHA_NAO_IDENTIFICADA
        ),
        "com_isbn": sum(1 for r in registros if r.get("isbn")),
        "erros": sum(1 for r in registros if r["status"] == STATUS_ERRO),
    }


def resumo(registros):
    return {
        "processadas": len(registros),
        "validados": sum(1 for r in registros if r["validado"]),
        "parciais": sum(1 for r in registros if r["status"] == STATUS_PARCIAL),
        "inconclusivos": sum(
            1 for r in registros if r["status"] == STATUS_INCONCLUSIVO
        ),
        "erros": sum(1 for r in registros if r["status"] == STATUS_ERRO),
        "com_faixa": sum(1 for r in registros if r.get("faixa_etaria")),
    }


def executar(settings, on_resultado=None, on_progresso=None, cancelar=None):
    """Processa a pasta inteira e exporta a planilha.

    on_resultado(registro): chamado ao fim de cada imagem.
    on_progresso(feitas, total, atual): atual é o nome da imagem em curso
        (ou None quando acabou de terminar uma).
    cancelar: threading.Event; checado entre imagens.
    Retorna a lista de registros. Levanta RuntimeError se a planilha falhar.
    """
    ficha = settings.modo == MODO_FICHA
    pasta = settings.pasta_fichas if ficha else settings.pasta_capas
    arquivo_excel = settings.arquivo_excel_fichas if ficha else settings.arquivo_excel

    pasta.mkdir(parents=True, exist_ok=True)
    imagens = listar_imagens(pasta)

    if not imagens:
        log(f"Nenhuma imagem encontrada em: {pasta}")
        log("Adicione arquivos JPG, JPEG, PNG ou WEBP à pasta.")
        return []

    total = len(imagens)
    registros = []
    erro_quota = None
    try:
        for i, imagem in enumerate(imagens):
            if cancelar is not None and cancelar.is_set():
                log("\nCancelado. Exportando o que já foi processado...")
                break
            if on_progresso:
                on_progresso(i, total, imagem.name)
            if ficha:
                registro = processar_ficha(imagem)
            else:
                registro = processar_imagem(imagem, settings.modo_renomear)
            registros.append(registro)
            if on_resultado:
                on_resultado(registro)
            if on_progresso:
                on_progresso(i + 1, total, None)
    except QuotaEsgotada as erro:
        erro_quota = erro
        log(f"\n{erro}")
        log("Exportando o que já foi processado...")
    except KeyboardInterrupt:
        log("\nInterrompido. Exportando o que já foi processado...")

    if registros:
        exportar_excel(registros, arquivo_excel, MODO_FICHA if ficha else MODO_CAPA)
        log(f"\nPlanilha criada: {arquivo_excel}")

    if erro_quota is not None:
        salvo = (
            f"\n\nJá processado: {len(registros)} de {total}; salvo em {arquivo_excel}."
            if registros
            else ""
        )
        raise QuotaEsgotada(f"{erro_quota}{salvo}")

    return registros
