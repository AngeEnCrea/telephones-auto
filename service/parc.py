"""parc.py : les iPhone branchés sur le PC. Toutes les 3 s, demande au pilote Apple qui est là ; un nouveau venu a
son rang (donc ses ports) pour toujours, gardé dans rangs.json : le téléphone n° 0 reste sur les mêmes ports après
un redémarrage. Tient aussi le tunnel iOS 17+ de go-ios, un seul pour tous les téléphones, sans droits
administrateur (--userspace)."""
import asyncio
import json
import logging
import time

import goios
import lieux
from appareil import Telephone
from goios import ErreurIos
from processus import Processus

log = logging.getLogger("parc")


class Parc:
    def __init__(self, http):
        self.http = http
        self.telephones = {}
        self.pilote = {"etat": "attente", "message": "Démarrage…"}
        self.tunnel = Processus("tunnel", [lieux.IOS, "tunnel", "start", "--userspace",
                                           f"--pair-record-path={lieux.APPAIRAGE}"])
        self.besoin_tunnel = False
        self._tunnels, self._tunnels_lus = {}, 0
        self._fichier_rangs = lieux.DONNEES / "rangs.json"
        try:
            self.rangs = json.loads(self._fichier_rangs.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.rangs = {}

    def rang_de(self, udid):
        if udid not in self.rangs:
            self.rangs[udid] = max(self.rangs.values(), default=-1) + 1
            self._fichier_rangs.parent.mkdir(parents=True, exist_ok=True)
            self._fichier_rangs.write_text(json.dumps(self.rangs, indent=1), encoding="utf-8")
        return self.rangs[udid]

    def telephone(self, udid):
        return self.telephones.get(udid)

    def premier_pret(self):
        return next((t for t in self.telephones.values() if t.pret), None)

    async def boucle(self):
        while True:
            try:
                await self._tour()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("tour du parc")
            await asyncio.sleep(3)

    async def _tour(self):
        try:
            udids = await goios.udids()
            self.pilote = {"etat": "ok", "message": "Pilote Apple en marche"}
        except ErreurIos as e:
            self.pilote = {"etat": "ko", "message": f"Le pilote Apple ne répond pas ({e})",
                           "aide": "Service « Apple Mobile Device Service » arrêté ? Redémarre le PC ou relance le service."}
            udids = []
        for u in udids:
            t = self.telephones.get(u)
            if t is None:
                t = self.telephones[u] = Telephone(u, self.rang_de(u), self)
                log.info("nouvel iPhone branché : %s (rang %s)", u, t.rang)
                t.demarrer()
            elif not t.branche:
                log.info("iPhone rebranché : %s", t.nom)
                await t.rebrancher()
        for u, t in self.telephones.items():
            if u not in udids and t.branche:
                log.info("iPhone débranché : %s", t.nom)
                await t.debrancher()
        if self.besoin_tunnel and not self.tunnel.vivant and (not self.tunnel.fini_le or time.time() - self.tunnel.fini_le > 10):
            lieux.APPAIRAGE.mkdir(parents=True, exist_ok=True)
            await self.tunnel.demarrer()

    async def tunnel_de(self, udid):
        if time.time() - self._tunnels_lus > 3:
            self._tunnels = {t.get("udid"): t for t in await goios.tunnels()}
            self._tunnels_lus = time.time()
        return self._tunnels.get(udid)

    async def arreter(self):
        for t in self.telephones.values():
            await t.debrancher()
        await self.tunnel.arreter()

    def dict(self):
        return {"pilote": self.pilote,
                "tunnel": {"vivant": self.tunnel.vivant, "besoin": self.besoin_tunnel,
                           "message": self.tunnel.dernier_message() if self.tunnel.tombe else ""},
                "telephones": [t.dict() for t in sorted(self.telephones.values(), key=lambda t: t.rang)]}
