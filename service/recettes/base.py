"""recettes/base.py : ce qu'une recette de publication peut faire sur l'iPhone. Chaque étape est notée avec une
capture d'écran réduite : quand un parcours casse (l'app a déplacé ou renommé un bouton), on voit où et pourquoi ;
l'arbre de l'écran est gardé à côté pour recaler la recette.

On trouve les boutons par leur nom d'accessibilité (ce que VoiceOver lirait), en français et en anglais, jamais par
des coordonnées en dur : un bouton déplacé reste trouvé, un bouton renommé casse net et le dit."""
import asyncio
import datetime as dt
import io
import json
import logging
import time
from zoneinfo import ZoneInfo

import goios
from wda import ErreurAgent

log = logging.getLogger("robot")
PARIS = ZoneInfo("Europe/Paris")


class ErreurPublication(RuntimeError):
    pass


def q(texte):
    """Un texte entre guillemets pour un prédicat NSPredicate."""
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def pareil(texte):
    """Un texte comparable à un autre : fins de ligne et apostrophes typographiques ramenées à une seule forme."""
    return (texte or "").replace("\r\n", "\n").replace("\r", "\n").replace("’", "'").strip()


def jpeg_reduit(png, largeur=420):
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if im.width > largeur:
        im = im.resize((largeur, round(im.height * largeur / im.width)))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=72)
    return out.getvalue()


class Robot:
    def __init__(self, tel, pub, stock, dossier):
        self.t, self.a = tel, tel.agent
        self.pub, self.stock, self.dossier = pub, stock, dossier
        self.repetition = bool(pub.get("repetition"))
        dossier.mkdir(parents=True, exist_ok=True)

    # ── journal de la publication ───────────────────────────────────────────────────────────────────────
    async def etape(self, message):
        """Note l'étape, avec la capture de ce que l'écran montre à ce moment."""
        nom = None
        try:
            jpg = jpeg_reduit(await self.a.capture())
            n = len(self.stock.etapes(self.pub["id"])) + 1
            nom = f"{n:02d}.jpg"
            (self.dossier / nom).write_bytes(jpg)
        except Exception as e:           # une capture ratée n'arrête pas la publication
            log.warning("capture impossible : %s", e)
        self.stock.etape(self.pub["id"], message, nom)
        log.info("publication %s : %s", self.pub["id"], message)

    async def garder_arbre(self, nom="arbre-echec.json"):
        try:
            (self.dossier / nom).write_text(json.dumps(await self.a.arbre(), ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning("arbre de l'écran impossible : %s", e)

    # ── trouver et toucher ──────────────────────────────────────────────────────────────────────────────
    async def trouver(self, *textes, types=None, delai=8.0, contient=False):
        """Attend (au plus `delai` s) un élément à l'écran dont le label ou le name vaut l'un des textes (ou le
        contient) ; rend son identifiant, ou None."""
        op = "CONTAINS[c]" if contient else "=="
        pred = "(" + " OR ".join(f"label {op} {q(t)} OR name {op} {q(t)}" for t in textes) + ")"
        if types:
            pred += " AND type IN {" + ", ".join(q("XCUIElementType" + x) for x in types) + "}"
        fin = time.monotonic() + delai
        while True:
            try:
                for eid in await self.a.chercher("predicate string", pred):
                    if await self.visible(eid):
                        return eid
            except ErreurAgent as e:
                log.debug("recherche : %s", e)
            if time.monotonic() >= fin:
                return None
            await asyncio.sleep(0.6)

    async def visible(self, eid):
        try:
            r = await self.a.rect(eid)
        except ErreurAgent:
            return False
        w, h = self.t.taille or (10_000, 10_000)
        return r["width"] > 0 and r["height"] > 0 and r["x"] < w and r["y"] < h and r["x"] + r["width"] > 0 and r["y"] + r["height"] > 0

    async def toucher(self, *textes, types=None, delai=8.0, contient=False, obligatoire=True):
        eid = await self.trouver(*textes, types=types, delai=delai, contient=contient)
        if not eid:
            if obligatoire:
                raise ErreurPublication(f"introuvable à l'écran : « {' » ou « '.join(textes)} »")
            return False
        await self.a.cliquer(eid)
        await asyncio.sleep(0.8)
        return True

    async def si_present(self, *textes, delai=1.5, **kw):
        return await self.toucher(*textes, delai=delai, obligatoire=False, **kw)

    async def attendre(self, *textes, delai=20.0, **kw):
        eid = await self.trouver(*textes, delai=delai, **kw)
        if not eid:
            raise ErreurPublication(f"toujours pas à l'écran après {delai:.0f} s : « {' » ou « '.join(textes)} »")
        return eid

    async def elements(self, type_, dans=None):
        """Les éléments visibles d'un type, avec leur rectangle, triés de haut en bas puis de gauche à droite."""
        out = []
        for eid in await self.a.chercher("class name", "XCUIElementType" + type_):
            try:
                r = await self.a.rect(eid)
            except ErreurAgent:
                continue
            if r["width"] > 0 and r["height"] > 0 and (not dans or dans(r)):
                out.append((eid, r))
        return sorted(out, key=lambda e: (round(e[1]["y"]), e[1]["x"]))

    # ── gestes composés ─────────────────────────────────────────────────────────────────────────────────
    async def lancer_propre(self, bundle):
        """L'app relancée à neuf : on part toujours du même écran."""
        try:
            await self.a.fermer(bundle)
        except ErreurAgent:
            pass
        await self.a.lancer(bundle)
        await asyncio.sleep(4)

    async def coller(self, eid, texte):
        """Écrit un texte (émojis compris) dans un champ par le presse-papiers : taper au clavier virtuel est lent
        et perd des caractères."""
        try:
            await goios.presse_papiers_ecrire(self.t.udid, texte)
        except Exception:
            await self.a.presse_papiers(texte)
        await self.a.cliquer(eid)
        await asyncio.sleep(1.0)
        r = await self.a.rect(eid)
        await self.a.appui_long(r["x"] + min(r["width"] / 2, 120), r["y"] + min(r["height"] / 2, 24), 0.9)
        if not await self.toucher("Coller", "Paste", delai=4, obligatoire=False):
            log.warning("menu Coller absent : on tape la légende au clavier")
            await self.a.ecrire(texte)

    async def taper(self, trouver_champ, texte):
        """Tape `texte` dans le champ que rend `trouver_champ()` (une coroutine : identifiant du champ), puis le relit.
        Le presse-papiers n'est joignable ni par le câble ni par l'agent sur l'iPhone 12 / iOS 26.5 (mesuré le
        04/10/2026 : go-ios n'y a pas accès, l'agent le lit vide) ; XCTest, lui, tape directement accents, émojis et
        retours à la ligne (50 caractères en 2 s). Une légende qui ne se relit pas pareille arrête la publication."""
        await self.a.reglages(maxTypingFrequency=30)
        await self.a.ecrire(texte)
        await asyncio.sleep(1)
        lu = (await self.a.attribut(await trouver_champ(), "value")) or ""
        if pareil(lu) != pareil(texte):
            raise ErreurPublication(f"la légende tapée ne se relit pas pareille (lu : « {lu[:80]} »)")

    async def coller_et_lire(self, trouver_champ):
        """Colle le presse-papiers dans un champ de l'app (appui long › Coller) et rend ce que le champ contient : la
        seule façon de lire un lien copié par l'app sur cet iPhone (04/10/2026). None si « Coller » n'apparaît pas."""
        eid = await trouver_champ()
        await self.a.cliquer(eid)
        await asyncio.sleep(1)
        r = await self.a.rect(await trouver_champ())
        await self.a.appui_long(r["x"] + min(r["width"] / 2, 100), r["y"] + r["height"] / 2, 0.9)
        if not await self.toucher("Coller", "Paste", types=["MenuItem"], delai=4, obligatoire=False):
            return None
        await asyncio.sleep(1)
        return await self.a.attribut(await trouver_champ(), "value")

    async def premier_touchable(self, predicat):
        """Le premier élément touchable qui répond au prédicat. Le mot « hittable » n'est pas compris dans les
        prédicats de cet agent (vu le 04/10/2026 : il rend aussi les éléments cachés, comme le 2e champ de légende
        d'Instagram) : on le lit élément par élément."""
        trouves = await self.a.chercher("predicate string", predicat)
        for eid in trouves:
            try:
                if await self.a.attribut(eid, "hittable") in (True, "true", "1"):
                    return eid
            except ErreurAgent:
                continue
        return trouves[0] if trouves else None

    async def alertes(self, accepter=("Autoriser l’accès complet", "Autoriser l'accès complet", "Allow Full Access",
                                     "Autoriser l’accès à toutes les photos", "Autoriser l'accès à toutes les photos",
                                     "Autoriser", "Allow", "OK"), tout_refuser=False):
        """Répond aux alertes système qui bloquent le parcours ; rend le texte vu, ou None. L'accès aux photos est
        accordé en entier (« Limiter l'accès » obligerait à choisir chaque vidéo à la main). Refusés toujours : le
        suivi publicitaire (« … à suivre vos activités »), la caméra et le micro (inutiles pour publier une vidéo
        rangée dans la pellicule ; TikTok les demande en ouvrant la création, vu le 04/10/2026)."""
        texte = await self.a.alerte()
        if not texte:
            return None
        try:
            boutons = await self.a.boutons_alerte() or []
        except ErreurAgent:
            boutons = []
        bas = texte.lower()
        if any(m in bas for m in ("suivre vos activités", "track your activity")):
            accepter = ("Demander à l’app de ne pas me suivre", "Demander à l'app de ne pas me suivre", "Ask App Not to Track")
        elif tout_refuser or any(m in bas for m in ("caméra", "micro", "camera", "microphone")):
            choix = next((b for b in boutons if b in ("Ne pas autoriser", "Don’t Allow", "Don't Allow", "Plus tard", "Pas maintenant",
                                                     "Not Now", "Annuler", "Cancel")), None)
            log.info("alerte « %s » → refusée", texte.replace("\n", " ")[:120])
            await self.a.refuser_alerte(choix)
            await asyncio.sleep(1)
            return texte
        choix = next((b for a in accepter for b in boutons if b == a), None)
        log.info("alerte « %s » → %s", texte.replace("\n", " ")[:120], choix or "acceptée")
        await self.a.accepter_alerte(choix)
        await asyncio.sleep(1)
        return texte


class RobotSeance(Robot):
    """Le robot d'une séance de warm-up (chauffe.py) : mêmes gestes, mais son journal est celui de la séance (une
    ligne par étape, une capture aux étapes clés, pas à chaque vidéo)."""

    def __init__(self, tel, stock, seance, dossier):
        super().__init__(tel, {"id": seance["id"], "repetition": 0}, stock, dossier)
        self.seance, self.n = seance, 0

    async def etape(self, message, capture=True):
        nom = None
        if capture:
            try:
                jpg = jpeg_reduit(await self.a.capture())
                self.n += 1
                nom = f"{self.n:02d}.jpg"
                (self.dossier / nom).write_bytes(jpg)
            except Exception as e:
                log.warning("capture impossible : %s", e)
        heure = dt.datetime.now(PARIS).strftime("%H:%M:%S")          # le journal se lit à l'heure de Paris
        self.stock.noter_seance(self.seance["id"], f"{heure} {message}" + (f" [{nom}]" if nom else ""))
        log.info("warm-up, séance %s : %s", self.seance["id"], message)

    async def alertes_refusees(self):
        """Pendant un warm-up, toute alerte système est refusée (notifications, contacts, position…)."""
        return await self.alertes(tout_refuser=True)
