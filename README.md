# Téléphones auto — publier sur TikTok et Instagram depuis un iPhone, tout seul

Un petit service qui tourne sur ton ordinateur (Windows ou Mac), tient un iPhone branché en USB et s'en sert **comme
une personne** : il ouvre TikTok ou Instagram, passe sur le bon compte, choisit la vidéo, tape la légende et publie.
Tu le pilotes depuis une page web locale (http://127.0.0.1:4330/telephones/) :

- **l'écran de l'iPhone en direct**, cliquable (toucher, glisser, écrire) ;
- **les comptes** connectés sur l'iPhone, rangés en **groupes** (par exemple le TikTok et l'Insta d'une même page) ;
- **la file des publications** : une vidéo, un compte, une légende, une heure ; chaque publication garde une capture
  d'écran par étape ;
- **la programmation automatique** : tu déposes une vidéo dans `videos/<groupe>/`, elle part toute seule sur les
  comptes du groupe au prochain **créneau** (9 h, 12 h, 15 h, 18 h, 21 h par défaut, à ± 15 min tirées au hasard) ;
- **le calendrier** : ce qui sort quand, sur quels comptes, et ce qui est raté ;
- **le warm-up automatique** des nouveaux comptes : quelques jours à scroller leur niche (recherche de mots-clés, vidéos
  regardées, quelques likes et abonnements) avant de publier ; ou le **warm-up rapide**, des séances d'affilée jusqu'à
  l'heure que tu choisis ;
- **le hub** : la santé de chaque page (vues, shadowban probable, chute, compte déconnecté), les vues par jour et par
  semaine, l'état des téléphones, avec des **alertes Discord** en option ;
- **plusieurs iPhone et plusieurs pages** : montée en charge d'une page neuve (1 vidéo le 1er jour, 2 le 2e… jusqu'à 5),
  objectif de publications par jour, projets séparés sur un même téléphone ;
- **YouTube Shorts**, par l'app YT Studio de l'iPhone, en plus de TikTok et Instagram.

```
 ton ordinateur ──USB──▶ iPhone
   service Python          WebDriverAgent (l'agent de test d'Apple, signé avec ton Apple ID)
   page web locale         TikTok, Instagram, YT Studio (tes comptes, connectés par toi)
   videos/  ──▶ la vidéo passe par le câble ──▶ VLC ──▶ Raccourci « Auto importer » ──▶ Photos ──▶ l'app
```

## À savoir avant de commencer

- **Les conditions d'utilisation.** Automatiser TikTok ou Instagram depuis un téléphone va contre leurs règles : le
  risque qu'un compte soit restreint est faible mais réel. Le service publie à un rythme normal (un compte au plus
  toutes les 30 min, des heures qui varient) et le warm-up n'écrit jamais de commentaire ni de message.
- **Le logiciel ne tape jamais de mot de passe.** Tu te connectes toi-même à tes comptes, sur l'iPhone, une fois ; tu
  te connectes toi-même à ton Apple ID dans Impactor.
- **Rien ne part par surprise.** Seules les vidéos du dossier `videos/` peuvent partir (le fichier est relu au moment
  de publier). Une publication ratée après le dernier bouton n'est **jamais** relancée toute seule (elle est peut-être déjà en ligne) :
  tu regardes son déroulé et tu décides. Seul un échec passager d'une page, AVANT le dernier bouton, est retenté une fois. Le mode **Répétition** fait tout le parcours sans toucher le dernier bouton.
- **Un iPhone dédié** est le plus simple : sans code de verrouillage (sinon le robot ne peut pas le réveiller), en
  français, toujours branché.
- **Avec un Apple ID gratuit, l'agent doit être re-signé chaque semaine** (un clic dans Impactor : le service corrige
  le reste tout seul). Un compte développeur Apple payant (99 €/an) le signe pour un an.

## Installer

**Le plus simple : avec Claude Code.** Ouvre ce dossier dans Claude Code et dis-lui :

> Installe-moi ce système, pas à pas.

[`CLAUDE.md`](CLAUDE.md) lui explique tout : ce qu'il fait lui-même, ce que toi seul peux faire (brancher, « Se fier »,
te connecter), et comment vérifier chaque étape.

**À la main :** suis [`docs/INSTALLATION.md`](docs/INSTALLATION.md) (ordinateur), puis [`docs/IPHONE.md`](docs/IPHONE.md)
(iPhone), puis [`docs/UTILISATION.md`](docs/UTILISATION.md). En cas de souci : [`docs/DEPANNAGE.md`](docs/DEPANNAGE.md).

Ce qu'il faut :

| | |
|---|---|
| un ordinateur | Windows 10/11 (le chemin le plus éprouvé) ou macOS ; allumé, sans mise en veille |
| un iPhone | iOS 17 ou plus récent (calé sur iOS 26.5, iPhone 12), câble de données |
| un Apple ID | gratuit (agent à re-signer chaque semaine) ou développeur payant |
| sur l'iPhone | TikTok, Instagram, VLC (gratuit), l'app Raccourcis, l'app Fichiers ; YT Studio pour YouTube |
| en option | une clé [Scrape Creators](https://scrapecreators.com) (liens, vues, hub, santé des pages) ; un serveur Discord (alertes) |
| sur l'ordinateur | Python 3.12, go-ios, Impactor, pymobiledevice3 ; sur Windows le pilote Apple Mobile Device Support |

## Tous les jours

1. Dépose tes vidéos dans `videos/<nom du groupe>/` (avec `ma-video.txt` à côté pour la légende) : elles partent
   seules aux créneaux. Ou publie-en une à la main depuis l'onglet **Publications**.
2. Regarde le **📅 Calendrier** : ce qui est parti (avec le lien), ce qui arrive, ce qui a raté.
3. Pour un nouveau compte : **🔥 Warm-up**, ses mots-clés de niche, 7 jours (ou ⚡ rapide) : tout le reste est automatique.
4. Regarde le **hub**, en tête du Calendrier : la santé des pages et ce qui demande ton attention.

## Ce qu'il y a dans le dossier

| | |
|---|---|
| `service/` | le service (Python 3.12, aiohttp) : `parc.py` et `appareil.py` (les iPhone branchés et leur préparation), `wda.py` (l'agent), `goios.py`, `signature.py` (re-signature de l'agent), `photos.py` (la vidéo dans la pellicule), `publication.py` (la file), `programmation.py` (les créneaux, les pages, l'objectif), `partage.py` (plusieurs projets sur un iPhone), `chauffe.py` (le warm-up), `inventaire.py` (les comptes connectés sur chaque iPhone), `sante.py` et `salons.py` (la santé, les alertes Discord), `videos.py` (le dossier des vidéos), `liens.py` (le lien publié, en option), `recettes/` (TikTok, Instagram, YouTube), `stock.py` (SQLite), `serveur.py` (l'API et la page) |
| `interface/` | la page web (JavaScript simple, sans build) |
| `tests/` | un **faux iPhone** (go-ios, WebDriverAgent, un mini TikTok et un mini Instagram) et un essai complet du service contre lui : `python tests/essai_local.py` (macOS ou Linux), plus les essais `tests/essai_*.py` (pages, objectif, corbeille, partage, YouTube) |
| `outils/` | `preparer_agent.py` (fabrique l'IPA de l'agent), `lancer.bat` / `lancer.sh` |
| `docs/` | installation, iPhone, utilisation, dépannage, recettes |
| `lieux.exemple.json` | les chemins et les ports, à copier en `lieux.json` |

Tout ce qui est propre à ton installation (`lieux.json`, `donnees/`, `videos/`, le certificat `.p12`) reste hors du
dépôt (`.gitignore`).
