# ModularCV

Une chaîne **modulaire, traçable et fondée sur les faits** pour produire des CV et des lettres de motivation,
avec des garde-fous qui empêchent un pipeline automatisé d'inventer des faits, d'expédier un document périmé
ou de laisser fuiter des données personnelles. Pensé pour les étudiants et les développeurs en début de carrière
qui postulent au Canada et au Québec (documents en français et en anglais, conventions du coop de l'ÉTS) ;
rien dans le code n'est lié à une personne en particulier.

English: [README.md](README.md)

## Contenu

| Module | Rôle |
|---|---|
| `modularcv.provenance` | Un document généré doit citer un **vrai commit Git** contenant les sources exactes utilisées. Un placeholder (des zéros), l'absence de Git, un SHA inconnu ou une source modifiée refusent la génération. |
| `modularcv.readiness` | Promotion **fail-closed** : un paquet n'est « prêt à envoyer » que si ses preuves (sources, snapshot, chaîne plan-PDF, contrôles, registre de péremption, métadonnées du CV et approbation humaine du PDF exact) concordent, recalculées à chaque appel. Un index secondaire ne peut jamais le promouvoir. |
| `modularcv.profile` | **Profile-v1** : votre identité (chaque champ `public` ou `private`), langues, familles de CV, politique et disponibilités, gardés dans votre espace de travail. Une disponibilité ne compte que si un fait `CONFIRMED` la soutient. |
| `modularcv.content` | **ResumeContent-v1** : le texte de votre CV comme données validées (sections, blocs, puces, compétences, bases), en français, en anglais ou les deux. Chaque puce, compétence et en-tête de bloc nomme les faits qui le soutiennent ; il ne peut être imprimé que s'ils sont tous `CONFIRMED`. Le LaTeX brut est refusé, et la vérification prouve l'existence et le statut des faits, jamais le sens d'un texte (voir [docs/CONTENT.md](docs/CONTENT.md), en anglais). |
| `modularcv.joboffer`, `taxonomy`, `matrix`, `plan` | **JobOffer-v1**, une petite **taxonomie** configurable, la **matrice des exigences** (`DIRECT`, `ADJACENT`, `ABSENT`, `FORBIDDEN_TO_CLAIM`) et un **plan de personnalisation** déterministe : lesquelles de vos lignes prouvées répondraient à une offre. Seuls les faits confirmés comptent, une interdiction l'emporte sur la pertinence, une exigence non satisfaite reste explicite. Le plan n'est pas un CV et aucun modèle n'écrit rien (voir [docs/PLAN.md](docs/PLAN.md), en anglais). |
| `modularcv.assemble`, `latex`, `pdf` | Transforme un plan de personnalisation **vérifié** en CV structuré puis en fichier LaTeX générique, échappé et déterministe, et le compile avec `pdflatex` s'il est installé (facultatif). Aucun modèle n'écrit rien, rien n'est marqué prêt à envoyer (voir [docs/RENDER.md](docs/RENDER.md), en anglais). |
| `modularcv.package`, `chain` | Construit un **paquet** (plan, CV assemblé, `.tex`, PDF, métadonnées, snapshot) dans votre espace de travail privé, enregistre une **approbation humaine du PDF exact** et calcule `READY_TO_SEND` à partir des preuves à chaque appel. Rien n'est envoyé, rien n'est approuvé automatiquement (voir [docs/PACKAGE.md](docs/PACKAGE.md), en anglais). |
| `modularcv.legacy` | `facts import` : transforme un document Markdown historique en base de faits *proposée*, selon une correspondance que vous écrivez. Une ligne inconnue n'est jamais importée et rien ne devient `CONFIRMED` tout seul (voir [docs/IMPORT.md](docs/IMPORT.md), en anglais). |
| `modularcv.privacy` | Analyse un répertoire (et l'historique) à la recherche de courriels, téléphones, NAS, chemins d'utilisateur, URL de profil, identifiants et de vos propres termes privés, **avant** publication. |
| `skills/cv-panel` | Skill Claude Code : sept lecteurs indépendants (ATS, recruteur RH, gestionnaire technique, conseiller en stage ÉTS, candidat concurrent, coéquipier, vérificateur de faits) relisent un CV et sa lettre. **Relecture seulement : il ne réécrit rien et n'ajoute aucun fait.** |

**Vous débutez ? Commencez par [docs/QUICKSTART.fr.md](docs/QUICKSTART.fr.md)** (un exemple fictif en cinq minutes, ce que signifie
`READY_TO_SEND`, dépannage). Voir ensuite [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GOVERNANCE.md](docs/GOVERNANCE.md) et
[docs/WORKSPACE.md](docs/WORKSPACE.md).

## Vos données restent privées

Ce dépôt ne contient **aucune donnée personnelle**. Gardez un espace de travail privé distinct (vos faits, CV et
candidatures) et exécutez ModularCV dessus. `facts.md`, `applications/` et `packages/` sont ignorés par Git ici
volontairement.

## Démarrage rapide

```bash
python -m pip install -e ".[dev]"     # Python 3.12 à 3.14, pip >= 21.3 (voir docs/QUICKSTART.fr.md ; pas de commande `modularcv` : `python -m modularcv`)
python -m pytest                      # tous les tests utilisent des données synthétiques
python -m modularcv profile check     # depuis votre espace de travail (exemple : examples/workspace/)
python -m modularcv content check     # ResumeContent-v1 et ses références aux faits (exemple : examples/workspace/content/)
python -m modularcv offer check offre.json   # JobOffer-v1 (exemples : examples/workspace/offers/)
python -m modularcv matrix --offer offers/backend-intern.json   # états des exigences, à partir des faits confirmés seulement
python -m modularcv plan --offer offers/backend-intern.json     # plan de personnalisation déterministe (PLAN_ONLY)
python -m modularcv render --plan plans/p.json --offer offers/backend-intern.json --out out/cv.tex   # ajouter --pdf out/cv.pdf si pdflatex est installé
python -m modularcv package create --name job --plan plans/job.json --offer offers/job.json --tex out/job.tex --compile   # puis : package review, package approve (par vous), package status ; un PDF donné avec --pdf ne peut jamais être READY_TO_SEND
python -m modularcv facts import --mapping import-map.json --in ancien.md --dry-run   # simulation, aucune écriture
python -m modularcv privacy --root . --deny-file ~/termes-prives.txt --history        # avant toute publication
```

Pour le skill : copiez `skills/cv-panel/` dans `~/.claude/skills/`, puis `/cv-panel cv.pdf lettre.pdf <offre>`.

## Statut, plateformes prises en charge et limites

`0.2.0`, **non publiée** (version candidate) : la chaîne indépendante de toute personne, de la base de faits à un PDF approuvé par un humain
(provenance, readiness, `Profile-v1`, import historique contrôlé, `ResumeContent-v1`, offres, plan, assemblage, LaTeX générique, paquets).
Rien n'est envoyé nulle part et rien n'est approuvé automatiquement. Le moteur de génération du projet privé d'origine n'est pas inclus : il
contient encore le contenu d'une personne ; le porter derrière une base de faits configurable reste à faire.

| Sujet | Statut |
|---|---|
| Python | **3.12, 3.13, 3.14** (`Requires-Python : >=3.12,<3.15`). Suite complète exécutée sur 3.12 et 3.14 (Windows) et 3.13 (conteneur Linux) ; pas toutes les combinaisons de version et de plateforme. 3.9 et 3.10 : environnements de régression seulement, aucun support. 3.15 non testée. |
| Le moteur et le `.tex` | Bibliothèque standard seulement. Le même exemple synthétique donne le même plan et le même `.tex` sur les interpréteurs ci-dessus. |
| PDF avec MiKTeX (Windows) | Éprouvé. |
| PDF avec TeX Live (Linux) | **Non testé.** Sans distribution TeX, vous obtenez le `.tex` et pas de PDF. |
| macOS | Non testé. |
| Systèmes de suivi de candidatures (ATS) | **Non vérifiés, rien n'est certifié.** Seuls l'ordre et les accents du texte extrait ont été regardés sur l'exemple. |

**Garanties.** Tout ce qui est imprimé vient d'un fait `CONFIRMED` ; un document généré cite le vrai commit Git de ses sources ; la chaîne plan,
assemblage, `.tex` et PDF est recalculée à chaque appel ; `READY_TO_SEND` est calculé, jamais stocké, et se perd dès qu'une source, un fichier du
paquet ou le PDF change.

**Limites.** Les contrôles prouvent que les faits existent et sont confirmés, pas qu'une phrase dit ce qu'ils disent. Une approbation est un
fichier JSON non signé qui lie une décision aux octets exacts d'un PDF : le relecteur n'est **pas authentifié**. Seul un PDF compilé par
`package create --compile` peut devenir `READY_TO_SEND` ; l'origine enregistrée du PDF est une déclaration dans un fichier, **pas une preuve
cryptographique**, et qui peut écrire dans votre espace de travail peut la falsifier, comme une approbation. `READY_TO_SEND` signifie que le
processus est cohérent, pas que vous remplissez les exigences du poste. `pdflatex` n'est pas un bac à sable. L'analyse de confidentialité est
une recherche de motifs au mieux. Détails : [docs/PACKAGE.md](docs/PACKAGE.md) (« Limits that are not hidden », en anglais).

## Licence

MIT. `skills/cv-panel` est adapté de [hiring-panel-skill](https://github.com/alexyc9381/hiring-panel-skill)
de Alex Chen (MIT) ; voir `skills/cv-panel/NOTICE.md`.
