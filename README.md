# Titivillus — Aplicativo Desktop

Aplicativo desktop para catalogação de livros a partir de imagens de capas e fichas bibliográficas. O projeto utiliza Python para o processamento dos dados, FastAPI para a API local e Tauri para exibir a interface desenvolvida com HTML, CSS e JavaScript.

## Tecnologias

- **Python:** lógica de processamento e validação bibliográfica.
- **FastAPI e Uvicorn:** API HTTP local.
- **HTML, CSS e JavaScript:** interface gráfica.
- **Tauri e Rust:** aplicação desktop.
- **Pandas e OpenPyXL:** manipulação de planilhas Excel.
- **Google Gemini:** apoio à leitura de imagens.
- **Google Books e Open Library:** consulta e validação de informações bibliográficas.

## Arquitetura

```text
Titivillus Desktop
├── Tauri / Rust
├── Frontend
│   └── HTML, CSS e JavaScript
└── Backend Python
    └── FastAPI / Uvicorn
        ├── Leitura de imagens
        ├── Identificação de livros
        ├── Validação bibliográfica
        └── Exportação para Excel
```

O frontend se comunica com o backend por meio de uma API HTTP local. O Tauri fornece a janela desktop, enquanto o processamento continua sendo realizado pelo Python.

## Estrutura do projeto

```text
Titivillus_Tauri_FastAPI/
├── capas/                  # Imagens das capas
├── fichas/                 # Imagens das fichas bibliográficas
├── frontend/               # Interface HTML, CSS e JavaScript
├── src-tauri/              # Configuração e código Rust do Tauri
├── scripts/                # Scripts auxiliares
├── tests/                  # Testes automatizados
├── titivillus/             # Backend e lógica Python
├── .venv/                  # Ambiente virtual Python
├── .env                    # Configurações e chaves locais
├── iniciar_titivillus.sh   # Script de inicialização
├── package.json            # Scripts e dependências Node.js
├── requirements.txt        # Dependências Python
├── livros.xlsx             # Planilha de livros
└── fichas.xlsx             # Planilha de fichas
```

A estrutura pode variar conforme a configuração local. Preserve as pastas de imagens e as planilhas que contenham dados importantes.

## Requisitos

- Python 3 e suporte a ambientes virtuais (`venv`).
- Node.js e npm.
- Rust e Cargo.
- Dependências nativas necessárias para compilar o Tauri.
- Conexão com a internet para serviços bibliográficos e modelos externos.

No Linux, instale as ferramentas e bibliotecas de sistema exigidas pela versão do Tauri utilizada pelo projeto.

## Instalação

Entre na pasta do projeto:

```bash
cd ~/Documentos/titivillus_app/Titivillus_Tauri_FastAPI
```

Crie o ambiente virtual Python, caso ainda não exista:

```bash
python3 -m venv .venv
```

Instale as dependências Python:

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Instale as dependências do frontend:

```bash
npm install
```

### Configuração das credenciais

Configure no arquivo `.env` as variáveis esperadas pelo backend, incluindo `GEMINI_API_KEY` quando necessário.

Não publique o arquivo `.env` nem suas chaves de API no GitHub. Se existir um `.env.example`, utilize-o como referência para criar a configuração local.

Verifique se as pastas `capas/` e `fichas/` existem e se o usuário possui permissão de leitura. O usuário também precisa ter permissão para gravar nas planilhas de saída.

## Executar em modo de desenvolvimento

Na raiz do projeto, execute:

```bash
./iniciar_titivillus.sh
```

O script ativa o ambiente Python, verifica se a API local está respondendo na porta `8000`, inicia o backend quando necessário e executa a interface Tauri em modo de desenvolvimento.

Mantenha o terminal aberto durante a execução.

Para iniciar apenas o backend manualmente:

```bash
.venv/bin/python -m uvicorn titivillus.api:app --host 127.0.0.1 --port 8000
```

A URL base utilizada pelo frontend deve ser:

```text
http://127.0.0.1:8000/api
```

A porta `1420` é utilizada pelo servidor de desenvolvimento do frontend. Evite iniciar várias instâncias do aplicativo simultaneamente.

## API local

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/health` | Verifica se a API está funcionando. |
| `GET` | `/api/settings` | Retorna configurações e caminhos utilizados. |
| `GET` | `/api/files?mode=capa` | Lista arquivos de capas. |
| `GET` | `/api/files?mode=ficha` | Lista arquivos de fichas. |
| `GET` | `/api/state` | Consulta o estado do processamento. |
| `GET` | `/api/records/fields?mode=...` | Consulta os campos de registros do modo solicitado. |
| `POST` | `/api/run` | Inicia um processamento com os parâmetros enviados. |
| `POST` | `/api/stop` | Solicita a interrupção do processamento. |

### Verificar o backend

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/settings
curl -fsS 'http://127.0.0.1:8000/api/files?mode=capa'
curl -fsS 'http://127.0.0.1:8000/api/files?mode=ficha'
```

## Processamento dos arquivos

1. Coloque as imagens de capas em `capas/`.
2. Coloque as imagens de fichas bibliográficas em `fichas/`.
3. Confira a qualidade das imagens e a configuração dos diretórios.
4. Execute o processamento pela interface.
5. Revise os resultados e as planilhas geradas.

As planilhas normalmente utilizadas são `livros.xlsx` e `fichas.xlsx`. Os caminhos efetivamente configurados podem ser consultados no endpoint `/api/settings`.

Antes de processar novamente um lote, confira os resultados existentes e mantenha cópias de segurança dos dados importantes.

## Testes

Execute os testes disponíveis:

```bash
.venv/bin/python -m pytest
```

Caso o `pytest` não esteja instalado, instale-o no ambiente virtual se ele fizer parte das dependências de desenvolvimento do projeto.

## Compilar o aplicativo

Para gerar a versão de distribuição:

```bash
npm run tauri build
```

O Tauri gera os artefatos conforme a configuração em `src-tauri/tauri.conf.json` e as ferramentas disponíveis no sistema.

**Importante:** compilar o Tauri não garante automaticamente que o backend Python e todas as suas dependências serão empacotados junto. Antes de distribuir o aplicativo em outro computador, verifique a configuração de empacotamento do backend.

## Solução de problemas

### Erro `EADDRINUSE` na porta `1420`

Esse erro indica que outro processo já está usando a porta do servidor de desenvolvimento.

Identifique os processos:

```bash
ss -ltnp | grep -E ':1420|:8000|:8765'
pgrep -af 'vite|dev-server.mjs|tauri dev|uvicorn'
```

Encerre apenas os processos antigos pertencentes ao Titivillus. Evite `killall node`, pois ele pode fechar outros aplicativos.

### A interface não encontra as imagens

Confira se o backend lista os arquivos:

```bash
curl -fsS 'http://127.0.0.1:8000/api/files?mode=capa'
curl -fsS 'http://127.0.0.1:8000/api/files?mode=ficha'
```

Confira também:

- Se `frontend/app.js` utiliza `http://127.0.0.1:8000/api`.
- Se os caminhos retornados por `/api/settings` estão corretos.
- Se os diretórios existem e podem ser lidos pelo usuário.
- Se a interface consegue interpretar os dados retornados pela API.

Se a API encontra as imagens, mas elas não aparecem na janela, investigue a renderização no frontend.

### O backend não inicia

Verifique as dependências e a porta:

```bash
.venv/bin/python -m pip check
ss -ltnp | grep ':8000'
```

Se a porta já estiver ocupada, identifique o processo antes de encerrá-lo.

### Erros de credenciais ou serviços externos

Confira as variáveis de ambiente e a conexão com os serviços utilizados. Não compartilhe chaves de API em logs públicos, capturas de tela ou no repositório.

## Segurança e versionamento

Não versione arquivos de credenciais, o ambiente virtual ou dependências instaladas localmente.

Confira se o `.gitignore` exclui, conforme aplicável:

```gitignore
.env
.venv/
node_modules/
__pycache__/
*.py[cod]
.pytest_cache/
```

Revise também as planilhas e imagens antes de publicá-las no GitHub, pois elas podem conter dados pessoais ou informações que não devem ser compartilhadas.

## Desenvolvimento

- `frontend/`: interface gráfica.
- `src-tauri/`: integração desktop.
- `titivillus/`: API e lógica Python.
- `tests/`: testes automatizados.

Ao modificar as portas da API, atualize tanto o frontend quanto o script de inicialização. Preserve a lógica Python existente ao alterar a interface, exceto quando uma mudança funcional exigir alterações no backend.
