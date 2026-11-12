# Builds the ModularCV Desktop Windows installer (NSIS, per-user, unsigned) from a clean checkout.
#
#   powershell -File desktop\build-installer.ps1 [-Python <python 3.12-3.14>]
#
# Prerequisites on the BUILD machine only: Python 3.12-3.14, Node.js + npm, Rust (MSVC), Git. The installed application needs none
# of them: it carries its own engine (PyInstaller onedir sidecar) and relies on WebView2, which Windows 11 includes.
# Output (git-ignored): desktop\src-tauri\target\release\bundle\nsis\ModularCV Desktop_<version>_x64-setup.exe
# Nothing is signed, nothing is uploaded, no tag or release is made.

param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$desktop = $PSScriptRoot
$repo = Split-Path -Parent $desktop
$resources = Join-Path $desktop "src-tauri\resources"

function Step([string]$name, [scriptblock]$body) {
  Write-Host "`n=== $name ===" -ForegroundColor Cyan
  & $body
  if ($LASTEXITCODE -ne 0) { throw "failed: $name" }
}

Step "Embedded engine (PyInstaller onedir)" { & (Join-Path $desktop "build-sidecar.ps1") -Mode onedir -Python $Python }

Step "Fictional example workspace (resource)" {
  $target = Join-Path $resources "examples"
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  New-Item -ItemType Directory -Force (Join-Path $target "workspace") | Out-Null
  Copy-Item -Recurse -Force (Join-Path $repo "examples\workspace\*") (Join-Path $target "workspace")
  $global:LASTEXITCODE = 0
}

# Keep the build machine's paths (user profile, cargo registry, checkout) out of the executable's panic/debug strings.
$env:RUSTFLAGS = "--remap-path-prefix=$env:USERPROFILE=Z:/user --remap-path-prefix=$repo=Z:/src"

Push-Location $desktop
try {
  Step "Front end dependencies" { npm ci }
  Step "Tauri production build (NSIS)" { npx tauri build --bundles nsis }
} finally { Pop-Location }

$installer = Get-ChildItem (Join-Path $desktop "src-tauri\target\release\bundle\nsis") -Filter "*-setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$hash = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash
"Installer: $($installer.FullName)"
"Size: {0:N1} MB   SHA-256: {1}" -f ($installer.Length / 1MB), $hash
