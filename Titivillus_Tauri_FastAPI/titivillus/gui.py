"""Interface gráfica (tkinter): python -m titivillus"""

import os
import pathlib
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import log as log_mod
from .config import (
    API_KEY,
    ARQUIVO_EXCEL,
    ARQUIVO_EXCEL_FICHAS,
    GOOGLE_BOOKS_KEY,
    MODELO,
    MODELO_FICHA,
    MODO_CAPA,
    MODO_FICHA,
    MODO_NUNCA,
    MODO_VALIDADOS,
    MODO_VALIDADOS_E_INCONCLUSIVOS,
    PASTA_CAPAS,
    PASTA_FICHAS,
    Settings,
)
from .modelos import (
    CAMPOS,
    CAMPOS_FICHA,
    STATUS_ERRO,
    STATUS_FICHA_LIDA,
    STATUS_FICHA_NAO_IDENTIFICADA,
    STATUS_INCONCLUSIVO,
    STATUS_PARCIAL,
    STATUS_SEM_MATCH,
    STATUS_VALIDADO,
)
from .leitor_capa import QuotaEsgotada
from .pipeline import executar, listar_imagens, resumo, resumo_fichas
from .tema import COR, aplicar_tema

MODOS_RENOMEAR = {
    "Só validados": MODO_VALIDADOS,
    "Validados + inconclusivos": MODO_VALIDADOS_E_INCONCLUSIVOS,
    "Não renomear": MODO_NUNCA,
}

CORES_STATUS = {
    STATUS_VALIDADO: COR["ok_bg"],
    STATUS_PARCIAL: COR["aviso_bg"],
    STATUS_INCONCLUSIVO: COR["laranja_bg"],
    STATUS_SEM_MATCH: COR["neutro_bg"],
    STATUS_ERRO: COR["erro_bg"],
    STATUS_FICHA_LIDA: COR["ok_bg"],
    STATUS_FICHA_NAO_IDENTIFICADA: COR["aviso_bg"],
}

# (chave do registro, título, largura, estica)
COLUNAS_POR_MODO = {
    MODO_CAPA: (
        ("arquivo", "Arquivo", 300, True),
        ("titulo", "Título", 220, False),
        ("volume", "Vol", 45, False),
        ("autor", "Autor", 160, False),
        ("faixa_etaria", "Faixa", 55, False),
        ("status", "Status", 190, False),
    ),
    MODO_FICHA: (
        ("arquivo", "Arquivo", 160, True),
        ("titulo", "Título", 220, False),
        ("autores", "Autores", 170, False),
        ("editora", "Editora", 120, False),
        ("ano_publicacao", "Ano", 50, False),
        ("isbn", "ISBN", 125, False),
        ("edicao", "Edição", 70, False),
        ("status", "Status", 165, False),
    ),
}

ROTULOS = {
    MODO_CAPA: {
        "pasta": "Pasta das capas",
        "excel": "Planilha de saída",
        "vazio": "Nenhum JPG, JPEG, PNG ou WEBP na pasta de capas.",
    },
    MODO_FICHA: {
        "pasta": "Pasta das fichas",
        "excel": "Planilha das fichas",
        "vazio": "Nenhum JPG, JPEG, PNG ou WEBP na pasta de fichas.",
    },
}


def abrir_no_sistema(caminho):
    caminho = str(caminho)
    if sys.platform.startswith("win"):
        os.startfile(caminho)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.master = master
        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.worker = None
        self.sair_ao_terminar = False
        self.modo_em_execucao = MODO_CAPA
        self.registros_por_item = {}

        self.var_modo = tk.StringVar(value=MODO_CAPA)
        self.var_pasta = {
            MODO_CAPA: tk.StringVar(value=str(PASTA_CAPAS)),
            MODO_FICHA: tk.StringVar(value=str(PASTA_FICHAS)),
        }
        self.var_excel = {
            MODO_CAPA: tk.StringVar(value=str(ARQUIVO_EXCEL)),
            MODO_FICHA: tk.StringVar(value=str(ARQUIVO_EXCEL_FICHAS)),
        }
        self.var_renomear = tk.StringVar(value="Validados + inconclusivos")
        self.var_rotulo_pasta = tk.StringVar()
        self.var_rotulo_excel = tk.StringVar()
        self.var_dica = tk.StringVar()
        self.var_progresso = tk.DoubleVar(value=0)
        self.var_texto_progresso = tk.StringVar(value="Parado")
        self.var_resumo = tk.StringVar(value="")

        self._montar()
        self._trocar_modo()
        self.pack(fill="both", expand=True)
        self.after(100, self._drenar_fila)

    # ---------------------------------------------------------- layout

    def _montar(self):
        self.columnconfigure(1, weight=1)

        seletor = ttk.Frame(self)
        seletor.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(seletor, text="Ler a partir de").pack(side="left", padx=(0, 10))
        self.rb_capa = ttk.Radiobutton(
            seletor,
            text="Capa (título, autor, volume, faixa etária)",
            value=MODO_CAPA,
            variable=self.var_modo,
            command=self._trocar_modo,
        )
        self.rb_capa.pack(side="left", padx=(0, 16))
        self.rb_ficha = ttk.Radiobutton(
            seletor,
            text="Ficha catalográfica (todas as informações do livro)",
            value=MODO_FICHA,
            variable=self.var_modo,
            command=self._trocar_modo,
        )
        self.rb_ficha.pack(side="left")

        ttk.Label(self, textvariable=self.var_rotulo_pasta).grid(
            row=1, column=0, sticky="w"
        )
        self.ent_pasta = ttk.Entry(self)
        self.ent_pasta.grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        ttk.Button(self, text="Escolher…", command=self._escolher_pasta).grid(
            row=1, column=2
        )

        ttk.Label(self, textvariable=self.var_rotulo_excel).grid(
            row=2, column=0, sticky="w"
        )
        self.ent_excel = ttk.Entry(self)
        self.ent_excel.grid(row=2, column=1, sticky="ew", padx=6, pady=2)
        ttk.Button(self, text="Salvar como…", command=self._escolher_excel).grid(
            row=2, column=2
        )

        ttk.Label(self, text="Renomear fotos").grid(row=3, column=0, sticky="w")
        quadro_renomear = ttk.Frame(self)
        quadro_renomear.grid(row=3, column=1, sticky="w", padx=6, pady=2)
        self.cb_renomear = ttk.Combobox(
            quadro_renomear,
            textvariable=self.var_renomear,
            values=list(MODOS_RENOMEAR),
            state="readonly",
            width=28,
        )
        self.cb_renomear.pack(side="left")
        ttk.Label(quadro_renomear, textvariable=self.var_dica, style="Dim.TLabel").pack(
            side="left", padx=10
        )

        self.lbl_chaves = ttk.Label(
            self, style="Erro.TLabel" if not API_KEY else "Dim.TLabel"
        )
        self.lbl_chaves.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 8))

        botoes = ttk.Frame(self)
        botoes.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.btn_iniciar = ttk.Button(
            botoes, text="Iniciar", command=self._iniciar, style="Accent.TButton"
        )
        self.btn_iniciar.pack(side="left")
        self.btn_parar = ttk.Button(
            botoes,
            text="Parar",
            command=self._parar,
            state="disabled",
            style="Destructive.TButton",
        )
        self.btn_parar.pack(side="left", padx=6)
        ttk.Button(botoes, text="Abrir planilha", command=self._abrir_planilha).pack(
            side="right"
        )
        ttk.Button(botoes, text="Abrir pasta", command=self._abrir_pasta).pack(
            side="right", padx=6
        )

        barra = ttk.Frame(self)
        barra.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        barra.columnconfigure(0, weight=1)
        ttk.Progressbar(barra, variable=self.var_progresso, maximum=100).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(barra, textvariable=self.var_texto_progresso, width=48).grid(
            row=0, column=1, padx=(8, 0), sticky="w"
        )

        painel = ttk.PanedWindow(self, orient="vertical")
        painel.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(7, weight=1)

        quadro_tabela = ttk.Frame(painel)
        self.tabela = ttk.Treeview(quadro_tabela, show="headings", height=10)
        for status, cor in CORES_STATUS.items():
            self.tabela.tag_configure(status, background=cor, foreground=COR["fg"])
        self.tabela.bind("<Double-1>", self._mostrar_detalhes)
        rolagem = ttk.Scrollbar(
            quadro_tabela, orient="vertical", command=self.tabela.yview
        )
        self.tabela.configure(yscrollcommand=rolagem.set)
        self.tabela.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        painel.add(quadro_tabela, weight=3)

        quadro_log = ttk.Frame(painel)
        self.caixa_log = tk.Text(
            quadro_log,
            height=9,
            state="disabled",
            font=("TkFixedFont", 9),
            bg=COR["view"],
            fg=COR["fg"],
            insertbackground=COR["fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COR["borda"],
            highlightcolor=COR["borda"],
            padx=8,
            pady=6,
            wrap="word",
        )
        rolagem_log = ttk.Scrollbar(
            quadro_log, orient="vertical", command=self.caixa_log.yview
        )
        self.caixa_log.configure(yscrollcommand=rolagem_log.set)
        self.caixa_log.pack(side="left", fill="both", expand=True)
        rolagem_log.pack(side="right", fill="y")
        painel.add(quadro_log, weight=2)

        ttk.Label(self, textvariable=self.var_resumo).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

    # ------------------------------------------------------------ modo

    def _modo(self):
        return self.var_modo.get()

    def _trocar_modo(self):
        modo = self._modo()
        self.var_rotulo_pasta.set(ROTULOS[modo]["pasta"])
        self.var_rotulo_excel.set(ROTULOS[modo]["excel"])
        self.ent_pasta.configure(textvariable=self.var_pasta[modo])
        self.ent_excel.configure(textvariable=self.var_excel[modo])

        if modo == MODO_FICHA:
            self.cb_renomear.configure(state="disabled")
            self.var_dica.set("(fotos das fichas não são renomeadas)")
            self.lbl_chaves.configure(
                text=f"Gemini: {'ok' if API_KEY else 'AUSENTE (defina GEMINI_API_KEY no .env)'}"
                f"   |   Modelo da ficha: {MODELO_FICHA}"
                f"   |   Duplo clique numa linha mostra todos os campos"
            )
        else:
            self.cb_renomear.configure(state="readonly")
            self.var_dica.set("")
            self.lbl_chaves.configure(
                text=f"Gemini: {'ok' if API_KEY else 'AUSENTE (defina GEMINI_API_KEY no .env)'}"
                f"   |   Google Books: "
                f"{'ok' if GOOGLE_BOOKS_KEY else 'sem chave (cota anônima, tende a dar 429)'}"
                f"   |   Modelo: {MODELO}"
            )

        self._aplicar_colunas(modo)
        self.tabela.delete(*self.tabela.get_children())
        self.registros_por_item.clear()
        self.var_resumo.set("")
        self.var_progresso.set(0)
        self.var_texto_progresso.set("Parado")

    def _aplicar_colunas(self, modo):
        colunas = COLUNAS_POR_MODO[modo]
        self.tabela.configure(columns=[c[0] for c in colunas])
        for chave, titulo, largura, estica in colunas:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(chave, width=largura, anchor="w", stretch=estica)

    # ------------------------------------------------------- escolhas

    def _escolher_pasta(self):
        var = self.var_pasta[self._modo()]
        pasta = filedialog.askdirectory(
            title=ROTULOS[self._modo()]["pasta"], initialdir=var.get() or "."
        )
        if pasta:
            var.set(pasta)

    def _escolher_excel(self):
        var = self.var_excel[self._modo()]
        atual = pathlib.Path(var.get() or "livros.xlsx")
        arquivo = filedialog.asksaveasfilename(
            title="Salvar planilha",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialdir=str(atual.parent),
            initialfile=atual.name,
        )
        if arquivo:
            var.set(arquivo)

    def _abrir_pasta(self):
        pasta = pathlib.Path(self.var_pasta[self._modo()].get())
        if pasta.is_dir():
            abrir_no_sistema(pasta)
        else:
            messagebox.showwarning("Pasta", "A pasta não existe.")

    def _abrir_planilha(self):
        arquivo = pathlib.Path(self.var_excel[self._modo()].get())
        if arquivo.is_file():
            abrir_no_sistema(arquivo)
        else:
            messagebox.showinfo("Planilha", "A planilha ainda não foi criada.")

    # ------------------------------------------------------- execução

    def _iniciar(self):
        if self.worker and self.worker.is_alive():
            return

        if not API_KEY:
            messagebox.showerror(
                "Chave ausente",
                "Defina GEMINI_API_KEY no arquivo .env (ao lado da pasta "
                "'titivillus') ou no ambiente e reabra o programa.",
            )
            return

        modo = self._modo()
        pasta = pathlib.Path(self.var_pasta[modo].get().strip()).expanduser()
        excel = pathlib.Path(self.var_excel[modo].get().strip()).expanduser()
        if not pasta.is_dir():
            messagebox.showerror("Pasta", f"A pasta não existe:\n{pasta}")
            return
        if excel.suffix.lower() != ".xlsx":
            messagebox.showerror("Planilha", "O arquivo de saída precisa ser .xlsx.")
            return
        total = len(listar_imagens(pasta))
        if total == 0:
            messagebox.showinfo("Sem imagens", ROTULOS[modo]["vazio"])
            return
        if excel.exists() and not messagebox.askyesno(
            "Sobrescrever", f"{excel.name} já existe e será sobrescrita. Continuar?"
        ):
            return

        settings = Settings(
            modo=modo,
            pasta_capas=pathlib.Path(self.var_pasta[MODO_CAPA].get().strip()).expanduser(),
            arquivo_excel=pathlib.Path(self.var_excel[MODO_CAPA].get().strip()).expanduser(),
            pasta_fichas=pathlib.Path(self.var_pasta[MODO_FICHA].get().strip()).expanduser(),
            arquivo_excel_fichas=pathlib.Path(
                self.var_excel[MODO_FICHA].get().strip()
            ).expanduser(),
            modo_renomear=MODOS_RENOMEAR[self.var_renomear.get()],
        )

        self.modo_em_execucao = modo
        self.tabela.delete(*self.tabela.get_children())
        self.registros_por_item.clear()
        self._limpar_log()
        self.var_progresso.set(0)
        self.var_texto_progresso.set(f"0/{total}")
        self.var_resumo.set("")
        self.cancelar.clear()
        self._alternar_controles(rodando=True)

        log_mod.set_handler(lambda msg: self.fila.put(("log", msg)))
        self.worker = threading.Thread(
            target=self._rodar, args=(settings,), daemon=True
        )
        self.worker.start()

    def _rodar(self, settings):
        try:
            registros = executar(
                settings,
                on_resultado=lambda r: self.fila.put(("resultado", r)),
                on_progresso=lambda f, t, a: self.fila.put(("progresso", f, t, a)),
                cancelar=self.cancelar,
            )
            self.fila.put(("fim", registros, None))
        except Exception as erro:  # a thread nunca pode morrer calada
            self.fila.put(("fim", [], erro))

    def _parar(self):
        self.cancelar.set()
        self.btn_parar.state(["disabled"])
        self.var_texto_progresso.set("Parando após a imagem atual…")

    def _alternar_controles(self, rodando):
        self.btn_iniciar.state(["disabled"] if rodando else ["!disabled"])
        self.btn_parar.state(["!disabled"] if rodando else ["disabled"])
        estado = ["disabled"] if rodando else ["!disabled"]
        self.rb_capa.state(estado)
        self.rb_ficha.state(estado)

    # ------------------------------------------------- fila -> interface

    def _drenar_fila(self):
        try:
            while True:
                self._tratar(self.fila.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._drenar_fila)

    def _tratar(self, msg):
        tipo = msg[0]
        if tipo == "log":
            self._escrever_log(msg[1])
        elif tipo == "resultado":
            self._adicionar_linha(msg[1])
        elif tipo == "progresso":
            _, feitas, total, atual = msg
            self.var_progresso.set(100 * feitas / total if total else 0)
            if atual:
                self.var_texto_progresso.set(f"{feitas}/{total}  {atual}")
            else:
                self.var_texto_progresso.set(f"{feitas}/{total}")
        elif tipo == "fim":
            self._finalizar(msg[1], msg[2])

    def _finalizar(self, registros, erro):
        log_mod.set_handler(None)
        self._alternar_controles(rodando=False)
        if isinstance(erro, QuotaEsgotada):
            self.var_texto_progresso.set("Interrompido: cota do Gemini esgotada")
            messagebox.showwarning("Cota do Gemini esgotada", str(erro))
        elif erro is not None:
            self.var_texto_progresso.set("Falhou")
            messagebox.showerror("Erro", str(erro))
        else:
            self.var_texto_progresso.set(
                "Cancelado" if self.cancelar.is_set() else "Concluído"
            )
            if registros:
                if self.modo_em_execucao == MODO_FICHA:
                    r = resumo_fichas(registros)
                    self.var_resumo.set(
                        f"Processadas: {r['processadas']}  |  Lidas: {r['lidas']}  |  "
                        f"Não identificadas: {r['nao_identificadas']}  |  "
                        f"Com ISBN: {r['com_isbn']}  |  Erros: {r['erros']}"
                    )
                else:
                    r = resumo(registros)
                    self.var_resumo.set(
                        f"Processadas: {r['processadas']}  |  Validadas: {r['validados']}  |  "
                        f"Parciais: {r['parciais']}  |  Inconclusivas: {r['inconclusivos']}  |  "
                        f"Erros: {r['erros']}  |  Com faixa etária: {r['com_faixa']}"
                    )
        if self.sair_ao_terminar:
            self.master.destroy()

    def _adicionar_linha(self, r):
        colunas = COLUNAS_POR_MODO[self.modo_em_execucao]
        item = self.tabela.insert(
            "",
            "end",
            values=tuple(r.get(c[0]) or "" for c in colunas),
            tags=(r.get("status") or "",),
        )
        self.registros_por_item[item] = r
        self.tabela.see(item)

    def _escrever_log(self, texto):
        self.caixa_log.configure(state="normal")
        self.caixa_log.insert("end", texto + "\n")
        self.caixa_log.see("end")
        self.caixa_log.configure(state="disabled")

    def _limpar_log(self):
        self.caixa_log.configure(state="normal")
        self.caixa_log.delete("1.0", "end")
        self.caixa_log.configure(state="disabled")

    # ------------------------------------------------ detalhes da linha

    def _mostrar_detalhes(self, _evento=None):
        selecionados = self.tabela.selection()
        if not selecionados:
            return
        registro = self.registros_por_item.get(selecionados[0])
        if not registro:
            return

        campos = CAMPOS_FICHA if self.modo_em_execucao == MODO_FICHA else CAMPOS
        janela = tk.Toplevel(self.master)
        janela.title(registro.get("titulo") or registro.get("arquivo") or "Detalhes")
        janela.configure(bg=COR["janela"])
        janela.geometry("720x560")

        quadro = ttk.Frame(janela, padding=10)
        quadro.pack(fill="both", expand=True)
        texto = tk.Text(
            quadro,
            bg=COR["view"],
            fg=COR["fg"],
            insertbackground=COR["fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COR["borda"],
            padx=10,
            pady=8,
            wrap="word",
        )
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=rolagem.set)
        texto.tag_configure("campo", foreground=COR["fg_dim"])
        texto.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

        for campo in campos:
            valor = registro.get(campo)
            texto.insert("end", f"{campo}\n", "campo")
            texto.insert("end", f"{valor if valor not in (None, '') else '—'}\n\n")
        texto.configure(state="disabled")
        janela.bind("<Escape>", lambda _e: janela.destroy())

    # ------------------------------------------------------- fechar

    def pedir_fechar(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno(
                "Em andamento",
                "Há um processamento em andamento. Parar após a imagem atual, "
                "exportar a planilha e sair?",
            ):
                self.sair_ao_terminar = True
                self._parar()
            return
        self.master.destroy()


def main():
    raiz = tk.Tk()
    raiz.title("Titivillus – catalogador de livros")
    raiz.geometry("1100x740")
    raiz.minsize(860, 540)
    aplicar_tema(raiz)
    app = App(raiz)
    raiz.protocol("WM_DELETE_WINDOW", app.pedir_fechar)
    raiz.mainloop()


if __name__ == "__main__":
    main()
