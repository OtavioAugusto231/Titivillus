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
    GOOGLE_BOOKS_KEY,
    MODELO,
    MODO_NUNCA,
    MODO_VALIDADOS,
    MODO_VALIDADOS_E_INCONCLUSIVOS,
    PASTA_CAPAS,
    Settings,
)
from .modelos import (
    STATUS_ERRO,
    STATUS_INCONCLUSIVO,
    STATUS_PARCIAL,
    STATUS_SEM_MATCH,
    STATUS_VALIDADO,
)
from .pipeline import executar, listar_imagens, resumo
from .tema import COR, aplicar_tema

MODOS = {
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
}

COLUNAS = (
    ("arquivo", "Arquivo", 300),
    ("titulo", "Título", 220),
    ("volume", "Vol", 45),
    ("autor", "Autor", 160),
    ("faixa", "Faixa", 55),
    ("status", "Status", 190),
)


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

        self.var_pasta = tk.StringVar(value=str(PASTA_CAPAS))
        self.var_excel = tk.StringVar(value=str(ARQUIVO_EXCEL))
        self.var_modo = tk.StringVar(value="Validados + inconclusivos")
        self.var_progresso = tk.DoubleVar(value=0)
        self.var_texto_progresso = tk.StringVar(value="Parado")
        self.var_resumo = tk.StringVar(value="")

        self._montar()
        self.pack(fill="both", expand=True)
        self.after(100, self._drenar_fila)

    # ---------------------------------------------------------- layout

    def _montar(self):
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Pasta das capas").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_pasta).grid(
            row=0, column=1, sticky="ew", padx=6, pady=2
        )
        ttk.Button(self, text="Escolher…", command=self._escolher_pasta).grid(
            row=0, column=2
        )

        ttk.Label(self, text="Planilha de saída").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_excel).grid(
            row=1, column=1, sticky="ew", padx=6, pady=2
        )
        ttk.Button(self, text="Salvar como…", command=self._escolher_excel).grid(
            row=1, column=2
        )

        ttk.Label(self, text="Renomear fotos").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            self,
            textvariable=self.var_modo,
            values=list(MODOS),
            state="readonly",
            width=28,
        ).grid(row=2, column=1, sticky="w", padx=6, pady=2)

        chaves = (
            f"Gemini: {'ok' if API_KEY else 'AUSENTE (defina GEMINI_API_KEY no .env)'}"
            f"   |   Google Books: "
            f"{'ok' if GOOGLE_BOOKS_KEY else 'sem chave (cota anônima, tende a dar 429)'}"
            f"   |   Modelo: {MODELO}"
        )
        ttk.Label(
            self,
            text=chaves,
            style="Erro.TLabel" if not API_KEY else "Dim.TLabel",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 8))

        botoes = ttk.Frame(self)
        botoes.grid(row=4, column=0, columnspan=3, sticky="ew")
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
        self.btn_planilha = ttk.Button(
            botoes, text="Abrir planilha", command=self._abrir_planilha
        )
        self.btn_planilha.pack(side="right")
        ttk.Button(botoes, text="Abrir pasta", command=self._abrir_pasta).pack(
            side="right", padx=6
        )

        barra = ttk.Frame(self)
        barra.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        barra.columnconfigure(0, weight=1)
        ttk.Progressbar(barra, variable=self.var_progresso, maximum=100).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(barra, textvariable=self.var_texto_progresso, width=48).grid(
            row=0, column=1, padx=(8, 0), sticky="w"
        )

        painel = ttk.PanedWindow(self, orient="vertical")
        painel.grid(row=6, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(6, weight=1)

        quadro_tabela = ttk.Frame(painel)
        self.tabela = ttk.Treeview(
            quadro_tabela,
            columns=[c[0] for c in COLUNAS],
            show="headings",
            height=10,
        )
        for chave, titulo, largura in COLUNAS:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(
                chave, width=largura, anchor="w", stretch=(chave == "arquivo")
            )
        for status, cor in CORES_STATUS.items():
            self.tabela.tag_configure(status, background=cor, foreground=COR["fg"])
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
            row=7, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

    # ------------------------------------------------------- escolhas

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(
            title="Pasta com as capas", initialdir=self.var_pasta.get() or "."
        )
        if pasta:
            self.var_pasta.set(pasta)

    def _escolher_excel(self):
        atual = pathlib.Path(self.var_excel.get() or "livros.xlsx")
        arquivo = filedialog.asksaveasfilename(
            title="Salvar planilha",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialdir=str(atual.parent),
            initialfile=atual.name,
        )
        if arquivo:
            self.var_excel.set(arquivo)

    def _abrir_pasta(self):
        pasta = pathlib.Path(self.var_pasta.get())
        if pasta.is_dir():
            abrir_no_sistema(pasta)
        else:
            messagebox.showwarning("Pasta", "A pasta não existe.")

    def _abrir_planilha(self):
        arquivo = pathlib.Path(self.var_excel.get())
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

        pasta = pathlib.Path(self.var_pasta.get().strip()).expanduser()
        excel = pathlib.Path(self.var_excel.get().strip()).expanduser()
        if not pasta.is_dir():
            messagebox.showerror("Pasta", f"A pasta não existe:\n{pasta}")
            return
        if excel.suffix.lower() != ".xlsx":
            messagebox.showerror("Planilha", "O arquivo de saída precisa ser .xlsx.")
            return
        total = len(listar_imagens(pasta))
        if total == 0:
            messagebox.showinfo(
                "Sem imagens", "Nenhum JPG, JPEG, PNG ou WEBP na pasta escolhida."
            )
            return
        if excel.exists() and not messagebox.askyesno(
            "Sobrescrever", f"{excel.name} já existe e será sobrescrita. Continuar?"
        ):
            return

        settings = Settings(
            pasta_capas=pasta,
            arquivo_excel=excel,
            modo_renomear=MODOS[self.var_modo.get()],
        )

        self.tabela.delete(*self.tabela.get_children())
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
        if erro is not None:
            self.var_texto_progresso.set("Falhou")
            messagebox.showerror("Erro", str(erro))
        else:
            self.var_texto_progresso.set(
                "Cancelado" if self.cancelar.is_set() else "Concluído"
            )
            if registros:
                r = resumo(registros)
                self.var_resumo.set(
                    f"Processadas: {r['processadas']}  |  Validadas: {r['validados']}  |  "
                    f"Parciais: {r['parciais']}  |  Inconclusivas: {r['inconclusivos']}  |  "
                    f"Erros: {r['erros']}  |  Com faixa etária: {r['com_faixa']}"
                )
        if self.sair_ao_terminar:
            self.master.destroy()

    def _adicionar_linha(self, r):
        self.tabela.insert(
            "",
            "end",
            values=(
                r.get("arquivo") or "",
                r.get("titulo") or "",
                r.get("volume") or "",
                r.get("autor") or "",
                r.get("faixa_etaria") or "",
                r.get("status") or "",
            ),
            tags=(r.get("status") or "",),
        )
        filhos = self.tabela.get_children()
        if filhos:
            self.tabela.see(filhos[-1])

    def _escrever_log(self, texto):
        self.caixa_log.configure(state="normal")
        self.caixa_log.insert("end", texto + "\n")
        self.caixa_log.see("end")
        self.caixa_log.configure(state="disabled")

    def _limpar_log(self):
        self.caixa_log.configure(state="normal")
        self.caixa_log.delete("1.0", "end")
        self.caixa_log.configure(state="disabled")

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
    raiz.geometry("1100x720")
    raiz.minsize(820, 520)
    aplicar_tema(raiz)
    app = App(raiz)
    raiz.protocol("WM_DELETE_WINDOW", app.pedir_fechar)
    raiz.mainloop()


if __name__ == "__main__":
    main()
