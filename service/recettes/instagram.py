"""recettes/instagram.py : publier un reel sur Instagram depuis l'iPhone.

Calé le 04/10/2026 sur le vrai iPhone (Instagram en français, iOS 26.5), en répétition jusqu'à l'écran final, puis à la
1re vraie publication (fenêtre « À propos de Reels »). Le téléphone reste sur Instagram jusqu'à la fin de l'envoi
(Instagram n'envoie qu'au premier plan, vu le 05/10/2026), puis passe à la suite ; le lien est retrouvé à part (liens.py). On s'y repère par les identifiants d'accessibilité d'Instagram (name :
« profile-tab », « creation-reel »…), qui ne dépendent pas de la langue, plutôt que par les libellés. Ce qui suit le
dernier bouton a été vu le 04/10/2026 (reel en ligne sur @mapage.reels).

Choix de l'utilisateur (04/10/2026) : le partage sur Facebook que le compte a déjà réglé (« Partager aussi sur… ») reste tel
quel ; la recette n'y touche pas. Sauf pour un projet réglé « facebook_instagram:<projet> » :
elle le coche (options_ecran_final), comme le reel d'essai demandé publication par publication."""
import asyncio
import datetime as dt
import json
import logging
import os
import random
import re
import time
from zoneinfo import ZoneInfo

from recettes.base import ErreurPublication, q
from wda import ErreurAgent

log = logging.getLogger("instagram")
BUNDLE = "com.burbn.instagram"
# Niveaux de l'arbre lus pour chercher un bouton (voir wda.PROFONDEUR), mesurés le 04/10/2026 : le fil, à l'ouverture,
# sur 15 (la barre d'onglets est au niveau 9) ; le profil, la création, l'écran final et un reel ouvert se lisent sur
# 30 niveaux en moins de 2 s.
PROFONDEUR = 15
PROFONDEUR_PROFIL = 30
INTRUS = ("Pas maintenant", "Plus tard", "Ignorer", "Not now", "Skip")
# Les écrans de Meta qu'Instagram met par-dessus tout au lancement (vus le 21/10/2026 sur l'iPhone 1 : 17 reels ratés les
# 20 et 21/10 en « user-switch-title-button », 10 sur 13 le 21, l'onglet Profil touché à travers eux) : la demande de
# consentement « Autorisez ou non le traitement de vos données à des fins publicitaires » (un seul bouton, « Démarrer »)
# et la feuille « Votre Compte Meta est disponible » (son bouton « Examiner le compte » couvre la barre d'onglets). Ce sont
# des choix sur les comptes de l'utilisateur : le logiciel n'y touche JAMAIS. Ils ne reviennent pas à chaque lancement (un reel est
# parti 5 min après un échec) : Instagram est fermé puis rouvert, de plus en plus tard ; s'ils restent, l'échec dit à l'utilisateur
# quoi faire. (titre, textes qui le trahissent, bouton qui le confirme) ; « Démarrer » est au niveau 8 de l'arbre, le
# titre au 12 ; « Examiner le compte » trahit la feuille au cas où son titre serait plus profond que la lecture du fil
ECRANS_META = (("Autorisez ou non le traitement de vos données à des fins publicitaires", ("fins publicitaires",),
                ("Démarrer", "Get started", "Get Started")),
               ("Votre Compte Meta est disponible", ("Votre Compte Meta est disponible", "Examiner le compte"), None))
ATTENTES_META = tuple(int(x) for x in (os.environ.get("TELEPHONES_ATTENTES_META") or "30,90,180").split(","))
# « Nettoyage du compte » (vue le 24/10/2026 sur l'iPhone 1, compte @mapage.fun ; plus AUCUN reel ne partait de ce
# téléphone depuis le 22/10 au soir, ~40 échecs en « profile-tab ») : Instagram croit que quelqu'un d'autre s'est servi du
# compte et propose de supprimer ce qui a été publié depuis (« Tout supprimer », « Choisir le contenu à supprimer »). La
# page couvre toute l'app, sans retour, à chaque lancement. Le logiciel n'y touche JAMAIS (ce serait effacer des reels) :
# échec immédiat, qui dit à l'utilisateur quoi faire. (textes qui la trahissent, bouton qui la confirme)
NETTOYAGE = (("Nettoyage du compte", "activité récente"), ("Tout supprimer",))
MOIS = {"JANVIER": 1, "FEVRIER": 2, "FÉVRIER": 2, "MARS": 3, "AVRIL": 4, "MAI": 5, "JUIN": 6, "JUILLET": 7, "AOUT": 8,
        "AOÛT": 8, "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DECEMBRE": 12, "DÉCEMBRE": 12}


async def publier(r, compte, legende):
    await r.etape("Ouverture d'Instagram")
    await r.a.profondeur(PROFONDEUR)
    await r.lancer_propre(BUNDLE)
    await r.alertes()
    await fermer_intrus(r)
    await choisir_compte(r, compte["identifiant"])

    await r.etape("Création : + › Reel")
    await r.toucher("profile-add-button", delai=10)
    await r.toucher("creation-reel", delai=8)
    await r.alertes()
    await choisir_video(r)

    await r.etape("Éditeur d'Instagram : suivant, sans rien toucher")
    await passer_editeur(r)
    # le 1er reel d'un compte public (vu le 18/10/2026 sur @mapage.niche et @mapage.autre) : le volet « D'autres
    # personnes peuvent désormais télécharger et partager vos reels » couvre la légende ; « Continuer » garde le réglage
    # d'Instagram (les pages sont publiques, c'est voulu), « Gérer les paramètres » n'est jamais touché
    if await r.trouver("télécharger et partager vos reels", contient=True, delai=2):
        await r.toucher("Continuer", "Continue", types=["Button"], delai=5)
        await r.etape("Volet « D'autres personnes peuvent télécharger vos reels » : Continuer")

    if legende:
        await r.etape("Légende")
        await ecrire_legende(r, legende)
    await options_ecran_final(r, compte)
    await r.etape("Prêt à publier")
    if r.repetition:
        await abandonner(r)
        return None

    await r.toucher("share-sheet-share-button", delai=8)
    await partager(r)
    await r.etape("Partagée : envoi en cours (Instagram doit rester à l'écran)")
    await attendre_envoi(r)
    await r.etape("Envoi fini : le téléphone passe à la suite (lien cherché à part)")
    return None


# ── les choix de l'écran final  ──────────
# Relevés ce jour-là sur @autrepage, sous la légende : « Ajouter une mention IA » (made-with-ai-switch, pas touché),
# « Audience », « Essai » (trial-switch : « votre reel sera d'abord montré uniquement aux non-followers »), puis la ligne
# « Partager aussi sur…, Désactivé » qui ouvre un écran avec l'interrupteur Facebook (share-service-cell-switch). Sans
# Page Facebook reliée au compte, cet interrupteur ouvre un assistant « Étape 1 sur 3 » (relier une Page) : on l'annule,
# la vidéo part sans Facebook et l'étape le dit. Les boutons du bas (Enregistrer le brouillon / Partager, y ≥ 753)
# recouvrent la liste : un interrupteur n'est touché qu'une fois remonté au-dessus.
HAUT_BOUTONS = 740


async def amener(r, *textes, contient=False):
    """Fait défiler l'écran final jusqu'à ce que l'élément soit entre la barre du haut et les boutons du bas."""
    for _ in range(5):
        eid = await r.trouver(*textes, contient=contient, delai=1.5)
        if eid:
            x = await r.a.rect(eid)
            if x["y"] > 100 and x["y"] + x["height"] < HAUT_BOUTONS:
                return eid
        await r.a.glisser(195, 690, 195, 330, 0.4)
        await asyncio.sleep(1.2)
    return None


async def ligne_cochee(r, libelle):
    """La ligne de l'interrupteur dit « Coché, <libellé>… » : c'est elle qui fait foi. Le petit interrupteur à l'intérieur
    (« trial-switch ») garde la valeur 0 même coché (1er vrai reel d'essai, 26/10/2026 à 20 h 02 : « Essai » activé à
    l'écran, la recette l'a cru décoché et s'est arrêtée)."""
    for eid in await r.a.chercher("predicate string", f"type == 'XCUIElementTypeSwitch' AND label CONTAINS {q(libelle)}"):
        try:
            lab = (await r.a.attribut(eid, "label")) or ""
        except ErreurAgent:
            continue
        if lab.startswith("Coché") or lab.startswith("Checked"):
            return True
    return False


async def cocher(r, eid, quoi, libelle=None):
    """Met un interrupteur sur « coché » (rien s'il l'est déjà) ; rend True s'il est coché. `libelle` : le texte de sa
    ligne, lu en priorité (voir ligne_cochee)."""
    if (libelle and await ligne_cochee(r, libelle)) or str(await r.a.attribut(eid, "value")) == "1":
        return True
    await r.a.cliquer(eid)
    await asyncio.sleep(1.5)
    try:
        return (libelle and await ligne_cochee(r, libelle)) or str(await r.a.attribut(eid, "value")) == "1"
    except ErreurAgent:
        return False


async def options_ecran_final(r, compte):
    try:
        options = json.loads(r.pub.get("options") or "{}")
    except (ValueError, TypeError):
        options = {}
    facebook = r.stock.reglage(f"facebook_instagram:{compte.get('projet') or ''}", "0") == "1"
    if facebook:
        await partager_sur_facebook(r)
    if options.get("essai"):
        eid = await amener(r, "trial-switch")
        if not eid:
            raise ErreurPublication("reel d'essai demandé, mais l'interrupteur « Essai » n'est pas sur l'écran final")
        if not await cocher(r, eid, "essai", libelle="Essai"):
            raise ErreurPublication("reel d'essai demandé, mais l'interrupteur « Essai » ne se coche pas (voir la capture)")
        await r.etape("Reel d'essai coché (d'abord montré aux non-followers)")


async def partager_sur_facebook(r):
    ligne = await amener(r, "Partager aussi sur", contient=True)
    if not ligne:
        await r.etape("⚠️ Pas de ligne « Partager aussi sur… » sur l'écran final : publié sans Facebook")
        return
    if "facebook" in ((await r.a.attribut(ligne, "label")) or "").lower():
        await r.etape("Partage sur Facebook déjà coché")
        return
    await r.a.cliquer(ligne)
    eid = await r.attendre("share-service-cell-switch", delai=8)
    if str(await r.a.attribut(eid, "value")) != "1":
        await r.a.cliquer(eid)
        await asyncio.sleep(3)
        if await r.trouver("Étape 1 sur 3", contient=True, delai=2) or await r.trouver("cancel-button", delai=1):
            await r.toucher("cancel-button", delai=5)
            await r.toucher("BackButton", delai=5)
            await r.attendre("share-sheet-share-button", delai=10)
            await r.etape("⚠️ Facebook : aucune Page Facebook reliée à ce compte Instagram (Instagram ouvre « relier une "
                          "Page ») : publié sans Facebook. À relier une fois dans Instagram")
            return
    ok = str(await r.a.attribut(await r.attendre("share-service-cell-switch", delai=5), "value")) == "1"
    await r.toucher("BackButton", delai=5)
    await r.attendre("share-sheet-share-button", delai=10)
    if not ok:
        raise ErreurPublication("le partage sur Facebook ne se coche pas (voir la capture)")
    await r.etape("Partage sur Facebook coché")


async def partager(r):
    """Après le dernier bouton de l'écran final (« Suivant »), Instagram peut montrer la fenêtre « À propos de
    Reels » (vue le 04/10/2026 à la 1re vraie publication de @mapage.reels : « Votre reel sera partagé
    publiquement… », boutons Partager / Annuler) : on touche « Partager ». L'écran final reste dans l'arbre sous
    cette fenêtre : la preuve du départ est sa disparition (« sundial-share-sheet-view-controller »)."""
    fin = time.monotonic() + 25
    while time.monotonic() < fin:
        await asyncio.sleep(2)
        if not await r.trouver("sundial-share-sheet-view-controller", delai=1):
            return
        bouton = await r.premier_touchable("type == 'XCUIElementTypeButton' AND label IN {'Partager', 'Share'}")
        if bouton:
            await r.etape("Fenêtre « À propos de Reels » : Partager")
            try:
                await r.a.cliquer(bouton)
            except ErreurAgent as e:
                # la fenêtre se fermait déjà : le reel part (publication 91 du 10/10/2026, notée ratée alors qu'elle
                # était en ligne) ; on regarde de nouveau si l'écran final est parti
                if "stale element" not in str(e):
                    raise
    raise ErreurPublication("toujours sur l'écran final 25 s après le dernier bouton : un écran inattendu (voir la "
                            "capture) ; vérifie sur le compte avant de relancer")


async def attendre_envoi(r, delai=600):
    """Instagram n'envoie la vidéo que s'il reste au premier plan : vu le 05/10/2026 à 17 h 57, le téléphone passé à
    TikTok juste après « Partager », le bandeau « Ne fermez pas Instagram pour finir de publier • 26.5% » est resté figé,
    puis « Une erreur s'est produite, veuillez réessayer plus tard » : rien n'était en ligne. On reste donc sur
    Instagram tant que ce bandeau est là ; un envoi en erreur est relancé par sa flèche ↻ (deux fois au plus : c'est le
    même envoi, jamais une seconde publication)."""
    await r.a.profondeur(PROFONDEUR_PROFIL)       # le bandeau est au niveau ~20 du fil (mesuré : 0,5 s sur 30 niveaux)
    erreurs = lambda: r.a.chercher("predicate string", "label BEGINSWITH 'Une erreur s' OR label BEGINSWITH 'Something went wrong'")  # noqa: E731
    await asyncio.sleep(2)
    anciennes = len(await erreurs())   # un vieil envoi raté resté affiché : sa flèche ↻ relancerait CET envoi-là, pas le nôtre
    debut, vu, relances = time.monotonic(), False, 0
    while time.monotonic() - debut < delai:
        await asyncio.sleep(3)
        if await r.trouver("Ne fermez pas", "Don’t close", "Don't close", "Publication en cours", delai=1, contient=True):
            vu = True
            continue
        if len(await erreurs()) > anciennes:
            if anciennes:
                raise ErreurPublication("l'envoi Instagram est tombé en erreur, à côté d'un ancien envoi raté resté affiché : "
                                        "rien n'est relancé (vérifie sur le compte, supprime l'ancien envoi raté)")
            if relances >= 2:
                raise ErreurPublication("Instagram n'arrive pas à envoyer la vidéo (« Une erreur s'est produite », 3 essais) : "
                                        "rien n'est en ligne ; reprogramme-la plus tard")
            relances += 1
            await r.etape(f"Envoi Instagram en erreur : on le relance (↻, essai {relances + 1})")
            await r.toucher("ig icon arrow cw outline 16", delai=4)
            continue
        if vu or time.monotonic() - debut > 15:   # bandeau parti (envoi fini), ou jamais vu : envoi éclair
            return
    raise ErreurPublication(f"l'envoi Instagram n'est pas fini après {delai // 60} min (bandeau toujours là) : vérifie sur le compte")


async def fermer_intrus(r):
    for _ in range(3):
        if not await r.si_present(*INTRUS, delai=1.5):
            break
    await fermer_panneau(r)


async def fermer_panneau(r):
    """Les panneaux qu'Instagram glisse par-dessus (vu le 05/10/2026 à 12 h 05, après « Suivant » dans l'éditeur :
    « Enrichissez vos vidéos avec Edits », sa pub pour l'app Edits, boutons « Obtenir » / « Télécharger sur l'App
    Store » — JAMAIS touchés) : on les ferme par leur poignée « Fermer ». Pas « À propos de Reels » (son « Partager »
    fait partir la vidéo : partager() s'en charge). Rend True si un panneau a été fermé."""
    if not await r.trouver("ig-partial-modal-sheet-view-controller-content", delai=1):
        return False
    if await r.a.chercher("predicate string", "type == 'XCUIElementTypeButton' AND label IN {'Partager', 'Share'}"):
        return False
    poignee = await r.premier_touchable("type == 'XCUIElementTypeButton' AND label IN {'Fermer', 'Close'}")
    if poignee:
        await r.a.cliquer(poignee)
    else:
        largeur, _ = r.t.taille or (390, 844)
        await r.a.toucher(largeur / 2, 150)                   # au-dessus du panneau : il se ferme
    await asyncio.sleep(1.5)
    await r.etape("Panneau d'Instagram fermé (publicité, sans rien installer)")
    return True


async def passer_editeur(r):
    """« Suivant » dans l'éditeur, jusqu'à l'écran final ; un panneau glissé par-dessus est fermé, puis on retouche."""
    for _ in range(3):
        await fermer_panneau(r)
        await r.toucher("sundial-right-chevron-suivant-button", delai=20)
        if await r.trouver("share-sheet-share-button", delai=15):
            return
    raise ErreurPublication("l'écran final d'Instagram ne vient pas après « Suivant » (voir la capture)")


async def ecran_meta(r):
    """Le titre de l'écran de Meta par-dessus Instagram (voir ECRANS_META), ou None."""
    for titre, textes, boutons in ECRANS_META:
        if await r.trouver(*textes, contient=True, delai=0.5) and (not boutons or await r.trouver(*boutons, types=["Button"], delai=0.5)):
            return titre
    return None


async def sans_ecran_meta(r):
    """Ferme et rouvre Instagram tant qu'un écran de Meta le couvre (3 fois au plus, de plus en plus tard), sans jamais
    y toucher ; rend quand il n'y en a plus, sinon échec clair pour l'utilisateur."""
    for attente in ATTENTES_META:
        texte = await ecran_meta(r)
        if not texte:
            return
        await r.etape(f"Écran de Meta par-dessus Instagram (« {texte} ») : on n'y touche pas, Instagram rouvert dans {attente} s")
        try:
            await r.a.fermer(BUNDLE)
        except ErreurAgent:
            pass
        await asyncio.sleep(attente)
        await r.a.profondeur(PROFONDEUR)
        await r.lancer_propre(BUNDLE)
        await r.alertes(tout_refuser=True)      # le robot d'une publication n'a pas alertes_refusees()
        await fermer_intrus(r)
    texte = await ecran_meta(r)
    if texte:
        raise ErreurPublication(f"Instagram montre encore l'écran de Meta « {texte} » après {len(ATTENTES_META)} réouvertures : "
                                "le logiciel n'y touche jamais (choix sur le compte). Ouvre Instagram sur ce téléphone, "
                                "et fais ce choix ou ferme cet écran une fois, à la main")


async def sans_nettoyage(r):
    """Échec clair si Instagram est bloqué sur « Nettoyage du compte » (voir NETTOYAGE) ; rien n'y est touché."""
    textes, boutons = NETTOYAGE
    if await r.trouver(*textes, contient=True, delai=0.5) and await r.trouver(*boutons, types=["Button"], delai=0.5):
        raise ErreurPublication("Instagram est bloqué sur « Nettoyage du compte » (il croit que quelqu'un d'autre s'est servi "
                                "du compte ouvert dans l'app et propose de supprimer ce qui a été publié depuis) : le logiciel "
                                "n'y touche jamais. Ouvre Instagram sur ce téléphone et sors de cette page SANS RIEN "
                                "SUPPRIMER (jamais « Tout supprimer »), puis vérifie la sécurité du compte")


async def aller_au_profil(r):
    await r.a.profondeur(PROFONDEUR)            # on peut être sur le fil (vidéos) : lecture courte d'abord
    await sans_nettoyage(r)
    await sans_ecran_meta(r)                    # sinon l'onglet Profil est touché à travers l'écran de Meta
    await r.toucher("profile-tab", delai=10)
    await r.a.profondeur(PROFONDEUR_PROFIL)
    await asyncio.sleep(1.5)


async def compte_actif(r):
    """Le nom du compte affiché en haut du profil (« mapage.reels »), lu sur le bouton qui ouvre la liste. Un écran
    de Meta arrivé juste après l'ouverture a pu couvrir le profil : Instagram est rouvert, puis on y retourne."""
    eid = await r.trouver("user-switch-title-button", delai=10)
    if not eid:
        await sans_nettoyage(r)
    if not eid and await ecran_meta(r):
        await sans_ecran_meta(r)
        await aller_au_profil(r)
        eid = await r.trouver("user-switch-title-button", delai=10)
    if not eid:
        eid = await r.attendre("user-switch-title-button", delai=1)
    return ((await r.a.attribut(eid, "label")) or "").strip(), eid


async def choisir_compte(r, identifiant):
    """La liste des comptes (le nom en haut du profil) est lisible, chaque ligne étiquetée « Profil INSTAGRAM, <nom>,
    … ». Toujours le nom EXACT (un des morceaux entre virgules) : mapage est contenu dans mapage2.0.
    « Ajouter un compte Instagram » n'est jamais touché."""
    await r.etape(f"Compte @{identifiant}")
    await aller_au_profil(r)
    actif, titre = await compte_actif(r)
    if actif == identifiant:
        return
    await r.a.cliquer(titre)
    await asyncio.sleep(1.5)
    ligne = None
    for eid in await r.a.chercher("predicate string",
                                  f"type == 'XCUIElementTypeButton' AND label CONTAINS {q(', ' + identifiant)}"):
        morceaux = [m.strip() for m in ((await r.a.attribut(eid, "label")) or "").split(",")[1:]]
        if identifiant in morceaux:
            ligne = eid
            break
    if not ligne:
        raise ErreurPublication(f"@{identifiant} n'est pas parmi les comptes connectés à Instagram sur ce téléphone "
                                f"(compte actif : @{actif}) : connecte-le une fois à la main (Profil › nom du compte "
                                "› Ajouter un compte Instagram)")
    await r.a.cliquer(ligne)
    await asyncio.sleep(4)
    await fermer_intrus(r)
    actif, _ = await compte_actif(r)
    if actif != identifiant:
        raise ErreurPublication(f"le changement de compte vers @{identifiant} n'a pas pris (compte actif : @{actif})")
    await r.etape(f"Compte actif : @{identifiant}")


async def lister_comptes(r):
    """Les comptes connectés à Instagram sur ce téléphone (bouton « Rafraîchir » du warm-up, 13/10/2026) : le nom en haut
    du profil ouvre la liste, chaque ligne étiquetée « Profil INSTAGRAM, <nom>, … » ; rien n'est touché dans la liste
    (« Ajouter un compte Instagram » encore moins). Rend les noms."""
    await r.etape("Ouverture d'Instagram")
    await r.a.profondeur(PROFONDEUR)
    await r.lancer_propre(BUNDLE)
    await r.alertes()
    await fermer_intrus(r)
    await aller_au_profil(r)
    actif, titre = await compte_actif(r)
    noms = [actif] if actif else []
    await r.a.cliquer(titre)
    await asyncio.sleep(1.5)
    for eid in await r.a.chercher("predicate string", "type == 'XCUIElementTypeButton' AND label CONTAINS[c] 'INSTAGRAM,'"):
        morceaux = [m.strip() for m in ((await r.a.attribut(eid, "label")) or "").split(",")]
        nom = morceaux[1] if len(morceaux) > 1 else ""
        if re.fullmatch(r"[A-Za-z0-9._]{1,30}", nom) and nom not in noms:
            noms.append(nom)
    await r.etape(f"{len(noms)} compte(s) dans la liste d'Instagram : {', '.join(noms)}")
    await r.a.toucher((r.t.taille or (390, 844))[0] / 2, 120)      # au-dessus du panneau : il se ferme
    return [x.lower() for x in noms]


def date_de(label):
    """La date d'une vignette de la galerie (« …, DIMANCHE, OCTOBRE 4, 2026 »), ou None."""
    m = re.search(r"([A-ZÀ-Ü]+) (\d{1,2}), (\d{4})", label or "") or re.search(r"(\d{1,2}) ([A-ZÀ-Ü]+) (\d{4})", label or "")
    if not m:
        return None
    a, b, annee = m.groups()
    mois, jour = (a, b) if a.isalpha() else (b, a)
    try:
        return dt.date(int(annee), MOIS[mois.upper()], int(jour))
    except (KeyError, ValueError):
        return None


async def choisir_video(r):
    """La vidéo la plus récente de la pellicule, celle que le service vient d'y ranger : la 1re case après la caméra
    (« gallery-video-cell-0 »), vérifiée par sa date (du jour, ou de la veille passé minuit). Jamais une vidéo plus
    ancienne : la pellicule garde aussi des vidéos personnelles.
    Deux galeries vues le 04/10/2026 : sur @mapage.reels, un toucher ouvre l'éditeur ; sur @mapage, la
    sélection multiple est active (bouton sans libellé) et le toucher SÉLECTIONNE la vidéo (bandeau « Vidéo
    sélectionnée » en bas, bouton Suivant). Dans ce cas : exactement une vidéo sélectionnée, la nôtre, puis Suivant."""
    await r.attendre("gallery-close-button", delai=15)
    # une création coupée net (une publication ratée) laisse un brouillon : Instagram demande « Poursuivre la
    # modification de votre brouillon ? » par-dessus la galerie (vu le 05/10/2026 à 15 h 08) ; jamais « Continuer »
    # (ce serait l'ancienne vidéo) : « Commencer une nouvelle vidéo »
    if await r.si_present("Commencer une nouvelle vidéo", "Start new video", "Start New Video", types=["Button"], delai=2):
        await r.etape("Brouillon d'une publication coupée : « Commencer une nouvelle vidéo »")
        await asyncio.sleep(1.5)
    cases = await r.a.chercher("predicate string", "name BEGINSWITH 'gallery-' AND name ENDSWITH '-cell-0'")
    if not cases:
        raise ErreurPublication("galerie vide ou illisible (accès aux photos refusé à Instagram ?)")
    if (await r.a.attribut(cases[0], "name")) != "gallery-video-cell-0":
        raise ErreurPublication("le plus récent de la pellicule n'est pas une vidéo : la vidéo du service n'y est pas")
    case = cases[0]
    label = (await r.a.attribut(case, "label")) or ""
    jour, aujourdhui = date_de(label), dt.datetime.now(ZoneInfo("Europe/Paris")).date()
    if jour is None or (aujourdhui - jour).days not in (0, 1):
        raise ErreurPublication(f"la vidéo la plus récente de la pellicule n'est pas celle du jour ({label}) : rien "
                                "n'est choisi")
    await r.etape(f"Vidéo choisie : {label}")
    rect = await r.a.rect(case)
    for essai in range(2):
        await r.a.toucher(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)
        await asyncio.sleep(3)
        if await r.trouver("sundial-right-chevron-suivant-button", delai=3):
            return                                         # galerie simple : l'éditeur est ouvert
        choisies = await r.a.chercher("predicate string", "type == 'XCUIElementTypeButton' AND label == 'Vidéo sélectionnée'")
        if len(choisies) == 1:
            await r.etape("Sélection multiple : une seule vidéo choisie, Suivant")
            await r.toucher("reels-gallery-selection-next", delai=6)
            await asyncio.sleep(3)
            return
        if len(choisies) > 1:
            raise ErreurPublication(f"{len(choisies)} vidéos sélectionnées dans la galerie : une seule doit partir "
                                    "(vide la sélection dans Instagram avant de relancer)")
        # aucune : le toucher a désélectionné une vidéo restée choisie d'avant, on la rechoisit
    raise ErreurPublication("la vidéo ne se sélectionne pas dans la galerie (voir la capture)")


async def champ_legende(r):
    """Le champ de la légende visible (l'écran final en garde un second, caché, sous le mode « Légende »)."""
    eid = await r.premier_touchable("name == 'caption-cell-text-view'")
    if not eid:
        raise ErreurPublication("champ de la légende introuvable")
    return eid


async def ecrire_legende(r, legende):
    """Toucher le champ ouvre le mode « Légende » (champ en haut, clavier, bouton OK) ; la légende y est tapée puis
    relue avant OK."""
    await r.a.cliquer(await champ_legende(r))
    await asyncio.sleep(1.5)
    await r.taper(lambda: champ_legende(r), legende)
    await r.toucher("OK", types=["Button"], delai=6)
    await asyncio.sleep(1)


async def abandonner(r):
    """Répétition : on sort sans publier et sans garder de brouillon : Retour › Abandonner l'aperçu › Recommencer
    (le brouillon de la répétition est jeté) › Fermer la galerie."""
    for nom in ("BackButton", "discard-reel-preview", "camera-discard-draft", "gallery-close-button"):
        await r.si_present(nom, delai=5)
        await asyncio.sleep(1)
    await r.etape("Répétition : reel abandonné sans brouillon, rien n'est parti")




# ── warm-up (chauffe.py), calé le 07/10/2026 sur le vrai iPhone ─────────────────────────────────────────────────────
# Explorer (« explore-tab ») › champ « search-text-input » › mot-clé + Entrée › résultats (onglets « search-for-you-serp »…,
# « Comptes », puis « Publications » : cases « Vidéo de <compte> ») ; un reel ouvert (« reels-viewer ») se lit sur
# 30 niveaux en 1 s : « Reel de <compte>. », « like-button » (J'aime), « follow-button » (« Suivre <compte> »), sa
# légende ; « back-button » ramène aux résultats. L'onglet « reels-tab » ouvre le même lecteur.
PUBS = ("Sponsorisé", "Publicité", "Sponsored")


async def chauffer(r, compte, s):
    """Une séance de warm-up (chauffe.Seance) : la niche d'abord (recherche, reels des résultats), puis l'onglet Reels."""
    await r.etape("Ouverture d'Instagram")
    await r.a.profondeur(PROFONDEUR)
    await r.lancer_propre(BUNDLE)
    await r.alertes_refusees()
    await fermer_intrus(r)
    await choisir_compte(r, compte["identifiant"])
    await r.a.profondeur(PROFONDEUR_PROFIL)
    s.demarrer()
    niche = s.duree * random.uniform(0.5, 0.65)
    for _ in range(3):
        if s.fini() or s.ecoule() >= niche or not s.mot():
            break
        if await chercher(r, s):
            await regarder(r, s, niche=True, jusqua=niche)
    if not s.fini():
        await revenir_aux_onglets(r)
        await r.etape("Onglet Reels")
        await r.toucher("reels-tab", delai=8)
        await asyncio.sleep(2)
        await regarder(r, s, niche=False)
    await r.etape(f"Fin de la séance : {s.resume()}")


async def revenir_aux_onglets(r):
    """Ramène à un écran qui montre la barre d'onglets (un reel ouvert depuis la recherche la cache)."""
    for _ in range(4):
        if await r.trouver("explore-tab", delai=2):
            return
        await r.alertes_refusees()
        if not await r.si_present("back-button", "BackButton", delai=1.5):
            await fermer_intrus(r)
        await asyncio.sleep(1.2)
    raise ErreurPublication("la barre d'onglets d'Instagram ne revient pas (voir la capture)")


async def chercher(r, s):
    """Cherche le prochain mot-clé de la niche (Explorer) et ouvre le 1er reel des résultats."""
    mot = s.mot()
    await revenir_aux_onglets(r)
    await r.toucher("explore-tab", delai=8)
    await asyncio.sleep(2)
    champ = await r.premier_touchable("name == 'search-text-input'")
    if not champ:
        await r.etape("Champ de recherche introuvable (Explorer)")
        return False
    await r.a.cliquer(champ)
    await asyncio.sleep(1)
    await r.si_present("Effacer le texte", "Clear text", types=["Button"], delai=0.8)
    await r.a.ecrire(mot + "\n")
    await asyncio.sleep(3.5)
    s.cherche(mot)
    if not await r.trouver("search-for-you-serp", delai=6):
        await r.etape(f"Recherche « {mot} » : pas de résultats")
        return False
    # les reels de la grille des résultats (2 par ligne, ~190 pt de large) ; pas ceux du carrousel d'un compte en tête
    # des résultats (3 par ligne, ~125 pt, même nom « media-discovery-cell » : vu le 07/10/2026 sur une recherche, ils
    # ouvrent les « Publications » du compte, pas le lecteur de reels)
    videos = []
    for eid in await r.a.chercher("predicate string", "name == 'media-discovery-cell' AND (label BEGINSWITH 'Vidéo de' OR label BEGINSWITH 'Video by')"):
        try:
            rect = await r.a.rect(eid)
        except Exception:
            continue
        if rect["width"] >= 170 and 140 < rect["y"] and rect["y"] + 60 < (r.t.taille or (390, 844))[1]:
            videos.append((rect["y"], rect["x"], eid))
    await r.etape(f"Recherche « {mot} » : {len(videos)} reel(s) à l'écran")
    if not videos:
        return False
    await r.a.cliquer(min(videos)[2])
    await asyncio.sleep(3)
    if await r.trouver("reels-viewer", delai=6):
        return True
    await r.etape("Le reel ne s'est pas ouvert dans le lecteur : retour")
    return False


def _noeuds(n):
    yield n
    for e in n.get("children") or []:
        yield from _noeuds(e)


async def reel_courant(r):
    """Le reel à l'écran, lu dans l'arbre (1 s) : {auteur, pub, like (label, valeur), suivre (label)}, ou None si on
    n'est plus dans le lecteur. Une publicité (« Sponsorisée », bouton « Acheter », vue le 07/10/2026) n'a pas de
    « Reel de … » : auteur None, pub vraie."""
    w, h = r.t.taille or (390, 844)
    try:
        arbre = await r.a.arbre()
    except Exception:
        return None

    def visible(n):
        x = n.get("rect") or {}
        return x.get("width", 0) > 0 and x.get("height", 0) > 0 and 0 <= x.get("y", -1) < h - 40 and 0 <= x.get("x", -1) < w

    reel = {"auteur": None, "pub": False, "like": None, "suivre": None}
    lecteur = False
    for n in _noeuds(arbre or {}):
        lab, nom = n.get("label") or "", n.get("name") or ""
        lecteur = lecteur or nom in ("reels-viewer", "sundial-viewer-video-cell")
        if lab.startswith(("Reel de ", "Reel by ")) and visible(n) and (n.get("rect") or {}).get("y", 99) < 40 and not reel["auteur"]:
            reel["auteur"] = lab.split(" ", 2)[-1].rstrip(".")
    if not lecteur and not reel["auteur"]:
        return None
    if not reel["auteur"]:
        reel["pub"] = True                       # dans le lecteur, sans « Reel de … » : une publicité (ou inconnu)
    for n in _noeuds(arbre):
        lab, nom = n.get("label") or "", n.get("name") or ""
        if not visible(n):
            continue
        if any(m in lab for m in PUBS):
            reel["pub"] = True
        if nom == "like-button" and reel["like"] is None:
            reel["like"] = (lab, str(n.get("value") or ""))
        if nom == "follow-button" and lab.startswith(("Suivre", "Follow")):
            reel["suivre"] = lab
    return reel


def deja_aime(like):
    lab, valeur = like or ("", "")
    return lab in ("Je n’aime plus", "Je n'aime plus", "Unlike", "Ne plus aimer") or valeur.lower() in ("1", "true", "sélectionné", "selected")


async def regarder(r, s, niche, jusqua=None):
    """Regarde les reels les uns après les autres ; les publicités passées vite ; dans la niche, quelques likes et
    abonnements si le jour du warm-up le permet."""
    n = 0
    while not s.fini() and (jusqua is None or s.ecoule() < jusqua):
        reel = await reel_courant(r)
        if not reel:
            await r.alertes_refusees()
            await fermer_intrus(r)
            if niche or not await r.si_present("reels-tab", delai=3):
                await r.etape("Plus sur les reels")
                return
            continue
        d = random.uniform(1.5, 3) if reel["pub"] else s.duree_video(niche)
        await s.regarder(d * 0.5)
        if niche and not reel["pub"] and not s.fini():
            if reel["suivre"] and s.envie_de_suivre():
                await suivre(r, s, reel)
            if reel["like"] and not deja_aime(reel["like"]) and s.envie_de_liker(d):
                await liker(r, s, reel)
            if s.envie_de_liker_commentaires(d):
                await liker_commentaires(r, s)
        await s.regarder(d * 0.5)
        s.vues += 1
        n += 1
        if s.fini():
            break
        await glisser(r)
        if n % 5 == 0:
            await r.alertes_refusees()


async def glisser(r):
    w, h = r.t.taille or (390, 844)
    x = w / 2 + random.uniform(-30, 30)
    await r.a.glisser(x, h * random.uniform(0.62, 0.7), x + random.uniform(-15, 15), h * random.uniform(0.18, 0.26),
                      random.uniform(0.18, 0.32))
    await asyncio.sleep(random.uniform(0.8, 1.4))


async def liker(r, s, reel):
    """Le bouton « J'aime » du reel ; compté si son état a changé."""
    bouton = await r.premier_touchable("name == 'like-button'")
    if not bouton:
        return
    await r.a.cliquer(bouton)
    await asyncio.sleep(1.2)
    apres = await reel_courant(r)
    if apres and apres["like"] and apres["like"] != reel["like"]:
        s.likes += 1
        await r.etape(f"Like n° {s.likes} ({reel['auteur']})", capture=s.likes == 1)
    else:
        await r.etape(f"Like pas vu ({reel['auteur']} : bouton inchangé)")


async def liker_commentaires(r, s):
    """Ouvre les commentaires du reel, aime un ou deux commentaires du haut, referme. Calé le 14/10/2026 sur le vrai iPhone
    (sonde.py) : chaque commentaire a son bouton « comment-like-button » (« Aimer le commentaire »), touché PAR SON NOM ;
    jamais la barre d'émojis ni le champ du bas (un toucher y publie un commentaire). Le panneau se ferme d'un toucher
    au-dessus de lui (y = 110 pt : sur la vidéo). Compté si le bouton ne dit plus « Aimer le commentaire »."""
    bouton = await r.premier_touchable("name == 'comment-button'")
    if not bouton:
        return
    w, h = r.t.taille or (390, 844)
    try:
        await r.a.cliquer(bouton)
    except ErreurAgent:
        return
    await asyncio.sleep(2.5)

    async def coeurs():
        """Les cœurs de la liste visible, lus à neuf : [(y, eid, label)] (après un like, Instagram redessine la liste et
        les anciens identifiants ne valent plus rien : « stale element », vu le 14/10/2026)."""
        out = []
        for eid in await r.a.chercher("predicate string", "name == 'comment-like-button'"):
            try:
                x, lab = await r.a.rect(eid), (await r.a.attribut(eid, "label")) or ""
            except ErreurAgent:
                continue
            if 300 < x["y"] < h - 140:          # dans la liste visible, loin de la barre d'émojis et du champ
                out.append((x["y"], eid, lab))
        return sorted(out, key=lambda c: c[0])

    try:
        voulus, vus = random.randint(1, 2), set()
        for _ in range(5):
            if voulus <= 0 or not s.peut_liker_commentaire() or s.fini():
                break
            libres = [c for c in await coeurs() if c[2] == "Aimer le commentaire" and round(c[0]) not in vus]
            if not libres:
                break
            y, eid, _ = random.choice(libres[:3])   # un des trois du haut : pas forcément le premier
            vus.add(round(y))
            try:
                await r.a.cliquer(eid)
            except ErreurAgent as e:
                await r.etape(f"Like de commentaire raté ({e})", capture=False)
                continue
            await asyncio.sleep(random.uniform(0.9, 1.6))
            apres = next((c[2] for c in await coeurs() if abs(c[0] - y) < 8), "")
            if apres and apres != "Aimer le commentaire":
                s.likes_com += 1
                voulus -= 1
                await r.etape(f"Like de commentaire n° {s.likes_com}", capture=s.likes_com == 1)
            else:
                await r.etape("Like de commentaire pas vu (bouton inchangé)", capture=False)
            await s.regarder(random.uniform(1.5, 4))
    except ErreurAgent as e:                     # un commentaire raté ne coupe jamais la séance
        await r.etape(f"Commentaires : {e}", capture=False)
    finally:
        await r.a.toucher(w / 2, 110)            # au-dessus du panneau : il se ferme
        await asyncio.sleep(1.5)


async def suivre(r, s, reel):
    """« Suivre <compte> » sur le reel ; compté si le bouton a changé ou disparu."""
    bouton = await r.premier_touchable(f"name == 'follow-button' AND label == {q(reel['suivre'])}")
    if not bouton:
        return
    await r.a.cliquer(bouton)
    await asyncio.sleep(1.5)
    apres = await reel_courant(r)
    if apres and apres["suivre"] == reel["suivre"]:
        await r.etape(f"Abonnement pas vu ({reel['suivre']})")
        return
    s.abonnements += 1
    await r.etape(f"Abonnement n° {s.abonnements} : {reel['auteur']}")
