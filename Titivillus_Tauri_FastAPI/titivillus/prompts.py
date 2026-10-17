"""Prompts enviados ao Gemini."""

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

PROMPT_FICHA = """
Esta imagem é a página de créditos de um livro: normalmente traz a ficha
catalográfica (CIP - Catalogação na Publicação) e os dados da edição.
Extraia todas as informações legíveis.

Campos:
- titulo: título principal, sem subtítulo e sem número de volume;
- subtitulo;
- titulo_original: título no idioma original (comum em traduções:
  "Título original: ...");
- autores: lista, um item por autor, como impresso (a ficha costuma trazer
  "Sobrenome, Nome");
- tradutor, ilustrador, organizador: nome(s), separados por vírgula;
- editora;
- cidade: cidade da publicação;
- ano_publicacao: só o ano da edição/publicação; se houver copyright de outro
  ano, registre-o em outras_informacoes;
- edicao: ex.: "2. ed.", "1ª edição";
- isbn: como impresso, com hífens; se houver mais de um (impresso, e-book),
  separe por "; ";
- paginas: número de páginas (ex.: "320 p." -> "320");
- serie_colecao e volume (número na série);
- idioma;
- cdd, cdu: apenas o código de classificação;
- assuntos: lista, um item por assunto catalogado, sem a numeração "1.", "2.";
- bibliotecario_crb: nome e registro CRB, se houver;
- ficha_catalografica: transcrição literal do bloco da ficha (do cabeçalho
  "Dados Internacionais de Catalogação..." até o CDD/CDU/CRB), preservando as
  quebras de linha;
- outras_informacoes: demais textos legíveis da página (copyright, créditos de
  revisão/capa/diagramação, endereço da editora, gráfica, etc.), em texto
  corrido.

Regras:
- Não invente nem complete informação. Campo ausente ou ilegível: null.
- Transcreva letra por letra e dígito por dígito, principalmente ISBN, ano,
  CDD e CRB.
- Não confunda título original com o título da edição, nem editora com gráfica.
- Responda somente em JSON válido, com exatamente estes campos.
"""
