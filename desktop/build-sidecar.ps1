# Builds the embedded Python engine ("sidecar") of ModularCV Desktop with PyInstaller.
#
#   powershell -File desktop\build-sidecar.ps1 [-Mode onedir|onefile] [-Python <python 3.12-3.14>]
#
# Output (git-ignored): desktop\src-tauri\resources\engine\   (onedir: mcv-engine.exe + _internal\, onefile: mcv-engine.exe)
# The build tools live in a private virtual environment OUTSIDE the repository; the engine gets no new dependency.
# Nothing is signed. The engine package `modularcv` and the adapter are bundled unchanged.

param(
  [ValidateSet("onedir", "onefile")][string]$Mode = "onedir",
  [string]$Python = "python",
  [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$desktop = $PSScriptRoot
$repo = Split-Path -Parent $desktop
if (-not $Out) { $Out = Join-Path $desktop "src-tauri\resources\engine" }
$work = Join-Path $desktop "build\sidecar-$Mode"
$venv = Join-Path $env:LOCALAPPDATA "modularcv-build\venv"
$PyInstallerVersion = "6.22.3"

if (-not (Test-Path "$venv\Scripts\python.exe")) {
  New-Item -ItemType Directory -Force (Split-Path $venv) | Out-Null
  & $Python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "cannot create the build environment" }
}
& "$venv\Scripts\python.exe" -m pip install --quiet "pyinstaller==$PyInstallerVersion"
if ($LASTEXITCODE -ne 0) { throw "cannot install PyInstaller" }

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force $Out | Out-Null
if (Test-Path $work) { Remove-Item -Recurse -Force $work }

$flags = @("--noconfirm", "--clean", "--console", "--name", "mcv-engine", "--distpath", $work, "--workpath", (Join-Path $work "work"),
           "--specpath", $work, "--paths", $repo, "--paths", (Join-Path $desktop "adapter"), "--collect-submodules", "modularcv",
           "--hidden-import", "mcv_adapter", "--hidden-import", "mcv_diag",
           "--exclude-module", "tkinter", "--exclude-module", "unittest", "--exclude-module", "pydoc", "--exclude-module", "test")
if ($Mode -eq "onefile") { $flags += "--onefile" } else { $flags += "--onedir" }
$env:PYTHONHASHSEED = "0"
& "$venv\Scripts\python.exe" -m PyInstaller @flags (Join-Path $desktop "sidecar\mcv_engine.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if ($Mode -eq "onefile") {
  Copy-Item (Join-Path $work "mcv-engine.exe") (Join-Path $Out "mcv-engine.exe")
} else {
  Copy-Item -Recurse (Join-Path $work "mcv-engine\*") $Out
}
$size = (Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum).Sum
"Sidecar ($Mode) built: $Out ({0:N1} MB)" -f ($size / 1MB)
