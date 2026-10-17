"""Log desacoplado: o CLI imprime, a GUI redireciona para a fila da interface."""

_handler = print


def set_handler(funcao=None):
    global _handler
    _handler = funcao or print


def log(mensagem=""):
    _handler(mensagem)
