# Préparer l'iPhone (une fois)

Ce sont tes gestes, sur le téléphone : le service ne peut pas les faire à ta place. La page
http://127.0.0.1:4330/telephones/ suit la préparation étape par étape et dit, quand une étape bloque, quoi faire.

## 1. Les réglages

- **Pas de code de verrouillage** (Réglages › Face ID et code › Désactiver le code) : sinon le robot ne peut pas
  réveiller le téléphone. C'est pourquoi un iPhone dédié est préférable.
- **Verrouillage automatique** : 5 min (Réglages › Luminosité et affichage).
- **Langue française** (Réglages › Général › Langue) : les recettes cherchent les boutons par leurs noms français
  (certains ont aussi leur nom anglais).
- **Photos iCloud coupé** (Réglages › Photos) : la pellicule reste sur le téléphone.
- **Mises à jour automatiques des apps coupées** (Réglages › App Store) : une nouvelle version de TikTok ou
  d'Instagram peut déplacer un bouton et casser une recette ; mets à jour à la main, puis fais une Répétition.
- **Ne pas déranger** allumé : pas de notification au milieu d'une publication.
- **Internet** : Wi-Fi, ou un forfait de données (option « Publier seulement en Wi-Fi » dans la page si besoin).
- L'app **Fichiers** d'Apple doit être installée (le Raccourci s'en sert).

## 2. Brancher et faire confiance

Branche l'iPhone à l'ordinateur avec un **câble de données**, déverrouille-le, touche **« Se fier »** à cet
ordinateur (et tape ton code si iOS le demande ce jour-là). La page passe à l'étape suivante.

## 3. Le mode développeur

La page fait apparaître le menu ; sur l'iPhone : Réglages › Confidentialité et sécurité › **Mode développeur** ›
activer ; l'iPhone redémarre ; confirmer **« Activer »**. Ensuite le service ouvre le tunnel (iOS 17+) et monte
l'image développeur tout seul.

## 4. L'agent (WebDriverAgent), signé avec ton Apple ID

L'agent est l'app de test d'Apple qui touche, glisse, écrit et lit l'écran. Il doit être signé avec un Apple ID :

1. Ouvre **Impactor** sur l'ordinateur, **connecte-toi avec ton Apple ID** (toi-même), choisis le fichier
   `donnees/agent/WebDriverAgent-<version>.ipa`, options par défaut (signature « Apple ID », mode « Installer »),
   **Installer**.
2. Sur l'iPhone, connecté à Internet : Réglages › Général › **VPN et gestion de l'appareil** › ton Apple ID
   (« App de développeur ») › **Faire confiance**.
3. Dans Impactor : Réglages › **Exporter P12** (sans mot de passe), et range le fichier `.p12` dans
   `donnees/certificats/` (dossier réglé par `certificats`). À refaire une fois par an (durée du certificat).

**Pourquoi le service re-signe l'agent.** Impactor signe l'app mais laisse son module de test
(`WebDriverAgentRunner.xctest`) sans signature, et iOS refuse de le charger (« Failed to load the test bundle »). Le
service le voit, lit sur l'iPhone le profil qu'Impactor y a mis, re-signe l'agent avec go-ios et le certificat
exporté, le réinstalle et le relance (`service/signature.py`).

**Chaque semaine (Apple ID gratuit)** : le profil dure 7 jours. Avant l'échéance affichée dans l'étape « Agent
installé », refais simplement « Installer » dans Impactor : le service corrige derrière, tout seul. (Un compte
développeur Apple payant donne un an.)

Quand l'agent tourne, **l'écran de l'iPhone s'affiche en direct dans la page** : tu peux cliquer dessus.

## 5. VLC et le Raccourci « Auto importer »

TikTok et Instagram ne publient que depuis la pellicule (Photos). Le service y range chaque vidéo par le câble : il
la dépose dans le dossier de **VLC** (app gratuite dont le dossier est ouvert à l'ordinateur), puis lance le
Raccourci **« Auto importer »** qui la range dans Photos.

1. Installe **VLC** depuis l'App Store et ouvre-le une fois.
2. Dans l'app **Raccourcis**, crée un raccourci nommé exactement **`Auto importer`**, avec deux actions (noms d'iOS 26) :
   - **Récupérer le fichier dans le dossier** : Dossier « Sur mon iPhone › VLC », chemin du fichier **`import/`**
     suivi de la variable **Entrée du raccourci** (sans cette variable, le Raccourci prend le dossier entier et échoue) ;
   - **Enregistrer dans l'album photo** (Récents).
3. Dans la page, dépose d'abord une vidéo dans `videos/`, puis bouton **« Essai : une vidéo dans Photos »**. La
   première fois, Raccourcis demande l'accès au dossier de VLC et à Photos : le service touche « Toujours autoriser ».
   La vidéo doit apparaître dans Photos.

Chaque publication laisse sa vidéo dans la pellicule : vide-la de temps en temps (sans toucher à tes propres photos).

## 6. Les comptes

1. **Connecte-toi toi-même** à chaque compte dans l'app, sur l'iPhone. Plusieurs comptes dans la même app :
   TikTok › Profil › ton nom (en haut) › Ajouter un compte ; Instagram › Profil › ton nom › Ajouter un compte.
2. Dans la page, onglet **Comptes** : plateforme, @ exact, le téléphone, et un **groupe** (les comptes qui publient
   les mêmes vidéos, par exemple le TikTok et l'Insta d'une même page).
3. Onglet **Publications** › Nouvelle publication, coche **Répétition** : le robot fait tout le parcours sans le
   dernier bouton. Regarde son déroulé (une capture par étape). Si tout est bon, « Publier pour de vrai ».

Le partage automatique sur Facebook, s'il est réglé sur un compte Instagram, reste comme tu l'as réglé : la recette
n'y touche pas.
