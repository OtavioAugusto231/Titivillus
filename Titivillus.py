import json
import os
import pathlib
import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd
import requests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = pathlib.Path(__file__).resolve().parent
PASTA_CAPAS = BASE_DIR / "capas"
ARQUIVO_EXCEL = BASE_DIR / "livros.xlsx"

# Pode sobrescrever via variável de ambiente sem editar o código.
MODELO = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

# Defina GEMINI_API_KEY no ambiente. Não grave a chave diretamente no código.
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY) if API_KEY else None

# Recomendado: sem chave a cota anônima do Google Books costuma dar 429.
# Crie em console.cloud.google.com (API "Books API") e exporte GOOGLE_BOOKS_API_KEY.
GOOGLE_BOOKS_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()

EXTENSOES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Renomeia a foto somente se o livro for confirmado no Google Books.
RENOMEAR_APENAS_VALIDADOS = True

TENTATIVAS = 3
CODIGOS_RETENTAVEIS = {429, 500, 502, 503, 504}
LIMITE_NOME_ARQUIVO = 80  # caracteres por campo (evita estourar 255 bytes)

PROMPT = """
Analise a imagem da capa (ou lombada) de um livro.

Identifique:
- titulo: título do livro;
- autor: nome do autor.

Regras:
- Não invente informações.
- Se não conseguir identificar um campo, use null.
- Não confunda editora, tradutor ou ilustrador com o autor.
- Responda somente em JSON válido:
  {"titulo": "string ou null", "autor": "string ou null"}
"""

CAMPOS = [
    "titulo",
    "autor",
    "titulo_google_books",
    "autor_google_books",
    "validado",
    "arquivo",
    "erro",
]


class Capa(BaseModel):
    titulo: Optional[str] = None
    autor: Optional[str] = None


# ============================================================
# UTILITÁRIOS
# ============================================================


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
    """Normaliza texto para comparação: sem acentos, pontuação e caixa."""
    texto = texto_seguro(texto) or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto.casefold())
    return " ".join(texto.split())


def similaridade(a, b):
    """Similaridade entre 0 e 1, tolerante a subtítulo e a ordem de tokens."""
    a = normalizar(a)
    b = normalizar(b)
    if not a or not b:
        return 0.0

    direta = SequenceMatcher(None, a, b).ratio()

    # "Sobrenome, Nome" vs "Nome Sobrenome"
    ordenada = SequenceMatcher(
        None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))
    ).ratio()

    # Título sem subtítulo (ou o contrário)
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


def resultado_vazio(arquivo, erro):
    return {
        "titulo": None,
        "autor": None,
        "titulo_google_books": None,
        "autor_google_books": None,
        "validado": False,
        "arquivo": arquivo,
        "erro": erro,
    }


# ============================================================
# RENOMEAÇÃO DAS FOTOS
# ============================================================


def renomear_foto(path, titulo, autor):
    titulo = limpar_nome(titulo) or "Título desconhecido"
    autor = limpar_nome(autor) or "Autor desconhecido"

    novo_nome = f"{titulo} - {autor}{path.suffix.lower()}"
    destino = path.with_name(novo_nome)

    if destino == path:
        return path.name

    if destino.exists():
        base = destino.stem
        contador = 2
        while destino.exists():
            destino = path.with_name(f"{base} ({contador}){path.suffix.lower()}")
            contador += 1

    path.rename(destino)
    print(f"  Foto renomeada: {destino.name}")
    return destino.name


# ============================================================
# 1. RECONHECIMENTO DA CAPA COM GEMINI
# ============================================================


def chamar_gemini(dados_imagem, mime):
    ultimo_erro = None

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return client.models.generate_content(
                model=MODELO,
                contents=[
                    types.Part.from_bytes(data=dados_imagem, mime_type=mime),
                    PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Capa,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as erro:
            ultimo_erro = erro
            codigo = getattr(erro, "code", None)

            if codigo == 404:
                raise RuntimeError(
                    f"Modelo '{MODELO}' não encontrado. Liste os disponíveis com "
                    "client.models.list() e defina GEMINI_MODEL com o ID exato."
                ) from erro

            if codigo in CODIGOS_RETENTAVEIS and tentativa < TENTATIVAS:
                espera = 2**tentativa
                print(f"  API retornou {codigo}; nova tentativa em {espera}s...")
                time.sleep(espera)
                continue
            raise

    raise ultimo_erro  # pragma: no cover


def ler_capa(path):
    if client is None:
        raise RuntimeError(
            "Chave Gemini ausente. Defina a variável de ambiente GEMINI_API_KEY."
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

    return {
        "titulo": texto_seguro(dados.get("titulo")),
        "autor": texto_seguro(dados.get("autor")),
    }


# ============================================================
# 2. VALIDAÇÃO COM GOOGLE BOOKS
# ============================================================


def buscar_google_books(consulta):
    params = {"q": consulta, "maxResults": 10, "printType": "books"}
    if GOOGLE_BOOKS_KEY:
        params["key"] = GOOGLE_BOOKS_KEY

    for tentativa in range(1, TENTATIVAS + 1):
        resposta = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params,
            timeout=15,
        )
        if resposta.status_code in CODIGOS_RETENTAVEIS and tentativa < TENTATIVAS:
            espera = 2**tentativa
            print(
                f"  Google Books {resposta.status_code}; nova tentativa em {espera}s..."
            )
            time.sleep(espera)
            continue
        break

    resposta.raise_for_status()
    corpo = resposta.json()
    itens = corpo.get("items", []) if isinstance(corpo, dict) else []
    return itens if isinstance(itens, list) else []


def escolher_melhor(itens, titulo, autor):
    melhor = None
    melhor_pontuacao = 0.0

    for item in itens:
        if not isinstance(item, dict):
            continue
        volume = item.get("volumeInfo", {})
        if not isinstance(volume, dict):
            continue

        titulo_api = texto_seguro(volume.get("title"))
        if not titulo_api:
            continue

        autores_api = volume.get("authors", [])
        if not isinstance(autores_api, list):
            autores_api = []
        autores_api = [a for a in map(texto_seguro, autores_api) if a]

        pontuacao_titulo = similaridade(titulo, titulo_api)

        if autor:
            if not autores_api:
                continue
            pontuacao_autor = max(similaridade(autor, nome) for nome in autores_api)
            if pontuacao_titulo < 0.70 or pontuacao_autor < 0.65:
                continue
            pontuacao = 0.70 * pontuacao_titulo + 0.30 * pontuacao_autor
        else:
            if pontuacao_titulo < 0.85:
                continue
            pontuacao = pontuacao_titulo

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = {
                "titulo": titulo_api,
                "autor": ", ".join(autores_api) or None,
            }

    return melhor


def validar(d):
    d["titulo_google_books"] = None
    d["autor_google_books"] = None
    d["validado"] = False

    titulo = texto_seguro(d.get("titulo"))
    autor = texto_seguro(d.get("autor"))

    if not titulo:
        return d

    # Consulta estrita primeiro; se não achar nada, consulta solta.
    estrita = f'intitle:"{titulo}"'
    if autor:
        estrita += f' inauthor:"{autor}"'
    solta = f"{titulo} {autor}" if autor else titulo

    try:
        melhor = None
        for consulta in (estrita, solta):
            itens = buscar_google_books(consulta)
            melhor = escolher_melhor(itens, titulo, autor)
            if melhor:
                break
    except (requests.RequestException, ValueError) as erro:
        d["erro"] = f"Falha no Google Books: {erro}"
        return d

    if melhor:
        d["titulo_google_books"] = melhor["titulo"]
        d["autor_google_books"] = melhor["autor"]
        d["validado"] = True

    return d


# ============================================================
# 3. PROCESSAMENTO INDIVIDUAL
# ============================================================


def processar_imagem(path):
    print(f"\nProcessando: {path.name}")

    try:
        dados = ler_capa(path)
        dados["erro"] = None
        dados["arquivo"] = path.name
        dados = validar(dados)

        print(f"  Lido: {dados.get('titulo')!r} / {dados.get('autor')!r}")
        if dados.get("erro"):
            print(f"  Erro: {dados['erro']}")
        elif dados["validado"]:
            print(f"  Validado: {dados['titulo_google_books']!r}")
        else:
            print("  Sem correspondência no Google Books.")

        if dados["validado"] or not RENOMEAR_APENAS_VALIDADOS:
            if dados.get("titulo"):
                dados["arquivo"] = renomear_foto(
                    path, dados.get("titulo"), dados.get("autor")
                )

        return dados

    except Exception as erro:
        print(f"  Erro: {erro}")
        return resultado_vazio(path.name, f"Falha no processamento: {erro}")


# ============================================================
# 4. ORDENAÇÃO ALFABÉTICA E EXPORTAÇÃO
# ============================================================


def exportar_excel(registros):
    df = pd.DataFrame(registros, columns=CAMPOS)

    df["_ordem"] = df["titulo"].map(normalizar)
    df["_sem_titulo"] = df["titulo"].map(lambda valor: not bool(texto_seguro(valor)))

    df = df.sort_values(by=["_sem_titulo", "_ordem"], kind="stable").drop(
        columns=["_sem_titulo", "_ordem"]
    )

    try:
        df.to_excel(ARQUIVO_EXCEL, index=False)
    except ModuleNotFoundError as erro:
        if "openpyxl" in str(erro):
            raise RuntimeError(
                "A biblioteca openpyxl não está instalada no ambiente virtual. "
                "Execute: venv/bin/python -m pip install openpyxl"
            ) from erro
        raise
    except PermissionError as erro:
        raise RuntimeError(
            f"Sem permissão para gravar {ARQUIVO_EXCEL}. "
            "Feche a planilha se ela estiver aberta."
        ) from erro


# ============================================================
# 5. EXECUÇÃO PRINCIPAL
# ============================================================


def main():
    PASTA_CAPAS.mkdir(parents=True, exist_ok=True)

    imagens = sorted(
        p
        for p in PASTA_CAPAS.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES
    )

    if not imagens:
        print(f"Nenhuma imagem encontrada em: {PASTA_CAPAS}")
        print("Adicione arquivos JPG, JPEG, PNG ou WEBP à pasta capas.")
        return

    print(f"Imagens encontradas: {len(imagens)} (modelo: {MODELO})")
    registros = [processar_imagem(imagem) for imagem in imagens]

    try:
        exportar_excel(registros)
    except Exception as erro:
        print(f"\nNão foi possível criar a planilha: {erro}")
        return

    confirmados = sum(1 for r in registros if r["validado"])
    erros = sum(1 for r in registros if r["erro"])

    print("\n========== RESULTADO ==========")
    print(f"Imagens processadas: {len(registros)}")
    print(f"Correspondências encontradas: {confirmados}")
    print(f"Registros com erros: {erros}")
    print(f"Planilha criada: {ARQUIVO_EXCEL}")


if __name__ == "__main__":
    main()
