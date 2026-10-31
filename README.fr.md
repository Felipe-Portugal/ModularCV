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
| `modularcv.readiness` | Promotion **fail-closed** : un paquet n'est « prêt à envoyer » que si son état déclaré, ses contrôles, le registre de péremption et les métadonnées du CV concordent. Un index secondaire ne peut jamais le promouvoir. |
| `modularcv.privacy` | Analyse un répertoire (et l'historique) à la recherche de courriels, téléphones, NAS, chemins d'utilisateur, URL de profil, identifiants et de vos propres termes privés, **avant** publication. |
| `skills/cv-panel` | Skill Claude Code : sept lecteurs indépendants (ATS, recruteur RH, gestionnaire technique, conseiller en stage ÉTS, candidat concurrent, coéquipier, vérificateur de faits) relisent un CV et sa lettre. **Relecture seulement : il ne réécrit rien et n'ajoute aucun fait.** |

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GOVERNANCE.md](docs/GOVERNANCE.md) et
[docs/WORKSPACE.md](docs/WORKSPACE.md).

## Vos données restent privées

Ce dépôt ne contient **aucune donnée personnelle**. Gardez un espace de travail privé distinct (vos faits, CV et
candidatures) et exécutez ModularCV dessus. `facts.md`, `applications/` et `packages/` sont ignorés par Git ici
volontairement.

## Démarrage rapide

```bash
python -m pip install -e ".[dev]"     # Python 3.9+
python -m pytest                      # tous les tests utilisent des données synthétiques
```

Pour le skill : copiez `skills/cv-panel/` dans `~/.claude/skills/`, puis `/cv-panel cv.pdf lettre.pdf <offre>`.

## Licence

MIT. `skills/cv-panel` est adapté de [hiring-panel-skill](https://github.com/alexyc9381/hiring-panel-skill)
de Alex Chen (MIT) ; voir `skills/cv-panel/NOTICE.md`.
