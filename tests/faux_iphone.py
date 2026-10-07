"""faux_iphone.py : un faux iPhone pour essayer le service sans téléphone (sur le Mac, en quelques secondes).

- `faux-ios` (le script à côté) appelle ce module comme go-ios : list, info, devmode, image, tunnel, apps, fsync,
  pasteboard, screenshot, et les deux programmes qui tournent en continu : `ui run wda` (le faux WebDriverAgent)
  et `forward <port> 9100` (le faux flux d'écran MJPEG) ;
- le faux WebDriverAgent fait tourner un mini TikTok et un mini Instagram, aux noms d'accessibilité relevés sur le
  vrai iPhone le 04/10/2026 (juste ce qu'il faut pour dérouler les recettes, pièges compris : bandeau des comptes de
  TikTok hors de l'arbre, son ajouté par TikTok, galerie en sélection multiple, champ de légende caché…) ;
- tout l'état vit dans $FAUX_IOS_DIR/etat.json (branché ? appairé ? écran courant ? presse-papiers ?), que le
  test lit et modifie.

Ce n'est pas TikTok : la vraie app a d'autres noms de boutons. Ça prouve la plomberie (préparation, file, robot,
captures, lien renvoyé au centre), pas la recette."""
import asyncio
import base64
import io
import json
import os
import re
import shutil
import signal
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DIR = Path(os.environ.get("FAUX_IOS_DIR", "/tmp/faux-ios"))
ETAT = DIR / "etat.json"
UDID = "00008110-FAUXIPHONE0001"
W, H = 390, 844
WDA_BUNDLE = "com.faux.WebDriverAgentRunner.xctrunner"
VLC = "org.videolan.vlc-ios"
TIKTOK = "com.zhiliaoapp.musically"
INSTAGRAM = "com.burbn.instagram"


def etat_initial():
    return {"branche": True, "appaire": True, "devmode": True, "image": False, "ios": "26.0", "tunnel": False,
            "apps": [TIKTOK, INSTAGRAM, VLC, WDA_BUNDLE], "presse_papiers": "", "ecran": "accueil", "photos": [],
            "tt_comptes": ["ma_page2.0", "ma_page"], "tt_actif": "ma_page2.0", "tt_ajout_touche": False, "tt_videos": {},
            "tt_lancements": 0, "tt_photos_ok": False, "tt_desc": "", "selection": None, "alertes": [],
            "tt_camera_vue": False, "tt_filtre": "Tous", "tt_choisies": [], "tt_son": None, "tt_brouillons": {}, "tt_posts": [],
            "ig_comptes": ["ma.page.ig2", "ma.page.ig"], "ig_actif": "ma.page.ig2", "ig_pubs": {}, "focus": None,
            "ig_multi": {"ma.page.ig": True}, "ig_choisies": [], "ig_selection": None, "ig_desc": "", "ig_recherche": "",
            "ig_brouillons": 0,
            "tss_https_ko": True, "image_par": None,     # comme le PC : Windows ne connaît pas la racine d'Apple
            "xctest_non_signe": True, "agent_signe_par": None,   # comme Impactor : module de test de l'agent pas signé
            "raccourci_efface": False,                          # le Raccourci à 2 actions (02/10/2026) : il n'efface pas le fichier
            "menu_coller_jusqua": 0, "envoi_jusqua": 0, "journal": [],
            # le warm-up (07/10/2026) : fil « Pour toi », recherche, vidéos ouvertes ; reels d'Instagram
            "tt_q": "", "tt_onglet_r": "Top", "tt_lecture": 0, "tt_aimes": [], "tt_suivis": [], "tt_fil_vues": 0,
            "tt_fil_likes": 0, "tt_vues_niche": 0, "tt_recherches": [], "tt_pop_vue": False, "tt_coeur_anim": 0,
            "ig_lecture": None, "ig_aimes": [], "ig_suivis": [], "ig_vues": 0, "ig_recherches": [], "ig_unlike": False}


def lire():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return etat_initial()


def ecrire(e):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = ETAT.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ETAT)


def dire(msg, niveau="INFO", **x):
    print(json.dumps({"level": niveau, "msg": msg, **x}), file=sys.stderr)


def app_dir(app):
    return DIR / "apps" / app


# ── le faux go-ios ────────────────────────────────────────────────────────────────────────────────────
def goios(argv):
    opts = {a.split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    mots = [a for a in argv if not a.startswith("--")]
    e = lire()
    cmd = mots[0] if mots else ""

    if cmd == "list":
        print(json.dumps({"deviceList": [UDID] if e["branche"] else []}))
    elif cmd == "info":
        if not e["appaire"]:
            dire("failed getting values", "ERROR", err="could not retrieve PairRecord")
            return 1
        print(json.dumps({"DeviceName": "iPhone de test", "ProductType": "iPhone14,5", "ProductVersion": e["ios"]}))
    elif cmd == "pair":
        e["appaire"] = True
        ecrire(e)
    elif cmd == "devmode":
        if mots[1] == "get":
            print(json.dumps({"DeveloperModeEnabled": e["devmode"]}))
    elif cmd == "image":
        if mots[1] == "list":
            dire("image signature" if e["image"] else "none", signature="abcd")
        elif mots[1] == "auto":
            if e.get("tss_https_ko"):        # le PC du 01/10/2026 : gs.apple.com refusé en HTTPS
                base = Path(opts["--basedir"]) / "ddi-FAUX" / "Restore"
                (base / "Firmware").mkdir(parents=True, exist_ok=True)
                for f in (base / "FAUX.dmg", base / "BuildManifest.plist", base / "Firmware" / "FAUX.dmg.trustcache"):
                    f.write_bytes(b"faux")
                dire("success downloaded image")
                dire("error mounting image", "ERROR", err="MountImage: failed to get signature from Apple: getSignature: failed "
                     "to send request: Post \"https://gs.apple.com/TSS/controller?action=2\": tls: failed to verify certificate: "
                     "x509: certificate signed by unknown authority")
                return 1
            e["image"], e["image_par"] = True, "go-ios"
            ecrire(e)
            dire("success downloaded image")
            dire("success mounting image")
    elif cmd == "tunnel":
        if mots[1] == "ls":
            if not e["tunnel"]:
                dire("failed to get tunnel infos", "ERROR")
                return 1
            print(json.dumps([{"udid": UDID, "address": "fd00::1", "rsdPort": 58783, "userspaceTun": True, "userspaceTunPort": 60105}]))
        elif mots[1] == "start":
            e["tunnel"] = True
            ecrire(e)

            def fin(*_):
                x = lire()
                x["tunnel"] = False
                ecrire(x)
                sys.exit(0)
            signal.signal(signal.SIGTERM, fin)
            while True:
                time.sleep(1)
    elif cmd == "apps":
        noms = {TIKTOK: ("TikTok", "TikTok"), INSTAGRAM: ("Instagram", "Instagram"), VLC: ("VLC", "VLC"), WDA_BUNDLE: ("WebDriverAgentRunner-Runner", "WebDriverAgentRunner-Runner")}
        print(json.dumps([{"CFBundleIdentifier": b, "CFBundleName": noms.get(b, (b,))[0], "CFBundleExecutable": noms.get(b, (b, b))[1]}
                          for b in e["apps"]]))
    elif cmd == "fsync":
        racine = app_dir(opts["--app"]) if opts.get("--app") else DIR / "media"
        if mots[1] == "mkdir":
            (racine / opts["--path"].lstrip("/")).mkdir(parents=True, exist_ok=True)
        elif mots[1] == "push":
            dst = racine / opts["--dstPath"].lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(opts["--srcPath"], dst)
        elif mots[1] == "tree":
            d = racine / opts["--path"].lstrip("/")
            if not d.is_dir():
                dire("fsync: tree view failed", "ERROR")
                return 1
            print(f"|-{d.name}/")
            for f in sorted(d.rglob("*")):             # comme go-ios (WalkDir) : sous-dossiers compris
                print(f"{'|  ' * len(f.relative_to(d).parts)}|-{f.name}{'/' if f.is_dir() else ''}")
        elif mots[1] == "rm":
            (racine / opts["--path"].lstrip("/")).unlink(missing_ok=True)
    elif cmd == "pasteboard":
        if mots[1] == "set":
            e["presse_papiers"] = sys.stdin.read()
            ecrire(e)
        else:
            print(e["presse_papiers"])
    elif cmd == "screenshot":
        Path(opts["--output"]).write_bytes(dessiner(e, "PNG"))
    elif cmd == "forward":
        asyncio.run(servir_flux(int(mots[1])))
    elif cmd == "ui" and mots[1:3] == ["run", "wda"]:
        if e.get("xctest_non_signe") and e.get("agent_signe_par") != "go-ios":
            dire("ui run: runner failed", "ERROR", error="Failed to load the test bundle (Error code: 103, Domain: com.apple.XCTestErrorDomain)")
            return 1
        asyncio.run(servir_wda(int(opts["--host-port"])))
    elif cmd == "kill":
        e.setdefault("tues", []).append(mots[1] if len(mots) > 1 else "")
        ecrire(e)
        dire("process killed")
    elif cmd == "sign" and mots[1:2] == ["app"]:
        manque = [o for o in ("--path", "--p12file", "--profile", "--bundleid") if not opts.get(o)]
        if manque or not all(Path(opts[o]).exists() for o in ("--path", "--p12file", "--profile")) or "--install" not in opts:
            dire("failed signing app", "ERROR", err=f"arguments : {opts}")
            return 1
        e["agent_signe_par"] = "go-ios"
        ecrire(e)
        dire("signed app", bundleID=opts["--bundleid"])
        dire("installation successful")
    else:
        dire(f"commande inconnue du faux go-ios : {argv}", "ERROR")
        return 2
    return 0


# ── l'écran : un mini TikTok et un mini Instagram, aux noms relevés sur le vrai iPhone (04/10/2026) ─────────
# Chaque élément : (type, label, (x, y, l, h), name, value, touchable). name None : comme le label.
JOURS = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]
MOIS_FR = ["JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOÛT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DÉCEMBRE"]
ALERTES = {"camera": ("« TikTok » souhaite accéder à la caméra.", ["Ne pas autoriser", "Autoriser"]),
           "micro": ("« TikTok » souhaite accéder au micro.", ["Ne pas autoriser", "Autoriser"]),
           "photos": ("« TikTok » souhaite accéder à l’intégralité de votre photothèque.",
                      ["Limiter l’accès…", "Autoriser l’accès complet", "Ne pas autoriser"])}


def E(t, label, rect, name=None, value=None, touchable=True):
    return (t, label, rect, name, value, touchable)


def onglets():
    return [E("Button", "Accueil", (0, 761, 78, 49)), E("Button", "Créer", (156, 761, 78, 49)), E("Button", "Profil", (312, 761, 78, 49))]


def ig_onglets():
    return [E("Button", "Fil principal", (0, 761, 78, 49), "mainfeed-tab"), E("Button", "Reels", (78, 761, 78, 49), "reels-tab"),
            E("Button", "Explorer", (234, 761, 78, 49), "explore-tab"), E("Button", "Profil", (312, 761, 78, 49), "profile-tab")]


def videos(e):
    """La pellicule, de la plus ancienne à la plus récente : deux vidéos personnelles (août), puis celles du service (du jour)."""
    import datetime as dt
    jour = dt.date.today().isoformat()
    return [{"nom": "perso-1.mov", "jour": "2026-08-30"}, {"nom": "perso-2.mov", "jour": "2026-08-31"}] + \
           [{"nom": n, "jour": jour} for n in e["photos"]]


def tt_cases(e):
    """La galerie de TikTok, filtre « Vidéos » : des plus anciennes (en haut) aux plus récentes (en bas) ; 12 cases à
    l'écran, les 12 dernières une fois la galerie descendue (un glissement suffit ici)."""
    vids = videos(e)
    vus = vids[-12:] if e.get("tt_defile") else vids[:12]
    return [(v["nom"], (i % 3 * 130, 141 + i // 3 * 131, 129, 129)) for i, v in enumerate(vus)]


def niche(i):
    """La i-ème vidéo de la niche (résultats de recherche, puis celles qui suivent quand on glisse)."""
    return {"id": f"n{i}", "auteur": f"revendeur.{i % 4}", "desc": f"Achat revente vinted, épisode {i}"}


def tt_cases_resultats(e):
    """L'onglet Vidéos des résultats de TikTok : 4 cases, la 1re une publicité (jamais ouverte)."""
    cases = [("pub", "Vinted 24h, gagne 500 € par jour. Publicité. Il y a 2 j. MarqueX. 99 j'aime.")]
    cases += [(i, f"{niche(i)['desc']}. Il y a {i + 1} j. {niche(i)['auteur']}. {1000 * (i + 1)} j'aime.") for i in range(3)]
    rects = [(4, 137, 189, 377), (197, 137, 189, 377), (4, 518, 189, 377), (197, 518, 189, 377)]
    return [(c, l, r) for (c, l), r in zip(cases, rects)]


def ig_reel(e):
    """Le reel à l'écran (lecteur d'Instagram) : ses infos, ou None. Un reel sur sept est une publicité."""
    lec = e.get("ig_lecture")
    if not lec:
        return None
    i = lec["i"]
    n = niche(i) if lec["source"] == "recherche" else {"id": f"r{i}", "auteur": f"createur.{i % 5}", "desc": f"Reel au hasard {i}"}
    return {**n, "pub": i % 7 == 3}


def ig_compte_label(e, c):
    return f"Profil INSTAGRAM, {c}" + ("" if c == e["ig_actif"] else ", 8 followers et 3 autres")


def elements(e):
    ec = e["ecran"]
    if ec == "accueil":
        return [E("Icon", "TikTok", (40, 120, 64, 64)), E("Icon", "Instagram", (130, 120, 64, 64)), E("Icon", "VLC", (220, 120, 64, 64))]
    if ec == "raccourcis":
        return [E("StaticText", "Auto importer", (20, 200, 350, 40))]
    # TikTok
    if ec == "tt_intrus":                     # vu le 03/10/2026 : tant qu'elle est là, rien d'autre ne répond
        return [E("StaticText", "Mise à jour des Règles de la communauté", (64, 307, 262, 54)),
                E("Button", "J'ai compris", (44, 512, 302, 49))]
    if ec == "tt_fil":
        l = onglets() + [E("Button", "LIVE", (16, 57, 24, 24)), E("Button", "Suivis", (140, 47, 55, 44), "following"),
                         E("Button", "Pour toi", (272, 47, 68, 44), "top_tabs_recomend", "1"), E("Button", "Rechercher", (350, 57, 24, 24))]
        if e["envoi_jusqua"] > time.time():
            l.append(E("StaticText", "Envoi 42 %", (10, 60, 120, 30)))
        return l
    if ec == "tt_pop":                        # une fenêtre glissée sur le fil pendant qu'on scrolle
        return [E("StaticText", "Ajoute tes amis sur TikTok", (64, 307, 262, 54)), E("Button", "Pas maintenant", (44, 512, 302, 49))]
    if ec == "tt_recherche":
        return [E("Button", "Retour", (4, 47, 44, 44)), E("SearchField", "Tendance : la mode d'automne", (48, 51, 229, 36), None, e["tt_q"] or None),
                E("Button", "Recherche vocale", (229, 51, 48, 36)), E("Button", "Rechercher", (293, 47, 81, 44))]
    if ec == "tt_resultats":
        o = e["tt_onglet_r"]
        l = [E("Button", "Retour", (4, 47, 44, 44)), E("SearchField", "Rechercher", (48, 51, 291, 36), None, e["tt_q"] or None),
             E("Button", "Top", (117, 102, 27, 22), None, "1" if o == "Top" else None), E("Button", "Utilisateurs", (166, 102, 81, 22)),
             E("Button", "LIVE", (266, 102, 32, 22)), E("Button", "Vidéos", (318, 102, 49, 22), None, "1" if o == "Vidéos" else None)]
        if o == "Vidéos":
            l += [E("Other", label, rect) for _, label, rect in tt_cases_resultats(e)]
        return l
    if ec == "tt_video":                      # une vidéo ouverte : ses boutons de droite ne sont PAS dans l'arbre
        return [E("Other", None, (0, 0, 390, 844), "TTKFeedDetailRootComponent", touchable=False),
                E("Button", "returnButton", (6, 47, 44, 44))]
    if ec in ("tt_live", "tt_pub", "tt_autre_profil"):     # les pièges : jamais ouverts par le warm-up
        return [E("Button", "Fermer", (8, 64, 44, 45))]
    if ec in ("tt_profil", "tt_comptes"):     # le panneau des comptes n'est PAS dans l'arbre (vrai TikTok, 04/10/2026)
        vids = e["tt_videos"].get(e["tt_actif"], [])
        charge = [E("StaticText", "chargement…", (150, 380, 90, 20))] if e.get("tt_bascule") else []
        if e.get("tt_profil_charge_jusqua", 0) > time.time():     # le profil qui s'ouvre charge (vu le 05/10/2026)
            charge.append(E("Other", "Chargement", (179, 45, 32, 32)))
        return charge + ([E("Button", "Menu", (342, 47, 42, 44), "nav_bar_end_settings"),
                 E("StaticText", e["tt_actif"].replace("_", " ").title(), (16, 103, 226, 38)),
                 E("Button", "Changer de compte", (246, 114, 16, 16), "IconArrowTriangleDownLargeFill"),
                 E("Other", "@" + e["tt_actif"], (16, 143, 120, 16), "user_account_user_name")]
                + [E("Cell", f"Vidéo {v}", (i % 3 * 130, 400 + i // 3 * 170, 128, 168)) for i, v in enumerate(vids)] + onglets())
    if ec == "tt_creation":                   # caméra et micro refusés : l'écran le dit, « Importer » reste là
        return [E("Button", "Fermer", (8, 64, 44, 45)), E("Button", "Accéder à la caméra", (78, 394, 234, 60)),
                E("Button", "Importer", (12, 756, 44, 44), "recordPageUploadButton")]
    if ec == "tt_galerie":
        l = [E("Button", "Retour", (16, 62, 24, 24)), E("Button", "Tous", (15, 101, 66, 40)), E("Button", "Vidéos", (80, 101, 76, 40)),
             E("Cell", "Camera", (157, 638, 76, 76), touchable=False)]           # un effet de la caméra, caché dessous
        l += [E("Cell", None, r) for _, r in tt_cases(e)] if e["tt_filtre"] == "Vidéos" else []
        l += [E("Cell", None, (6 + 82 * j, 669, 76, 76)) for j, _ in enumerate(e["tt_choisies"])]   # le bandeau des choisies
        if e["tt_choisies"]:
            l.append(E("Button", "icDeleteAssetOptimize", (50, 679, 26, 26)))
        return l + [E("Button", "Suivant", (199, 762, 179, 44))]
    if ec == "tt_editeur":
        son = e.get("tt_son")
        return [E("Button", "Retour", (14, 74, 28, 29), "(editPageBackButton)"),
                E("Button", son or "Ajouter un son", (101, 66, 188, 45) if son else (118, 66, 154, 45)),
                E("Button", "Récents", (140, 56, 110, 36), touchable=False),          # la galerie, cachée dessous
                E("Button", "Paramètres", (348, 72, 32, 33), "editPageToolBarPrivacySettings"),
                E("Button", "Suivant", (199, 762, 179, 44), "(editPageNextButton)")]
    if ec == "tt_poster":                     # clavier ouvert (champ touché) : « Publier » du bas caché, pastille hors de l'arbre
        l = [E("Button", "Retour", (6, 47, 44, 44), "(publishPageBackButton)"),
             E("TextView", "Ajouter une description…", (16, 105, 230, 143), None, e["tt_desc"] or "Ajouter une description…")]
        if e.get("focus") == "tt_desc":
            return l + [E("Key", " ", (100, 722, 192, 54), "space")]
        return l + [E("Button", "Brouillons", (12, 758, 180, 48)), E("Button", "Publier", (198, 758, 180, 48))]
    # Instagram
    if ec == "ig_fil":
        envoi = e.get("ig_envoi") or {}
        if envoi.get("etat") in ("en_cours", "bloque"):
            return [E("StaticText", "Ne fermez pas Instagram pour finir de publier • 26.5%", (55, 240, 328, 34))] + ig_onglets()
        if envoi.get("etat") == "erreur":
            return [E("StaticText", "Une erreur s’est produite, veuillez réessayer plus tard.", (55, 240, 221, 34)),
                    E("Button", "ig icon arrow cw outline 16", (289, 235, 44, 44)), E("Button", "ig icon x pano outline 16", (335, 235, 44, 44))] + ig_onglets()
        return ig_onglets()
    if ec == "ig_profil":
        n = 40 + len(e["ig_pubs"].get(e["ig_actif"], []))
        return [E("Button", "Appuyez pour ouvrir le menu de création", (16, 50, 24, 44), "profile-add-button"),
                E("Button", e["ig_actif"], (104, 47, 182, 50), "user-switch-title-button", "D’autres profils ont reçu des notifications"),
                E("Button", "Nombre de publications", (123, 144, 97, 78), "user-detail-header-media-button", f"{n} publications"),
                E("Cell", "Reels", (130, 711, 130, 41))] + ig_onglets()
    if ec == "ig_comptes":
        l = [E("Button", ig_compte_label(e, c), (16, 529 + 64 * i, 358, 64)) for i, c in enumerate(e["ig_comptes"])]
        return l + [E("Button", "Ajouter un compte Instagram", (16, 529 + 64 * len(l), 358, 64), "IdentitySwitcher_EntryPoint_AddInstagramAccount")]
    if ec == "ig_creer":
        return [E("Cell", "Reel", (0, 360, 390, 44), "creation-reel"), E("Cell", "Publication", (0, 448, 390, 44), "creation-post")]
    if ec == "ig_galerie":
        import datetime as dt
        multi = e["ig_multi"].get(e["ig_actif"], False)
        l = [E("Button", "Fermer la galerie", (12, 59, 44, 44), "gallery-close-button"),
             E("Button", None if multi else "Sélectionner", (342, 172, 32, 32), "multi-select"),
             E("Cell", "Caméra", (0, 214, 129, 229), "gallery-camera-dark-background")]
        for i, v in enumerate(reversed(videos(e))):                            # les plus récentes d'abord
            d = dt.date.fromisoformat(v["jour"])
            lab = f"Miniature vidéo, durée de la vidéo\xa0: 0:24, {JOURS[d.weekday()]}, {MOIS_FR[d.month - 1]} {d.day}, {d.year}"
            k = i + 1
            l.append(E("Cell", lab, (k % 3 * 130, 214 + k // 3 * 230, 130, 229), f"gallery-video-cell-{i}"))
        if multi and e["ig_choisies"]:
            l += [E("Button", "Vidéo sélectionnée", (12 + 34 * j, 746, 30, 53)) for j, _ in enumerate(e["ig_choisies"])]
            l.append(E("Button", "Suivant", (293, 751, 85, 43), "reels-gallery-selection-next"))
        if e.get("ig_brouillon_coupe"):
            l += [E("StaticText", "Poursuivre la modification de votre brouillon\xa0?", (70, 361, 250, 49)),
                  E("Button", "Continuer", (45, 520, 300, 53)), E("Button", "Commencer une nouvelle vidéo", (45, 572, 300, 53))]
        return l
    if ec in ("ig_editeur", "ig_promo"):
        l = [E("Button", "Abandonner l’aperçu du reel", (12, 59, 44, 44), "discard-reel-preview"),
             E("Button", "Audio suggéré, Appuyez pour appliquer", (85, 59, 220, 44), "sundial-postcapture-suggestion-pill"),
             E("Button", "Suivant", (289, 753, 85, 44), "sundial-right-chevron-suivant-button")]
        if ec == "ig_promo":                  # vu le 05/10/2026 : la pub pour l'app Edits, glissée par-dessus l'éditeur
            l += [E("Other", None, (0, 444, 390, 800), "ig-partial-modal-sheet-view-controller-content", touchable=False),
                  E("Button", "Fermer", (178, 459, 34, 2), "Bouton"),
                  E("StaticText", "Enrichissez vos vidéos avec Edits", (24, 473, 242, 48)),
                  E("Button", "Obtenir", (285, 663, 80, 62), "AppStoreComponents.offerButton"),
                  E("Button", "Télécharger sur l’App\xa0Store", (87, 752, 216, 32))]
        return l
    if ec == "ig_abandon":
        return [E("StaticText", "Recommencer\xa0?", (132, 309, 126, 20)),
                E("Button", "Recommencer", (45, 408, 300, 53), "camera-discard-draft"),
                E("Button", "Enregistrer le brouillon", (45, 460, 300, 53), "camera-save-draft"),
                E("Button", "Continuer les modifications", (45, 512, 300, 53), "camera-cancel-draft")]
    if ec in ("ig_final", "ig_apropos"):
        l = [E("Other", None, (0, 0, 390, 844), "sundial-share-sheet-view-controller", touchable=False),
             E("Button", "Retour", (20, 47, 36, 44), "BackButton"),
             E("TextView", "Ajouter une légende...", (16, 409, 358, 148), "caption-cell-text-view", e["ig_desc"] or None),
             E("Cell", "Partager aussi sur…, Ma Page", (0, 641, 390, 49)),
             E("Button", "Enregistrer le brouillon", (16, 753, 171, 45), "save-draft-button"),
             E("Button", "Suivant", (203, 753, 171, 45), "share-sheet-share-button")]
        if ec == "ig_apropos":                # vue le 04/10/2026 : l'écran final reste dessous, dans l'arbre
            l += [E("StaticText", "À propos de Reels", (0, 154, 390, 31)), E("Button", "Partager", (16, 680, 358, 44)),
                  E("Button", "Annuler", (16, 734, 358, 32))]
        return l
    if ec == "ig_legende":                    # le mode « Légende » : un 2e champ, caché, reste dessous (vu le 04/10/2026)
        return [E("Button", "OK", (334, 54, 36, 30)),
                E("TextView", "Ajouter une légende...", (16, 409, 358, 148), "caption-cell-text-view", e["ig_desc"] or None, touchable=False),
                E("TextView", "Ajouter une légende...", (16, 101, 358, 98), "caption-cell-text-view", e["ig_desc"] or None)]
    if ec == "ig_reels":
        a = e["ig_actif"]
        l = [E("Cell", f"Reel de {a} - 2,8 M\xa0lectures", (0, 231, 130, 231), "reels-video-thumbnail"),     # épinglé
             E("Image", None, (105, 239, 17, 17), "ig_icon_pin_filled_24")]
        for i, _ in enumerate(e["ig_pubs"].get(a, [])[:5]):
            k = i + 1
            l.append(E("Cell", f"Reel de {a} - 0\xa0lecture", (k % 3 * 130, 231 + k // 3 * 231, 130, 231), "reels-video-thumbnail"))
        return l + ig_onglets()
    if ec == "ig_reel":
        return [E("Button", "Retour", (18, 60, 24, 24), "back-button"), E("Button", "J’aime", (337, 444, 45, 44), "like-button"),
                E("Button", "Envoyer", (337, 587, 45, 44), "send-button"), E("Button", "Plus d’actions", (339, 655, 41, 48), "more-options-button")]
    if ec == "ig_envoi":
        return [E("SearchField", "Rechercher des comptes", (45, 417, 275, 44), "search-text-input"),
                E("Button", "Un ami", (40, 480, 100, 120)),                # un contact : jamais touché
                E("Button", "Copier le lien", (92, 707, 78, 89))]
    if ec == "ig_resultats":
        return [E("Button", "Retour", (20, 47, 36, 44), "BackButton"), E("Button", "Pour vous", (0, 101, 99, 41), "search-for-you-serp", "1"),
                E("Button", "Profils", (98, 101, 72, 41), "search-user-serp"), E("StaticText", "Comptes", (16, 158, 358, 20)),
                # le carrousel d'un compte en tête des résultats (vu sur « vinted ») : mêmes noms que la grille, plus petit,
                # il ouvre les « Publications » du compte, pas le lecteur de reels
                E("Cell", "Vidéo de vinted", (0, 230, 128, 180), "media-discovery-cell"),
                E("Cell", "Vidéo de vinted", (131, 230, 128, 180), "media-discovery-cell"),
                E("Cell", None, (0, 189, 390, 59), "search-collection-view-cell-1"),
                E("StaticText", "Publications", (16, 495, 358, 20)),
                E("Cell", f"Vidéo de {niche(0)['auteur']}", (0, 530, 195, 260), "media-discovery-cell"),
                E("Cell", f"Vidéo de {niche(1)['auteur']}", (195, 530, 195, 260), "media-discovery-cell")] + ig_onglets()
    if ec == "ig_lecteur":
        r = ig_reel(e)
        l = [E("Other", None, (0, 0, 390, 844), "reels-viewer", touchable=False)]
        if not r["pub"]:                      # une publicité n'a pas de « Reel de … » (vu le 07/10/2026)
            l.append(E("Other", f"Reel de {r['auteur']}.", (0, 0, 390, 761), touchable=False))
        l += [E("Button", "J’aime", (337, 372, 45, 44), "like-button", "1" if r["id"] in e["ig_aimes"] else None),
             E("Button", "Envoyer", (337, 590, 45, 44), "send-button"),
             E("StaticText", r["desc"], (16, 719, 307, 22))]
        if r["auteur"] not in e["ig_suivis"]:
            l.append(E("Button", f"Suivre {r['auteur']}", (162, 680, 59, 26), "follow-button"))
        if r["pub"]:
            l += [E("StaticText", "Sponsorisée", (300, 520, 80, 16)), E("Button", "Acheter", (16, 420, 300, 40))]
        if e["ig_lecture"]["source"] == "recherche":
            l.append(E("Button", "Retour", (18, 60, 24, 24), "back-button"))
        else:
            l += ig_onglets()
        return l
    if ec == "ig_explorer":
        l = [E("SearchField", "Rechercher", (48, 56, 246, 36), "search-text-input", e["ig_recherche"] or None, touchable=False),
             E("SearchField", "Rechercher", (48, 54, 260, 36), "search-text-input", e["ig_recherche"] or None)]
        if e["menu_coller_jusqua"] > time.time():
            l.append(E("MenuItem", "Coller", (20, 98, 73, 44)))
        if e.get("focus") == "ig_recherche":
            l += [E("Button", "Effacer le texte", (283, 63, 20, 19)), E("Button", "Annuler", (321, 56, 56, 32), "search-bar-cancel-button")]
        return l + ig_onglets()
    return []


def panneau_comptes(e):
    """(haut du panneau, [centre de chaque ligne de compte], centre de « Ajouter un compte »), en points."""
    n = len(e["tt_comptes"])
    haut = 750 - 76 * n - 90
    return haut, [haut + 90 + 76 * i for i in range(n)], 750


def toucher_panneau(e, y):
    haut, lignes, ajout = panneau_comptes(e)
    e["journal"].append(f"tt_comptes:toucher {y:.0f}")
    if abs(y - ajout) < 38:
        e["tt_ajout_touche"] = True          # la connexion d'un compte : la recette ne doit jamais y aller
        e["ecran"] = "tt_profil"
        return
    for i, c in enumerate(lignes):
        if abs(y - c) < 38 and e["tt_comptes"][i] != e["tt_actif"]:
            e["tt_bascule"] = {"compte": e["tt_comptes"][i], "a": time.time() + 6}   # « chargement… » 6 s, comme le vrai
            break
    e["ecran"] = "tt_profil"                 # une ligne touchée, ou à côté : le panneau se ferme


def poster_tiktok(e):
    vid = str(7_000_000 + len(e["journal"]))
    e["tt_videos"].setdefault(e["tt_actif"], []).insert(0, vid)
    e["tt_posts"].append({"compte": e["tt_actif"], "id": vid, "desc": e["tt_desc"], "t": int(time.time())})
    e["dernier_post"] = {"compte": e["tt_actif"], "desc": e["tt_desc"], "photo": e["selection"], "son": e.get("tt_son")}
    e["ecran"], e["envoi_jusqua"], e["selection"], e["tt_choisies"] = "tt_fil", time.time() + 3, None, []


def cliquer(e, el):
    typ, label, name = el[0], el[1], el[3]
    ec = e["ecran"]
    e["journal"].append(f"{ec}:{label if label is not None else name}")
    nom = name or label
    # TikTok
    if ec == "tt_intrus" and label == "J'ai compris":
        e["ecran"] = "tt_fil"
    elif ec in ("tt_fil", "tt_profil") and label == "Profil":
        e["ecran"], e["tt_profil_charge_jusqua"] = "tt_profil", time.time() + 4
    elif ec in ("tt_fil", "tt_profil") and label == "Créer":
        e["ecran"] = "tt_creation"
        if not e["tt_camera_vue"]:
            e["tt_camera_vue"], e["alertes"] = True, ["camera", "micro"]
    elif ec in ("tt_fil", "tt_profil") and label == "Accueil":
        e["ecran"] = "tt_fil"
    elif ec == "tt_fil" and label == "Rechercher":
        e["ecran"], e["focus"], e["tt_q"] = "tt_recherche", "tt_q", ""
    elif ec == "tt_fil" and label == "LIVE":
        e["ecran"] = "tt_live"
        e["journal"].append("piège:LIVE ouvert")
    elif ec == "tt_pop" and label == "Pas maintenant":
        e["ecran"] = "tt_fil"
    elif ec == "tt_recherche" and typ == "SearchField":
        e["focus"] = "tt_q"
    elif ec == "tt_recherche" and label == "Retour":
        e["ecran"], e["focus"] = "tt_fil", None
    elif ec == "tt_recherche" and label == "Rechercher" and e["tt_q"].strip():
        e["ecran"], e["focus"], e["tt_onglet_r"] = "tt_resultats", None, "Top"
        e["tt_recherches"].append(e["tt_q"].strip())
    elif ec == "tt_resultats" and label in ("Top", "Vidéos"):
        e["tt_onglet_r"] = label
    elif ec == "tt_resultats" and label == "Retour":
        e["ecran"], e["focus"] = "tt_recherche", None
    elif ec == "tt_resultats" and typ == "Other" and label:
        case = next((c for c, l, _ in tt_cases_resultats(e) if l == label), None)
        if case == "pub":
            e["ecran"] = "tt_pub"
            e["journal"].append("piège:publicité ouverte")
        elif case is not None:
            e["ecran"], e["tt_lecture"] = "tt_video", case
    elif ec == "tt_video" and label == "returnButton":
        e["ecran"] = "tt_resultats"
    elif ec in ("tt_live", "tt_pub", "tt_autre_profil") and label == "Fermer":
        e["ecran"] = "tt_fil"
    elif ec == "tt_profil" and label == "Changer de compte" and not e.get("tt_bascule") \
            and e.get("tt_profil_charge_jusqua", 0) <= time.time():        # en plein chargement : la flèche ne répond pas
        e["ecran"] = "tt_comptes"
    elif ec == "tt_profil" and typ == "Cell":
        e["ecran"] = "tt_video"
    elif ec == "tt_creation" and nom == "recordPageUploadButton":
        if e["tt_photos_ok"]:
            e["ecran"], e["tt_defile"] = "tt_galerie", False
        else:
            e["alertes"] = ["photos"]
    elif ec == "tt_creation" and label == "Fermer":
        e["ecran"] = "tt_fil"
    elif ec == "tt_galerie" and label in ("Tous", "Vidéos"):
        e["tt_filtre"] = label
    elif ec == "tt_galerie" and label == "icDeleteAssetOptimize":
        e["tt_choisies"] = []
    elif ec == "tt_galerie" and label == "Retour":
        e["ecran"] = "tt_creation"
    elif ec == "tt_galerie" and label == "Suivant" and e["tt_choisies"]:
        e["ecran"], e["selection"], e["tt_son"] = "tt_editeur", e["tt_choisies"][-1], "Midnight Without Footsteps"   # TikTok pose un son
    elif ec == "tt_editeur" and nom == "(editPageNextButton)":
        e["ecran"], e["tt_desc"] = "tt_poster", ""
    elif ec == "tt_editeur" and nom == "(editPageBackButton)":
        e["ecran"] = "tt_galerie"
        e["tt_brouillons"][e["tt_actif"]] = e["tt_brouillons"].get(e["tt_actif"], 0) + 1   # TikTok garde un brouillon
    elif ec == "tt_poster" and typ == "TextView":
        e["focus"] = "tt_desc"
    elif ec == "tt_poster" and nom == "(publishPageBackButton)":
        e["ecran"], e["focus"] = "tt_editeur", None
    elif ec == "tt_poster" and label == "Brouillons":
        e["tt_brouillons"][e["tt_actif"]] = e["tt_brouillons"].get(e["tt_actif"], 0) + 1
        e["ecran"] = "tt_profil"
    elif ec == "tt_poster" and label == "Publier":
        poster_tiktok(e)
    elif ec == "tt_video" and label == "Partager":
        e["ecran"] = "tt_partage"
    # Instagram
    elif ec in ("ig_fil", "ig_profil", "ig_reels", "ig_explorer") and nom == "profile-tab":
        e["ecran"], e["focus"] = "ig_profil", None
    elif ec in ("ig_fil", "ig_profil", "ig_reels", "ig_resultats", "ig_lecteur", "ig_explorer") and nom == "explore-tab":
        e["ecran"], e["ig_recherche"], e["focus"] = "ig_explorer", "", None
    elif ec in ("ig_fil", "ig_profil", "ig_reels", "ig_resultats", "ig_lecteur", "ig_explorer") and nom == "reels-tab":
        e["ecran"], e["ig_lecture"], e["focus"] = "ig_lecteur", {"source": "reels", "i": 0}, None
    elif ec == "ig_resultats" and nom == "BackButton":
        e["ecran"] = "ig_explorer"
    elif ec == "ig_resultats" and label == "Vidéo de vinted":
        e["ecran"] = "ig_profil_autre"
        e["journal"].append("piège:carrousel d'un compte ouvert depuis les résultats")
    elif ec == "ig_resultats" and typ == "Cell" and label and label.startswith("Vidéo de "):
        e["ecran"], e["ig_lecture"] = "ig_lecteur", {"source": "recherche", "i": 0 if label.endswith(niche(0)["auteur"]) else 1}
    elif ec == "ig_resultats" and typ == "Cell":
        e["ecran"] = "ig_profil_autre"
        e["journal"].append("piège:profil ouvert depuis les résultats")
    elif ec == "ig_lecteur" and nom == "back-button":
        e["ecran"] = "ig_resultats"
    elif ec == "ig_lecteur" and nom == "like-button":
        r = ig_reel(e)
        if r["id"] in e["ig_aimes"]:
            e["ig_aimes"].remove(r["id"])
            e["ig_unlike"] = True
        else:
            e["ig_aimes"].append(r["id"])
            if r["pub"]:
                e["journal"].append("piège:publicité likée")
    elif ec == "ig_lecteur" and nom == "follow-button":
        e["ig_suivis"].append(ig_reel(e)["auteur"])
    elif ec == "ig_profil" and nom == "user-switch-title-button":
        e["ecran"] = "ig_comptes"
    elif ec == "ig_profil" and nom == "profile-add-button":
        e["ecran"] = "ig_creer"
    elif ec == "ig_profil" and typ == "Cell" and label == "Reels":
        e["ecran"] = "ig_reels"
    elif ec == "ig_comptes" and label == "Ajouter un compte Instagram":
        e["ig_ajout_touche"], e["ecran"] = True, "ig_profil"
    elif ec == "ig_comptes" and label and label.startswith("Profil INSTAGRAM, "):
        e["ig_actif"], e["ecran"] = label.split(", ")[1], "ig_profil"
    elif ec == "ig_creer" and nom == "creation-reel":
        e["ecran"], e["ig_choisies"] = "ig_galerie", []
    elif ec == "ig_galerie" and e.get("ig_brouillon_coupe"):     # la question bloque tout le reste
        if label == "Commencer une nouvelle vidéo":
            e["ig_brouillon_coupe"] = False
        elif label == "Continuer":
            e["ig_continuer_touche"] = True
    elif ec == "ig_galerie" and nom == "gallery-close-button":
        e["ecran"] = "ig_profil"
    elif ec == "ig_galerie" and nom and nom.startswith("gallery-video-cell-"):
        v = list(reversed(videos(e)))[int(nom.rsplit("-", 1)[1])]["nom"]
        if e["ig_multi"].get(e["ig_actif"], False):
            e["ig_choisies"] = [x for x in e["ig_choisies"] if x != v] if v in e["ig_choisies"] else e["ig_choisies"] + [v]
        else:
            e["ecran"], e["ig_selection"] = "ig_editeur", v
    elif ec == "ig_galerie" and nom == "reels-gallery-selection-next" and len(e["ig_choisies"]) == 1:
        e["ecran"], e["ig_selection"] = "ig_editeur", e["ig_choisies"][0]
    elif ec == "ig_editeur" and nom == "sundial-postcapture-suggestion-pill":
        e["ig_audio_touche"] = True
    elif ec == "ig_editeur" and nom == "discard-reel-preview":
        e["ecran"] = "ig_abandon"
    elif ec == "ig_editeur" and nom == "sundial-right-chevron-suivant-button" and not e.get("ig_promo_vue"):
        e["ig_promo_vue"], e["ecran"] = True, "ig_promo"       # la pub Edits arrive, le « Suivant » n'est pas passé
    elif ec == "ig_promo" and label == "Fermer":
        e["ecran"] = "ig_editeur"
    elif ec == "ig_promo" and label in ("Obtenir", "Télécharger sur l’App\xa0Store"):
        e["ig_appstore_touche"] = True
    elif ec == "ig_editeur" and nom == "sundial-right-chevron-suivant-button":
        e["ecran"], e["ig_desc"] = "ig_final", ""
    elif ec == "ig_abandon" and nom == "camera-discard-draft":
        e["ecran"], e["ig_choisies"], e["ig_selection"] = "ig_galerie", [], None
    elif ec == "ig_abandon" and nom == "camera-save-draft":
        e["ig_brouillons"] += 1
        e["ecran"] = "ig_galerie"
    elif ec == "ig_final" and typ == "TextView":
        e["ecran"], e["focus"] = "ig_legende", "ig_desc"
    elif ec == "ig_final" and nom == "BackButton":
        e["ecran"] = "ig_editeur"
    elif ec == "ig_final" and nom == "save-draft-button":
        e["ig_brouillons"] += 1
    elif ec == "ig_final" and nom == "share-sheet-share-button" and not e.get("ig_apropos_vu", {}).get(e["ig_actif"]):
        e.setdefault("ig_apropos_vu", {})[e["ig_actif"]] = True
        e["ecran"] = "ig_apropos"
    elif ec == "ig_apropos" and label == "Annuler":
        e["ecran"] = "ig_final"
    elif (ec == "ig_final" and nom == "share-sheet-share-button") or (ec == "ig_apropos" and label == "Partager"):
        # l'envoi prend 6 s et ne finit que si Instagram reste à l'écran (vu le 05/10/2026)
        e["ig_envoi"] = {"compte": e["ig_actif"], "desc": e["ig_desc"], "video": e["ig_selection"], "fin": time.time() + 6, "etat": "en_cours"}
        e["ecran"], e["ig_selection"], e["ig_choisies"] = "ig_fil", None, []
    elif ec == "ig_fil" and label == "ig icon arrow cw outline 16" and (e.get("ig_envoi") or {}).get("etat") == "erreur":
        e["ig_envoi"].update(etat="en_cours", fin=time.time() + 6)
    elif ec == "ig_legende" and label == "OK":
        e["ecran"], e["focus"] = "ig_final", None
    elif ec == "ig_legende" and typ == "TextView":
        e["focus"] = "ig_desc"
    elif ec == "ig_reels" and nom == "reels-video-thumbnail":
        cases = [x for x in elements(e) if x[3] == "reels-video-thumbnail"]
        i = next(k for k, x in enumerate(cases) if x[2] == el[2])
        e["ig_ouvert"] = "EPINGLE" if i == 0 else e["ig_pubs"][e["ig_actif"]][i - 1]["id"]
        e["ecran"] = "ig_reel"
    elif ec == "ig_reel" and nom == "like-button":
        e["ig_like_touche"] = True
    elif ec == "ig_reel" and nom == "send-button":
        e["ecran"] = "ig_envoi"
    elif ec == "ig_reel" and nom == "back-button":
        e["ecran"] = "ig_profil"
    elif ec == "ig_envoi" and label == "Copier le lien":
        e["presse_papiers"] = f"https://www.instagram.com/reel/{e['ig_ouvert']}/?igsh=ZmF1eA=="
    elif ec == "ig_envoi" and label == "Un ami":
        e["ig_contact_touche"] = True
    elif ec == "ig_explorer" and typ == "SearchField":
        e["focus"] = "ig_recherche"
    elif ec == "ig_explorer" and label == "Coller":
        e["ig_recherche"], e["menu_coller_jusqua"] = e["presse_papiers"], 0
    elif ec == "ig_explorer" and label == "Effacer le texte":
        e["ig_recherche"] = ""
    elif ec == "ig_explorer" and nom == "search-bar-cancel-button":
        e["focus"] = None


def toucher_galerie_tt(e, x, y):
    """Le rond (en haut à droite d'une case) choisit ou retire la vidéo ; ailleurs, la case ouvre un aperçu."""
    if e["tt_filtre"] != "Vidéos":
        return False
    for nom, (cx, cy, cw, ch) in tt_cases(e):
        if cx <= x <= cx + cw and cy <= y <= cy + ch:
            if x >= cx + cw - 36 and y <= cy + 36:
                e["tt_choisies"] = [v for v in e["tt_choisies"] if v != nom] if nom in e["tt_choisies"] else e["tt_choisies"] + [nom]
                e["journal"].append(f"tt_galerie:rond {nom}")
            else:
                e["journal"].append(f"tt_galerie:aperçu {nom}")
            return True
    return False


def dessiner(e, fmt="JPEG", echelle=1.0):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (int(W * echelle), int(H * echelle)), (18, 18, 22))
    d = ImageDraw.Draw(im)
    s = echelle
    d.text((12 * s, 12 * s), f"faux iPhone · {e['ecran']} · {time.strftime('%H:%M:%S')}", fill=(255, 255, 255))
    for typ, label, (x, y, w, h), *_ in elements(e):
        d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], outline=(100, 210, 255))
        d.text(((x + 4) * s, (y + 4) * s), f"{typ} {label}"[:40], fill=(230, 230, 230))
    if e["ecran"] == "tt_comptes":
        haut, lignes, ajout = panneau_comptes(e)
        d.rectangle([0, haut * s, W * s, H * s], fill=(255, 255, 255))
        d.text((150 * s, (haut + 20) * s), "Changer de compte", fill=(0, 0, 0))
        for c in lignes:
            d.ellipse([16 * s, (c - 28) * s, 72 * s, (c + 28) * s], fill=(190, 120, 60))
        d.ellipse([16 * s, (ajout - 28) * s, 72 * s, (ajout + 28) * s], fill=(235, 235, 235))
    if e["ecran"] == "tt_poster" and e.get("focus") == "tt_desc":
        d.rounded_rectangle([300 * s, 54 * s, 374 * s, 84 * s], radius=14 * s, fill=(254, 44, 85))   # la pastille « Publier »
        d.text((314 * s, 62 * s), "Publier", fill=(255, 255, 255))
    if e["ecran"] == "tt_video":            # la colonne de droite : photo du compte, « + » rouge, cœur, commentaires
        v = niche(e["tt_lecture"])
        d.ellipse([336 * s, 328 * s, 380 * s, 372 * s], fill=(120, 140, 170))
        if v["auteur"] not in e["tt_suivis"]:
            d.ellipse([348 * s, 362 * s, 368 * s, 382 * s], fill=(254, 44, 85))
            d.line([(353 * s, 372 * s), (363 * s, 372 * s)], fill=(255, 255, 255), width=max(1, int(2 * s)))
            d.line([(358 * s, 367 * s), (358 * s, 377 * s)], fill=(255, 255, 255), width=max(1, int(2 * s)))
        coeur = (254, 44, 85) if v["id"] in e["tt_aimes"] else (245, 245, 245)
        d.ellipse([343 * s, 404 * s, 359 * s, 420 * s], fill=coeur)
        d.ellipse([357 * s, 404 * s, 373 * s, 420 * s], fill=coeur)
        d.polygon([(343 * s, 413 * s), (373 * s, 413 * s), (358 * s, 434 * s)], fill=coeur)
        d.ellipse([344 * s, 475 * s, 372 * s, 499 * s], fill=(240, 240, 240))                  # commentaires
        d.rectangle([349 * s, 540 * s, 367 * s, 566 * s], fill=(240, 240, 240))                # favoris
        d.polygon([(346 * s, 625 * s), (370 * s, 614 * s), (346 * s, 603 * s)], fill=(240, 240, 240))   # partage
        if e.get("tt_coeur_anim", 0) > time.time():          # le gros cœur rouge du double-toucher, au milieu
            x, y = e["tt_coeur_xy"]
            d.ellipse([(x - 40) * s, (y - 40) * s, (x + 40) * s, (y + 40) * s], fill=(254, 44, 85))
    if e.get("alertes"):
        d.rectangle([40 * s, 330 * s, 350 * s, 470 * s], fill=(60, 60, 66))
        d.text((52 * s, 350 * s), ALERTES[e["alertes"][0]][0], fill=(255, 255, 255))
    out = io.BytesIO()
    im.save(out, fmt, quality=60) if fmt == "JPEG" else im.save(out, fmt)
    return out.getvalue()


# ── le faux WebDriverAgent ────────────────────────────────────────────────────────────────────────────
def predicat(pred, el):
    """Un mini NSPredicate, juste ce qu'emploient les recettes : ==, !=, <, >, <=, >=, CONTAINS, CONTAINS[c],
    BEGINSWITH, ENDSWITH, IN {…}, AND, OR, parenthèses ; label, name, value, type, hittable, rect.x/y/width/height."""
    jetons = re.findall(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|==|!=|<=|>=|CONTAINS\[c\]|[(){}<>,]|[\w.]+', pred)
    pos = [0]

    def voir():
        return jetons[pos[0]] if pos[0] < len(jetons) else None

    def prendre():
        pos[0] += 1
        return jetons[pos[0] - 1]

    def valeur(t):
        if t[0] in "\"'":
            return re.sub(r"\\(.)", r"\1", t[1:-1])
        try:
            return float(t)
        except ValueError:
            return t

    def attribut(a):
        t, label, (x, y, w, h), name, value, touchable = el
        return {"label": label, "name": name if name is not None else label, "value": value, "type": "XCUIElementType" + t,
                "hittable": 1.0 if touchable else 0.0, "rect.x": x, "rect.y": y, "rect.width": w, "rect.height": h}.get(a)

    def comparaison():
        a, op = prendre(), prendre()
        v = attribut(a)
        if op == "IN":
            prendre()
            vals = []
            while voir() != "}":
                t = prendre()
                if t != ",":
                    vals.append(valeur(t))
            prendre()
            return v in vals
        b = valeur(prendre())
        if op == "==":
            return v == b
        if op == "!=":
            return v != b
        if v is None:
            return False
        if op in ("<", ">", "<=", ">="):
            return {"<": v < b, ">": v > b, "<=": v <= b, ">=": v >= b}[op]
        v, b = str(v), str(b)
        return {"CONTAINS[c]": b.lower() in v.lower(), "CONTAINS": b in v, "BEGINSWITH": v.startswith(b), "ENDSWITH": v.endswith(b)}[op]

    def facteur():
        if voir() == "(":
            prendre()
            r = expression()
            prendre()
            return r
        return comparaison()

    def terme():
        r = facteur()
        while voir() == "AND":
            prendre()
            f = facteur()
            r = r and f
        return r

    def expression():
        r = terme()
        while voir() == "OR":
            prendre()
            t = terme()
            r = r or t
        return r

    return bool(expression())


async def servir_wda(port):
    from aiohttp import web

    def rep(v=None, status=200, sid="S1"):
        return web.json_response({"value": v, "sessionId": sid}, status=status)

    def err(code, erreur, message=""):
        return web.json_response({"value": {"error": erreur, "message": message}}, status=code)

    def ident(e, i):
        return f"{e['ecran']}-{i}"

    def trouve(e, eid):
        ec, _, i = eid.rpartition("-")
        els = elements(e)
        return els[int(i)] if ec == e["ecran"] and i.isdigit() and int(i) < len(els) else None

    async def gerer(req):
        chemin = re.sub(r"^/session/[^/]+", "", req.path)
        corps = await req.json() if req.can_read_body else {}
        e = lire()
        if e.get("tt_bascule") and time.time() >= e["tt_bascule"]["a"]:     # le changement de compte de TikTok aboutit
            e["tt_actif"], e["tt_bascule"] = e["tt_bascule"]["compte"], None
            ecrire(e)
        envoi = e.get("ig_envoi")
        if envoi and envoi["etat"] == "en_cours":
            if not e["ecran"].startswith("ig_"):                  # Instagram quitté avant la fin : l'envoi se bloque
                envoi["etat"] = "bloque"
                e["journal"].append("ig_envoi:bloqué (Instagram quitté)")
            elif time.time() >= envoi["fin"]:                      # au premier plan jusqu'au bout : la vidéo est en ligne
                code = f"FAUX{len(e['journal'])}"
                e["ig_pubs"].setdefault(envoi["compte"], []).insert(0, {"id": code, "desc": envoi["desc"], "video": envoi["video"], "t": int(time.time())})
                e["ig_dernier_post"] = {"compte": envoi["compte"], "desc": envoi["desc"], "video": envoi["video"]}
                e["ig_envoi"] = None
                e["journal"].append("ig_envoi:fini")
            ecrire(e)
        elif envoi and envoi["etat"] == "bloque" and e["ecran"].startswith("ig_"):   # revenu sur Instagram : l'erreur
            envoi["etat"] = "erreur"
            ecrire(e)
        m = req.method
        # les gestes faits sur un élément (la fenêtre de l'app) : comme les mêmes gestes à l'écran ; sur le fil et les
        # vidéos de TikTok, un geste aux coordonnées de l'écran dure plus de 2 min sur le vrai iPhone (07/10/2026) : piège
        sur_elt = re.fullmatch(r"/wda/element/([^/]+)/(swipe|tap|doubleTap)", chemin)
        if sur_elt:
            chemin = {"swipe": "/actions", "tap": "/wda/tap", "doubleTap": "/wda/doubleTap"}[sur_elt.group(2)]
            if sur_elt.group(2) == "doubleTap":
                corps = {"x": W / 2, "y": H / 2}
        elif chemin in ("/actions", "/wda/tap", "/wda/doubleTap") and e["ecran"] in ("tt_fil", "tt_video"):
            e["journal"].append(f"piège:geste {chemin} aux coordonnées sur {e['ecran']} (plus de 2 min sur le vrai TikTok)")
            ecrire(e)
        try:
            if req.path == "/status":
                return rep({"ready": True, "ios": {"ip": "192.168.1.77" if e.get("wifi", True) else None}, "build": {"version": "faux"}})
            if req.path == "/session" and m == "POST":
                return rep({"sessionId": "S1", "capabilities": {}})
            if chemin == "/wda/screen":
                return rep({"screenSize": {"width": W, "height": H}, "statusBarSize": {"width": W, "height": 47}, "scale": 3})
            if chemin == "/screenshot":
                return rep(base64.b64encode(dessiner(e, "PNG")).decode())
            if chemin == "/source":
                return rep({"type": "Application", "label": "faux", "rect": {"x": 0, "y": 0, "width": W, "height": H},
                            "children": [{"type": t, "label": l, "name": n if n is not None else l, "value": v, "isEnabled": True,
                                          "rect": {"x": x, "y": y, "width": w, "height": h}, "children": []}
                                         for t, l, (x, y, w, h), n, v, _ in elements(e)]})
            if chemin == "/appium/settings":
                if "snapshotMaxDepth" in corps.get("settings", {}):
                    e.setdefault("profondeurs", []).append(corps["settings"]["snapshotMaxDepth"])
                    ecrire(e)
                return rep(None)
            if chemin in ("/wda/pressButton", "/wda/unlock", "/wda/keyboard/dismiss", "/timeouts"):
                return rep(None)
            if chemin == "/actions":                         # un glissement : la galerie de TikTok descend, une vidéo passe
                if e["ecran"] == "tt_galerie":
                    e["tt_defile"] = True
                elif e["ecran"] == "tt_video":
                    e["tt_lecture"] += 1
                    e["tt_vues_niche"] += 1
                elif e["ecran"] == "tt_fil":
                    e["tt_fil_vues"] += 1
                    if e["tt_fil_vues"] == 3 and not e["tt_pop_vue"]:       # une fenêtre glissée par TikTok
                        e["ecran"], e["tt_pop_vue"] = "tt_pop", True
                elif e["ecran"] == "ig_lecteur":
                    e["ig_lecture"]["i"] += 1
                    e["ig_vues"] += 1
                ecrire(e)
                return rep(None)
            if chemin == "/wda/batteryInfo":
                return rep({"level": 0.87, "state": 2})
            if chemin == "/wda/locked":
                return rep(False)
            if chemin == "/wda/activeAppInfo":
                ec = e["ecran"]
                b = TIKTOK if ec.startswith("tt_") else INSTAGRAM if ec.startswith("ig_") else \
                    {"photos": "com.apple.mobileslideshow", "raccourcis": "com.apple.shortcuts"}.get(ec, "com.apple.springboard")
                return rep({"bundleId": b, "name": ec, "pid": 1})
            if chemin == "/wda/homescreen":
                e["ecran"] = "accueil"
            elif chemin == "/wda/apps/launch":
                b = corps["bundleId"]
                if b == TIKTOK:
                    e["ecran"] = "tt_intrus" if e["tt_lancements"] == 0 else "tt_fil"
                    e["tt_lancements"] += 1
                elif b == INSTAGRAM:
                    e["ecran"] = "ig_fil"
                elif b == "com.apple.shortcuts":
                    e["ecran"] = "raccourcis"
            elif chemin == "/wda/apps/terminate":
                if (corps["bundleId"] == TIKTOK and e["ecran"].startswith("tt_")) or (corps["bundleId"] == INSTAGRAM and e["ecran"].startswith("ig_")):
                    e["ecran"], e["focus"] = "accueil", None
                ecrire(e)
                return rep(True)
            elif chemin == "/url":
                u = urlparse(corps["url"])
                if u.scheme == "shortcuts":
                    q = parse_qs(u.query)
                    nom = q["text"][0]
                    e["ecran"] = "raccourcis"
                    ecrire(e)
                    await asyncio.sleep(1)            # le Raccourci range la vidéo dans Photos
                    f = app_dir(VLC) / "Documents" / "import" / nom
                    e = lire()
                    if f.exists():
                        e["photos"].append(nom)
                        dcim = DIR / "media" / "DCIM" / "100APPLE"   # la vraie preuve : une vidéo de plus dans la pellicule
                        dcim.mkdir(parents=True, exist_ok=True)
                        (dcim / f"IMG_{len(e['photos']):04d}.MP4").write_bytes(b"video")
                        if e.get("raccourci_efface"):  # première version : il efface lui-même la copie de VLC
                            f.unlink()             # (et, comme le vrai iPhone du 02/10, Raccourcis n'ouvre pas Photos)
            elif chemin == "/wda/keys":
                texte, champ = "".join(corps["value"]), e.get("focus")
                if champ in ("tt_q", "ig_recherche") and "\n" in texte:     # Entrée : la recherche part
                    e[champ] = (e.get(champ) or "") + texte.split("\n")[0]
                    if champ == "tt_q" and e["tt_q"].strip():
                        e["ecran"], e["tt_onglet_r"] = "tt_resultats", "Top"
                        e["tt_recherches"].append(e["tt_q"].strip())
                    elif champ == "ig_recherche" and e["ig_recherche"].strip() and e["ecran"] == "ig_explorer":
                        e["ecran"] = "ig_resultats"
                        e["ig_recherches"].append(e["ig_recherche"].strip())
                    e["focus"] = None
                elif champ in ("tt_desc", "ig_desc", "ig_recherche", "tt_q"):
                    e[champ] = (e.get(champ) or "") + texte
            elif chemin == "/wda/doubleTap":                   # deux touchers : le like de TikTok
                e["journal"].append(f"{e['ecran']}:double")
                if e["ecran"] == "tt_video":
                    v = niche(e["tt_lecture"])["id"]
                    if v not in e["tt_aimes"]:
                        e["tt_aimes"].append(v)
                    e["tt_coeur_anim"], e["tt_coeur_xy"] = time.time() + 1.0, [corps["x"], corps["y"]]
                elif e["ecran"] == "tt_fil":
                    e["tt_fil_likes"] += 1
            elif chemin == "/wda/touchAndHold":
                if e["ecran"] in ("tt_poster", "ig_explorer"):
                    e["menu_coller_jusqua"] = time.time() + 5
            elif chemin == "/wda/tap" and e["ecran"] == "tt_video" and corps["x"] > 330:     # la colonne de droite (hors de l'arbre)
                x, y, v = corps["x"], corps["y"], niche(e["tt_lecture"])
                if abs(x - 358) <= 12 and abs(y - 372) <= 12 and v["auteur"] not in e["tt_suivis"]:
                    e["tt_suivis"].append(v["auteur"])
                elif abs(x - 358) <= 18 and abs(y - 420) <= 18:
                    e["journal"].append("piège:cœur touché")
                    e["tt_aimes"] = [i for i in e["tt_aimes"] if i != v["id"]] if v["id"] in e["tt_aimes"] else e["tt_aimes"] + [v["id"]]
                elif abs(x - 358) <= 24 and abs(y - 350) <= 24:
                    e["ecran"] = "tt_autre_profil"
                    e["journal"].append("piège:profil ouvert")
                else:
                    e["journal"].append(f"tt_video:colonne {x:.0f},{y:.0f}")
            elif chemin == "/wda/tap" and e["ecran"] == "tt_comptes":
                toucher_panneau(e, corps["y"])
            elif chemin == "/wda/tap" and e["ecran"] == "ig_envoi" and corps["y"] < 400:
                e["ecran"] = "ig_reel"                                     # au-dessus du panneau d'envoi : il se ferme
            elif chemin == "/wda/tap" and e["ecran"] == "tt_galerie" and toucher_galerie_tt(e, corps["x"], corps["y"]):
                pass
            elif chemin == "/wda/tap" and e["ecran"] == "tt_poster" and e.get("focus") == "tt_desc" \
                    and 300 <= corps["x"] <= 374 and 54 <= corps["y"] <= 84:
                e["journal"].append("tt_poster:pastille Publier")
                poster_tiktok(e)
                e["focus"] = None
            elif chemin == "/wda/tap" and e["ecran"] == "tt_editeur" and corps["y"] < 120 and e.get("tt_son") and corps["x"] > 101 + 188 - 36:
                e["journal"].append(f"tt_editeur:son retiré ({e['tt_son']})")   # la croix de la pastille du son
                e["tt_son"] = None
            elif chemin == "/wda/tap":
                x, y = corps["x"], corps["y"]
                for el in elements(e):
                    bx, by, bw, bh = el[2]
                    if el[5] and bx <= x <= bx + bw and by <= y <= by + bh:
                        cliquer(e, el)
                        break
            elif chemin == "/elements":
                if corps["using"] == "class name" and corps["value"] == "XCUIElementTypeWindow":
                    ids = ["fenetre"]                          # la fenêtre de l'app : les gestes sur un fil vidéo passent par elle
                elif corps["using"] == "class name":
                    t = corps["value"].replace("XCUIElementType", "")
                    ids = [ident(e, i) for i, el in enumerate(elements(e)) if el[0] == t]
                else:
                    ids = [ident(e, i) for i, el in enumerate(elements(e)) if predicat(corps["value"], el)]
                return rep([{"ELEMENT": i} for i in ids])
            elif re.fullmatch(r"/element/[^/]+/attribute/(label|name|value|hittable)", chemin):
                el = trouve(e, chemin.split("/")[2])
                if not el:
                    return err(404, "stale element reference", chemin)
                quoi = chemin.rsplit("/", 1)[1]
                return rep({"label": el[1], "name": el[3] if el[3] is not None else el[1], "value": el[4], "hittable": el[5]}[quoi])
            elif re.fullmatch(r"/element/[^/]+/(rect|click|text)", chemin):
                eid, action = chemin.split("/")[2], chemin.split("/")[3]
                el = trouve(e, eid)
                if not el:
                    return err(404, "stale element reference", eid)
                if action == "rect":
                    x, y, w, h = el[2]
                    return rep({"x": x, "y": y, "width": w, "height": h})
                if action == "text":
                    return rep(el[1])
                cliquer(e, el)
            elif chemin == "/alert/text":
                return rep(ALERTES[e["alertes"][0]][0]) if e.get("alertes") else err(404, "no such alert")
            elif chemin == "/wda/alert/buttons":
                return rep(ALERTES[e["alertes"][0]][1] if e.get("alertes") else [])
            elif chemin in ("/alert/accept", "/alert/dismiss"):
                if not e.get("alertes"):
                    return err(404, "no such alert")
                quelle, bouton = e["alertes"].pop(0), corps.get("name")
                e["journal"].append(f"alerte {quelle} : {bouton} ({'acceptée' if chemin.endswith('accept') else 'refusée'})")
                if quelle == "photos" and chemin.endswith("accept"):
                    if bouton == "Autoriser l’accès complet":
                        e["tt_photos_ok"], e["ecran"], e["tt_defile"] = True, "tt_galerie", False
                    else:
                        e["tt_photos_limite"] = True
                elif quelle in ("camera", "micro") and chemin.endswith("accept"):
                    e["tt_camera_accordee"] = True
            else:
                return err(404, "unknown command", f"{m} {req.path}")
            ecrire(e)
            return rep(None)
        except Exception as x:
            return err(500, "unknown error", repr(x))

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", gerer)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    dire("faux WebDriverAgent prêt", port=port)
    await asyncio.Event().wait()


async def servir_flux(port):
    from aiohttp import web

    async def flux(req):
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "multipart/x-mixed-replace; boundary=--BoundaryString"
        await resp.prepare(req)
        try:
            while True:
                jpg = dessiner(lire(), "JPEG", 0.5)
                await resp.write(b"--BoundaryString\r\nContent-type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n\r\n")
                await asyncio.sleep(0.25)
        except (ConnectionResetError, RuntimeError):
            pass
        return resp

    app = web.Application()
    app.router.add_get("/{tail:.*}", flux)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    await asyncio.Event().wait()


def pmd3(argv):
    """Le faux pymobiledevice3 : `mounter mount-personalized … <dmg> <trustcache> <manifeste>` et
    `provision dump --udid U <dossier>` (le profil de 7 jours qu'Impactor aurait installé)."""
    if argv[:2] == ["provision", "dump"]:
        import datetime as dt
        import plistlib
        maintenant = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
        plist = plistlib.dumps({"Name": "iOS Team Provisioning Profile: " + WDA_BUNDLE, "UUID": "FAUX-PROFIL-0001",
                                "TeamIdentifier": ["TEAMFAUX"], "CreationDate": maintenant,
                                "ExpirationDate": maintenant + dt.timedelta(days=7),
                                "Entitlements": {"application-identifier": "TEAMFAUX." + WDA_BUNDLE, "get-task-allow": True}})
        (Path(argv[-1]) / "FAUX-PROFIL-0001.mobileprovision").write_bytes(b"0\x82\x10CMS" + plist + b"\x00signature")
        print("INFO downloading FAUX-PROFIL-0001.mobileprovision")
        return 0
    if argv[:2] == ["mounter", "mount-personalized"] and all(Path(f).exists() for f in argv[-3:]):
        e = lire()
        e["image"], e["image_par"] = True, "pymobiledevice3"
        ecrire(e)
        print("INFO Sending TSS request...\nINFO Personalized image mounted successfully")
        return 0
    print(f"faux pymobiledevice3 : commande inconnue {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if sys.argv[1:2] == ["--pmd3"]:
        sys.exit(pmd3(sys.argv[2:]))
    if sys.argv[1:2] == ["--reinitialiser"]:
        ecrire(etat_initial())
        sys.exit(0)
    sys.exit(goios(sys.argv[1:]))
