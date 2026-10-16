# Titivillus

Catalogador de livros a partir de fotos. Você joga as imagens numa pasta, abre a interface (ou roda o CLI) e recebe uma planilha `.xlsx`.

Dois modos de leitura:

- **Capa**: extrai título, volume, autor e faixa etária da capa ou lombada, confere o resultado no Google Books (com Open Library de reserva) e, opcionalmente, renomeia a foto.
- **Ficha catalográfica**: lê a página de créditos e extrai todos os dados da edição (editora, ano, ISBN, CDD/CDU, assuntos, etc.).

Feito pra catalogar acervo sem digitar nada na mão.

## Como funciona

### Modo capa

1. Lê as imagens da pasta `capas/` (JPG, JPEG, PNG e WEBP, só o nível raiz da pasta, sem subpastas).
2. Manda cada imagem ao Gemini, que devolve `titulo`, `volume` e `autor`. Se o autor vier vazio, faz uma segunda leitura focada só nele.
3. Valida o resultado em fontes externas, na ordem:
   1. **Google Books**: consulta estrita (`intitle:"..." inauthor:"..."`) e, se não casar, uma consulta solta.
   2. **Open Library**: usada se o Google Books não casar ou estiver fora do ar.
4. Pede ao Gemini a **faixa etária** (chamada só de texto, usando o título canônico quando o livro foi validado).
5. Renomeia a foto conforme o modo escolhido (ver [Renomeação](#renomeação-das-fotos)).
6. Grava tudo em `livros.xlsx`.

O passo 3 existe porque modelo de visão erra: fonte decorativa, lombada cortada, foto torta. Sem validação a planilha sai com título inventado.

**Critérios de match** (comparação fuzzy, sem acento e sem diferença de caixa; ajustáveis em `titivillus/config.py`):

| Situação | Limiar | Resultado |
|---|---|---|
| Título e autor lidos | título ≥ 0,70 e autor ≥ 0,65 | `validado` |
| Só título lido | título ≥ 0,85 | `validado` |
| Título quase idêntico, autor divergente ou ausente na fonte | título ≥ 0,92 | `parcial`: apenas sugestão, nunca valida nem renomeia |

### Modo ficha

Lê a página de créditos com o Gemini e grava todos os campos legíveis. Não há validação externa, faixa etária nem renomeação. Listas (autores, assuntos) viram `a; b; c` na célula. Campo ausente ou ilegível fica vazio; o modelo é instruído a não completar nada.

Como é texto miúdo e denso, vale usar um modelo mais forte só para este modo (`GEMINI_MODEL_FICHA`).

## Requisitos

- Python 3.10 ou superior
- tkinter (para a interface gráfica). No Debian/Ubuntu: `sudo apt install python3-tk`
- Chave de API do Gemini
- Chave da Google Books API (opcional, mas recomendada; ver [Limitações](#limitações))
- Fotos nítidas, uma por livro, com a capa (ou a página de créditos) inteira visível

## Instalação

```bash
git clone <url-do-repositorio> Titivillus
cd Titivillus
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Dependências: `google-genai`, `pandas`, `openpyxl`, `requests`, `pydantic`.

## Configuração

Copie o exemplo e preencha:

```bash
cp .env.example .env
```

O `.env` fica na raiz do projeto (ao lado da pasta `titivillus/`). Variáveis já exportadas no shell têm prioridade sobre o `.env`. A chave nunca vai no código. **Não versione o `.env`.**

| Variável | Obrigatória | Padrão | Função |
|---|---|---|---|
| `GEMINI_API_KEY` | sim | — | Chave da API do Gemini |
| `GOOGLE_BOOKS_API_KEY` | não | — | Chave do Google Books. Sem ela a cota anônima estoura (429) quase sempre |
| `GEMINI_MODEL` | não | `gemini-3.1-flash-lite` | Modelo usado para ler capas |
| `GEMINI_MODEL_FICHA` | não | o mesmo de `GEMINI_MODEL` | Modelo usado só nas fichas |
| `GEMINI_MODEL_FAIXA` | não | o mesmo de `GEMINI_MODEL` | Modelo usado para a faixa etária |
| `GEMINI_MODEL_FAIXA_FALLBACK` | não | `gemini-2.5-flash` | Modelo tentado se o da faixa etária falhar |

A cota diária do Gemini é **por modelo**. Se estourar, trocar `GEMINI_MODEL` resolve sem trocar de chave.

Para criar a chave do Google Books: console.cloud.google.com, ative a "Books API" no projeto e gere uma chave de API.

## Uso

### Interface gráfica

```bash
python -m titivillus
```

- Escolha o modo (capa ou ficha), a pasta de entrada e o arquivo `.xlsx` de saída.
- Escolha a política de renomeação (só no modo capa).
- **Iniciar** processa a pasta; **Parar** interrompe após a imagem atual e exporta o que já foi lido.
- A tabela mostra cada imagem conforme é processada, colorida por status. Duplo clique numa linha abre todos os campos do registro.
- **Abrir pasta** e **Abrir planilha** chamam o aplicativo padrão do sistema.
- Se a planilha de saída já existir, a interface pede confirmação antes de sobrescrever.

### Linha de comando

Rode a partir da raiz do projeto:

```bash
python -m titivillus.cli          # capas (padrão)
python -m titivillus.cli ficha    # fichas catalográficas
```

O CLI usa sempre as pastas e planilhas padrão e a renomeação padrão (`validados + inconclusivos`). Não há flag para desligar a renomeação nem confirmação antes de sobrescrever a planilha; para isso, use a interface gráfica.

### Pastas e arquivos padrão

| Modo | Entrada | Saída |
|---|---|---|
| Capa | `capas/` | `livros.xlsx` |
| Ficha | `fichas/` | `fichas.xlsx` |

As pastas são criadas automaticamente se não existirem. A planilha só é gravada se pelo menos uma imagem foi processada. Se ela estiver aberta no Excel/LibreOffice, a gravação falha com mensagem clara: feche e rode de novo.

## Planilhas geradas

Ordenação: título (sem acento e sem diferença de caixa), depois número do volume. Linhas sem título vão para o fim.

### `livros.xlsx`

| Coluna | Conteúdo |
|---|---|
| `titulo`, `volume`, `autor` | O que o Gemini leu da capa |
| `faixa_etaria` | `Livre`, `7+`, `10+`, `12+`, `14+`, `16+` ou `18+`; vazio se o modelo não souber |
| `titulo_google_books`, `autor_google_books` | Título e autor canônicos da fonte que validou (ou sugeriu). **Atenção:** o nome da coluna é histórico; quando a fonte é a Open Library, os dados dela vão aqui também |
| `validado` | `True` só no status `validado` |
| `status` | Ver tabela abaixo |
| `fonte_validacao` | `Google Books`, `Open Library` ou `<fonte> (só título)` nos parciais |
| `arquivo` | Nome final da foto (já renomeada, se for o caso) |
| `erro` | Falha de processamento ou fonte que não respondeu |

| Status | Significado | Ação |
|---|---|---|
| `validado` | Título e autor batem com uma fonte | Nenhuma |
| `parcial (conferir autor)` | Título quase idêntico, autor divergente | Conferir o autor à mão |
| `sem correspondência` | As fontes responderam e nada bateu | Conferir a linha (livro raro, leitura errada ou fora de catálogo) |
| `inconclusivo (fonte indisponível)` | Nenhum match, nenhuma sugestão parcial e pelo menos uma fonte falhou | Rodar de novo depois ou conferir à mão |
| `erro` | Falha ao processar a imagem | Ver coluna `erro` |

### `fichas.xlsx`

`arquivo`, `titulo`, `subtitulo`, `titulo_original`, `autores`, `tradutor`, `ilustrador`, `organizador`, `editora`, `cidade`, `ano_publicacao`, `edicao`, `isbn`, `paginas`, `serie_colecao`, `volume`, `idioma`, `cdd`, `cdu`, `assuntos`, `bibliotecario_crb`, `ficha_catalografica` (transcrição literal do bloco), `outras_informacoes`, `status`, `erro`.

Status: `lida` (achou título ou ISBN), `ficha não identificada` (nenhum dos dois) e `erro`.

## Renomeação das fotos

Só no modo capa. O padrão é `Título Vol N - autor em minúsculas.ext`. Caracteres proibidos em nome de arquivo são removidos, cada parte é cortada em 80 caracteres e colisões ganham sufixo ` (2)`, ` (3)`...

| Política | Renomeia quando o status é |
|---|---|
| Só validados | `validado` |
| Validados + inconclusivos (**padrão**) | `validado` ou `inconclusivo` |
| Não renomear | nunca |

Pontos que importam:

- A renomeação **altera os arquivos originais** na pasta de entrada. Faça backup do lote ou escolha "Não renomear" na primeira execução.
- O nome usa o título e o autor **como o Gemini leu**, não os da fonte. Em `inconclusivo` isso significa renomear com uma leitura que ninguém conferiu.
- `parcial` e `sem correspondência` nunca renomeiam.

## Estrutura

```
Titivillus/
├── titivillus/
│   ├── __main__.py       # abre a interface (python -m titivillus)
│   ├── cli.py            # linha de comando
│   ├── gui.py            # interface tkinter
│   ├── tema.py           # tema escuro (paleta libadwaita)
│   ├── config.py         # .env, modelos, limiares, constantes
│   ├── pipeline.py       # orquestra o lote e exporta a planilha
│   ├── leitor_capa.py    # Gemini: capa, autor, faixa etária, retry e cota
│   ├── leitor_ficha.py   # Gemini: ficha catalográfica
│   ├── prompts.py        # prompts enviados ao Gemini
│   ├── modelos.py        # schemas, campos e status
│   ├── validacao.py      # Google Books → Open Library → sugestão parcial
│   ├── fontes.py         # clientes das APIs, throttle, backoff, cooldown
│   ├── matching.py       # comparação fuzzy entre leitura e candidatos
│   ├── planilha.py       # ordenação e exportação .xlsx
│   ├── arquivos.py       # renomeação das fotos
│   ├── textos.py         # normalização e similaridade
│   └── log.py            # log desacoplado (CLI imprime, GUI usa fila)
├── capas/                # entrada: fotos de capas
├── fichas/               # entrada: fotos de fichas catalográficas
├── livros.xlsx           # saída do modo capa
├── fichas.xlsx           # saída do modo ficha
├── .env                  # chaves (não versionar)
├── .env.example
├── requirements.txt
└── venv/
```

## Limitações

- A leitura depende da qualidade da foto. Reflexo, desfoque e capa parcial derrubam a taxa de acerto.
- **Chamadas de API por imagem (capa):** 1 chamada de visão, mais 1 se o autor vier vazio, mais 1 de texto para a faixa etária (e outra se cair no modelo de fallback). Fora o Gemini, até 2 consultas ao Google Books e até 2 à Open Library. Em lote grande, acompanhe a cota.
- **Cota diária do Gemini esgotada** (erro 429 "PerDay"): o processamento para, a planilha é gravada com o que já foi lido e a mensagem informa quantas imagens foram feitas. Erros 429/5xx transitórios têm 3 novas tentativas (5 s, 15 s, 30 s).
- **Google Books sem chave:** 1 nova tentativa e, se continuar em 429, a fonte é pulada por 15 min (as imagens seguintes caem direto na Open Library). Com chave: 3 novas tentativas (5 s, 15 s, 40 s, respeitando `Retry-After`) e cooldown de 2 min. Intervalo mínimo de 1,2 s entre requisições.
- Livros raros, edições antigas ou fora de catálogo podem não aparecer em nenhuma das fontes. Confira à mão as linhas `sem correspondência`, `parcial` e `inconclusivo`.
- A faixa etária é uma estimativa do modelo a partir de título e autor, não uma classificação oficial. Quando o modelo não conhece a obra, o campo fica vazio.
- Fichas não passam por nenhuma validação externa: ISBN, ano e CDD vêm só da leitura da imagem. Confira os dígitos.
- O processamento é sequencial, uma imagem por vez.
- As imagens são enviadas à API do Gemini; título e autor lidos vão para Google Books e Open Library. Não use com material que não possa sair da máquina.

## Nome

Titivillus é o demônio que, segundo a tradição medieval, plantava erros nos manuscritos copiados pelos escribas. Aqui ele trabalha ao contrário: Google Books e Open Library existem pra pegar os erros dele.
