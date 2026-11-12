//! Bridge to the ModularCV Python engine.
//!
//! The only operation exposed is `facts_check`, which runs the real CLI
//! (`python -m modularcv facts check --root <workspace>`). No validation rule is
//! re-implemented here. The interpreter is launched without a shell, with a
//! timeout, and its output is parsed into a typed result. Nothing is logged:
//! workspace paths and diagnostics never leave the returned object.
//!
//! `EngineLauncher` isolates how the engine is started. In a packaged application the engine is the embedded
//! sidecar (`mcv-engine.exe`, a PyInstaller build of the unchanged engine and adapter) found in the
//! application's resource folder; in development it is the Python interpreter running the repository. A
//! release build never falls back to a system Python.

use serde::{Deserialize, Serialize};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_OUTPUT: u64 = 4 * 1024 * 1024;

/// The single operation the front end may request.
pub const OP_FACTS_CHECK: &str = "facts_check";

#[derive(Debug, Clone)]
pub struct EngineLauncher {
    /// Program and leading arguments, e.g. `["python"]` or `["py", "-3.14"]`.
    pub interpreter: Vec<String>,
    /// Directory containing the `modularcv` package (dev: the repository root; packaged: the resource folder,
    /// which holds `examples/workspace`).
    pub engine_dir: PathBuf,
    pub timeout: Duration,
    /// The embedded engine executable, when there is one. It takes precedence over any Python.
    pub sidecar: Option<PathBuf>,
}

/// Name of the embedded engine inside `<resources>/engine/`.
pub const SIDECAR_NAME: &str = "mcv-engine.exe";

/// How the engine will be started, decided from the launcher alone.
enum Backend {
    Sidecar(PathBuf),
    Python(Vec<String>),
}

/// The embedded engine inside the application's resource folder, if it is there.
pub fn find_sidecar(resource_dir: Option<&Path>) -> Option<PathBuf> {
    find_sidecar_with(std::env::var_os("MODULARCV_SIDECAR").map(PathBuf::from), resource_dir)
}

fn find_sidecar_with(override_path: Option<PathBuf>, resource_dir: Option<&Path>) -> Option<PathBuf> {
    if let Some(p) = override_path.filter(|p| p.is_file()) {
        return Some(p);
    }
    let candidate = resource_dir?.join("engine").join(SIDECAR_NAME);
    candidate.is_file().then_some(candidate)
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct Diagnostic {
    pub code: String,
    pub line: Option<u32>,
    pub message: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct FactsReport {
    pub status: String,
    pub file: String,
    pub fact_count: Option<u32>,
    pub counts: Option<std::collections::BTreeMap<String, u32>>,
    pub publishable: Option<u32>,
    pub facts_source_sha256: Option<String>,
    pub factbase_sha256: Option<String>,
    #[serde(default)]
    pub errors: Vec<Diagnostic>,
    #[serde(default)]
    pub warnings: Vec<Diagnostic>,
}

/// Outcome category returned to React. `valid` is the only success.
#[derive(Debug, Serialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Valid,
    Invalid,
    ConfigError,
    WorkspaceMissing,
    OperationNotAllowed,
    PythonUnavailable,
    EngineNotFound,
    Timeout,
    ProcessFailed,
    InvalidOutput,
}

#[derive(Debug, Serialize, Clone)]
pub struct ValidationResult {
    pub outcome: Outcome,
    pub exit_code: Option<i32>,
    pub report: Option<FactsReport>,
    /// Short human-readable detail (never contains fact text).
    pub detail: Option<String>,
    /// First stderr lines from the engine (diagnostic codes and messages).
    pub stderr_excerpt: Option<String>,
    pub duration_ms: u64,
}

impl ValidationResult {
    fn fail(outcome: Outcome, detail: impl Into<String>, started: Instant) -> Self {
        ValidationResult {
            outcome,
            exit_code: None,
            report: None,
            detail: Some(detail.into()),
            stderr_excerpt: None,
            duration_ms: started.elapsed().as_millis() as u64,
        }
    }
}

struct RawRun {
    exit_code: Option<i32>,
    stdout: String,
    stderr: String,
    timed_out: bool,
}

fn run_process(
    program: &str,
    args: &[String],
    cwd: &Path,
    envs: &[(&str, String)],
    stdin: Option<Vec<u8>>,
    timeout: Duration,
) -> std::io::Result<RawRun> {
    let mut cmd = Command::new(program);
    cmd.args(args)
        .current_dir(cwd)
        .stdin(if stdin.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1");
    for (k, v) in envs {
        cmd.env(k, v);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut child = cmd.spawn()?;
    if let (Some(data), Some(mut pipe)) = (stdin, child.stdin.take()) {
        std::thread::spawn(move || {
            use std::io::Write;
            let _ = pipe.write_all(&data);
        });
    }
    let mut out = child.stdout.take().expect("piped stdout");
    let mut err = child.stderr.take().expect("piped stderr");
    let t_out = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = (&mut out).take(MAX_OUTPUT).read_to_end(&mut buf);
        buf
    });
    let t_err = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = (&mut err).take(MAX_OUTPUT).read_to_end(&mut buf);
        buf
    });
    let deadline = Instant::now() + timeout;
    let mut timed_out = false;
    let status = loop {
        match child.try_wait()? {
            Some(s) => break Some(s),
            None if Instant::now() >= deadline => {
                timed_out = true;
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
            None => std::thread::sleep(Duration::from_millis(20)),
        }
    };
    let stdout = String::from_utf8_lossy(&t_out.join().unwrap_or_default()).into_owned();
    let stderr = String::from_utf8_lossy(&t_err.join().unwrap_or_default()).into_owned();
    Ok(RawRun {
        exit_code: status.and_then(|s| s.code()),
        stdout,
        stderr,
        timed_out,
    })
}

/// True when `text` ("Python 3.14.1") is a supported interpreter (3.12 to 3.14).
pub fn python_version_supported(text: &str) -> bool {
    let v = text.trim().trim_start_matches("Python").trim();
    let mut it = v.split('.');
    let major: u32 = it.next().and_then(|x| x.parse().ok()).unwrap_or(0);
    let minor: u32 = it.next().and_then(|x| x.parse().ok()).unwrap_or(0);
    major == 3 && (12..=14).contains(&minor)
}

/// Where the development engine lives. Only debug builds know the checkout; a release build embeds no
/// build-machine path (the packaged engine is found through the application resources instead).
#[cfg(debug_assertions)]
fn default_engine_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

#[cfg(not(debug_assertions))]
fn default_engine_dir() -> PathBuf {
    PathBuf::new()
}

impl EngineLauncher {
    /// Development launcher: `MODULARCV_PYTHON` override, else common launchers.
    pub fn from_env() -> Self {
        let engine_dir = std::env::var_os("MODULARCV_ENGINE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(default_engine_dir);
        let interpreter = match std::env::var("MODULARCV_PYTHON") {
            Ok(p) if !p.trim().is_empty() => vec![p],
            _ => Vec::new(),
        };
        EngineLauncher {
            interpreter,
            engine_dir,
            timeout: DEFAULT_TIMEOUT,
            sidecar: None,
        }
    }

    /// Launcher of the running application: the embedded engine when the resource folder holds it (packaged
    /// application), the development interpreter otherwise (debug builds only).
    pub fn for_app(resource_dir: Option<&Path>) -> Self {
        let mut launcher = Self::from_env();
        launcher.sidecar = find_sidecar(resource_dir);
        if let (Some(_), Some(dir)) = (&launcher.sidecar, resource_dir) {
            launcher.engine_dir = dir.to_path_buf();
        }
        launcher
    }

    /// `Ok` with the way to start the engine, or a stable code and a short message. A release build without the
    /// embedded engine is an error: it never silently uses whatever Python is installed.
    fn backend(&self) -> Result<Backend, (&'static str, String)> {
        if let Some(path) = &self.sidecar {
            return Ok(Backend::Sidecar(path.clone()));
        }
        if !cfg!(debug_assertions) {
            return Err(("ENGINE_NOT_FOUND", "The embedded ModularCV engine was not found in this installation.".into()));
        }
        if !self.engine_dir.join("modularcv").join("__main__.py").is_file() {
            return Err(("ENGINE_NOT_FOUND", "The ModularCV engine package was not found (set MODULARCV_ENGINE_DIR).".into()));
        }
        self.find_python().map(Backend::Python).map_err(|e| ("PYTHON_UNAVAILABLE", e))
    }

    fn candidates(&self) -> Vec<Vec<String>> {
        if !self.interpreter.is_empty() {
            return vec![self.interpreter.clone()];
        }
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        vec![
            s(&["python"]),
            s(&["python3"]),
            s(&["py", "-3.14"]),
            s(&["py", "-3.13"]),
            s(&["py", "-3.12"]),
        ]
    }

    /// First candidate that runs and reports a supported version.
    fn find_python(&self) -> Result<Vec<String>, String> {
        let mut seen = Vec::new();
        for cand in self.candidates() {
            let args: Vec<String> = cand[1..]
                .iter()
                .cloned()
                .chain(std::iter::once("--version".to_string()))
                .collect();
            match run_process(&cand[0], &args, &self.engine_dir, &[], None, Duration::from_secs(10)) {
                Ok(r) if r.exit_code == Some(0) => {
                    let text = if r.stdout.trim().is_empty() { &r.stderr } else { &r.stdout };
                    if python_version_supported(text) {
                        return Ok(cand);
                    }
                    seen.push(format!("{} ({})", cand.join(" "), text.trim()));
                }
                _ => {}
            }
        }
        if seen.is_empty() {
            Err("No Python interpreter found (3.12 to 3.14 required).".into())
        } else {
            Err(format!(
                "No supported Python found (3.12 to 3.14 required). Found: {}",
                seen.join(", ")
            ))
        }
    }

    /// Run `facts check` on `workspace` for an allowed `operation`.
    pub fn validate(&self, operation: &str, workspace: &str) -> ValidationResult {
        let started = Instant::now();
        if operation != OP_FACTS_CHECK {
            return ValidationResult::fail(
                Outcome::OperationNotAllowed,
                "Only the facts_check operation is allowed.",
                started,
            );
        }
        let ws = Path::new(workspace.trim());
        if workspace.trim().is_empty() || !ws.is_dir() {
            return ValidationResult::fail(
                Outcome::WorkspaceMissing,
                "The workspace folder does not exist or is not a directory.",
                started,
            );
        }
        let (program, args, envs, cwd): (String, Vec<String>, Vec<(&str, String)>, PathBuf) = match self.backend() {
            Ok(Backend::Sidecar(path)) => {
                let cwd = path.parent().map(Path::to_path_buf).unwrap_or_else(std::env::temp_dir);
                let mut args: Vec<String> = ["cli", "facts", "check", "--root"].iter().map(|s| s.to_string()).collect();
                args.push(ws.to_string_lossy().into_owned());
                (path.to_string_lossy().into_owned(), args, Vec::new(), cwd)
            }
            Ok(Backend::Python(python)) => {
                let mut args: Vec<String> = python[1..].to_vec();
                args.extend(["-m", "modularcv", "facts", "check", "--root"].iter().map(|s| s.to_string()));
                args.push(ws.to_string_lossy().into_owned());
                (python[0].clone(), args, vec![("PYTHONPATH", self.engine_dir.to_string_lossy().into_owned())], self.engine_dir.clone())
            }
            Err((code, message)) => {
                let outcome = if code == "PYTHON_UNAVAILABLE" { Outcome::PythonUnavailable } else { Outcome::EngineNotFound };
                return ValidationResult::fail(outcome, message, started);
            }
        };
        let run = match run_process(&program, &args, &cwd, &envs, None, self.timeout) {
            Ok(r) => r,
            Err(e) => {
                return ValidationResult::fail(Outcome::ProcessFailed, format!("Could not start the engine: {}", e.kind()), started)
            }
        };
        interpret(run, started)
    }
}

fn excerpt(stderr: &str) -> Option<String> {
    let lines: Vec<&str> = stderr
        .lines()
        .filter(|l| !l.trim().is_empty())
        .take_while(|l| !l.trim_start().starts_with('{'))
        .take(8)
        .collect();
    if lines.is_empty() {
        None
    } else {
        Some(lines.join("\n"))
    }
}

/// Parse a JSON object from `text`: whole text, else from the first `{` line.
fn parse_json(text: &str) -> Option<serde_json::Value> {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(text.trim()) {
        return Some(v);
    }
    let idx = text
        .match_indices('{')
        .map(|(i, _)| i)
        .find(|&i| i == 0 || text.as_bytes()[i - 1] == b'\n')?;
    serde_json::from_str(text[idx..].trim()).ok()
}

fn interpret(run: RawRun, started: Instant) -> ValidationResult {
    let ms = started.elapsed().as_millis() as u64;
    let mk = |outcome, detail: Option<String>, report| ValidationResult {
        outcome,
        exit_code: run.exit_code,
        report,
        detail,
        stderr_excerpt: excerpt(&run.stderr),
        duration_ms: ms,
    };
    if run.timed_out {
        return mk(Outcome::Timeout, Some("The engine did not finish in time and was stopped.".into()), None);
    }
    let Some(code) = run.exit_code else {
        return mk(Outcome::ProcessFailed, Some("The engine was terminated abnormally.".into()), None);
    };
    match code {
        0 | 1 => {
            let report: Option<FactsReport> = serde_json::from_str(run.stdout.trim()).ok();
            let Some(report) = report else {
                return mk(Outcome::InvalidOutput, Some("The engine returned output that is not the expected JSON.".into()), None);
            };
            // Fail closed: exit code and reported status must agree.
            match (code, report.status.as_str(), report.errors.is_empty()) {
                (0, "OK", true) => mk(Outcome::Valid, None, Some(report)),
                (1, "INVALID", false) => mk(Outcome::Invalid, None, Some(report)),
                _ => mk(
                    Outcome::InvalidOutput,
                    Some("Exit code and reported status disagree; result rejected.".into()),
                    None,
                ),
            }
        }
        2 => {
            let v = parse_json(&run.stderr).or_else(|| parse_json(&run.stdout));
            let detail = v
                .as_ref()
                .and_then(|v| v.get("detail"))
                .and_then(|d| d.as_str())
                .map(str::to_owned)
                .or_else(|| Some("The engine could not read the workspace or its fact file.".into()));
            let report = v.and_then(|v| serde_json::from_value::<FactsReport>(v).ok());
            mk(Outcome::ConfigError, detail, report)
        }
        n => mk(Outcome::ProcessFailed, Some(format!("The engine exited with unexpected code {n}.")), None),
    }
}

// ---------------------------------------------------------------- structured adapter

/// Closed list of adapter operations the front end may trigger. The Python
/// adapter re-checks the name; nothing here forwards a command line.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdapterOp {
    Read,
    SaveFact,
    SaveProfile,
    OffersList,
    OfferRead,
    OfferSave,
    OfferDelete,
    OfferImport,
    AdaptOptions,
    Matrix,
    Plan,
    PlansList,
    PlanRead,
    Provenance,
    Assemble,
    LatexStatus,
    Render,
    OutputsList,
    PackageCreate,
    PackagesList,
    PackageReview,
    PackageStatus,
    PdfRead,
    PackageApprove,
}

impl AdapterOp {
    pub fn name(self) -> &'static str {
        match self {
            AdapterOp::Read => "read",
            AdapterOp::SaveFact => "save_fact",
            AdapterOp::SaveProfile => "save_profile",
            AdapterOp::OffersList => "offers_list",
            AdapterOp::OfferRead => "offer_read",
            AdapterOp::OfferSave => "offer_save",
            AdapterOp::OfferDelete => "offer_delete",
            AdapterOp::OfferImport => "offer_import",
            AdapterOp::AdaptOptions => "adapt_options",
            AdapterOp::Matrix => "matrix",
            AdapterOp::Plan => "plan",
            AdapterOp::PlansList => "plans_list",
            AdapterOp::PlanRead => "plan_read",
            AdapterOp::Provenance => "provenance",
            AdapterOp::Assemble => "assemble",
            AdapterOp::LatexStatus => "latex_status",
            AdapterOp::Render => "render",
            AdapterOp::OutputsList => "outputs_list",
            AdapterOp::PackageCreate => "package_create",
            AdapterOp::PackagesList => "packages_list",
            AdapterOp::PackageReview => "package_review",
            AdapterOp::PackageStatus => "package_status",
            AdapterOp::PdfRead => "pdf_read",
            AdapterOp::PackageApprove => "package_approve",
        }
    }

    /// The only way a name coming from the front end becomes an operation.
    pub fn from_name(name: &str) -> Option<AdapterOp> {
        const ALL: [AdapterOp; 24] = [
            AdapterOp::Read,
            AdapterOp::SaveFact,
            AdapterOp::SaveProfile,
            AdapterOp::OffersList,
            AdapterOp::OfferRead,
            AdapterOp::OfferSave,
            AdapterOp::OfferDelete,
            AdapterOp::OfferImport,
            AdapterOp::AdaptOptions,
            AdapterOp::Matrix,
            AdapterOp::Plan,
            AdapterOp::PlansList,
            AdapterOp::PlanRead,
            AdapterOp::Provenance,
            AdapterOp::Assemble,
            AdapterOp::LatexStatus,
            AdapterOp::Render,
            AdapterOp::OutputsList,
            AdapterOp::PackageCreate,
            AdapterOp::PackagesList,
            AdapterOp::PackageReview,
            AdapterOp::PackageStatus,
            AdapterOp::PdfRead,
            AdapterOp::PackageApprove,
        ];
        ALL.iter().copied().find(|op| op.name() == name)
    }

    /// Longest an operation may run before it is stopped (PDF compilation is the slow one).
    fn timeout(self, default: Duration) -> Duration {
        match self {
            AdapterOp::Render | AdapterOp::PackageCreate => Duration::from_secs(180),
            AdapterOp::PackagesList => Duration::from_secs(120),
            AdapterOp::PackageReview | AdapterOp::PackageStatus | AdapterOp::PackageApprove => default.max(Duration::from_secs(60)),
            AdapterOp::Plan | AdapterOp::Matrix | AdapterOp::Assemble => default.max(Duration::from_secs(60)),
            _ => default,
        }
    }
}

const MAX_REQUEST: usize = 1024 * 1024;

type Command4 = (String, Vec<String>, Vec<(&'static str, String)>, PathBuf);

impl EngineLauncher {
    /// Program, arguments, environment and working directory for one of the two fixed scripts
    /// (`adapter.py` or `diag.py`) of the Python adapter, or the matching mode of the embedded engine.
    fn command(&self, backend: Backend, script: &str, extra: &[String]) -> Result<Command4, (&'static str, String)> {
        match backend {
            Backend::Sidecar(path) => {
                let mode = if script == "adapter.py" { "adapter" } else { "diagnose" };
                let mut args = vec![mode.to_string()];
                args.extend(extra.iter().cloned());
                let cwd = path.parent().map(Path::to_path_buf).unwrap_or_else(std::env::temp_dir);
                Ok((path.to_string_lossy().into_owned(), args, Vec::new(), cwd))
            }
            Backend::Python(python) => {
                let file = if script == "adapter.py" { "mcv_adapter.py" } else { "mcv_diag.py" };
                let path = self.engine_dir.join("desktop").join("adapter").join(file);
                if !path.is_file() {
                    return Err(("ENGINE_NOT_FOUND", "The ModularCV engine or the desktop adapter was not found.".into()));
                }
                let mut args: Vec<String> = python[1..].to_vec();
                args.push("-I".into());
                args.push(path.to_string_lossy().into_owned());
                args.extend(extra.iter().cloned());
                Ok((python[0].clone(), args, vec![("MODULARCV_ENGINE_DIR", self.engine_dir.to_string_lossy().into_owned())], self.engine_dir.clone()))
            }
        }
    }

    /// Environment diagnostics (embedded engine, Git, provenance, LaTeX). Always an object with `ok`; the mode of the
    /// launcher is added so the screen can say which engine answered.
    pub fn diagnose(&self, workspace: Option<&str>) -> serde_json::Value {
        let backend = match self.backend() {
            Ok(b) => b,
            Err((code, message)) => return adapter_error(code, &message),
        };
        let mode = if matches!(backend, Backend::Sidecar(_)) { "embedded" } else { "development" };
        let extra: Vec<String> = match workspace {
            Some(w) if !w.trim().is_empty() && Path::new(w.trim()).is_dir() => vec!["--root".into(), w.trim().into()],
            _ => Vec::new(),
        };
        let (program, args, envs, cwd) = match self.command(backend, "diag.py", &extra) {
            Ok(c) => c,
            Err((code, message)) => return adapter_error(code, &message),
        };
        let run = match run_process(&program, &args, &cwd, &envs, None, Duration::from_secs(60)) {
            Ok(r) => r,
            Err(_) => return adapter_error("PROCESS_FAILED", "Could not start the engine."),
        };
        if run.timed_out {
            return adapter_error("TIMEOUT", "The diagnostics did not answer in time and were stopped.");
        }
        match serde_json::from_str::<serde_json::Value>(run.stdout.trim()) {
            Ok(mut v) if v.is_object() && v.get("ok") == Some(&serde_json::Value::Bool(true)) && run.exit_code == Some(0) => {
                v["mode"] = mode.into();
                v
            }
            _ => adapter_error("INVALID_OUTPUT", "The engine returned an unreadable answer; nothing was assumed."),
        }
    }
}

fn adapter_error(code: &str, message: &str) -> serde_json::Value {
    serde_json::json!({"ok": false, "code": code, "message": message, "details": []})
}

impl EngineLauncher {
    /// Run one adapter operation. `payload` holds the operation's fields (no `op`, no `root`).
    /// Always returns a JSON object with `ok`; failures to start are reported with stable codes.
    pub fn adapter(&self, op: AdapterOp, workspace: &str, payload: serde_json::Value) -> serde_json::Value {
        let ws = Path::new(workspace.trim());
        if workspace.trim().is_empty() || !ws.is_dir() {
            return adapter_error("WORKSPACE_MISSING", "The workspace folder does not exist or is not a directory.");
        }
        let serde_json::Value::Object(mut request) = payload else {
            return adapter_error("BAD_REQUEST", "The request must be an object.");
        };
        request.remove("op");
        request.insert("op".into(), op.name().into());
        request.insert("root".into(), ws.to_string_lossy().as_ref().into());
        let body = serde_json::to_vec(&serde_json::Value::Object(request)).unwrap_or_default();
        if body.len() > MAX_REQUEST {
            return adapter_error("BAD_REQUEST", "The request is too large.");
        }
        let backend = match self.backend() {
            Ok(b) => b,
            Err((code, message)) => return adapter_error(code, &message),
        };
        let (program, args, envs, cwd) = match self.command(backend, "adapter.py", &[]) {
            Ok(c) => c,
            Err((code, message)) => return adapter_error(code, &message),
        };
        let run = match run_process(&program, &args, &cwd, &envs, Some(body), op.timeout(self.timeout)) {
            Ok(r) => r,
            Err(_) => return adapter_error("PROCESS_FAILED", "Could not start the engine adapter."),
        };
        if run.timed_out {
            return adapter_error("TIMEOUT", "The engine did not answer in time and was stopped.");
        }
        match serde_json::from_str::<serde_json::Value>(run.stdout.trim()) {
            Ok(v) if v.is_object() && v.get("ok").is_some() && run.exit_code == Some(0) => v,
            _ => adapter_error("INVALID_OUTPUT", "The engine adapter returned an unreadable answer; nothing was assumed."),
        }
    }
}

// ---------------------------------------------------------------- demo workspace

#[derive(Debug, Serialize, Clone)]
pub struct DemoWorkspace {
    pub path: String,
    /// False when the folder already existed and was left untouched.
    pub created: bool,
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let to = dst.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &to)?;
        } else {
            std::fs::copy(entry.path(), to)?;
        }
    }
    Ok(())
}

/// Content of the deliberately broken demo fact file (no real data).
pub const INVALID_FACTS: &str = "<!-- modularcv: FactBase-v1 -->\n\n# Broken demo\n\n- [demo.broken] NOT_A_STATUS: This line uses an unknown status.\n";

/// Fixed identity of the commit made in the *test* Git workspace. It never touches the user's Git configuration.
const GIT_TEST_IDENTITY: [&str; 4] = ["-c", "user.name=ModularCV test", "-c", "user.email=test"];

/// Copy the public example workspace into `target` and make it an independent Git repository with one explicit test
/// commit of the fictional sources. Reserved for tests and demonstrations: it only ever runs on a folder that does not exist
/// yet, inside the app data folder, and never on a user's own workspace. Never overwrites.
pub fn ensure_git_demo_workspace(engine_dir: &Path, target: &Path) -> Result<DemoWorkspace, String> {
    if target.exists() {
        return Ok(DemoWorkspace { path: target.to_string_lossy().into_owned(), created: false });
    }
    let git_ok = std::process::Command::new("git").arg("--version").output().map(|o| o.status.success()).unwrap_or(false);
    if !git_ok {
        return Err("Git was not found on PATH: the Git demo workspace cannot be prepared.".into());
    }
    let made = ensure_demo_workspace(engine_dir, target, false)?;
    let run = |args: &[&str]| -> Result<(), String> {
        let status = std::process::Command::new("git")
            .args(GIT_TEST_IDENTITY)
            .args(args)
            .current_dir(target)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map_err(|_| "Could not start Git.".to_string())?;
        if status.success() { Ok(()) } else { Err("A Git step of the demo workspace failed.".to_string()) }
    };
    let result = run(&["init", "-q"]).and_then(|_| run(&["add", "-A"])).and_then(|_| run(&["commit", "-q", "-m", "fictional test sources"]));
    if let Err(e) = result {
        let _ = std::fs::remove_dir_all(target);
        return Err(e);
    }
    Ok(made)
}

/// Copy the public example workspace into `target`. Never overwrites: an
/// existing folder is reused as is.
pub fn ensure_demo_workspace(engine_dir: &Path, target: &Path, invalid: bool) -> Result<DemoWorkspace, String> {
    if target.exists() {
        return Ok(DemoWorkspace { path: target.to_string_lossy().into_owned(), created: false });
    }
    let src = engine_dir.join("examples").join("workspace");
    if !src.is_dir() {
        return Err("The public example workspace was not found in the engine folder.".into());
    }
    copy_dir(&src, target).map_err(|e| format!("Could not create the demo workspace: {}", e.kind()))?;
    if invalid {
        std::fs::write(target.join("facts.md"), INVALID_FACTS)
            .map_err(|e| format!("Could not write the demo facts file: {}", e.kind()))?;
    }
    Ok(DemoWorkspace { path: target.to_string_lossy().into_owned(), created: true })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
    }

    fn launcher() -> EngineLauncher {
        EngineLauncher::from_env()
    }

    fn demo(invalid: bool) -> (tempfile::TempDir, String) {
        let tmp = tempfile::tempdir().unwrap();
        let target = tmp.path().join("ws");
        ensure_demo_workspace(&repo_root(), &target, invalid).unwrap();
        let p = target.to_string_lossy().into_owned();
        (tmp, p)
    }

    #[test]
    fn valid_workspace_is_validated_by_real_engine() {
        let (_t, ws) = demo(false);
        let r = launcher().validate(OP_FACTS_CHECK, &ws);
        assert_eq!(r.outcome, Outcome::Valid, "{:?}", r);
        assert_eq!(r.exit_code, Some(0));
        let rep = r.report.unwrap();
        assert_eq!(rep.status, "OK");
        assert_eq!(rep.fact_count, Some(9));
        assert!(rep.errors.is_empty());
    }

    #[test]
    fn invalid_facts_are_refused() {
        let (_t, ws) = demo(true);
        let r = launcher().validate(OP_FACTS_CHECK, &ws);
        assert_eq!(r.outcome, Outcome::Invalid, "{:?}", r);
        assert_eq!(r.exit_code, Some(1));
        assert!(!r.report.unwrap().errors.is_empty());
    }

    #[test]
    fn missing_workspace() {
        let r = launcher().validate(OP_FACTS_CHECK, "Z:\\definitely\\not\\here");
        assert_eq!(r.outcome, Outcome::WorkspaceMissing);
    }

    #[test]
    fn empty_directory_is_a_config_or_process_error_not_success() {
        let tmp = tempfile::tempdir().unwrap();
        let r = launcher().validate(OP_FACTS_CHECK, &tmp.path().to_string_lossy());
        assert_ne!(r.outcome, Outcome::Valid, "{:?}", r);
        assert_eq!(r.outcome, Outcome::ConfigError, "{:?}", r);
        assert_eq!(r.exit_code, Some(2));
    }

    #[test]
    fn operation_not_allowed() {
        let r = launcher().validate("facts_import", ".");
        assert_eq!(r.outcome, Outcome::OperationNotAllowed);
    }

    #[test]
    fn python_unavailable() {
        let mut l = launcher();
        l.interpreter = vec!["no-such-python-binary-xyz".into()];
        let (_t, ws) = demo(false);
        let r = l.validate(OP_FACTS_CHECK, &ws);
        assert_eq!(r.outcome, Outcome::PythonUnavailable);
    }

    #[test]
    fn engine_not_found() {
        let mut l = launcher();
        let tmp = tempfile::tempdir().unwrap();
        l.engine_dir = tmp.path().to_path_buf();
        let (_t, ws) = demo(false);
        assert_eq!(l.validate(OP_FACTS_CHECK, &ws).outcome, Outcome::EngineNotFound);
    }

    #[test]
    fn version_filter() {
        assert!(python_version_supported("Python 3.12.1"));
        assert!(python_version_supported("Python 3.14.10\n"));
        assert!(!python_version_supported("Python 3.11.9"));
        assert!(!python_version_supported("Python 3.15.0"));
        assert!(!python_version_supported("Python 2.7"));
        assert!(!python_version_supported("garbage"));
    }

    fn raw(code: Option<i32>, out: &str, err: &str, timed_out: bool) -> RawRun {
        RawRun { exit_code: code, stdout: out.into(), stderr: err.into(), timed_out }
    }

    #[test]
    fn interpret_error_paths() {
        let s = Instant::now();
        assert_eq!(interpret(raw(Some(0), "not json", "", false), s).outcome, Outcome::InvalidOutput);
        assert_eq!(interpret(raw(Some(0), "", "", false), s).outcome, Outcome::InvalidOutput);
        assert_eq!(interpret(raw(Some(7), "", "boom", false), s).outcome, Outcome::ProcessFailed);
        assert_eq!(interpret(raw(None, "", "", false), s).outcome, Outcome::ProcessFailed);
        assert_eq!(interpret(raw(None, "", "", true), s).outcome, Outcome::Timeout);
        // exit 0 but status INVALID must never be a success
        let bad = r#"{"status":"INVALID","file":"f","errors":[{"code":"X","line":1,"message":"m"}],"warnings":[]}"#;
        assert_eq!(interpret(raw(Some(0), bad, "", false), s).outcome, Outcome::InvalidOutput);
        // exit 1 but status OK
        let ok = r#"{"status":"OK","file":"f","errors":[],"warnings":[]}"#;
        assert_eq!(interpret(raw(Some(1), ok, "", false), s).outcome, Outcome::InvalidOutput);
        // config error JSON on stderr
        let r = interpret(raw(Some(2), "", "{\"status\":\"CONFIG_ERROR\",\"detail\":\"bad root\"}", false), s);
        assert_eq!(r.outcome, Outcome::ConfigError);
        assert_eq!(r.detail.as_deref(), Some("bad root"));
    }

    #[test]
    fn timeout_kills_process() {
        let l = launcher();
        let py = l.find_python().unwrap();
        let args: Vec<String> = py[1..].iter().cloned().chain(["-c".to_string(), "import time; time.sleep(30)".to_string()]).collect();
        let t = Instant::now();
        let r = run_process(&py[0], &args, &l.engine_dir, &[], None, Duration::from_millis(400)).unwrap();
        assert!(r.timed_out);
        assert!(t.elapsed() < Duration::from_secs(10));
    }

    #[test]
    fn demo_workspace_never_overwrites() {
        let tmp = tempfile::tempdir().unwrap();
        let target = tmp.path().join("ws");
        std::fs::create_dir(&target).unwrap();
        std::fs::write(target.join("keep.txt"), "mine").unwrap();
        let d = ensure_demo_workspace(&repo_root(), &target, true).unwrap();
        assert!(!d.created);
        assert_eq!(std::fs::read_to_string(target.join("keep.txt")).unwrap(), "mine");
        assert!(!target.join("facts.md").exists());
    }

    #[test]
    fn adapter_reads_and_edits_through_real_engine() {
        let (_t, ws) = demo(false);
        let l = launcher();
        let state = l.adapter(AdapterOp::Read, &ws, serde_json::json!({}));
        assert_eq!(state["ok"], true, "{state}");
        assert_eq!(state["facts"]["valid"], true);
        let sha = state["facts"]["source_sha256"].clone();
        let bad = l.adapter(AdapterOp::SaveFact, &ws, serde_json::json!({
            "expected_sha256": sha, "mode": "update",
            "fact": {"id": "exp.junior-dev.speed", "status": "CONFIRMED", "text": "Improved."}
        }));
        assert_eq!(bad["ok"], false);
        assert_eq!(bad["code"], "CONFIRMATION_REQUIRED");
        let stale = l.adapter(AdapterOp::SaveFact, &ws, serde_json::json!({
            "expected_sha256": "0000", "mode": "update",
            "fact": {"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "text": "Improved."}
        }));
        assert_eq!(stale["code"], "CONFLICT");
        let ok = l.adapter(AdapterOp::SaveFact, &ws, serde_json::json!({
            "expected_sha256": sha, "mode": "update",
            "fact": {"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "text": "Improved, unmeasured."}
        }));
        assert_eq!(ok["ok"], true, "{ok}");
    }

    #[test]
    fn adapter_error_paths() {
        let l = launcher();
        assert_eq!(l.adapter(AdapterOp::Read, "Z:\\nope", serde_json::json!({}))["code"], "WORKSPACE_MISSING");
        let (_t, ws) = demo(false);
        let mut no_py = launcher();
        no_py.interpreter = vec!["no-such-python-binary-xyz".into()];
        assert_eq!(no_py.adapter(AdapterOp::Read, &ws, serde_json::json!({}))["code"], "PYTHON_UNAVAILABLE");
        assert_eq!(l.adapter(AdapterOp::Read, &ws, serde_json::json!("not an object"))["code"], "BAD_REQUEST");
        let mut lost = launcher();
        let tmp = tempfile::tempdir().unwrap();
        lost.engine_dir = tmp.path().to_path_buf();
        assert_eq!(lost.adapter(AdapterOp::Read, &ws, serde_json::json!({}))["code"], "ENGINE_NOT_FOUND");
    }

    #[test]
    fn only_listed_operations_resolve() {
        assert_eq!(AdapterOp::from_name("render"), Some(AdapterOp::Render));
        assert_eq!(AdapterOp::from_name("offer_delete"), Some(AdapterOp::OfferDelete));
        for bad in ["", "run_shell", "RENDER", "render ", "../render", "python", "cmd /c dir"] {
            assert_eq!(AdapterOp::from_name(bad), None, "{bad}");
        }
    }

    #[test]
    fn adapter_runs_offer_and_plan_operations() {
        let (_t, ws) = demo(false);
        let l = launcher();
        let list = l.adapter(AdapterOp::OffersList, &ws, serde_json::json!({}));
        assert_eq!(list["ok"], true, "{list}");
        assert!(list["offers"].as_array().unwrap().len() >= 2);
        let plan = l.adapter(AdapterOp::Plan, &ws, serde_json::json!({"offer_file": "backend-intern.json", "write": true}));
        assert_eq!(plan["ok"], true, "{plan}");
        let file = plan["written"]["file"].as_str().unwrap().to_string();
        let tex = l.adapter(AdapterOp::Render, &ws, serde_json::json!({"offer_file": "backend-intern.json", "plan_file": file}));
        assert_eq!(tex["ok"], true, "{tex}");
        assert_eq!(tex["ready_to_send"], false);
        let again = l.adapter(AdapterOp::Render, &ws, serde_json::json!({"offer_file": "backend-intern.json", "plan_file": file}));
        assert_eq!(again["code"], "OUTPUT_EXISTS");
    }

    #[test]
    fn package_operations_resolve_and_review_works() {
        for name in ["package_create", "packages_list", "package_review", "package_status", "pdf_read"] {
            assert!(AdapterOp::from_name(name).is_some(), "{name}");
        }
        for bad in ["approve", "record_review", "package_delete", "package_set_status"] {
            assert_eq!(AdapterOp::from_name(bad), None, "{bad}");
        }
        let (_t, ws) = demo(false);
        let l = launcher();
        let list = l.adapter(AdapterOp::PackagesList, &ws, serde_json::json!({}));
        assert_eq!(list["ok"], true, "{list}");
        assert_eq!(list["packages"].as_array().unwrap().len(), 0);
        assert_eq!(AdapterOp::from_name("package_approve"), Some(AdapterOp::PackageApprove));
        // the approval operation refuses anything that is not an explicit, confirmed decision
        let refused = l.adapter(AdapterOp::PackageApprove, &ws, serde_json::json!({"name": "x", "decision": "APPROVED", "reviewer": "Fictional"}));
        assert_eq!(refused["ok"], false);
        assert_eq!(refused["code"], "CONFIRMATION_REQUIRED");
        let none = l.adapter(AdapterOp::PdfRead, &ws, serde_json::json!({"package": "../../x"}));
        assert_eq!(none["ok"], false);
    }

    #[test]
    fn git_demo_workspace_is_an_independent_repository_and_never_overwrites() {
        let tmp = tempfile::tempdir().unwrap();
        let target = tmp.path().join("git-demo");
        let made = ensure_git_demo_workspace(&repo_root(), &target).unwrap();
        assert!(made.created && target.join(".git").is_dir());
        let count = std::process::Command::new("git").args(["rev-list", "--count", "HEAD"]).current_dir(&target).output().unwrap();
        assert_eq!(String::from_utf8_lossy(&count.stdout).trim(), "1");
        let again = ensure_git_demo_workspace(&repo_root(), &target).unwrap();
        assert!(!again.created);
    }

    #[test]
    fn diagnostics_report_engine_git_and_latex_without_paths() {
        let (_t, ws) = demo(false);
        let d = launcher().diagnose(Some(&ws));
        assert_eq!(d["ok"], true, "{d}");
        assert_eq!(d["mode"], "development");
        assert_eq!(d["engine"]["status"], "OK");
        assert!(["FOUND", "ABSENT"].contains(&d["git"]["status"].as_str().unwrap()));
        assert!(["FOUND", "ABSENT"].contains(&d["latex"]["pdflatex"].as_str().unwrap()));
        assert!(["VERIFIED", "UNVERIFIABLE", "NOT_CHECKED"].contains(&d["provenance"]["status"].as_str().unwrap()));
        assert_eq!(d["offline"], true);
        let text = d.to_string();
        assert!(!text.contains(&ws), "a workspace path leaked into the diagnostics");
        // without a workspace the provenance is simply not checked
        assert_eq!(launcher().diagnose(None)["provenance"]["status"], "NOT_CHECKED");
    }

    #[test]
    fn sidecar_is_found_only_where_expected() {
        let tmp = tempfile::tempdir().unwrap();
        assert!(find_sidecar_with(None, Some(tmp.path())).is_none());
        std::fs::create_dir_all(tmp.path().join("engine")).unwrap();
        std::fs::write(tmp.path().join("engine").join(SIDECAR_NAME), b"x").unwrap();
        assert_eq!(find_sidecar_with(None, Some(tmp.path())), Some(tmp.path().join("engine").join(SIDECAR_NAME)));
        assert!(find_sidecar_with(None, None).is_none());
        // an override pointing at a missing file is ignored
        assert!(find_sidecar_with(Some(tmp.path().join("missing.exe")), None).is_none());
    }

    /// Runs only against a built embedded engine (`MODULARCV_SIDECAR`); `verify.ps1` builds it and sets
    /// `MODULARCV_REQUIRE_SIDECAR=1`, in which case its absence fails the test instead of skipping it.
    #[test]
    fn embedded_engine_runs_every_kind_of_operation() {
        let Some(path) = std::env::var_os("MODULARCV_SIDECAR").map(PathBuf::from).filter(|p| p.is_file()) else {
            assert!(std::env::var_os("MODULARCV_REQUIRE_SIDECAR").is_none(), "the embedded engine is required but missing");
            eprintln!("embedded engine not built: test not run");
            return;
        };
        let (_t, ws) = demo(false);
        let mut l = launcher();
        l.sidecar = Some(path);
        // structured read and the engine's own facts check
        let read = l.adapter(AdapterOp::Read, &ws, serde_json::json!({}));
        assert_eq!(read["ok"], true, "{read}");
        let check = l.validate(OP_FACTS_CHECK, &ws);
        assert_eq!(check.outcome, Outcome::Valid, "{:?}", check.detail);
        // a write, with the engine's refusal of an implicit confirmation
        let sha = read["facts"]["source_sha256"].clone();
        let bad = l.adapter(AdapterOp::SaveFact, &ws, serde_json::json!({"expected_sha256": sha, "mode": "update",
            "fact": {"id": "exp.junior-dev.speed", "status": "CONFIRMED", "text": "Improved."}}));
        assert_eq!(bad["code"], "CONFIRMATION_REQUIRED");
        let ok = l.adapter(AdapterOp::SaveFact, &ws, serde_json::json!({"expected_sha256": sha, "mode": "update",
            "fact": {"id": "exp.junior-dev.speed", "status": "NOT_CONFIRMED", "text": "Improved, unmeasured."}}));
        assert_eq!(ok["ok"], true, "{ok}");
        // offer -> matrix -> plan -> .tex through the embedded engine
        let plan = l.adapter(AdapterOp::Plan, &ws, serde_json::json!({"offer_file": "backend-intern.json", "write": true}));
        assert_eq!(plan["ok"], true, "{plan}");
        let file = plan["written"]["file"].as_str().unwrap().to_string();
        let tex = l.adapter(AdapterOp::Render, &ws, serde_json::json!({"offer_file": "backend-intern.json", "plan_file": file}));
        assert_eq!(tex["ok"], true, "{tex}");
        assert_eq!(tex["ready_to_send"], false);
        // approval is refused without explicit confirmations, even through the embedded engine
        let refused = l.adapter(AdapterOp::PackageApprove, &ws, serde_json::json!({"name": "x", "decision": "APPROVED", "reviewer": "Fictional"}));
        assert_eq!(refused["code"], "CONFIRMATION_REQUIRED");
        // diagnostics say the engine is embedded
        let d = l.diagnose(Some(&ws));
        assert_eq!((d["ok"].clone(), d["mode"].clone(), d["engine"]["embedded"].clone()), (true.into(), "embedded".into(), true.into()), "{d}");
        // an unknown mode is refused by the embedded entry point
        let run = run_process(&l.sidecar.clone().unwrap().to_string_lossy(), &["rm".to_string(), "-rf".to_string()], &std::env::temp_dir(), &[], None, Duration::from_secs(30)).unwrap();
        assert_eq!(run.exit_code, Some(2));
    }

    #[test]
    fn adapter_cannot_smuggle_another_operation() {
        let (_t, ws) = demo(false);
        let r = launcher().adapter(AdapterOp::Read, &ws, serde_json::json!({"op": "save_fact"}));
        assert_eq!(r["ok"], true);
        assert!(r.get("facts").is_some());
    }
}
