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
autoriser » (c'est le Raccourci du service, sur le téléphone du service). Vu le 16/10/2026 sur l'iPhone 2 (iOS 26.7) :
« Autoriser « Auto importer » à produire 1 photo ? » arrive APRÈS que la vidéo est dans la pellicule, et reste
par-dessus Instagram et TikTok tant qu'on n'y répond pas (les 4 publications du jour ratées : « creation-reel »
introuvable, comptes « pas connectés », liste des comptes fermée) : elle est donc cherchée aussi une fois la vidéo
rangée."""
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


async def autoriser(tel, delai, accueil=False):
    """« Toujours autoriser » si Raccourcis le demande dans les `delai` secondes ; rend True s'il a été touché.
    `accueil` (la vidéo déjà rangée) : rien trouvé, on revient à l'écran d'accueil et on cherche encore (vu le 18/10/2026
    sur l'iPhone 2 : « … à partager 1 photo et 1 élément multimédia avec Photos ? » par-dessus Raccourcis n'est ni dans
    l'arbre ni une alerte ; par-dessus l'accueil, elle est dans l'arbre)."""
    fin = time.monotonic() + delai
    while True:
        try:
            for eid in await tel.agent.chercher("predicate string", AUTORISER):
                log.info("%s : Raccourcis demande une autorisation, « Toujours autoriser »", tel.nom)
                await tel.agent.cliquer(eid)
                await asyncio.sleep(1)
                return True
            texte = await tel.agent.alerte()     # hors de l'arbre de l'app au premier plan : l'alerte d'iOS
            if texte and RACCOURCI in texte:
                boutons = await tel.agent.boutons_alerte() or []
                choix = next((x for x in ("Toujours autoriser", "Always Allow") if x in boutons), None)
                if choix:
                    log.info("%s : « %s » → %s", tel.nom, texte.replace("\n", " ")[:100], choix)
                    await tel.agent.accepter_alerte(choix)
                    await asyncio.sleep(1)
                    return True
        except ErreurAgent as e:
            log.debug("autorisation de Raccourcis : %s", e)
        if accueil:
            accueil = False
            try:
                await tel.agent.accueil()
            except ErreurAgent as e:
                log.debug("retour à l'accueil : %s", e)
            continue
        if time.monotonic() >= fin:
            return False
        await asyncio.sleep(1)


async def importer(tel, fichier, nom, delai=150):
    """Range `fichier` (chemin sur le PC) dans Photos sous le nom `nom` (.mp4). Lève ErreurImport en clair."""
    if tel.apps and not any(a.get("CFBundleIdentifier") == VLC for a in tel.apps):
        raise ErreurImport("VLC n'est pas installé sur l'iPhone (App Store, gratuit) : le service y dépose les vidéos.")
    await goios.creer_dossier(tel.udid, VLC, DOSSIER)
    # la copie d'un essai raté (coupé avant d'être rangé) reste dans VLC ; réécrite, elle garde sa date de création, et
    # Photos date la vidéo de ce jour-là : Instagram la refuse, pas « du jour » (1208, déposée le 23/10, relancée le
    # 26/10/2026). On efface donc l'ancienne copie du service avant de déposer la nouvelle.
    if nom in (await goios.lister(tel.udid, VLC, DOSSIER) or []):
        await goios.supprimer(tel.udid, VLC, f"{DOSSIER}/{nom}")
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
            await autoriser(tel, 4, accueil=True)
            log.info("%s : %s rangée dans Photos", tel.nom, nom)
            return
        nouvelles = [n for n in set(await goios.lister(tel.udid, None, "/DCIM") or []) - avant
                     if n.upper().endswith((".MP4", ".MOV", ".M4V"))]
        if nouvelles:                                                 # une nouvelle vidéo dans la pellicule
            await autoriser(tel, 4, accueil=True)                                   # la demande d'iOS peut encore suivre (16/10/2026)
            await goios.supprimer(tel.udid, VLC, f"{DOSSIER}/{nom}")
            log.info("%s : %s rangée dans Photos (%s), copie de VLC effacée", tel.nom, nom, ", ".join(sorted(nouvelles)))
            return
        try:
            app = ((await tel.agent.app_active()) or {}).get("bundleId")
            if app == PHOTOS:                                        # x-success : rangée sans erreur
                await autoriser(tel, 4, accueil=True)
                await goios.supprimer(tel.udid, VLC, f"{DOSSIER}/{nom}")
                log.info("%s : %s rangée dans Photos (copie de VLC effacée)", tel.nom, nom)
                return
            await autoriser(tel, 0)                                  # première fois : les autorisations
        except ErreurAgent as e:
            log.debug("attente du Raccourci : %s", e)
    raise ErreurImport(f"le Raccourci « {RACCOURCI} » n'a pas rangé la vidéo en {delai} s. Vérifie qu'il existe sous ce nom "
                       "exact (2 actions : « Récupérer le fichier dans le dossier » VLC, chemin import/Entrée du raccourci, "
                       "puis « Enregistrer dans l'album photo »).")
