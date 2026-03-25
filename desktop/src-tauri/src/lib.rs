use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::env;
use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};

#[derive(Clone, Debug, Serialize)]
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
    resolve_python_executable(root, env::var("CODEX_AUTO_PYTHON").ok())
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

fn parse_bridge_output(
    status_success: bool,
    stdout: &[u8],
    stderr: &[u8],
) -> Result<Value, String> {
    let stdout = String::from_utf8_lossy(stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(stderr).trim().to_string();

    if !status_success {
        let message = if stderr.is_empty() { stdout } else { stderr };
        return Err(message);
    }

    if stdout.is_empty() {
        return Ok(serde_json::json!({}));
    }

    serde_json::from_str(&stdout).map_err(|error| format!("Failed to parse bridge JSON: {error}"))
}

fn run_bridge_command(
    command: &str,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<Value, String> {
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
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
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
    drop(child.stdin.take());

    let output = child
        .wait_with_output()
        .map_err(|error| format!("Failed to wait for Python bridge: {error}"))?;
    parse_bridge_output(output.status.success(), &output.stdout, &output.stderr)
}

fn register_job_start(state: &AppState, command: &str) -> Result<JobSnapshot, String> {
    let mut jobs = state
        .jobs
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;
    if jobs.values().any(|job| job.status == "running") {
        return Err("Another background task is already running.".to_string());
    }

    let started_at = now_ms();
    let snapshot = JobSnapshot {
        id: format!("job-{}-{}", command, started_at),
        command: command.to_string(),
        status: "running".to_string(),
        error: None,
        result: None,
        updated_at_ms: started_at,
    };
    jobs.insert(snapshot.id.clone(), snapshot.clone());
    Ok(snapshot)
}

fn update_job_state(state: &AppState, job_id: &str, mutate: impl FnOnce(&mut JobSnapshot)) {
    if let Ok(mut jobs) = state.jobs.lock() {
        if let Some(job) = jobs.get_mut(job_id) {
            mutate(job);
            job.updated_at_ms = now_ms();
        }
    }
}

fn update_job<R: tauri::Runtime>(
    app: &AppHandle<R>,
    job_id: &str,
    mutate: impl FnOnce(&mut JobSnapshot),
) {
    let state = app.state::<AppState>();
    update_job_state(state.inner(), job_id, mutate);
}

fn get_job_snapshot(state: &AppState, job_id: &str) -> Option<JobSnapshot> {
    state
        .jobs
        .lock()
        .ok()
        .and_then(|jobs| jobs.get(job_id).cloned())
}

fn list_job_snapshots(state: &AppState) -> Vec<JobSnapshot> {
    state
        .jobs
        .lock()
        .map(|jobs| jobs.values().cloned().collect())
        .unwrap_or_default()
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
fn start_bridge_job<R: tauri::Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    command: String,
    payload: Option<Value>,
    workspace_root: Option<String>,
) -> Result<JobSnapshot, String> {
    let snapshot = register_job_start(state.inner(), &command)?;
    let job_id = snapshot.id.clone();

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
    get_job_snapshot(state.inner(), &job_id)
}

#[tauri::command]
fn list_bridge_jobs(state: State<'_, AppState>) -> Vec<JobSnapshot> {
    list_job_snapshots(state.inner())
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;

    static TEST_DIR_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TestDir {
        path: PathBuf,
    }

    impl TestDir {
        fn new() -> Self {
            let path = env::temp_dir().join(format!(
                "codex-auto-desktop-tests-{}-{}",
                std::process::id(),
                TEST_DIR_COUNTER.fetch_add(1, Ordering::Relaxed)
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

    fn sample_job(id: &str, command: &str, status: &str) -> JobSnapshot {
        JobSnapshot {
            id: id.to_string(),
            command: command.to_string(),
            status: status.to_string(),
            error: None,
            result: Some(json!({"ok": true, "command": command})),
            updated_at_ms: 123,
        }
    }

    fn insert_job(state: &AppState, job: JobSnapshot) {
        state
            .jobs
            .lock()
            .expect("lock app state")
            .insert(job.id.clone(), job);
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
    fn resolve_python_executable_falls_back_to_python() {
        let root = TestDir::new();

        let resolved = resolve_python_executable(root.path(), None);

        assert_eq!(resolved, "python");
    }

    #[test]
    fn build_pythonpath_places_src_first_and_preserves_existing_paths() {
        let root = TestDir::new();
        let existing_one = root.path().join("existing-one");
        let existing_two = root.path().join("existing-two");
        fs::create_dir_all(&existing_one).expect("create existing_one");
        fs::create_dir_all(&existing_two).expect("create existing_two");
        let existing =
            env::join_paths([existing_one.clone(), existing_two.clone()]).expect("join paths");

        let pythonpath = build_pythonpath(root.path(), Some(existing)).expect("build PYTHONPATH");
        let parts: Vec<PathBuf> = env::split_paths(&OsString::from(pythonpath)).collect();

        assert_eq!(
            parts,
            vec![root.path().join("src"), existing_one, existing_two]
        );
    }

    #[test]
    fn parse_bridge_output_returns_empty_object_for_blank_stdout() {
        let value = parse_bridge_output(true, b"  \n", b"").expect("parse empty output");

        assert_eq!(value, serde_json::json!({}));
    }

    #[test]
    fn parse_bridge_output_parses_json_payload() {
        let value =
            parse_bridge_output(true, br#"{"ok":true,"count":2}"#, b"").expect("parse JSON");

        assert_eq!(value, serde_json::json!({"ok": true, "count": 2}));
    }

    #[test]
    fn parse_bridge_output_uses_stderr_on_failure() {
        let error =
            parse_bridge_output(false, b"{\"ignored\":true}", b"bridge failed").expect_err("fail");

        assert_eq!(error, "bridge failed");
    }

    #[test]
    fn parse_bridge_output_falls_back_to_stdout_when_stderr_is_empty() {
        let error = parse_bridge_output(false, b"bridge failed on stdout", b"").expect_err("fail");

        assert_eq!(error, "bridge failed on stdout");
    }

    #[test]
    fn parse_bridge_output_reports_invalid_json() {
        let error = parse_bridge_output(true, b"{not-json}", b"").expect_err("invalid JSON");

        assert!(error.contains("Failed to parse bridge JSON"));
    }

    #[test]
    fn register_job_start_records_running_snapshot_for_command_state() {
        let state = AppState::default();

        let snapshot = register_job_start(&state, "bootstrap").expect("register running job");
        let stored = get_job_snapshot(&state, &snapshot.id).expect("stored job");

        assert!(snapshot.id.starts_with("job-bootstrap-"));
        assert_eq!(snapshot.command, "bootstrap");
        assert_eq!(snapshot.status, "running");
        assert_eq!(snapshot.error, None);
        assert_eq!(snapshot.result, None);
        assert_eq!(stored.id, snapshot.id);
        assert_eq!(stored.updated_at_ms, snapshot.updated_at_ms);
    }

    #[test]
    fn register_job_start_rejects_when_command_state_already_has_running_job() {
        let state = AppState::default();
        insert_job(&state, sample_job("job-running", "bootstrap", "running"));

        let error = register_job_start(&state, "list-projects").expect_err("reject second run");

        assert_eq!(error, "Another background task is already running.");
    }

    #[test]
    fn get_job_snapshot_returns_seeded_job_for_command_lookup() {
        let state = AppState::default();
        insert_job(&state, sample_job("job-one", "bootstrap", "completed"));

        let response = get_job_snapshot(&state, "job-one").expect("get job snapshot");

        assert_eq!(response.id, "job-one");
        assert_eq!(response.command, "bootstrap");
        assert_eq!(response.status, "completed");
        assert_eq!(
            response.result,
            Some(json!({"ok": true, "command": "bootstrap"}))
        );
    }

    #[test]
    fn get_job_snapshot_returns_none_for_unknown_job() {
        let state = AppState::default();

        let response = get_job_snapshot(&state, "missing-job");

        assert!(response.is_none());
    }

    #[test]
    fn list_job_snapshots_returns_all_jobs_for_command_listing() {
        let state = AppState::default();
        insert_job(&state, sample_job("job-b", "bootstrap", "completed"));
        insert_job(&state, sample_job("job-a", "list-projects", "failed"));

        let mut ids = list_job_snapshots(&state)
            .into_iter()
            .map(|job| job.id)
            .collect::<Vec<_>>();
        ids.sort();

        assert_eq!(ids, vec!["job-a".to_string(), "job-b".to_string()]);
    }

    #[test]
    fn update_job_state_applies_completion_result_for_command_state() {
        let state = AppState::default();
        let snapshot = register_job_start(&state, "bootstrap").expect("register running job");

        while now_ms() <= snapshot.updated_at_ms {
            std::thread::sleep(Duration::from_millis(1));
        }

        update_job_state(&state, &snapshot.id, |job| {
            job.status = "completed".to_string();
            job.result = Some(json!({"workspace_root": "temp-workspace"}));
            job.error = None;
        });

        let updated = get_job_snapshot(&state, &snapshot.id).expect("updated job");
        assert_eq!(updated.status, "completed");
        assert_eq!(updated.error, None);
        assert_eq!(
            updated.result,
            Some(json!({"workspace_root": "temp-workspace"}))
        );
        assert!(updated.updated_at_ms > snapshot.updated_at_ms);
    }
}
