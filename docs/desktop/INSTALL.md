# Installing ModularCV Desktop on Windows

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

ModularCV Desktop is a Windows application for the ModularCV engine. It is a **beta** (`0.5.0-beta.1`): it works, it was tested on the
machines listed in [KNOWN_ISSUES.md](KNOWN_ISSUES.md), and it has rough edges.

## What you need

| Item | Needed for | Notes |
|---|---|---|
| Windows 11, 64-bit | The application | Tested on Windows 11 (see the test record below). Windows 10 was **not** tested. |
| About 30 MB of disk space | The installed application | The installer itself is about 10 MB. |
| WebView2 runtime | The window of the application | Part of Windows 11. If it is missing, the installer downloads Microsoft's small bootstrapper, so an internet connection is needed **during installation only** in that case. |
| Git for Windows | Packages (the engine checks a commit of your sources) | Optional. Without it you can still browse, edit, analyse offers and produce `.tex` files. |
| MiKTeX or TeX Live (`pdflatex`) | PDF files | Optional. Without it you get the `.tex` file and no PDF. |

You do **not** need Python, Node.js or Rust. The application carries its own copy of the engine.

The installer never installs Git or LaTeX, and the application never downloads anything. Settings > Environment diagnostics tells you,
offline and read-only, which optional tools it can find.

## 1. Download and check the file

Download `ModularCV Desktop_0.5.0-beta.1_x64-setup.exe` from the **Releases** page of the GitHub repository. Do not take it from anywhere else.

Check its SHA-256 fingerprint before running it. In PowerShell, from the folder that holds the file:

```powershell
Get-FileHash ".\ModularCV Desktop_0.5.0-beta.1_x64-setup.exe" -Algorithm SHA256
```

The result must be exactly:

```
F1DA86139CDA4125FCCE4E2D171256791F29E7CE29A170CE28BFF4764A1F14B8
```

If it differs, do not run the file. The same fingerprint is in the release notes.

## 2. Run the installer

Double-click the file. The installer is **not signed** (the project has no code-signing certificate), so Windows SmartScreen may show
"Windows protected your PC". If the fingerprint matched, choose **More info**, then **Run anyway**. This is expected for an unsigned program;
the fingerprint is what tells you the file is the published one.

- It installs **for your user only**; no administrator rights are asked.
- It installs into `%LOCALAPPDATA%\ModularCV Desktop` and adds a Start-menu entry named **ModularCV**.
- The language is French or English.
- If WebView2 is missing it is downloaded and installed first.

Some antivirus programs scan a new program the first time it runs, which can make the first start slower.

## 3. Start it

Open **ModularCV** from the Start menu. Continue with [FIRST_RUN.md](FIRST_RUN.md).

## Test record of the installer

The fingerprint above belongs to the installer that was built and tested. It was tested on a Windows 11 virtual machine with none of the
development tools installed: installation, start from the Start menu, the main journeys with and without Git and LaTeX, closing and reopening,
and uninstalling. That virtual machine was built from a third-party, stripped-down Windows 11 image, not from a stock installation, so a test on a
stock Windows 11 is still recommended. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Updating

Run the newer installer. Your workspaces are never inside the installation folder and are not touched by the installer. Installing over
an older version was **not tested** for this beta; if in doubt, uninstall first (see [UNINSTALL.md](UNINSTALL.md)).

## Removing it

See [UNINSTALL.md](UNINSTALL.md).
