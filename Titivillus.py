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


def carregar_env(caminho):
    """Carrega KEY=VALOR de um .env simples (sem dependências).
    Variáveis já exportadas no shell têm prioridade."""
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


carregar_env(BASE_DIR / ".env")

PASTA_CAPAS = BASE_DIR / "capas"
ARQUIVO_EXCEL = BASE_DIR / "livros.xlsx"

MODELO = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
MODELO_FAIXA = os.environ.get("GEMINI_MODEL_FAIXA", "").strip() or MODELO
MODELO_FAIXA_FALLBACK = os.environ.get(
    "GEMINI_MODEL_FAIXA_FALLBACK", "gemini-2.5-flash"
).strip()

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY) if API_KEY else None

# Sem chave, a cota anônima do Google Books estoura (429) quase sempre.
# Crie em console.cloud.google.com (ative "Books API") e coloque no .env:
#   GOOGLE_BOOKS_API_KEY=sua_chave
GOOGLE_BOOKS_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()

EXTENSOES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Renomeia a foto somente se o livro for confirmado (status "validado").
RENOMEAR_APENAS_VALIDADOS = True

CODIGOS_RETENTAVEIS = {429, 500, 502, 503, 504}
ESPERAS_GEMINI = (5, 15, 30)
ESPERAS_BOOKS = (5, 15, 40)
ESPERAS_BOOKS_SEM_CHAVE = (5,)  # sem chave, insistir só desperdiça tempo
GB_INTERVALO = 1.2
GB_COOLDOWN_COM_CHAVE = 120  # s sem consultar o Google Books após esgotar retries
GB_COOLDOWN_SEM_CHAVE = 900
LIMITE_NOME_ARQUIVO = 80

LIMIAR_TITULO = 0.70
LIMIAR_AUTOR = 0.65
LIMIAR_TITULO_SEM_AUTOR = 0.85
LIMIAR_PARCIAL = 0.92  # só título: sugere, mas NÃO valida nem renomeia

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
- Transcreva nomes letra por letra, com atenção à primeira letra (erros comuns:
  M/I/N, O/Q, rn/m).
- Responda somente em JSON válido:
  {"titulo": "string ou null", "volume": "string ou null", "autor": "string ou null"}
"""

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

CAMPOS = [
    "titulo",
    "volume",
    "autor",
    "faixa_etaria",
    "titulo_google_books",
    "autor_google_books",
    "validado",
    "status",
    "fonte_validacao",
    "arquivo",
    "erro",
]

STATUS_VALIDADO = "validado"
STATUS_PARCIAL = "parcial (conferir autor)"
STATUS_SEM_MATCH = "sem correspondência"
STATUS_INCONCLUSIVO = "inconclusivo (fonte indisponível)"
STATUS_ERRO = "erro"


class Capa(BaseModel):
    titulo: Optional[str] = None
    volume: Optional[str] = None
    autor: Optional[str] = None


class Autor(BaseModel):
    autor: Optional[str] = None


class FaixaEtaria(BaseModel):
    faixa_etaria: Optional[str] = None


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


def resultado_vazio(arquivo, erro):
    return {
        "titulo": None,
        "volume": None,
        "autor": None,
        "faixa_etaria": None,
        "titulo_google_books": None,
        "autor_google_books": None,
        "validado": False,
        "status": STATUS_ERRO,
        "fonte_validacao": None,
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


def gerar_com_retry(modelo, contents, schema):
    """generate_content com backoff para 429/5xx. Levanta o erro final."""
    for tentativa in range(len(ESPERAS_GEMINI) + 1):
        try:
            return client.models.generate_content(
                model=modelo,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as erro:
            codigo = getattr(erro, "code", None)

            if codigo == 404:
                raise RuntimeError(
                    f"Modelo '{modelo}' não encontrado. Liste os disponíveis com "
                    "client.models.list() e defina GEMINI_MODEL com o ID exato."
                ) from erro

            if codigo in CODIGOS_RETENTAVEIS and tentativa < len(ESPERAS_GEMINI):
                espera = ESPERAS_GEMINI[tentativa]
                print(f"  API retornou {codigo}; nova tentativa em {espera}s...")
                time.sleep(espera)
                continue
            raise


def chamar_gemini(dados_imagem, mime, prompt=PROMPT, schema=Capa):
    return gerar_com_retry(
        MODELO,
        [types.Part.from_bytes(data=dados_imagem, mime_type=mime), prompt],
        schema,
    )


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
    """Chamada só de texto. Tenta o modelo principal e depois o fallback.
    Retorna uma das FAIXAS ou None."""
    if not titulo or client is None:
        return None

    autor_txt = f", de {autor}" if autor else ""
    prompt = PROMPT_FAIXA.format(titulo=titulo, autor_txt=autor_txt)

    modelos = [MODELO_FAIXA]
    if MODELO_FAIXA_FALLBACK and MODELO_FAIXA_FALLBACK != MODELO_FAIXA:
        modelos.append(MODELO_FAIXA_FALLBACK)

    for modelo in modelos:
        try:
            resposta = gerar_com_retry(modelo, [prompt], FaixaEtaria)
        except Exception as erro:
            print(f"  Faixa etária falhou em {modelo}: {erro}")
            continue

        try:
            dados = json.loads(getattr(resposta, "text", None) or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        valor = (
            texto_seguro(dados.get("faixa_etaria")) if isinstance(dados, dict) else None
        )
        if not valor:
            return None  # "não sei"; fallback não muda isso
        valor = valor.replace(" ", "")
        return valor if valor in FAIXAS else None

    return None


def ler_capa(path):
    if client is None:
        raise RuntimeError(
            "Chave Gemini ausente. Defina GEMINI_API_KEY (ambiente ou .env)."
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
# 2. VALIDAÇÃO (GOOGLE BOOKS + OPEN LIBRARY)
# ============================================================

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
            print(
                f"  Google Books segue em {resposta.status_code}; "
                f"pulando-o pelos próximos {cooldown // 60} min."
            )
            break

        espera = esperas[tentativa]
        retry_after = resposta.headers.get("Retry-After", "")
        if retry_after.isdigit():
            espera = max(espera, int(retry_after))
        print(f"  Google Books {resposta.status_code}; nova tentativa em {espera}s...")
        time.sleep(espera)

    resposta.raise_for_status()
    corpo = resposta.json()
    itens = corpo.get("items", []) if isinstance(corpo, dict) else []
    return itens if isinstance(itens, list) else []


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


def _extrair(item):
    """Devolve (titulo_api, [autores_api]) ou None se o item for inválido."""
    if not isinstance(item, dict):
        return None
    volume = item.get("volumeInfo", {})
    if not isinstance(volume, dict):
        return None
    titulo_api = texto_seguro(volume.get("title"))
    if not titulo_api:
        return None
    autores = volume.get("authors", [])
    if not isinstance(autores, list):
        autores = []
    return titulo_api, [a for a in map(texto_seguro, autores) if a]


def escolher_melhor(itens, titulo, autor):
    """Match completo: título E autor (quando há autor)."""
    melhor = None
    melhor_pontuacao = 0.0

    for item in itens:
        extraido = _extrair(item)
        if not extraido:
            continue
        titulo_api, autores_api = extraido

        pontuacao_titulo = similaridade(titulo, titulo_api)

        if autor:
            if not autores_api:
                continue
            pontuacao_autor = max(similaridade(autor, nome) for nome in autores_api)
            if pontuacao_titulo < LIMIAR_TITULO or pontuacao_autor < LIMIAR_AUTOR:
                continue
            pontuacao = 0.70 * pontuacao_titulo + 0.30 * pontuacao_autor
        else:
            if pontuacao_titulo < LIMIAR_TITULO_SEM_AUTOR:
                continue
            pontuacao = pontuacao_titulo

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = {"titulo": titulo_api, "autor": ", ".join(autores_api) or None}

    return melhor


def escolher_parcial(itens, titulo):
    """Título quase idêntico, autor divergente/ausente. Serve de SUGESTÃO para
    revisão humana (ex.: autor lido errado no OCR); nunca valida nem renomeia."""
    melhor = None
    melhor_pontuacao = 0.0
    for item in itens:
        extraido = _extrair(item)
        if not extraido:
            continue
        titulo_api, autores_api = extraido
        pontuacao = similaridade(titulo, titulo_api)
        if pontuacao >= LIMIAR_PARCIAL and pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = {"titulo": titulo_api, "autor": ", ".join(autores_api) or None}
    return melhor


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


def validar(d):
    d["titulo_google_books"] = None
    d["autor_google_books"] = None
    d["validado"] = False
    d["fonte_validacao"] = None
    d["status"] = STATUS_SEM_MATCH

    titulo = texto_seguro(d.get("titulo"))
    autor = texto_seguro(d.get("autor"))

    if not titulo:
        return d

    estrita = f'intitle:"{titulo}"'
    if autor:
        estrita += f' inauthor:"{autor}"'
    solta = f"{titulo} {autor}" if autor else titulo

    fontes = [
        (
            "Google Books",
            lambda: buscar_google_books_duas_consultas(estrita, solta, titulo, autor),
        ),
        ("Open Library", lambda: buscar_open_library(titulo, autor)),
    ]

    falhas = []
    todos = []  # (fonte, itens) das fontes que responderam

    for nome, buscar in fontes:
        try:
            itens = buscar()
        except (requests.RequestException, ValueError) as erro:
            falhas.append(f"{nome}: {erro}")
            print(f"  {nome} indisponível, tentando próxima fonte...")
            continue

        melhor = escolher_melhor(itens, titulo, autor)
        print(
            f"  {nome}: {len(itens)} candidato(s), match={'sim' if melhor else 'não'}"
        )
        if melhor:
            d["titulo_google_books"] = melhor["titulo"]
            d["autor_google_books"] = melhor["autor"]
            d["validado"] = True
            d["status"] = STATUS_VALIDADO
            d["fonte_validacao"] = nome
            return d
        todos.append((nome, itens))

    # Sem match completo: procura sugestão por título (revisão humana).
    for nome, itens in todos:
        parcial = escolher_parcial(itens, titulo)
        if parcial:
            d["titulo_google_books"] = parcial["titulo"]
            d["autor_google_books"] = parcial["autor"]
            d["fonte_validacao"] = f"{nome} (só título)"
            d["status"] = STATUS_PARCIAL
            break

    # Fonte que falhou torna o "sem match" inconclusivo.
    if falhas:
        d["erro"] = "Validação incompleta: " + " | ".join(falhas)
        if d["status"] == STATUS_SEM_MATCH:
            d["status"] = STATUS_INCONCLUSIVO

    return d


# ============================================================
# 3. PROCESSAMENTO INDIVIDUAL
# ============================================================


def processar_imagem(path):
    print(f"\nProcessando: {path.name}")

    # A lista é tirada no início da execução; se o arquivo sumiu depois
    # (renomeado/movido por outra execução, sync, explorador de arquivos...),
    # falha com mensagem clara em vez de estourar Errno 2 lá no meio.
    if not path.exists():
        msg = (
            "Arquivo não existe mais (renomeado ou movido depois da listagem; "
            "há outra execução do script ou sincronização mexendo na pasta?)"
        )
        print(f"  Pulado: {msg}")
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

        print(
            f"  Lido: {dados.get('titulo')!r} | vol {dados.get('volume')!r} "
            f"| {dados.get('autor')!r} | faixa {dados.get('faixa_etaria')!r}"
        )
        print(f"  Status: {dados['status']}")
        if dados["validado"]:
            print(
                f"  Validado ({dados['fonte_validacao']}): "
                f"{dados['titulo_google_books']!r}"
            )
        elif dados["status"] == STATUS_PARCIAL:
            print(
                f"  Sugestão ({dados['fonte_validacao']}): "
                f"{dados['titulo_google_books']!r} de {dados['autor_google_books']!r}"
            )
        elif dados.get("erro"):
            print(f"  Fonte com falha: {dados['erro']}")

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
                "Execute: .venv/bin/python -m pip install openpyxl"
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

    if not GOOGLE_BOOKS_KEY:
        print(
            "Aviso: GOOGLE_BOOKS_API_KEY ausente. Google Books será tentado com "
            "retry curto e pulado por 15 min se continuar em 429."
        )

    print(f"Imagens encontradas: {len(imagens)} (modelo: {MODELO})")

    registros = []
    try:
        for imagem in imagens:
            registros.append(processar_imagem(imagem))
    except KeyboardInterrupt:
        print("\nInterrompido. Exportando o que já foi processado...")

    if not registros:
        return

    try:
        exportar_excel(registros)
    except Exception as erro:
        print(f"\nNão foi possível criar a planilha: {erro}")
        return

    confirmados = sum(1 for r in registros if r["validado"])
    parciais = sum(1 for r in registros if r["status"] == STATUS_PARCIAL)
    inconclusivos = sum(1 for r in registros if r["status"] == STATUS_INCONCLUSIVO)
    erros = sum(1 for r in registros if r["status"] == STATUS_ERRO)
    com_faixa = sum(1 for r in registros if r.get("faixa_etaria"))

    print("\n========== RESULTADO ==========")
    print(f"Imagens processadas: {len(registros)}")
    print(f"Validados: {confirmados}")
    print(f"Parciais (título bate, conferir autor): {parciais}")
    print(f"Inconclusivos (fonte fora do ar): {inconclusivos}")
    print(f"Erros de processamento: {erros}")
    print(f"Faixa etária preenchida: {com_faixa}")
    print(f"Planilha criada: {ARQUIVO_EXCEL}")


if __name__ == "__main__":
    main()
