use serde::Serialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::env;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, State};

const DEFAULT_BRIDGE_TIMEOUT_SECS: u64 = 300;
const MIN_BRIDGE_TIMEOUT_SECS: u64 = 5;
const MAX_BRIDGE_TIMEOUT_SECS: u64 = 3_600;
const MAX_BRIDGE_COMMAND_LEN: usize = 64;
const MAX_WORKSPACE_ROOT_LEN: usize = 4_096;
const BRIDGE_EVENT_NAME: &str = "jakal-flow://bridge-event";

#[derive(Default)]
struct AppState {
    bridge: Mutex<Option<BridgeSession>>,
}

#[derive(Clone)]
struct BridgeSession {
    stdin: Arc<Mutex<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, Sender<Result<Value, String>>>>>,
    next_id: Arc<AtomicU64>,
    stderr_lines: Arc<Mutex<Vec<String>>>,
    _child: Arc<Mutex<Child>>,
}

#[derive(Clone, Debug, Serialize)]
struct BridgeEventPayload {
    event: String,
    payload: Value,
}

fn parse_bridge_timeout(env_override: Option<String>) -> Duration {
    let seconds = env_override
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(DEFAULT_BRIDGE_TIMEOUT_SECS)
        .clamp(MIN_BRIDGE_TIMEOUT_SECS, MAX_BRIDGE_TIMEOUT_SECS);
    Duration::from_secs(seconds)
}

fn bridge_timeout() -> Duration {
    parse_bridge_timeout(env::var("JAKAL_FLOW_BRIDGE_TIMEOUT_SECS").ok())
}

fn normalize_bridge_command(command: &str) -> Result<String, String> {
    let trimmed = command.trim();
    if trimmed.is_empty() {
        return Err("Bridge command is required.".to_string());
    }
    if trimmed.len() > MAX_BRIDGE_COMMAND_LEN {
        return Err(format!(
            "Bridge command is too long (max {MAX_BRIDGE_COMMAND_LEN} characters)."
        ));
    }
    if !trimmed
        .chars()
        .all(|value| value.is_ascii_alphanumeric() || value == '-' || value == '_')
    {
        return Err("Bridge command may only contain letters, numbers, '-' and '_'.".to_string());
    }
    Ok(trimmed.to_string())
}

fn normalize_workspace_root(workspace_root: Option<String>) -> Result<Option<String>, String> {
    match workspace_root {
        Some(path) => {
            let trimmed = path.trim();
            if trimmed.is_empty() {
                return Ok(None);
            }
            if trimmed.len() > MAX_WORKSPACE_ROOT_LEN {
                return Err(format!(
                    "Workspace root is too long (max {MAX_WORKSPACE_ROOT_LEN} characters)."
                ));
            }
            if trimmed.contains('\0') {
                return Err("Workspace root contains an invalid null character.".to_string());
            }
            Ok(Some(trimmed.to_string()))
        }
        None => Ok(None),
    }
}

fn repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .map_err(|error| format!("Failed to resolve repo root: {error}"))
}

fn resolve_python_executable(root: &Path, env_override: Option<String>) -> String {
    if let Some(value) = env_override {
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

fn python_executable(root: &Path) -> String {
    resolve_python_executable(root, env::var("JAKAL_FLOW_PYTHON").ok())
}

fn build_pythonpath(root: &Path, existing: Option<OsString>) -> Result<String, String> {
    let mut paths = vec![root.join("src")];
    if let Some(existing) = existing {
        paths.extend(env::split_paths(&existing));
    }
    let joined =
        env::join_paths(paths).map_err(|error| format!("Failed to build PYTHONPATH: {error}"))?;
    Ok(joined.to_string_lossy().into_owned())
}

fn pythonpath_with_src(root: &Path) -> Result<String, String> {
    build_pythonpath(root, env::var_os("PYTHONPATH"))
}

fn stderr_excerpt(stderr_lines: &Arc<Mutex<Vec<String>>>) -> String {
    stderr_lines
        .lock()
        .map(|lines| lines.join(" | "))
        .unwrap_or_default()
}

fn store_stderr_line(stderr_lines: &Arc<Mutex<Vec<String>>>, line: String) {
    if let Ok(mut lines) = stderr_lines.lock() {
        let trimmed = line.trim().to_string();
        if !trimmed.is_empty() {
            lines.push(trimmed);
            if lines.len() > 12 {
                let drain_len = lines.len() - 12;
                lines.drain(0..drain_len);
            }
        }
    }
}

fn fail_pending_requests(
    pending: &Arc<Mutex<HashMap<String, Sender<Result<Value, String>>>>>,
    error: String,
) {
    let senders = pending
        .lock()
        .map(|mut items| items.drain().map(|(_, sender)| sender).collect::<Vec<_>>())
        .unwrap_or_default();
    for sender in senders {
        let _ = sender.send(Err(error.clone()));
    }
}

impl BridgeSession {
    fn new<R: tauri::Runtime>(app: &AppHandle<R>) -> Result<Self, String> {
        let root = repo_root()?;
        let python = python_executable(&root);
        let pythonpath = pythonpath_with_src(&root)?;
        let mut child = Command::new(python)
            .arg("-m")
            .arg("jakal_flow.bridge_server")
            .arg("--stdio")
            .current_dir(&root)
            .env("PYTHONPATH", pythonpath)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("Failed to start Python bridge server: {error}"))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to capture Python bridge stdin.".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to capture Python bridge stdout.".to_string())?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| "Failed to capture Python bridge stderr.".to_string())?;

        let pending = Arc::new(Mutex::new(HashMap::<String, Sender<Result<Value, String>>>::new()));
        let stderr_lines = Arc::new(Mutex::new(Vec::<String>::new()));
        let stdout_pending = Arc::clone(&pending);
        let stdout_stderr = Arc::clone(&stderr_lines);
        let stderr_sink = Arc::clone(&stderr_lines);
        let app_handle = app.clone();

        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let line = match line {
                    Ok(value) => value,
                    Err(error) => {
                        fail_pending_requests(
                            &stdout_pending,
                            format!("Failed to read Python bridge stdout: {error}"),
                        );
                        return;
                    }
                };
                if line.trim().is_empty() {
                    continue;
                }
                let parsed: Value = match serde_json::from_str(&line) {
                    Ok(value) => value,
                    Err(error) => {
                        store_stderr_line(
                            &stdout_stderr,
                            format!("Invalid bridge JSON from stdout: {error}"),
                        );
                        continue;
                    }
                };
                let kind = parsed
                    .get("kind")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                match kind.as_str() {
                    "response" => {
                        let id = parsed
                            .get("id")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string();
                        if id.is_empty() {
                            continue;
                        }
                        let sender = stdout_pending
                            .lock()
                            .ok()
                            .and_then(|mut items| items.remove(&id));
                        if let Some(sender) = sender {
                            let ok = parsed.get("ok").and_then(Value::as_bool).unwrap_or(false);
                            if ok {
                                let value = parsed.get("result").cloned().unwrap_or(Value::Null);
                                let _ = sender.send(Ok(value));
                            } else {
                                let error = parsed
                                    .get("error")
                                    .and_then(Value::as_str)
                                    .unwrap_or("Python bridge request failed.")
                                    .to_string();
                                let _ = sender.send(Err(error));
                            }
                        }
                    }
                    "event" => {
                        let event_name = parsed
                            .get("event")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string();
                        let payload = parsed.get("payload").cloned().unwrap_or(Value::Null);
                        let _ = app_handle.emit(
                            BRIDGE_EVENT_NAME,
                            BridgeEventPayload {
                                event: event_name,
                                payload,
                            },
                        );
                    }
                    _ => {}
                }
            }
            let detail = stderr_excerpt(&stdout_stderr);
            let error = if detail.is_empty() {
                "Python bridge server closed unexpectedly.".to_string()
            } else {
                format!("Python bridge server closed unexpectedly. {detail}")
            };
            fail_pending_requests(&stdout_pending, error);
        });

        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(value) = line {
                    store_stderr_line(&stderr_sink, value);
                }
            }
        });

        let session = Self {
            stdin: Arc::new(Mutex::new(stdin)),
            pending,
            next_id: Arc::new(AtomicU64::new(1)),
            stderr_lines,
            _child: Arc::new(Mutex::new(child)),
        };
        let ping = session.request("ping", json!({}), bridge_timeout())?;
        let status = ping
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if status != "ok" {
            return Err("Python bridge server did not acknowledge startup.".to_string());
        }
        Ok(session)
    }

    fn request(&self, method: &str, params: Value, timeout: Duration) -> Result<Value, String> {
        let request_id = format!("req-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let (sender, receiver): (Sender<Result<Value, String>>, Receiver<Result<Value, String>>) =
            mpsc::channel();
        self.pending
            .lock()
            .map_err(|_| "Failed to lock pending bridge requests.".to_string())?
            .insert(request_id.clone(), sender);

        let message = json!({
            "id": request_id,
            "method": method,
            "params": params,
        });
        let serialized = serde_json::to_string(&message)
            .map_err(|error| format!("Failed to serialize bridge request: {error}"))?;
        {
            let mut stdin = self
                .stdin
                .lock()
                .map_err(|_| "Failed to lock Python bridge stdin.".to_string())?;
            if let Err(error) = stdin.write_all(serialized.as_bytes()) {
                self.pending
                    .lock()
                    .ok()
                    .and_then(|mut items| items.remove(message["id"].as_str().unwrap_or_default()));
                return Err(format!("Failed to write bridge request: {error}"));
            }
            if let Err(error) = stdin.write_all(b"\n") {
                self.pending
                    .lock()
                    .ok()
                    .and_then(|mut items| items.remove(message["id"].as_str().unwrap_or_default()));
                return Err(format!("Failed to finalize bridge request: {error}"));
            }
            if let Err(error) = stdin.flush() {
                self.pending
                    .lock()
                    .ok()
                    .and_then(|mut items| items.remove(message["id"].as_str().unwrap_or_default()));
                return Err(format!("Failed to flush bridge request: {error}"));
            }
        }
        match receiver.recv_timeout(timeout) {
            Ok(result) => result,
            Err(_) => {
                self.pending
                    .lock()
                    .ok()
                    .and_then(|mut items| items.remove(message["id"].as_str().unwrap_or_default()));
                let detail = stderr_excerpt(&self.stderr_lines);
                if detail.is_empty() {
                    Err(format!(
                        "Python bridge server timed out after {} seconds while running '{}'.",
                        timeout.as_secs(),
                        method
                    ))
                } else {
                    Err(format!(
                        "Python bridge server timed out after {} seconds while running '{}'. {}",
                        timeout.as_secs(),
                        method,
                        detail
                    ))
                }
            }
        }
    }
}

fn bridge_session<R: tauri::Runtime>(
    app: &AppHandle<R>,
    state: &AppState,
) -> Result<BridgeSession, String> {
    if let Ok(guard) = state.bridge.lock() {
        if let Some(session) = guard.as_ref() {
            return Ok(session.clone());
        }
    }
    let session = BridgeSession::new(app)?;
    let mut guard = state
        .bridge
        .lock()
        .map_err(|_| "Failed to lock bridge session state.".to_string())?;
    *guard = Some(session.clone());
    Ok(session)
}

fn bridge_params(
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<Value, String> {
    Ok(json!({
        "command": normalize_bridge_command(&command)?,
        "payload": payload.unwrap_or(Value::Null),
        "workspace_root": normalize_workspace_root(workspace_root)?,
    }))
}

#[tauri::command]
fn bridge_request<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request("bridge_request", bridge_params(command, payload, workspace_root)?, bridge_timeout())
}

#[tauri::command]
fn start_bridge_job<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request("start_job", bridge_params(command, payload, workspace_root)?, bridge_timeout())
}

#[tauri::command]
fn get_bridge_job<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    job_id: String,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request("get_job", json!({ "job_id": job_id }), bridge_timeout())
}

#[tauri::command]
fn list_bridge_jobs<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request("list_jobs", json!({}), bridge_timeout())
}

#[tauri::command]
fn configure_bridge_scheduler<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    max_concurrent_jobs: i64,
    workspace_root: Option<String>,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request(
        "configure_scheduler",
        json!({
            "max_concurrent_jobs": max_concurrent_jobs,
            "workspace_root": normalize_workspace_root(workspace_root)?,
        }),
        bridge_timeout(),
    )
}

#[tauri::command]
fn cancel_bridge_job<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    job_id: String,
) -> Result<Value, String> {
    let session = bridge_session(&app, state.inner())?;
    session.request("cancel_job", json!({ "job_id": job_id }), bridge_timeout())
}


#[tauri::command]
fn open_in_system(path: String) -> Result<(), String> {
    if path.trim().is_empty() {
        return Err("Path is required.".to_string());
    }
    #[cfg(target_os = "windows")]
    { Command::new("explorer").arg(&path).spawn().map_err(|e| e.to_string()).map(|_| ()) }
    #[cfg(target_os = "macos")]
    { Command::new("open").arg(&path).spawn().map_err(|e| e.to_string()).map(|_| ()) }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    { Command::new("xdg-open").arg(&path).spawn().map_err(|e| e.to_string()).map(|_| ()) }
}

#[tauri::command]
fn open_in_vscode(path: String) -> Result<(), String> {
    if path.trim().is_empty() {
        return Err("Path is required.".to_string());
    }
    Command::new("code").arg(&path).spawn().map_err(|e| e.to_string()).map(|_| ())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            bridge_request,
            start_bridge_job,
            get_bridge_job,
            list_bridge_jobs,
            configure_bridge_scheduler,
            cancel_bridge_job,
            open_in_system,
            open_in_vscode
        ])
        .run(tauri::generate_context!())
        .expect("error while running jakal-flow desktop");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};

    static TEST_DIR_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TestDir {
        path: PathBuf,
    }

    impl TestDir {
        fn new() -> Self {
            let path = env::temp_dir().join(format!(
                "jakal-flow-desktop-tests-{}-{}",
                std::process::id(),
                TEST_DIR_COUNTER.fetch_add(1, AtomicOrdering::Relaxed)
            ));
            fs::create_dir_all(&path).expect("create test directory");
            Self { path }
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TestDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn touch(path: &Path) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create parent directories");
        }
        fs::write(path, b"").expect("create file");
    }

    #[test]
    fn resolve_python_executable_prefers_non_empty_override() {
        let root = TestDir::new();
        touch(&root.path().join(".venv").join("Scripts").join("python.exe"));

        let resolved = resolve_python_executable(root.path(), Some("custom-python".to_string()));

        assert_eq!(resolved, "custom-python");
    }

    #[test]
    fn resolve_python_executable_ignores_blank_override_and_uses_windows_venv() {
        let root = TestDir::new();
        let windows_python = root.path().join(".venv").join("Scripts").join("python.exe");
        touch(&windows_python);

        let resolved = resolve_python_executable(root.path(), Some("   ".to_string()));

        assert_eq!(resolved, windows_python.to_string_lossy());
    }

    #[test]
    fn resolve_python_executable_uses_unix_venv_when_windows_venv_is_missing() {
        let root = TestDir::new();
        let unix_python = root.path().join(".venv").join("bin").join("python");
        touch(&unix_python);

        let resolved = resolve_python_executable(root.path(), None);

        assert_eq!(resolved, unix_python.to_string_lossy());
    }

    #[test]
    fn build_pythonpath_prepends_repo_src() {
        let root = TestDir::new();
        let existing = env::join_paths([root.path().join("existing")]).expect("join paths");

        let pythonpath = build_pythonpath(root.path(), Some(existing)).expect("pythonpath");

        assert!(pythonpath.contains(&root.path().join("src").to_string_lossy().to_string()));
        assert!(pythonpath.contains("existing"));
    }

    #[test]
    fn bridge_params_normalize_inputs() {
        let params = bridge_params(
            "run-plan".to_string(),
            Some(json!({"repo_id": "demo"})),
            Some("C:/workspace".to_string()),
        )
        .expect("params");

        assert_eq!(params["command"], "run-plan");
        assert_eq!(params["payload"]["repo_id"], "demo");
        assert_eq!(params["workspace_root"], "C:/workspace");
    }

    #[test]
    fn normalize_workspace_root_rejects_embedded_nul() {
        let error = normalize_workspace_root(Some("bad\0path".to_string())).expect_err("expected error");

        assert!(error.contains("null character"));
    }
}
