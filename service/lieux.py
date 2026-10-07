"""lieux.py : où vivent les choses. lieux.json, à la racine (à côté de README.md), donne les chemins et les ports :
copie lieux.exemple.json en lieux.json et adapte-le. Sans lui, des valeurs par défaut (tout sous donnees/ et videos/,
à la racine). Les variables d'environnement TELEPHONES_* passent devant (les essais s'en servent pour brancher le
faux go-ios)."""
import json
import os
import shutil
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _charger():
    try:
        return json.loads((RACINE / "lieux.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


L = _charger()
SUR_LE_PC = bool(L)                        # lieux.json présent : l'installation réelle (sans lui : développement, essais)
HOTE = L.get("hote", "127.0.0.1")
PORT = int(os.environ.get("TELEPHONES_PORT") or L.get("port") or 4330)
PREFIXE = "/telephones"                    # l'interface : http://127.0.0.1:4330/telephones/
IOS = os.environ.get("TELEPHONES_IOS") or L.get("ios") or shutil.which("ios") or "ios"
# pymobiledevice3 : lit les profils de l'iPhone (re-signature de l'agent, signature.py) et, sur Windows, obtient la
# signature de l'image développeur que go-ios n'obtient pas (goios.py)
PMD3 = os.environ.get("TELEPHONES_PMD3") or L.get("pymobiledevice3")
DONNEES = Path(os.environ.get("TELEPHONES_DONNEES") or L.get("donnees") or RACINE / "donnees")
VIDEOS = Path(os.environ.get("TELEPHONES_VIDEOS") or L.get("videos") or RACINE / "videos")       # les vidéos à publier (videos.py)
JOURNAL = os.environ.get("TELEPHONES_JOURNAL") or L.get("journal")   # None : la console
DDI = Path(L.get("ddi") or DONNEES / "ddi")                 # images développeur téléchargées par go-ios
AGENT = Path(os.environ.get("TELEPHONES_AGENT") or L.get("agent") or DONNEES / "agent")      # IPA de WebDriverAgent
CERTIFICATS = Path(os.environ.get("TELEPHONES_CERTIFICATS") or L.get("certificats") or DONNEES / "certificats")  # .p12 d'Impactor
SECRETS = Path(os.environ.get("TELEPHONES_SECRETS") or L.get("secrets") or DONNEES / "secrets")   # scrapecreators.env (liens.py)
APPAIRAGE = Path(L.get("appairage") or DONNEES / "appairage")   # identité du tunnel iOS 17+ de go-ios
PORT_AGENT = int(os.environ.get("TELEPHONES_PORT_AGENT") or L.get("port_agent", 18100))   # WebDriverAgent du rang 0 ; +1 par téléphone
PORT_FLUX = int(os.environ.get("TELEPHONES_PORT_FLUX") or L.get("port_flux", 19100))      # son écran (MJPEG) ; +1 par téléphone
