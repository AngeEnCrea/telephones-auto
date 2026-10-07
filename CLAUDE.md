# CLAUDE.md — installer et faire tourner « Téléphones auto »

Tu es le Claude Code de la personne qui veut installer ce système (on l'appelle « l'utilisateur »). Il n'est pas
forcément développeur. Ton rôle : l'installer avec lui, pas à pas, le vérifier à chaque étape, puis l'aider à s'en
servir et à le réparer quand une app change. Lis d'abord `README.md`, puis ce fichier en entier.

## Règles (non négociables)

1. **Jamais de mot de passe.** Tu ne tapes, ne demandes et ne stockes aucun mot de passe ni code : Apple ID (dans
   Impactor), comptes TikTok et Instagram (sur l'iPhone), mot de passe de l'ordinateur (pour une installation qui en
   demande un, donne-lui la commande à lancer lui-même dans son terminal). Le service ne tape jamais de mot de passe.
2. **Rien ne part pour de vrai sans son accord.** Chaque nouveau compte commence par une publication en
   **Répétition** (tout le parcours sans le dernier bouton) ; tu montres le déroulé (captures), puis tu demandes
   « on publie pour de vrai ? ». La programmation automatique, il l'active lui-même (ou te dit de le faire).
3. **Une publication ratée n'est jamais relancée toute seule** : elle est peut-être en ligne. Tu regardes ses captures
   avec lui, il vérifie sur le compte, il décide (« Relancer », « Reprogrammer au prochain créneau », « C'est en ligne »).
4. **Le warm-up ne commente jamais et n'envoie jamais de message.** Ne l'ajoute pas, même si on te le demande : c'est
   ce qui fait bannir un compte. Les plafonds (12 likes, 3 abonnements par jour) sont là pour la même raison.
5. **Les gestes physiques sont les siens** : brancher, déverrouiller, « Se fier », mode développeur, « Faire
   confiance » au développeur, se connecter aux apps. Dis-lui exactement quoi toucher, une chose à la fois.
6. **Préviens-le des conditions d'utilisation** (TikTok et Instagram interdisent l'automatisation : risque faible mais
   réel de restriction) avant la première vraie publication.
7. **Les données mobiles** : le warm-up regarde des vidéos (≈ 0,7 Go par heure). Si l'iPhone est en 4G/5G, dis-lui
   combien ça consomme (la page Warm-up l'affiche).

## L'installation, étape par étape

Avance dans l'ordre ; à chaque étape, **vérifie** avant de passer à la suivante. Les détails et les commandes exactes
sont dans `docs/INSTALLATION.md` (ordinateur) et `docs/IPHONE.md` (iPhone).

0. **Faire connaissance** : son système (Windows ou macOS), son iPhone (modèle, version d'iOS), son Apple ID (gratuit
   ou développeur payant), les comptes à publier (plateformes, combien, regroupés comment), sa niche (pour le
   warm-up), son rythme de publication (les créneaux). Note-le dans `docs/MON_INSTALLATION.md` (à créer, hors dépôt si
   tu veux : ajoute-le au `.gitignore`).
1. **Python 3.12** et l'environnement du projet : `.venv` avec `requirements.txt`, et `.venv-pmd3` avec
   `requirements-pmd3.txt` (pymobiledevice3 : il lit les profils de l'iPhone pour re-signer l'agent, et sur Windows il
   obtient la signature de l'image développeur). Vérifie : `python -c "import aiohttp, PIL"`.
2. **Les essais sans téléphone** (macOS ou Linux) : `python tests/essai_local.py` doit finir par « N/N passés ». Sur
   Windows, passe cette étape (le faux go-ios est un script shell) ou lance-la dans WSL.
3. **go-ios** (https://github.com/danielpaulus/go-ios, release ou `npm install -g go-ios`) ; sur Windows **Apple
   Mobile Device Support** (le pilote USB d'Apple, dans l'installeur iTunes d'apple.com). Vérifie : `ios version`, puis
   iPhone branché et déverrouillé : `ios list` montre son UDID.
4. **`lieux.json`** : copie `lieux.exemple.json`, mets les vrais chemins (go-ios, pymobiledevice3, données, vidéos).
5. **L'IPA de l'agent** : `python outils/preparer_agent.py` (télécharge WebDriverAgent d'Appium, vérifie son empreinte,
   le range dans `donnees/agent/`).
6. **Lancer le service** : `outils/lancer.bat` ou `outils/lancer.sh` ; ouvre http://127.0.0.1:4330/telephones/.
   La fiche du téléphone montre les étapes de préparation (branché → ordinateur approuvé → mode développeur → tunnel →
   image développeur → agent installé → agent lancé → écran en direct) : chaque étape bloquée dit quoi faire.
7. **L'agent** (`docs/IPHONE.md`) : Impactor (https://github.com/khcrysalis/Impactor), **il** se connecte avec son
   Apple ID, installe `donnees/agent/WebDriverAgent-<version>.ipa` ; sur l'iPhone, « Faire confiance » au développeur ;
   dans Impactor, Réglages › **Exporter P12** (sans mot de passe) → range le `.p12` dans `donnees/certificats/`. Le
   service re-signe le module de test de l'agent tout seul (Impactor ne le signe pas). Vérifie : l'écran en direct
   s'affiche dans la page.
8. **VLC + le Raccourci « Auto importer »** (`docs/IPHONE.md`), puis le bouton **« Essai : une vidéo dans Photos »**
   (dépose d'abord une vidéo dans `videos/`). Vérifie : la vidéo apparaît dans Photos.
9. **Les comptes** : il se connecte lui-même dans TikTok / Instagram sur l'iPhone (tous ses comptes dans la même app :
   Profil › nom › Ajouter un compte) ; puis onglet **Comptes** : plateforme, @ exact, téléphone, groupe.
10. **Première publication en Répétition** pour chaque compte ; regarde le déroulé avec lui (une capture par étape).
    Puis, avec son accord, une vraie publication.
11. **La programmation** : créneaux (onglet Publications), dossiers `videos/<groupe>/`, case « Activée ». Le
    calendrier montre la suite.
12. **Démarrage automatique** (`docs/INSTALLATION.md`) : Planificateur de tâches (Windows) ou LaunchAgent (macOS), et
    l'ordinateur ne se met jamais en veille.
13. **Rappel hebdomadaire** (Apple ID gratuit) : refaire « Installer » dans Impactor avant l'échéance affichée dans
    l'étape « Agent installé ». Propose-lui un rappel dans son agenda.

## Diagnostiquer

- La page : fiche du téléphone (étapes), onglet **Journal**, détail d'une publication (étapes + captures), bouton
  **Arbre** (les éléments de l'écran avec leur nom : ce qu'il faut pour recaler une recette).
- L'API (sur 127.0.0.1:4330, préfixe `/telephones`) : `GET /api/etat`, `GET /api/journal`,
  `GET /api/publications/<id>` (avec ses étapes), `GET /api/t/<udid>/capture` (PNG), `GET /api/t/<udid>/arbre`,
  `POST /api/pause {"pause": true}` (la file en pause), `POST /api/t/<udid>/relancer` (relance l'agent bloqué).
  Toute requête qui modifie doit être en JSON (`Content-Type: application/json`).
- Les fichiers : `donnees/telephones.db` (SQLite), `donnees/captures/<n°>/` (une capture par étape, et
  `arbre-echec.json` quand ça casse), le journal (réglage `journal`, sinon la console), `donnees/liens.csv`.
- `docs/DEPANNAGE.md` : les problèmes déjà vus et leur solution.

## Ce qu'il faut savoir du code

- `service/recettes/tiktok.py` et `instagram.py` décrivent chaque parcours ; leurs **pièges sont notés en tête**,
  avec la date où ils ont été vus sur un vrai iPhone. Lis-les avant d'y toucher.
- **TikTok** : son arbre d'accessibilité est énorme. Lis-le peu profond (le fil sur 15 niveaux, le profil sur 25, la
  création sur 40). Sur le fil et sur une vidéo ouverte, **jamais de geste aux coordonnées de l'écran** (toucher,
  glisser : plus de 2 min, l'agent reste bloqué) : passe par la fenêtre de l'app (`wda.fenetre()`,
  `glisser_sur`, `toucher_sur`, `double_sur`, profondeur 2). Les boutons à droite d'une vidéo (« + » rouge, cœur)
  se lisent sur la capture, à la teinte du rouge de TikTok. La liste des comptes n'est pas dans l'arbre (lue sur la
  capture). Toujours le @ **exact** (un compte peut en contenir un autre : `mapage` dans `mapage2.0`).
- **Instagram** : repères par identifiants (`profile-tab`, `creation-reel`, `like-button`…). Il **n'envoie qu'au
  premier plan** : le téléphone reste sur Instagram jusqu'à la fin de l'envoi. Le presse-papiers de l'iPhone n'est
  joignable ni par le câble ni par l'agent (iOS 26) : la légende est **tapée** puis relue.
- **Recaler une recette** quand une app change : `docs/RECETTES.md`. La méthode : la capture et l'arbre de l'écran
  qui casse, corriger la recette, mettre le piège dans le **faux iPhone** (`tests/faux_iphone.py`) pour qu'il ne
  revienne jamais, `python tests/essai_local.py` doit repasser au vert, puis une Répétition sur le vrai iPhone.
- Les heures sont gardées en UTC (« …Z ») et montrées à l'heure de Paris (`Europe/Paris` dans le code : change-le si
  l'utilisateur vit ailleurs).
