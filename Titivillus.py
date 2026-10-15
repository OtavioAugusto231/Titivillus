import json
import os
import pathlib
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd
import requests
from google import genai
from google.genai import types

# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = pathlib.Path(__file__).resolve().parent
PASTA_CAPAS = BASE_DIR / "capas"
ARQUIVO_EXCEL = BASE_DIR / "livros.xlsx"

MODELO = "gemini-3.1-flash-lite"

client = genai.Client(
    api_key=os.environ["SUA_CHAVE_API_AQUI"]
)  # Substitua pela sua chave de API do Gemini.

PROMPT = """
Analise a imagem da capa de um livro.

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


# ============================================================
# UTILITÁRIOS
# ============================================================


def normalizar(texto):
    """Normaliza texto para comparação sem acentos."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto.casefold())
    return " ".join(texto.split())


def similaridade(a, b):
    """Compara duas strings e retorna um valor entre 0 e 1."""
    a = normalizar(a)
    b = normalizar(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def limpar_nome(texto):
    """Remove caracteres proibidos em nomes de arquivos."""
    texto = texto or ""
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)
    texto = texto.strip().rstrip(". ")

    # Evita nomes vazios ou reservados no Windows.
    if texto.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
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

    # Não renomeia se já estiver com o nome desejado.
    if destino.resolve() == path.resolve():
        return path.name

    # Evita sobrescrever uma imagem existente.
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


def ler_capa(path):
    tipos_midia = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    extensao = path.suffix.lower()

    if extensao not in tipos_midia:
        raise ValueError("Formato de imagem não suportado.")

    resposta = client.models.generate_content(
        model=MODELO,
        contents=[
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type=tipos_midia[extensao],
            ),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "titulo": {"type": ["STRING", "NULL"]},
                    "autor": {"type": ["STRING", "NULL"]},
                },
                "required": ["titulo", "autor"],
            },
        ),
    )

    if not resposta.text:
        raise ValueError("O Gemini retornou uma resposta vazia.")

    dados = json.loads(resposta.text)

    titulo = dados.get("titulo")
    autor = dados.get("autor")

    if titulo is not None and not isinstance(titulo, str):
        raise ValueError("Título retornado em formato inválido.")

    if autor is not None and not isinstance(autor, str):
        raise ValueError("Autor retornado em formato inválido.")

    return {
        "titulo": titulo.strip() if titulo and titulo.strip() else None,
        "autor": autor.strip() if autor and autor.strip() else None,
    }


# ============================================================
# 2. VALIDAÇÃO COM GOOGLE BOOKS
# ============================================================


def validar(d):
    d["titulo_google_books"] = None
    d["autor_google_books"] = None
    d["validado"] = False

    if not d["titulo"]:
        return d

    consulta = f'intitle:"{d["titulo"]}"'

    if d["autor"]:
        consulta += f' inauthor:"{d["autor"]}"'

    try:
        resposta = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={
                "q": consulta,
                "maxResults": 5,
                "printType": "books",
            },
            timeout=15,
        )

        resposta.raise_for_status()
        itens = resposta.json().get("items", [])

    except (requests.RequestException, ValueError) as erro:
        d["erro"] = f"Falha no Google Books: {erro}"
        return d

    melhor = None
    melhor_pontuacao = 0.0

    for item in itens:
        volume = item.get("volumeInfo", {})
        titulo_api = volume.get("title")

        if not titulo_api:
            continue

        autores_api = volume.get("authors", [])

        pontuacao_titulo = similaridade(
            d["titulo"],
            titulo_api,
        )

        if d["autor"]:
            if not autores_api:
                continue

            pontuacao_autor = max(
                similaridade(d["autor"], autor_api) for autor_api in autores_api
            )

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

        dados = validar(dados)

        # Renomeia a imagem usando os dados reconhecidos.
        novo_nome = renomear_foto(
            path,
            dados["titulo"],
            dados["autor"],
        )

        dados["arquivo"] = novo_nome

        return dados

    except Exception as erro:
        print(f"  Erro: {erro}")

        return resultado_vazio(
            path.name,
            f"Falha no processamento: {erro}",
        )


# ============================================================
# 4. ORDENAÇÃO ALFABÉTICA E EXPORTAÇÃO
# ============================================================


def exportar_excel(registros):
    df = pd.DataFrame(registros, columns=CAMPOS)

    # Chave temporária que ignora acentos e caixa.
    df["_ordem"] = df["titulo"].fillna("").map(normalizar)

    # Títulos desconhecidos ficam no final.
    df["_sem_titulo"] = df["titulo"].isna() | (
        df["titulo"].fillna("").str.strip() == ""
    )

    df = df.sort_values(
        by=["_sem_titulo", "_ordem"],
        kind="stable",
    ).drop(columns=["_sem_titulo", "_ordem"])

    df.to_excel(ARQUIVO_EXCEL, index=False)


# ============================================================
# 5. EXECUÇÃO PRINCIPAL
# ============================================================


def main():
    PASTA_CAPAS.mkdir(parents=True, exist_ok=True)

    imagens = sorted(
        p
        for p in PASTA_CAPAS.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    if not imagens:
        print(f"Nenhuma imagem encontrada em: {PASTA_CAPAS}")
        print("Adicione arquivos JPG, JPEG ou PNG à pasta capas.")
        return

    print(f"Imagens encontradas: {len(imagens)}")

    registros = []

    for imagem in imagens:
        registro = processar_imagem(imagem)
        registros.append(registro)

    exportar_excel(registros)

    confirmados = sum(1 for registro in registros if registro["validado"])

    erros = sum(1 for registro in registros if registro["erro"])

    print("\n========== RESULTADO ==========")
    print(f"Imagens processadas: {len(registros)}")
    print(f"Correspondências encontradas: {confirmados}")
    print(f"Registros com erros: {erros}")
    print(f"Planilha criada: {ARQUIVO_EXCEL}")


if __name__ == "__main__":
    main()
