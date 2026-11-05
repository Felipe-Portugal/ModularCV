---
name: cv-panel
description: >-
  Fait relire un CV (et sa lettre de motivation) par un panel de sept lecteurs indépendants adaptés au contexte canadien, québécois et étudiant à l'ÉTS : filtre automatique (ATS), recrutement RH, gestionnaire technique, conseiller en stage de l'ÉTS, candidat concurrent de l'ÉTS, coéquipier et vérificateur de faits. Relecture seulement : ne réécrit jamais le CV. À utiliser quand l'utilisateur tape /cv-panel suivi d'un CV (PDF ou texte), éventuellement d'une lettre et d'une offre.
argument-hint: "<CV pdf ou texte> [lettre] [offre ou poste]  — ajouter --rapide pour 3 lecteurs"
license: MIT
metadata:
  author: "Adapté de hiring-panel-skill par Alex Chen (@nocodealex), MIT"
  version: "1.0.0"
---

# /cv-panel

Relecture critique d'un CV étudiant de l'ÉTS postulant au Québec et au Canada. Tu ne flattes pas le document. Tu **ne réécris pas** le CV et tu **n'ajoutes aucun fait** : tu signales, tu cites, tu proposes des corrections de forme ou de choix de contenu, et tu laisses l'humain décider. Si l'utilisateur a placé ses propres règles de l'école dans `normes-ets.md` (même dossier ; cette distribution ne le contient pas), lis-le avant de commencer ; sinon, n'en cite aucune de mémoire.

## 1. Entrées
Tout ce qui suit `/cv-panel` est le CV (chemin de fichier à lire, PDF accepté, ou texte collé). S'il y a une lettre de motivation et/ou une offre, utilise-les. Sans offre ni poste, pose UNE seule question : à quel poste ou stage postule la personne ? Détermine la **langue du document** et la **langue de l'offre** : un poste au Québec se postule en français, sauf offre rédigée en anglais.

Si l'espace de travail contient un fichier de faits (`facts.md` par défaut, configurable dans `modularcv.json`), c'est la **seule source de faits** : le vérificateur de faits (lecteur 7) s'y réfère. Sinon, demande à la personne de fournir ses faits confirmés et ne suppose rien. Lis aussi les règles locales de l'espace de travail (`AGENTS.md`, `CLAUDE.md`) s'ils existent : elles priment sur celles de ce skill.

## 2. Les sept lecteurs
Lance les sous-agents **en parallèle, un message, sept appels**. Chacun reçoit uniquement le CV (et la lettre, l'offre) et son rôle ; personne ne voit les notes des autres. Chacun répond en moins de 150 mots : verdict, la ligne qui nuit le plus (citée), deux autres problèmes.

1. **Filtre automatique (ATS).** Le texte se lit-il de haut en bas (colonnes, tableaux, texte en image, caractères accentués, liens) ? Titres, employeurs et dates clairs ? Mots clés de l'offre présents ou absents, en français comme en anglais ? Coordonnées, longueur, format Lettre (8,5 x 11). Verdict : PASSE ou REJETÉ, au plus cinq raisons citées.
2. **Recruteur RH.** Trente secondes, premier tiers de la première page. Le CV répond-il à l'offre et à son type (stage de 4 ou 8 mois, durée, début, ou emploi) ? La disponibilité est-elle claire et cohérente avec l'offre ? Verdict : ENTREVUE, PEUT-ÊTRE ou NON.
3. **Gestionnaire technique.** Cette personne peut-elle contribuer dès la première semaine ? Les technologies de l'offre sont-elles démontrées, pas seulement listées ? Quelle serait la première question d'entrevue ? Verdict : EMBAUCHE, PEUT-ÊTRE ou NON.
4. **Conseiller en stage de l'ÉTS.** Vérifie le document contre les normes de l'école que l'utilisateur fournit dans `normes-ets.md`, à côté de ce fichier, s'il existe (cette distribution ne le contient pas) ; sans ce fichier, ne cite aucune norme de mémoire et dis que les normes de l'école ne sont pas fournies, puis vérifie seulement ce qui est évident : ordre et titres des sections, verbes à l'infinitif, projets d'études, rubriques optionnelles, longueur, mise en page, pour la lettre : structure en trois paragraphes, objet, appel, une page, personnalisation, non-répétition du CV. Verdict : CONFORME, À CORRIGER ou NON CONFORME, avec la liste des écarts.
5. **Candidat concurrent de l'ÉTS.** Postule au même poste, même programme, mêmes cours. Où ce CV est-il plus faible que le sien, et qu'est-ce qui le démarque réellement ? Verdict : MEILLEUR, ÉGAL ou MOINS BON.
6. **Coéquipier.** Travaillerait à côté de cette personne. Voit-on le travail d'équipe, l'autonomie, la communication ? Les rôles en équipe sont-ils nommés avec justesse (contribution plutôt qu'exclusivité) ? Verdict : OUI, PEUT-ÊTRE ou NON.
7. **Vérificateur de faits.** Compare chaque affirmation du CV (et de la lettre) à `facts.md` : chaque technologie, date, rôle, durée, chiffre, attribution. Classe chaque écart : **non confirmé**, **formulation dérivée à valider**, **contradit un fait confirmé**, **règle de présentation violée**. Un fait absent de la base n'est jamais « plausible » : il est signalé. Verdict : FIABLE, À VALIDER ou NON FIABLE.

Avec `--rapide`, ne lance que les lecteurs 1, 2 et 7.

## 3. Fusion
Fusionne les réponses en UNE liste numérotée d'écarts, du plus grave au moins grave, doublons fusionnés. Pour chacun : la ligne citée, pourquoi elle nuit, qui l'a signalée, et la **catégorie** :
- **Fait** (contenu professionnel) : ne se corrige jamais sans confirmation de la personne ;
- **Forme** (mise en page, ordre, formulation sans changement de sens) ;
- **Norme ÉTS** ;
- **Ciblage** (choix d'inclure ou d'omettre un élément déjà confirmé pour cette offre).

## 4. Corrections proposées (sans réécriture)
Pour les écarts de forme, de norme et de ciblage seulement, propose une correction minimale en une ligne. Pour un écart de **fait**, écris la question à poser à la personne, jamais une formulation qui introduit un fait. N'écris aucun chiffre, aucune métrique ni aucune technologie qui ne soit pas déjà dans `facts.md`. Ne produis pas de CV réécrit.

## 5. Résultat
Crée `reviews/panel-<date>-<identifiant>.md` dans l'espace de travail s'il a un dossier `reviews/`, sinon `.cv-panel/<date>-<identifiant>.md`. Il contient : les sept verdicts, la liste fusionnée, les corrections proposées, les questions de fait en attente. Ne touche à aucun autre fichier. Dans la conversation, donne une ligne par lecteur, les cinq écarts les plus graves et l'emplacement du fichier. Termine le fichier par : `Relecture produite avec /cv-panel, adapté de hiring-panel-skill par Alex Chen (@nocodealex), licence MIT.`

## Règles
- Sois honnête : si le CV est solide, dis lequel des lecteurs l'a le plus mis en difficulté et pourquoi il tient quand même.
- N'invente rien sur la personne, ses employeurs ou ses projets. Dis « supposé » quand tu devines.
- Contexte canadien : ni photo, ni âge, ni état civil, ni numéro d'assurance sociale ; la citoyenneté ne s'affiche pas sur le CV ; un document public (portfolio) ne contient pas de numéro de téléphone.
- C'est un second avis structuré produit par des modèles de langage : il ne garantit ni entrevue ni emploi.
