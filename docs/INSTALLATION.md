# Installer le service sur l'ordinateur

Deux chemins : **Windows** (le plus éprouvé : c'est là que tout a été calé, d'octobre 2026) et **macOS** (même
service ; moins éprouvé, les écarts sont signalés). À la fin, la page http://127.0.0.1:4330/telephones/ s'ouvre et
montre l'iPhone branché.

L'ordinateur doit rester **allumé et sans mise en veille** : c'est lui qui publie aux créneaux.

---

## Windows 10 / 11

Exemple de dossiers (tu peux en choisir d'autres : ils se règlent dans `lieux.json`) :

```
C:\Telephones\            le dépôt (service\, interface\, …), lieux.json, .venv\, .venv-pmd3\
C:\Telephones\donnees\    la base, les captures, l'agent, le certificat (créé tout seul)
C:\Telephones\videos\     les vidéos à publier
C:\Outils\go-ios\ios.exe  go-ios
```

1. **Le dépôt** : `git clone <adresse du dépôt> C:\Telephones` (ou télécharger le zip et le décompresser là).
2. **Python 3.12** : https://www.python.org/downloads/ (cocher « Add python.exe to PATH ») ou
   `winget install Python.Python.3.12`. Puis, dans `C:\Telephones` :
   ```bat
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   py -3.12 -m venv .venv-pmd3
   .venv-pmd3\Scripts\python -m pip install -r requirements-pmd3.txt
   ```
   (`pymobiledevice3` vit à part : il a beaucoup de dépendances. Il lit les profils de l'iPhone pour re-signer
   l'agent, et obtient la signature de l'image développeur que go-ios n'obtient pas sur Windows.)
3. **Le pilote USB d'Apple** (« Apple Mobile Device Support ») : installe **iTunes** depuis
   https://www.apple.com/itunes/ (la version 64 bits du site d'Apple, pas celle du Microsoft Store), ou seulement
   `AppleMobileDeviceSupport64.msi` extrait de son installeur avec 7-Zip. Vérifie dans les Services Windows :
   « Apple Mobile Device Service » tourne.
4. **go-ios** : https://github.com/danielpaulus/go-ios/releases (calé avec la 1.3.2), le zip Windows, décompressé dans
   `C:\Outils\go-ios\`. Vérifie : `C:\Outils\go-ios\ios.exe version`. Pas besoin de droits administrateur ni de
   wintun : le service lance le tunnel iOS 17+ en mode `--userspace`.
5. **Impactor** (signe l'agent avec ton Apple ID) : https://github.com/khcrysalis/Impactor/releases, la version
   Windows.
6. **`lieux.json`** : copie `lieux.exemple.json` en `lieux.json` et adapte les chemins (doubler les `\`).
7. **L'IPA de l'agent** :
   ```bat
   .venv\Scripts\python outils\preparer_agent.py
   ```
   Il télécharge WebDriverAgent publié par Appium (16.13.6 par défaut ; une autre version en argument), vérifie son
   empreinte et range `WebDriverAgent-16.13.6.ipa` dans `donnees\agent\`.
8. **Lancer** : `outils\lancer.bat`, puis ouvrir http://127.0.0.1:4330/telephones/. La suite se passe sur l'iPhone :
   [`IPHONE.md`](IPHONE.md).
9. **Démarrage automatique** (quand tout marche) : Planificateur de tâches › Créer une tâche :
   - Général : nom « Telephones », « Exécuter seulement si l'utilisateur est connecté » (le plus simple : la session
     Windows reste ouverte ; sinon « que l'utilisateur soit connecté ou non », qui demande ton mot de passe Windows,
     à taper toi-même) ;
   - Déclencheurs : « À l'ouverture de session », avec « Répéter la tâche toutes les 5 minutes » pendant
     « Indéfiniment » ;
   - Actions : programme `C:\Telephones\.venv\Scripts\pythonw.exe` (sans fenêtre), arguments
     `C:\Telephones\service\telephones.py`, commencer dans `C:\Telephones` ;
   - Paramètres : décocher « Arrêter la tâche si elle s'exécute plus de… » ; « Si la tâche est déjà en cours :
     ne pas démarrer une nouvelle instance ».

   Le service ne tourne qu'en un exemplaire (s'il trouve son port pris, il s'arrête) : la répétition toutes les 5 min
   le relance seulement s'il est tombé.

   Et l'alimentation : Paramètres › Système › Alimentation › mise en veille **Jamais** (sur secteur).

## macOS

1. **Outils** : Homebrew (https://brew.sh), puis
   ```sh
   brew install python@3.12
   brew install --cask impactor
   npm install -g go-ios        # ou le zip macOS des releases de go-ios ; il faut Node pour npm
   ```
   Pas de pilote à installer : macOS parle déjà à l'iPhone.
2. **Le dépôt** : `git clone <adresse du dépôt> ~/Telephones`, puis dans `~/Telephones` :
   ```sh
   python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
   python3.12 -m venv .venv-pmd3 && .venv-pmd3/bin/pip install -r requirements-pmd3.txt
   ```
3. **Les essais sans téléphone** (une minute ou dix, tout doit passer) :
   ```sh
   .venv/bin/python tests/essai_local.py
   ```
4. **`lieux.json`** : copie `lieux.exemple.json` ; `"ios"` = le chemin de `which ios`, `"pymobiledevice3"` =
   `/Users/<toi>/Telephones/.venv-pmd3/bin/pymobiledevice3` ; enlève les chemins Windows (les valeurs par défaut
   rangent tout sous `donnees/` et `videos/`).
5. **L'IPA de l'agent** : `.venv/bin/python outils/preparer_agent.py`.
6. **Lancer** : `outils/lancer.sh`, puis http://127.0.0.1:4330/telephones/ et [`IPHONE.md`](IPHONE.md).
7. **Démarrage automatique** : un LaunchAgent, `~/Library/LaunchAgents/com.telephones.auto.plist` :
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>Label</key><string>com.telephones.auto</string>
     <key>ProgramArguments</key><array>
       <string>/Users/TOI/Telephones/.venv/bin/python</string>
       <string>/Users/TOI/Telephones/service/telephones.py</string>
     </array>
     <key>WorkingDirectory</key><string>/Users/TOI/Telephones</string>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
   </dict></plist>
   ```
   puis `launchctl load ~/Library/LaunchAgents/com.telephones.auto.plist`. Et Réglages › Énergie : empêcher la mise
   en veille automatique (Mac de bureau, ou portable branché capot ouvert).

   Écarts possibles sur macOS : l'image développeur et le tunnel passent normalement par go-ios seul (pymobiledevice3
   ne sert qu'à lire les profils) ; si une étape de préparation bloque, son message le dit : voir
   [`DEPANNAGE.md`](DEPANNAGE.md).

## Option : le lien de chaque vidéo publiée

Le service peut retrouver l'adresse de chaque vidéo publiée (TikTok et Instagram) grâce à
[Scrape Creators](https://scrapecreators.com) (service payant, à crédits) : mets ta clé dans
`donnees/secrets/scrapecreators.env` (dossier réglé par `secrets`) :

```
SCRAPECREATORS_API_KEY=ta-clé
```

Sans clé, tout marche pareil : la publication est notée « publiée », sans lien (« Lien pas retrouvé »). Les liens
trouvés sont aussi notés dans `donnees/liens.csv`.
