#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{process::{Child, Command, Stdio}, sync::Mutex};
use tauri::{Manager, RunEvent};
struct Backend(Mutex<Option<Child>>);
fn start_backend() -> Result<Child, String> {
 let root=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().ok_or("Raiz do projeto não encontrada")?.to_path_buf();
 let python=std::env::var("TITIVILLUS_PYTHON").unwrap_or_else(|_| if cfg!(windows){"python".into()}else{"python3".into()});
 Command::new(python).args(["-m","titivillus.api"]).current_dir(&root).env("PYTHONPATH",&root).env("TITIVILLUS_API_HOST","127.0.0.1").env("TITIVILLUS_API_PORT","8765").stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().map_err(|e|format!("Não foi possível iniciar o backend Python. Instale requirements.txt ou defina TITIVILLUS_PYTHON. {e}"))
}
fn stop_backend(backend:&Backend){if let Ok(mut guard)=backend.0.lock(){if let Some(mut child)=guard.take(){let _=child.kill();let _=child.wait();}}}
fn main(){let app=tauri::Builder::default().setup(|app|{let child=start_backend().map_err(std::io::Error::other)?;app.manage(Backend(Mutex::new(Some(child))));Ok(())}).build(tauri::generate_context!()).expect("erro ao inicializar Titivillus");app.run(|handle,event|{if let RunEvent::Exit=event{if let Some(backend)=handle.try_state::<Backend>(){stop_backend(&backend);}}});}
