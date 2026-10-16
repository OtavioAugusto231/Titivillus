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
