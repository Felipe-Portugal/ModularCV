# Full verification of the desktop application and the engine it sits on.
#
# `pyproject.toml` sets `testpaths = ["tests"]`, so a bare `python -m pytest`
# at the repository root does NOT run `desktop/adapter/tests`. This script runs
# every suite explicitly and stops at the first failure.
#
# Usage (from anywhere):  powershell -File desktop\verify.ps1 [-Python <interpreter>] [-SkipRust]

param(
  [string]$Python = "python",
  [switch]$SkipRust
)

$ErrorActionPreference = "Continue"  # native stderr must not abort; exit codes decide
$desktop = $PSScriptRoot
$root = Split-Path -Parent $desktop

function Step([string]$name, [scriptblock]$body) {
  Write-Host "`n=== $name ===" -ForegroundColor Cyan
  & $body
  if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name" -ForegroundColor Red; exit 1 }
}

Push-Location $root
try {
  Step "Engine suite (tests/)" { & $Python -m pytest -q -p no:cacheprovider }
  Step "Adapter suite (desktop/adapter/tests, real engine)" { & $Python -m pytest -q -p no:cacheprovider desktop/adapter/tests }
  Step "Privacy scanner" { & $Python -m modularcv privacy --root . }
  Push-Location $desktop
  try {
    Step "Front end: typecheck" { npm run typecheck }
    Step "Front end: unit tests" { npm test }
    Step "Front end: build" { npm run build }
  } finally { Pop-Location }
  Step "Embedded engine (PyInstaller sidecar) build" { & (Join-Path $desktop "build-sidecar.ps1") -Python $Python }
  $env:MODULARCV_SIDECAR = Join-Path $desktop "src-tauri\resources\engine\mcv-engine.exe"
  $env:MODULARCV_REQUIRE_SIDECAR = "1"
  Step "Embedded engine: adapter tests against the packaged executable" {
    $env:MODULARCV_TEST_SIDECAR = $env:MODULARCV_SIDECAR
    & $Python -m pytest -q -p no:cacheprovider desktop/sidecar/tests
  }
  if (-not $SkipRust) {
    # tauri-build requires every bundled resource directory to exist, even for `cargo test`. `resources/examples` is git-ignored
    # and normally filled by build-installer.ps1, so a clean checkout (such as a CI runner) must prepare it here, the same way.
    $examples = Join-Path $desktop "src-tauri\resources\examples"
    if (Test-Path $examples) { Remove-Item -Recurse -Force $examples }
    New-Item -ItemType Directory -Force (Join-Path $examples "workspace") | Out-Null
    Copy-Item -Recurse -Force (Join-Path $root "examples\workspace\*") (Join-Path $examples "workspace")
    $global:LASTEXITCODE = 0
    Push-Location (Join-Path $desktop "src-tauri")
    try {
      Step "Rust: tests" { cargo test }
      Step "Rust: clippy" { cargo clippy --all-targets -- -D warnings }
    } finally { Pop-Location }
  }
  Write-Host "`nAll suites passed." -ForegroundColor Green
} finally { Pop-Location }
