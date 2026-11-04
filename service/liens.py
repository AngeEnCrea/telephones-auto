"""liens.py : retrouver le lien d'une vidéo que le téléphone vient de publier, par Scrape Creators, avec la clé du
donnees/secrets/scrapecreators.env (réglage « secrets », jamais affichée ; sans elle, pas de lien), EN ARRIÈRE-PLAN :
le téléphone passe tout de suite à la publication suivante. Sur TikTok, l'écran de lecture d'une vidéo est trop
lourd pour l'agent ; sur Instagram, le compteur de publications du profil ne bouge pas (775 avant comme après, vu le
04/10/2026). Les dernières vidéos du compte, elles, donnent la légende et l'heure de chacune : on reconnaît la nôtre
à sa légende, publiée après le début de la publication. Coût : 1 à 4 crédits par vidéo."""
import asyncio
import json
import logging
import os
import urllib.parse

import aiohttp

import lieux
from recettes.base import pareil

log = logging.getLogger("liens")
SCRAPE = os.environ.get("TELEPHONES_SCRAPE") or "https://api.scrapecreators.com/"     # les essais branchent un faux
ATTENTES = tuple(int(x) for x in (os.environ.get("TELEPHONES_ATTENTES_LIENS") or "45,90,180").split(","))


def cle():
    """La clé Scrape Creators : celle des téléphones (scrapecreators-telephones.env, une clé à part, 08/10/2026), sinon
    celle du suivi des vues (scrapecreators.env)."""
    for nom in ("scrapecreators-telephones.env", "scrapecreators.env"):
        try:
            for ligne in (lieux.SECRETS / nom).read_text(encoding="utf-8-sig").splitlines():
                k, _, v = ligne.strip().partition("=")
                if k.strip() == "SCRAPECREATORS_API_KEY" and v.strip():
                    return v.strip()
        except OSError:
            continue
    return None


async def _get(http, chemin, k):
    async with http.get(SCRAPE + chemin, headers={"x-api-key": k}, timeout=aiohttp.ClientTimeout(total=120)) as r:
        if r.status != 200:
            raise RuntimeError(f"Scrape Creators : HTTP {r.status}")
        return json.loads(await r.text())


FENETRE_S = 2 * 3600     # un post vient de la publication s'il sort dans les 2 h qui suivent son départ


def choisir_post(posts, depuis, legende, pris=()):
    """Le post de NOTRE publication parmi les derniers d'un compte ([(ts, desc, lien)]) : le plus ancien sorti après son
    départ (2 min de marge) et dans les 2 h, de même légende, pas déjà rattaché à une autre publication. Le plus ancien,
    pas le premier de la liste (le plus récent) : avec une légende commune à toutes les publications (Instagram :
    « @moncompte » depuis le 09/10/2026), le premier venu serait le dernier reel du compte, pas le nôtre."""
    bons = sorted((x for x in posts if depuis - 120 <= x[0] <= depuis + FENETRE_S and x[2] not in pris
                   and (not legende or meme_legende(x[1], legende))), key=lambda x: x[0])
    return bons[0][2] if bons else None


def meme_legende(desc, legende):
    """La légende publiée commence comme la nôtre (TikTok peut couper ou réordonner les hashtags en fin de texte)."""
    a, b = pareil(desc).lower(), pareil(legende).lower()
    return bool(b) and a[:40] == b[:40]


async def lien_instagram(handle, legende, depuis, attentes=ATTENTES, pris=()):
    """Le lien du reel de @handle publié après `depuis` avec cette légende (les 12 derniers posts du profil)."""
    k = cle()
    if not k:
        log.warning("pas de clé Scrape Creators (secrets\\scrapecreators.env) : lien Instagram à coller à la main")
        return None
    h = urllib.parse.quote(handle.lstrip("@"))
    async with aiohttp.ClientSession() as http:
        for attente in attentes:
            await asyncio.sleep(attente)
            try:
                d = await _get(http, f"v1/instagram/profile?handle={h}&trim=true", k)
            except Exception as e:
                log.warning("profil Instagram @%s : %s", handle, e)
                continue
            u = (d.get("data") or {}).get("user") or {}
            posts = []
            for bord in (u.get("edge_owner_to_timeline_media") or {}).get("edges") or []:
                n = bord.get("node") or {}
                if not n.get("shortcode"):
                    continue
                texte = ((((n.get("edge_media_to_caption") or {}).get("edges") or [{}])[0].get("node") or {}).get("text") or "")
                genre = "reel" if n.get("product_type") == "clips" else "p"
                posts.append((n.get("taken_at_timestamp") or 0, texte, f"https://www.instagram.com/{genre}/{n['shortcode']}/"))
            lien = choisir_post(posts, depuis, legende, pris)
            if lien:
                return lien
    return None


async def retrouver(plateforme, handle, legende, depuis, pris=()):
    if plateforme == "tiktok":
        return await lien_tiktok(handle, legende, depuis, pris=pris)
    if plateforme == "instagram":
        return await lien_instagram(handle, legende, depuis, pris=pris)
    return None


async def lien_tiktok(handle, legende, depuis, attentes=ATTENTES, pris=()):
    """Le lien de la vidéo de @handle publiée après `depuis` (horodatage) avec cette légende ; sans légende, la plus
    récente publiée après `depuis`. None si la clé manque ou si elle n'apparaît pas (vérification à la main)."""
    k = cle()
    if not k:
        log.warning("pas de clé Scrape Creators (secrets\\scrapecreators.env) : lien TikTok à coller à la main")
        return None
    h = urllib.parse.quote(handle.lstrip("@"))
    async with aiohttp.ClientSession() as http:
        try:
            uid = ((await _get(http, f"v1/tiktok/profile?handle={h}", k)).get("user") or {}).get("id") or ""
        except Exception as e:
            log.warning("profil TikTok @%s : %s", handle, e)
            uid = ""
        for attente in attentes:
            await asyncio.sleep(attente)
            try:
                d = await _get(http, f"v3/tiktok/profile/videos?handle={h}&user_id={uid}&sort_by=latest&trim=true", k)
            except Exception as e:
                log.warning("vidéos TikTok @%s : %s", handle, e)
                continue
            lien = choisir_post([(v.get("create_time") or 0, v.get("desc") or "", f"https://www.tiktok.com/@{handle.lstrip('@')}/video/{v['aweme_id']}")
                                 for v in d.get("aweme_list") or [] if v.get("aweme_id")], depuis, legende, pris)
            if lien:
                return lien
    return None
