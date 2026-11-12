# CV statuses and what an approval means

Français : [LISEZMOI.fr.md](LISEZMOI.fr.md)

## The three statuses

The status of a package is **computed by the engine every time you ask** (the **Refresh status** button, or when you open the screen). It is
never stored and never typed. The application shows the engine's own word.

| Status | Meaning | Typical reasons |
|---|---|---|
| `NEEDS_REVIEW` | The evidence is intact but incomplete, or things moved on since the package was made. | No review yet (`HUMAN_REVIEW_REQUIRED`, `REVIEW_FILE_MISSING`); no PDF (`FINAL_DOCUMENT_MISSING`); a source file changed since packaging (`SOURCE_CHANGED_SINCE_PACKAGING`); the PDF or another file changed (`ARTIFACT_CHANGED_SINCE_PACKAGING`); Git cannot verify the recorded commit. |
| `READY_TO_SEND` | Every check below passes **right now**, and you approved this exact PDF. | |
| `BLOCKED` | The package or its chain of evidence cannot be trusted. | You **refused** the document; the package files were altered or are inconsistent; the package is stale. |

A `.tex` file alone is never `READY_TO_SEND`. The document that can be approved and sent is the PDF.

## What `READY_TO_SEND` requires

All of these, re-derived on every check: your source files are present, valid and still equal to what was frozen in the package and to the
Git commit; the facts used are still confirmed; the plan, the `.tex` and the metadata agree with each other; the PDF is the one the package
recorded; the PDF was produced by compiling the package's own `.tex` (a PDF supplied from elsewhere can never reach `READY_TO_SEND`); and an
approval file names this exact PDF.

If you change anything afterwards (a fact, an offer, the `.tex`, the PDF, even one byte), the status drops back. That is deliberate.
Restoring the exact original bytes restores the evidence.

## What an approval is, and is not

**Your approval is a decision you take on your own computer, recorded in a plain local file that is not signed and not authenticated.**

- The file is `applications\<package>\cv\cv-quality-review.json` in your workspace. It contains your decision, the name you typed, the
  fingerprint of the PDF you looked at, and the warnings shown to you.
- Anyone who can write to your workspace folder, or you with a text editor, can create or edit such a file. The application does not
  prove who wrote it and does not prove a person was at the keyboard. It is **not** a digital signature and not a certificate.
- What the engine does check is that the file names *this* package and *this exact PDF*. A different PDF, or an altered package, makes the
  approval stop counting.
- To make approval deliberate, the screen needs your explicit steps (every page seen, two confirmations, your name, the first 12 characters of the
  PDF fingerprint, a final dialog). These steps guard against accidents, not against someone who deliberately writes the file by hand.

**`READY_TO_SEND` proves the process, not the candidate.** It does not say that you meet the job's requirements: unsatisfied required requirements
stay listed in the package and on the review screen. It does not check spelling, tone or truth beyond what the fact base confirms. Read the PDF
yourself before you send it.

The application never sends anything anywhere and never commits to your Git repository on its own.
