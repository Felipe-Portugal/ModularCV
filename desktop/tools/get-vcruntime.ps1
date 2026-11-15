# Fetches the Visual C++ runtime that the embedded engine needs, from Microsoft, and verifies it.
#
#   powershell -File desktop\tools\get-vcruntime.ps1 -Dest <file> [-Python <python>] [-ExpectSha256 <hash>] [-MinVersion 14.44.35229.0]
#
# Why: python314.dll and the extension modules of the engine are linked with MSVC 14.44.35229 and need a VCRUNTIME140.dll at least that recent
# (Microsoft: the redistributable must be the same as or later than the build tools). Microsoft allows redistributing its runtime files only to
# licensed Visual Studio users, unmodified, under the Microsoft Software License Terms. The file is taken, byte for byte, from the Visual C++
# Redistributable that Microsoft publishes (https://aka.ms/vc14/vc_redist.x64.exe), after checking its Authenticode signature.
# Nothing is installed. Checks: the bundle and the DLL are signed by Microsoft (Valid), the DLL is x64 and not older than -MinVersion, and, when
# -ExpectSha256 is given (the release build does), the DLL hash equals the pinned one (desktop\licenses\microsoft-runtime.json).

param(
  [Parameter(Mandatory = $true)][string]$Dest,
  [string]$Python = "python",
  [string]$ExpectSha256 = "",
  [string]$MinVersion = "14.44.35229.0"
)

$ErrorActionPreference = "Stop"
$tmp = Join-Path $env:TEMP ("mcv-vcredist-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
  $bundle = Join-Path $tmp "vc_redist.x64.exe"
  Invoke-WebRequest -Uri "https://aka.ms/vc14/vc_redist.x64.exe" -OutFile $bundle -UseBasicParsing -MaximumRedirection 5
  $sig = Get-AuthenticodeSignature $bundle
  if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") { throw "the Visual C++ Redistributable is not validly signed by Microsoft" }
  $bundleHash = (Get-FileHash $bundle -Algorithm SHA256).Hash
  & $Python -I (Join-Path $PSScriptRoot "extract_vcruntime.py") $bundle $Dest | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "cannot extract vcruntime140.dll from the redistributable" }
  $dll = Get-Item $Dest
  $dsig = Get-AuthenticodeSignature $dll.FullName
  if ($dsig.Status -ne "Valid" -or $dsig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") { throw "vcruntime140.dll is not validly signed by Microsoft" }
  $bytes = [IO.File]::ReadAllBytes($dll.FullName)
  $pe = [BitConverter]::ToUInt32($bytes, 0x3c)
  if ([BitConverter]::ToUInt16($bytes, $pe + 4) -ne 0x8664) { throw "vcruntime140.dll is not an x64 binary" }
  $version = [version]$dll.VersionInfo.FileVersion
  if ($version -lt [version]$MinVersion) { throw "vcruntime140.dll $version is older than the required $MinVersion" }
  $hash = (Get-FileHash $dll.FullName -Algorithm SHA256).Hash
  if ($ExpectSha256 -and $hash -ne $ExpectSha256.ToUpper()) {
    throw "vcruntime140.dll $version has SHA-256 $hash but $ExpectSha256 is pinned: Microsoft published another build. Review it, then update desktop\licenses\microsoft-runtime.json."
  }
  "vcruntime140.dll $version SHA-256 $hash (from vc_redist.x64.exe SHA-256 $bundleHash, signature $($dsig.SignerCertificate.Subject.Split(',')[0]))"
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
