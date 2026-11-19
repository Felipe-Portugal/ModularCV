# What ModularCV Desktop does

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

ModularCV Desktop is a window around the ModularCV engine. It adds **no rule of its own**: every read, write and verdict goes through the real
engine, and the engine's answer is shown as it is. If you know the command line, it is the same chain with buttons.

## The chain

0. **Profiles and import.** The dashboard creates a **profile** for you (a folder under `Documents\ModularCV\Profiles`) with a valid, empty
   fact base. **Import a CV** reads the text of a CV you already have (PDF, `.docx`, text, or pasted), on your computer, with no network and
   no model, and proposes entries: contact details, experience, education, skills. You correct them and tick what you confirm; only confirmed
   entries enter your CVs, the others are kept as facts to confirm. Lines the reading could not place are listed, never dropped silently.
1. **Facts.** Your CV is built only from facts you confirmed. The dashboard runs **Check facts** and shows the engine's verdict.
2. **Data.** Screens for the profile, experiences, education, skills and job offers. Reading is the default; **Edit** turns a screen into a
   form with an "unsaved changes" indicator and a confirmation before leaving.
3. **Tailor my CV.** For a job offer: the **requirement matrix** (what your facts cover directly, adjacently or not at all), the **tailoring plan**,
   the **`.tex`** file, the **PDF** (needs `pdflatex`), and a **package** that freezes sources, plan, `.tex` and PDF together (in a Git repository, the sources must be committed; without
   Git, the package keeps an exact copy of them).
4. **Review my CV.** The exact PDF of the package, page by page, with its fingerprint, the warnings, the unsatisfied requirements, and the
   status computed by the engine. Approval or refusal is explicit and deliberate ([STATUSES.md](STATUSES.md)).
5. **History.** Packages and generated PDFs; open a PDF with your usual viewer, show a file in Explorer.
6. **Settings.** Light, dark or system theme; French or English; **Environment diagnostics** (offline, read-only).

## What it will not do

- It does not invent facts, and it does not say you fit a job. It shows which of your confirmed facts cover which requirement.
- Importing a CV confirms nothing by itself: each entry needs your tick and the date you confirm it. The import does not understand a CV: it
  is a plain reading of headings, bullets and dates. Unusual layouts (two columns, tables, scanned pages) need corrections, which the review
  screen is for.
- It does not send, upload or publish anything, and has no network access of its own.
- It does not install Git or LaTeX, does not commit to your repository, and does not approve a CV for you.
- It does not sign anything: an approval is a local decision in an unsigned file ([STATUSES.md](STATUSES.md)).

## Privacy

Everything stays on your computer. There is no account, no telemetry, no update check. The application reads and writes only the workspace
folder you open, the profiles it keeps for you (`Documents\ModularCV\Profiles`) and its own data folder
(`%LOCALAPPDATA%\org.modularcv.desktop`). A CV you choose to import is read once and is neither copied nor changed. The embedded engine accepts a closed list of operations and is
started without a shell and with time limits. Windows file access is limited to the folder and file pickers you use, the workspace you choose and the profiles folder.

## Build and licences

The installer carries the unchanged engine (`mcv-engine.exe`, a PyInstaller build), the application (Tauri 2, Rust, React) and the licence texts
under `legal\` in the installation folder (`LICENSE`; `THIRD_PARTY_NOTICES.md`, the inventory of third-party components; `THIRD_PARTY_LICENSES.txt`, their licence texts and notices). ModularCV is released under the MIT licence.
