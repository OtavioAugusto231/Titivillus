"""Renomeação das fotos: 'Título [Vol N] - autor em minúsculas.ext'."""

from .log import log
from .textos import limpar_nome


def renomear_foto(path, titulo, autor, volume=None):
    titulo = limpar_nome(titulo) or "Título desconhecido"
    autor = limpar_nome(autor).lower() or "autor desconhecido"
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
    log(f"  Foto renomeada: {destino.name}")
    return destino.name
