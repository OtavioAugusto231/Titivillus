"""API local do Titivillus. A lógica de negócio continua em pipeline.py."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import log as log_mod
from .config import (
    API_KEY, ARQUIVO_EXCEL, ARQUIVO_EXCEL_FICHAS, EXTENSOES, GOOGLE_BOOKS_KEY,
    MODELO, MODELO_FICHA, MODO_CAPA, MODO_FICHA, MODO_NUNCA,
    MODO_VALIDADOS, MODO_VALIDADOS_E_INCONCLUSIVOS, PASTA_CAPAS, PASTA_FICHAS,
    Settings,
)
from .modelos import CAMPOS, CAMPOS_FICHA

app = FastAPI(title="Titivillus Local API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_lock = threading.RLock()
_cancel = threading.Event()
_worker: threading.Thread | None = None
_state = {
    "running": False, "mode": MODO_CAPA, "done": 0, "total": 0,
    "current": None, "records": [], "logs": [], "error": None,
    "summary": {}, "started_at": None, "finished_at": None,
}
_LOG_LIMIT = 400

def _listar_imagens(pasta: Path):
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSOES)

def _append_log(message: str):
    with _lock:
        _state["logs"].append({"time": time.strftime("%H:%M:%S"), "message": str(message)})
        if len(_state["logs"]) > _LOG_LIMIT:
            del _state["logs"][:-_LOG_LIMIT]

log_mod.set_handler(_append_log)

class RunRequest(BaseModel):
    mode: Literal["capa", "ficha"] = "capa"
    input_dir: str | None = None
    output_file: str | None = None
    rename_policy: Literal["validados", "validados_inconclusivos", "nunca"] = "validados_inconclusivos"

class SettingsResponse(BaseModel):
    mode: str
    covers_dir: str
    cards_dir: str
    books_xlsx: str
    cards_xlsx: str
    rename_policy: str
    gemini_configured: bool
    google_books_configured: bool
    model_cover: str
    model_card: str

@app.get("/api/health")
def health():
    return {"ok": True, "app": "Titivillus", "version": app.version}

@app.get("/api/settings", response_model=SettingsResponse)
def get_settings():
    return SettingsResponse(
        mode=MODO_CAPA, covers_dir=str(PASTA_CAPAS), cards_dir=str(PASTA_FICHAS),
        books_xlsx=str(ARQUIVO_EXCEL), cards_xlsx=str(ARQUIVO_EXCEL_FICHAS),
        rename_policy=MODO_VALIDADOS_E_INCONCLUSIVOS,
        gemini_configured=bool(API_KEY), google_books_configured=bool(GOOGLE_BOOKS_KEY),
        model_cover=MODELO, model_card=MODELO_FICHA,
    )

@app.get("/api/files")
def files(mode: Literal["capa", "ficha"] = MODO_CAPA):
    directory = PASTA_FICHAS if mode == MODO_FICHA else PASTA_CAPAS
    output = ARQUIVO_EXCEL_FICHAS if mode == MODO_FICHA else ARQUIVO_EXCEL
    directory.mkdir(parents=True, exist_ok=True)
    images = [{"name": p.name, "path": str(p), "size": p.stat().st_size} for p in _listar_imagens(directory)]
    return {"mode": mode, "directory": str(directory), "output": str(output), "count": len(images), "files": images}

@app.get("/api/state")
def state():
    with _lock:
        return {**_state, "records": list(_state["records"]), "logs": list(_state["logs"])}

def _run_job(request: RunRequest):
    global _worker
    mode = request.mode
    defaults_dir = PASTA_FICHAS if mode == MODO_FICHA else PASTA_CAPAS
    defaults_out = ARQUIVO_EXCEL_FICHAS if mode == MODO_FICHA else ARQUIVO_EXCEL
    input_dir = Path(request.input_dir).expanduser().resolve() if request.input_dir else defaults_dir
    output_file = Path(request.output_file).expanduser().resolve() if request.output_file else defaults_out
    policy = {
        "validados": MODO_VALIDADOS,
        "validados_inconclusivos": MODO_VALIDADOS_E_INCONCLUSIVOS,
        "nunca": MODO_NUNCA,
    }[request.rename_policy]
    settings = Settings(modo=mode, pasta_capas=input_dir if mode == MODO_CAPA else PASTA_CAPAS,
        arquivo_excel=output_file if mode == MODO_CAPA else ARQUIVO_EXCEL,
        pasta_fichas=input_dir if mode == MODO_FICHA else PASTA_FICHAS,
        arquivo_excel_fichas=output_file if mode == MODO_FICHA else ARQUIVO_EXCEL_FICHAS,
        modo_renomear=policy)
    try:
        from .leitor_capa import QuotaEsgotada
        from .pipeline import executar, resumo, resumo_fichas
        def on_result(record):
            with _lock:
                _state["records"].append(record)
        def on_progress(done, total, current):
            with _lock:
                _state["done"] = done
                _state["total"] = total
                _state["current"] = current
        records = executar(settings, on_resultado=on_result, on_progresso=on_progress, cancelar=_cancel)
        summary = resumo_fichas(records) if mode == MODO_FICHA else resumo(records)
        with _lock:
            _state["summary"] = summary
    except Exception as exc:
        _append_log(f"Execução encerrada com aviso/erro: {exc}")
        with _lock:
            _state["error"] = str(exc)
    finally:
        with _lock:
            _state["running"] = False
            _state["current"] = None
            _state["finished_at"] = time.time()
        _append_log("Execução finalizada.")

@app.post("/api/run")
def run(request: RunRequest):
    global _worker
    with _lock:
        if _state["running"]:
            raise HTTPException(status_code=409, detail="Já existe um processamento em andamento.")
        if not API_KEY:
            raise HTTPException(status_code=400, detail="GEMINI_API_KEY não está configurada no arquivo .env ou no ambiente.")
        directory = Path(request.input_dir).expanduser().resolve() if request.input_dir else (PASTA_FICHAS if request.mode == MODO_FICHA else PASTA_CAPAS)
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(status_code=400, detail=f"A pasta de entrada não existe: {directory}")
        _cancel.clear()
        _state.update(running=True, mode=request.mode, done=0, total=0, current=None,
            records=[], logs=[], error=None, summary={}, started_at=time.time(), finished_at=None)
        _append_log(f"Iniciando processamento de {'fichas' if request.mode == MODO_FICHA else 'capas'} em {directory}")
        _worker = threading.Thread(target=_run_job, args=(request,), daemon=True, name="titivillus-worker")
        _worker.start()
    return {"accepted": True, "message": "Processamento iniciado."}

@app.post("/api/stop")
def stop():
    with _lock:
        if not _state["running"]:
            return {"accepted": False, "message": "Não há processamento em andamento."}
        _cancel.set()
        _append_log("Cancelamento solicitado; a imagem atual será concluída.")
    return {"accepted": True, "message": "Cancelamento solicitado."}

@app.get("/api/records/fields")
def record_fields(mode: Literal["capa", "ficha"] = MODO_CAPA):
    return {"fields": CAMPOS_FICHA if mode == MODO_FICHA else CAMPOS}

def main():
    import uvicorn
    host = os.environ.get("TITIVILLUS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("TITIVILLUS_API_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)

if __name__ == "__main__":
    main()
