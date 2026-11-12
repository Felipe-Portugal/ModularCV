mod engine;

use engine::{AdapterOp, DemoWorkspace, EngineLauncher, ValidationResult};
use std::path::Path;
use tauri::Manager;

/// Runs the real engine off the UI thread. `operation` must be `facts_check`.
#[tauri::command]
async fn validate_workspace(app: tauri::AppHandle, operation: String, workspace: String) -> Result<ValidationResult, String> {
    let launcher = launcher(&app);
    tauri::async_runtime::spawn_blocking(move || launcher.validate(&operation, &workspace))
        .await
        .map_err(|_| "The validation task failed unexpectedly.".to_string())
}

/// Creates (never overwrites) a fictional demo workspace outside the repository,
/// in the app data folder. `kind` is `valid` or `invalid`.
#[tauri::command]
async fn prepare_demo_workspace(app: tauri::AppHandle, kind: String) -> Result<DemoWorkspace, String> {
    let invalid = match kind.as_str() {
        "valid" => false,
        "invalid" => true,
        "git" => return prepare_git_demo(app).await,
        _ => return Err("Unknown demo kind.".into()),
    };
    let base = app.path().app_local_data_dir().map_err(|_| "No app data folder available.".to_string())?;
    let target = base.join(if invalid { "demo-workspace-invalid" } else { "demo-workspace" });
    let engine_dir = launcher(&app).engine_dir;
    tauri::async_runtime::spawn_blocking(move || engine::ensure_demo_workspace(&engine_dir, &target, invalid))
        .await
        .map_err(|_| "The task failed unexpectedly.".to_string())?
}

/// Test/demo only, on explicit request: the fictional workspace as an independent Git repository (never a user workspace).
async fn prepare_git_demo(app: tauri::AppHandle) -> Result<DemoWorkspace, String> {
    let base = app.path().app_local_data_dir().map_err(|_| "No app data folder available.".to_string())?;
    let target = base.join("demo-workspace-git");
    let engine_dir = launcher(&app).engine_dir;
    tauri::async_runtime::spawn_blocking(move || engine::ensure_git_demo_workspace(&engine_dir, &target))
        .await
        .map_err(|_| "The task failed unexpectedly.".to_string())?
}

/// The launcher of the running application: embedded engine when installed, development interpreter otherwise.
fn launcher(app: &tauri::AppHandle) -> EngineLauncher {
    let resources = app.path().resource_dir().ok();
    EngineLauncher::for_app(resources.as_deref())
}

async fn run_adapter(app: &tauri::AppHandle, op: AdapterOp, workspace: String, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    let launcher = launcher(app);
    tauri::async_runtime::spawn_blocking(move || launcher.adapter(op, &workspace, payload))
        .await
        .map_err(|_| "The task failed unexpectedly.".to_string())
}

/// Reads facts, profile and resume content through the engine.
#[tauri::command]
async fn read_workspace(app: tauri::AppHandle, workspace: String) -> Result<serde_json::Value, String> {
    run_adapter(&app, AdapterOp::Read, workspace, serde_json::json!({})).await
}

/// Saves one fact (update or create). Validated and written by the engine adapter.
#[tauri::command]
async fn save_fact(app: tauri::AppHandle, workspace: String, request: serde_json::Value) -> Result<serde_json::Value, String> {
    run_adapter(&app, AdapterOp::SaveFact, workspace, request).await
}

/// Saves whitelisted profile fields. Validated and written by the engine adapter.
#[tauri::command]
async fn save_profile(app: tauri::AppHandle, workspace: String, request: serde_json::Value) -> Result<serde_json::Value, String> {
    run_adapter(&app, AdapterOp::SaveProfile, workspace, request).await
}

/// Runs one operation of the closed adapter list (offers, matrix, plan, assembly, generation).
/// An unknown name is refused here, before any process is started.
#[tauri::command]
async fn adapter_call(app: tauri::AppHandle, workspace: String, operation: String, request: serde_json::Value) -> Result<serde_json::Value, String> {
    match AdapterOp::from_name(&operation) {
        Some(op) => run_adapter(&app, op, workspace, request).await,
        None => Ok(serde_json::json!({"ok": false, "code": "OPERATION_NOT_ALLOWED", "message": "Unknown operation.", "details": []})),
    }
}

/// Environment diagnostics: embedded engine, Git, provenance of the workspace, LaTeX. Read-only, offline, closed answer.
#[tauri::command]
async fn diagnostics(app: tauri::AppHandle, workspace: Option<String>) -> Result<serde_json::Value, String> {
    let launcher = launcher(&app);
    tauri::async_runtime::spawn_blocking(move || launcher.diagnose(workspace.as_deref()))
        .await
        .map_err(|_| "The task failed unexpectedly.".to_string())
}

/// Shows a generated file (or the workspace folder) in Windows Explorer. Only paths inside the
/// workspace are accepted; nothing is opened or executed.
#[tauri::command]
fn reveal_in_explorer(workspace: String, relative: Option<String>) -> Result<(), String> {
    let root = Path::new(&workspace).canonicalize().map_err(|_| "The workspace does not exist.".to_string())?;
    let target = match relative.as_deref() {
        None | Some("") => root.clone(),
        Some(rel) => {
            if rel.contains("..") || Path::new(rel).is_absolute() {
                return Err("Unsafe path.".into());
            }
            root.join(rel).canonicalize().map_err(|_| "The file does not exist.".to_string())?
        }
    };
    if !target.starts_with(&root) {
        return Err("The path is outside the workspace.".into());
    }
    let mut cmd = std::process::Command::new("explorer.exe");
    if target.is_file() {
        cmd.arg(format!("/select,{}", target.display()));
    } else {
        cmd.arg(target.as_os_str());
    }
    cmd.spawn().map(|_| ()).map_err(|_| "Could not open Explorer.".to_string())
}

/// Opens a package or generated PDF in the system's PDF reader. The document is first validated by the engine adapter
/// (fixed locations of the active workspace, real PDF, no link); only that validated path is handed to Windows.
#[tauri::command]
async fn open_pdf(app: tauri::AppHandle, workspace: String, package: Option<String>, output: Option<String>) -> Result<(), String> {
    let mut request = serde_json::Map::new();
    request.insert("with_bytes".into(), false.into());
    if let Some(p) = package {
        request.insert("package".into(), p.into());
    }
    if let Some(o) = output {
        request.insert("output".into(), o.into());
    }
    let checked = run_adapter(&app, AdapterOp::PdfRead, workspace.clone(), serde_json::Value::Object(request)).await?;
    if checked["ok"] != true {
        return Err(checked["message"].as_str().unwrap_or("The document cannot be opened.").to_string());
    }
    let relative = checked["file"].as_str().ok_or("The document cannot be opened.")?.to_string();
    let root = Path::new(&workspace).canonicalize().map_err(|_| "The workspace does not exist.".to_string())?;
    let target = root.join(&relative).canonicalize().map_err(|_| "The document does not exist.".to_string())?;
    let is_pdf = target.extension().map(|e| e.eq_ignore_ascii_case("pdf")).unwrap_or(false);
    if !target.starts_with(&root) || !is_pdf || !target.is_file() {
        return Err("The document is not an allowed PDF of this workspace.".into());
    }
    std::process::Command::new("explorer.exe").arg(target.as_os_str()).spawn().map(|_| ()).map_err(|_| "Could not open the PDF reader.".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![validate_workspace, prepare_demo_workspace, read_workspace, save_fact, save_profile, adapter_call, reveal_in_explorer, open_pdf, diagnostics])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
