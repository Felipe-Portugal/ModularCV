# First start

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

This page walks you through the first ten minutes with a **fictional** workspace, so you can see every screen without touching your own data.
Install the application first ([INSTALL.md](INSTALL.md)).

## 1. Check your environment

Open **Settings** (language and theme are there too) and read **Environment diagnostics**. It shows, offline and read-only:

- the embedded engine and its version;
- whether Git is found, and whether the open folder is a Git repository;
- whether `pdflatex` is found, and whether PDF compilation can be attempted.

"Found" only means the program was found. It does not prove it is correctly configured (see [KNOWN_ISSUES.md](KNOWN_ISSUES.md)).

![Settings and environment diagnostics](img/settings-diagnostics.png)

## 2. Open the demonstration workspace

On the dashboard, choose **Demo workspace**. The application copies a fictional example into
`%LOCALAPPDATA%\org.modularcv.desktop\demo-workspace`. Then choose **Check facts**: the engine reads the fact base and shows its verdict
(how many facts are confirmed, derived, not confirmed or withdrawn, and which can be published in a CV).

![Dashboard with the facts check](img/dashboard-facts.png)

A second button creates a workspace with a deliberately broken fact file, to show how errors are reported. Nothing is ever overwritten:
an existing folder is reused as it is.

### Your own CV

On the dashboard, under **Your profiles**, give a profile name, your name and the language of your CVs, then **Create the profile**. The
application creates the folder `Documents\ModularCV\Profiles\<profile name>` with an empty, valid fact base and a profile. You do not
write any file by hand.

**Import a CV** then opens:

1. Choose a file (PDF, `.docx` or text) or paste the text of a CV you already have. The text is read on your computer and shown to you; correct
   it if needed.
2. **Analyse the text**: the application proposes your contact details, your experience, education and skills. Lines it could not place are
   listed at the end.
3. Correct, complete or delete the entries. Tick what you confirm to be accurate, and give the date you confirm it. For each contact detail,
   choose whether it is saved and whether it may appear on a CV.
4. **Save into my profile**. Confirmed entries enter your CVs. Unconfirmed ones are kept as facts to confirm and stay out of your CVs.

The import confirms nothing by itself and uses no network and no model. To use a workspace you manage yourself (for example a private Git
repository, see the engine's [WORKSPACE.md](../WORKSPACE.md)), use **Existing folder (advanced)** > **Choose a folder**. A folder with no
profile yet can be initialised from the application. Keep any workspace **outside** the application's own data folders.

A profile kept by the application is not a Git repository: its packages (step 5 of "Tailor my CV") keep an exact copy of your sources,
checked by fingerprint, where a Git workspace names a commit.

## 3. Look at, and edit, the data

The profile, experiences, education, skills and job offers screens read the workspace files through the engine. **Edit** turns a screen into
a form; unsaved changes are flagged and you are asked before you leave.

![Experiences](img/experiences.png)

## 4. Adapt a CV to an offer

Open **Tailor my CV** and follow the steps:

1. Pick a job offer and choose **Analyse requirements**. The application shows the **requirement matrix**: each requirement is *Demonstrated*, *Nearby* or *Absent* against your confirmed facts (the engine's `DIRECT`, `ADJACENT`, `ABSENT`), and a requirement you must not claim is flagged. Unmet required requirements stay listed.
2. Build the **tailoring plan**.
3. Generate the **`.tex`** file. This works without any LaTeX installation.
4. With `pdflatex` available, compile a **PDF**.
5. Create a **package**. In a Git repository the sources must be committed first (the application never commits); without Git, the
   package keeps a copy of them.

![Requirement matrix](img/matrix.png)

The package freezes the sources, the plan, the `.tex` and the PDF together, and records the Git commit of your sources, or keeps a copy of
them when the workspace has no Git.

## 5. Review and approve

Open **Review my CV**. The screen shows the exact PDF the package refers to, with its fingerprint, the warnings, and the status computed by
the engine. To approve you must, explicitly: view every page, tick the two confirmations, type your name, type the first 12 characters of the
PDF fingerprint, choose **Approve** or **Refuse**, and confirm in a last dialog. Nothing is pre-ticked and nothing happens by itself.

![Review screen](img/review.png)

Read [STATUSES.md](STATUSES.md) before relying on `READY_TO_SEND`. In short: **approval is your own decision, recorded in a local file that is
not signed.**

## 6. History

**History** lists packages and generated PDFs. Closing and reopening the application loses nothing: everything is in your workspace files.
