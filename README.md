# Titivillus

Script em Python que transforma fotos de capas de livros em uma planilha. Você joga as fotos numa pasta, roda o script e recebe um `livros.xlsx` com título e autor de cada livro, já conferidos no Google Books.

Feito pra catalogar acervo sem digitar nada na mão.

## Como funciona

1. Lê todas as imagens da pasta `capas/`.
2. Manda cada capa para o Gemini (`gemini-3.1-flash-lite`), que extrai título e autor.
3. Busca o resultado no Google Books para confirmar que o livro existe e corrigir erros de leitura.
4. Grava tudo em `livros.xlsx`.

O passo 3 existe porque modelo de visão erra: capa com fonte decorativa, lombada cortada, foto torta. Sem a validação, a planilha sai com título inventado.

## Requisitos

- Python 3.10 ou superior
- Chave de API do Gemini
- Fotos das capas, de preferência uma por livro, com a capa inteira visível

## Instalação

```bash
git clone <url-do-repositorio> Titivillus
cd Titivillus
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Defina a chave como variável de ambiente. O script não aceita a chave no código:

```bash
export GEMINI_API_KEY="sua-chave-aqui"
```

Para não repetir isso toda vez, coloque a linha no `~/.bashrc` ou `~/.zshrc`.

## Uso

Coloque as fotos em `capas/` e rode:

```bash
python Titivillus.py
```

Ao terminar, o resultado fica em `livros.xlsx` na raiz do projeto.

## Estrutura

```
Titivillus/
├── Titivillus.py     # script principal
├── capas/            # fotos de entrada
├── livros.xlsx       # saída gerada
└── venv/             # ambiente virtual
```

## Limitações

- A leitura depende da qualidade da foto. Reflexo, desfoque e capa parcial derrubam a taxa de acerto.
- Livros raros, edições antigas ou fora de catálogo podem não aparecer no Google Books. Nesses casos confira a linha à mão.
- Cada capa vira uma chamada de API. Em lotes grandes, fique de olho na cota da sua chave.

## Nome

Titivillus é o demônio que, segundo a tradição medieval, plantava erros nos manuscritos copiados pelos escribas. Aqui ele trabalha ao contrário: o Google Books existe pra pegar os erros dele.
