# Limits and known issues, ModularCV Desktop 0.5.0-beta.1

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

This is a beta. Everything below is stated plainly so you can decide whether it suits you.

## What was tested, and where

- **The installer** (SHA-256 `0763AECE…57F4`, no Microsoft runtime file inside) was tested on the same kind of virtual machine (Windows 11 build 26200,
  stripped-down third-party image): without the Visual C++ Redistributable (installer warning, application message), with 14.44.35211 (too old: message), and with
  14.52.37029 (engine starts; 16 of 16 and 29 of 29 journey checks; language, theme and workspace kept after a restart; silent uninstall that kept the
  application data and an external fictional workspace). Details in [INSTALL.md](INSTALL.md).
- **An earlier candidate on Windows 11 64-bit, on a virtual machine built from a third-party, stripped-down Windows 11 image**, withdrawn
  because it carried Microsoft's runtime file. No Python, Node.js or Rust was installed in it. Hash checked in the machine; fresh silent install; start from the Start-menu
  shortcut; with Git and LaTeX hidden from the application: fictional workspace, profile editing, offers, matrix, plan, `.tex`, diagnostics
  (16 of 16 checks); then, with Git and MiKTeX installed in the machine: PDF, package, review, approval, revocation after a change, refusal,
  stale evidence and the command-line verdict (29 of 29 checks); a package created through the interface; English and light theme kept after a
  restart; a silent uninstall that kept the application data and an external fictional workspace. Both sets passed on the first run. The installed
  `legal` folder was checked: it holds `LICENSE`, `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`, byte-identical to the files built in. The
  machine had no Visual C++ Redistributable; that candidate carried the DLL itself.
- **Windows 11 Home on the development computer:** an **earlier build** of this beta went through the same journeys with the development tools
  hidden from the application. This exact installer was **not** run there.
- **Automated checks on GitHub** (engine on Python 3.12 and 3.14, and the Desktop suites) pass, but the runner has no LaTeX, so the tests that need
  `pdflatex` are skipped there: 8 in the engine suite, 70 in the adapter suite and 2 in the packaged-engine suite, among them most of the review
  and approval tests of the adapter. They pass on a machine with MiKTeX. The checks do not build or test the installer.
- **Not tested:** a stock Windows 11 installation, Windows 10, ARM Windows, TeX Live, installing over an older version, the graphical uninstaller
  with the "delete application data" box ticked (on this exact installer), a screen reader, high-contrast mode, display scaling above 100 %,
  workspaces on network drives, very long paths.
- The virtual machine was slow (two virtual processors), so timings measured there are not representative of a real computer.

## Third-party licences

- `legal\THIRD_PARTY_LICENSES.txt` reproduces the licence texts and copyright notices of the third-party components that could be identified as
  redistributed, and `legal\THIRD_PARTY_NOTICES.md` is their inventory. This is a best-effort audit, not legal advice.
- The licence texts of NSIS 3.13 (installer stub, LZMA module) and of its plug-in are reproduced, and the WebView2 SDK loader is identified
  (1.0.3800.47).
- The engine does not ship Microsoft's `VCRUNTIME140.dll` nor the Universal CRT files. The Microsoft Visual C++ Redistributable (x64) 14.44.35229 or newer is a
  prerequisite: Microsoft distributes it (https://aka.ms/vc14/vc_redist.x64.exe), you install it (administrator rights may be needed), and ModularCV only checks for it. Without it, or with an older
  one, the installer warns and the application explains the problem instead of starting its engine.
- **Still open:** `desktop.exe` links Microsoft's static C runtime libraries (`libcmt`, `libvcruntime`) and imports the Universal CRT that Windows provides. The Visual
  Studio terms list files that may be copied next to a program (the "REDIST list"); they do not list these libraries, and no notice requirement for them was found, but this
  is a reading of the published terms, not a legal opinion, and whether the maintainer's own Visual Studio use qualifies was not checked from here. Microsoft's own terms for the
  Redistributable are not reproduced here and apply to your installation of it. No legal review was made.
- The Unicode data inside the engine's Python is version 16.0.0 (checked on the Python 3.14.10 that the engine is built from; the shipped `unicodedata.pyd` is byte-identical to that
  Python's). The installed notices still list that point as undetermined: they are embedded in the installer and are not changed after the tested build.

## Installation

- **The installer is unsigned.** Windows SmartScreen will warn. Check the SHA-256 fingerprint ([INSTALL.md](INSTALL.md)).
- **WebView2.** If the runtime is missing, the installer downloads Microsoft's bootstrapper, so internet is needed once. On the test
  image, a leftover registry entry made the installer believe WebView2 was present; Windows 11 itself ships the runtime. If the window stays
  blank or the application does not start, install the "Evergreen" WebView2 runtime from Microsoft.
- Antivirus software may scan the program on first run and slow it down.
- **Visual C++ Redistributable.** Without the Redistributable 14.44.35229 or newer, the engine cannot start: the installer warns before installing (and goes on in
  a silent installation), and the application shows a message with Microsoft's download address. Installing the Redistributable may need administrator rights. The check
  looks for the Redistributable that Microsoft registers on the computer: a copy of `vcruntime140.dll` that merely sits in a folder of your `PATH` (some tools carry one) is not accepted,
  even if Windows would load it.

## LaTeX and PDF

- **The diagnostics only check that `pdflatex` can be found.** A LaTeX installation that is present but badly configured (for example a
  MiKTeX that cannot build its formats) still shows "available". Compilation then fails with the message `PDF_FAILED`; the application
  reports it and does not crash, but it cannot warn you beforehand.
- **MiKTeX may ask to install packages on its first compilation**, and may print "you have not checked for MiKTeX updates". The first PDF can
  be slow. The application never installs LaTeX components for you.
- PDF compilation is only tested with MiKTeX. TeX Live is expected to work (the engine accepts it) but was not tried.

## Packages and Git

- Creating a package requires a Git repository whose sources are committed. Without Git you can still produce a `.tex` file.
- The application never commits for you. If you change a source after packaging, the package returns to `NEEDS_REVIEW` and you build a new one.
- Keep your real workspace **outside** `%LOCALAPPDATA%\org.modularcv.desktop` and `%APPDATA%\org.modularcv.desktop` (see [UNINSTALL.md](UNINSTALL.md)).

## Approval

- An approval is a **local decision in an unsigned file** ([STATUSES.md](STATUSES.md)). It is not a signature, not authenticated, and not proof that
  a particular person approved.
- `READY_TO_SEND` proves the process, not the candidate and not the quality of the text.

## Application

- Windows only. The interface is in French and English; some engine messages (reasons, codes) stay in English.
- It is a shell around the ModularCV engine, bundled in the installer at the engine's version `0.2.0`. The Desktop version (`0.5.0-beta.1`) is
  independent of the engine and of the command-line release `v0.2.0`.
- No telemetry, no update check, no network access by the application. You must look for new versions yourself.
- Small windows: the minimum size is 720 by 520 pixels.

## Reporting a problem

Open an issue on the GitHub repository. **Do not attach your real CV, facts or PDF.** Describe the steps, the Windows version, whether Git
and `pdflatex` are available (Settings > Environment diagnostics), and the exact message shown.
