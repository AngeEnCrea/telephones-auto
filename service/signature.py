"""signature.py : garder l'agent signé.

Avec un Apple ID gratuit, Impactor obtient d'Apple un profil de 7 jours et installe l'agent, mais il laisse son module
de test (WebDriverAgentRunner.xctest) sans signature : iOS refuse de le charger (« Failed to load the test bundle »,
XCTest 103, mesuré le 01/10/2026). Le service re-signe donc l'agent lui-même avec go-ios, qui signe les .xctest, à
partir :
  - du certificat exporté d'Impactor (Réglages › Exporter P12, sans mot de passe), rangé dans donnees/certificats/ (réglage « certificats ») ;
  - du profil le plus récent qu'Impactor a installé sur l'iPhone (lu par pymobiledevice3, service misagent).
Chaque semaine, il suffit de refaire « Installer » dans Impactor : le service corrige derrière, tout seul."""
import datetime as dt
import logging
import plistlib
import shutil

import goios
import lieux

log = logging.getLogger("signature")


class ErreurSignature(RuntimeError):
    pass


def lire_profil(chemin):
    """Le plist d'un .mobileprovision (enveloppe CMS) : nom, identifiant d'app, équipe, dates (UTC)."""
    d = chemin.read_bytes()
    p = plistlib.loads(d[d.index(b"<?xml"):d.index(b"</plist>") + 8])
    utc = lambda x: x.replace(tzinfo=dt.timezone.utc) if x and x.tzinfo is None else x
    return {"chemin": chemin, "nom": p.get("Name"), "uuid": p.get("UUID"),
            "app_id": (p.get("Entitlements") or {}).get("application-identifier", ""),
            "equipe": (p.get("TeamIdentifier") or [""])[0],
            "cree": utc(p.get("CreationDate")), "expire": utc(p.get("ExpirationDate"))}


async def profils(udid):
    """Les profils installés sur l'iPhone, copiés dans profils/<udid>/ puis lus."""
    if not lieux.PMD3:
        raise ErreurSignature("pymobiledevice3 absent : impossible de lire les profils de l'iPhone")
    dossier = lieux.DONNEES / "profils" / udid
    shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True)
    await goios.pymobiledevice3("provision", "dump", "--udid", udid, str(dossier), delai=120)
    out = []
    for f in dossier.glob("*.mobileprovision"):
        try:
            out.append(lire_profil(f))
        except (ValueError, plistlib.InvalidFileException) as e:
            log.warning("profil illisible %s : %s", f.name, e)
    return out


def profil_de(liste, bundle):
    """Le profil valide le plus récent de l'agent (application-identifier = <équipe>.<bundle>)."""
    maintenant = dt.datetime.now(dt.timezone.utc)
    bons = [p for p in liste if p["app_id"].endswith("." + bundle) and p["expire"] and p["expire"] > maintenant]
    return max(bons, key=lambda p: p["cree"]) if bons else None


def certificat(equipe=None):
    """Le certificat exporté d'Impactor (<équipe>_certificate.p12) le plus récent."""
    if not lieux.CERTIFICATS.is_dir():
        return None
    l = sorted(lieux.CERTIFICATS.glob(f"{equipe or '*'}_certificate.p12"), key=lambda f: f.stat().st_mtime, reverse=True)
    return l[0] if l else None


def ipa_agent():
    """L'IPA de WebDriverAgent à signer (fabriquée par outils/preparer_agent.py), la version la plus récente."""
    l = sorted((f for f in lieux.AGENT.glob("WebDriverAgent-*.ipa") if "-signe" not in f.name),
               key=lambda f: f.stat().st_mtime, reverse=True) if lieux.AGENT.is_dir() else []
    return l[0] if l else None


async def resigner(udid, bundle):
    """Re-signe l'agent avec le dernier profil de l'iPhone et le réinstalle ; rend le profil utilisé."""
    profil = profil_de(await profils(udid), bundle)
    if not profil:
        raise ErreurSignature("aucun profil valide de l'agent sur l'iPhone : refais « Installer » dans Impactor")
    p12 = certificat(profil["equipe"]) or certificat()
    if not p12:
        raise ErreurSignature("le certificat n'est pas sur le PC : dans Impactor, Réglages › Exporter P12")
    ipa = ipa_agent()
    if not ipa:
        raise ErreurSignature("l'IPA de l'agent manque (outils/preparer_agent.py)")
    sortie = lieux.DONNEES / "agent-signe.ipa"
    await goios.exiger("sign", "app", f"--path={ipa}", f"--p12file={p12}", "--p12password=", f"--profile={profil['chemin']}",
                       f"--bundleid={bundle}", f"--output={sortie}", "--install", udid=udid, delai=600)
    log.info("agent re-signé et réinstallé (profil %s, expire le %s)", profil["uuid"], profil["expire"])
    return profil
