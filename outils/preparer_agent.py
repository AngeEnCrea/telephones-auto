"""preparer_agent.py [version] : fabrique l'IPA de WebDriverAgent à signer avec Impactor
(donnees/agent/WebDriverAgent-<version>.ipa, ou le dossier du réglage « agent » de lieux.json). Part de la version
réelle-appareil publiée par Appium sur GitHub (WebDriverAgentRunner-Runner.zip, non signée), vérifie son empreinte
contre celle que GitHub publie, retire les symboles de débogage (.dSYM, refusés dans PlugIns) et range l'app dans
Payload/ en gardant les droits Unix des fichiers (l'exécutable doit le rester).

  .venv\\Scripts\\python outils\\preparer_agent.py          (Windows ; 16.13.6 par défaut, ou une autre version en argument)
  .venv/bin/python outils/preparer_agent.py              (macOS, Linux)
"""
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "service"))
import lieux  # noqa: E402

VERSION = sys.argv[1] if len(sys.argv) > 1 else "16.13.6"
DOSSIER = lieux.AGENT
NOM = "WebDriverAgentRunner-Runner.zip"


def main():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"https://api.github.com/repos/appium/WebDriverAgent/releases/tags/v{VERSION}", timeout=30) as r:
        actif = next(a for a in json.load(r)["assets"] if a["name"] == NOM)
    attendue = actif["digest"].split(":", 1)[1]
    brut = DOSSIER / f"{NOM[:-4]}-{VERSION}.zip"
    urllib.request.urlretrieve(actif["browser_download_url"], brut)
    vue = hashlib.sha256(brut.read_bytes()).hexdigest()
    if vue != attendue:
        brut.unlink()
        sys.exit(f"EMPREINTE DIFFÉRENTE ({vue} au lieu de {attendue}) : rien n'est fabriqué")
    ipa = DOSSIER / f"WebDriverAgent-{VERSION}.ipa"
    gardes = retires = 0
    with zipfile.ZipFile(brut) as src, zipfile.ZipFile(ipa, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if ".dSYM/" in info.filename or info.filename.endswith(".dSYM"):
                retires += 1
                continue
            copie = zipfile.ZipInfo("Payload/" + info.filename, info.date_time)
            copie.external_attr, copie.create_system = info.external_attr, info.create_system
            copie.compress_type = zipfile.ZIP_STORED if info.is_dir() else zipfile.ZIP_DEFLATED
            dst.writestr(copie, b"" if info.is_dir() else src.read(info))
            gardes += 1
    print(f"empreinte vérifiée ({vue[:16]}…) ; {ipa} : {gardes} entrées, {retires} de débogage retirées")


if __name__ == "__main__":
    main()
