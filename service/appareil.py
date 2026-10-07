"""appareil.py : un iPhone branché sur l'ordinateur, et la préparation qui l'amène jusqu'à « prêt à piloter ». Chaque étape
dit en clair où elle en est et, quand elle bloque, ce que l'utilisateur doit faire sur l'iPhone. Une fois prêt, on ne vérifie
plus que l'agent (une requête HTTP) : la chaîne complète ne repart que s'il se tait."""
import asyncio
import datetime as dt
import logging
import time

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:                      # Windows sans la base des fuseaux (paquet tzdata) : heure UTC
    PARIS = None

import goios
import lieux
import signature
from goios import ErreurIos
from processus import Processus
from signature import ErreurSignature
from wda import PROFONDEUR, Agent, ErreurAgent

log = logging.getLogger("telephone")

ETAPES = [
    ("branche", "Branché en USB"),
    ("confiance", "Ordinateur approuvé"),
    ("mode_dev", "Mode développeur"),
    ("tunnel", "Tunnel iOS 17+"),
    ("image", "Image développeur"),
    ("agent", "Agent installé"),
    ("pilotage", "Agent lancé"),
    ("ecran", "Écran en direct"),
]

AIDE = {
    "branche": "Rebranche l'iPhone sur le PC avec un câble de données (pas un câble de charge seule).",
    "confiance": "Déverrouille l'iPhone : à « Faire confiance à cet ordinateur ? », touche Se fier, puis tape ton code.",
    "mode_dev": "Sur l'iPhone : Réglages › Confidentialité et sécurité › Mode développeur, active-le. L'iPhone "
                "redémarre : déverrouille-le et touche « Activer ».",
    "image": "Laisse l'iPhone déverrouillé, le PC doit avoir Internet (téléchargement chez Apple la première fois).",
    "agent": "Installe l'agent avec Impactor sur le PC (README, « Installer l'agent »).",
    "confiance_dev": "Sur l'iPhone, connecté à Internet : Réglages › Général › VPN et gestion de l'appareil › ton "
                     "Apple ID (sous « App de développeur ») › « Faire confiance », puis confirmer. Avec un Apple ID "
                     "gratuit, la signature dure 7 jours : refais Impactor à l'échéance.",
    "verrouille": "Déverrouille l'iPhone (ou enlève le code : un téléphone dédié s'en passe).",
    "resigner": "Il faut le certificat exporté d'Impactor (Réglages › Exporter P12) et un profil valide sur l'iPhone "
                "(refais « Installer » dans Impactor s'il a expiré).",
}

# les modèles les plus courants (ProductType → nom) ; les autres s'affichent tels quels
MODELES = {
    "iPhone12,8": "iPhone SE (2e gén.)", "iPhone14,6": "iPhone SE (3e gén.)",
    "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,5": "iPhone 13", "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus", "iPhone15,2": "iPhone 14 Pro",
    "iPhone15,3": "iPhone 14 Pro Max", "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max", "iPhone17,3": "iPhone 16",
    "iPhone17,4": "iPhone 16 Plus", "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,5": "iPhone 16e",
}


def trouver_agent(apps):
    """Le bundle de WebDriverAgent parmi les apps installées : Impactor le renomme (suffixe d'équipe), on le
    reconnaît à son exécutable ou à son nom."""
    for a in apps:
        b = str(a.get("CFBundleIdentifier") or "")
        ex = str(a.get("CFBundleExecutable") or "") + str(a.get("CFBundleName") or "")
        if "WebDriverAgentRunner" in ex or ("WebDriverAgent" in b and b.endswith(".xctrunner")):
            return b
    return None


def cause_agent(proc):
    """Pourquoi l'agent n'a pas démarré, dit à partir de ce que go-ios a écrit. Quand l'iPhone refuse le lancement,
    go-ios ne rapporte que « could not get pid » ; la vraie raison n'est que dans le journal de l'iPhone. Mesuré le
    01/10/2026 : « Needs Explicit User Trust, reason: User hasn't trusted the profile » (développeur pas approuvé)."""
    if proc.dit("not been explicitly trusted", "untrusted", "is not trusted", "0xe8008018", "0xe800801c",
                "could not get pid", "failed to launch app", "deviceprocesscontrolservice"):
        return ("L'iPhone refuse de lancer l'agent : le plus souvent, le développeur n'est pas encore approuvé "
                "(ou la signature de 7 jours a expiré)."), AIDE["confiance_dev"]
    if proc.dit("Failed to load the test bundle"):
        return ("Le module de test de l'agent n'est pas signé (installation par Impactor) : le service le re-signe "
                "tout seul, au plus une fois toutes les 10 min."), AIDE["resigner"]
    if proc.dit("expired", "0xe8008016", "invalid code signature"):
        return "La signature de l'agent a expiré.", AIDE["confiance_dev"]
    if proc.dit("locked", "passcode"):
        return "L'iPhone est verrouillé.", AIDE["verrouille"]
    if proc.dit("developer mode"):
        return "Le mode développeur est coupé.", AIDE["mode_dev"]
    return proc.dernier_message() or "L'agent s'est arrêté sans rien dire.", ""


class Etape:
    def __init__(self, cle, titre):
        self.cle, self.titre = cle, titre
        self.etat, self.message, self.aide, self.le = "attente", "", "", time.time()

    def pose(self, etat, message="", aide=""):
        if (etat, message) != (self.etat, self.message):
            self.le = time.time()
        self.etat, self.message, self.aide = etat, message, aide

    def dict(self):
        return {"cle": self.cle, "titre": self.titre, "etat": self.etat, "message": self.message, "aide": self.aide,
                "le": self.le}


class Telephone:
    def __init__(self, udid, rang, parc):
        self.udid, self.rang, self.parc = udid, rang, parc
        self.port_agent = lieux.PORT_AGENT + rang
        self.port_flux = lieux.PORT_FLUX + rang
        self.agent = Agent(self.port_agent, parc.http)
        self.proc_agent = Processus(f"agent-{rang}", [])
        self.proc_flux = Processus(f"ecran-{rang}", [lieux.IOS, "forward", self.port_flux, 9100, f"--udid={udid}"])
        self.gestes = asyncio.Lock()     # un seul robot (ou geste de la main) à la fois sur l'écran
        self.occupe = None                # « publication n° 12 » pendant qu'un robot travaille
        self._tache = None
        self._reinitialiser()

    def _reinitialiser(self):
        self.etapes = {k: Etape(k, t) for k, t in ETAPES}
        self.infos, self.apps, self.bundle_agent = {}, [], None
        self.ip = None          # l'adresse Wi-Fi de l'iPhone, lue sur l'agent (None : pas de Wi-Fi)
        self.nom = self.udid[:8]
        self.branche, self.pret = True, False
        self.taille = None                # (largeur, hauteur) de l'écran en points
        self.batterie = None
        self.expire = None                # fin de validité du profil de l'agent (Apple ID gratuit : 7 jours)
        self._appaire_le = self._revele_le = self._apps_lues = self._image_ratee = 0
        self._resigne_le = self._profils_lus = 0
        self._silence = None               # depuis quand l'agent ne répond plus

    # ── cycle de vie ─────────────────────────────────────────────────────────────────────────────────────
    def demarrer(self):
        self._tache = asyncio.create_task(self._boucle())

    async def rebrancher(self):
        self._reinitialiser()
        self.demarrer()

    async def debrancher(self):
        if self._tache:
            self._tache.cancel()
        self.branche = self.pret = False
        self.etapes["branche"].pose("ko", "Débranché", AIDE["branche"])
        for k in list(self.etapes)[1:]:
            self.etapes[k].pose("attente")
        self.agent.sid = None
        await self.proc_agent.arreter()
        await self.proc_flux.arreter()

    async def _boucle(self):
        while True:
            try:
                await (self._surveiller() if self.pret else self._preparer())
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("préparation de %s", self.nom)
            await asyncio.sleep(10 if self.pret else 3)

    def version(self):
        try:
            return tuple(int(x) for x in str(self.infos.get("ProductVersion", "0")).split("."))
        except ValueError:
            return (0,)

    def _bloque(self, cle, message, aide=""):
        self.pret = False
        self.etapes[cle].pose("ko", message, aide)
        for k in list(self.etapes)[list(self.etapes).index(cle) + 1:]:
            self.etapes[k].pose("attente")

    def _attend(self, cle, message):
        self.pret = False
        self.etapes[cle].pose("attente", message)

    # ── la chaîne complète ────────────────────────────────────────────────────────────────────────────────
    async def _preparer(self):
        self.etapes["branche"].pose("ok", "Branché en USB")

        try:
            self.infos = await goios.infos(self.udid)
        except ErreurIos:
            if time.time() - self._appaire_le > 20:   # redemande l'appairage toutes les 20 s, pas plus
                self._appaire_le = time.time()
                await goios.appairer(self.udid)
            return self._bloque("confiance", "En attente de ton accord sur l'iPhone", AIDE["confiance"])
        self.nom = self.infos.get("DeviceName") or self.nom
        pt = self.infos.get("ProductType", "")
        self.etapes["confiance"].pose("ok", f"{MODELES.get(pt, pt)} · iOS {self.infos.get('ProductVersion', '?')}")
        v = self.version()

        if v >= (16,):
            dev = await goios.mode_developpeur(self.udid)
            if dev is False:
                if time.time() - self._revele_le > 120:
                    self._revele_le = time.time()
                    await goios.reveler_mode_developpeur(self.udid)
                return self._bloque("mode_dev", "Désactivé", AIDE["mode_dev"])
            self.etapes["mode_dev"].pose("ok", "Activé" if dev else "État inconnu")
        else:
            self.etapes["mode_dev"].pose("inutile", "Pas nécessaire avant iOS 16")

        if v >= (17,):
            self.parc.besoin_tunnel = True
            tun = await self.parc.tunnel_de(self.udid)
            if not tun:
                msg = self.parc.tunnel.dernier_message() if self.parc.tunnel.code is not None else ""
                return self._attend("tunnel", f"Ouverture du tunnel… {msg}".strip())
            self.etapes["tunnel"].pose("ok", "Ouvert" + (" (sans droits administrateur)" if tun.get("userspaceTun") else ""))
        else:
            self.etapes["tunnel"].pose("inutile", "Pas nécessaire avant iOS 17")

        try:
            if not await goios.image_montee(self.udid):
                if time.time() - self._image_ratee < 60:
                    return
                self._attend("image", "Téléchargement et montage (la première fois : quelques minutes)…")
                await goios.monter_image(self.udid)
            self.etapes["image"].pose("ok", "Montée")
        except ErreurIos as e:
            self._image_ratee = time.time()
            return self._bloque("image", f"Échec : {e}", AIDE["image"])

        if not self.bundle_agent or time.time() - self._apps_lues > 300:
            self.apps = await goios.apps(self.udid)
            self._apps_lues = time.time()
            self.bundle_agent = trouver_agent(self.apps)
        if not self.bundle_agent:
            return self._bloque("agent", "Pas installé", AIDE["agent"])
        await self._lire_signature()
        self.etapes["agent"].pose("ok", self._message_agent())

        st = await self.agent.statut()
        if not st:
            p = self.proc_agent
            if not p.vivant:
                if p.tombe and p.dit("Failed to load the test bundle") and time.time() - self._resigne_le > 600:
                    # l'agent posé par Impactor : son module de test n'est pas signé ; on le re-signe (signature.py)
                    self._resigne_le = time.time()
                    self._attend("pilotage", "Module de test de l'agent pas signé (Impactor) : re-signature par le service…")
                    try:
                        profil = await signature.resigner(self.udid, self.bundle_agent)
                    except (ErreurSignature, ErreurIos) as e:
                        return self._bloque("pilotage", f"Re-signature impossible : {e}",
                                            "Dans Impactor : refais « Installer », et vérifie que le certificat est "
                                            "exporté (Réglages › Exporter P12).")
                    self.expire, self._profils_lus = profil["expire"], time.time()
                    self.etapes["agent"].pose("ok", self._message_agent())
                    p.code = None                            # on relance tout de suite
                elif p.tombe:
                    cause, aide = cause_agent(p)
                    self._bloque("pilotage", cause, aide)
                    if time.time() - p.fini_le < 30:     # 30 s entre deux essais : relancer XCTest coûte
                        return
                p.args = [lieux.IOS, "ui", "run", "wda", f"--bundleid={self.bundle_agent}",
                          f"--host-port={self.port_agent}", f"--udid={self.udid}"]
                self.agent.sid = None
                # un ancien agent resté coincé sur l'iPhone empêche le nouveau de démarrer (« cannot initiate a IDE
                # session », mesuré le 02/10/2026 après un blocage dans TikTok) : on l'arrête d'abord
                await goios.ios("kill", self.bundle_agent, udid=self.udid, delai=30)
                await p.demarrer()
            elif p.age() > 90:      # lancé mais muet depuis 90 s : on recommence
                cause, aide = cause_agent(p)
                await p.arreter()
                return self._bloque("pilotage", f"Muet depuis 90 s. {cause}", aide)
            if self.etapes["pilotage"].etat != "ko":
                self._attend("pilotage", "Lancement de l'agent sur l'iPhone…")
            return
        self.ip = (st.get("ios") or {}).get("ip") or None
        self.etapes["pilotage"].pose("ok", "Prêt" + (f" · {self.ip}" if self.ip else ""))

        if not self.proc_flux.vivant:
            await self.proc_flux.demarrer()
            await asyncio.sleep(1)
        if not await port_ouvert(self.port_flux):
            return self._attend("ecran", "Relais de l'écran en cours d'ouverture…")
        self.etapes["ecran"].pose("ok", "En direct")
        if not await self._reglages_agent():
            return self._attend("pilotage", "L'agent ne prend pas ses réglages : nouvel essai…")
        self.pret = True
        self._silence = None
        log.info("%s prêt (agent sur le port %s, écran sur le port %s)", self.nom, self.port_agent, self.port_flux)

    async def _lire_signature(self, tous_les=3600):
        """La date de fin du profil de l'agent, lue sur l'iPhone au plus une fois par heure."""
        if not lieux.PMD3 or time.time() - self._profils_lus < tous_les:
            return
        self._profils_lus = time.time()
        try:
            profil = signature.profil_de(await signature.profils(self.udid), self.bundle_agent)
            self.expire = profil["expire"] if profil else None
        except (ErreurSignature, ErreurIos) as e:
            log.warning("%s : profils illisibles (%s)", self.nom, e)

    def _message_agent(self):
        if not self.expire:
            return self.bundle_agent
        reste = (self.expire - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
        quand = self.expire.astimezone(PARIS).strftime("%d/%m à %H:%M") if PARIS else self.expire.strftime("%d/%m %H:%M UTC")
        if reste < 24:
            return f"Signature valable jusqu'au {quand} : refais « Installer » dans Impactor avant (le service re-signe derrière)."
        return f"Signé jusqu'au {quand}"

    async def _reglages_agent(self):
        """Taille de l'écran (pour convertir un clic en points) et flux : 10 images/s, demi-résolution (la
        qualité est refaite par serveur.py : WebDriverAgent réencode toujours à 90 % au moins)."""
        try:
            e = await self.agent.ecran()
            s = (e or {}).get("screenSize") or {}
            self.taille = (s.get("width"), s.get("height"))
            await self.agent.reglages(mjpegServerFramerate=10, mjpegScalingFactor=50, mjpegServerScreenshotQuality=45,
                                      # apps vidéo (TikTok, Instagram) : elles ne sont jamais « au repos » ; sans ça,
                                      # chaque geste attend ce repos et l'agent se bloque (mesuré le 02/10/2026 sur TikTok)
                                      waitForIdleTimeout=0, animationCoolOffTimeout=0, snapshotMaxDepth=PROFONDEUR)
            return True
        except ErreurAgent as e:
            log.warning("%s : réglages de l'agent impossibles (%s)", self.nom, e)
            return False

    # ── une fois prêt : on surveille l'agent et le relais de l'écran ─────────────────────────────────────────
    async def _surveiller(self):
        st = await self.agent.statut(delai=5)
        if st:   # l'adresse Wi-Fi de l'iPhone (aucune : pas de Wi-Fi, au mieux le réseau mobile)
            self.ip = (st.get("ios") or {}).get("ip") or None
        if st and self.proc_flux.vivant:
            self._silence = None
            try:
                self.batterie = await self.agent.batterie()
            except ErreurAgent:
                pass
            if not self.occupe:
                await self._lire_signature()
                self.etapes["agent"].pose("ok", self._message_agent())
            return
        if st and not self.proc_flux.vivant:
            await self.proc_flux.demarrer()
            return
        if self.occupe:                 # un robot travaille : l'agent peut être lent quelques secondes
            return
        self._silence = self._silence or time.time()
        if time.time() - self._silence > 20:
            log.warning("%s : l'agent ne répond plus depuis 20 s, on reprend la préparation", self.nom)
            self.pret = False
            self.etapes["pilotage"].pose("attente", "L'agent ne répond plus : relance…")
            await self.proc_agent.arreter()

    async def relancer_agent(self):
        self.pret = False
        self._apps_lues = 0
        await self.proc_agent.arreter()
        await self.proc_flux.arreter()

    # ── ce que l'interface affiche ──────────────────────────────────────────────────────────────────────
    def dict(self):
        pt = self.infos.get("ProductType", "")
        return {
            "udid": self.udid, "rang": self.rang, "nom": self.nom, "modele": MODELES.get(pt, pt), "ios": self.infos.get("ProductVersion"),
            "branche": self.branche, "pret": self.pret, "occupe": self.occupe, "taille": self.taille, "ip": self.ip, "wifi": bool(self.ip),
            "batterie": self.batterie, "agent": self.bundle_agent, "expire": self.expire.isoformat() if self.expire else None,
            "etapes": [e.dict() for e in self.etapes.values()],
            "apps": sorted({a.get("CFBundleIdentifier") for a in self.apps if a.get("CFBundleIdentifier")}),
        }


async def port_ouvert(port, delai=2):
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), delai)
        w.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False
