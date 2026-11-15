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
| Microsoft Visual C++ Redistributable (x64) 14.44.35229 or newer | The embedded engine | **Not included in ModularCV**: Microsoft distributes it separately, from https://aka.ms/vc14/vc_redist.x64.exe (more at <https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist>). Installing it may need **administrator rights**; ModularCV itself never asks for them and never downloads or installs it. Many Windows 11 computers have it already; if yours does not, or has an older one, the installer and the application tell you so and where to get it. |
| WebView2 runtime | The window of the application | Part of Windows 11. If it is missing, the installer downloads Microsoft's small bootstrapper, so an internet connection is needed **during installation only** in that case. |
| Git for Windows | Packages (the engine checks a commit of your sources) | Optional. Without it you can still browse, edit, analyse offers and produce `.tex` files. |
| MiKTeX or TeX Live (`pdflatex`) | PDF files | Optional. Without it you get the `.tex` file and no PDF. |

You do **not** need Python, Node.js or Rust. The application carries its own copy of the engine. The only Microsoft component it expects you to provide is
the Visual C++ Redistributable above. If it is missing, the installer shows a warning and lets you stop (in a silent installation it only logs the fact); the
application then explains the problem and does not start its engine until the Redistributable is installed. Your workspaces are not affected.

The installer never installs Git or LaTeX, and the application never downloads anything. Settings > Environment diagnostics tells you,
offline and read-only, which optional tools it can find.

## 1. Download and check the file (after the publication)

Once the beta is published, download `ModularCV Desktop_0.5.0-beta.1_x64-setup.exe` from the **Releases** page of the GitHub repository. Do not take it from anywhere else.

Check its SHA-256 fingerprint before running it. In PowerShell, from the folder that holds the file:

```powershell
Get-FileHash ".\ModularCV Desktop_0.5.0-beta.1_x64-setup.exe" -Algorithm SHA256
```

The result must be exactly the fingerprint published with the release. If it differs, do not run the file.

The installer for this beta (`ModularCV Desktop_0.5.0-beta.1_x64-setup.exe`, unsigned, 9,544,231 bytes) has this SHA-256 fingerprint:

```
0763AECE52C9E816767E8BD68B42646428B118FE10A4DD6FB172A0BD08D757F4
```

It is built from the sources of this repository and does not contain Microsoft's Visual C++ runtime (see "What you need"). The release will publish exactly the
file that has this fingerprint. If the file you downloaded shows a different fingerprint, do not run it. Until the release exists there is nothing to download and
nothing to compare.

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

**The installer above** (SHA-256 `0763AECE…57F4`) was tested on a **Windows 11 virtual machine** (build 26200, built from a third-party, stripped-down
image, not a stock installation; no Python, Node.js or Rust; Git and MiKTeX installed for the second set). The hash was checked in the machine.

- **No Visual C++ Redistributable:** the engine does not start (the launcher reports it cannot load the Python DLL); the application's diagnostics show the
  message with Microsoft's download address; the graphical installer shows the warning (English and French); answering No aborts the installation ("Installation
  Aborted") and answering Yes installs; a silent installation goes on. Installed files: 33, none of them a Microsoft runtime file.
- **Redistributable 14.44.35211 (older than the minimum):** the application shows the "too old" message, with the installed and the required version.
  (The engine itself still ran with that version: the minimum is a conservative policy, not a measured failure point.)
- **Redistributable 14.52.37029 (Microsoft's current file, signature valid):** the engine starts. The modules loaded by the running engine were listed:
  `VCRUNTIME140.dll`, `ucrtbase.dll` and `msvcp_win.dll` come from `System32`; `python314.dll` and `libcrypto-3.dll` come from the application folder.
  Journeys with Git and LaTeX hidden: **16 of 16** checks; with Git and MiKTeX: **29 of 29** checks. Language, theme and workspace kept after a restart.
  Silent uninstall: program, shortcut and registry entry removed; the application data and an external fictional workspace kept. Of the 33 installed
  files, 31 are byte-identical to build files; `desktop.exe` differs from the build output by 3 bytes (the bundle-type marker Tauri writes), and
  `uninstall.exe` is generated by the installer.

The earlier candidate, which carried Microsoft's `VCRUNTIME140.dll`, is withdrawn and will not be published. What was done with
that earlier candidate:

- **Windows 11 virtual machine** (built from a third-party, stripped-down image, not a stock installation; no Python, Node.js or Rust installed):
  hash checked in the machine, fresh silent install, start from the Start-menu shortcut, the journeys with Git and LaTeX hidden from the
  application (16 of 16 checks), then with Git and MiKTeX (29 of 29 checks: profile, offers, matrix, `.tex`, PDF, package, review, approval,
  revocation after a change, refusal, stale evidence), a package created through the interface, English and light theme kept after a
  restart, and a silent uninstall that kept the application data and an external fictional workspace. The installed `legal` folder holds
  `LICENSE`, `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`, byte-identical to the files that were built in; of the 34 installed files,
  32 are byte-identical to the build inputs and the other two (`desktop.exe`, written by Tauri at bundling, and `uninstall.exe`, generated by
  the installer) were checked separately. The machine had **no Visual C++ Redistributable**; that candidate carried the DLL itself.
- **Not done with this exact file:** a stock Windows 11 installation, Windows 10, TeX Live, the graphical uninstaller with the "delete application
  data" box ticked, installing over an older version, and a run on the developer's own computer (an earlier build of this beta went through the
  same journeys there).
- GitHub's automated checks run the engine and Desktop test suites on Windows. The runner has no LaTeX, so the tests that need `pdflatex` are
  skipped there (they pass on a machine with MiKTeX), and the checks do not build or test the installer.

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Licences

The installation folder has a `legal` folder that can be read offline: `LICENSE` (the ModularCV licence, MIT), `THIRD_PARTY_NOTICES.md` (the
inventory of third-party components) and `THIRD_PARTY_LICENSES.txt` (their licence texts and copyright notices). A few items could not be
settled, for example whether the C runtime that `desktop.exe` links statically needs a notice; Microsoft's Visual C++ Redistributable is not shipped and is listed as a prerequisite; the open points are listed at the end of that file and in
[KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Updating

Run the newer installer. Your workspaces are never inside the installation folder and are not touched by the installer. Installing over
an older version was **not tested** for this beta; if in doubt, uninstall first (see [UNINSTALL.md](UNINSTALL.md)).

## Removing it

See [UNINSTALL.md](UNINSTALL.md).
