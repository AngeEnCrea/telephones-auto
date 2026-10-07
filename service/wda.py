"""wda.py : WebDriverAgent, l'agent qui tourne sur l'iPhone (installé avec Impactor, lancé par `ios ui run wda`).
Il tape, glisse, écrit, lit l'écran (l'arbre d'accessibilité : chaque bouton avec son nom) et le filme (flux MJPEG,
relayé par serveur.py). Les coordonnées sont en points iOS, pas en pixels : (0, 0) en haut à gauche, /wda/screen
donne la taille. Routes vérifiées sur les sources d'appium/WebDriverAgent v16.13.6."""
import asyncio
import base64

import aiohttp

W3C_ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
# Jusqu'où l'agent lit l'arbre de l'écran (en niveaux) pour chercher un bouton : assez pour les apps du système (Photos,
# Raccourcis). Les apps vidéo ont un arbre immense : sur le fil de TikTok, au-delà de 15 niveaux, la lecture dure 65 s
# et ne rend rien (mesuré le 02/10/2026 : 15 → 0,3 s ; 18 à 40 → 65 s ou plus, aucun élément). Une recette fixe la sienne.
PROFONDEUR = 40


class ErreurAgent(RuntimeError):
    def __init__(self, message, code=None, erreur=None):
        self.code = code          # statut HTTP (None : pas de réponse)
        self.erreur = erreur      # l'erreur W3C (« no such element », « invalid session id »…)
        super().__init__(message)


class Agent:
    def __init__(self, port, http):
        self.base = f"http://127.0.0.1:{port}"
        self.http = http
        self.sid = None
        self._verrou = asyncio.Lock()

    async def _req(self, methode, chemin, corps=None, delai=60):
        try:
            async with self.http.request(methode, self.base + chemin, json=corps,
                                         timeout=aiohttp.ClientTimeout(total=delai)) as r:
                try:
                    d = await r.json(content_type=None)
                except ValueError:
                    d = None
                v = d.get("value") if isinstance(d, dict) else None
                if r.status >= 400 or (isinstance(v, dict) and v.get("error")):
                    err = v.get("error") if isinstance(v, dict) else None
                    msg = (v.get("message") or "") if isinstance(v, dict) else ""
                    raise ErreurAgent(f"{methode} {chemin} : {err or r.status} {msg[:300]}".strip(), r.status, err)
                return v
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            raise ErreurAgent(f"l'agent ne répond pas ({type(e).__name__})") from e

    async def session(self):
        async with self._verrou:
            if not self.sid:
                v = await self._req("POST", "/session", {"capabilities": {"alwaysMatch": {}, "firstMatch": [{}]}})
                self.sid = (v or {}).get("sessionId")
                if not self.sid:
                    raise ErreurAgent("l'agent n'a pas ouvert de session")
            return self.sid

    async def s(self, methode, chemin, corps=None, delai=60):
        """Une commande de session. Une session perdue (agent relancé entre-temps) est rouverte une fois."""
        for essai in (0, 1):
            sid = await self.session()
            try:
                return await self._req(methode, f"/session/{sid}{chemin}", corps, delai)
            except ErreurAgent as e:
                if essai == 0 and (e.erreur == "invalid session id" or (e.code == 404 and "session" in str(e).lower())):
                    self.sid = None
                    continue
                raise

    # ── état ──────────────────────────────────────────────────────────────────────────────────────────
    async def statut(self, delai=3):
        """Le /status de l'agent, ou None s'il ne répond pas."""
        try:
            return await self._req("GET", "/status", delai=delai)
        except ErreurAgent:
            return None

    async def ecran(self):
        """{screenSize: {width, height} en points, statusBarSize, scale}."""
        return await self._req("GET", "/wda/screen")

    async def capture(self):
        """Capture PNG pleine résolution (octets)."""
        return base64.b64decode(await self._req("GET", "/screenshot", delai=30))

    async def arbre(self):
        """L'arbre d'accessibilité de l'écran (JSON : type, label, name, value, rect, isEnabled, children…)."""
        return await self._req("GET", "/source?format=json", delai=90)

    async def app_active(self):
        return await self._req("GET", "/wda/activeAppInfo")

    async def verrouille(self):
        return bool(await self._req("GET", "/wda/locked"))

    async def deverrouiller(self):
        await self._req("POST", "/wda/unlock", delai=30)

    async def batterie(self):
        """{level: 0..1, state: 1 débranché, 2 en charge, 3 pleine}."""
        return await self.s("GET", "/wda/batteryInfo")

    async def reglages(self, **r):
        await self.s("POST", "/appium/settings", {"settings": r})

    async def profondeur(self, niveaux=PROFONDEUR):
        await self.reglages(snapshotMaxDepth=niveaux)

    # ── gestes (points iOS) ─────────────────────────────────────────────────────────────────────────────
    async def toucher(self, x, y):
        await self.s("POST", "/wda/tap", {"x": x, "y": y})

    async def double(self, x, y):
        """Deux touchers rapides au même endroit."""
        await self.s("POST", "/wda/doubleTap", {"x": x, "y": y})

    # Les gestes « sur un élément » : sur un fil vidéo de TikTok, un geste à des coordonnées de l'écran (toucher,
    # glisser, deux touchers, /actions) fait relire tout l'arbre de l'app à XCTest : plus de 2 min, et l'agent reste
    # bloqué derrière (mesuré le 07/10/2026). Le même geste fait sur la fenêtre de l'app (trouvée sur 2 niveaux en
    # 0,1 s) prend 0,4 s : glisser 0,4 s, toucher 0,7 s.
    async def fenetre(self):
        """La fenêtre de l'app au premier plan (la profondeur de lecture doit être basse : 2 suffit)."""
        ids = await self.chercher("class name", "XCUIElementTypeWindow")
        if not ids:
            raise ErreurAgent("pas de fenêtre à l'écran")
        return ids[0]

    async def glisser_sur(self, eid, sens="up", vitesse=2500):
        await self.s("POST", f"/wda/element/{eid}/swipe", {"direction": sens, "velocity": vitesse}, delai=30)

    async def toucher_sur(self, eid, x, y):
        """Un toucher à (x, y) points, comptés depuis le coin de l'élément (la fenêtre : depuis le coin de l'écran)."""
        await self.s("POST", f"/wda/element/{eid}/tap", {"x": x, "y": y}, delai=30)

    async def double_sur(self, eid):
        """Deux touchers rapides au milieu de l'élément (la fenêtre : au milieu de l'écran, sur la vidéo)."""
        await self.s("POST", f"/wda/element/{eid}/doubleTap", {}, delai=30)

    async def appui_long(self, x, y, duree=1.0):
        await self.s("POST", "/wda/touchAndHold", {"x": x, "y": y, "duration": duree})

    async def glisser(self, x1, y1, x2, y2, duree=0.35):
        doigt = {"type": "pointer", "id": "doigt", "parameters": {"pointerType": "touch"}, "actions": [
            {"type": "pointerMove", "duration": 0, "x": x1, "y": y1},
            {"type": "pointerDown", "button": 0},
            {"type": "pause", "duration": 60},
            {"type": "pointerMove", "duration": int(duree * 1000), "x": x2, "y": y2},
            {"type": "pointerUp", "button": 0}]}
        await self.s("POST", "/actions", {"actions": [doigt]}, delai=30)

    async def ecrire(self, texte):
        """Tape au clavier, dans le champ qui a le focus."""
        await self.s("POST", "/wda/keys", {"value": list(texte)}, delai=180)

    async def bouton(self, nom):
        """home, volumeUp, volumeDown."""
        await self.s("POST", "/wda/pressButton", {"name": nom})

    async def accueil(self):
        await self._req("POST", "/wda/homescreen")

    async def fermer_clavier(self):
        await self.s("POST", "/wda/keyboard/dismiss", {})

    # ── apps et liens ──────────────────────────────────────────────────────────────────────────────────
    async def ouvrir_url(self, url):
        await self.s("POST", "/url", {"url": url}, delai=60)

    async def lancer(self, bundle):
        await self.s("POST", "/wda/apps/launch", {"bundleId": bundle, "arguments": [], "environment": {}}, delai=90)

    async def activer(self, bundle):
        await self.s("POST", "/wda/apps/activate", {"bundleId": bundle}, delai=60)

    async def fermer(self, bundle):
        return await self.s("POST", "/wda/apps/terminate", {"bundleId": bundle}, delai=60)

    async def etat_app(self, bundle):
        """1 fermée, 2 suspendue, 3 en arrière-plan, 4 au premier plan."""
        return await self.s("POST", "/wda/apps/state", {"bundleId": bundle})

    # ── éléments (boutons, champs…) ─────────────────────────────────────────────────────────────────────
    async def chercher(self, using, valeur):
        """using : 'predicate string', 'class chain', 'accessibility id', 'xpath'… ; rend les identifiants."""
        v = await self.s("POST", "/elements", {"using": using, "value": valeur}, delai=30)
        return [e.get("ELEMENT") or e.get(W3C_ELEMENT) for e in (v or [])]

    async def rect(self, eid):
        return await self.s("GET", f"/element/{eid}/rect")

    async def cliquer(self, eid):
        await self.s("POST", f"/element/{eid}/click")

    async def texte(self, eid):
        return await self.s("GET", f"/element/{eid}/text")

    async def attribut(self, eid, nom):
        return await self.s("GET", f"/element/{eid}/attribute/{nom}")

    async def saisir(self, eid, texte):
        await self.s("POST", f"/element/{eid}/value", {"value": list(texte)}, delai=180)

    async def vider(self, eid):
        await self.s("POST", f"/element/{eid}/clear")

    # ── alertes système (autorisations, « Ouvrir dans … ? ») ──────────────────────────────────────────────
    async def alerte(self):
        """Le texte de l'alerte affichée, ou None."""
        try:
            return await self._req("GET", "/alert/text", delai=10)
        except ErreurAgent as e:
            if e.erreur == "no such alert" or e.code == 404:
                return None
            raise

    async def boutons_alerte(self):
        return await self.s("GET", "/wda/alert/buttons")

    async def accepter_alerte(self, nom=None):
        await self._req("POST", "/alert/accept", {"name": nom} if nom else {})

    async def refuser_alerte(self, nom=None):
        await self._req("POST", "/alert/dismiss", {"name": nom} if nom else {})

    async def presse_papiers(self, texte):
        """Repli quand go-ios ne peut pas écrire le presse-papiers (iOS 16 et moins)."""
        await self._req("POST", "/wda/setPasteboard",
                        {"content": base64.b64encode(texte.encode("utf-8")).decode(), "contentType": "plaintext"})
