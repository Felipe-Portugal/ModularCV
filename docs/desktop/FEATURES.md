# What ModularCV Desktop does

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

ModularCV Desktop is a window around the ModularCV engine. It adds **no rule of its own**: every read, write and verdict goes through the real
engine, and the engine's answer is shown as it is. If you know the command line, it is the same chain with buttons.

## The chain

1. **Facts.** Your CV is built only from facts you confirmed. The dashboard runs **Check facts** and shows the engine's verdict.
2. **Data.** Screens for the profile, experiences, education, skills and job offers. Reading is the default; **Edit** turns a screen into a
   form with an "unsaved changes" indicator and a confirmation before leaving.
3. **Tailor my CV.** For a job offer: the **requirement matrix** (what your facts cover directly, adjacently or not at all), the **tailoring plan**,
   the **`.tex`** file, the **PDF** (needs `pdflatex`), and a **package** (needs Git) that freezes sources, plan, `.tex` and PDF together.
4. **Review my CV.** The exact PDF of the package, page by page, with its fingerprint, the warnings, the unsatisfied requirements, and the
   status computed by the engine. Approval or refusal is explicit and deliberate ([STATUSES.md](STATUSES.md)).
5. **History.** Packages and generated PDFs; open a PDF with your usual viewer, show a file in Explorer.
6. **Settings.** Light, dark or system theme; French or English; **Environment diagnostics** (offline, read-only).

## What it will not do

- It does not invent facts, and it does not say you fit a job. It shows which of your confirmed facts cover which requirement.
- It does not send, upload or publish anything, and has no network access of its own.
- It does not install Git or LaTeX, does not commit to your repository, and does not approve a CV for you.
- It does not sign anything: an approval is a local decision in an unsigned file ([STATUSES.md](STATUSES.md)).

## Privacy

Everything stays on your computer. There is no account, no telemetry, no update check. The application reads and writes only the workspace
folder you open and its own data folder (`%LOCALAPPDATA%\org.modularcv.desktop`). The embedded engine accepts a closed list of operations and is
started without a shell and with time limits. Windows file access is limited to the folder picker you use and the workspace you choose.

## Build and licences

The installer carries the unchanged engine (`mcv-engine.exe`, a PyInstaller build), the application (Tauri 2, Rust, React) and the licence texts
under `legal\` in the installation folder (`LICENSE`; `THIRD_PARTY_NOTICES.md`, the inventory of third-party components; `THIRD_PARTY_LICENSES.txt`, their licence texts and notices). ModularCV is released under the MIT licence.
