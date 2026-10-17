# Titivillus — desktop Tauri + backend Python

Catalogador de livros a partir de fotografias. A lógica de negócio existente em `titivillus/` foi mantida; a interface nova usa Tauri, HTML, CSS e JavaScript e conversa com uma API local FastAPI. O frontend não duplica o processamento bibliográfico.

## Requisitos

- Python 3.10+ e dependências de `requirements.txt`.
- Node.js 20+ e npm.
- Rust/Cargo compatível com Tauri 2.
- No Linux, dependências Tauri/WebKitGTK; consulte a documentação oficial do Tauri para os pacotes da sua distribuição.
- Chave Gemini para processar imagens; Google Books é opcional.

## Preparar ambiente

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY; não versione esse arquivo.
npm install
```

## Executar em desenvolvimento

Na raiz do projeto:

```bash
npm run tauri dev
```

O Tauri inicia o backend Python em `127.0.0.1:8765` e encerra o processo filho ao fechar a aplicação. O frontend Vite usa `127.0.0.1:1420`. Para diagnosticar a API separadamente, execute `python -m titivillus.api` e abra `http://127.0.0.1:8765/docs`.

Se o Python não for encontrado, defina `TITIVILLUS_PYTHON` com o caminho absoluto do interpretador, por exemplo `TITIVILLUS_PYTHON="$PWD/.venv/bin/python" npm run tauri dev`.

## Compilar

```bash
npm run tauri build
```

Os artefatos Tauri são gerados em `src-tauri/target/release/bundle/`. **Limitação de distribuição:** a configuração atual usa o Python do sistema/ambiente virtual e executa o backend a partir da árvore do projeto. Para um instalador autossuficiente em máquinas sem Python, ainda é necessário empacotar o backend e suas dependências (por exemplo, PyInstaller como sidecar Tauri) e mover os dados editáveis para o diretório de dados do usuário. Isso não está concluído.

## Uso

- **Visão geral:** estado da API, contagem de imagens, progresso e resultados recentes.
- **Capas:** seleciona pasta, `.xlsx` de saída e política de renomeação. Renomear altera os arquivos originais; faça backup ou selecione “Não renomear”.
- **Fichas catalográficas:** seleciona pasta e planilha de saída.
- **Registro de atividade:** logs do pipeline e erros.
- **Configurações:** presença das chaves, caminhos e modelos. As chaves não são enviadas ao frontend.

Os caminhos padrão continuam definidos em `titivillus/config.py`. Os dados existentes não são apagados pela migração. O CLI continua disponível:

```bash
python -m titivillus.cli       # capas
python -m titivillus.cli ficha # fichas
```

## API local

- `GET /api/health` — estado do serviço.
- `GET /api/settings` — caminhos, modelos e presença das credenciais, sem revelar chaves.
- `GET /api/files?mode=capa|ficha` — imagens da pasta selecionada.
- `GET /api/state` — progresso, registros, logs e resumo.
- `POST /api/run` — inicia lote (`mode`, `input_dir`, `output_file`, `rename_policy`).
- `POST /api/stop` — solicita cancelamento após a imagem atual.
- `GET /api/records/fields?mode=capa|ficha` — campos dos registros.

A API escuta apenas em `127.0.0.1` por padrão. Não exponha essa porta na rede.

## Testes

```bash
python -m pytest -q
python -m py_compile titivillus/*.py
node --check frontend/app.js
npm run build
```

Testes de leitura real dependem de `GEMINI_API_KEY` e acesso aos serviços externos. Use imagens e diretórios temporários nos testes para evitar sobrescrever o catálogo real.
