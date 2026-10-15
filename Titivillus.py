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
# Modelo só da etapa de faixa etária (opcional; padrão = MODELO).
MODELO_FAIXA = os.environ.get("GEMINI_MODEL_FAIXA", "").strip() or MODELO

# Defina GEMINI_API_KEY no ambiente. Não grave a chave diretamente no código.
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY) if API_KEY else None

# Recomendado: sem chave a cota anônima do Google Books costuma dar 429.
# Crie em console.cloud.google.com (API "Books API") e exporte GOOGLE_BOOKS_API_KEY.
GOOGLE_BOOKS_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()
_google_books_bloqueado = False

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

FAIXAS = ["Livre", "7+", "10+", "12+", "14+", "16+", "18+"]

PROMPT = """
Analise a imagem da capa (ou lombada) de um livro.

Identifique:
- titulo: título da obra/série, SEM o número do volume;
- volume: número do volume/tomo/edição na série (apenas o número, ex.: "12").
  Procure na capa e na lombada: "Vol. 3", "nº 7", "Tomo 2", numeral grande
  isolado ou na lateral. Livros avulsos não têm volume;
- autor: nome do autor.

Regras:
- Não invente informações.
- Se não conseguir identificar um campo, use null. Em especial, só informe
  volume se o número estiver legível; na dúvida, use null.
- Não confunda editora, tradutor ou ilustrador com o autor.
- O autor pode ser pseudônimo, nome artístico ou nome de canal/youtuber/marca
  impresso na capa. Se um nome aparece como autoria, preencha o campo autor.
- Responda somente em JSON válido:
  {"titulo": "string ou null", "volume": "string ou null", "autor": "string ou null"}
"""

CAMPOS = [
    "titulo",
    "volume",
    "autor",
    "faixa_etaria",
    "titulo_google_books",
    "autor_google_books",
    "validado",
    "fonte_validacao",
    "arquivo",
    "erro",
]


class Capa(BaseModel):
    titulo: Optional[str] = None
    volume: Optional[str] = None
    autor: Optional[str] = None


class Autor(BaseModel):
    autor: Optional[str] = None


class FaixaEtaria(BaseModel):
    faixa_etaria: Optional[str] = None


PROMPT_AUTOR = """
Esta é a capa (ou lombada) de um livro. Diga APENAS quem aparece como autor.

Regras:
- Aceite pseudônimos, nomes artísticos e nomes de canal/youtuber/marca quando
  estiverem impressos como autoria (geralmente em destaque, perto do título).
- Se houver mais de um autor, separe por vírgula.
- Não use editora, tradutor ou ilustrador.
- Se realmente não houver nenhum nome de autoria visível, use null.
- Responda somente em JSON válido: {"autor": "string ou null"}
"""

PROMPT_FAIXA = """
Livro: "{titulo}"{autor_txt}.

Indique a faixa etária indicativa de leitura (público-alvo), considerando
temas, violência, conteúdo sexual, vocabulário e complexidade.

Escolha EXATAMENTE um destes valores: Livre, 7+, 10+, 12+, 14+, 16+, 18+.

Regras:
- Baseie-se na obra real. Se você não conhece este livro com segurança,
  use null. Não chute.
- Obras infantis ilustradas: Livre ou 7+. Infantojuvenil: 10+ a 14+.
  Conteúdo adulto explícito: 18+.
- Responda somente em JSON válido: {{"faixa_etaria": "valor ou null"}}
"""


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
        "volume": None,
        "autor": None,
        "faixa_etaria": None,
        "titulo_google_books": None,
        "autor_google_books": None,
        "validado": False,
        "arquivo": arquivo,
        "erro": erro,
    }


# ============================================================
# RENOMEAÇÃO DAS FOTOS
# ============================================================


def renomear_foto(path, titulo, autor, volume=None):
    titulo = limpar_nome(titulo) or "Título desconhecido"
    autor = limpar_nome(autor) or "Autor desconhecido"
    volume = limpar_nome(volume)
    if volume:
        titulo = f"{titulo} Vol {volume}"

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


def chamar_gemini(dados_imagem, mime, prompt=PROMPT, schema=Capa):
    ultimo_erro = None

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return client.models.generate_content(
                model=MODELO,
                contents=[
                    types.Part.from_bytes(data=dados_imagem, mime_type=mime),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
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


def ler_autor(path, mime):
    """Segunda leitura focada só no autor, usada quando a primeira vem vazia."""
    try:
        resposta = chamar_gemini(path.read_bytes(), mime, PROMPT_AUTOR, Autor)
        dados = json.loads(getattr(resposta, "text", None) or "{}")
        return texto_seguro(dados.get("autor")) if isinstance(dados, dict) else None
    except Exception as erro:
        print(f"  Segunda leitura do autor falhou: {erro}")
        return None


def ler_faixa_etaria(titulo, autor=None):
    """Chamada só de texto. Retorna uma das FAIXAS ou None."""
    if not titulo or client is None:
        return None

    autor_txt = f", de {autor}" if autor else ""
    prompt = PROMPT_FAIXA.format(titulo=titulo, autor_txt=autor_txt)

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = client.models.generate_content(
                model=MODELO_FAIXA,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FaixaEtaria,
                    temperature=0,
                ),
            )
            dados = json.loads(getattr(resposta, "text", None) or "{}")
            valor = (
                texto_seguro(dados.get("faixa_etaria"))
                if isinstance(dados, dict)
                else None
            )
            if not valor:
                return None
            valor = valor.replace(" ", "")
            return valor if valor in FAIXAS else None
        except genai_errors.APIError as erro:
            codigo = getattr(erro, "code", None)
            if codigo in CODIGOS_RETENTAVEIS and tentativa < TENTATIVAS:
                espera = 2**tentativa
                print(f"  API retornou {codigo}; nova tentativa em {espera}s...")
                time.sleep(espera)
                continue
            print(f"  Faixa etária falhou: {erro}")
            return None
        except Exception as erro:
            print(f"  Faixa etária falhou: {erro}")
            return None
    return None


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

    autor = texto_seguro(dados.get("autor"))
    if not autor:
        autor = ler_autor(path, mime)
        if autor:
            print(f"  Autor recuperado na segunda leitura: {autor!r}")

    return {
        "titulo": texto_seguro(dados.get("titulo")),
        "volume": texto_seguro(dados.get("volume")),
        "autor": autor,
    }


# ============================================================
# 2. VALIDAÇÃO COM GOOGLE BOOKS
# ============================================================


def buscar_google_books(consulta):
    global _google_books_bloqueado
    if _google_books_bloqueado:
        raise requests.RequestException("pulado: cota excedida (429) nesta execução")

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

    if resposta.status_code == 429:
        _google_books_bloqueado = True

    resposta.raise_for_status()
    corpo = resposta.json()
    itens = corpo.get("items", []) if isinstance(corpo, dict) else []
    return itens if isinstance(itens, list) else []


def buscar_open_library(titulo, autor):
    """Fallback sem chave. Devolve itens no mesmo formato do Google Books."""
    params = {"title": titulo, "limit": 10, "fields": "title,author_name"}
    if autor:
        params["author"] = autor

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
            print("  Open Library lento; tentando de novo...")
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

    fontes = [
        (
            "Google Books",
            lambda: [
                item
                for consulta in (estrita, solta)
                for item in buscar_google_books(consulta)
            ],
        ),
        ("Open Library", lambda: buscar_open_library(titulo, autor)),
    ]

    falhas = []
    consultou_alguma = False

    for nome, buscar in fontes:
        try:
            itens = buscar()
        except (requests.RequestException, ValueError) as erro:
            falhas.append(f"{nome}: {erro}")
            print(f"  {nome} indisponível, tentando próxima fonte...")
            continue

        consultou_alguma = True
        melhor = escolher_melhor(itens, titulo, autor)
        print(
            f"  {nome}: {len(itens)} candidato(s), match={'sim' if melhor else 'não'}"
        )
        if melhor:
            d["titulo_google_books"] = melhor["titulo"]
            d["autor_google_books"] = melhor["autor"]
            d["validado"] = True
            d["fonte_validacao"] = nome
            return d

    # Só marca erro se NENHUMA fonte respondeu. Sem match com fonte ativa não é erro.
    if not consultou_alguma and falhas:
        d["erro"] = "Falha na validação: " + " | ".join(falhas)

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

        # Título/autor canônicos do Google Books têm prioridade quando validado.
        titulo_faixa = (
            dados.get("titulo_google_books") if dados["validado"] else None
        ) or dados.get("titulo")
        autor_faixa = (
            dados.get("autor_google_books") if dados["validado"] else None
        ) or dados.get("autor")
        dados["faixa_etaria"] = ler_faixa_etaria(titulo_faixa, autor_faixa)

        print(
            f"  Lido: {dados.get('titulo')!r} | vol {dados.get('volume')!r} "
            f"| {dados.get('autor')!r} | faixa {dados.get('faixa_etaria')!r}"
        )
        if dados.get("erro"):
            print(f"  Erro: {dados['erro']}")
        elif dados["validado"]:
            print(f"  Validado: {dados['titulo_google_books']!r}")
        else:
            print("  Sem correspondência no Google Books.")

        if dados["validado"] or not RENOMEAR_APENAS_VALIDADOS:
            if dados.get("titulo"):
                dados["arquivo"] = renomear_foto(
                    path,
                    dados.get("titulo"),
                    dados.get("autor"),
                    dados.get("volume"),
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

    def numero_volume(valor):
        if isinstance(valor, str):
            achado = re.search(r"\d+", valor)
            if achado:
                return int(achado.group())
        return 0

    df["_ordem"] = df["titulo"].map(normalizar)
    df["_sem_titulo"] = df["titulo"].map(
        lambda valor: not (isinstance(valor, str) and valor.strip())
    )
    df["_vol"] = df["volume"].map(numero_volume)

    df = df.sort_values(by=["_sem_titulo", "_ordem", "_vol"], kind="stable").drop(
        columns=["_sem_titulo", "_ordem", "_vol"]
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
    com_faixa = sum(1 for r in registros if r.get("faixa_etaria"))

    print("\n========== RESULTADO ==========")
    print(f"Imagens processadas: {len(registros)}")
    print(f"Correspondências encontradas: {confirmados}")
    print(f"Faixa etária preenchida: {com_faixa}")
    print(f"Registros com erros: {erros}")
    print(f"Planilha criada: {ARQUIVO_EXCEL}")


if __name__ == "__main__":
    main()
