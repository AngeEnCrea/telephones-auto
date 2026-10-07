"""programmation.py : les vidéos d'un dossier de groupe partent toutes seules, aux créneaux.

Une vidéo déposée dans videos/<groupe>/ (videos.py ; <groupe> : le nom d'un groupe de comptes, onglet Comptes) est mise
en file, une fois, sur les comptes de SON groupe (TikTok et Instagram ensemble) au prochain créneau libre du groupe.
Créneaux, heure de Paris : réglage « creneaux » (9 h, 12 h, 15 h, 18 h, 21 h par défaut) ; les groupes se répartissent
à égale distance entre deux créneaux, dans l'ordre des noms (2 groupes, créneaux toutes les 3 h : le 1er à 9 h, le 2e
à 10 h 30…), pour que le téléphone ne publie pas tout d'un coup. Chaque passage est tiré au hasard à ± 15 min du
créneau : jamais deux jours pareils (12 h 11, 14 h 56…).
Un créneau manqué (téléphone débranché, sans réseau, file en pause) ne se rattrape pas en rafale : passé de plus de
30 min, la publication programmée (TikTok + Insta du groupe ensemble) est reportée au prochain créneau libre de son
groupe (vu le 06/10/2026 : l'iPhone sans internet une nuit, les publications du matin seraient toutes sorties d'un
coup à son retour, une heure avant celles de midi).
Une vidéo à la racine de videos/ ne part qu'à la main (onglet Publications), à l'heure qu'on lui donne."""
import datetime as dt
import logging
import random
from zoneinfo import ZoneInfo

import videos
from recettes import PRETES

log = logging.getLogger("programmation")
PARIS = ZoneInfo("Europe/Paris")
CRENEAUX = "09:00,12:00,15:00,18:00,21:00"
OCCUPE = ("en_attente", "en_cours", "publie")
VARIATION_MIN = 15          # ± 15 min autour du créneau, tiré au hasard à chaque passage
PRIS_MIN = VARIATION_MIN + 10   # une publication à moins de 25 min d'un créneau l'occupe
RETARD_MAX_MIN = 2 * VARIATION_MIN   # au-delà de 30 min de retard, une publication programmée est reportée


def creneaux(stock):
    """Les créneaux du jour, [(heure, minute)…], du réglage « creneaux » (« 09:00,12:00,… »)."""
    out = set()
    for x in (stock.reglage("creneaux", CRENEAUX) or "").split(","):
        h, _, m = x.strip().partition(":")
        if h.isdigit() and 0 <= int(h) <= 23 and (not m or (m.isdigit() and 0 <= int(m) <= 59)):
            out.add((int(h), int(m or 0)))
    return sorted(out)


def nom_groupe(c):
    return c["groupe"] or "@" + c["identifiant"]


def pas_creneaux(stock):
    """L'écart le plus court entre deux créneaux qui se suivent (minutes), 3 h au plus (un seul créneau par jour)."""
    cr = [h * 60 + m for h, m in creneaux(stock)]
    return min([b - a for a, b in zip(cr, cr[1:])] + [180])


def ecart_groupes(stock, n):
    """L'écart entre deux groupes qui se suivent (minutes) : n groupes à égale distance entre deux créneaux."""
    return max(pas_creneaux(stock) // max(n, 1), 15)


def decalage(stock, noms, groupe):
    """Le décalage du groupe sur les créneaux (minutes) : les groupes du projet (`noms`, triés) à égale distance entre
    deux créneaux (2 groupes, toutes les 3 h : 0 et 90 min)."""
    return noms.index(groupe) * ecart_groupes(stock, len(noms)) if groupe in noms else 0


def groupe_de(stock, compte):
    """(ids des comptes du groupe de ce compte, son décalage) : de quoi chercher son prochain créneau libre."""
    comptes = stock.comptes_du_projet(compte["projet"] or "")
    groupe = nom_groupe(compte)
    du_groupe = [c["id"] for c in comptes if nom_groupe(c) == groupe] or [compte["id"]]
    noms = sorted({nom_groupe(c) for c in comptes}) or [groupe]
    return du_groupe, decalage(stock, noms, groupe)


def a_paris(quand):
    return dt.datetime.fromisoformat(quand.replace("Z", "+00:00")).astimezone(PARIS)


def prochain_creneau(stock, comptes_ids, decalage_min=0, maintenant=None, marge_min=5, varier=True):
    """Le prochain créneau libre (UTC, « …Z ») pour ces comptes (aucune publication prévue à 25 min près), l'heure
    tirée au hasard à ± 15 min du créneau (jamais avant maintenant + 2 min)."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    pris = [dt.datetime.fromisoformat(p["quand"].replace("Z", "+00:00"))
            for p in stock.publications_des_comptes(comptes_ids) if p["etat"] in OCCUPE and p["quand"]]
    jour = maintenant.astimezone(PARIS).date()
    for j in range(90):
        d = jour + dt.timedelta(days=j)
        for h, m in creneaux(stock):
            t = (dt.datetime(d.year, d.month, d.day, h, m, tzinfo=PARIS) + dt.timedelta(minutes=decalage_min)).astimezone(dt.timezone.utc)
            if t >= maintenant + dt.timedelta(minutes=marge_min) and all(abs((t - x).total_seconds()) >= PRIS_MIN * 60 for x in pris):
                if varier:
                    t += dt.timedelta(seconds=random.randint(-VARIATION_MIN * 60, VARIATION_MIN * 60))
                    t = max(t, maintenant + dt.timedelta(minutes=2))
                return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


async def programmer(stock, http):
    """Un passage : chaque vidéo d'un dossier de groupe, pas encore en file, part sur son groupe au prochain créneau.
    Rend la liste de ce qui a été programmé."""
    if stock.reglage("programmation_auto", "1") != "1" or not creneaux(stock):
        return []
    faits = []
    bloques = stock.comptes_bloques()
    for v in await videos.videos_publiables(http):
        if not v.get("groupe") or v["statut"] != "valide" or stock.publications_de_video(v["cle"]):
            continue
        slug, _ = videos.decouper(v["cle"])
        comptes = stock.comptes_du_projet(slug)
        du_groupe = [c for c in comptes if nom_groupe(c) == v["groupe"] and c["udid"] and PRETES.get(c["plateforme"])]
        if not du_groupe:
            log.warning("vidéo « %s » : aucun compte prêt dans le groupe %s", v["titre"], v["groupe"])
            continue
        du_groupe = [c for c in du_groupe if c["id"] not in bloques]   # en warm-up, publications bloquées (chauffe.py)
        if not du_groupe:
            continue                      # tout le groupe en warm-up : la vidéo attend la fin
        groupes = sorted({nom_groupe(c) for c in comptes})
        quand = prochain_creneau(stock, [c["id"] for c in du_groupe], decalage(stock, groupes, v["groupe"]))
        if not quand:
            continue
        envoi = stock.creer_envoi(v["cle"], v["titre"], 0, auto=True)
        for c in du_groupe:
            stock.creer_publication(c["id"], v["cle"], v["titre"], (v.get("description") or "")[:2200], quand, False, envoi)
        log.info("programmée : « %s » pour %s (%s compte(s)), le %s", v["titre"], v["groupe"], len(du_groupe),
                 a_paris(quand).strftime("%d/%m à %H:%M"))
        faits.append({"video": v["cle"], "groupe": v["groupe"], "quand": quand, "comptes": [c["id"] for c in du_groupe]})
    return faits


def en_retard(stock, p, maintenant=None):
    """Les minutes de retard d'une publication PROGRAMMÉE (envoi « auto ») passée de plus de 30 min, sinon 0. Les
    envois à la main partent quand ils peuvent (leur rythme : un compte toutes les 30 min, stock.prochaine)."""
    if not p.get("quand") or p.get("repetition") or not p.get("envoi_id"):
        return 0
    envoi = stock.envoi(p["envoi_id"])
    if not envoi or not envoi["auto"]:
        return 0
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    retard = (maintenant - dt.datetime.fromisoformat(p["quand"].replace("Z", "+00:00"))).total_seconds() / 60
    return int(retard) if retard > RETARD_MAX_MIN else 0


def lot_de(stock, p):
    """La publication et ses sœurs du même envoi sur le même groupe, encore en attente (TikTok + Insta d'un créneau)."""
    if not p.get("envoi_id"):
        return [p]
    compte = stock.compte(p["compte_id"])
    du_groupe, _ = groupe_de(stock, compte)
    soeurs = [x for x in stock.publications_de_envoi(p["envoi_id"])
              if x["id"] != p["id"] and x["etat"] == "en_attente" and x["compte_id"] in du_groupe]
    return [p] + soeurs


def reporter(stock, pubs, raison):
    """Met ces publications (un même groupe) ENSEMBLE au prochain créneau libre du groupe, en attente, avec une étape
    qui dit pourquoi. Rend l'heure (UTC, « …Z »), ou None s'il n'y a aucun créneau."""
    if not pubs:
        return None
    du_groupe, dec = groupe_de(stock, stock.compte(pubs[0]["compte_id"]))
    quand = prochain_creneau(stock, du_groupe, dec)
    if not quand:
        return None
    for x in pubs:
        if x["etat"] != "en_attente":
            stock.maj_publication(x["id"], etat="en_attente", erreur="", fin=None)
        stock.maj_publication(x["id"], quand=quand)
        stock.etape(x["id"], f"{raison} : reportée au {a_paris(quand).strftime('%d/%m à %H:%M')}")
    log.info("%s : n° %s reportée(s) au %s", raison, ", ".join(str(x["id"]) for x in pubs),
             a_paris(quand).strftime("%d/%m à %H:%M"))
    return quand
