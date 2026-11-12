# Installer sous Windows

English: [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)

Cette page vous mène d'une machine Windows vierge à un premier essai sur l'exemple fictif, avec PowerShell. Elle complète
[QUICKSTART.fr.md](QUICKSTART.fr.md), qui explique ce que fait chaque commande et ce que signifie `READY_TO_SEND`.

Le moteur et la ligne de commande s'installent **depuis un clone du dépôt**, comme décrit ici. Il n'y a pas de dépôt sur un index de paquets (PyPI).
Si vous préférez une application graphique, **ModularCV Desktop** (bêta, facultative) a son propre installateur et ses propres instructions :
[desktop/LISEZMOI.fr.md](desktop/LISEZMOI.fr.md). Le reste de cette page concerne la ligne de commande.

**Ce qui a réellement été essayé.** Les commandes ci-dessous ont été exécutées sous Windows 11 avec Windows PowerShell 5.1, Git, Python 3.14 et
MiKTeX (la seule distribution TeX éprouvée à ce jour). Python 3.12 et 3.13 sont pris en charge mais n'ont pas servi à cette page. PowerShell 7,
les autres versions de Windows et TeX Live sous Windows n'ont pas été essayés.

## 1. Ce qu'il vous faut

| Outil | Exigence | Vérification |
|---|---|---|
| Python | **3.12, 3.13 ou 3.14**. Les autres versions sont refusées par `pip` (`Requires-Python : >=3.12,<3.15`). | `py -0p` liste les versions installées |
| Git | Un Git pour Windows récent. Git doit connaître votre nom et votre courriel pour valider (commit) l'exemple. | `git --version` |
| MiKTeX | **Facultatif.** Nécessaire seulement pour obtenir un PDF. Sans lui, vous obtenez quand même le `.tex` et un paquet reste `NEEDS_REVIEW`. | `python -m modularcv latex check` |
| Réseau | Nécessaire une fois par `pip`, qui télécharge `setuptools` (version 77 ou plus) pour construire le projet. Il n'y a aucune autre dépendance. | |

Installez Python depuis [python.org](https://www.python.org/downloads/windows/) (cochez l'option *py launcher*) et Git depuis
[git-scm.com](https://git-scm.com/download/win). Ouvrez ensuite une **nouvelle** fenêtre PowerShell pour que les nouveaux programmes soient trouvés.

## 2. Récupérer le code

```powershell
git clone https://github.com/Felipe-Portugal/ModularCV
cd ModularCV
```

(Dans Windows PowerShell 5.1, `&&` n'enchaîne pas les commandes : une commande par ligne, ou `;`.)

## 3. Créer un environnement virtuel

Créez-le **hors** du clone pour qu'il ne se mélange jamais au dépôt ni à l'analyse de confidentialité. Remplacez `3.14` par la version prise
en charge que vous avez installée :

```powershell
py -3.14 -m venv $HOME\venvs\modularcv
$py = "$HOME\venvs\modularcv\Scripts\python.exe"
& $py --version
```

Il n'est pas nécessaire d'activer l'environnement : appelez `$py` explicitement, comme ci-dessous. (Si vous préférez
`& $HOME\venvs\modularcv\Scripts\Activate.ps1` et que PowerShell répond que l'exécution de scripts est désactivée, continuez avec `$py`, ou
autorisez les scripts pour la fenêtre courante seulement avec `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.)

## 4. Installer ModularCV et le vérifier

```powershell
& $py -m pip install -e ".[dev]"
& $py -m modularcv --help
& $py -m pytest -q
```

- Il n'y a **pas de commande `modularcv`** : lancez toujours `& $py -m modularcv ...` (ou `python -m modularcv ...` une fois l'environnement activé).
- `.[dev]` ajoute `pytest`, la seule dépendance de développement. Le moteur n'utilise que la bibliothèque standard de Python.
- La suite de tests n'utilise que des données synthétiques et dure quelques minutes.
- L'installation écrit un dossier `modularcv.egg-info` dans le clone ; Git l'ignore.

## 5. Sortie PDF : MiKTeX (facultatif)

1. Installez MiKTeX depuis [miktex.org](https://miktex.org/download). Ouvrez une nouvelle fenêtre PowerShell.
2. Vérifiez que ModularCV le trouve :

   ```powershell
   pdflatex --version
   & $py -m modularcv latex check
   ```

   `latex check` affiche `"pdflatex": "FOUND"` et la distribution, ou `"pdflatex": "ABSENT"`. ModularCV n'installe jamais `pdflatex`.
3. Le gabarit de CV a besoin des paquets LaTeX `fontenc`, `inputenc`, `lmodern`, `geometry` et `enumitem`. MiKTeX peut récupérer les paquets
   manquants à la demande. ModularCV lance `pdflatex` sans entrée console (`-interaction=nonstopmode`) et avec une limite de temps : une boîte de
   dialogue d'installation ne peut donc pas recevoir de réponse. Dans *MiKTeX Console → Settings*, réglez l'installation des paquets
   manquants sur **Yes** (automatique), ou installez les paquets d'avance. Ce réglage n'a pas été vérifié sur une installation neuve de
   MiKTeX : si la compilation expire ou échoue, regardez d'abord ici.

## 6. Premier essai sur l'exemple fictif

Travaillez dans un dossier distinct, jamais dans le clone. Lancez ces commandes depuis le clone, pour que `examples\workspace` existe :

```powershell
Copy-Item -Recurse examples\workspace $HOME\cv-demo
cd $HOME\cv-demo
git init
git config user.name "Demo User"
git config user.email "demo@example.invalid"
git add -A
git commit -m "sources de l'exemple"
```

Ici, `git config` ne vaut que pour ce dépôt de démonstration. Dans un vrai espace de travail, utilisez votre identité (ou une adresse
*no-reply* GitHub). Ensuite :

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

Le rôle de chaque commande est expliqué dans [QUICKSTART.fr.md](QUICKSTART.fr.md), et toutes les options sont listées dans [CLI.md](CLI.md) (en anglais).

- **Sans MiKTeX**, `render` écrit `out\job.tex`, signale `PDF_UNAVAILABLE`, se termine avec le code `4` (`pdflatex` introuvable), et
  `package create --compile` ne peut pas construire de paquet. Tout ce qui précède fonctionne.
- **Avec MiKTeX**, `package status` indique `NEEDS_REVIEW` (raison `HUMAN_REVIEW_REQUIRED`) et se termine avec le code `1` : seul
  `READY_TO_SEND` donne `0`, et rien n'a été approuvé. C'est l'état attendu de l'exemple.
- **Approuver est votre décision.** `package approve` doit être lancé par vous, dans un vrai terminal, après avoir lu le PDF
  (`applications\job\cv\resume.pdf`). Il refuse de s'exécuter depuis un script. **N'approuvez pas l'exemple fictif dans un vrai espace de travail.**

## 7. Problèmes courants sous PowerShell

| Ce que vous voyez | Signification | Que faire |
|---|---|---|
| `python` ouvre le Microsoft Store, ou affiche « Python was not found » | Un alias Windows masque le vrai programme. | Utilisez `py -3.14 ...`, ou désactivez les *alias d'exécution d'application* de `python.exe` dans les paramètres Windows. |
| `No suitable Python runtime found` | La version demandée n'est pas installée. | Lancez `py -0p` et utilisez une version prise en charge (3.12 à 3.14). |
| `ERROR: Package 'modularcv' requires a different Python` | Le Python utilisé est hors de 3.12 à 3.14. | Recréez l'environnement virtuel avec une version prise en charge. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Politique d'exécution de PowerShell. | Appelez `$py` directement (section 3), ou assouplissez la politique pour la fenêtre courante seulement. |
| `The token '&&' is not a valid statement separator` | Windows PowerShell 5.1 n'a pas `&&`. | Une commande par ligne, ou `;`. |
| `pip` ne peut pas télécharger `setuptools` | Pas de réseau, ou un proxy. | Installez `setuptools>=77` dans l'environnement, puis `pip install --no-build-isolation -e ".[dev]"`. |
| `latex check` indique `ABSENT` après l'installation de MiKTeX | La fenêtre courante ne connaît pas le nouveau `PATH`. | Ouvrez une nouvelle fenêtre PowerShell. |
| `render` se termine avec `4` / `5` | Pas de `pdflatex` / la compilation a échoué. | Voir la section 5 ; ajoutez `--log out\cv.log` et gardez ce journal privé (il peut citer le CV). |
| `GIT_REPOSITORY_UNAVAILABLE`, `SOURCE_NOT_AT_COMMIT` | L'espace de travail n'est pas un dépôt Git, ou une source a changé après le dernier commit. | `git init` / `git add -A` puis `git commit`, et reconstruisez le plan. |
| `WORKSPACE_NOT_REPOSITORY_ROOT` | Le dossier de travail est à l'intérieur d'un autre dépôt Git (par exemple votre dossier utilisateur est lui-même un dépôt). | Lancez `git init` dans le dossier de travail lui-même, ou déplacez-le. |
| `OUTPUT_EXISTS`, `PACKAGE_EXISTS` | ModularCV n'écrase jamais un fichier. | Choisissez un autre nom de fichier ou de paquet. |
| `warning: LF will be replaced by CRLF` de Git | Git sous Windows convertit les fins de ligne. | Sans conséquence : les textes sont normalisés en LF avant le hachage, une copie Windows ne change donc aucune empreinte. |

Les autres erreurs sont expliquées dans le tableau de dépannage de [QUICKSTART.fr.md](QUICKSTART.fr.md).

## 8. Gardez vos vraies données hors du clone

Vos faits, CV et paquets vont dans un dépôt Git **privé** distinct (voir [WORKSPACE.md](WORKSPACE.md), en anglais), pas dans ce clone et pas dans
un dossier partagé ou synchronisé publiquement. Ne les mettez jamais dans une issue ni dans une pull request.
