use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::env;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};

#[derive(Clone, Serialize)]
struct JobSnapshot {
    id: String,
    command: String,
    status: String,
    error: Option<String>,
    result: Option<Value>,
    updated_at_ms: u128,
}

#[derive(Default)]
struct AppState {
    jobs: Mutex<HashMap<String, JobSnapshot>>,
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .map_err(|error| format!("Failed to resolve repo root: {error}"))
}

fn python_executable(root: &Path) -> String {
    if let Ok(value) = env::var("CODEX_AUTO_PYTHON") {
        if !value.trim().is_empty() {
            return value;
        }
    }

    let windows_venv = root.join(".venv").join("Scripts").join("python.exe");
    if windows_venv.exists() {
        return windows_venv.to_string_lossy().into_owned();
    }

    let unix_venv = root.join(".venv").join("bin").join("python");
    if unix_venv.exists() {
        return unix_venv.to_string_lossy().into_owned();
    }

    "python".to_string()
}

fn pythonpath_with_src(root: &Path) -> Result<String, String> {
    let mut paths = vec![root.join("src")];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        paths.extend(env::split_paths(&existing));
    }
    let joined = env::join_paths(paths).map_err(|error| format!("Failed to build PYTHONPATH: {error}"))?;
    Ok(joined.to_string_lossy().into_owned())
}

fn run_bridge_command(command: &str, payload: Option<Value>, workspace_root: Option<String>) -> Result<Value, String> {
    let root = repo_root()?;
    let python = python_executable(&root);
    let pythonpath = pythonpath_with_src(&root)?;
    let mut process = Command::new(python);
    process
        .arg("-m")
        .arg("codex_auto.ui_bridge")
        .arg(command)
        .current_dir(&root)
        .env("PYTHONPATH", pythonpath)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(path) = workspace_root {
        process.arg("--workspace-root").arg(path);
    }

    let mut child = process
        .spawn()
        .map_err(|error| format!("Failed to start Python bridge: {error}"))?;

    if let Some(payload) = payload {
        if let Some(stdin) = child.stdin.as_mut() {
            stdin
                .write_all(
                    serde_json::to_vec(&payload)
                        .map_err(|error| format!("Failed to serialize bridge payload: {error}"))?
                        .as_slice(),
                )
                .map_err(|error| format!("Failed to write bridge payload: {error}"))?;
        }
    }

    let output = child
        .wait_with_output()
        .map_err(|error| format!("Failed to wait for Python bridge: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    if !output.status.success() {
        let message = if stderr.is_empty() { stdout } else { stderr };
        return Err(message);
    }

    if stdout.is_empty() {
        return Ok(serde_json::json!({}));
    }

    serde_json::from_str(&stdout).map_err(|error| format!("Failed to parse bridge JSON: {error}"))
}

fn update_job(app: &AppHandle, job_id: &str, mutate: impl FnOnce(&mut JobSnapshot)) {
    if let Ok(mut jobs) = app.state::<AppState>().jobs.lock() {
        if let Some(job) = jobs.get_mut(job_id) {
            mutate(job);
            job.updated_at_ms = now_ms();
        }
    }
}

#[tauri::command]
fn bridge_request(
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<Value, String> {
    run_bridge_command(&command, payload, workspace_root)
}

#[tauri::command]
fn start_bridge_job(
    app: AppHandle,
    state: State<'_, AppState>,
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<JobSnapshot, String> {
    {
        let jobs = state.jobs.lock().map_err(|_| "Failed to lock job state.".to_string())?;
        if jobs.values().any(|job| job.status == "running") {
            return Err("Another background task is already running.".to_string());
        }
    }

    let job_id = format!("job-{}-{}", command, now_ms());
    let snapshot = JobSnapshot {
        id: job_id.clone(),
        command: command.clone(),
        status: "running".to_string(),
        error: None,
        result: None,
        updated_at_ms: now_ms(),
    };

    state
        .jobs
        .lock()
        .map_err(|_| "Failed to record background job.".to_string())?
        .insert(job_id.clone(), snapshot.clone());

    std::thread::spawn(move || {
        let result = run_bridge_command(&command, payload, workspace_root);
        match result {
            Ok(value) => update_job(&app, &job_id, |job| {
                job.status = "completed".to_string();
                job.result = Some(value);
                job.error = None;
            }),
            Err(error) => update_job(&app, &job_id, |job| {
                job.status = "failed".to_string();
                job.error = Some(error);
                job.result = None;
            }),
        }
    });

    Ok(snapshot)
}

#[tauri::command]
fn get_bridge_job(job_id: String, state: State<'_, AppState>) -> Option<JobSnapshot> {
    state.jobs.lock().ok().and_then(|jobs| jobs.get(&job_id).cloned())
}

#[tauri::command]
fn list_bridge_jobs(state: State<'_, AppState>) -> Vec<JobSnapshot> {
    state
        .jobs
        .lock()
        .map(|jobs| jobs.values().cloned().collect())
        .unwrap_or_default()
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            bridge_request,
            start_bridge_job,
            get_bridge_job,
            list_bridge_jobs
        ])
        .run(tauri::generate_context!())
        .expect("error while running codex-auto desktop");
}
