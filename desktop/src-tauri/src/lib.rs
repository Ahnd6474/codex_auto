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
use tauri::{AppHandle, Emitter, Manager, State};
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const DEFAULT_BRIDGE_TIMEOUT_SECS: u64 = 300;
const MIN_BRIDGE_TIMEOUT_SECS: u64 = 5;
const MAX_BRIDGE_TIMEOUT_SECS: u64 = 3_600;
const MAX_BRIDGE_COMMAND_LEN: usize = 64;
const MAX_WORKSPACE_ROOT_LEN: usize = 4_096;
const BRIDGE_EVENT_NAME: &str = "jakal-flow://bridge-event";
const BUNDLED_RUNTIME_DIRNAME: &str = "rt";
const BUNDLED_PYTHON_DIRNAME: &str = "py";
const BUNDLED_TOOLING_DIRNAME: &str = "bin";
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
struct AppState {
    bridge: Mutex<Option<BridgeSession>>,
}

#[derive(Clone)]
struct BridgeSession {
    stdin: Arc<Mutex<ChildStdin>>,
    pending: PendingRequestRegistry,
    next_id: Arc<AtomicU64>,
    stderr_lines: Arc<Mutex<Vec<String>>>,
    _child: Arc<Mutex<Child>>,
}

#[derive(Clone, Debug, Serialize)]
struct BridgeEventPayload {
    event: String,
    payload: Value,
}

type BridgeResponse = Result<Value, String>;
type PendingRequest = Sender<BridgeResponse>;

#[derive(Clone, Default)]
struct PendingRequestRegistry {
    inner: Arc<Mutex<HashMap<String, PendingRequest>>>,
}

impl PendingRequestRegistry {
    fn insert(&self, request_id: String, sender: PendingRequest) -> Result<(), String> {
        self.inner
            .lock()
            .map_err(|_| "Failed to lock pending bridge requests.".to_string())?
            .insert(request_id, sender);
        Ok(())
    }

    fn take(&self, request_id: &str) -> Option<PendingRequest> {
        self.inner
            .lock()
            .ok()
            .and_then(|mut items| items.remove(request_id))
    }

    fn clear(&self, request_id: &str) -> bool {
        self.inner
            .lock()
            .ok()
            .and_then(|mut items| items.remove(request_id).map(|_| ()))
            .is_some()
    }

    fn count(&self) -> usize {
        self.inner.lock().map(|items| items.len()).unwrap_or(0)
    }

    fn fail_all(&self, error: String) {
        let senders: Vec<PendingRequest> = self
            .inner
            .lock()
            .map(|mut items| items.drain().map(|(_, sender)| sender).collect())
            .unwrap_or_default();
        for sender in senders {
            let _ = sender.send(Err(error.clone()));
        }
    }
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

fn checkout_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn backend_root_is_usable(root: &Path) -> bool {
    root.join("src").join("jakal_flow").is_dir()
}

fn normalized_existing_path(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn path_is_within(path: &Path, base: &Path) -> bool {
    let normalized_path = normalized_existing_path(path);
    let normalized_base = normalized_existing_path(base);
    normalized_path == normalized_base || normalized_path.starts_with(&normalized_base)
}

fn resource_root_candidates(resource_root: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    let relative_suffixes = [
        PathBuf::new(),
        PathBuf::from("_up_"),
        PathBuf::from("_up_").join("_up_"),
    ];
    for suffix in relative_suffixes {
        let candidate = if suffix.as_os_str().is_empty() {
            resource_root.to_path_buf()
        } else {
            resource_root.join(suffix)
        };
        if !candidates.iter().any(|existing| existing == &candidate) {
            candidates.push(candidate);
        }
    }
    candidates
}

fn unique_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut unique = Vec::new();
    for path in paths {
        if !unique.iter().any(|existing| existing == &path) {
            unique.push(path);
        }
    }
    unique
}

fn current_executable_path() -> Option<PathBuf> {
    env::current_exe().ok()
}

fn current_executable_dir() -> Option<PathBuf> {
    current_executable_path().and_then(|path| path.parent().map(Path::to_path_buf))
}

fn app_resource_roots<R: tauri::Runtime>(app: &AppHandle<R>) -> Vec<PathBuf> {
    unique_paths(
        [
            app.path().resource_dir().ok(),
            current_executable_dir(),
        ]
        .into_iter()
        .flatten()
        .collect(),
    )
}

fn should_prefer_checkout_root(checkout_root: &Path, executable_path: Option<&Path>) -> bool {
    let Some(executable_path) = executable_path else {
        return false;
    };
    let checkout_target_root = checkout_root.join("desktop").join("src-tauri").join("target");
    path_is_within(executable_path, &checkout_target_root)
}

fn resolve_backend_root(
    checkout_root: &Path,
    resource_roots: &[PathBuf],
    prefer_checkout: bool,
) -> Result<PathBuf, String> {
    let checkout_candidate = checkout_root
        .canonicalize()
        .unwrap_or_else(|_| checkout_root.to_path_buf());
    if prefer_checkout && backend_root_is_usable(&checkout_candidate) {
        return Ok(checkout_candidate);
    }

    for resource_root in resource_roots {
        for resource_candidate in resource_root_candidates(resource_root) {
            let resolved = resource_candidate
                .canonicalize()
                .unwrap_or(resource_candidate);
            if backend_root_is_usable(&resolved) {
                return Ok(resolved);
            }
        }
    }

    if backend_root_is_usable(&checkout_candidate) {
        return Ok(checkout_candidate);
    }

    let searched_resources = if resource_roots.is_empty() {
        "<none>".to_string()
    } else {
        resource_roots
            .iter()
            .flat_map(|root| resource_root_candidates(root))
            .map(|candidate| candidate.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    };
    let resource_hint = if resource_roots.is_empty() {
        "<none>".to_string()
    } else {
        resource_roots
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    };
    Err(format!(
        "Failed to resolve desktop backend root. checkout={} resources={resource_hint} searched=[{}]",
        checkout_root.display(),
        searched_resources
    ))
}

fn repo_root<R: tauri::Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    let checkout = checkout_root();
    let resource_roots = app_resource_roots(app);
    resolve_backend_root(
        &checkout,
        &resource_roots,
        should_prefer_checkout_root(&checkout, current_executable_path().as_deref()),
    )
}

fn bundled_runtime_root(resource_roots: &[PathBuf]) -> Option<PathBuf> {
    for root in resource_roots {
        for candidate_root in resource_root_candidates(root) {
            let runtime_root = candidate_root.join(BUNDLED_RUNTIME_DIRNAME);
            if runtime_root.is_dir() {
                return Some(runtime_root);
            }
        }
    }
    None
}

fn bundled_python_home(resource_roots: &[PathBuf]) -> Option<PathBuf> {
    let candidate = bundled_runtime_root(resource_roots)?.join(BUNDLED_PYTHON_DIRNAME);
    if candidate.join("Lib").is_dir() {
        Some(candidate)
    } else {
        None
    }
}

fn bundled_tooling_bin(resource_roots: &[PathBuf]) -> Option<PathBuf> {
    let candidate = bundled_runtime_root(resource_roots)?.join(BUNDLED_TOOLING_DIRNAME);
    if candidate.is_dir() {
        Some(candidate)
    } else {
        None
    }
}

fn resolve_python_executable(root: &Path, resource_roots: &[PathBuf], env_override: Option<String>) -> String {
    if let Some(value) = env_override {
        if !value.trim().is_empty() {
            return value;
        }
    }

    if let Some(bundled_home) = bundled_python_home(resource_roots) {
        let bundled_python = bundled_home.join("python.exe");
        if bundled_python.exists() {
            return bundled_python.to_string_lossy().into_owned();
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

fn prepend_env_path(path: &Path, existing: Option<OsString>) -> Result<String, String> {
    let mut paths = vec![path.to_path_buf()];
    if let Some(existing) = existing {
        paths.extend(env::split_paths(&existing));
    }
    env::join_paths(paths)
        .map(|joined| joined.to_string_lossy().into_owned())
        .map_err(|error| format!("Failed to build PATH: {error}"))
}

fn apply_background_process_flags(command: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        command.creation_flags(CREATE_NO_WINDOW);
    }
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

fn format_bridge_error_payload(error: &Value) -> String {
    const BRIDGE_ERROR_PREFIX: &str = "BRIDGE_ERROR_JSON:";
    let fallback = "Python bridge request failed.".to_string();
    if error.is_object() || error.is_array() {
        return serde_json::to_string(error)
            .map(|payload| format!("{BRIDGE_ERROR_PREFIX}{payload}"))
            .unwrap_or(fallback);
    }
    if let Some(message) = error.as_str() {
        let trimmed = message.trim();
        return if trimmed.is_empty() {
            fallback
        } else {
            trimmed.to_string()
        };
    }
    if error.is_null() {
        return fallback;
    }
    error.to_string()
}

fn log_bridge_issue(
    component: &str,
    request_id: &str,
    method: &str,
    error: &str,
    pending_count: usize,
) {
    eprintln!(
        "[jakal-flow bridge] {component} request_id={request_id} method={method} pending={pending_count} error={error}"
    );
}

impl BridgeSession {
    fn new<R: tauri::Runtime>(app: &AppHandle<R>) -> Result<Self, String> {
        let root = repo_root(app)?;
        let resource_roots = app_resource_roots(app);
        let python = resolve_python_executable(&root, &resource_roots, env::var("JAKAL_FLOW_PYTHON").ok());
        let pythonpath = pythonpath_with_src(&root)?;
        let mut command = Command::new(&python);
        command
            .arg("-m")
            .arg("jakal_flow.bridge_server")
            .arg("--stdio")
            .current_dir(&root)
            .env("PYTHONPATH", pythonpath)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(python_home) = bundled_python_home(&resource_roots) {
            command
                .env("PYTHONHOME", python_home.as_os_str())
                .env("PYTHONNOUSERSITE", "1")
                .env("JAKAL_FLOW_BUNDLED_PYTHON_HOME", python_home.as_os_str());
        }
        if let Some(tooling_bin) = bundled_tooling_bin(&resource_roots) {
            let path = prepend_env_path(&tooling_bin, env::var_os("PATH"))?;
            command
                .env("PATH", path)
                .env("JAKAL_FLOW_BUNDLED_TOOLING_ROOT", tooling_bin.as_os_str());
        }
        apply_background_process_flags(&mut command);
        let mut child = command
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

        let pending = PendingRequestRegistry::default();
        let stderr_lines = Arc::new(Mutex::new(Vec::<String>::new()));
        let stdout_pending = pending.clone();
        let stdout_stderr = Arc::clone(&stderr_lines);
        let stderr_sink = Arc::clone(&stderr_lines);
        let app_handle = app.clone();

        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let line = match line {
                    Ok(value) => value,
                    Err(error) => {
                        stdout_pending
                            .fail_all(format!("Failed to read Python bridge stdout: {error}"));
                        return;
                    }
                };
                if line.trim().is_empty() {
                    continue;
                }
                let parsed: Value = match serde_json::from_str(&line) {
                    Ok(value) => value,
                    Err(error) => {
                        log_bridge_issue(
                            "stdout_parse",
                            "",
                            "bridge",
                            &format!("Invalid bridge JSON from stdout: {error}"),
                            stdout_pending.count(),
                        );
                        store_stderr_line(
                            &stdout_stderr,
                            format!("Invalid bridge JSON from stdout: {error} line={line}"),
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
                            log_bridge_issue(
                                "response",
                                "",
                                "bridge",
                                "response payload is missing id",
                                stdout_pending.count(),
                            );
                            continue;
                        }
                        let sender = stdout_pending.take(&id);
                        if sender.is_none() {
                            log_bridge_issue(
                                "response_orphan",
                                &id,
                                "bridge",
                                "request context was already cleared",
                                stdout_pending.count(),
                            );
                        }
                        if let Some(sender) = sender {
                            let ok = parsed.get("ok").and_then(Value::as_bool).unwrap_or(false);
                            if ok {
                                let value = parsed.get("result").cloned().unwrap_or(Value::Null);
                                let _ = sender.send(Ok(value));
                            } else {
                                let error = parsed
                                    .get("error")
                                    .map_or_else(|| "Python bridge request failed.".to_string(), format_bridge_error_payload);
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
                    _ => {
                        log_bridge_issue(
                            "stdout_unknown_kind",
                            "",
                            "bridge",
                            &format!("Unexpected message kind: {kind}"),
                            stdout_pending.count(),
                        );
                    }
                }
            }
            let detail = stderr_excerpt(&stdout_stderr);
            let error = if detail.is_empty() {
                "Python bridge server closed unexpectedly.".to_string()
            } else {
                format!("Python bridge server closed unexpectedly. {detail}")
            };
            stdout_pending.fail_all(error);
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
        let (sender, receiver): (PendingRequest, Receiver<BridgeResponse>) = mpsc::channel();

        let message = json!({
            "id": request_id,
            "method": method,
            "params": params,
        });
        let serialized = serde_json::to_string(&message)
            .map_err(|error| {
                log_bridge_issue(
                    "serialize",
                    &request_id,
                    method,
                    &format!("failed to serialize request payload: {error}"),
                    self.pending.count(),
                );
                format!("Failed to serialize bridge request: {error}")
            })?;
        self.pending.insert(request_id.clone(), sender)?;
        {
            let mut stdin = self
                .stdin
                .lock()
                .map_err(|_| "Failed to lock Python bridge stdin.".to_string())?;
            if let Err(error) = stdin.write_all(serialized.as_bytes()) {
                let removed = self.pending.clear(&request_id);
                log_bridge_issue(
                    "write",
                    &request_id,
                    method,
                    if removed {
                        "write_all(payload) failed"
                    } else {
                        "write_all(payload) failed but request was not tracked"
                    },
                    self.pending.count(),
                );
                return Err(format!("Failed to write bridge request: {error}"));
            }
            if let Err(error) = stdin.write_all(b"\n") {
                let removed = self.pending.clear(&request_id);
                log_bridge_issue(
                    "write",
                    &request_id,
                    method,
                    if removed {
                        "finalize request message failed"
                    } else {
                        "finalize request message failed but request was not tracked"
                    },
                    self.pending.count(),
                );
                return Err(format!("Failed to finalize bridge request: {error}"));
            }
            if let Err(error) = stdin.flush() {
                let removed = self.pending.clear(&request_id);
                log_bridge_issue(
                    "write",
                    &request_id,
                    method,
                    if removed {
                        "flush failed"
                    } else {
                        "flush failed but request was not tracked"
                    },
                    self.pending.count(),
                );
                return Err(format!("Failed to flush bridge request: {error}"));
            }
        }
        match receiver.recv_timeout(timeout) {
            Ok(result) => result,
            Err(_) => {
                let removed = self.pending.clear(&request_id);
                log_bridge_issue(
                    "timeout",
                    &request_id,
                    method,
                    if removed {
                        "request did not complete before timeout"
                    } else {
                        "request did not complete before timeout but request was not tracked"
                    },
                    self.pending.count(),
                );
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

        let resolved = resolve_python_executable(root.path(), &[], Some("custom-python".to_string()));

        assert_eq!(resolved, "custom-python");
    }

    #[test]
    fn resolve_python_executable_ignores_blank_override_and_uses_windows_venv() {
        let root = TestDir::new();
        let windows_python = root.path().join(".venv").join("Scripts").join("python.exe");
        touch(&windows_python);

        let resolved = resolve_python_executable(root.path(), &[], Some("   ".to_string()));

        assert_eq!(resolved, windows_python.to_string_lossy());
    }

    #[test]
    fn resolve_python_executable_uses_unix_venv_when_windows_venv_is_missing() {
        let root = TestDir::new();
        let unix_python = root.path().join(".venv").join("bin").join("python");
        touch(&unix_python);

        let resolved = resolve_python_executable(root.path(), &[], None);

        assert_eq!(resolved, unix_python.to_string_lossy());
    }

    #[test]
    fn resolve_python_executable_prefers_bundled_runtime_before_repo_venv() {
        let root = TestDir::new();
        let resources = TestDir::new();
        let bundled_python = resources
            .path()
            .join(BUNDLED_RUNTIME_DIRNAME)
            .join(BUNDLED_PYTHON_DIRNAME)
            .join("python.exe");
        let venv_python = root.path().join(".venv").join("Scripts").join("python.exe");
        touch(&bundled_python);
        touch(
            &resources
                .path()
                .join(BUNDLED_RUNTIME_DIRNAME)
                .join(BUNDLED_PYTHON_DIRNAME)
                .join("Lib")
                .join("os.py"),
        );
        touch(&venv_python);

        let resolved =
            resolve_python_executable(root.path(), &[resources.path().to_path_buf()], None);

        assert_eq!(resolved, bundled_python.to_string_lossy());
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
    fn prepend_env_path_adds_directory_before_existing_entries() {
        let root = TestDir::new();
        let bundled = root
            .path()
            .join(BUNDLED_RUNTIME_DIRNAME)
            .join(BUNDLED_TOOLING_DIRNAME);
        let existing = env::join_paths([root.path().join("existing")]).expect("join paths");

        let path_value = prepend_env_path(&bundled, Some(existing)).expect("path");

        let entries: Vec<PathBuf> = env::split_paths(&OsString::from(path_value)).collect();
        assert_eq!(entries.first(), Some(&bundled));
        assert!(entries.iter().any(|entry| entry.ends_with("existing")));
    }

    #[test]
    fn resolve_backend_root_prefers_checkout_when_available() {
        let checkout = TestDir::new();
        let resources = TestDir::new();
        touch(&checkout.path().join("src").join("jakal_flow").join("__init__.py"));
        touch(&resources.path().join("src").join("jakal_flow").join("__init__.py"));

        let resolved = resolve_backend_root(
            checkout.path(),
            &[resources.path().to_path_buf()],
            true,
        )
        .expect("backend root");

        assert_eq!(resolved, checkout.path().canonicalize().expect("canonical checkout"));
    }

    #[test]
    fn resolve_backend_root_prefers_bundled_resources_for_installed_launches() {
        let checkout = TestDir::new();
        let resources = TestDir::new();
        touch(&checkout.path().join("src").join("jakal_flow").join("__init__.py"));
        touch(
            &resources
                .path()
                .join("_up_")
                .join("_up_")
                .join("src")
                .join("jakal_flow")
                .join("__init__.py"),
        );

        let resolved = resolve_backend_root(
            checkout.path(),
            &[resources.path().to_path_buf()],
            false,
        )
        .expect("backend root");

        assert_eq!(
            resolved,
            resources
                .path()
                .join("_up_")
                .join("_up_")
                .canonicalize()
                .expect("canonical installed resources")
        );
    }

    #[test]
    fn resolve_backend_root_falls_back_to_bundled_resources() {
        let checkout = TestDir::new();
        let resources = TestDir::new();
        touch(&resources.path().join("src").join("jakal_flow").join("__init__.py"));

        let resolved = resolve_backend_root(
            checkout.path(),
            &[resources.path().to_path_buf()],
            false,
        )
        .expect("backend root");

        assert_eq!(resolved, resources.path().canonicalize().expect("canonical resources"));
    }

    #[test]
    fn resolve_backend_root_falls_back_to_nested_installed_resources() {
        let checkout = TestDir::new();
        let resources = TestDir::new();
        touch(
            &resources
                .path()
                .join("_up_")
                .join("_up_")
                .join("src")
                .join("jakal_flow")
                .join("__init__.py"),
        );

        let resolved = resolve_backend_root(
            checkout.path(),
            &[resources.path().to_path_buf()],
            false,
        )
        .expect("backend root");

        assert_eq!(
            resolved,
            resources
                .path()
                .join("_up_")
                .join("_up_")
                .canonicalize()
                .expect("canonical installed resources")
        );
    }

    #[test]
    fn bundled_runtime_root_finds_nested_installed_runtime() {
        let resources = TestDir::new();
        let bundled_runtime = resources.path().join("_up_").join("_up_").join(BUNDLED_RUNTIME_DIRNAME);
        fs::create_dir_all(&bundled_runtime).expect("create bundled runtime");

        let resolved = bundled_runtime_root(&[resources.path().to_path_buf()]).expect("runtime root");

        assert_eq!(resolved, bundled_runtime);
    }

    #[test]
    fn should_prefer_checkout_root_only_for_target_binaries() {
        let checkout = TestDir::new();
        let target_executable = checkout
            .path()
            .join("desktop")
            .join("src-tauri")
            .join("target")
            .join("release")
            .join("jakal-flow-desktop.exe");
        let installed_executable = checkout
            .path()
            .join(".artifacts")
            .join("msi_admin_extract")
            .join("PFiles")
            .join("jakal-flow Desktop")
            .join("jakal-flow-desktop.exe");
        touch(&target_executable);
        touch(&installed_executable);

        assert!(should_prefer_checkout_root(checkout.path(), Some(&target_executable)));
        assert!(!should_prefer_checkout_root(checkout.path(), Some(&installed_executable)));
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
    fn format_bridge_error_payload_wraps_object_error_with_prefix() {
        let payload = json!({
            "message": "Failed",
            "reason_code": "invalid_request",
        });
        let formatted = format_bridge_error_payload(&payload);
        assert!(
            formatted.starts_with("BRIDGE_ERROR_JSON:"),
            "formatted error payload should be prefixed as transport object"
        );
        let parsed = serde_json::from_str::<Value>(&formatted["BRIDGE_ERROR_JSON:".len()..]).unwrap();
        assert_eq!(parsed["reason_code"], "invalid_request");
    }

    #[test]
    fn format_bridge_error_payload_keeps_scalar_errors() {
        assert_eq!(format_bridge_error_payload(&json!("bridge request failed.")), "bridge request failed.");
        assert_eq!(format_bridge_error_payload(&Value::Null), "Python bridge request failed.");
        let array_payload = json!([1, 2, 3]);
        let formatted = format_bridge_error_payload(&array_payload);
        assert!(
            formatted.starts_with("BRIDGE_ERROR_JSON:"),
            "array payload should also be wrapped"
        );
    }

    #[test]
    fn normalize_workspace_root_rejects_embedded_nul() {
        let error = normalize_workspace_root(Some("bad\0path".to_string())).expect_err("expected error");

        assert!(error.contains("null character"));
    }
}
