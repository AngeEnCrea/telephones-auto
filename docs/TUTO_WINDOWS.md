# Tuto Windows : de zéro à la première publication

Pour un PC Windows 10 ou 11 et un iPhone. Compte 1 à 2 heures. Pas besoin de savoir coder : copie les commandes dans
**PowerShell** (menu Démarrer › tape « PowerShell »), une à la fois.

**Le plus simple :** installe Claude Code, ouvre le dossier du projet et dis-lui « Installe-moi ce système, pas à pas ».
Il fait les étapes ci-dessous avec toi. Ce tuto sert si tu préfères le faire seul, ou pour comprendre où il en est.

> **À savoir :** TikTok et Instagram interdisent l'automatisation, tes comptes peuvent être restreints. Commence avec un
> iPhone et des comptes de test. Le logiciel ne tape jamais tes mots de passe : c'est toi qui te connectes.

## Ce qu'il te faut

- un PC qui reste allumé (c'est lui qui publie) ;
- un iPhone dédié, iOS 17 ou plus récent, et un câble de **données** ;
- un Apple ID (un gratuit suffit, mais il faudra refaire un clic chaque semaine) ;
- sur l'iPhone : TikTok, Instagram, VLC, Raccourcis et Fichiers (YT Studio pour YouTube).

## Partie 1 : le PC

### 1. Télécharger le projet

Sur [la page du projet](https://github.com/AngeEnCrea/telephones-auto) : bouton vert **Code › Download ZIP**.
Décompresse-le et renomme le dossier pour avoir `C:\Telephones` (le fichier `README.md` doit être directement dedans).

### 2. Installer Python 3.12

```powershell
winget install Python.Python.3.12
```

Ferme PowerShell, rouvre-le, puis installe ce dont le projet a besoin (plusieurs minutes) :

```powershell
cd C:\Telephones
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
py -3.12 -m venv .venv-pmd3
.venv-pmd3\Scripts\python -m pip install -r requirements-pmd3.txt
```

### 3. Installer le pilote Apple

Installe **iTunes** depuis [apple.com/itunes](https://www.apple.com/itunes/) : la version du site d'Apple, **pas celle du
Microsoft Store**. Vérifie : menu Démarrer › « Services » › **Apple Mobile Device Service** doit être « En cours d'exécution ».

### 4. Installer go-ios

Sur [les versions de go-ios](https://github.com/danielpaulus/go-ios/releases), télécharge le zip Windows (le projet est
calé avec la 1.3.2) et décompresse-le dans `C:\Outils\go-ios`. Vérifie :

```powershell
C:\Outils\go-ios\ios.exe version
```

### 5. Installer Impactor

Sur [les versions d'Impactor](https://github.com/khcrysalis/Impactor/releases), télécharge la version Windows et installe-la.
Si sa fenêtre n'apparaît pas à l'ouverture, regarde sa petite icône à côté de l'horloge.

### 6. Régler les chemins

```powershell
cd C:\Telephones
copy lieux.exemple.json lieux.json
```

Si tu as gardé les dossiers de ce tuto, il n'y a rien à changer. Sinon, ouvre `lieux.json` et adapte les chemins, en
doublant les `\`.

### 7. Préparer l'agent et lancer le service

L'agent est le petit programme qui touche l'écran de l'iPhone à ta place.

```powershell
cd C:\Telephones
.venv\Scripts\python outils\preparer_agent.py
outils\lancer.bat
```

Laisse cette fenêtre ouverte et va sur **http://127.0.0.1:4330/telephones/**. La page montre l'iPhone et te dit quoi faire à
chaque étape bloquée.

## Partie 2 : l'iPhone

### 8. Les réglages

- **Pas de code de verrouillage** : Réglages › Face ID et code › Désactiver le code.
- **Langue française** : Réglages › Général › Langue.
- **Photos iCloud coupé** : Réglages › Photos.
- **Mises à jour automatiques des apps coupées** : Réglages › App Store.
- **Ne pas déranger** allumé, et Internet (Wi-Fi ou forfait de données).

### 9. Brancher et activer le mode développeur

1. Branche l'iPhone, déverrouille-le et touche **« Se fier »**.
2. Réglages › Confidentialité et sécurité › **Mode développeur** › activer. L'iPhone redémarre : confirme **« Activer »**.

### 10. Installer l'agent

1. Ouvre **Impactor**, connecte-toi avec ton Apple ID, choisis
   `C:\Telephones\donnees\agent\WebDriverAgent-16.13.6.ipa` et clique sur **Installer**.
2. Sur l'iPhone : Réglages › Général › **VPN et gestion de l'appareil** › ton Apple ID › **Faire confiance**.
3. Dans Impactor : Réglages › **Exporter P12**, sans mot de passe. Range le fichier dans `C:\Telephones\donnees\certificats\`
   (crée le dossier s'il n'existe pas).

Le service termine le travail tout seul. **C'est bon quand l'écran de l'iPhone s'affiche en direct dans la page.**

### 11. Créer le Raccourci qui range les vidéos

1. Installe **VLC** et ouvre-le une fois.
2. Dans **Raccourcis**, crée un raccourci nommé exactement **`Auto importer`**, avec deux actions :
   - **Récupérer le fichier dans le dossier** : dossier « Sur mon iPhone › VLC », chemin `import/` suivi de la variable
     **Entrée du raccourci** (sans cette variable, ça échoue) ;
   - **Enregistrer dans l'album photo**.
3. Dépose une vidéo dans `C:\Telephones\videos\`, puis clique sur **« Essai : une vidéo dans Photos »** dans la page.

**C'est bon quand la vidéo apparaît dans Photos.**

## Partie 3 : publier

### 12. Ajouter tes comptes

1. Connecte-toi toi-même dans TikTok et Instagram sur l'iPhone (Profil › ton nom › Ajouter un compte).
2. Dans la page, onglet **Comptes** : la plateforme, le @ exact, le téléphone et un **groupe**, par exemple « Page 1 » pour le
   TikTok et l'Insta d'une même page.

### 13. Faire une répétition, puis une vraie publication

Onglet **Publications › Nouvelle publication**, coche **Répétition** : le robot fait tout sauf le dernier bouton. Regarde les
captures. Si tout est bon, clique sur **« Publier pour de vrai »**.

### 14. Mettre un compte neuf en warm-up

Page **🔥 Warm-up** : clique sur **Rafraîchir les comptes**, coche le compte, écris ses mots-clés de niche (un par ligne),
garde 7 jours et lance. Ensuite tout est automatique.

### 15. Programmer les publications

Range tes vidéos ici, avec le nom exact du groupe. Le fichier `.txt` du même nom est la légende :

```
C:\Telephones\videos\Page 1\ma-video.mp4
C:\Telephones\videos\Page 1\ma-video.txt
```

Onglet **Publications › Programmation automatique** : coche **Activée**. Les vidéos partent toutes seules aux créneaux, et le
**📅 Calendrier** montre ce qui sort et quand.

## Partie 4 : le laisser tourner

### 16. Démarrer tout seul et ne jamais dormir

- Paramètres › Système › Alimentation : mise en veille **Jamais**.
- Pour le démarrage automatique, suis l'étape 9 de la section Windows d'[`INSTALLATION.md`](INSTALLATION.md).

### 17. Le geste de chaque semaine (Apple ID gratuit)

L'agent expire au bout de 7 jours. Avant la date affichée dans l'étape « Agent installé » de la page, refais **Installer** dans
Impactor, puis **Faire confiance** sur l'iPhone si la page le demande. Mets-toi un rappel : sans ça, plus rien ne part.

## Si ça bloque

Regarde d'abord ce que dit la page, puis [`DEPANNAGE.md`](DEPANNAGE.md). Les pannes les plus fréquentes :

| Ce que tu vois | Quoi faire |
|---|---|
| « Branche l'iPhone… » alors qu'il est branché | essaie un autre câble (de données) et vérifie le service Apple de l'étape 3 |
| `py` n'est pas reconnu | ferme et rouvre PowerShell, sinon réinstalle Python en cochant « Add python.exe to PATH » |
| L'iPhone « se débranche » tout seul | le PC est à 100 % : ferme ce qui consomme, surtout les rendus vidéo |
| Plus rien ne part après une semaine | l'agent a expiré : refais l'étape 17 |

Pour aller plus loin (hub, alertes Discord, plusieurs iPhone) : [`UTILISATION.md`](UTILISATION.md).
