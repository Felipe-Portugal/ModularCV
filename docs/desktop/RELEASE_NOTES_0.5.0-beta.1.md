# ModularCV Desktop 0.5.0-beta.1, release notes

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

First beta of ModularCV Desktop, a Windows application for the ModularCV engine. **Prepared, not yet published: there is no Desktop release yet.**
The command-line release `v0.2.0` is unchanged; the engine inside the installer is that same `0.2.0` engine.

## Download (not available yet)

The installer is not published. It will be downloadable from the **Releases** page of the GitHub repository after the official publication.

The installer tested so far is `ModularCV Desktop_0.5.0-beta.1_x64-setup.exe`, 9.56 MiB, unsigned. Its SHA-256, for information only:

```
F1DA86139CDA4125FCCE4E2D171256791F29E7CE29A170CE28BFF4764A1F14B8
```

This value is **not** the final fingerprint of the future release: the final installer will be identified and verified when the release is made,
and its fingerprint will be published with it. Check the file before running it ([INSTALL.md](INSTALL.md)). Windows SmartScreen will warn because the installer is not signed.

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
- Tested on Windows 11 on a virtual machine made from a stripped-down image, and on the developer's Windows 11 Home. **Not tested:** a stock
  Windows 11 installation, Windows 10, TeX Live. Full list in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Under the hood

Tauri 2 (Rust), React and TypeScript front end, the unchanged Python engine packaged with PyInstaller (onedir), pdf.js for the PDF view. Installed
size about 27 MB. The engine runs from a closed list of operations, without a shell, with time limits. Licences of the components are listed
in `THIRD_PARTY_NOTICES.md`, installed under `legal\`.

## Versions

| Part | Version |
|---|---|
| ModularCV Desktop | `0.5.0-beta.1` |
| ModularCV engine and CLI inside it | `0.2.0` (tag `v0.2.0` is unchanged) |

## Feedback

Open an issue on the GitHub repository with the steps, your Windows version, the diagnostics summary and the exact message. **Never attach your
real CV, facts or PDFs.**
