# Installing on Windows

Français : [INSTALL_WINDOWS.fr.md](INSTALL_WINDOWS.fr.md)

This page takes you from a bare Windows machine to a first run on the fictional example, using PowerShell. It complements
[QUICKSTART.md](QUICKSTART.md), which explains what each command does and what `READY_TO_SEND` means.

ModularCV is installed **from a clone of the repository**. There is no installer, no `.exe`, no package-index (PyPI) upload and no
desktop application. A desktop application is not part of this project today and none is promised.

**What was actually tried.** The commands below were run on Windows 11 with Windows PowerShell 5.1, Git, Python 3.14 and MiKTeX (the
only TeX distribution exercised so far). Python 3.12 and 3.13 are supported but were not used for this page. PowerShell 7, other
Windows versions, and TeX Live on Windows were not tried.

## 1. What you need

| Tool | Requirement | Check |
|---|---|---|
| Python | **3.12, 3.13 or 3.14**. Other versions are refused by `pip` (`Requires-Python: >=3.12,<3.15`). | `py -0p` lists the installed versions |
| Git | Any recent Git for Windows. Git must know your name and e-mail so you can commit the example. | `git --version` |
| MiKTeX | **Optional.** Needed only to get a PDF. Without it you still get the `.tex`, and a package stays `NEEDS_REVIEW`. | `python -m modularcv latex check` |
| Network | Needed once by `pip`, which downloads `setuptools` (version 77 or later) to build the project. There is no other dependency. | |

Install Python from [python.org](https://www.python.org/downloads/windows/) (tick the *py launcher* option) and Git from
[git-scm.com](https://git-scm.com/download/win). Open a **new** PowerShell window afterwards so the new programs are found.

## 2. Get the code

```powershell
git clone https://github.com/Felipe-Portugal/ModularCV
cd ModularCV
```

(In Windows PowerShell 5.1, `&&` does not chain commands: use one line per command, or `;`.)

## 3. Create a virtual environment

Create it **outside** the clone so that it is never mixed with the repository or scanned by the privacy check. Replace `3.14` by the
supported version you installed:

```powershell
py -3.14 -m venv $HOME\venvs\modularcv
$py = "$HOME\venvs\modularcv\Scripts\python.exe"
& $py --version
```

You do not need to activate the environment: call `$py` explicitly, as below. (If you prefer
`& $HOME\venvs\modularcv\Scripts\Activate.ps1` and PowerShell answers that running scripts is disabled, either keep using `$py`, or allow
scripts for the current window only with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.)

## 4. Install ModularCV and check it

```powershell
& $py -m pip install -e ".[dev]"
& $py -m modularcv --help
& $py -m pytest -q
```

- There is **no `modularcv` command**: always run `& $py -m modularcv ...` (or `python -m modularcv ...` once the environment is active).
- `.[dev]` adds `pytest`, the only development dependency. The engine itself uses the Python standard library only.
- The test suite uses synthetic data only and takes a few minutes.
- The installation writes a `modularcv.egg-info` folder in the clone; Git ignores it.

## 5. PDF output: MiKTeX (optional)

1. Install MiKTeX from [miktex.org](https://miktex.org/download). Open a new PowerShell window.
2. Check that ModularCV finds it:

   ```powershell
   pdflatex --version
   & $py -m modularcv latex check
   ```

   `latex check` prints `"pdflatex": "FOUND"` and the distribution, or `"pdflatex": "ABSENT"`. ModularCV never installs `pdflatex` itself.
3. The CV template needs the LaTeX packages `fontenc`, `inputenc`, `lmodern`, `geometry` and `enumitem`. MiKTeX can fetch missing
   packages on demand. ModularCV starts `pdflatex` with no console input (`-interaction=nonstopmode`) and a time limit, so an
   installation dialog cannot be answered: in *MiKTeX Console → Settings*, set the missing-package installation to **Yes** (automatic),
   or install the packages beforehand. This setting was not verified on a fresh MiKTeX install: if the compilation times out or fails,
   look here first.

## 6. First run on the fictional example

Work in a separate folder, never in the clone. Run these from the clone, so that `examples\workspace` exists:

```powershell
Copy-Item -Recurse examples\workspace $HOME\cv-demo
cd $HOME\cv-demo
git init
git config user.name "Demo User"
git config user.email "demo@example.invalid"
git add -A
git commit -m "example sources"
```

`git config` here applies to this demo repository only. Use your own identity (or a GitHub *no-reply* address) in a real workspace.
Then:

```powershell
& $py -m modularcv provenance
& $py -m modularcv facts check facts.md
& $py -m modularcv profile check
& $py -m modularcv content check
& $py -m modularcv offer check offers\backend-intern.json
& $py -m modularcv matrix --offer offers\backend-intern.json
mkdir plans, out
& $py -m modularcv plan --offer offers\backend-intern.json --out plans\job.json
& $py -m modularcv render --plan plans\job.json --offer offers\backend-intern.json --out out\job.tex --pdf out\job.pdf
& $py -m modularcv package create --name job --plan plans\job.json --offer offers\backend-intern.json --tex out\job.tex --compile
& $py -m modularcv package review --name job
& $py -m modularcv package status --name job
```

Each command's purpose is explained in [QUICKSTART.md](QUICKSTART.md), and every option is listed in [CLI.md](CLI.md).

- **Without MiKTeX**, `render` writes `out\job.tex`, reports `PDF_UNAVAILABLE`, exits with code `4` (`pdflatex` not found), and `package create --compile` cannot
  build a package. Everything before that works.
- **With MiKTeX**, `package status` reports `NEEDS_REVIEW` (reason `HUMAN_REVIEW_REQUIRED`) and exits with code `1`: only `READY_TO_SEND` exits `0`, and nothing has been
  approved. That is the expected state of the example.
- **Approving is your decision.** `package approve` must be run by you in a real terminal, after reading the PDF
  (`applications\job\cv\resume.pdf`). It refuses to run from a script. **Do not approve the fictional example in a real workspace.**

## 7. Common problems in PowerShell

| What you see | Meaning | What to do |
|---|---|---|
| `python` opens the Microsoft Store, or prints "Python was not found" | Windows has an alias that hides the real program. | Use `py -3.14 ...`, or turn off *App execution aliases* for `python.exe` in Windows Settings. |
| `No suitable Python runtime found` | The version you asked for is not installed. | Run `py -0p` and use a supported version (3.12 to 3.14). |
| `ERROR: Package 'modularcv' requires a different Python` | The Python used is outside 3.12 to 3.14. | Recreate the virtual environment with a supported version. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell execution policy. | Call `$py` directly (section 3), or relax the policy for the current window only. |
| `The token '&&' is not a valid statement separator` | Windows PowerShell 5.1 has no `&&`. | One command per line, or `;`. |
| `pip` cannot download `setuptools` | No network, or a proxy. | Install `setuptools>=77` in the environment, then `pip install --no-build-isolation -e ".[dev]"`. |
| `latex check` says `ABSENT` after installing MiKTeX | The current window does not know the new `PATH`. | Open a new PowerShell window. |
| `render` exits `4` / `5` | No `pdflatex` / the compilation failed. | See section 5; add `--log out\cv.log` and keep that log private (it can quote the CV). |
| `GIT_REPOSITORY_UNAVAILABLE`, `SOURCE_NOT_AT_COMMIT` | The workspace is not a Git repository, or a source changed after the last commit. | `git init` / `git add -A` and `git commit`, then build the plan again. |
| `WORKSPACE_NOT_REPOSITORY_ROOT` | The workspace folder is inside another Git repository (for example your user folder is itself a repository). | Run `git init` in the workspace folder itself, or move it elsewhere. |
| `OUTPUT_EXISTS`, `PACKAGE_EXISTS` | ModularCV never overwrites a file. | Choose a new file or package name. |
| `warning: LF will be replaced by CRLF` from Git | Git on Windows converts line endings. | Harmless: texts are normalised to LF before hashing, so a Windows checkout does not change a fingerprint. |

Other errors are explained in the troubleshooting table of [QUICKSTART.md](QUICKSTART.md#troubleshooting).

## 8. Keep your real data out of the clone

Your facts, CVs and packages belong in a separate **private** Git repository (see [WORKSPACE.md](WORKSPACE.md)), not in this clone and
not in a folder that is shared or synchronised publicly. Never put them in an issue or a pull request.
