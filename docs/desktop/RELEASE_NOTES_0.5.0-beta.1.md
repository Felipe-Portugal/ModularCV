# ModularCV Desktop 0.5.0-beta.1, release notes

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

First beta of ModularCV Desktop, a Windows application for the ModularCV engine. **Prepared — not yet published: there is no Desktop release yet.**
The command-line release `v0.2.0` is unchanged; the engine inside the installer is that same `0.2.0` engine.

## Download (not available yet)

The installer is not published. Prepared file: 9,544,231 bytes, SHA-256 `0763AECE52C9E816767E8BD68B42646428B118FE10A4DD6FB172A0BD08D757F4`; the release
will publish exactly that file. It will be downloadable from the
**Releases** page of the GitHub repository after the official publication. Check the file before running it ([INSTALL.md](INSTALL.md)). Windows SmartScreen will
warn because the installer is not signed.

**Provenance.** The file is built by `desktop/build-installer.ps1` from commit `4b04af5e11389585c3feb0d36ef3ee8c9b03b640` (branch `fix/desktop-no-embedded-vcruntime`). The
commit that merged it into `main` (`4d153dc18755f3b41c276ef5cd62cc15da830f73`) differs from that build commit only by documentation: nothing that the installer embeds changed. The
installer is built on the maintainer's computer and is not produced by the automated checks.

## Prerequisite: Microsoft Visual C++ Redistributable

The embedded engine needs the **Microsoft Visual C++ Redistributable (x64) 14.44.35229 or newer**. ModularCV does **not** include it: Microsoft distributes it
itself (https://aka.ms/vc14/vc_redist.x64.exe), you install it, and installing it may need **administrator rights**. ModularCV never downloads or installs it.
Many Windows 11 computers already have it. If it is missing or too old, the installer warns before installing, and the application explains the problem instead of
starting its engine. Your workspaces are not affected.

## What is in this beta

- Open a workspace (or the built-in fictional demonstration), check the fact base, browse and edit profile, experiences, education, skills and offers.
- Requirement matrix, tailoring plan, `.tex` generation, PDF compilation with `pdflatex`, packages that freeze the evidence.
- A review screen that shows the exact PDF, the warnings and the engine's status, and records your own approval or refusal after explicit steps.
- French and English interface, light and dark themes, offline read-only environment diagnostics.
- Per-user installer (no administrator rights); the uninstaller keeps your workspaces and, by default, the application's data.
- No network access by the application, no telemetry, no update check.

## What you should know

- **An approval is your own decision, recorded in a local file that is not signed.** `READY_TO_SEND` proves the process, not the candidate
  ([STATUSES.md](STATUSES.md)).
- Git and LaTeX are optional and are never installed for you. The diagnostics only check that they can be found.
- The installer is unsigned. If WebView2 is missing, the installer downloads Microsoft's bootstrapper.
- This installer was tested on a Windows 11 virtual machine made from a stripped-down image (not a stock installation): without the Redistributable, with an
  older one, and with a current one (16 of 16 and 29 of 29 journey checks, restart, silent uninstall; record in [INSTALL.md](INSTALL.md)). An earlier candidate
  (which carried Microsoft's runtime file; withdrawn) was also exercised on the developer's Windows 11 Home. **Not tested:** a stock Windows 11 installation, Windows 10, TeX Live. The
  automated checks on GitHub skip the tests that need LaTeX, so PDF and approval tests are not run there (they were run locally with MiKTeX).
  Full list in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Under the hood

Tauri 2 (Rust), React and TypeScript front end, the unchanged Python engine packaged with PyInstaller (onedir), pdf.js for the PDF view. Installed
size about 27 MB. The engine runs from a closed list of operations, without a shell, with time limits. Licences of the components are listed
in `THIRD_PARTY_NOTICES.md`, and their licence texts and copyright notices are in `THIRD_PARTY_LICENSES.txt`, both installed under `legal\`.
Some licensing points are not settled; see [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Versions

| Part | Version |
|---|---|
| ModularCV Desktop | `0.5.0-beta.1` |
| ModularCV engine and CLI inside it | `0.2.0` (tag `v0.2.0` is unchanged) |

## Feedback

Open an issue on the GitHub repository with the steps, your Windows version, the diagnostics summary and the exact message. **Never attach your
real CV, facts or PDFs.**
