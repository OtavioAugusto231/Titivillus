"""Tema escuro no estilo GNOME (paleta do libadwaita) para ttk/tkinter."""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

COR = {
    "janela": "#242424",
    "superficie": "#303030",  # barras, cabeçalhos
    "campo": "#383838",  # entradas, botões
    "view": "#1e1e1e",  # tabela, log
    "borda": "#454545",
    "fg": "#ffffff",
    "fg_dim": "#9a9996",
    "fg_off": "#6f6f6f",
    "destaque": "#3584e4",
    "destaque_hover": "#4a93ec",
    "perigo": "#c01c28",
    "perigo_hover": "#d3323d",
    "erro": "#ff7b63",
    # linhas da tabela por status (fundos escuros)
    "ok_bg": "#1f3a2a",
    "aviso_bg": "#3b3720",
    "laranja_bg": "#47301d",
    "neutro_bg": "#2f2f2f",
    "erro_bg": "#4a2325",
}


def _escolher_fonte(raiz):
    familias = set(tkfont.families(raiz))
    for nome in ("Cantarell", "Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans"):
        if nome in familias:
            return nome
    return tkfont.nametofont("TkDefaultFont").actual("family")


def aplicar_tema(raiz):
    c = COR
    familia = _escolher_fonte(raiz)
    for nome, tamanho in (
        ("TkDefaultFont", 10),
        ("TkTextFont", 10),
        ("TkMenuFont", 10),
        ("TkHeadingFont", 10),
    ):
        tkfont.nametofont(nome).configure(family=familia, size=tamanho)

    raiz.configure(bg=c["janela"])
    # Widgets tk "puros" (listbox do combobox, diálogos internos)
    raiz.option_add("*TCombobox*Listbox.background", c["campo"])
    raiz.option_add("*TCombobox*Listbox.foreground", c["fg"])
    raiz.option_add("*TCombobox*Listbox.selectBackground", c["destaque"])
    raiz.option_add("*TCombobox*Listbox.selectForeground", c["fg"])
    raiz.option_add("*TCombobox*Listbox.borderWidth", 0)
    raiz.option_add("*Text.background", c["view"])
    raiz.option_add("*Text.foreground", c["fg"])

    s = ttk.Style(raiz)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass

    s.configure(".", background=c["janela"], foreground=c["fg"], borderwidth=0)
    s.configure("TFrame", background=c["janela"])
    s.configure("TLabel", background=c["janela"], foreground=c["fg"])
    s.configure("Dim.TLabel", foreground=c["fg_dim"])
    s.configure("Erro.TLabel", foreground=c["erro"])

    botao = dict(
        background=c["campo"],
        foreground=c["fg"],
        bordercolor=c["borda"],
        lightcolor=c["campo"],
        darkcolor=c["campo"],
        focuscolor=c["campo"],
        padding=(14, 6),
        relief="flat",
    )
    s.configure("TButton", **botao)
    s.map(
        "TButton",
        background=[("disabled", c["superficie"]), ("pressed", "#505050"), ("active", "#434343")],
        foreground=[("disabled", c["fg_off"])],
        lightcolor=[("active", "#434343")],
        darkcolor=[("active", "#434343")],
    )

    for nome, normal, hover in (
        ("Accent.TButton", c["destaque"], c["destaque_hover"]),
        ("Destructive.TButton", c["perigo"], c["perigo_hover"]),
    ):
        s.configure(
            nome,
            **{**botao, "background": normal, "lightcolor": normal, "darkcolor": normal,
               "bordercolor": normal, "focuscolor": normal},
        )
        s.map(
            nome,
            background=[("disabled", c["superficie"]), ("active", hover)],
            lightcolor=[("disabled", c["superficie"]), ("active", hover)],
            darkcolor=[("disabled", c["superficie"]), ("active", hover)],
            bordercolor=[("disabled", c["superficie"])],
            foreground=[("disabled", c["fg_off"])],
        )

    campo = dict(
        fieldbackground=c["campo"],
        foreground=c["fg"],
        insertcolor=c["fg"],
        bordercolor=c["borda"],
        lightcolor=c["campo"],
        darkcolor=c["campo"],
        padding=6,
    )
    s.configure("TEntry", **campo)
    s.map(
        "TEntry",
        bordercolor=[("focus", c["destaque"])],
        lightcolor=[("focus", c["destaque"])],
        darkcolor=[("focus", c["destaque"])],
    )
    s.configure("TCombobox", **campo, background=c["campo"], arrowcolor=c["fg"])
    s.map(
        "TCombobox",
        fieldbackground=[("readonly", c["campo"])],
        foreground=[("readonly", c["fg"])],
        selectbackground=[("readonly", c["campo"])],
        selectforeground=[("readonly", c["fg"])],
        bordercolor=[("focus", c["destaque"])],
        background=[("active", "#434343")],
    )

    s.configure(
        "Treeview",
        background=c["view"],
        fieldbackground=c["view"],
        foreground=c["fg"],
        bordercolor=c["borda"],
        lightcolor=c["borda"],
        darkcolor=c["borda"],
        rowheight=26,
    )
    s.map(
        "Treeview",
        background=[("selected", c["destaque"])],
        foreground=[("selected", c["fg"])],
    )
    s.configure(
        "Treeview.Heading",
        background=c["superficie"],
        foreground=c["fg"],
        bordercolor=c["borda"],
        lightcolor=c["superficie"],
        darkcolor=c["superficie"],
        relief="flat",
        padding=(8, 6),
    )
    s.map("Treeview.Heading", background=[("active", "#3a3a3a")])

    s.configure(
        "Horizontal.TProgressbar",
        troughcolor=c["campo"],
        background=c["destaque"],
        bordercolor=c["campo"],
        lightcolor=c["destaque"],
        darkcolor=c["destaque"],
        thickness=8,
    )

    for orient in ("Vertical", "Horizontal"):
        s.configure(
            f"{orient}.TScrollbar",
            background="#505050",
            troughcolor=c["view"],
            bordercolor=c["view"],
            lightcolor="#505050",
            darkcolor="#505050",
            arrowcolor=c["fg_dim"],
            gripcount=0,
        )
        s.map(
            f"{orient}.TScrollbar",
            background=[("active", "#6a6a6a")],
            lightcolor=[("active", "#6a6a6a")],
            darkcolor=[("active", "#6a6a6a")],
        )

    s.configure(
        "TRadiobutton",
        background=c["janela"],
        foreground=c["fg"],
        indicatorcolor=c["campo"],
        indicatorbackground=c["campo"],
        focuscolor=c["janela"],
        padding=(2, 4),
    )
    s.map(
        "TRadiobutton",
        background=[("active", c["janela"]), ("disabled", c["janela"])],
        foreground=[("disabled", c["fg_off"])],
        indicatorcolor=[("selected", c["destaque"]), ("active", "#4a4a4a")],
    )

    s.configure("TPanedwindow", background=c["janela"])
    s.configure("Sash", sashthickness=6, background=c["janela"])
    return familia
