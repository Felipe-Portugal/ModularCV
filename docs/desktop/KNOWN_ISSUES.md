# Limits and known issues, ModularCV Desktop 0.5.0-beta.1

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

This is a beta. Everything below is stated plainly so you can decide whether it suits you.

## What was tested, and where

- **Windows 11 25H2, 64-bit, on a virtual machine built from a third-party, stripped-down Windows 11 image.** No Python, Node.js or Rust was
  installed in it. Tested with the exact installer: installation, Start-menu launch, fictional workspace, editing, offers, matrix, plan, `.tex`,
  diagnostics, closing and reopening, uninstalling; then, with Git and MiKTeX installed in the machine, the PDF, package, review, approval,
  revocation after a change, refusal and the command-line verdict.
- **Windows 11 Home on the development computer**, with the same journeys and the development tools hidden from the application.
- **Not tested:** a stock Windows 11 installation, Windows 10, ARM Windows, TeX Live, installing over an older version, a screen reader,
  high-contrast mode, display scaling above 100 %, workspaces on network drives, very long paths.
- The virtual machine was slow (two virtual processors), so timings measured there are not representative of a real computer.

## Installation

- **The installer is unsigned.** Windows SmartScreen will warn. Check the SHA-256 fingerprint ([INSTALL.md](INSTALL.md)).
- **WebView2.** If the runtime is missing, the installer downloads Microsoft's bootstrapper, so internet is needed once. On the test
  image, a leftover registry entry made the installer believe WebView2 was present; Windows 11 itself ships the runtime. If the window stays
  blank or the application does not start, install the "Evergreen" WebView2 runtime from Microsoft.
- Antivirus software may scan the program on first run and slow it down.

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
