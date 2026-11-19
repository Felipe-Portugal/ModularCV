# Graphical approval in the Desktop application: design and limits

Status: **implemented in the Desktop adapter, with no change to the Python engine (0.2.0) and none to `package approve`.**
This file replaces the earlier proposal, which assumed an engine change was needed.

## Study: is an engine change needed?

No. The engine already provides everything an approval needs, and the property that matters is inside it:

- `package.review_summary()` re-derives, from the disk, the document hash, the plan/assembly/`.tex` hashes, the items to
  acknowledge (unmet required requirements, pending directives, warnings, page verdict) and the status.
- `package.record_review()` refuses a package that is not reviewable (any reason other than `HUMAN_REVIEW_REQUIRED`), copies every
  field of the review from the verified package (never from the caller), and creates the file exclusively (`REVIEW_EXISTS`).
- `package.status()` recomputes `READY_TO_SEND` from the evidence on every call.

What `record_review()` does **not** do is prove that a person decided, or that the person saw what is now on disk. Its docstring
leaves the human act to the caller; the command line supplies it with an interactive terminal and a typed hash prefix. Being able
to call it is not a safeguard. The adapter therefore adds those two guarantees around it, and nothing else.

## What the adapter (`package_approve`) does

1. **Explicit acts, all required, none defaulted**: a `decision` that is exactly `APPROVED` or `REJECTED`, a reviewer name, two
   explicit confirmations (`confirm_examined`, `confirm_final`, strictly the boolean `true`), the 12 characters of the PDF SHA-256
   typed by the person, the review context the person was shown and the hash of the bytes the screen displayed.
2. **Re-read the disk under the workspace lock** (`review_summary()`), then refuse unless: the package has a PDF; the engine's
   reasons are only `HUMAN_REVIEW_REQUIRED` (so provenance, sources, chain and snapshot are all valid); the *review context* still
   equals the one displayed; the displayed bytes still hash to the on-disk PDF; and the typed prefix is the start of that hash.
   The review context is a fingerprint of the package name, the CV identity, the document (hash, size, pages, origin, page
   verdict), the plan/assembly/`.tex` hashes, the whole to-acknowledge block and the engine's reasons.
3. **Record through the engine** (`record_review()`), with a fixed note saying it came from the Desktop review screen (plus the
   person's optional note). No terminal is simulated; `package approve` is untouched and still refuses without one.
4. **Check what was written** against what was compared in step 2. If they differ (a change landing in the few milliseconds
   between the two reads), the adapter withdraws the file it has just created itself and reports `REVIEW_CONTEXT_CHANGED`: an
   approval of something the person did not see is never left behind.
5. **Recompute and report**: the answer carries a fresh `package.status()`. The screen shows that verdict, never its own. An
   approval that the engine does not turn into `READY_TO_SEND` is shown as such.

The screen enforces what only a screen can: nothing is ticked or filled in, the confirmation is disabled until the exact PDF is
displayed (hash verified in the browser against the engine's) and every page has been rendered, a final confirmation dialog
precedes the write, and a refused or stale decision offers to reopen the review.

## Limits that remain (stated, not hidden)

- **No proof of a human.** The approval is still an unsigned JSON file. The adapter operation can be called by any code that
  can talk to the application's backend or write the workspace; the web view has no shell access, the operation list is closed,
  and the screen, the typed hash and the recorded note make an unattended approval harder, not impossible. Keep the workspace
  private and under Git.
- **Residual concurrency window.** Between independent processes the lock is cooperative and does not cover an external editor.
  A file changed between the context comparison and the engine's own read is caught by step 4 and withdrawn; a change after the
  write is caught by the status recomputation (the evidence no longer matches, so the status cannot stay `READY_TO_SEND`).
  What cannot be excluded is the instant between two reads performed by two different processes with no common lock.
- **Withdrawal deletes one file**: only the review file the adapter has just created exclusively, under its own lock, and only
  when it contradicts the context that was compared.
- **Semantics**: as before, `READY_TO_SEND` proves the process, not that the candidate meets the job's requirements.

No change to `docs/PACKAGE.md` was made: the engine's rules are unchanged. Its sentence that `package approve` is the human step
still describes the command; the Desktop review screen is a second entry point that applies the checks above.
