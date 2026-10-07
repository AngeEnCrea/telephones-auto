"""goios.py : tout ce qui parle à l'iPhone par le câble, avec go-ios (réglage « ios »), sauf l'écran
et les gestes, qui passent par WebDriverAgent (wda.py). go-ios rend son résultat en JSON sur la sortie standard, et
ses messages, JSON aussi (une ligne par message : level, msg, err…), sur la sortie d'erreur."""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys

import lieux

log = logging.getLogger("go-ios")
SANS_FENETRE = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW : aucune console qui s'ouvre


class ErreurIos(RuntimeError):
    """Une commande go-ios a échoué ; `messages` garde ce qu'elle a dit, pour en traduire la cause à l'utilisateur."""

    def __init__(self, args, code, messages):
        self.code = code
        self.messages = messages
        super().__init__(f"ios {' '.join(args)} : {resume(messages) or f'code {code}'}")

    def contient(self, *mots):
        return contient(self.messages, *mots)


def messages(texte):
    out = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            m = json.loads(ligne)
            out.append(m if isinstance(m, dict) else {"msg": ligne})
        except ValueError:
            out.append({"msg": ligne})
    return out


def contient(msgs, *mots):
    texte = json.dumps(msgs, ensure_ascii=False).lower()
    return any(m.lower() in texte for m in mots)


def resume(msgs):
    """La dernière erreur dite par go-ios, en une ligne (msg : err)."""
    for m in reversed(msgs):
        if str(m.get("level", "")).upper() in ("ERROR", "FATAL") or m.get("err") or m.get("error"):
            return " : ".join(str(x) for x in (m.get("msg"), m.get("err") or m.get("error")) if x)
    return str(msgs[-1].get("msg", "")) if msgs else ""


def dernier_json(texte):
    for ligne in reversed(texte.strip().splitlines()):
        try:
            return json.loads(ligne)
        except ValueError:
            continue
    return None


async def ios(*args, udid=None, delai=60, entree=None):
    """Lance `ios <args> [--udid=…]` ; rend (code, stdout, messages). Ne lève que si le délai est dépassé."""
    cmd = [lieux.IOS, *args] + ([f"--udid={udid}"] if udid else [])
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=subprocess.PIPE if entree is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SANS_FENETRE)
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(entree.encode("utf-8") if entree is not None else None), delai)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ErreurIos(args, None, [{"level": "ERROR", "msg": f"pas de réponse en {delai} s"}])
    return proc.returncode, out.decode("utf-8", "replace"), messages(err.decode("utf-8", "replace"))


async def exiger(*args, udid=None, delai=60, entree=None):
    code, out, msgs = await ios(*args, udid=udid, delai=delai, entree=entree)
    if code != 0:
        raise ErreurIos(args, code, msgs)
    return out, msgs


# ── Ce que le pilote Apple voit ─────────────────────────────────────────────────────────────────────
async def udids():
    """Les iPhone branchés (appairés ou non). Lève si le pilote Apple ne répond pas."""
    out, _ = await exiger("list", delai=20)
    return list((dernier_json(out) or {}).get("deviceList") or [])


async def infos(udid):
    """Les valeurs de lockdown (DeviceName, ProductType, ProductVersion…). Lève si l'ordinateur n'est pas approuvé."""
    out, _ = await exiger("info", udid=udid, delai=30)
    d = dernier_json(out)
    return d if isinstance(d, dict) else {}


async def appairer(udid):
    """Demande l'appairage : l'iPhone affiche « Faire confiance à cet ordinateur ? »."""
    return await ios("pair", udid=udid, delai=60)


async def mode_developpeur(udid):
    code, out, _ = await ios("devmode", "get", udid=udid, delai=30)
    d = dernier_json(out) if code == 0 else None
    return bool(d.get("DeveloperModeEnabled")) if isinstance(d, dict) else None


async def reveler_mode_developpeur(udid):
    """Fait apparaître l'interrupteur Mode développeur dans les Réglages de l'iPhone."""
    await ios("devmode", "reveal", udid=udid, delai=30)


async def image_montee(udid):
    _, msgs = await exiger("image", "list", udid=udid, delai=40)
    return any(m.get("msg") == "image signature" for m in msgs)


async def monter_image(udid):
    """Télécharge (la première fois) et monte l'image développeur. `ios image auto` rend 0 même quand le
    téléchargement échoue : seul le message « success mounting image » fait foi.

    Sur Windows, la première signature d'Apple échoue : go-ios la demande en HTTPS à gs.apple.com, dont le
    certificat descend de la racine privée d'Apple (« Apple Root CA »), inconnue de Windows (mesuré le 01/10/2026,
    « x509: certificate signed by unknown authority »). pymobiledevice3 fait la même demande en HTTP, comme les outils
    d'Apple eux-mêmes (le ticket rendu est signé par Apple et vérifié par l'iPhone) : il prend le relais, avec l'image
    que go-ios vient de télécharger. Les fois suivantes, go-ios réutilise le ticket gardé par l'iPhone."""
    lieux.DDI.mkdir(parents=True, exist_ok=True)
    code, _, msgs = await ios("image", "auto", f"--basedir={lieux.DDI}", udid=udid, delai=900)
    if any(m.get("msg") == "success mounting image" for m in msgs):
        return
    erreur = ErreurIos(("image", "auto"), code, msgs)
    if lieux.PMD3 and erreur.contient("failed to get signature from Apple"):
        log.info("signature d'Apple refusée à go-ios (%s) : pymobiledevice3 prend le relais", resume(msgs))
        return await monter_image_pymobiledevice3(udid)
    raise erreur


def image_telechargee():
    """(image, trustcache, BuildManifest) de l'image personnalisée la plus récente téléchargée par go-ios."""
    for restore in sorted(lieux.DDI.glob("ddi-*/Restore"), key=lambda p: p.stat().st_mtime, reverse=True):
        manifeste = restore / "BuildManifest.plist"
        for dmg in restore.glob("*.dmg"):
            tc = restore / "Firmware" / (dmg.name + ".trustcache")
            if manifeste.exists() and tc.exists():
                return dmg, tc, manifeste
    return None


async def pymobiledevice3(*args, delai=300):
    """Lance pymobiledevice3 (sortie et erreurs mêlées, sans couleurs) ; rend (code, texte)."""
    proc = await asyncio.create_subprocess_exec(
        lieux.PMD3, *args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=SANS_FENETRE, env={**os.environ, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), delai)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ErreurIos(("pymobiledevice3",) + args[:2], None, [{"level": "ERROR", "msg": f"pas de réponse en {delai} s"}])
    texte = out.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise ErreurIos(("pymobiledevice3",) + args[:2], proc.returncode,
                        [{"level": "ERROR", "msg": ligne} for ligne in texte.strip().splitlines()[-3:]])
    return proc.returncode, texte


async def monter_image_pymobiledevice3(udid):
    fichiers = image_telechargee()
    if not fichiers:
        raise ErreurIos(("pymobiledevice3",), None, [{"level": "ERROR", "msg": "aucune image personnalisée téléchargée"}])
    try:
        _, texte = await pymobiledevice3("mounter", "mount-personalized", "--udid", udid, *map(str, fichiers))
    except ErreurIos as e:
        if e.contient("already mounted"):
            return
        raise
    if "mounted successfully" in texte or "already mounted" in texte:
        log.info("image développeur montée par pymobiledevice3 (%s)", fichiers[0].parent.parent.name)
        return
    raise ErreurIos(("pymobiledevice3", "mounter", "mount-personalized"), 0,
                    [{"level": "ERROR", "msg": ligne} for ligne in texte.strip().splitlines()[-3:]])


async def tunnels():
    """Les tunnels iOS 17+ ouverts par l'agent de go-ios ([] s'il ne tourne pas)."""
    code, out, _ = await ios("tunnel", "ls", delai=15)
    d = dernier_json(out) if code == 0 else None
    return d if isinstance(d, list) else []


async def apps(udid):
    """Les apps installées par l'utilisateur (dictionnaires d'Info.plist : CFBundleIdentifier, CFBundleName…)."""
    out, _ = await exiger("apps", udid=udid, delai=90)
    d = dernier_json(out)
    return d if isinstance(d, list) else []


# ── Fichiers d'une app (le dossier Documents de VLC, où le service dépose les vidéos) ──────────────────────
async def pousser(udid, app, source, destination):
    await exiger("fsync", f"--app={app}", "push", f"--srcPath={source}", f"--dstPath={destination}",
                 udid=udid, delai=900)


async def lister(udid, app, chemin):
    """Les noms des fichiers (pas des dossiers) sous `chemin`, sous-dossiers compris ; None si le dossier n'existe
    pas. `app` None : le dossier Media de l'iPhone (la pellicule est dans /DCIM)."""
    code, out, _ = await ios("fsync", *([f"--app={app}"] if app else []), "tree", f"--path={chemin}", udid=udid, delai=60)
    if code != 0:
        return None
    noms = []
    for ligne in out.splitlines():
        nom = re.sub(r"^[|\s]*-", "", ligne.rstrip())
        if nom and not nom.endswith("/"):
            noms.append(nom)
    return noms


async def creer_dossier(udid, app, chemin):
    await ios("fsync", f"--app={app}", "mkdir", f"--path={chemin}", udid=udid, delai=60)   # déjà là : sans effet


async def supprimer(udid, app, chemin):
    await ios("fsync", f"--app={app}", "rm", f"--path={chemin}", udid=udid, delai=60)


# ── Presse-papiers (iOS 17+, par le tunnel) : les légendes avec émojis passent par là, pas par le clavier ─────
async def presse_papiers_ecrire(udid, texte):
    await exiger("pasteboard", "set", udid=udid, delai=30, entree=texte)


async def presse_papiers_lire(udid):
    out, _ = await exiger("pasteboard", "get", udid=udid, delai=30)
    return out.rstrip("\r\n")


async def capture(udid, sortie):
    """Capture d'écran sans l'agent (plus lente) : sert quand WebDriverAgent ne tourne pas."""
    await exiger("screenshot", f"--output={sortie}", udid=udid, delai=60)
