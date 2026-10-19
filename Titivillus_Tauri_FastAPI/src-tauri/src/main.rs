#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};

use tauri::{Manager, RunEvent};

struct Backend(Mutex<Option<Child>>);

fn start_backend(app: &tauri::App) -> Result<Child, String> {
    let project_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("Raiz do projeto não encontrada")?
        .to_path_buf();

    // Em desenvolvimento, os dados continuam na pasta do projeto.
    // No pacote instalado, ficam na pasta de dados do usuário.
    let data_dir = if cfg!(debug_assertions) {
        project_dir.clone()
    } else {
        app.path()
            .app_data_dir()
            .map_err(|e| format!("Não foi possível localizar a pasta de dados: {e}"))?
    };

    fs::create_dir_all(&data_dir)
        .map_err(|e| format!("Não foi possível criar a pasta de dados: {e}"))?;
    fs::create_dir_all(data_dir.join("capas"))
        .map_err(|e| format!("Não foi possível criar a pasta capas: {e}"))?;
    fs::create_dir_all(data_dir.join("fichas"))
        .map_err(|e| format!("Não foi possível criar a pasta fichas: {e}"))?;

    #[cfg(debug_assertions)]
    let mut command = {
        let python = std::env::var("TITIVILLUS_PYTHON")
            .unwrap_or_else(|_| "python3".to_string());

        let mut cmd = Command::new(python);
        cmd.args(["-m", "titivillus.api"])
            .current_dir(&project_dir)
            .env("PYTHONPATH", &project_dir);
        cmd
    };

    #[cfg(not(debug_assertions))]
    let mut command = {
        let executable = app
            .path()
            .resource_dir()
            .map_err(|e| format!("Não foi possível localizar os recursos: {e}"))?
            .join("titivillus-api")
            .join("titivillus-api");

        if !executable.is_file() {
            return Err(format!(
                "Executável do backend não encontrado em: {}",
                executable.display()
            ));
        }

        Command::new(executable)
    };

    command
        .current_dir(&data_dir)
        .env("TITIVILLUS_DATA_DIR", &data_dir)
        .env("TITIVILLUS_API_HOST", "127.0.0.1")
        .env("TITIVILLUS_API_PORT", "8765")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Não foi possível iniciar a API do Titivillus: {e}"))
}

fn stop_backend(backend: &Backend) {
    if let Ok(mut guard) = backend.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let child = start_backend(app).map_err(std::io::Error::other)?;
            app.manage(Backend(Mutex::new(Some(child))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Erro ao inicializar Titivillus");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(backend) = handle.try_state::<Backend>() {
                stop_backend(&backend);
            }
        }
    });
}
