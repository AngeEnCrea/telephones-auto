# Dépannage

Les problèmes déjà vus sur un vrai iPhone, et quoi faire. Pour tout le reste : la fiche du téléphone (l'étape bloquée
dit pourquoi), le détail de la publication (une capture par étape), l'onglet Journal.

## La préparation du téléphone

| Ce que tu vois | Quoi faire |
|---|---|
| « Branche l'iPhone… » alors qu'il est branché | câble de **données** (pas seulement de charge) ; sur Windows, « Apple Mobile Device Service » doit tourner (Services) ; `ios list` doit montrer l'UDID |
| « Ordinateur approuvé » bloqué | déverrouiller l'iPhone, toucher « Se fier » ; si rien ne s'affiche : débrancher, rebrancher |
| « Mode développeur » bloqué | Réglages › Confidentialité et sécurité › Mode développeur ; l'iPhone redémarre ; « Activer » |
| « Image développeur » bloquée sur Windows, `x509: certificate signed by unknown authority` | normal : go-ios n'obtient pas la signature d'Apple sur Windows ; il faut `pymobiledevice3` dans `lieux.json` (il prend le relais) |
| « Agent installé » : échéance dépassée, ou l'agent ne démarre plus | Apple ID gratuit = 7 jours : refaire « Installer » dans Impactor ; le service re-signe et relance tout seul |
| « Failed to load the test bundle » / « module de test pas signé » | le certificat exporté d'Impactor manque : Impactor › Réglages › Exporter P12 → `donnees/certificats/` |
| « Déverrouille l'iPhone » | enlever le code de verrouillage (le robot ne sait pas le taper) |

## L'agent ne répond plus

« l'agent ne répond pas (TimeoutError) », l'écran en direct figé, des gestes qui prennent des minutes :

1. le bouton **⟳ Agent** sous l'écran (ou `POST /api/t/<udid>/relancer`, ou débrancher/rebrancher) : le service
   relance l'agent (une minute) ;
2. si une app est restée ouverte sur un fil vidéo : ramène l'iPhone à l'écran d'accueil (bouton accueil de la page),
   ferme l'app.

Cause connue : sur le fil de TikTok et sur une vidéo ouverte, l'arbre de l'écran est énorme. Un geste **aux
coordonnées de l'écran** (toucher, glisser) y fait relire tout l'arbre à l'agent : plus de 2 minutes, et tout ce qui
suit attend. Les recettes passent donc par **la fenêtre de l'app** (gestes « sur un élément », 0,4 s) et lisent l'écran
peu profond. Si tu écris une recette : voir [`RECETTES.md`](RECETTES.md).

## La vidéo n'arrive pas dans Photos

- « VLC n'est pas installé » : l'installer (App Store) et l'ouvrir une fois.
- « le Raccourci « Auto importer » n'a pas rangé la vidéo » : vérifier son **nom exact**, ses deux actions, le chemin
  `import/` **suivi de la variable « Entrée du raccourci »**, et que l'app **Fichiers** est installée.
- La première fois, Raccourcis demande l'accès au dossier de VLC et à Photos : le service touche « Toujours
  autoriser » ; si ça bloque, l'accepter à la main une fois.

## TikTok

- **Une fenêtre à l'ouverture** (« Mise à jour des Règles », « J'ai compris », amis, avis) : la recette en ferme
  plusieurs ; une nouvelle → la capture du déroulé la montre : ajouter son bouton dans `INTRUS` (`tiktok.py`).
- **« @x n'est pas parmi les comptes connectés »** : connecte ce compte dans TikTok sur l'iPhone (Profil › nom ›
  Ajouter un compte), avec le même @.
- **La liste des comptes ne s'ouvre pas** : le profil était en train de charger ; la recette attend et réessaie trois
  fois. Si ça persiste, la capture le montre.
- **Une répétition laisse un brouillon** (Profil › Brouillons) : TikTok garde toute vidéo passée dans l'éditeur.
  Supprime-les toi-même de temps en temps.
- **Le son ajouté par TikTok** à l'import est retiré (sa croix) ; « Publier » (pastille rouge, clavier ouvert) est
  repéré sur la capture.

## Instagram

- **Un envoi figé puis « Une erreur s'est produite »** : Instagram n'envoie qu'au premier plan ; la recette reste sur
  Instagram jusqu'à la fin de l'envoi. S'il reste de vieux envois ratés affichés (bandeaux ↻ / ✕), supprime-les à la
  main dans Instagram : la recette ne relance jamais un envoi qui n'est pas le sien.
- **« Poursuivre la modification de votre brouillon ? »** : la recette répond « Commencer une nouvelle vidéo ».
- **La galerie** : seule une vidéo du jour est choisie ; la sélection multiple est gérée.

## Les publications

- **Une publication ratée** n'est jamais relancée seule : ouvre-la, regarde la dernière capture, vérifie sur le compte.
  En ligne quand même → « C'est en ligne ✓ » ; pas en ligne → « Reprogrammer au prochain créneau » (calendrier) ou
  « Relancer ».
- **L'iPhone sans internet** : l'envoi échoue au bout de quelques minutes. Wi-Fi stable, forfait de données, ou case
  « Publier seulement en Wi-Fi ».
- **L'ordinateur s'est éteint ou mis en veille** : les créneaux manqués passent au prochain créneau libre (pas de
  rafale au réveil). Empêcher la mise en veille ; démarrage automatique ([`INSTALLATION.md`](INSTALLATION.md)).
- **« Lien pas retrouvé »** : pas de clé Scrape Creators, plus de crédits, ou la légende a été modifiée par l'app. La
  publication est bien partie : vérifier sur le compte.
- **Une légende** est **tapée** puis relue (le presse-papiers de l'iPhone n'est pas joignable sur iOS 26) : une très
  longue légende prend quelques secondes de plus.

## Le warm-up

- **« Plus sur les vidéos / les reels »** dans le journal d'une séance : une fenêtre ou une pub a fait sortir la
  séance ; elle revient au fil et continue. Si ça se répète, regarde les captures de la séance (bouton Séances).
- **« Like pas vu » / « Abonnement pas vu »** : le geste n'a pas été confirmé sur la capture (rien n'est compté).
  Si ça arrive à chaque fois, l'app a changé l'apparence de ses boutons : recaler (`RECETTES.md`).
- Une séance qui ne démarre pas : une publication arrive bientôt (elle passe avant), la file est en pause, ou la
  tranche horaire du jour est passée.
