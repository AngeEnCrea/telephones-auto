"""photos.py : mettre une vidéo dans la pellicule de l'iPhone (TikTok, Instagram et YouTube ne prennent qu'elle).
Par le câble, sans réseau : go-ios dépose le fichier dans le dossier Documents de VLC (app gratuite dont le dossier
est ouvert à l'ordinateur), puis le Raccourci « Auto importer » le range dans Photos.

Le Raccourci, créé une fois à la main sur l'iPhone (iOS 26, deux actions) :
  1. Récupérer le fichier dans le dossier : Dossier « Sur mon iPhone › VLC », chemin « import/[Entrée du raccourci] » ;
  2. Enregistrer dans l'album photo (Récents).
La preuve que la vidéo est rangée : une nouvelle vidéo dans le dossier de la pellicule (/DCIM, lu par le câble).
Le service efface alors la copie déposée dans VLC. (Mesuré le 02/10/2026 : lancé par l'adresse x-callback, le Raccourci
finit « success: yes » mais n'ouvre pas l'app Photos demandée en x-success : ce n'est donc qu'une preuve de secours,
comme le fichier qui disparaît de VLC quand le Raccourci l'efface lui-même, avec une 3e action « Supprimer les
fichiers ».) Pièges vus ce jour-là : l'app Fichiers d'Apple doit être installée (sinon « Récupérer le fichier » plante),
et le chemin doit être « import/ » SUIVI de la variable « Entrée de raccourci » (sans elle, le Raccourci prend le
dossier et « Enregistrer dans l'album photo » échoue sur « Chargement du cadre interrompu »).

La première fois, Raccourcis demande d'autoriser l'accès au dossier de VLC et à Photos : le service touche « Toujours
autoriser » (c'est le Raccourci du service, sur le téléphone dédié)."""
import asyncio
import logging
import time
from urllib.parse import quote

import goios
from wda import ErreurAgent

log = logging.getLogger("photos")
VLC = "org.videolan.vlc-ios"
PHOTOS = "com.apple.mobileslideshow"
DOSSIER = "/Documents/import"
RACCOURCI = "Auto importer"
AUTORISER = 'type == "XCUIElementTypeButton" AND label IN {"Toujours autoriser", "Always Allow", "Autoriser", "Allow"}'


class ErreurImport(RuntimeError):
    pass


async def importer(tel, fichier, nom, delai=150):
    """Range `fichier` (chemin sur le PC) dans Photos sous le nom `nom` (.mp4). Lève ErreurImport en clair."""
    if tel.apps and not any(a.get("CFBundleIdentifier") == VLC for a in tel.apps):
        raise ErreurImport("VLC n'est pas installé sur l'iPhone (App Store, gratuit) : le service y dépose les vidéos.")
    await goios.creer_dossier(tel.udid, VLC, DOSSIER)
    await goios.pousser(tel.udid, VLC, fichier, f"{DOSSIER}/{nom}")
    noms = await goios.lister(tel.udid, VLC, DOSSIER)
    if noms is None or nom not in noms:
        raise ErreurImport("la vidéo n'est pas arrivée dans le dossier de VLC")
    avant = set(await goios.lister(tel.udid, None, "/DCIM") or [])
    await tel.agent.accueil()              # Photos ne doit pas déjà être au premier plan : c'est une preuve de secours
    url = (f"shortcuts://x-callback-url/run-shortcut?name={quote(RACCOURCI)}&input=text&text={quote(nom)}"
           f"&x-success={quote('photos-redirect://', safe='')}&x-error={quote('shortcuts://', safe='')}")
    await tel.agent.ouvrir_url(url)
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        await asyncio.sleep(2)
        noms = await goios.lister(tel.udid, VLC, DOSSIER)
        if noms is not None and nom not in noms:                    # le Raccourci a effacé lui-même
            log.info("%s : %s rangée dans Photos", tel.nom, nom)
            return
        nouvelles = [n for n in set(await goios.lister(tel.udid, None, "/DCIM") or []) - avant
                     if n.upper().endswith((".MP4", ".MOV", ".M4V"))]
        if nouvelles:                                                 # une nouvelle vidéo dans la pellicule
            await goios.supprimer(tel.udid, VLC, f"{DOSSIER}/{nom}")
            log.info("%s : %s rangée dans Photos (%s), copie de VLC effacée", tel.nom, nom, ", ".join(sorted(nouvelles)))
            return
        try:
            app = ((await tel.agent.app_active()) or {}).get("bundleId")
            if app == PHOTOS:                                        # x-success : rangée sans erreur
                await goios.supprimer(tel.udid, VLC, f"{DOSSIER}/{nom}")
                log.info("%s : %s rangée dans Photos (copie de VLC effacée)", tel.nom, nom)
                return
            for eid in await tel.agent.chercher("predicate string", AUTORISER):   # première fois : les autorisations
                log.info("%s : Raccourcis demande une autorisation, « Toujours autoriser »", tel.nom)
                await tel.agent.cliquer(eid)
                break
        except ErreurAgent as e:
            log.debug("attente du Raccourci : %s", e)
    raise ErreurImport(f"le Raccourci « {RACCOURCI} » n'a pas rangé la vidéo en {delai} s. Vérifie qu'il existe sous ce nom "
                       "exact (2 actions : « Récupérer le fichier dans le dossier » VLC, chemin import/Entrée du raccourci, "
                       "puis « Enregistrer dans l'album photo »).")
