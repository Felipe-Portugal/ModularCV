//! The Microsoft Visual C++ Redistributable (x64) that the embedded engine needs.
//!
//! ModularCV Desktop does not ship `VCRUNTIME140.dll` or any other Microsoft C or C++ runtime file: Microsoft
//! distributes its Redistributable itself, and the user installs it separately (an installation may need
//! administrator rights). This module only *looks* for it, through the registry key that every Redistributable
//! writes, and describes what is wrong in plain words. It never downloads or installs anything.
//!
//! The minimum is the toolset recorded in `python314.dll` (MSVC 14.44.35229): Microsoft asks for a Redistributable at
//! least as recent as the build tools. The same minimum is written in `windows/hooks.nsh` (installer) and in
//! `desktop/licenses/vc-runtime-prerequisite.json`; a test keeps the three equal.

use std::cmp::Ordering;

pub const MIN_MAJOR: u32 = 14;
pub const MIN_MINOR: u32 = 44;
pub const MIN_BUILD: u32 = 35229;
pub const MIN_VERSION_TEXT: &str = "14.44.35229";
pub const DOWNLOAD_URL: &str = "https://aka.ms/vc14/vc_redist.x64.exe";
pub const INFO_URL: &str = "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist";

#[cfg(windows)]
const REGISTRY_KEY: &str = r"HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64";

/// Version of an installed Redistributable, as the registry reports it (major, minor, build).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Version(pub u32, pub u32, pub u32);

impl PartialOrd for Version {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Version {
    fn cmp(&self, other: &Self) -> Ordering {
        (self.0, self.1, self.2).cmp(&(other.0, other.1, other.2))
    }
}

impl std::fmt::Display for Version {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}.{}.{}", self.0, self.1, self.2)
    }
}

pub const MINIMUM: Version = Version(MIN_MAJOR, MIN_MINOR, MIN_BUILD);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Ok(Version),
    Missing,
    TooOld(Version),
}

/// Reads `reg query` output: the `Installed` flag and the version, or `None` when the key does not hold both.
pub fn parse_reg_query(text: &str) -> Option<(bool, Version)> {
    let (mut installed, mut major, mut minor, mut build) = (None, None, None, None);
    for line in text.lines() {
        let mut parts = line.split_whitespace();
        let (Some(name), Some(kind), Some(value)) = (parts.next(), parts.next(), parts.next()) else { continue };
        if kind != "REG_DWORD" {
            continue;
        }
        let Some(number) = value.strip_prefix("0x").and_then(|h| u32::from_str_radix(h, 16).ok()) else { continue };
        match name {
            "Installed" => installed = Some(number),
            "Major" => major = Some(number),
            "Minor" => minor = Some(number),
            "Bld" => build = Some(number),
            _ => {}
        }
    }
    Some((installed? == 1, Version(major?, minor?, build?)))
}

/// What the registry reading means. A missing key, an `Installed` flag other than 1 or unreadable output all count as missing.
pub fn evaluate(reading: Option<(bool, Version)>) -> Status {
    match reading {
        Some((true, v)) if v >= MINIMUM => Status::Ok(v),
        Some((true, v)) => Status::TooOld(v),
        _ => Status::Missing,
    }
}

#[cfg(windows)]
fn read_registry() -> Option<String> {
    use std::os::windows::process::CommandExt;
    let system_root = std::env::var_os("SystemRoot").unwrap_or_else(|| r"C:\Windows".into());
    let reg = std::path::Path::new(&system_root).join("System32").join("reg.exe");
    let out = std::process::Command::new(reg)
        .args(["query", REGISTRY_KEY, "/reg:64"])
        .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
        .output()
        .ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).into_owned())
}

/// The installed Redistributable, looked up now.
#[cfg(windows)]
pub fn check() -> Status {
    evaluate(read_registry().as_deref().and_then(parse_reg_query))
}

/// Outside Windows there is no embedded engine to protect (development only).
#[cfg(not(windows))]
pub fn check() -> Status {
    Status::Ok(MINIMUM)
}

/// Stable error code and message for a runtime that cannot be used, `None` when it is fine.
pub fn problem_for(status: Status) -> Option<(&'static str, String)> {
    let how = format!(
        "ModularCV does not include this Microsoft component. Install the Microsoft Visual C++ Redistributable (x64) from {DOWNLOAD_URL} \
         (administrator rights may be required), then restart ModularCV. More: {INFO_URL}"
    );
    match status {
        Status::Ok(_) => None,
        Status::Missing => Some((
            "RUNTIME_MISSING",
            format!("The Microsoft Visual C++ Redistributable (x64) {MIN_VERSION_TEXT} or newer was not found. {how}"),
        )),
        Status::TooOld(v) => Some((
            "RUNTIME_TOO_OLD",
            format!("The installed Microsoft Visual C++ Redistributable (x64) is {v}; {MIN_VERSION_TEXT} or newer is required. {how}"),
        )),
    }
}

/// Message for an engine that Windows could not load although the registry looked fine (damaged or removed runtime).
pub fn load_failure_message() -> String {
    format!(
        "Windows could not load the embedded engine: a library it needs is missing or incompatible. Install or repair the Microsoft Visual C++ \
         Redistributable (x64) {MIN_VERSION_TEXT} or newer from {DOWNLOAD_URL}, then restart ModularCV. More: {INFO_URL}"
    )
}

/// True when `code` is a Windows loader failure of the engine process: DLL not found (0xC0000135), entry point not
/// found (0xC0000139) or bad image (0xC000007B).
pub fn is_loader_failure(code: Option<i32>) -> bool {
    matches!(code.map(|c| c as u32), Some(0xC000_0135 | 0xC000_0139 | 0xC000_007B))
}

/// Looks for the runtime, once it has been found good it is not looked up again during this run.
pub fn problem() -> Option<(&'static str, String)> {
    use std::sync::atomic::{AtomicBool, Ordering};
    static GOOD: AtomicBool = AtomicBool::new(false);
    if GOOD.load(Ordering::Relaxed) {
        return None;
    }
    let status = check();
    if matches!(status, Status::Ok(_)) {
        GOOD.store(true, Ordering::Relaxed);
    }
    problem_for(status)
}

#[cfg(test)]
mod tests {
    use super::*;

    const REG_OK: &str = "\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\X64\r\n    Installed    REG_DWORD    0x1\r\n    Major    REG_DWORD    0xe\r\n    Minor    REG_DWORD    0x34\r\n    Bld    REG_DWORD    0x90a5\r\n    Version    REG_SZ    v14.52.37029.00\r\n    RuntimeMajor    REG_DWORD    0xe\r\n";

    #[test]
    fn registry_output_is_read() {
        assert_eq!(parse_reg_query(REG_OK), Some((true, Version(14, 52, 37029))));
        assert_eq!(parse_reg_query("ERROR: the system was unable to find the specified registry key"), None);
        assert_eq!(parse_reg_query(""), None);
        // a reading with the version only, or the flag only, is not trusted
        assert_eq!(parse_reg_query("    Installed    REG_DWORD    0x1\r\n"), None);
        assert_eq!(parse_reg_query("    Major    REG_DWORD    0xe\r\n    Minor    REG_DWORD    0x2c\r\n    Bld    REG_DWORD    0x8a1d\r\n"), None);
    }

    #[test]
    fn minimum_matches_its_text() {
        assert_eq!(MINIMUM.to_string(), MIN_VERSION_TEXT);
    }

    #[test]
    fn versions_are_compared_field_by_field() {
        assert_eq!(evaluate(Some((true, Version(14, 44, 35229)))), Status::Ok(Version(14, 44, 35229)));
        assert_eq!(evaluate(Some((true, Version(14, 52, 37029)))), Status::Ok(Version(14, 52, 37029)));
        assert_eq!(evaluate(Some((true, Version(15, 0, 1)))), Status::Ok(Version(15, 0, 1)));
        assert_eq!(evaluate(Some((true, Version(14, 44, 35211)))), Status::TooOld(Version(14, 44, 35211)));
        assert_eq!(evaluate(Some((true, Version(14, 43, 99999)))), Status::TooOld(Version(14, 43, 99999)));
        assert_eq!(evaluate(Some((true, Version(13, 99, 99999)))), Status::TooOld(Version(13, 99, 99999)));
    }

    #[test]
    fn anything_unclear_counts_as_missing() {
        assert_eq!(evaluate(None), Status::Missing);
        assert_eq!(evaluate(Some((false, Version(14, 52, 37029)))), Status::Missing);
    }

    #[test]
    fn problems_have_stable_codes_and_point_to_microsoft_only() {
        assert!(problem_for(Status::Ok(MINIMUM)).is_none());
        let (code, message) = problem_for(Status::Missing).unwrap();
        assert_eq!(code, "RUNTIME_MISSING");
        assert!(message.contains(DOWNLOAD_URL) && message.contains("administrator") && message.contains(MIN_VERSION_TEXT));
        let (code, message) = problem_for(Status::TooOld(Version(14, 44, 35211))).unwrap();
        assert_eq!(code, "RUNTIME_TOO_OLD");
        assert!(message.contains("14.44.35211") && message.contains(DOWNLOAD_URL));
        // links go to Microsoft and nowhere else
        for text in [message, load_failure_message()] {
            for url in text.split_whitespace().filter(|w| w.starts_with("http")) {
                let url = url.trim_end_matches(['.', ',']);
                assert!(url.starts_with("https://aka.ms/") || url.starts_with("https://learn.microsoft.com/"), "{url}");
            }
        }
    }

    #[test]
    fn loader_failures_are_recognised() {
        assert!(is_loader_failure(Some(0xC000_0135_u32 as i32)));
        assert!(is_loader_failure(Some(0xC000_0139_u32 as i32)));
        assert!(is_loader_failure(Some(0xC000_007B_u32 as i32)));
        assert!(!is_loader_failure(Some(0)));
        assert!(!is_loader_failure(Some(1)));
        assert!(!is_loader_failure(Some(2)));
        assert!(!is_loader_failure(None));
    }

    #[cfg(windows)]
    #[test]
    fn the_real_registry_can_be_read_on_this_machine() {
        // no assumption about what is installed: the lookup must simply end in one of the three states
        assert!(matches!(check(), Status::Ok(_) | Status::Missing | Status::TooOld(_)));
    }
}
