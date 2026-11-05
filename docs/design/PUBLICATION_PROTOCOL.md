# Publication protocol (PUB-0): a plan, not an execution

Status: **written, not executed.** PUB-0 authorised read-only audits and local simulations only. Nothing was pushed, renamed, created, deleted,
tagged, released or made public; no GitHub setting was changed. Every gate below needs the human authorisation named in "Authorisations".
This document is a maintainer document: it is listed in `PUBLIC_EXCLUDE.txt` and is not part of the public tree.

## 1. Facts observed (read-only, PUB-0)

Observed on GitHub with GET requests and `git ls-remote` / a mirror clone into a temporary folder:

| Subject | Observation |
|---|---|
| Repository | `$OWNER/ModularCV`, id `1441249060`, **private**, default branch `main`, not a fork, no forks (`forks_count` 0, `network_count` 0), not archived |
| Created / last push | 2026-10-31 (created 20:56 UTC, pushed 21:16 UTC) |
| Refs | `HEAD` and `refs/heads/main` only, both `0a553e11520bd672f1c0068e4ddc012511a4e292`; **no `refs/pull/*`**, no tags |
| History | **one commit**, `0a553e1` ("Initial release ... 0.1.0"), 30 files, includes `skills/cv-panel/normes-ets.md` (blob `128616d76ff9f65a09457aa3edbc6a52afb6937e`, 4748 bytes) |
| Pull requests / issues / releases | 0 / 0 / 0 |
| Actions / workflows / runs / artifacts | 0 / 0 / 0 / 0 |
| Pages, webhooks, deploy keys, environments, deployments, autolinks | none |
| Git LFS | none (no `filter=lfs` in `.gitattributes`) |
| Collaborators | the owner only |
| Branch protection and rulesets | not available on this private repository (HTTP 403 "Upgrade to GitHub Pro or make this repository public"); `main` is not protected |
| Exposure so far | events: only the repository creation; no public event; traffic: 5 clones / 2 unique cloners in the last 14 days, 0 views (a private repository: the owner's machines) |
| Local `origin` | `${SSH_USER}@github.com:$OWNER/ModularCV.git`; local ref `origin/main` = `0a553e1`, equal to the real remote ref |
| API identity | the token authenticates as `$OWNER` (id 124311477, the id of the no-reply address); `gh auth status` labels the keyring entry differently; token scopes `gist, read:org, repo, workflow` (no `delete_repo`) |

No other repository of the account was opened, listed or queried.

## 2. What GitHub documents (and what it does not)

From GitHub's own page "Removing sensitive data from a repository":

- After rewriting history and force-pushing, the old commits "may still be accessible": in clones and forks, **directly by SHA in cached views**, and through pull
  requests that reference them.
- Removing the cached views and the pull-request references requires **contacting GitHub Support**, which then dereferences pull requests, runs a garbage
  collection on the server and removes cached views.
- Support "won't remove non-sensitive data" and assists only where the risk cannot be mitigated by rotating credentials. **`normes-ets.md` is not a secret
  and not personal data, so there is no reason to expect that Support will purge it; this is a hypothesis to be asked, not a guarantee.**
- Commits that exist in forks stay accessible there; GitHub cannot give the forkers' contact details.

From "Renaming a repository": web traffic and `git clone|fetch|push` aimed at the old name are redirected to the renamed repository; **if a new repository
later takes the original name, the redirects stop working.** From "Deleting a repository": deletion cannot be undone for team permissions, a private
repository's forks are deleted with it, and some repositories can be restored **within 90 days**. Restoration is not possible if the repository belonged to
a non-empty fork network.

Local fact, verified in a temporary bare repository (PUB-0 simulation): after `git push --force` of the clean snapshot over a copy of the old history, `main`
pointed to the new commit, but the old commit and the school-file blob were **still present in the object store** (reported by `git fsck --unreachable`)
until `git gc --prune=now` ran. A server that has not collected garbage behaves the same way. Hence: a force-push moves a ref; it does not delete objects.

Not documented by GitHub, therefore a risk and not a promise: the delay before unreachable objects are collected, and whether an unreachable commit can still be
fetched or viewed by SHA after a force-push in this particular repository. It can only be probed after the fact (section 5, G2-A probe).

## 3. Strategies

| | A. Keep the repository, force-push the clean snapshot over `main` | B. Rename the old repository (private archive), create a new `ModularCV` | C. Delete the old repository, create a new `ModularCV` |
|---|---|---|---|
| Old objects absent from the public repository | **Not guaranteed**: they stay on GitHub's storage, reachable by SHA until a server-side collection that only Support can force, and Support is documented to decline non-sensitive data | **Yes**, by construction: a different repository id, not a fork, receives only the snapshot's objects | **Yes**, same as B |
| Verifiable before going public | Only by probing the old SHAs (a positive probe blocks; a negative one proves little) | **Yes**: a fresh mirror clone of the new repository shows exactly the objects pushed, and the old SHAs answer 404 | Yes |
| Keeps the name `$OWNER/ModularCV` | Yes | **Yes** (the new repository takes it) | Yes |
| Keeps the repository id and identity | Yes | No (new id; the archive keeps `1441249060`) | No |
| Complexity | Low, but the cleanup is not under our control | Medium: rename, re-point local remote, create, push | Medium |
| Reversibility | The force-push is not undoable remotely (the old commit is not reachable by ref); nothing is lost locally | Rename undoable only while the name is free; creation undoable by deleting an empty repository | **Irreversible after 90 days**; the remote copy is lost |
| Main risks | Publishing with the old commit still fetchable by SHA; relying on Support; hidden references | A stale local `origin` pointing at the old name would, after the new repository takes the name, push the private history to it; redirects stop (expected); confusing names | Loss of the only remote copy (mitigated by the local backups); permanent loss after 90 days |
| Authorisation | force-push, visibility change | rename, create, push, visibility change | delete, create, push, visibility change |

**Recommendation: B.** It is the only strategy that makes "the public repository holds nothing but the clean snapshot" *verifiable* and not dependent on a server-side
purge that GitHub does not promise for this kind of content. It is non-destructive: the old repository stays private under another name, with its content, so
nothing is lost and the choice between keeping or later deleting the archive (C) stays open. A is kept as a fallback only if it passes the probe of G2-A and
Support confirms in writing, which is unlikely. **A rename needs its own human authorisation (technical reason: the old objects cannot be separated from the
repository that holds them).**

## 4. Backups and what they protect

| Backup (local, outside any synchronised folder) | Command | Protects |
|---|---|---|
| Mirror of the current remote | `git clone --mirror ${SSH_USER}@github.com:$OWNER/ModularCV.git <backup>/ModularCV-remote-0a553e1.git` | the exact remote state (one commit) |
| Bundle of the development repository | `git -C <dev> bundle create <backup>/modularcv-dev.bundle --all` then `git bundle verify` and `sha256sum` | the whole private development history (25 commits at PUB-0), including the quarantined-file decisions |
| Remote metadata | `gh api repos/$OWNER/ModularCV > <backup>/repo-before.json` | id, visibility, settings |
| Clean snapshot | the temporary folder of G0 and its `PUBLIC_INVENTORY.sha256` | the thing to publish |

These backups contain the school summary and the private history: keep them private, never in a repository, never on a shared or synchronised drive.

## 5. Gates

Conventions: `DEV` is the development repository; `WORK` a new empty temporary folder; commands run in `bash`; `OWNER` is the GitHub account that owns the repositories (kept out of this file so that the tree holds no handle); `SSH_USER=git` (the SSH user of GitHub remotes, written as a variable so that the privacy scan does not read the URL as an e-mail address). `OLD_ID=1441249060`,
`OLD_COMMIT=0a553e11520bd672f1c0068e4ddc012511a4e292`, `OLD_BLOB=128616d76ff9f65a09457aa3edbc6a52afb6937e`,
`SNAP_TREE=11f9c27a5026605e5f1fa52be6af9fbab17875ce`. **Never run a push, a rename or a creation from `DEV`**: `DEV` still carries the private history.

### G0. Final verification (read-only; no authorisation beyond running it)

Entry: the maintainer asks for the publication run. Checks:

```bash
cd "$DEV"
git branch --show-current                                   # main
git merge-base --is-ancestor 794b498 HEAD && echo ok         # HEAD descends from the validated candidate
test -z "$(git status --porcelain)" && echo clean
git tag | wc -l                                             # 0
grep -m1 '^version' pyproject.toml; grep -m1 requires-python pyproject.toml     # 0.2.0 ; >=3.12,<3.15
sha256sum ../_quarantine/legacy_import.py                   # 5c73e936d25ce534dc13b8ef77005630f1643f96092140a3b690b190a2504106
git ls-remote origin                                        # HEAD and refs/heads/main = OLD_COMMIT only
gh api repos/$OWNER/ModularCV --jq '{id,private,default_branch,fork,forks_count}'   # OLD_ID, true, main, false, 0
gh api user --jq .login                                     # $OWNER
# the snapshot, from the committed HEAD:
mkdir "$WORK" && cd "$WORK" && git -C "$DEV" archive HEAD | tar -x
grep -vE '^(#|$)' PUBLIC_EXCLUDE.txt | tr -d '\r' | while read -r f; do rm -f "$f"; done
git init -q -b main && git add -A
GIT_AUTHOR_NAME=ModularCV GIT_COMMITTER_NAME=ModularCV GIT_AUTHOR_EMAIL=124311477+$OWNER@users.noreply.github.com \
GIT_COMMITTER_EMAIL=124311477+$OWNER@users.noreply.github.com git commit -q -m "ModularCV 0.2.0: initial public snapshot"
git rev-parse 'HEAD^{tree}'                                 # must equal SNAP_TREE (else: the public files changed; re-run the M8-B checks)
git ls-files -z | xargs -0 sha256sum | diff - "$DEV/docs/design/PUBLIC_INVENTORY.sha256" && echo inventory-ok
git rev-list --count HEAD; git remote | wc -l               # 1 ; 0
git rev-list --objects --all | grep -c "$OLD_BLOB"           # 0 (also: git cat-file -e $OLD_BLOB must fail)
python -m modularcv privacy --root . --deny-file <outside-deny-file> --history     # 0 finding(s)
```

If the public files changed on purpose, the tree differs: then rebuild wheel and sdist and repeat the M8-B journeys before continuing.
PASS: every line as annotated. BLOCKED: any difference. Side effects: none. Reversal: not applicable.

### G1. Backups (local only)

Run the four backups of section 4, `git bundle verify`, record the SHA-256 of the bundle. PASS: all verify. BLOCKED: any failure. Reversal: delete the
backup files. This gate changes nothing on GitHub.

### G2. Treatment of the remote history: strategy B

**Authorisation required: "rename and create" (G2-1 and G2-2) as one explicit approval.** Entry: G0 and G1 PASS.

```bash
# G2-0 the target name must be free (read-only)
gh api repos/$OWNER/ModularCV-private-archive 2>&1 | head -1          # must be a 404
# G2-1 rename the old repository.  EFFECT: new URL; web and git redirects from the old name until the name is reused. REVERSIBLE only while the old name is free.
gh repo rename ModularCV-private-archive -R $OWNER/ModularCV --yes
gh api repos/$OWNER/ModularCV-private-archive --jq '{id,private,full_name}'   # id 1441249060, private true
# G2-1b IMMEDIATELY detach the development repository from the redirect: otherwise, once the new repository takes the name, a push from DEV would reach it
git -C "$DEV" remote set-url origin ${SSH_USER}@github.com:$OWNER/ModularCV-private-archive.git
git -C "$DEV" remote -v                                                         # only the archive URL
# G2-2 create the new, EMPTY, PRIVATE repository (no README, no licence, no .gitignore, no template: the snapshot brings its own)
gh repo create $OWNER/ModularCV --private --description "Modular, traceable, fact-first workflow and guard rails for CVs and cover letters."
gh api repos/$OWNER/ModularCV --jq '{id,private,fork,size}'            # id != 1441249060, true, false, 0
git ls-remote ${SSH_USER}@github.com:$OWNER/ModularCV.git                      # empty
```

PASS: ids as annotated, the old repository private under the new name, the new one empty and private. BLOCKED: the new id equals the old one, or the name is
taken. Reversal: before G3, delete the empty new repository (requires the `delete_repo` scope or the web UI; deletion is restorable for 90 days) and rename
the archive back. After G3 reversal is a deletion plus recreation. **The Git history of the archive is never touched.**

*G2-A probe (only if the maintainer insists on strategy A; do not combine with B).* Build the snapshot as in G0; push it with an explicit lease
(`git push --force-with-lease=main:0a553e1 origin HEAD:main`); then probe, as GET: `gh api repos/$OWNER/ModularCV/commits/$OLD_COMMIT`,
`gh api repos/$OWNER/ModularCV/git/blobs/$OLD_BLOB`, `git ls-remote`, and open `https://github.com/$OWNER/ModularCV/commit/$OLD_COMMIT`
while signed in. Any answer other than 404/422 is BLOCKED for publication. A 404 is not proof (a cache may be warm elsewhere). Asking GitHub Support to purge is a
request, not an entitlement (section 2). **The force-push is irreversible in practice.**

### G3. Publication of the code (the repository stays PRIVATE)

**Authorisation required: "push the snapshot to the new private repository".** Entry: G2 PASS. Run only in `WORK` (never in `DEV`).

```bash
cd "$WORK"
git remote add origin ${SSH_USER}@github.com:$OWNER/ModularCV.git
git remote -v; git log --oneline; git rev-list --objects --all | grep -c "$OLD_BLOB"       # one remote line pair; 1 commit; 0
git push --dry-run origin main:main                                                         # a creation of main, nothing else
git push origin main:main                                                                   # NO --force, NO --mirror, NO --tags
```

PASS: `git ls-remote origin` shows `refs/heads/main` = the local commit and nothing else. BLOCKED: any rejection or extra ref. Effect: the content is on GitHub, private.
Reversal: delete the repository (restorable 90 days) and repeat G2-2; the content has been seen only by the owner.

### G4. Confidentiality verification (before any visibility change)

```bash
rm -rf "$CHECK" && git clone --mirror ${SSH_USER}@github.com:$OWNER/ModularCV.git "$CHECK" && cd "$CHECK"
git for-each-ref                                            # main only; no refs/pull, no tags
git rev-list --all | wc -l                                  # 1
git cat-file -e "$OLD_BLOB" || echo absent                  # absent (this is the point)
git cat-file -e "$OLD_COMMIT" || echo absent                # absent
git rev-list --objects --all | grep -ciE "normes-ets|PROJECT_STATE|PREPUBLICATION|PUBLIC_EXCLUDE|PUBLIC_SNAPSHOT|legacy_import|_quarantine|\.pdf$"    # 0 (the name normes-ets appears in SKILL.md text, not as a path)
# privacy of the clone, with the outside deny list, tree and history
git worktree list >/dev/null; mkdir ../t && git archive HEAD | tar -x -C ../t && python -m modularcv privacy --root ../t --deny-file <deny> --history
gh api repos/$OWNER/ModularCV/commits/$OLD_COMMIT 2>&1 | head -1     # 404/422
gh api repos/$OWNER/ModularCV/git/blobs/$OLD_BLOB 2>&1 | head -1      # 404
gh api repos/$OWNER/ModularCV --jq '{fork,network_count,forks_count,visibility,license:.license.spdx_id}'   # false 0 0 private MIT
gh api repos/$OWNER/ModularCV-private-archive --jq .visibility        # private
```

Then, from a clean virtual environment on 3.12 or later, `pip install` a wheel built from the clone and run `python -m modularcv --help` (optional, recommended once).
Review by a human, in the web UI of the private repository: README rendering, the licence panel, the file list against `PUBLIC_INVENTORY.sha256`.
**BLOCKED if** any old object is reachable (even once), the history has more than one commit, a private term is found, or the archive is not private.
Side effects: none. Reversal: not applicable.

### G5. Visibility

**Authorisation required, separate and explicit: "make $OWNER/ModularCV public".** Entry: G4 PASS and the answers to the decisions below.
Immediately before: repeat the three decisive checks of G4 (`git for-each-ref`, the old SHAs, privacy).

```bash
gh repo edit $OWNER/ModularCV --visibility public --accept-visibility-change-consequences
# afterwards, unauthenticated (no token):
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/$OWNER/ModularCV                        # 200
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/$OWNER/ModularCV/commits/$OLD_COMMIT     # 404 or 422
git ls-remote https://github.com/$OWNER/ModularCV.git                                                           # main only
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/$OWNER/ModularCV-private-archive         # 404 (private)
```

After the change, in the web UI (human): enable private vulnerability reporting, secret scanning and push protection, and protect `main` (these are available on a
public repository on the free plan); keep Actions without workflows. Note the README clone URL still reads `<your-user>`; changing it is a normal commit
and a normal push to the new repository, after the publication.
**Irreversibility:** once public, any copy (clone, mirror, search index, archive service) may persist. Going back to private is **not** an erasure.
This is why every earlier gate must PASS first, and why nothing may be made public "to test".
Reversal: `gh repo edit ... --visibility private` stops new access only.

### G6. Release `0.2.0`

**Authorisation required, separate: "tag and release 0.2.0".** Entry: G5 done and verified. From a fresh clone of the public repository (not `DEV`):

```bash
git clone ${SSH_USER}@github.com:$OWNER/ModularCV.git rel && cd rel
git -c user.name=ModularCV -c user.email=124311477+$OWNER@users.noreply.github.com tag -a v0.2.0 -m "ModularCV 0.2.0"
python -m build --outdir ../dist . && (cd ../dist && sha256sum *)       # in a virtual environment, as in M8-B
git push origin v0.2.0
gh release create v0.2.0 ../dist/* --title "ModularCV 0.2.0" --notes-file <notes>
```

The notes must state: Python 3.12 to 3.14; MiKTeX/Windows exercised; TeX Live/Linux, macOS and ATS **not verified**; origin of the PDF and the reviewer are
**not authenticated**; the archives' SHA-256. No PyPI upload. Reversal: delete the release and the tag (`git push --delete origin v0.2.0`); anything downloaded
meanwhile stays out there.

## 6. Authorisations and decisions (none was given in PUB-0)

1. Strategy (recommended B) and the rename of the old repository, with the archive name `ModularCV-private-archive` (or another).
2. "Create `$OWNER/ModularCV` private, empty" (G2-2) and "push the snapshot" (G3).
3. The public identity: the commit author is `ModularCV <124311477+$OWNER@users.noreply.github.com>`; confirm or change **before** G3 (changing it later rewrites the public history).
4. The list of `PUBLIC_EXCLUDE.txt` and the public documents (open decision 23).
5. The description line, topics, and the settings after publication.
6. "Make it public" (G5), separately, after reading the G4 report.
7. The version tag and release (G6); the number (open decision 24).
8. Whether to ask GitHub Support anything about the old objects (only meaningful for A), and whether the archive is kept or later deleted (C).
9. Whether the 25 local commits of `DEV` are pushed to the *archive* (never to the public repository).

## 7. Risks left after the protocol

- GitHub is trusted to keep a private repository private; the archive keeps `normes-ets.md` and the private history on GitHub's servers.
- Anyone who cloned the old repository holds the old history (the owner's machines and the copies of PUB-0 only: 5 clones, 2 unique cloners in the last 14 days).
- A temporary public exposure cannot be recalled (section G5).
- Cached or third-party copies after G5 cannot be removed by this protocol.
- The school-file *name* appears in the public tree (an optional, user-supplied file in `SKILL.md`; an exclusion line in `MANIFEST.in`; two tests): this reveals no content.
- The chosen archive name and the redirects: a link to `ModularCV` made before the rename lands on the new repository once it exists; links to the old commit
  hash (there are none in the public tree) would 404.
