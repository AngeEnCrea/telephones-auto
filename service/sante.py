"""sante.py : la santé des pages et des téléphones, et ses alertes sur Discord.

- **Le relevé** (8 h et 21 h 45, heure de Paris, ou à la main depuis le hub) : pour chaque compte actif TikTok et
  Instagram rattaché à un téléphone, ses derniers posts et leurs vues, par Scrape Creators (un appel par compte : TikTok
  v3/profile/videos, Instagram v1/profile), gardés par jour (table releves). Au passage, les liens qui manquaient à nos
  publications sont retrouvés (même légende, publiée après le départ).
- **Les règles**, compte par compte, sur le dernier relevé : shadowban probable (médiane sous 30 vues sur au moins 3
  posts de 24 h à 7 jours : la règle habituelle) ; zéro vue (tous les posts de 12 h à 48 h à 0) ; chute (la
  médiane des posts de 1 à 3 jours sous 40 % de celle des posts de 3 à 10 jours, quand celle-ci fait au moins 100).
  Et, à chaque publication ratée (publication.py) : 2 échecs d'affilée, ou un compte qui n'est plus connecté dans
  l'app. → 🩺 santé-pages, une fois par compte, par type et par jour.
- **Le rapport du soir** (après le relevé de 21 h 45) : 📊 rapport-du-jour, une carte par page (groupe).
- **La vigie** (chaque minute) : un iPhone hors ligne plus de 30 min entre 9 h et 23 h, l'agent qui expire dans moins de
  24 h, une batterie sous 20 % sans charger, les crédits Scrape Creators sous 300 → 🛠️ téléphones.
Sans clé Scrape Creators, pas de relevé (le hub le dit) : la vigie et les alertes d'échecs marchent quand même."""
import asyncio
import datetime as dt
import logging
import os
import statistics
import time
import urllib.parse
from zoneinfo import ZoneInfo

import liens
import salons

log = logging.getLogger("sante")
PARIS = ZoneInfo("Europe/Paris")
RELEVES = ((8, 0, "matin"), (21, 45, "soir"))
SHADOWBAN_VUES, SHADOWBAN_POSTS = 30, 3
CHUTE, CHUTE_MIN, CHUTE_POSTS, CHUTE_HABITUDE, PEPITE = 0.4, 100, 4, 10, 3
CHUTE_JOURS = 30
DIAGNOSTICS = {"shadowban", "zero_vue", "chute"}    # les types que diagnostic() calcule sur chaque relevé
HORS_LIGNE_MIN = float(os.environ.get("TELEPHONES_HORS_LIGNE_MIN") or 30)
TOUR_S = float(os.environ.get("TELEPHONES_SANTE_S") or 60)      # la vigie tourne chaque minute (les essais : 1 s)
JOURNEE = (9, 23)
CREDITS_BAS = 300
H = 3600


def jour_paris(t=None):
    return (t or dt.datetime.now(dt.timezone.utc)).astimezone(PARIS).date().isoformat()


def il_y_a(jours):
    """Le jour de Paris d'il y a tant de jours (AAAA-MM-JJ), pour lire les relevés gardés depuis."""
    return (dt.datetime.now(PARIS).date() - dt.timedelta(days=jours)).isoformat()


def maintenant_utc():
    return dt.datetime.now(dt.timezone.utc)


def nombre(n):
    return f"{n:,}".replace(",", " ") if isinstance(n, int) else "—"


def alerter(stock, discord, cle, type_, niveau, titre, details, salon="SANTE"):
    """Une alerte, une seule fois par sujet, par type et par jour : notée (le hub la montre) et postée sur Discord."""
    if not stock.noter_alerte(cle, type_, niveau, f"{titre} — {details}", jour_paris()):
        return False
    log.warning("alerte %s %s : %s — %s", cle, type_, titre, details)
    discord.envoyer(salon, embeds=[{"color": salons.ROUGE if niveau == "rouge" else salons.ORANGE, "title": titre[:250],
                                    "description": details[:3900]}])
    return True


# ── la lecture des comptes (Scrape Creators) ────────────────────────────────────────────────────────────────────────
async def lire_compte(http, plateforme, handle, k):
    """(abonnés, [{id, vues, ts, desc, lien}]) : les derniers posts d'un compte, du plus récent au plus ancien."""
    h = urllib.parse.quote(handle.lstrip("@"))
    if plateforme == "tiktok":
        d = await liens._get(http, f"v3/tiktok/profile/videos?handle={h}", k)
        l = d.get("aweme_list") or []
        abonnes = ((l[0].get("author") or {}).get("follower_count")) if l else None
        posts = [{"id": str(v.get("aweme_id")), "vues": int((v.get("statistics") or {}).get("play_count") or 0),
                  "ts": int(v.get("create_time") or 0), "desc": (v.get("desc") or "")[:200],
                  "lien": f"https://www.tiktok.com/@{handle}/video/{v.get('aweme_id')}"} for v in l]
    else:
        d = await liens._get(http, f"v1/instagram/profile?handle={h}", k)
        u = ((d.get("data") or {}).get("user")) or {}
        if not u:
            raise RuntimeError("compte introuvable")
        abonnes = (u.get("edge_followed_by") or {}).get("count")
        posts = []
        for e in (u.get("edge_owner_to_timeline_media") or {}).get("edges") or []:
            n = e.get("node") or {}
            if n.get("is_video") is False:      # une photo : pas de vues (elle fausserait « zéro vue »)
                continue
            legende = ((n.get("edge_media_to_caption") or {}).get("edges") or [{}])[0].get("node", {}).get("text", "")
            posts.append({"id": n.get("shortcode"), "vues": int(n.get("video_play_count") or n.get("video_view_count") or 0),
                          "ts": int(n.get("taken_at_timestamp") or 0), "desc": (legende or "")[:200],
                          "lien": f"https://www.instagram.com/reel/{n.get('shortcode')}/"})
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return abonnes, posts


def vues_j1(releves):
    """Les vues de chaque post au premier relevé gardé où il avait de 24 h à 72 h (un relevé par jour) : {id: (ts, vues)}.
    Comparer les posts au même âge : un post de 30 h n'a pas fini de monter, un de 5 jours si."""
    out = {}
    for r in releves:
        t = dt.datetime.fromisoformat(r["releve_le"].replace("Z", "+00:00")).timestamp()
        for p in r["posts"] or []:
            if p["id"] not in out and H * 24 < t - p["ts"] < H * 72:
                out[p["id"]] = (p["ts"], p["vues"])
    return out


def diagnostic(posts, maintenant=None, historique=()):
    """Les soucis d'un compte d'après ses posts (le dernier relevé) et ses relevés gardés du mois (historique, dans l'ordre) :
    [(type, niveau, titre, détails)]."""
    t = (maintenant or time.time())
    age = lambda p: t - p["ts"]  # noqa: E731
    out = []
    semaine = [p for p in posts if H * 24 < age(p) < H * 24 * 7]
    if len(semaine) >= SHADOWBAN_POSTS:
        m = statistics.median(p["vues"] for p in semaine)
        if m < SHADOWBAN_VUES:
            out.append(("shadowban", "rouge", "Shadowban probable",
                        f"médiane de {m:g} vues sur ses {len(semaine)} posts de plus de 24 h (7 derniers jours)"))
    recents = [p for p in posts if H * 12 < age(p) < H * 48]
    if recents and all(p["vues"] == 0 for p in recents):
        out.append(("zero_vue", "rouge", "Zéro vue", f"0 vue sur ses {len(recents)} posts de 12 h à 48 h"))
    # La chute : les vues au bout d'un jour des posts des 3 derniers jours contre celles des posts du mois au même âge.
    # (29/10/2026 : l'ancienne règle comparait des posts de 1 à 3 jours, pas finis, aux 3 seuls posts de plus de 3 jours
    # que rend Instagram (les 12 derniers), dont 2 pépites, et alertait sur Insta @mapage le jour de son reel à 18 000.)
    j1 = vues_j1(historique)
    jeunes = [v for ts, v in j1.values() if t - ts < H * 72]
    habitude = [v for ts, v in j1.values() if H * 96 < t - ts < H * 24 * CHUTE_JOURS]
    if len(jeunes) >= CHUTE_POSTS and len(habitude) >= CHUTE_HABITUDE:
        mj, mh = statistics.median(jeunes), statistics.median(habitude)
        pepite = any(p["vues"] >= PEPITE * mh for p in posts if age(p) < H * 72)    # un post qui part : la portée est là
        if mh >= CHUTE_MIN and mj < CHUTE * mh and not pepite:
            out.append(("chute", "orange", "Chute des vues",
                        f"médiane de {nombre(int(mj))} vues au bout d'un jour sur ses {len(jeunes)} derniers posts, "
                        f"contre {nombre(int(mh))} d'habitude (ses {len(habitude)} posts du mois, au même âge)"))
    return out


def projet_principal(stock):
    """Le projet des comptes clips (le projet principal) : le bilan et les alertes Discord (son serveur) ne parlent que de lui."""
    return stock.reglage("projet_principal", "perso") or "perso"


def du_projet(stock, c, projet=None):
    """Le compte compte-t-il pour ce projet (le projet principal par défaut) ? Un compte encore sans projet (neuf, en warm-up) est un
    compte clip du projet principal. (25/10/2026 : les comptes d'un autre projet s'étaient mêlés aux vues des pages du projet principal.)"""
    projet = projet or projet_principal(stock)
    return (c["projet"] or "") == projet or (not c["projet"] and projet == projet_principal(stock))


def vues_par_jour(stock, depuis_jour, projet=None):
    """Les vues gagnées chaque jour par les comptes des pages : d'un relevé gardé au suivant (le dernier du jour, 21 h 45 d'habitude), la
    hausse des vues de chaque post déjà vu, plus toutes les vues des posts apparus depuis ; au premier relevé d'un compte,
    ses posts de moins de 24 h seulement. Un post sorti des derniers relevés (Insta : les 12 derniers) ne compte plus.
    Rend {jour: {"tiktok": vues, "instagram": vues, "comptes": comptes relevés ce jour-là}}."""
    veille = (dt.date.fromisoformat(depuis_jour) - dt.timedelta(days=1)).isoformat()   # le point de départ du 1er jour
    jours = {}
    for c in stock.comptes():
        if c["plateforme"] not in ("tiktok", "instagram") or not du_projet(stock, c, projet):
            continue
        prec = None
        for r in stock.releves(c["id"], veille):
            if not r["posts"]:
                continue
            t = dt.datetime.fromisoformat(r["releve_le"].replace("Z", "+00:00")).timestamp()
            if prec is None:
                gain = sum(p["vues"] for p in r["posts"] if t - p["ts"] < 24 * H)
            else:
                avant = {p["id"]: p["vues"] for p in prec[1]["posts"]}
                gain = sum(max(0, p["vues"] - avant[p["id"]]) if p["id"] in avant else p["vues"] if p["ts"] >= prec[0] - H else 0
                           for p in r["posts"])
            prec = (t, r)
            if r["jour"] >= depuis_jour:
                j = jours.setdefault(r["jour"], {"tiktok": 0, "instagram": 0, "comptes": 0})
                j[c["plateforme"]] += gain
                j["comptes"] += 1
    return jours


async def relever(publieur, quand="à la main"):
    """Un relevé de tous les comptes : vues, liens manquants, alertes. Rend un bilan."""
    stock, http, discord = publieur.stock, publieur.http, publieur.discord
    k = liens.cle()
    bilan = {"comptes": 0, "erreurs": [], "alertes": 0, "liens": 0, "sans_cle": not k}
    if not k:
        log.info("relevé %s : pas de clé Scrape Creators", quand)
        return bilan
    jour = jour_paris()
    for c in stock.comptes():
        if not c["actif"] or not c["udid"] or c["plateforme"] not in ("tiktok", "instagram"):
            continue
        bilan["comptes"] += 1
        try:
            abonnes, posts = await lire_compte(http, c["plateforme"], c["identifiant"], k)
        except Exception as e:
            if any(f"HTTP {x}" in str(e) for x in (401, 402, 403)):    # clé refusée ou plus de crédits : inutile d'insister
                bilan["erreurs"].append(f"Scrape Creators refuse la clé ou n'a plus de crédits ({e}) : relevé arrêté")
                break
            bilan["erreurs"].append(f"{salons.PLATEFORME[c['plateforme']]} @{c['identifiant']} : {e}")
            stock.noter_releve(c["id"], jour, None, [], str(e)[:300])
            continue
        stock.noter_releve(c["id"], jour, abonnes, posts[:40])
        bilan["liens"] += retrouver_liens(publieur, c, posts)
        if not du_projet(stock, c):
            continue                  # un autre projet : relevé et liens, mais pas d'alerte sur le Discord du projet principal
        for type_, niveau, titre, details in diagnostic(posts, historique=stock.releves(c["id"], il_y_a(CHUTE_JOURS))):
            if alerter(stock, discord, f"compte:{c['id']}", type_, niveau,
                       f"{'🔴' if niveau == 'rouge' else '🟠'} {titre} · {salons.PLATEFORME[c['plateforme']]} @{c['identifiant']}",
                       details + (f"\nPage : {c['groupe']}" if c["groupe"] else "")):
                bilan["alertes"] += 1
    log.info("relevé %s : %s compte(s), %s alerte(s), %s lien(s) retrouvé(s), %s erreur(s)", quand, bilan["comptes"],
             bilan["alertes"], bilan["liens"], len(bilan["erreurs"]))
    if bilan["erreurs"]:          # une fois par jour au plus (tant que la clé n'a plus de crédits, pas un message par relevé)
        alerter(stock, discord, "scrape", "releve", "orange", "⚠️ Relevé des pages : comptes illisibles",
                "\n".join("• " + x for x in bilan["erreurs"][:15]), salon="TELEPHONES")
    return bilan


def retrouver_liens(publieur, compte, posts):
    """Les liens qui manquent à nos publications publiées de ce compte, retrouvés dans le relevé (même légende)."""
    n = 0
    miennes = publieur.stock.dernieres_publications(compte["id"], 30)
    pris = {p["lien"] for p in miennes if p["lien"]}
    candidats = [(x["ts"], x["desc"], x["lien"]) for x in posts]
    for p in sorted(miennes, key=lambda p: p["debut"] or p["cree_le"]):     # les plus anciennes d'abord
        if p["etat"] != "publie" or p["lien"]:
            continue
        depuis = dt.datetime.fromisoformat((p["debut"] or p["cree_le"]).replace("Z", "+00:00")).timestamp()
        lien = liens.choisir_post(candidats, depuis, p["legende"], pris)
        if lien:
            pris.add(lien)
            publieur.stock.maj_publication(p["id"], lien=lien)
            publieur.stock.etape(p["id"], f"En ligne (retrouvé au relevé) : {lien}")
            publieur.annoncer_lien(p["id"], lien)
            n += 1
    return n


def rapport(publieur):
    """Le bilan du soir sur 📊 rapport-du-jour : une carte par page (groupe de comptes)."""
    stock, discord = publieur.stock, publieur.discord
    if not discord.actif("RAPPORT"):
        return
    debut = dt.datetime.combine(dt.datetime.now(PARIS).date(), dt.time(0, 0), tzinfo=PARIS).astimezone(dt.timezone.utc)
    pubs = stock.publications_du_jour(debut.strftime("%Y-%m-%dT%H:%M:%SZ"))
    pages, total_ok, total_ko, vues_24h = {}, 0, 0, 0
    hier = (dt.datetime.now(PARIS).date() - dt.timedelta(days=1)).isoformat()
    for c in stock.comptes():
        if not c["actif"] or not c["udid"] or not du_projet(stock, c):
            continue
        miennes = [p for p in pubs if p["compte_id"] == c["id"]]
        ok, ko = sum(p["etat"] == "publie" for p in miennes), sum(p["etat"] == "echec" for p in miennes)
        total_ok, total_ko = total_ok + ok, total_ko + ko
        rel = stock.releves(c["id"], hier)
        dernier = rel[-1] if rel else None
        posts = dernier["posts"] if dernier else []
        v24 = sum(p["vues"] for p in posts if time.time() - p["ts"] < H * 24)
        vues_24h += v24
        semaine = [p["vues"] for p in posts if H * 24 < time.time() - p["ts"] < H * 24 * 7]
        delta = ""
        if dernier and len(rel) >= 2 and rel[-2]["abonnes"] is not None and dernier["abonnes"] is not None:
            d = dernier["abonnes"] - rel[-2]["abonnes"]
            delta = f" ({'+' if d >= 0 else ''}{d})"
        soucis = diagnostic(posts, historique=stock.releves(c["id"], il_y_a(CHUTE_JOURS))) if posts else []
        etat = "🔴" if any(n == "rouge" for _, n, _, _ in soucis) else "🟠" if soucis else "🟢" if dernier else "⚪"
        valeur = (f"{etat} {ok} ✅{f' · {ko} ❌' if ko else ''} · 👀 {nombre(v24)} vues (24 h)"
                  + (f" · médiane 7 j : {nombre(int(statistics.median(semaine)))}" if semaine else "")
                  + (f" · 👥 {nombre(dernier['abonnes'])}{delta}" if dernier and dernier["abonnes"] is not None else ""))
        pages.setdefault(c["groupe"] or "Sans page", []).append({"name": f"{salons.PLATEFORME[c['plateforme']]} @{c['identifiant']}",
                                                                 "value": valeur[:1000], "inline": False})
    jour = dt.datetime.now(PARIS).strftime("%d/%m")
    embeds = [{"color": salons.GRIS, "title": f"📄 {nom}", "fields": champs[:25]} for nom, champs in sorted(pages.items())]
    entete = f"📊 **Bilan du {jour}** : {total_ok} publication(s) en ligne, {total_ko} ratée(s) · 👀 {nombre(vues_24h)} vues sur 24 h"
    if not embeds:
        discord.envoyer("RAPPORT", entete + "\n(aucune page active)")
        return
    for i in range(0, len(embeds), 10):
        discord.envoyer("RAPPORT", entete if i == 0 else None, embeds=embeds[i:i + 10])


async def credits(publieur):
    """Les crédits Scrape Creators qui restent (None sans clé ou sans réponse) ; sous 300 : 🛠️ téléphones."""
    k = liens.cle()
    if not k:
        return None
    try:
        d = await liens._get(publieur.http, "v1/credit-balance", k)
        n = int(d.get("creditCount"))
    except Exception as e:
        log.warning("crédits Scrape Creators illisibles : %s", e)
        return None
    publieur.stock.poser_reglage("scrape_credits", str(n))
    if n < CREDITS_BAS:
        alerter(publieur.stock, publieur.discord, "scrape", "credits", "orange", "🟠 Crédits Scrape Creators bas",
                f"il en reste {nombre(n)} : les liens et les vues des pages s'arrêtent à 0. À recharger.", salon="TELEPHONES")
    return n


class Vigie:
    """Les téléphones, chaque minute : hors ligne trop longtemps, agent bientôt expiré, batterie faible."""

    def __init__(self, publieur):
        self.p = publieur
        self.hors_ligne = {}      # udid → (depuis quand il n'est plus prêt : monotonic, heure UTC)
        self.signale = set()      # udid signalés hors ligne (pour annoncer leur retour)

    def tour(self):
        maintenant_ = maintenant_utc()
        heure = maintenant_.astimezone(PARIS).hour
        for t in list(self.p.parc.telephones.values()):
            cle = f"telephone:{t.udid}"
            if t.pret:
                self.hors_ligne.pop(t.udid, None)
                if t.udid in self.signale:
                    self.signale.discard(t.udid)
                    self.p.discord.envoyer("TELEPHONES", f"🟢 **{t.nom}** est de nouveau prêt : la file repart.")
            else:
                debut, depuis = self.hors_ligne.setdefault(t.udid, (time.monotonic(), maintenant_))
                if time.monotonic() - debut >= HORS_LIGNE_MIN * 60 and JOURNEE[0] <= heure < JOURNEE[1]:
                    bloque = next((e for e in t.etapes.values() if e.etat in ("ko", "attente")), None)
                    # une alerte par panne (pas une par jour : deux pannes le même jour, deux alertes)
                    if alerter(self.p.stock, self.p.discord, f"{cle}:{depuis.strftime('%H%M%S')}", "hors_ligne", "rouge",
                               f"📵 {t.nom} hors ligne",
                               f"plus prêt depuis {int((time.monotonic() - debut) / 60)} min"
                               + (f" : {bloque.titre} — {bloque.message}" if bloque else "")
                               + (f"\n{bloque.aide}" if bloque and bloque.aide else ""), salon="TELEPHONES"):
                        self.signale.add(t.udid)
            if t.expire:
                reste = (t.expire - maintenant_).total_seconds() / H
                if reste < 24:
                    alerter(self.p.stock, self.p.discord, cle, "signature", "orange", f"🟠 L'agent de {t.nom} expire bientôt",
                            f"dans {max(0, int(reste))} h : refais « Installer » dans Impactor (le service re-signe derrière).",
                            salon="TELEPHONES")
            b = t.batterie or {}
            if isinstance(b.get("level"), (int, float)) and b["level"] < 0.2 and b.get("state") not in (2, 3):
                alerter(self.p.stock, self.p.discord, cle, "batterie", "orange", f"🔋 Batterie faible sur {t.nom}",
                        f"{int(b['level'] * 100)} % et pas en charge : vérifie le câble ou le hub USB.", salon="TELEPHONES")


async def boucle(publieur):
    """La vigie chaque minute ; les relevés de 8 h et 21 h 45 (et le rapport du soir), une fois par jour chacun."""
    vigie = Vigie(publieur)
    while True:
        try:
            vigie.tour()
            maintenant_ = dt.datetime.now(PARIS)
            jour = maintenant_.date().isoformat()
            dus = [nom for h, m, nom in RELEVES if (maintenant_.hour, maintenant_.minute) >= (h, m)
                   and publieur.stock.reglage(f"sante_releve_{nom}") != jour]
            if dus:                       # le plus récent seulement : un service rallumé à 22 h ne relève pas deux fois
                for nom in dus:
                    publieur.stock.poser_reglage(f"sante_releve_{nom}", jour)
                await relever(publieur, f"du {dus[-1]}")
                await credits(publieur)
                if dus[-1] == "soir":
                    rapport(publieur)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("santé des comptes")
        await asyncio.sleep(TOUR_S)
