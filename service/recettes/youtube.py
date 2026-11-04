"""recettes/youtube.py : publier un Short depuis l'app YT Studio de l'iPhone.

Relevé le 25/10/2026 à 16 h sur l'iPhone <udid> (YT Studio en français, chaîne « un autre projet »), jusqu'au bouton de mise en
ligne sans le toucher :
- tableau de bord : le nom de la chaîne sous « channel_overview_item », le bouton « top_bar.create » (Créer) ;
- Créer ouvre directement le sélecteur de photos d'iOS (accès privé : il montre toute la pellicule), la plus récente en
  haut à gauche ; chaque case « PXGGridLayout-Info » dit « Vidéo, dix-huit secondes, 25 octobre, 15:37 » : on vérifie
  que c'est bien la vidéo que le service vient de ranger (du jour, rangée il y a moins de 30 min) ;
- « Ajouter des détails » : le titre (« metadata_editor.title », un TextView ; un Short n'a pas d'autre texte), la
  visibilité (« privacy_picker_v2 », Privée par défaut → « Publique » : on publie à l'heure du créneau, comme TikTok
  et Insta, sans passer par « Programmer »), l'audience (« audience_picker » → « mfk.2 » : Non, pas conçue pour les
  enfants), « Utilisation de l'IA » jamais touché, « mde.upload_button » (Mettre en ligne le
  Short) ; « mde.close » demande « Supprimer les modifications ? » (Supprimer : rien d'importé, rien de gardé).
Ce qui suit « Mettre en ligne » n'a pas encore été vu : la recette attend que l'éditeur se ferme puis que l'envoi se
termine (l'app reste au premier plan), et garde une capture à chaque étape pour recaler au premier vrai Short."""
import asyncio
import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from recettes.base import ErreurPublication

log = logging.getLogger("youtube")
BUNDLE = "com.google.ios.ytcreator"
PARIS = ZoneInfo("Europe/Paris")
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
FRAICHEUR_MIN = 30
TITRE = "id.elements.components.metadata_editor.title"
VISIBILITE = "id.elements.components.metadata_editor.privacy_picker_v2"
AUDIENCE = "id.elements.components.metadata_editor.audience_picker"
RETOUR = "id.elements.components.metadata_editor.app_bar.back_button"
PAS_ENFANTS = "id.elements.components.metadata_editor.audience_settings.mfk.2"


def titre_de(legende, secours=""):
    """Le titre du Short : la 1re ligne de la légende (hashtags compris, comme les Shorts déjà postés), 100 caractères."""
    return (next((x.strip() for x in (legende or "").splitlines() if x.strip()), "") or secours)[:100]


def moment_de(label, maintenant=None):
    """L'heure (Paris) d'une case du sélecteur (« Vidéo, dix-huit secondes, 25 octobre, 15:37 »), ou None. Sans année
    affichée : celle de maintenant (ou la précédente si la date tomberait dans le futur)."""
    m = re.search(r"(\d{1,2}) ([a-zéèûô]+)(?: (\d{4}))?, (\d{1,2}):(\d{2})", (label or "").lower())
    if not m or m.group(2) not in MOIS:
        return None
    maintenant = maintenant or dt.datetime.now(PARIS)
    annee = int(m.group(3) or maintenant.year)
    t = dt.datetime(annee, MOIS[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=PARIS)
    if not m.group(3) and t > maintenant + dt.timedelta(days=1):
        t = t.replace(year=annee - 1)
    return t


async def publier(r, compte, legende):
    await r.etape("Ouverture de YT Studio")
    await r.lancer_propre(BUNDLE)
    await r.alertes()
    await verifier_chaine(r, compte["identifiant"])

    await r.etape("Créer › sélecteur de photos")
    await r.toucher("top_bar.create", delai=15)
    await sans_brouillon(r)
    await choisir_video(r)

    await r.etape("Détails du Short : titre")
    titre = titre_de(legende, r.pub.get("titre") or "")
    await r.attendre(TITRE, delai=60)                  # la vidéo se prépare avant l'écran des détails
    await r.a.cliquer(await champ_titre(r))
    await asyncio.sleep(1)
    await r.taper(lambda: champ_titre(r), titre)
    await sortir_du_titre(r)

    await r.etape("Visibilité : Publique")
    await r.toucher(VISIBILITE, delai=8)
    ligne = await r.attendre("Publique, Tout le monde", contient=True, types=["Button"], delai=8)
    x = await r.a.rect(ligne)
    await r.a.toucher(x["x"] + 30, x["y"] + x["height"] / 2)   # le rond : un toucher au milieu de la ligne ne prend pas
    await asyncio.sleep(1.5)
    # vérifié ICI : de retour sur les détails, l'arbre de YT Studio garde « Visibilité, Privée » alors que l'écran dit
    # Publique (2e répétition, 25/10/2026 à 17 h 09) ; dans cet écran, le rond coché donne la valeur « 1 » à sa ligne
    if not await coche_sur(r, x):
        raise ErreurPublication("le rond « Publique » ne se coche pas (voir la capture)")
    await r.toucher(RETOUR, delai=8)
    await r.attendre(VISIBILITE, delai=8)

    await r.etape("Audience : pas conçue pour les enfants")
    await r.toucher(AUDIENCE, delai=8)
    await r.toucher(PAS_ENFANTS, delai=8)
    await asyncio.sleep(1)
    await r.toucher(RETOUR, delai=8)
    await r.attendre("mde.upload_button", delai=10)

    await r.etape("Prêt à mettre en ligne")
    if r.repetition:
        await r.toucher("mde.close", delai=5)
        await r.si_present("Supprimer", types=["Button"], delai=5)
        await r.etape("Répétition : fermé sans mettre en ligne et brouillon supprimé, rien n'est parti")
        return None

    await r.toucher("mde.upload_button", delai=5)
    await r.etape("Mettre en ligne le Short : envoi en cours (YT Studio doit rester à l'écran)")
    await attendre_envoi(r, titre)
    return None


async def sortir_du_titre(r):
    """Après le titre, les suggestions de hashtags couvrent l'écran (1re répétition, 25/10/2026 à 16 h 39 : « Visibilité »
    touché sans effet). Toucher la barre « Ajouter des détails » les ferme (vérifié à la main à 16 h 44) ; le clavier
    reste, mais la ligne Visibilité est dégagée au-dessus, et il se ferme en passant par l'écran de visibilité."""
    try:
        await r.a.fermer_clavier()
    except Exception:
        pass
    await r.si_present("id.ui.title.tab.button", delai=3)
    await asyncio.sleep(1.5)
    if not await r.trouver(VISIBILITE, delai=5):
        raise ErreurPublication("les suggestions de hashtags couvrent encore l'écran après le titre")


async def coche_sur(r, ligne, delai=6):
    """La ligne est cochée dans l'écran de visibilité : un de ses boutons a la VALEUR « 1 » (3e répétition, 25/10/2026 à
    19 h 04 : l'ancienne ligne cochée garde aussi un « 1 » périmé, mais à sa propre hauteur)."""
    fin = asyncio.get_event_loop().time() + delai
    while asyncio.get_event_loop().time() < fin:
        for eid in await r.a.chercher("predicate string", "type == 'XCUIElementTypeButton' AND value == '1'"):
            try:
                m = await r.a.rect(eid)
            except Exception:
                continue
            if abs(m["y"] - ligne["y"]) < 10:
                return True
        await asyncio.sleep(1)
    return False


async def sans_brouillon(r):
    """« Créer » rouvre le brouillon d'une publication coupée net au lieu du sélecteur (vu le 25/10/2026 à 16 h 40,
    après la répétition ratée) : il partirait avec l'ANCIENNE vidéo. On le ferme (« Supprimer les modifications ? » ›
    Supprimer) et on recommence Créer."""
    for _ in range(2):
        if not await r.trouver("mde.close", delai=4):
            return
        await r.etape("Un brouillon de YT Studio s'est rouvert : supprimé, on recommence")
        await r.toucher("mde.close", delai=5)
        await r.toucher("Supprimer", types=["Button"], delai=6)
        await asyncio.sleep(2)
        await r.toucher("top_bar.create", delai=15)
    if await r.trouver("mde.close", delai=4):
        raise ErreurPublication("YT Studio rouvre toujours un ancien brouillon après « Créer » : rien n'est choisi")


async def degagee(r, nom):
    """L'élément est à l'écran et rien ne le recouvre (l'agent le dit « hittable »)."""
    eid = await r.trouver(nom, delai=2)
    if not eid:
        return False
    try:
        return (await r.a.attribut(eid, "hittable")) in (True, "true", "1")
    except Exception:
        return False


async def verifier_chaine(r, identifiant):
    """La chaîne ouverte dans YT Studio est bien celle du compte (son nom contient l'identifiant) : jamais une autre."""
    await r.attendre("top_bar.create", delai=20)
    if not await r.trouver(identifiant, types=["StaticText"], contient=True, delai=5):
        raise ErreurPublication(f"YT Studio n'est pas sur la chaîne « {identifiant} » : rien n'est publié "
                                "(change de chaîne dans l'app, menu du compte en haut à droite)")
    await r.etape(f"Chaîne « {identifiant} » ouverte")


async def champ_titre(r):
    """Le TextView du titre : celui qui est dans le bloc « metadata_editor.title »."""
    bloc = await r.attendre(TITRE, delai=8)
    b = await r.a.rect(bloc)
    dedans = await r.elements("TextView", dans=lambda x: abs(x["y"] - b["y"]) < 40 and abs(x["x"] - b["x"]) < 40)
    if not dedans:
        raise ErreurPublication("champ du titre introuvable")
    return dedans[0][0]


async def choisir_video(r, maintenant=None):
    """La case en haut à gauche du sélecteur (la plus récente), si c'est une vidéo rangée il y a moins de 30 min."""
    fin = asyncio.get_event_loop().time() + 20
    cases = []
    while not cases and asyncio.get_event_loop().time() < fin:
        cases = await r.a.chercher("predicate string", "name == 'PXGGridLayout-Info'")
        if not cases:
            await asyncio.sleep(1)
    if not cases:
        raise ErreurPublication("le sélecteur de photos ne s'ouvre pas (ou ne montre rien) après « Créer »")
    places = []
    for eid in cases:
        x = await r.a.rect(eid)
        if x["width"] > 0 and x["height"] > 0:
            places.append((round(x["y"]), x["x"], eid, x))
    _, _, eid, rect = min(places, key=lambda p: (p[0], p[1]))
    label = (await r.a.attribut(eid, "label")) or ""
    quand = moment_de(label, maintenant)
    maintenant = maintenant or dt.datetime.now(PARIS)
    if not label.lower().startswith("vidéo") or quand is None or (maintenant - quand) > dt.timedelta(minutes=FRAICHEUR_MIN):
        raise ErreurPublication(f"la plus récente de la pellicule n'est pas la vidéo que le service vient de ranger ({label}) : "
                                "rien n'est choisi")
    await r.etape(f"Vidéo choisie : {label}")
    await r.a.toucher(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)
    await asyncio.sleep(3)


async def attendre_envoi(r, titre, delai=600):
    """Après « Mettre en ligne » : l'éditeur se ferme, puis on vérifie que le Short est bien sur la chaîne, dans l'onglet
    Contenus, sous son titre (1er vrai Short, 26/10/2026 à 17 h 40 : en ligne en quelques secondes, mais l'ancienne
    attente cherchait « % » à l'écran et tombait sur les barres de défilement et la batterie, d'où un faux échec)."""
    fin = asyncio.get_event_loop().time() + delai
    while await r.trouver("mde.upload_button", delai=1):
        if asyncio.get_event_loop().time() > fin:
            raise ErreurPublication("YT Studio reste sur l'écran des détails après « Mettre en ligne » (voir la capture)")
        await asyncio.sleep(3)
    await r.etape("Éditeur fermé : envoi en cours")
    await asyncio.sleep(20)                         # l'app reste au premier plan : un Short de 15 s part en quelques secondes
    debut = (titre or "")[:30].strip()
    while asyncio.get_event_loop().time() < fin:
        await r.si_present("id.ui.pivotbar.FEcontent_hub.button", delai=3)
        await asyncio.sleep(4)
        if debut and await r.trouver(debut, types=["Button"], contient=True, delai=3):
            await r.etape("Short en ligne : vu dans Contenus de YT Studio")
            return
        await r.a.glisser(195, 300, 195, 650, 0.4)   # tirer pour rafraîchir la liste
        await asyncio.sleep(20)
    raise ErreurPublication("le Short n'apparaît pas dans Contenus de YT Studio après 10 min (vérifie sur la chaîne avant de relancer)")
