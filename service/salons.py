"""salons.py : les messages du service sur Discord, sur ton serveur. Un webhook par salon, rangé dans
secrets\\discord.env (jamais affiché) :

  DISCORD_SANTE         🩺・santé-pages      alertes des pages : 0 vue, shadowban probable, chute, compte déconnecté, échecs
  DISCORD_RAPPORT       📊・rapport-du-jour  le bilan du soir de chaque page
  DISCORD_PUBLICATIONS  📤・publications     chaque publication (complétée par son lien quand il arrive), chaque échec
  DISCORD_TELEPHONES    🛠️・téléphones      les pannes : iPhone hors ligne, agent à re-signer, crédits Scrape Creators bas
  DISCORD_WARMUP        🔥・warm-up          le résumé de chaque séance de warm-up

Sans le fichier, rien ne part : le service marche pareil. Un envoi raté est noté au journal, jamais bloquant (les
messages partent à côté, dans leur propre tâche)."""
import asyncio
import logging

import aiohttp

import lieux

log = logging.getLogger("discord")
SALONS = ("SANTE", "RAPPORT", "PUBLICATIONS", "TELEPHONES", "WARMUP")
ROUGE, ORANGE, VERT, GRIS = 0xFF453A, 0xFF9F0A, 0x30D158, 0x8E8E93


def webhooks():
    """{SALON: adresse du webhook}, lus dans secrets\\discord.env."""
    out = {}
    try:
        for ligne in (lieux.SECRETS / "discord.env").read_text(encoding="utf-8-sig").splitlines():
            k, _, v = ligne.strip().partition("=")
            if k.startswith("DISCORD_") and k[8:] in SALONS and v.strip().startswith("http"):
                out[k[8:]] = v.strip()
    except OSError:
        pass
    return out


class Discord:
    def __init__(self, http):
        self.http = http
        self.urls = webhooks()
        self.taches = set()
        if self.urls:
            log.info("Discord : %s salon(s) branché(s) (%s)", len(self.urls), ", ".join(self.urls))

    def actif(self, salon):
        return salon in self.urls

    async def _requete(self, methode, url, corps):
        for _ in range(4):
            try:
                async with self.http.request(methode, url, json=corps, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429:
                        d = await r.json(content_type=None)
                        await asyncio.sleep(float((d or {}).get("retry_after", 1)) + 0.3)
                        continue
                    if r.status >= 400:
                        log.warning("Discord : %s %s", r.status, (await r.text())[:200])
                        return None
                    return await r.json(content_type=None) if r.status != 204 else None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning("Discord injoignable : %s", e)
                return None
        return None

    async def poster(self, salon, texte=None, embeds=None):
        """Poste dans le salon ; rend l'identifiant du message (pour le compléter ensuite), ou None."""
        url = self.urls.get(salon)
        if not url:
            return None
        corps = {"username": "Téléphones auto", "allowed_mentions": {"parse": []}}
        if texte:
            corps["content"] = texte[:2000]
        if embeds:
            corps["embeds"] = embeds[:10]
        d = await self._requete("POST", url + "?wait=true", corps)
        return (d or {}).get("id")

    async def modifier(self, salon, message_id, texte=None, embeds=None):
        url = self.urls.get(salon)
        if not url or not message_id:
            return
        corps = {"allowed_mentions": {"parse": []}}
        if texte is not None:
            corps["content"] = texte[:2000]
        if embeds is not None:
            corps["embeds"] = embeds[:10]
        await self._requete("PATCH", f"{url}/messages/{message_id}", corps)

    def envoyer(self, salon, texte=None, embeds=None, apres=None):
        """Poste sans attendre (une tâche à côté) ; `apres(message_id)` est appelé une fois le message posté."""
        if not self.actif(salon):
            return

        async def tache():
            mid = await self.poster(salon, texte, embeds)
            if apres and mid:
                try:
                    apres(mid)
                except Exception as e:
                    log.warning("après l'envoi Discord : %s", e)

        t = asyncio.create_task(tache())
        self.taches.add(t)
        t.add_done_callback(self.taches.discard)

    def completer(self, salon, message_id, texte=None, embeds=None):
        if not self.actif(salon) or not message_id:
            return
        t = asyncio.create_task(self.modifier(salon, message_id, texte, embeds))
        self.taches.add(t)
        t.add_done_callback(self.taches.discard)


PLATEFORME = {"tiktok": "TikTok", "instagram": "Insta", "youtube": "YouTube"}


def ligne_compte(plateforme, identifiant, groupe=None):
    return f"{PLATEFORME.get(plateforme, plateforme)} **@{identifiant}**" + (f" · {groupe}" if groupe else "")
