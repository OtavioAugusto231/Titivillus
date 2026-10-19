# Titivillus — Aplicativo Desktop

Aplicativo desktop para catalogação de livros a partir de imagens de capas e fichas bibliográficas. O projeto utiliza Python para o processamento dos dados, FastAPI para a API local e Tauri para exibir a interface desenvolvida com HTML, CSS e JavaScript. A distribuição para Linux é feita em pacote `.deb` (também gera `.rpm` e AppImage), com o backend Python empacotado via PyInstaller.

## Tecnologias

- **Python:** lógica de processamento e validação bibliográfica.
- **FastAPI e Uvicorn:** API HTTP local.
- **PyInstaller:** empacotamento do backend Python (`--onedir`) para distribuição.
- **HTML, CSS e JavaScript:** interface gráfica.
- **Tauri 2 e Rust:** aplicação desktop e empacotamento (`.deb`, `.rpm`, AppImage).
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

O frontend se comunica com o backend por meio de uma API HTTP local. O Tauri fornece a janela desktop, enquanto o processamento continua sendo realizado pelo Python. Na versão empacotada, o backend vai dentro do aplicativo como recurso (`titivillus-api/`).

## Estrutura do projeto

```text
Titivillus_Tauri_FastAPI/
├── capas/                  # Imagens das capas
├── fichas/                 # Imagens das fichas bibliográficas
├── frontend/               # Interface HTML, CSS e JavaScript
├── dist/                   # Frontend estático gerado no build (não versionar)
├── pyinstaller-dist/       # Backend empacotado com PyInstaller (não versionar)
│   └── titivillus-api/
├── src-tauri/              # Configuração e código Rust do Tauri
│   ├── icons/              # Ícones gerados por `npx tauri icon`
│   ├── titivillus.desktop  # Template do .desktop usado no .deb
│   └── tauri.conf.json
├── scripts/                # Scripts auxiliares (inclui build.mjs)
├── tests/                  # Testes automatizados
├── titivillus/             # Backend e lógica Python
├── .venv/                  # Ambiente virtual Python
├── .env                    # Configurações e chaves locais
├── iniciar_titivillus.sh   # Script de inicialização (desenvolvimento)
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
- PyInstaller (instalado no `.venv`) para empacotar o backend.
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

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave da API do Google Gemini. |
| `TITIVILLUS_DATA_DIR` | Diretório de dados (capas, fichas e planilhas). Lido por `config.py`. |

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

A URL base utilizada pelo frontend em desenvolvimento deve ser:

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

No aplicativo empacotado a API local foi testada na porta `18765`. Ajuste o comando acima se estiver validando a versão instalada.

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

A compilação tem duas etapas: empacotar o backend Python e gerar o aplicativo com o Tauri.

### 1. Empacotar o backend

O Tauri inclui o backend como recurso, a partir de `pyinstaller-dist/titivillus-api/`. Essa pasta precisa existir **antes** do `tauri build`; sem ela o build falha por recurso inexistente.

```bash
.venv/bin/pyinstaller --onedir --name titivillus-api --distpath pyinstaller-dist <ponto_de_entrada>.py
```

Substitua `<ponto_de_entrada>` pelo script que inicia o Uvicorn do backend. O resultado deve ser `pyinstaller-dist/titivillus-api/`.

O mapeamento está em `src-tauri/tauri.conf.json`:

```json
"bundle": {
  "resources": {
    "../pyinstaller-dist/titivillus-api/": "titivillus-api/"
  }
}
```

### 2. Gerar o aplicativo

```bash
npx tauri build
```

O `beforeBuildCommand` (`npm run build`) copia o frontend estático para `dist/`. Os artefatos ficam em `src-tauri/target/release/bundle/`:

| Formato | Caminho |
|---|---|
| `.deb` | `src-tauri/target/release/bundle/deb/Titivillus_1.0.0_amd64.deb` |
| `.rpm` | `src-tauri/target/release/bundle/rpm/Titivillus-1.0.0-1.x86_64.rpm` |
| AppImage | `src-tauri/target/release/bundle/appimage/Titivillus_1.0.0_amd64.AppImage` |

### 3. Instalar o `.deb`

```bash
sudo dpkg -i src-tauri/target/release/bundle/deb/*.deb
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor
sudo update-desktop-database /usr/share/applications
```

Feche o aplicativo por completo antes de abri-lo novamente após uma reinstalação.

## Ícones

Os ícones ficam em `src-tauri/icons/` e são gerados a partir de um PNG quadrado (1024x1024):

```bash
npx tauri icon caminho/para/icone.png
```

O comando recria todos os tamanhos (`32x32.png`, `64x64.png`, `128x128.png`, `128x128@2x.png`, `icon.png`, `icon.ico`, `icon.icns` e variantes para Windows, Android e iOS). Rode-o novamente sempre que o ícone mudar ou a pasta for apagada.

O `tauri.conf.json` deve referenciar:

```json
"icon": [
  "icons/32x32.png",
  "icons/128x128.png",
  "icons/128x128@2x.png",
  "icons/icon.icns",
  "icons/icon.ico"
]
```

### Ícone na barra de tarefas (Linux/Wayland)

Em sessões Wayland, a barra de tarefas associa a janela ao `.desktop` pelo **app_id**, que no Tauri 2 é o `identifier` do `tauri.conf.json` (`br.titivillus.catalogo`). Se o `StartupWMClass` do `.desktop` não for igual a ele, o ícone aparece no menu de aplicativos, mas não na barra de tarefas.

O projeto resolve isso com um template de `.desktop` próprio, `src-tauri/titivillus.desktop`:

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name={{name}}
Exec={{exec}}
Icon={{icon}}
Terminal=false
Categories=Utility;
StartupWMClass=br.titivillus.catalogo
```

Referenciado em `tauri.conf.json`:

```json
"bundle": {
  "linux": {
    "deb": {
      "desktopTemplate": "titivillus.desktop"
    }
  }
}
```

Para conferir o resultado após instalar o `.deb`:

```bash
grep StartupWMClass /usr/share/applications/Titivillus.desktop
```

Deve imprimir `StartupWMClass=br.titivillus.catalogo`.

Em sessões X11 o `WM_CLASS` da janela é `titivillus-desktop`. Para conferir qual valor a janela usa em X11:

```bash
GDK_BACKEND=x11 titivillus-desktop &
xprop WM_CLASS
```

Em Wayland nativo o `xprop` não registra o clique e trava (Ctrl+C para sair). No GNOME, use Alt+F2, `lg`, aba **Windows**, e leia o `wmclass`.

## Solução de problemas

### Erro `EADDRINUSE` na porta `1420`

Esse erro indica que outro processo já está usando a porta do servidor de desenvolvimento.

Identifique os processos:

```bash
ss -ltnp | grep -E ':1420|:8000|:8765'
pgrep -af 'vite|dev-server.mjs|tauri dev|uvicorn'
```

Encerre apenas os processos antigos pertencentes ao Titivillus. Evite `killall node`, pois ele pode fechar outros aplicativos.

### `tauri build` falha por recurso inexistente

O caminho em `bundle.resources` aponta para uma pasta que não existe. Confirme que `pyinstaller-dist/titivillus-api/` foi gerada (etapa 1 de "Compilar o aplicativo") e que o caminho em `tauri.conf.json` corresponde.

### O ícone aparece no menu, mas não na barra de tarefas

Veja a seção "Ícone na barra de tarefas (Linux/Wayland)". Se o `StartupWMClass` instalado já for `br.titivillus.catalogo` e o problema persistir:

1. Feche o aplicativo por completo e abra pelo menu de aplicativos, não pelo terminal.
2. Faça logout e login para o shell reler o `.desktop`.
3. Se o tema de ícones (por exemplo, Papirus) não encontrar `titivillus-desktop`, use caminho absoluto no `Icon=` do template, por exemplo `Icon=/usr/share/icons/hicolor/128x128/apps/titivillus-desktop.png` (confirme o arquivo com `ls /usr/share/icons/hicolor/*/apps/ | grep -i titivillus`).

### A interface não encontra as imagens

Confira se o backend lista os arquivos:

```bash
curl -fsS 'http://127.0.0.1:8000/api/files?mode=capa'
curl -fsS 'http://127.0.0.1:8000/api/files?mode=ficha'
```

Confira também:

- Se `frontend/app.js` utiliza a URL base correta da API.
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

## Pendências

- Ícone na bandeja do sistema (system tray): requer a feature `tray-icon` do Tauri no `Cargo.toml` e a criação do ícone no `setup` do Rust. No Linux, os eventos de clique do tray não são emitidos; a interação deve ser feita pelo menu. No GNOME é necessária a extensão AppIndicator para a bandeja aparecer.

## Segurança e versionamento

Não versione arquivos de credenciais, o ambiente virtual, dependências instaladas localmente nem artefatos de build.

Confira se o `.gitignore` exclui, conforme aplicável:

```gitignore
.env
.venv/
node_modules/
__pycache__/
*.py[cod]
.pytest_cache/
dist/
pyinstaller-dist/
src-tauri/target/
*.bak
```

Revise também as planilhas e imagens antes de publicá-las no GitHub, pois elas podem conter dados pessoais ou informações que não devem ser compartilhadas.

## Desenvolvimento

- `frontend/`: interface gráfica.
- `src-tauri/`: integração desktop, ícones e template do `.desktop`.
- `titivillus/`: API e lógica Python.
- `tests/`: testes automatizados.

Ao modificar as portas da API, atualize tanto o frontend quanto o script de inicialização. Preserve a lógica Python existente ao alterar a interface, exceto quando uma mudança funcional exigir alterações no backend.
