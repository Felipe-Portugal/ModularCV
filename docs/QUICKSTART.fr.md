# Démarrage rapide et dépannage

English: [QUICKSTART.md](QUICKSTART.md)

ModularCV construit un CV **uniquement à partir de faits que vous avez confirmés**, et décide si le résultat peut être envoyé en
**recalculant les preuves à chaque appel**. Il n'écrit aucune phrase, n'envoie rien et n'approuve jamais un CV à votre place. Cette
page vous conduit de zéro à un paquet que vous pouvez relire, avec l'exemple fictif livré dans ce dépôt. Les guides détaillés
(`WORKSPACE.md`, `PACKAGE.md`, etc.) sont pour l'instant en anglais.

## Prérequis

| Besoin | Détail |
|---|---|
| Python | Bibliothèque standard seulement (aucune dépendance à installer). Les métadonnées déclarent `>= 3.9` ; toute la suite de tests a été exécutée sur 3.9, 3.10 (Linux) et 3.14. Les versions *prises en charge* restent à décider par le mainteneur. |
| Git | Votre espace de travail est un dépôt Git : un CV n'est construit qu'à partir de sources validées (commit) dedans. Git doit connaître votre nom et votre courriel (`git config user.name`, `user.email`). |
| `pdflatex` | **Facultatif.** MiKTeX (Windows) ou TeX Live. Sans lui, vous obtenez le `.tex` mais pas de PDF : le paquet reste `NEEDS_REVIEW` (jamais prêt). `python -m modularcv latex check` le dit. Seul MiKTeX sous Windows a été éprouvé ; **TeX Live et la compilation sous Linux ne sont pas testés**. Le gabarit utilise `fontenc`, `inputenc`, `lmodern`, `geometry` et `enumitem` ; sous Debian/Ubuntu ils devraient provenir de `texlive-latex-base`, `texlive-latex-recommended`, `texlive-latex-extra` et `texlive-fonts-recommended` (attendu, non vérifié : lancez `latex check`, puis compilez l'exemple). |
| Un espace de travail privé | Un dépôt Git privé distinct pour vos faits, CV et paquets. **Ne mettez jamais vos données dans ce dépôt-ci** (voir `docs/WORKSPACE.md`). |

## Installation

Depuis un clone de ce dépôt :

```bash
python -m pip install -e ".[dev]"      # pip télécharge setuptools >= 77 dans un environnement de construction isolé : il faut un réseau (ou --no-build-isolation avec setuptools >= 77 installé)
python -m modularcv --help
```

Il n'y a pas de commande `modularcv` : lancez toujours `python -m modularcv ...`. Sans installer, indiquez le clone à Python :
`PYTHONPATH=/chemin/vers/ModularCV python -m modularcv ...` (PowerShell : `$env:PYTHONPATH = "C:\chemin\vers\ModularCV"`).

> Vérifié (M8-A-R1, Windows) : `python -m build` produit un wheel et une archive source ; chacun s'installe dans un environnement
> virtuel neuf (wheel et mode éditable sur Python 3.14, archive source sur 3.9) et les commandes ci-dessus s'exécutent hors du clone.
> L'archive source contient les tests, exemples et la documentation, mais pas `skills/cv-panel/normes-ets.md` (droits de
> distribution non établis). Non vérifié : installation sous Linux et macOS, et PyPI (rien n'est publié).

## Essayer l'exemple fictif (environ cinq minutes)

```bash
cp -r examples/workspace ~/cv-demo && cd ~/cv-demo        # Windows : Copy-Item -Recurse examples\workspace $HOME\cv-demo
git init && git add -A && git commit -m "sources de l'exemple"   # vos sources doivent être validées (commit)
python -m modularcv provenance                              # affiche le commit auquel votre CV sera lié
python -m modularcv facts check facts.md                    # 1. les faits (statut OK)
python -m modularcv profile check                           # 2. identité, familles, disponibilités
python -m modularcv content check                           # 3. le texte du CV, lié aux faits
python -m modularcv offer check offers/backend-intern.json  # 4. une offre (ce qu'elle demande)
python -m modularcv matrix --offer offers/backend-intern.json     # 5. DIRECT / ADJACENT / ABSENT / FORBIDDEN_TO_CLAIM par exigence
mkdir plans out
python -m modularcv plan --offer offers/backend-intern.json --out plans/job.json            # 6. quelles lignes répondent à l'offre
python -m modularcv render --plan plans/job.json --offer offers/backend-intern.json \
                           --out out/job.tex --pdf out/job.pdf                                # 7. LaTeX et, avec pdflatex, le PDF
python -m modularcv package create --name job --plan plans/job.json --offer offers/backend-intern.json \
                           --tex out/job.tex --compile                                        # 8. le paquet (jamais une approbation)
python -m modularcv package review --name job                                                # 9. ce que vous devez examiner
```

L'étape 7 sort avec le code `4` si `pdflatex` est absent : le `.tex` est quand même écrit (et le paquet de l'étape 8 ne peut pas être fait).
L'étape 8 compile à votre place : `--compile` lance `pdflatex` sur les octets qu'il vient de vérifier et met ce résultat dans le paquet, donc
aucun fichier ne circule entre la compilation et le paquet. C'est la seule voie vers un paquet qui peut devenir `READY_TO_SEND` : un PDF
fourni avec `--pdf` est enregistré `SUPPLIED_PROVENANCE_NOT_VERIFIED` et son paquet reste `NEEDS_REVIEW` (`PDF_ORIGIN_NOT_VERIFIED`) quoi que
vous approuviez. Utilisez `--paper letterpaper`
avec `render` pour une page Lettre (le défaut est A4) ; `package create` reconnaît le papier tout seul.

Ensuite, **ouvrez `applications/job/cv/resume.pdf` et lisez-le en entier**, puis décidez vous-même :

```bash
python -m modularcv package approve --name job --reviewer "Votre Nom"    # une personne, dans un vrai terminal : tapez les 12 caractères du hachage
python -m modularcv package status --name job                            # code 0 seulement si READY_TO_SEND
```

`approve` refuse de s'exécuter depuis un script ou un tube (`APPROVAL_REQUIRES_A_PERSON`). N'approuvez pas l'exemple fictif dans un
vrai espace de travail : c'est une démonstration.

## Ce que `READY_TO_SEND` signifie, et ce qu'il ne signifie pas

Il signifie que le **processus est cohérent** : chaque source est validée et inchangée, les faits utilisés sont toujours `CONFIRMED`, le plan,
l'assemblage, le `.tex`, le PDF et les métadonnées concordent, et une approbation **que vous** avez enregistrée désigne ce PDF exact. Il ne
signifie **pas** que vous répondez aux exigences du poste (les exigences obligatoires non satisfaites restent listées dans `package status` et
dans l'approbation), que le PDF a été compilé à partir du `.tex` (cela n'est pas vérifié par la machine : votre lecture du PDF les relie), qu'un
système de suivi des candidatures (ATS) le lira bien, ni que l'approbation vient de vous (c'est un fichier JSON non signé).

## Écrire vos propres sources

| Fichier | Règle pratique |
|---|---|
| `facts.md` | Une ligne par fait : `- [id] STATUT: texte {technologies: ...; capabilities: ...; confirmed_on: ...}`. Seuls les faits `CONFIRMED` peuvent figurer sur un CV. N'inventez jamais une date ni un chiffre. Modèle : `examples/facts.v1.example.md`. |
| `profile.json` | Champs d'identité marqués `public` ou `private` (seuls les publics sont imprimés), vos **familles** (un type de CV avec sa cible de pages), politique, disponibilités. Exemple : `examples/workspace/profile.json`. |
| `content/resume.json` | Vos phrases, en FR et/ou EN. Chaque puce, compétence **et en-tête de bloc** nomme les faits qui la soutiennent (`supports`). Un bloc sans puce (par exemple votre diplôme) est omis du CV, sauf s'il porte `"protected": true`. `capabilities` et `technologies` doivent être des identifiants de la taxonomie : voir `examples/taxonomy.generic-v1.json` (identique à `builtin:generic-v1`). |
| `offers/*.json` | L'offre comme donnée. Les exigences sont extraites de la description ; ajoutez-en d'explicites au besoin. |

Si votre profil a plusieurs familles, nommez celle à utiliser : `matrix --family software ...` et `plan --family software ...`.

## Dépannage

| Ce que vous voyez | Signification | Que faire |
|---|---|---|
| `GIT_REPOSITORY_UNAVAILABLE` | L'espace de travail n'est pas un dépôt Git. | `git init`, ajoutez et validez vos sources. |
| `SOURCE_NOT_AT_COMMIT` / `SOURCE_COMMIT_UNVERIFIABLE` | Une source diffère du dernier commit, ou le commit est inconnu. | Validez vos sources puis refaites le plan. |
| `PLAN_FAMILY_REQUIRED` | Plusieurs familles dans le profil. | Ajoutez `--family NOM`. |
| `PLAN_CAPABILITY_UNKNOWN` | Un fait ou une puce utilise une capacité absente de la taxonomie. | Utilisez un identifiant de la taxonomie (par exemple `data-analysis`, pas `data`) ou fournissez la vôtre. |
| Une rubrique (par exemple Formation) manque au CV | Son bloc n'a aucune puce et n'est pas protégé (`content check` avertit `CONTENT_BLOCK_NEVER_PRINTED`). | Ajoutez `"protected": true` au bloc. |
| `PDF_NO_PAGE` | Le PDF donné à `package create --pdf` n'a aucune page lisible dans son arbre de pages. | Recompilez-le, ou utilisez `package create --compile`. |
| `ASSEMBLY_SOURCE_MISMATCH`, `ASSEMBLY_PLAN_FINGERPRINT` | Une source a changé après le plan, ou le plan a été modifié. | Refaites un plan (`plan --out` avec un nouveau nom de fichier). |
| `OUTPUT_EXISTS`, `PACKAGE_EXISTS` | Rien n'est jamais écrasé. | Choisissez un nouveau nom de fichier ou de paquet. |
| `render` sort avec `4` | `pdflatex` introuvable. | Installez MiKTeX ou TeX Live, ou continuez sans PDF (le paquet sera `NEEDS_REVIEW` / `FINAL_DOCUMENT_MISSING`). |
| `render` sort avec `5` | La compilation a échoué. | Relancez avec `--log out/cv.log` (le journal peut citer votre CV : gardez-le privé). |
| `APPROVAL_REQUIRES_A_PERSON` | `package approve` a été lancé sans terminal interactif. | Lancez-le vous-même dans un terminal. |
| `NEEDS_REVIEW` avec `ARTIFACT_CHANGED_SINCE_PACKAGING`, `HUMAN_REVIEW_MISMATCH` | Un fichier du paquet ou le PDF a changé après l'empaquetage ou l'approbation. | Un paquet n'est jamais modifié : créez-en un nouveau et relisez-le. |
| Avertissement `UNSATISFIED_REQUIRED` | Une exigence obligatoire de l'offre n'a aucun fait confirmé. | Rien n'est caché : décidez si vous postulez ; n'ajoutez jamais un fait que vous ne pouvez pas confirmer. |
