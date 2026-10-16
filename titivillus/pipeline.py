"""Orquestração: processa cada foto e exporta a planilha.
Usado igualmente pelo CLI e pela GUI."""

from .arquivos import renomear_foto
from .config import EXTENSOES
from .leitor_capa import ler_capa, ler_faixa_etaria
from .log import log
from .modelos import (
    STATUS_ERRO,
    STATUS_INCONCLUSIVO,
    STATUS_PARCIAL,
    STATUS_POR_MODO,
    STATUS_VALIDADO,
    resultado_vazio,
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

    except Exception as erro:
        log(f"  Erro: {erro}")
        return resultado_vazio(path.name, f"Falha no processamento: {erro}")


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
    settings.pasta_capas.mkdir(parents=True, exist_ok=True)
    imagens = listar_imagens(settings.pasta_capas)

    if not imagens:
        log(f"Nenhuma imagem encontrada em: {settings.pasta_capas}")
        log("Adicione arquivos JPG, JPEG, PNG ou WEBP à pasta.")
        return []

    total = len(imagens)
    registros = []
    try:
        for i, imagem in enumerate(imagens):
            if cancelar is not None and cancelar.is_set():
                log("\nCancelado. Exportando o que já foi processado...")
                break
            if on_progresso:
                on_progresso(i, total, imagem.name)
            registro = processar_imagem(imagem, settings.modo_renomear)
            registros.append(registro)
            if on_resultado:
                on_resultado(registro)
            if on_progresso:
                on_progresso(i + 1, total, None)
    except KeyboardInterrupt:
        log("\nInterrompido. Exportando o que já foi processado...")

    if registros:
        exportar_excel(registros, settings.arquivo_excel)
        log(f"\nPlanilha criada: {settings.arquivo_excel}")

    return registros
