# ModularCV Desktop en français

English: [INSTALL.md](INSTALL.md), [FIRST_RUN.md](FIRST_RUN.md), [STATUSES.md](STATUSES.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md), [UNINSTALL.md](UNINSTALL.md)

ModularCV Desktop est une application Windows pour le moteur ModularCV : elle construit un CV à partir de **vos faits confirmés**, avec une trace
vérifiable entre les faits et le PDF que vous envoyez. Tout reste sur votre ordinateur : pas de compte, pas de réseau, pas de télémétrie.
C'est une **bêta** (`0.5.0-beta.1`).

> **Préparée — pas encore publiée.** ModularCV Desktop `0.5.0-beta.1` n'est pas publié : il n'existe aujourd'hui ni version Desktop ni
> installateur à télécharger. L'installateur est construit et validé ; il sera proposé sur la page **Releases** du dépôt GitHub après la
> publication officielle. D'ici là, cette page décrit comment l'installation se déroulera, pour que vous puissiez la lire à l'avance.

À lire avant de vous y fier : **une approbation est votre propre décision, enregistrée dans un fichier local non signé** ; `READY_TO_SEND`
prouve le processus, pas la valeur du candidat ni la qualité du texte.

## Installer

Il faut Windows 11 64 bits (Windows 10 n'a pas été testé). Python, Node.js et Rust ne sont pas nécessaires : l'application embarque son moteur.
Git (pour créer des paquets) et MiKTeX ou TeX Live (pour produire un PDF) sont facultatifs et ne sont jamais installés par l'application.

1. Une fois la bêta publiée, téléchargez `ModularCV Desktop_0.5.0-beta.1_x64-setup.exe` depuis la page **Releases** du dépôt GitHub, et nulle part ailleurs.
2. Vérifiez l'empreinte SHA-256 avant de lancer le fichier :

   ```powershell
   Get-FileHash ".\ModularCV Desktop_0.5.0-beta.1_x64-setup.exe" -Algorithm SHA256
   ```

   Le résultat doit être exactement l'empreinte publiée avec la version. S'il diffère, ne lancez pas le fichier.

   L'installateur préparé pour cette bêta (`ModularCV Desktop_0.5.0-beta.1_x64-setup.exe`, 10 064 848 octets, soit 9,60 Mio, non signé) a été
   construit depuis le commit `fef0c6f` et a cette empreinte SHA-256 :

   ```
   1A117D080214F3F98048C17D31D07A2E776FF7D2BF87DAB7962B501DEEC04187
   ```

   C'est l'empreinte du fichier prévu pour la publication : la version publiera exactement ce fichier. Si le fichier téléchargé affiche une
   autre empreinte, ne le lancez pas. Tant que la version n'existe pas, il n'y a rien à télécharger ni à comparer.

3. Lancez l'installateur. Il n'est **pas signé** : SmartScreen peut afficher « Windows a protégé votre ordinateur ». Si l'empreinte correspond,
   choisissez **Informations complémentaires** puis **Exécuter quand même**.
4. L'installation se fait pour votre utilisateur seulement (pas de droits administrateur), dans `%LOCALAPPDATA%\ModularCV Desktop`. Si WebView2
   manque, l'installateur télécharge d'abord le petit programme d'amorçage de Microsoft (internet nécessaire à ce moment-là uniquement).
5. Ouvrez **ModularCV** depuis le menu Démarrer.

## Premier démarrage

1. **Réglages** > **Diagnostic de l'environnement** : moteur, Git, LaTeX, en lecture seule et hors ligne. « Trouvé » ne veut pas dire « bien configuré ».
2. Tableau de bord > **Espace de démonstration** : copie un exemple fictif dans `%LOCALAPPDATA%\org.modularcv.desktop\demo-workspace`. Puis **Vérifier les faits**.
3. Parcourez le profil, les expériences, les offres. **Modifier** ouvre un formulaire.
4. **Adapter mon CV** : matrice des exigences, plan d'adaptation, fichier `.tex` (sans LaTeX), PDF (avec `pdflatex`), paquet (avec Git).
5. **Vérifier mon CV** : le PDF exact, ses avertissements, le statut calculé par le moteur. Pour approuver : voir chaque page, cocher les deux
   confirmations, saisir votre nom et les 12 premiers caractères de l'empreinte du PDF, choisir Approuver ou Refuser, confirmer.

Pour votre propre CV, choisissez **Choisir un dossier…** et gardez votre espace de travail **en dehors** des dossiers de données de l'application.

## Les statuts

| Statut | Sens |
|---|---|
| `NEEDS_REVIEW` | Les preuves sont intactes mais incomplètes ou dépassées : pas encore de revue, pas de PDF, une source modifiée depuis le paquet. |
| `READY_TO_SEND` | Toutes les vérifications passent **maintenant** et vous avez approuvé ce PDF exact. |
| `BLOCKED` | La chaîne de preuves n'est plus fiable : refus de votre part, fichiers du paquet altérés, paquet périmé. |

Le statut est recalculé par le moteur à chaque demande. Modifier quoi que ce soit après l'approbation (même un octet du PDF) retire `READY_TO_SEND`.
Restaurer les octets d'origine le rétablit. Un fichier `.tex` seul n'est jamais prêt.

**L'approbation** est un fichier local (`applications\<paquet>\cv\cv-quality-review.json`) qui contient votre décision, le nom saisi et l'empreinte du
PDF vu. Il n'est ni signé ni authentifié : quiconque peut écrire dans votre dossier peut en créer un. Le moteur vérifie seulement qu'il désigne ce
paquet et ce PDF exact. Relisez le PDF vous-même avant de l'envoyer.

## Limites connues

- Installateur non signé ; testé avec ce fichier exact sur Windows 11 (machine virtuelle à partir d'une image allégée tierce) ; un build antérieur de
  cette bêta a aussi été essayé sur un Windows 11 Famille de développement.
  **Non testés** : Windows 11 standard, Windows 10, TeX Live, installation par-dessus une ancienne version, installateur graphique avec la case de
  suppression des données cochée.
- Les contrôles automatiques de GitHub n'exécutent pas les tests qui exigent LaTeX (PDF, approbation) : ils ont été exécutés en local avec MiKTeX.
- Le diagnostic vérifie seulement que `pdflatex` est trouvé ; un MiKTeX mal configuré affiche « disponible » puis la compilation échoue (`PDF_FAILED`).
- MiKTeX peut proposer d'installer des paquets à la première compilation.
- L'application n'envoie rien, ne se met pas à jour seule et n'installe jamais Git ni LaTeX.
- Licences : le dossier `legal` de l'installation contient `LICENSE` (licence MIT de ModularCV), `THIRD_PARTY_NOTICES.md` (inventaire des composants
  tiers) et `THIRD_PARTY_LICENSES.txt` (leurs textes de licence et mentions de droits d'auteur). Quelques points ne sont pas tranchés (conditions des
  fichiers de runtime C de Microsoft, version du chargeur WebView2) ; ils sont listés à la fin de ce dernier fichier.

Liste complète : [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (en anglais).

## Désinstaller

**Paramètres > Applications > Applications installées > ModularCV Desktop > Désinstaller**. Vos espaces de travail ne sont jamais touchés.
Sur la première page du désinstalleur, la case **« Delete the application data »** (supprimer les données de l'application, affichée en anglais) est
**décochée par défaut** : le bouton par défaut ne retire que le programme. Cochée, elle supprime uniquement `%APPDATA%\org.modularcv.desktop` et
`%LOCALAPPDATA%\org.modularcv.desktop` (réglages, espaces de démonstration). Testé sur une installation jetable avec des fichiers fictifs : un espace dans
Documents et des dossiers voisins au nom proche n'ont pas été touchés.
Ne gardez pas d'espace de travail réel dans `%LOCALAPPDATA%\org.modularcv.desktop` ni `%APPDATA%\org.modularcv.desktop`.
