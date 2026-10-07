"""recettes/tiktok.py : publier une vidéo sur TikTok depuis l'iPhone.

Calée le 04/10/2026 sur le vrai iPhone (TikTok en français, iOS 26.5), en répétition jusqu'à l'écran « Publier ».
Ce qui suit le dernier bouton n'a pas encore été vu en vrai : la première vraie publication le calera, captures à
l'appui. Le lien de la vidéo ne se lit pas à l'écran (l'écran de lecture d'une vidéo est trop lourd pour l'agent :
aucun bouton lisible, même en 60 s) : il est retrouvé à part, par Scrape Creators (liens.py), pendant que le
téléphone passe à la suite."""
import asyncio
import io
import random
import time

from recettes.base import ErreurPublication

BUNDLE = "com.zhiliaoapp.musically"
HAUT = 140          # la barre du haut de l'écran, en points
# Niveaux de l'arbre lus pour chercher un bouton (voir wda.PROFONDEUR), mesurés le 04/10/2026 : sur le fil et sur
# une vidéo ouverte, au-delà de 15 TikTok ne répond plus (65 s, rien) ; le profil se lit sur 25 niveaux en 0,6 s ;
# la création (galerie, éditeur, écran « Publier ») sur 40 en 1 à 4 s.
PROFONDEUR = 15
PROFONDEUR_PROFIL = 25
PROFONDEUR_CREATION = 40
# Les fenêtres que TikTok glisse à l'ouverture. Vu le 03/10/2026 : « Mise à jour des Règles de la communauté »,
# bouton « J'ai compris » (apostrophe droite) ; tant qu'elle est là, rien d'autre ne répond. Vu le 04/10/2026 :
# après une création coupée net, le bandeau « Continuer la modification de cette publication ? » (Enreg. brouillon /
# Modifier) couvre le haut du profil : on garde le brouillon, on ne reprend jamais la modification.
INTRUS = ("J'ai compris", "J’ai compris", "Got it", "Enreg. brouillon", "Save draft", "Pas maintenant", "Plus tard",
          "Ignorer", "Not now", "Skip", "Fermer", "Close")
DESCRIPTION = ("Ajouter une description…", "Ajouter une description...", "Add description…", "Add description...")


async def publier(r, compte, legende):
    await r.etape("Ouverture de TikTok")
    await r.a.profondeur(PROFONDEUR)
    await r.lancer_propre(BUNDLE)
    await r.alertes()
    await fermer_intrus(r)
    await choisir_compte(r, compte["identifiant"])

    await r.etape("Création : bouton +")
    await r.toucher("Créer", "Create", types=["Button"], delai=10)
    await asyncio.sleep(2)
    for _ in range(3):                           # caméra et micro : refusés (inutiles pour publier une vidéo rangée)
        if not await r.alertes():
            break
    await r.a.profondeur(PROFONDEUR_CREATION)
    await r.toucher("recordPageUploadButton", delai=10)   # « Importer », en bas à gauche
    await asyncio.sleep(2)
    await r.alertes()                            # photos : accès complet (sinon TikTok ne voit pas la vidéo)
    await choisir_video(r)

    await r.etape("Éditeur de TikTok")
    await retirer_son(r)
    await r.toucher("(editPageNextButton)", delai=15)

    await r.attendre(*DESCRIPTION, types=["TextView"], delai=20)
    if legende:
        await r.etape("Légende")
        await ecrire_legende(r, legende)
    await r.etape("Prêt à publier")
    if r.repetition:
        await abandonner(r)
        return None

    await toucher_publier(r)
    await r.a.profondeur(PROFONDEUR)             # TikTok revient sur le fil (vidéos) : lecture courte
    await asyncio.sleep(12)
    if await r.trouver(*DESCRIPTION, types=["TextView"], delai=1):
        raise ErreurPublication("toujours sur l'écran « Publier » 12 s après : un écran inattendu (voir la capture) ; "
                                "vérifie sur le compte avant de relancer")
    await r.etape("Envoyée : TikTok finit l'envoi tout seul, le téléphone passe à la suite (lien cherché à part)")
    return None


async def fermer_intrus(r):
    """Les fenêtres que TikTok glisse à l'ouverture (règles, nouveautés, amis, avis)."""
    for _ in range(3):
        if not await r.si_present(*INTRUS, delai=1.5):
            break


async def choisir_compte(r, identifiant):
    """Calé le 04/10/2026 sur le vrai iPhone. Le profil montre le compte actif : son @ exact est le label de l'élément
    « user_account_user_name ». La flèche « Changer de compte », à côté du nom, ouvre la liste des comptes connectés,
    mais cette liste n'est PAS dans l'arbre d'accessibilité (ni son titre, ni ses lignes) : on la lit sur la capture
    (lignes_comptes) et on touche les lignes une à une jusqu'à lire le bon @ sur le profil (TikTok reste sur le
    profil après le changement). La ligne « Ajouter un compte » n'est jamais touchée. Toujours le @ EXACT :
    « mapage » est contenu dans « mapage2.0 », un « contient » publierait sur le mauvais compte."""
    await r.etape(f"Compte @{identifiant}")
    await r.toucher("Profil", "Profile", types=["Button"], delai=10)
    await fermer_intrus(r)
    if not await r.trouver("nav_bar_end_settings", delai=8):          # le bouton Menu, en haut à droite du profil
        raise ErreurPublication("le profil de TikTok ne s'ouvre pas : une fenêtre de TikTok gêne ? (voir la capture)")
    await r.a.profondeur(PROFONDEUR_PROFIL)
    await fin_du_chargement(r)
    voulu = f"@{identifiant}"
    actif = await compte_actif(r)
    if actif == voulu:
        return
    essais = 0
    while True:
        lignes = await ouvrir_liste(r)
        if essais >= len(lignes):
            await r.a.toucher((r.t.taille or (390, 844))[0] / 2, 150)        # au-dessus du panneau : il se ferme
            raise ErreurPublication(f"{voulu} n'est pas parmi les {len(lignes)} compte(s) connecté(s) à TikTok sur ce "
                                    f"téléphone (compte actif : {actif or 'illisible'}) : connecte-le une fois à la main "
                                    "(Profil › flèche à côté du nom › Ajouter un compte)")
        await r.etape(f"Liste des comptes : ligne {essais + 1} sur {len(lignes)}")
        await r.a.toucher((r.t.taille or (390, 844))[0] / 2, lignes[essais])
        essais += 1
        actif = await attendre_changement(r, actif, voulu)
        if actif == voulu:
            await r.etape(f"Compte actif : {voulu}")
            return


async def fin_du_chargement(r, delai=15):
    """Le profil qui s'ouvre (ou qui change de compte) montre un rond « Chargement » en haut : tant qu'il est là, TikTok
    ignore les touchers (vu le 05/10/2026 à 17 h 58 : la flèche touchée trop tôt n'a rien ouvert)."""
    debut = time.monotonic()
    while time.monotonic() - debut < delai and await r.trouver("Chargement", "Loading", delai=0.5, contient=True):
        await asyncio.sleep(1)


async def ouvrir_liste(r, essais=3):
    """La flèche « Changer de compte », puis la liste des comptes guettée quelques secondes sur la capture ; si elle
    ne vient pas (toucher ignoré pendant un chargement), on attend la fin du chargement et on retouche."""
    for _ in range(essais):
        await fin_du_chargement(r)
        await r.toucher("Changer de compte", "Switch account", types=["Button"], delai=8)
        for _ in range(5):
            await asyncio.sleep(1)
            lignes = await lignes_comptes(r)
            if lignes:
                return lignes
    raise ErreurPublication("la liste des comptes de TikTok ne s'est pas ouverte (flèche à côté du nom, en haut du "
                            "profil) : voir la capture")


async def attendre_changement(r, avant, voulu, delai=30):
    """Après une ligne touchée : TikTok change de compte derrière un « chargement… » qui peut durer plus de 4 s (vu le
    05/10/2026 à 15 h 09 : la liste rouverte trop tôt ne s'ouvrait pas). On attend que le @ du profil change (ou
    devienne le bon) ; s'il n'a pas bougé au bout de 8 s sans chargement en cours, la ligne était le compte déjà
    actif : on passe à la suivante. Rend le @ lu à la fin."""
    debut = time.monotonic()
    actif = avant
    while time.monotonic() - debut < delai:
        await asyncio.sleep(2)
        await fermer_intrus(r)
        actif = await compte_actif(r)
        if actif == voulu or (actif and actif != avant):
            return actif
        if time.monotonic() - debut >= 8 and not await r.trouver("chargement", "Loading", delai=0.5, contient=True):
            return actif
    return actif


async def compte_actif(r):
    """Le @ du compte affiché sur le profil (« @mapage »), ou None."""
    eid = await r.trouver("user_account_user_name", delai=6)
    if not eid:
        return None
    try:
        return ((await r.a.attribut(eid, "label")) or "").strip() or None
    except Exception:
        return None


async def lignes_comptes(r):
    """Les centres (en points, de haut en bas) des lignes de compte du panneau « Changer de compte », lus sur la
    capture : le panneau monte du bas de l'écran ; sous ses lignes, son fond uni. En remontant la colonne x = 78 pt
    (entre les avatars et les noms) jusqu'au premier point qui n'est plus ce fond, on trouve le haut du panneau ;
    puis chaque avatar (colonne x = 44 pt) est une ligne. La dernière est « Ajouter un compte » : jamais rendue.
    Mesuré le 04/10/2026 : panneau à 508 pt, comptes à 598 et 674 pt, « Ajouter un compte » à 750 pt."""
    from PIL import Image
    im = Image.open(io.BytesIO(await r.a.capture())).convert("RGB")
    largeur, hauteur = r.t.taille or (390, 844)
    k = im.width / largeur

    def point(x, y):
        return im.getpixel((min(im.width - 1, int(x * k)), min(im.height - 1, int(y * k))))

    fond = point(78, hauteur - 12)

    def du_fond(c):
        return sum(abs(a - b) for a, b in zip(c, fond)) < 24

    y = hauteur - 12
    while y > 100 and du_fond(point(78, y)):
        y -= 0.5
    haut = y + 0.5
    if haut > hauteur - 120:                     # pas de panneau (moins d'une ligne de haut)
        return []
    lignes, debut, y = [], None, haut + 4
    while y < hauteur - 4:
        dehors = not du_fond(point(44, y))
        if dehors and debut is None:
            debut = y
        elif not dehors and debut is not None:
            if y - debut > 30:                   # un avatar fait 56 pt ; un trait ou un texte, bien moins
                lignes.append((debut + y) / 2)
            debut = None
        y += 0.5
    return lignes[:-1]


async def choisir_video(r):
    """Calé le 04/10/2026. La galerie de TikTok range les vidéos de la plus ancienne (en haut) à la plus récente (en
    bas) : filtre « Vidéos », on descend tout en bas, et c'est la DERNIÈRE case (en bas à droite). Ses cases n'ont ni
    nom ni date (pas de contrôle de date ici, contrairement à Instagram : la vidéo vient d'être rangée et vérifiée
    dans la pellicule par le PC, c'est la plus récente). La sélection multiple est active : on touche le rond de la
    case (en haut à droite), puis on vérifie qu'UNE seule vidéo est choisie (le bandeau du bas en montre une, 76 pt
    de côté) avant Suivant."""
    await r.toucher("Vidéos", "Videos", types=["Button"], delai=10)
    await asyncio.sleep(1.5)
    largeur, hauteur = r.t.taille or (390, 844)
    for _ in range(5):                                       # tout en bas de la galerie
        await r.a.glisser(largeur / 2, hauteur * 0.7, largeur / 2, hauteur * 0.25, 0.2)
        await asyncio.sleep(0.6)
    cases = await r.elements("Cell", dans=lambda b: b["width"] > 110 and b["height"] > 110 and b["y"] >= 140
                             and b["y"] + b["height"] <= hauteur - 90)
    if not cases:
        raise ErreurPublication("galerie vide ou illisible (accès aux photos refusé à TikTok ?)")
    _, b = max(cases, key=lambda e: (round(e[1]["y"]), e[1]["x"]))
    await r.etape("Vidéo la plus récente de la pellicule (dernière case)")
    await r.a.toucher(b["x"] + b["width"] - 18, b["y"] + 16)   # son rond de sélection
    await asyncio.sleep(1.5)
    choisies = 0
    for eid in await r.a.chercher("class name", "XCUIElementTypeCell"):
        c = await r.a.rect(eid)
        if 60 <= c["width"] <= 90 and 60 <= c["height"] <= 90 and hauteur * 0.75 <= c["y"] <= hauteur * 0.86 \
                and not await r.a.attribut(eid, "label"):
            choisies += 1
    if choisies != 1:
        raise ErreurPublication(f"{choisies} vidéo(s) choisie(s) dans la galerie de TikTok au lieu d'une (voir la capture)")
    await r.toucher("Suivant", "Next", types=["Button"], delai=8)
    await asyncio.sleep(4)


async def retirer_son(r):
    """TikTok pose parfois tout seul une musique sur la vidéo importée (vu le 04/10/2026 : « Magnetic Field 396 Hz »
    par-dessus la voix). La pastille du son, en haut au centre, porte alors le nom de la musique ; sa croix,
    à droite de la pastille, la retire : la pastille redevient « Ajouter un son »."""
    for _ in range(2):
        pastille = None
        for eid in await r.a.chercher("predicate string", "type == 'XCUIElementTypeButton' AND rect.y < 130"):
            b = await r.a.rect(eid)
            if 35 <= b["height"] <= 55 and 80 <= b["x"] <= 140 and b["width"] >= 120 and await r.a.attribut(eid, "hittable"):
                pastille = (eid, b)
                break
        if not pastille:
            return
        nom = (await r.a.attribut(pastille[0], "label")) or ""
        if nom in ("Ajouter un son", "Add sound"):
            return
        await r.etape(f"Son ajouté par TikTok retiré : {nom}")
        b = pastille[1]
        await r.a.toucher(b["x"] + b["width"] - 20, b["y"] + b["height"] / 2)
        await asyncio.sleep(1.5)
    raise ErreurPublication("le son ajouté par TikTok ne se retire pas (voir la capture)")


async def champ_description(r):
    eid = await r.trouver(*DESCRIPTION, types=["TextView"], delai=6)
    if not eid:
        raise ErreurPublication("champ de la description introuvable")
    return eid


async def ecrire_legende(r, legende):
    await r.a.cliquer(await champ_description(r))
    await asyncio.sleep(1.2)
    await r.taper(lambda: champ_description(r), legende)
    await asyncio.sleep(1)                       # le clavier reste ouvert : « Publier » est alors en haut à droite


async def toucher_publier(r):
    """« Publier ». Clavier fermé : le bouton du bas, lisible. Clavier ouvert (le cas après la légende : le clavier ne
    se referme pas sur ordre), TikTok remonte « Publier » en pastille rouge en haut à droite, mais HORS de l'arbre
    d'accessibilité, et celui du bas est caché sous le clavier (vu le 04/10/2026 à la 1re vraie publication, signalé
    par l'utilisateur) : on trouve la pastille sur la capture, par sa couleur (le rouge de TikTok), et on la touche."""
    eid = await r.premier_touchable("type == 'XCUIElementTypeButton' AND label IN {'Publier', 'Post'}")
    if eid and await r.a.attribut(eid, "hittable") in (True, "true", "1"):
        await r.a.cliquer(eid)
        return
    centre = await pastille_publier(r)
    if not centre:
        raise ErreurPublication("bouton « Publier » introuvable (ni en bas, ni en pastille rouge en haut à droite)")
    await r.etape("« Publier » : la pastille rouge en haut à droite (clavier ouvert)")
    await r.a.toucher(*centre)


async def pastille_publier(r):
    """Le centre (en points) de la pastille rouge « Publier » du haut de l'écran, lue sur la capture, ou None."""
    from PIL import Image
    im = Image.open(io.BytesIO(await r.a.capture())).convert("RGB")
    largeur, _ = r.t.taille or (390, 844)
    k = im.width / largeur
    xs, ys = [], []
    for y in range(int(40 * k), int(100 * k), 2):
        for x in range(int(largeur * 0.6 * k), im.width, 2):
            rouge, vert, bleu = im.getpixel((x, y))
            if rouge > 200 and vert < 100 and 50 < bleu < 140:      # le rouge de TikTok : (254, 44, 85)
                xs.append(x)
                ys.append(y)
    if len(xs) < 40:
        return None
    return sum(xs) / len(xs) / k, sum(ys) / len(ys) / k


async def abandonner(r):
    """Répétition : sortie sans publier : Retour (écran Publier) › Retour (éditeur) › vidéo retirée de la sélection ›
    Retour (galerie) › Fermer (création). TikTok ne pose aucune question mais GARDE un brouillon de la vidéo (vu le
    04/10/2026, 35 Mo, Profil › Brouillons) : quelle que soit la sortie (même l'app coupée net), une vidéo passée
    dans l'éditeur devient un brouillon. On ne l'efface pas (effacer est le geste de l'utilisateur)."""
    try:
        await r.a.fermer_clavier()
    except Exception:
        pass
    for nom in ("(publishPageBackButton)", "(editPageBackButton)", "icDeleteAssetOptimize"):
        await r.si_present(nom, delai=4)
        await asyncio.sleep(1.2)
    await r.si_present("Retour", types=["Button"], delai=3)
    await asyncio.sleep(1.2)
    await r.si_present("Fermer", types=["Button"], delai=3)
    await r.a.profondeur(PROFONDEUR)
    await r.etape("Répétition : rien n'est parti (TikTok garde un brouillon de la vidéo : Profil › Brouillons)")


# ── warm-up (chauffe.py), calé le 07/10/2026 sur le vrai iPhone ─────────────────────────────────────────────────────
# Le fil « Pour toi » se lit sur 15 niveaux : ses onglets du haut (« top_tabs_recomend », valeur 1 quand il est choisi)
# et la loupe « Rechercher », en haut à droite (le bouton LIVE est en haut à gauche : la flèche retour des autres
# écrans est au même endroit, on ne la touche jamais sur le fil). La page de recherche se lit sur 26 niveaux en 1 s :
# le champ, le bouton « Rechercher », les onglets (Top, Utilisateurs, LIVE, Vidéos…) et chaque vidéo de l'onglet
# Vidéos avec sa description (« légende. Il y a 4 j. auteur. 242751 j'aime. »). Une vidéo ouverte, elle, ne se lit
# PAS : sur le vrai iPhone, chercher un élément y a pris 3 min même sur 11 niveaux, et demander s'il y a une alerte
# 28 s (mesuré le 07/10/2026) ; seule la barre d'onglets du bas, sur 8 niveaux, répond vite (0,5 s). Pire : sur le
# fil comme sur une vidéo ouverte, un geste à des coordonnées (toucher, glisser) dure plus de 2 min et bloque l'agent ;
# fait sur la FENÊTRE de l'app (trouvée sur 2 niveaux), il prend 0,4 s, et l'alerte se lit en 0,3 s sur 2 niveaux.
# Sur une vidéo, on ne fait donc que des captures et des gestes sur la fenêtre : ses boutons de droite (photo du
# compte avec le « + » rouge pour s'y abonner, cœur, commentaires, favoris, partage) sont repérés sur la capture.
# La 1re vidéo ouverte d'une recherche peut être voilée par un tutoriel (« Plus de résultats pour… », une main qui
# glisse) : un glissement l'enlève.
PROFONDEUR_ONGLETS = 8        # la barre d'onglets du bas (Accueil…) est au niveau 6 : lecture courte, même sur une vidéo
PROFONDEUR_RECHERCHE = 26
PROFONDEUR_VIDEO = 2          # sur une vidéo : la fenêtre de l'app (niveau 1) et les alertes, rien d'autre
ROUGE = (254, 44, 85)
COLONNE = (338, 380)          # la colonne des boutons à droite d'une vidéo, en points
PUBS = ("Publicité", "Sponsorisé", "Sponsored", "Annonce", "LIVE")


async def chauffer(r, compte, s):
    """Une séance de warm-up (chauffe.Seance) : la niche d'abord (recherche, onglet Vidéos), puis « Pour toi »."""
    await r.etape("Ouverture de TikTok")
    await r.lancer_propre(BUNDLE)
    await alertes_video(r)
    await r.a.profondeur(PROFONDEUR)
    await fermer_intrus(r)
    await choisir_compte(r, compte["identifiant"])
    await aller_au_fil(r)
    s.demarrer()
    niche = s.duree * random.uniform(0.5, 0.65)
    for _ in range(3):
        if s.fini() or s.ecoule() >= niche or not s.mot():
            break
        if await chercher(r, s):
            await regarder(r, s, niche=True, jusqua=niche)
        await aller_au_fil(r)
    if not s.fini():
        await r.etape("Fil « Pour toi »")
        await regarder(r, s, niche=False)
    await r.etape(f"Fin de la séance : {s.resume()}")


async def aller_au_fil(r, relancer=True):
    """Revient sur « Pour toi » : depuis une vidéo ouverte, les résultats ou la recherche, la flèche retour en haut à
    gauche (sans jamais lire l'arbre d'une vidéo ouverte : seulement la barre d'onglets, sur 8 niveaux) ; depuis un
    autre onglet, « Accueil ». En dernier recours, TikTok relancé (il rouvre sur le compte actif)."""
    for essai in range(6):
        await r.a.profondeur(PROFONDEUR_ONGLETS)
        accueil = await r.trouver("Accueil", "Home", types=["Button"], delai=1.5)
        await r.a.profondeur(PROFONDEUR)
        if accueil:
            onglet = await r.trouver("top_tabs_recomend", delai=3)
            if onglet:
                if str(await r.a.attribut(onglet, "value")) != "1":
                    await r.a.cliquer(onglet)
                    await asyncio.sleep(1.5)
                return
            await alertes_video(r)
            await r.a.profondeur(PROFONDEUR)
            await fermer_intrus(r)
            await r.a.cliquer(accueil)
            await asyncio.sleep(2)
            continue
        if essai >= 3:                              # trois retours sans revoir les onglets : une fenêtre gêne ?
            await alertes_video(r)
            await fermer_intrus(r)
        await toucher_fenetre(r, 26, 69)           # la flèche retour (vidéo ouverte, résultats, recherche)
        await asyncio.sleep(1.5)
    if relancer:
        await r.etape("Le fil ne revient pas : TikTok relancé")
        await r.lancer_propre(BUNDLE)
        await alertes_video(r)
        await r.a.profondeur(PROFONDEUR)
        await fermer_intrus(r)
        return await aller_au_fil(r, relancer=False)
    raise ErreurPublication("le fil « Pour toi » ne revient pas (voir la capture)")


async def chercher(r, s):
    """Cherche le prochain mot-clé de la niche et ouvre la 1re vidéo de l'onglet Vidéos (ni publicité ni LIVE)."""
    mot = s.mot()
    await r.a.profondeur(PROFONDEUR)
    if not await r.toucher("Rechercher", "Search", types=["Button"], delai=6, obligatoire=False):
        await r.etape("Loupe « Rechercher » introuvable sur le fil")
        return False
    await asyncio.sleep(1.5)
    await r.a.profondeur(PROFONDEUR_RECHERCHE)
    champs = await r.elements("SearchField")
    if not champs:
        await r.etape("Champ de recherche introuvable")
        return False
    await r.si_present("Effacer le texte", "Clear text", types=["Button"], delai=0.5)
    await r.a.cliquer(champs[0][0])
    await asyncio.sleep(0.8)
    await r.a.ecrire(mot)
    await asyncio.sleep(0.8)
    if not await r.toucher("Rechercher", "Search", types=["Button"], delai=4, obligatoire=False):
        await r.a.ecrire("\n")
    await asyncio.sleep(3)
    if not await r.toucher("Vidéos", "Videos", types=["Button"], delai=8, obligatoire=False):
        await r.etape(f"Recherche « {mot} » : pas d'onglet Vidéos")
        return False
    await asyncio.sleep(3)
    cases = await resultats(r)
    s.cherche(mot)
    await r.etape(f"Recherche « {mot} » : {len(cases)} vidéo(s) à l'écran")
    if not cases:
        return False
    await r.a.cliquer(cases[0][0])
    await asyncio.sleep(3)
    if voilee(await r.a.capture()):             # le tutoriel « Plus de résultats pour… » : un glissement l'enlève
        await r.etape("Tutoriel « Plus de résultats » : enlevé d'un glissement")
        await glisser(r)
    return True


async def resultats(r):
    """Les vidéos de l'onglet Vidéos à l'écran, sans publicité ni LIVE : [(id, rect, description)], de haut en bas."""
    out = []
    w, h = r.t.taille or (390, 844)
    for eid in await r.a.chercher("predicate string", "type == 'XCUIElementTypeOther' AND (label CONTAINS[c] \"j'aime\" "
                                                      "OR label CONTAINS[c] 'j’aime' OR label CONTAINS[c] ' likes')"):
        try:
            rect, label = await r.a.rect(eid), (await r.a.attribut(eid, "label")) or ""
        except Exception:
            continue
        if rect["width"] >= 120 and rect["height"] >= 150 and rect["y"] >= 100 and rect["y"] + 80 < h \
                and not any(m in label for m in PUBS):
            out.append((eid, rect, label))
    return sorted(out, key=lambda c: (round(c[1]["y"]), c[1]["x"]))


async def regarder(r, s, niche, jusqua=None):
    """Regarde les vidéos les unes après les autres (glisser vers le haut), chacune un temps tiré au hasard ; dans la
    niche, quelques likes et abonnements si le jour du warm-up le permet."""
    n = 0
    while not s.fini() and (jusqua is None or s.ecoule() < jusqua):
        d = s.duree_video(niche)
        await s.regarder(d * 0.5)
        if niche and not s.fini():
            if s.envie_de_suivre():
                await suivre(r, s)
            if s.envie_de_liker(d):
                await liker(r, s)
        await s.regarder(d * 0.5)
        s.vues += 1
        n += 1
        if s.fini():
            break
        await glisser(r)
        if n % (3 if niche else 4) == 0:
            if niche:                              # vidéo ouverte : la capture seulement (l'arbre y prend des minutes)
                if not colonne_presente(await r.a.capture()):
                    await r.etape("Plus sur une vidéo (colonne de droite absente) : retour au fil")
                    return
            else:
                await alertes_video(r)
                await r.a.profondeur(PROFONDEUR)
                if not await r.trouver("top_tabs_recomend", delai=4):
                    await r.etape("Plus sur le fil : une fenêtre ? retour au fil")
                    await fermer_intrus(r)
                    await aller_au_fil(r)


def _bandes(png, garder, zone=(338, 380, 200, 720)):
    """Les bandes horizontales de la colonne de droite où des pixels répondent à `garder(pixel)` : [{y, h, l, x}] en
    points (y : milieu ; h : hauteur ; l : largeur ; x : milieu)."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    k = im.width / 390
    x0, x1, y0, y1 = (int(v * k) for v in zone)
    z = im.crop((x0, y0, x1, y1))
    largeur, px = z.width, list(z.getdata())
    out, debut, gauche, droite = [], None, 1e9, -1
    for y in range(z.height + 1):
        xs = [x for x in range(largeur) if garder(px[y * largeur + x])] if y < z.height else []
        if len(xs) >= max(2, k):
            debut = y if debut is None else debut
            gauche, droite = min(gauche, xs[0]), max(droite, xs[-1])
        elif debut is not None:
            out.append({"y": (y0 + (debut + y) / 2) / k, "h": (y - debut) / k, "l": (droite - gauche + 1) / k,
                        "x": (x0 + (gauche + droite) / 2) / k})
            debut, gauche, droite = None, 1e9, -1
    return [b for b in out if b["h"] >= 6]


def colonne_presente(png):
    """Une vidéo ouverte a, à droite, ses icônes blanches (cœur, commentaires, favoris, partage) : au moins deux
    taches blanches séparées (une page blanche, elle, n'en fait qu'une)."""
    return len([b for b in _bandes(png, lambda c: min(c[0], c[1], c[2]) >= 200, (338, 380, 380, 700)) if b["h"] <= 60]) >= 2


def voilee(png):
    """L'écran assombri par un tutoriel : plus rien de blanc dans la colonne de droite (le voile divise tout par deux)."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("L")
    k = im.width / 390
    return max(im.crop((int(338 * k), int(380 * k), int(380 * k), int(650 * k))).getdata()) < 170


async def fenetre(r):
    await r.a.profondeur(PROFONDEUR_VIDEO)
    return await r.a.fenetre()


async def toucher_fenetre(r, x, y):
    await r.a.toucher_sur(await fenetre(r), x, y)


async def alertes_video(r):
    """Les alertes, lues sur 2 niveaux (sur une vidéo de TikTok, plus profond : 28 s)."""
    await r.a.profondeur(PROFONDEUR_VIDEO)
    await r.alertes_refusees()


async def glisser(r):
    """Vidéo suivante : un glissement vers le haut sur la fenêtre, à une vitesse jamais deux fois la même."""
    await r.a.glisser_sur(await fenetre(r), "up", random.uniform(1800, 3200))
    await asyncio.sleep(random.uniform(0.6, 1.2))


def bandes_rouges(png):
    """Les taches rouges (rouge TikTok) de la colonne de droite d'une vidéo, de haut en bas. Le « + » pour s'abonner :
    un rond de 22 pt sous la photo du compte ; le cœur liké : une tache plus large (~30 pt), en dessous."""
    return _bandes(png, _rouge, (COLONNE[0], COLONNE[1], 200, 720))


def _rouge(c):
    """Le rouge rosé de TikTok (254, 44, 85), même assombri (le voile d'un tutoriel le divise par deux : (127, 23, 42),
    vu le 07/10/2026) : on regarde la teinte, pas la valeur."""
    r, g, b = c[0], c[1], c[2]
    return r >= 90 and g <= 0.32 * r and b <= 0.5 * r and b >= 0.9 * g


def coeur_rouge(bandes):
    """Le cœur liké : une tache rouge large (~30 pt ; le « + » n'en fait que 22, mesuré le 07/10/2026)."""
    return any(20 <= b["h"] <= 40 and b["l"] >= 26 for b in bandes)


def bouton_suivre(bandes, png=None):
    """Le « + » rouge sous la photo du compte (un rond de 22 pt avec une croix blanche au milieu) : la plus haute
    petite tache ronde, ou None. Avec la capture, le milieu doit être clair (la croix) : une tache rouge de la vidéo
    elle-même est écartée."""
    ronds = [b for b in bandes if 12 <= b["h"] <= 25 and 12 <= b["l"] <= 25]
    if png is not None:
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGB")
        k = im.width / 390

        def croix(b):
            return max(min(im.getpixel((int((b["x"] + dx) * k), int((b["y"] + dy) * k))))
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1)) >= 110
        ronds = [b for b in ronds if croix(b)]
    return min(ronds, key=lambda b: b["y"]) if ronds else None


async def liker(r, s):
    """Like de la vidéo par deux touchers au milieu de l'écran (jamais sur le cœur : un toucher dessus pourrait retirer
    un like) ; compté si le cœur de la colonne de droite est devenu rouge."""
    avant = bandes_rouges(await r.a.capture())
    if coeur_rouge(avant):
        return
    await r.a.double_sur(await fenetre(r))          # au milieu de l'écran : sur la vidéo
    await asyncio.sleep(1.5)
    apres = bandes_rouges(await r.a.capture())
    nouveau = [b for b in apres if b["l"] >= 24 and 18 <= b["h"] <= 40 and not any(abs(b["y"] - a["y"]) < 8 for a in avant)]
    if nouveau:                                     # un cœur rouge est apparu (ce qui était rouge avant ne compte pas)
        s.likes += 1
        await r.etape(f"Like n° {s.likes}", capture=s.likes == 1)
    else:
        await r.etape("Like pas vu sur la capture (le cœur n'est pas devenu rouge)")


async def suivre(r, s):
    """Abonnement au compte de la vidéo : le « + » rouge sous sa photo ; compté s'il a disparu."""
    png = await r.a.capture()
    plus = bouton_suivre(bandes_rouges(png), png)
    if not plus:
        return
    await toucher_fenetre(r, plus["x"], plus["y"])
    await asyncio.sleep(2.5)
    png = await r.a.capture()
    reste = bouton_suivre(bandes_rouges(png), png)
    if reste and abs(reste["y"] - plus["y"]) < 10:
        await r.etape("Abonnement pas vu (le « + » est toujours là)")
        return
    s.abonnements += 1
    await r.etape(f"Abonnement n° {s.abonnements}")
