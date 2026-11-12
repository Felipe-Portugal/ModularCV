# Installing ModularCV Desktop on Windows

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

ModularCV Desktop is a Windows application for the ModularCV engine. It is a **beta** (`0.5.0-beta.1`): it works, it was tested on the
machines listed in [KNOWN_ISSUES.md](KNOWN_ISSUES.md), and it has rough edges.

> **Prepared — not yet published.** ModularCV Desktop `0.5.0-beta.1` has not been published: there is no Desktop release and no installer to
> download today. The installer is built and validated; it will be offered on the **Releases** page of the GitHub repository after the
> official publication. Until then, this page describes how the installation will work, so that you can read it in advance.

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

## 1. Download and check the file (after the publication)

Once the beta is published, download `ModularCV Desktop_0.5.0-beta.1_x64-setup.exe` from the **Releases** page of the GitHub repository. Do not take it from anywhere else.

Check its SHA-256 fingerprint before running it. In PowerShell, from the folder that holds the file:

```powershell
Get-FileHash ".\ModularCV Desktop_0.5.0-beta.1_x64-setup.exe" -Algorithm SHA256
```

The result must be exactly the fingerprint published with the release. If it differs, do not run the file.

The installer prepared for this beta (`ModularCV Desktop_0.5.0-beta.1_x64-setup.exe`, 10,022,845 bytes, 9.56 MiB, unsigned) was built from commit
`da656f0` and has this SHA-256:

```
C638561536F3921B775C048ED4E8A4A86C8D06012DF13015CA474DF0FD45AF71
```

This is the fingerprint of the file planned for publication: the release will publish exactly that file. If the file you downloaded shows a
different fingerprint, do not run it. Until the release exists there is nothing to download and nothing to compare.

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

The fingerprint above is the one of the installer built from commit `da656f0`. What was done with that exact file:

- **Windows 11 virtual machine** (built from a third-party, stripped-down image, not a stock installation; no Python, Node.js or Rust installed):
  hash checked in the machine, fresh silent install, start from the Start-menu shortcut, the journeys with Git and LaTeX hidden from the
  application (16 of 16 checks), then with Git and MiKTeX (29 of 29 checks: profile, offers, matrix, `.tex`, PDF, package, review, approval,
  revocation after a change, refusal, stale evidence), a package created through the interface, English and light theme kept after a
  restart, and a silent uninstall that kept the application data and an external fictional workspace. The first run of the second set gave
  25 of 29: the four failures were in the test harness (its command-line checks pointed at a missing interpreter); the harness was fixed and the
  whole set was replayed (29 of 29).
- **Not done with this exact file:** a stock Windows 11 installation, Windows 10, TeX Live, the graphical uninstaller with the "delete application
  data" box ticked, installing over an older version, and a run on the developer's own computer (an earlier build of this beta went through the
  same journeys there).
- GitHub's automated checks run the engine and Desktop test suites on Windows. The runner has no LaTeX, so the tests that need `pdflatex` are
  skipped there (they pass on a machine with MiKTeX), and the checks do not build or test the installer.

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Updating

Run the newer installer. Your workspaces are never inside the installation folder and are not touched by the installer. Installing over
an older version was **not tested** for this beta; if in doubt, uninstall first (see [UNINSTALL.md](UNINSTALL.md)).

## Removing it

See [UNINSTALL.md](UNINSTALL.md).
