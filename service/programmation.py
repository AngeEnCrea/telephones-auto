"""programmation.py : les vidéos d'un dossier de groupe partent toutes seules, aux créneaux.

Une vidéo déposée dans videos/<groupe>/ (videos.py ; <groupe> : le nom d'un groupe de comptes, onglet Comptes) est mise
en file, une fois, sur les comptes de SON groupe (TikTok et Instagram ensemble) au prochain créneau libre du groupe.
Créneaux, heure de Paris : réglage « creneaux » (9 h, 12 h, 15 h, 18 h, 21 h par défaut) ; les groupes se répartissent
à égale distance entre deux créneaux, dans l'ordre des noms (2 groupes, créneaux toutes les 3 h : le 1er à 9 h, le 2e
à 10 h 30…), pour que le téléphone ne publie pas tout d'un coup. Chaque passage est tiré au hasard à ± 15 min du
créneau : jamais deux jours pareils (12 h 11, 14 h 56…).
Un créneau manqué (téléphone débranché, sans réseau, file en pause) ne se rattrape pas en rafale : passé de plus de
30 min, la publication programmée (TikTok + Insta du groupe ensemble) est reportée au prochain créneau libre de son
groupe (06/10/2026 : l'iPhone sans internet de 1 h 24 à 10 h 53, les publications de 8 h 58 et 9 h 18 seraient
sorties à 11 h, une heure avant celles de midi).
Seuls les remontages (« groupe » dans le dossier) partent ainsi : un original validé reste au compte principal
(planificateur externe), et l'utilisateur peut toujours envoyer une vidéo à la main (📤 Publier).
Cinq par jour sur CHAQUE compte (27/10/2026, « pourquoi les comptes clips ne publient pas 5 fois par jour ») : une page
garde 3 jours de file par compte (profondeur), le surplus part en réserve au centre ; une vidéo disparue ou refusée est
annulée dès qu'on la voit (purger) et, au créneau, la suivante prête prend sa place (remplacer) ; un échec passager est
relancé une fois ; les créneaux libres se comptent compte par compte, et les trous d'une file se comblent (compacter).
Un objectif par jour : réglage « objectif:<projet> » ;
ce qui manque à la dose normale de chaque page (5) part en +1 sur les pages déjà pleines (doses), et les créneaux
servent dans l'ordre du réglage (une page à 6 par jour prend les 6 premiers)."""
import datetime as dt
import logging
import random
import re
import time
from collections import Counter
from zoneinfo import ZoneInfo

import videos
from recettes import PRETES
from stock import maintenant as maintenant_iso

log = logging.getLogger("programmation")
PARIS = ZoneInfo("Europe/Paris")
CRENEAUX = "09:00,12:00,15:00,18:00,21:00"
OCCUPE = ("en_attente", "en_cours", "publie")
VARIATION_MIN = 15          # ± 15 min autour du créneau, tiré au hasard à chaque passage
PRIS_MIN = VARIATION_MIN + 10   # une publication à moins de 25 min d'un créneau l'occupe
RETARD_MAX_MIN = 2 * VARIATION_MIN   # au-delà de 30 min de retard, une publication programmée est reportée
DOSE = 5                    # la dose normale d'une page par jour, montée en charge finie (réglage « dose »)
PROFONDEUR = 15             # la file d'une page : 15 publications par compte, 3 jours à 5 par jour (réglage « profondeur »)
EN_TETE_MARGE_MIN = 20      # une pépite prend la place de la prochaine publication à plus de 20 min (pas celle qui part)
RELANCE = "Relance automatique après un échec passager"
# les échecs passagers (27/10/2026 : 6 en 4 jours, jamais relancés) : l'agent ou la base injoignables, la
# pellicule (DCIM, VLC, Raccourci), la liste des comptes qui ne s'ouvre pas, un bouton pas trouvé à l'écran ; JAMAIS : un
# compte déconnecté ou bloqué, ni ce qui a pu partir (les messages d'après le dernier bouton disent « vérifie sur le compte »)
PASSAGERS = ("l'agent ne répond pas", "injoignable", "dcim", "pellicule", "dossier de vlc", "n'a pas rangé la vidéo",
             "liste des comptes", "introuvable", "pas à l'écran", "ne s'ouvre pas", "ne revient pas", "pas de réponse en")
JAMAIS = ("n'est pas parmi", "pas connecté", "déconnect", "sans le trouver", "n'a pas pris", "bloqué", "suspendu",
          "restreint", "nettoyage du compte", "verrouill", "interrompue", "vérifie sur le compte", "écran inattendu",
          "n'est pas installé", "refusé")


def creneaux_par_priorite(stock):
    """Les créneaux dans l'ordre du réglage « creneaux » (« 09:00,12:00,…,19:30,16:30 ») : une page à n publications
    par jour prend les n premiers (03/11/2026 : les créneaux ajoutés pour l'objectif ne servent qu'aux pages renforcées)."""
    out = []
    for x in (stock.reglage("creneaux", CRENEAUX) or "").split(","):
        h, _, m = x.strip().partition(":")
        if h.isdigit() and 0 <= int(h) <= 23 and (not m or (m.isdigit() and 0 <= int(m) <= 59)) and (int(h), int(m or 0)) not in out:
            out.append((int(h), int(m or 0)))
    return out


def creneaux(stock):
    """Les créneaux du jour, [(heure, minute)…] dans l'ordre des heures, du réglage « creneaux » (« 09:00,12:00,… »)."""
    return sorted(creneaux_par_priorite(stock))


def creneaux_du_jour(stock, dose):
    """Les créneaux d'une page qui sort `dose` vidéos ce jour-là (les premiers du réglage), dans l'ordre des heures ;
    tous sans dose (None)."""
    return creneaux(stock) if dose is None else sorted(creneaux_par_priorite(stock)[:max(dose, 0)])


def nom_groupe(c):
    return c["groupe"] or "@" + c["identifiant"]


def ordre_groupes(noms):
    """Les noms de groupes triés, nombres compris (03/11/2026 : « Compte 10 » après « Compte 9 », pas après « Compte 1 »,
    sinon toute la grille se décale)."""
    return sorted(set(noms), key=lambda g: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", g)])


def pas_creneaux(stock):
    """L'écart le plus court entre deux créneaux qui se suivent (minutes), 3 h au plus (un seul créneau par jour)."""
    cr = [h * 60 + m for h, m in creneaux(stock)]
    return min([b - a for a, b in zip(cr, cr[1:])] + [180])


def ecart_groupes(stock, n):
    """L'écart entre deux groupes qui se suivent (minutes) : n groupes à égale distance entre deux créneaux ; le réglage
    « ecart_groupes » le fixe (03/11/2026 : des créneaux ajoutés entre les autres ne décalent plus toute la grille)."""
    try:
        fixe = int(stock.reglage("ecart_groupes", 0) or 0)
    except (TypeError, ValueError):
        fixe = 0
    return fixe if fixe >= 15 else max(pas_creneaux(stock) // max(n, 1), 15)


def decalage(stock, noms, groupe):
    """Le décalage du groupe sur les créneaux (minutes) : les groupes du projet (`noms`, triés) à égale distance entre
    deux créneaux (2 groupes, toutes les 3 h : 0 et 90 min)."""
    return noms.index(groupe) * ecart_groupes(stock, len(noms)) if groupe in noms else 0


def groupe_de(stock, compte):
    """(ids des comptes du groupe de ce compte, son décalage) : de quoi chercher son prochain créneau libre."""
    comptes = stock.comptes_du_projet(compte["projet"] or "")
    groupe = nom_groupe(compte)
    du_groupe = [c["id"] for c in comptes if nom_groupe(c) == groupe] or [compte["id"]]
    noms = ordre_groupes(nom_groupe(c) for c in comptes) or [groupe]
    return du_groupe, decalage(stock, noms, groupe)


def reglage_entier(stock, cle, defaut):
    try:
        return int(stock.reglage(cle, defaut) or 0)
    except (TypeError, ValueError):
        return defaut


def doses(stock, projet, jour):
    """{groupe: vidéos du jour} des pages réglées d'un projet. La dose normale (5, réglage « dose ») suit la montée en
    charge ; avec un objectif (réglage
    « objectif:<projet> », publications par jour), ce qui manque part en +1 sur les pages déjà à leur dose normale, à
    tour de rôle (le tour change chaque jour), jamais plus que de créneaux. Une page qui monte en charge prend sur ces
    renforts : l'objectif ne bouge pas.
    Les comptes en warm-up « publications bloquées » ne comptent pas."""
    n = len(creneaux(stock))
    normale = min(reglage_entier(stock, "dose", DOSE), n)
    bloques = stock.comptes_bloques()
    comptes = Counter(nom_groupe(c) for c in stock.comptes_du_projet(projet) if c["udid"] and c["id"] not in bloques)
    out = {}
    for p in stock.pages(projet):
        if p.get("debut"):
            j = (jour - dt.date.fromisoformat(p["debut"])).days
            out[p["groupe"]] = 0 if j < 0 else min(normale, j + 1)
    manque = reglage_entier(stock, f"objectif:{projet}", 0) - sum(d * comptes[g] for g, d in out.items())
    pleines = sorted(g for g, d in out.items() if d >= normale and comptes[g])
    if pleines:
        k = jour.toordinal() % len(pleines)
        niche = {p["groupe"] for p in stock.pages(projet) if p.get("niche")}
        pleines = sorted(pleines[k:] + pleines[:k], key=lambda g: g in niche)   # les pages de niche, moins de stock : après
    while manque > 0 and any(out[g] < n for g in pleines):
        for g in pleines:
            if manque > 0 and out[g] < n:
                out[g] += 1
                manque -= comptes[g]
    return out


def quota(stock, page, jour):
    """Le nombre de vidéos qu'une page peut sortir ce jour-là (doses : montée en charge, puis objectif du projet) ; None
    sans montée en charge (une page sans jour 1 : tous les créneaux)."""
    if not page or not page.get("debut"):
        return None
    return doses(stock, page["projet"], jour).get(page["groupe"], 0)


def page_des_comptes(stock, comptes_ids):
    """La page (projet, groupe) de ces comptes, ou None."""
    c = stock.compte(comptes_ids[0]) if comptes_ids else None
    return stock.page(c["projet"] or "", nom_groupe(c)) if c else None


def a_paris(quand):
    return dt.datetime.fromisoformat(quand.replace("Z", "+00:00")).astimezone(PARIS)


def prochain_creneau(stock, comptes_ids, decalage_min=0, maintenant=None, marge_min=5, varier=True, exclure=()):
    """Le prochain créneau libre (UTC, « …Z ») pour ces comptes : AUCUN d'eux n'a de publication prévue à 25 min près, et
    aucun n'a déjà sa dose du jour. Compte par compte (27/10/2026) : avant, un Insta relancé seul occupait aussi le créneau
    de son TikTok, qui restait vide (Compte 3 : 21 Insta en file pour 13 TikTok, des jours entiers sans TikTok). L'heure est
    tirée au hasard à ± 15 min du créneau (jamais avant maintenant + 2 min). `exclure` : les publications qu'on déplace ;
    leur créneau reste pris (« Reporter » les pousse plus loin), mais elles ne comptent plus dans la dose de leur jour
    (16/10/2026 : la 1re vidéo de une page neuve, en retard, se comptait elle-même et partait trois jours plus tard)."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    pris, par_jour = {}, {}           # par compte : ses heures prises, et ses publications jour par jour (la dose)
    for p in stock.publications_des_comptes(comptes_ids):
        if p["etat"] not in OCCUPE or not p["quand"]:
            continue
        x = dt.datetime.fromisoformat(p["quand"].replace("Z", "+00:00"))
        pris.setdefault(p["compte_id"], []).append(x)
        if p["id"] not in exclure:
            jours = par_jour.setdefault(p["compte_id"], {})
            d = x.astimezone(PARIS).date()
            jours[d] = jours.get(d, 0) + 1
    page = page_des_comptes(stock, comptes_ids)
    jour = maintenant.astimezone(PARIS).date()
    for j in range(90):
        d = jour + dt.timedelta(days=j)
        q = quota(stock, page, d)
        if q is not None and any(par_jour.get(c, {}).get(d, 0) >= q for c in comptes_ids):
            continue                  # un des comptes a sa dose du jour (montée en charge, 5 au plus)
        for h, m in creneaux_du_jour(stock, q):
            t = (dt.datetime(d.year, d.month, d.day, h, m, tzinfo=PARIS) + dt.timedelta(minutes=decalage_min)).astimezone(dt.timezone.utc)
            if t >= maintenant + dt.timedelta(minutes=marge_min) and all(
                    abs((t - x).total_seconds()) >= PRIS_MIN * 60 for c in comptes_ids for x in pris.get(c, ())):
                if varier:
                    t = varier_heure(t, maintenant)
                return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def varier_heure(t, maintenant):
    """L'heure d'un créneau tirée au hasard à ± 15 min, jamais avant maintenant + 2 min."""
    t += dt.timedelta(seconds=random.randint(-VARIATION_MIN * 60, VARIATION_MIN * 60))
    return max(t, maintenant + dt.timedelta(minutes=2))


def profondeur(stock):
    """Combien de publications une page garde en file, par compte (réglage « profondeur », 15 par défaut : 3 jours)."""
    try:
        return max(1, int(stock.reglage("profondeur", PROFONDEUR)))
    except (TypeError, ValueError):
        return PROFONDEUR


def placer(stock, cle, titre, description, comptes, decalage_min, maintenant=None):
    """Une vidéo sur ces comptes d'une page, chacun à SON prochain créneau libre : le même pour tous quand leurs files sont
    alignées (TikTok + Insta ensemble, une seule heure tirée au hasard), sinon chacun comble son trou (27/10/2026). Un seul
    envoi « auto » (un créneau manqué est reporté). Rend les publications créées."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    bases = {}
    for c in comptes:
        q = prochain_creneau(stock, [c["id"]], decalage_min, maintenant=maintenant, varier=False)
        if q:
            bases.setdefault(q, []).append(c)
    if not bases:
        return []
    envoi = stock.creer_envoi(cle, titre, 0, auto=True)
    pubs = []
    for q, cs in sorted(bases.items()):
        quand = varier_heure(dt.datetime.fromisoformat(q.replace("Z", "+00:00")), maintenant).strftime("%Y-%m-%dT%H:%M:%SZ")
        for c in cs:
            pubs.append(stock.creer_publication(c["id"], cle, titre, legende_pour(stock, c, (description or "")[:2200]),
                                                quand, False, envoi))
    return pubs


def placer_en_tete(stock, cle, titre, description, comptes, decalage_min, maintenant=None):
    """Une pépite (une vidéo qui a explosé sur un compte, remontée pour cette page) passe devant la file
    : sur chaque compte, elle prend l'heure de sa
    prochaine publication programmée à plus de 20 min, reportée au bout de la file ; jamais celle d'une autre pépite. Un
    compte sans file la prend à son prochain créneau libre. Rend les publications créées."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    limite = maintenant + dt.timedelta(minutes=EN_TETE_MARGE_MIN)
    envoi, pubs = None, []
    for c in comptes:
        file = [x for x in stock.file_des_comptes([c["id"]]) if x["quand"] and '"pepite": true' not in (x["options"] or "")
                and dt.datetime.fromisoformat(x["quand"].replace("Z", "+00:00")) >= limite]
        quand = None
        if file:
            x = min(file, key=lambda x: x["quand"])
            if reporter(stock, [stock.publication(x["id"])], f"Laisse sa place à une pépite (« {titre} »)"):
                quand = x["quand"]
        quand = quand or prochain_creneau(stock, [c["id"]], decalage_min, maintenant=maintenant)
        if not quand:
            continue
        envoi = envoi or stock.creer_envoi(cle, titre, 0, auto=True)
        pub = stock.creer_publication(c["id"], cle, titre, legende_pour(stock, c, (description or "")[:2200]), quand, False, envoi,
                                      options='{"pepite": true}')
        stock.etape(pub["id"], f"Pépite : passe devant la file, le {a_paris(quand).strftime('%d/%m à %H:%M')}")
        pubs.append(pub)
    return pubs


LEGENDES = ("instagram", "tiktok")


def legendes(stock, plateforme):
    """{projet: légende} : la règle des légendes d'une plateforme pour chaque projet (réglage legende_<plateforme>:<projet>)."""
    return {k.split(":", 1)[1]: v for k, v in stock.reglages_prefixe(f"legende_{plateforme}:").items() if v}


def legendes_instagram(stock):
    return legendes(stock, "instagram")


def legende_pour(stock, compte, legende, description=None):
    """La légende d'une publication. Sur Instagram, la règle du projet remplace le fichier .txt ; sur TikTok aussi depuis le 03/11/2026 (« sur tiktok ça : Tu veux accéder à mes fournisseurs
    privés ? »). Une légende tapée à la main (différente de la description) reste telle quelle."""
    if compte["plateforme"] in LEGENDES:
        regle = stock.reglage(f"legende_{compte['plateforme']}:{compte['projet']}")
        if regle and (description is None or (legende or "").strip() == (description or "").strip()):
            return regle
    return legende


async def programmer(stock, http):
    """Un passage : chaque vidéo d'un dossier de groupe, pas encore en file, part sur son groupe au prochain créneau.
    Une page ne garde que 3 jours d'avance par compte (« profondeur », 27/10/2026 : 131 publications en file pour le
    Compte 1, jusqu'au 10/11, et plus la file est longue, plus ses vidéos sont refaites sous un autre nom avant leur tour) :
    au-delà, le remontage attend, validé, que la file se vide. Rend la liste de ce qui a été programmé."""
    if stock.reglage("programmation_auto", "1") != "1" or not creneaux(stock):
        return []
    faits = []
    bloques = stock.comptes_bloques()
    prof = profondeur(stock)
    prets = await videos.videos_publiables(http)
    await purger(stock, http, prets)
    for v in prets:
        if not v.get("groupe") or v["statut"] != "valide" or stock.publications_de_video(v["cle"]):
            continue
        slug, _ = videos.decouper(v["cle"])
        page = stock.page(slug, v["groupe"])
        if page and page["niche"] and v.get("niche_ok") is not True:
            continue                      # une page de niche ne prend que les vidéos de sa niche (classées par le dossier)
        comptes = stock.comptes_du_projet(slug)
        du_groupe = [c for c in comptes if nom_groupe(c) == v["groupe"] and c["udid"] and PRETES.get(c["plateforme"])]
        if not du_groupe:
            log.warning("vidéo « %s » : aucun compte prêt dans le groupe %s", v["titre"], v["groupe"])
            continue
        du_groupe = [c for c in du_groupe if c["id"] not in bloques]   # en warm-up, publications bloquées (chauffe.py)
        if not du_groupe:
            continue                      # tout le groupe en warm-up : le remontage attend la fin
        file = Counter(x["compte_id"] for x in stock.file_des_comptes([c["id"] for c in du_groupe]))
        if not v.get("pepite"):           # une pépite passe devant, même file pleine (placer_en_tete)
            du_groupe = [c for c in du_groupe if file[c["id"]] < prof]
            if not du_groupe:
                continue                  # la file de la page est pleine : le remontage attend son tour, validé
        groupes = ordre_groupes(nom_groupe(c) for c in comptes)
        pubs = (placer_en_tete if v.get("pepite") else placer)(stock, v["cle"], v["titre"], v.get("description"), du_groupe,
                                                              decalage(stock, groupes, v["groupe"]))
        if not pubs:
            continue
        log.info("programmée%s : « %s » pour %s (%s compte(s)), le %s", " en tête (pépite)" if v.get("pepite") else "",
                 v["titre"], v["groupe"], len(pubs),
                 ", ".join(sorted({a_paris(x["quand"]).strftime("%d/%m à %H:%M") for x in pubs})))
        faits.append({"video": v["cle"], "groupe": v["groupe"], "quand": min(x["quand"] for x in pubs),
                      "comptes": [x["compte_id"] for x in pubs]})
    compacter(stock)
    return faits


def raison_pas_publiable(etat):
    """Pourquoi une vidéo ne part pas, (None : elle n'est plus dans le dossier)."""
    return ("refusée" if etat == "refuse" else "plus dans le dossier des vidéos"
            if etat is None else f"toujours en retouche (état : {etat})")


def page_reglee(stock, projet, groupe):
    """La page de ce groupe si elle est réglée (une niche, ou un jour 1 : les comptes clips du projet principal), sinon None."""
    page = stock.page(projet or "", groupe)
    return page if page and (page["niche"] or page["debut"]) else None


def comptes_des_pages(stock):
    """Les comptes actifs des pages réglées (pas un autre projet, qui se place à la main)."""
    pages = {(p["projet"], p["groupe"]) for p in stock.pages() if p["niche"] or p["debut"]}
    return [c for c in stock.comptes() if c["actif"] and (c["projet"], nom_groupe(c)) in pages]


def de_page(stock, p):
    """Une publication programmée (envoi « auto ») sur une page réglée : la programmation peut la remplacer, la relancer."""
    if not p or p.get("repetition") or not p.get("envoi_id"):
        return False
    envoi, compte = stock.envoi(p["envoi_id"]), stock.compte(p["compte_id"])
    return bool(envoi and envoi["auto"] and compte and page_reglee(stock, compte["projet"], nom_groupe(compte)))


def annuler(stock, pubs, raison):
    for x in pubs:
        stock.maj_publication(x["id"], etat="annule", fin=maintenant_iso())
        stock.etape(x["id"], f"Annulée : la vidéo est {raison}")


_relues = {}                # vidéo → dernière relecture d'avance (monotonic) : une vidéo en retouche relue toutes les 15 min


async def purger(stock, http, prets, n_max=10):
    """Les vidéos en file des pages qui ne sont plus dans la liste des vidéos du dossier, relues une à une (10 par
    passage au plus) : disparue (refaite sous un autre nom) ou refusée, elle est annulée tout de suite, partout où elle
    attend, au lieu de garder son créneau jusqu'au jour J (27/10/2026) : la page se remplit derrière. En retouche, elle
    garde sa place (au créneau, elle sera reportée ou remplacée). Liste vide : rien n'est touché."""
    publiables = {v["cle"] for v in prets}
    if not publiables:
        return []
    file = [x for x in stock.file_des_comptes([c["id"] for c in comptes_des_pages(stock)])
            if x["auto"] and x["video"].startswith(videos.PREFIXE) and x["video"] not in publiables]
    disparues, n = {}, 0
    for video in dict.fromkeys(x["video"] for x in file):
        if n >= n_max:
            break
        if time.monotonic() - _relues.get(video, -1e9) < 900:
            continue
        n += 1
        _relues[video] = time.monotonic()
        try:
            await videos.verifier_publiable(http, video)
        except videos.PasPubliable as e:
            if e.etat not in videos.EN_RETOUCHE:
                disparues[video] = raison_pas_publiable(e.etat)
        except Exception as e:
            log.info("relecture d'avance de %s : %s", video, e)
    annulees = [x for x in file if x["video"] in disparues]
    for video, raison in disparues.items():
        annuler(stock, [x for x in annulees if x["video"] == video], f"{raison} (vu d'avance)")
        log.info("%s : %s, %s publication(s) en file annulée(s) d'avance", video, raison,
                 sum(1 for x in annulees if x["video"] == video))
    return annulees


async def remplacer(stock, http, lot, raison, maintenant=None):
    """Le créneau d'une vidéo pas publiable au moment de partir ne reste pas vide (27/10/2026 : les Comptes 1 et 2 ont
    publié 0 à 1 vidéo le 26/10, leurs vidéos refaites sous un autre nom) : pour chaque compte du lot dont c'est l'heure,
    la prochaine publication PRÊTE de sa file (même compte, donc même légende Instagram, etc.) est avancée à maintenant.
    Prête : relue dans le dossier ; disparue ou refusée, elle est annulée et on prend la suivante ; en retouche, elle garde
    sa place. Seulement sur une page réglée (pas un autre projet, placé à la main). Rend les publications avancées."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    if not lot or not de_page(stock, lot[0]):
        return []
    dus = {x["compte_id"] for x in lot if x.get("quand")
           and dt.datetime.fromisoformat(x["quand"].replace("Z", "+00:00")) <= maintenant + dt.timedelta(minutes=5)}
    verdicts, avancees, deja = {}, [], {x["id"] for x in lot}
    for cid in sorted(dus):
        essais = 0
        for x in stock.file_des_comptes([cid]):
            if x["id"] in deja or not x["auto"] or not x["quand"] or x["quand"] <= maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"):
                continue
            if essais >= 6:
                break
            essais += 1
            ok = verdicts.get(x["video"])
            if ok is None:
                try:
                    await videos.verifier_publiable(http, x["video"])
                    ok = True
                except videos.PasPubliable as e:
                    ok = False
                    if e.etat not in videos.EN_RETOUCHE:
                        annuler(stock, lot_de(stock, stock.publication(x["id"])), raison_pas_publiable(e.etat))
                except Exception:
                    ok = True             # le dossier est illisible : la publication relira l'état en partant
                verdicts[x["video"]] = ok
            if not ok or stock.publication(x["id"])["etat"] != "en_attente":
                continue
            avant = a_paris(x["quand"]).strftime("%d/%m à %H:%M")
            stock.maj_publication(x["id"], quand=maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"))
            stock.etape(x["id"], f"Avancée à maintenant (prévue le {avant}) : {raison}")
            deja.add(x["id"])
            avancees.append(x)
            break
    if avancees:
        log.info("%s : n° %s avancée(s) à maintenant", raison, ", ".join(str(x["id"]) for x in avancees))
    return avancees


def compacter(stock, maintenant=None, n_max=5):
    """Les trous de la file d'un compte (un créneau libre avant sa publication la plus lointaine : une vidéo annulée, un
    réseau relancé seul) sont comblés par cette publication la plus lointaine, avancée (27/10/2026 : le TikTok du Compte 1
    n'avait rien de prévu le 29/10, quand son Insta y avait 5 relances seules). Une fois les deux files tassées, TikTok et
    Insta d'une page finissent au même créneau et les vidéos suivantes repartent ensemble. Pages réglées seulement,
    `n_max` par compte et par passage. Rend les publications avancées."""
    maintenant = maintenant or dt.datetime.now(dt.timezone.utc)
    bloques, faites = stock.comptes_bloques(), []
    for c in comptes_des_pages(stock):
        if c["id"] in bloques or not c["udid"]:
            continue
        _, dec = groupe_de(stock, c)
        for _ in range(n_max):
            file = [x for x in stock.file_des_comptes([c["id"]]) if x["auto"] and x["quand"]]
            if not file:
                break
            loin = max(file, key=lambda x: x["quand"])
            t_loin = dt.datetime.fromisoformat(loin["quand"].replace("Z", "+00:00"))
            trou = prochain_creneau(stock, [c["id"]], dec, maintenant=maintenant, marge_min=10, varier=False, exclure={loin["id"]})
            if not trou or dt.datetime.fromisoformat(trou.replace("Z", "+00:00")) >= t_loin - dt.timedelta(minutes=PRIS_MIN):
                break
            quand = varier_heure(dt.datetime.fromisoformat(trou.replace("Z", "+00:00")), maintenant).strftime("%Y-%m-%dT%H:%M:%SZ")
            stock.maj_publication(loin["id"], quand=quand)
            stock.etape(loin["id"], f"Avancée dans un trou de la file : prévue le {a_paris(loin['quand']).strftime('%d/%m à %H:%M')}, "
                                    f"maintenant le {a_paris(quand).strftime('%d/%m à %H:%M')}")
            faites.append(loin)
    if faites:
        log.info("files tassées : %s publication(s) avancée(s) dans un trou (%s)", len(faites), ", ".join(str(x["id"]) for x in faites))
    return faites


def passager(msg):
    """Un échec passager, qui vaut une relance (pas un compte déconnecté ou bloqué, ni ce qui a pu partir)."""
    m = (msg or "").lower()
    return not any(x in m for x in JAMAIS) and any(x in m for x in PASSAGERS)


def en_trop(stock, comptes_ids, prof):
    """Ce qui dépasse la profondeur voulue dans la file d'une page : pour chaque compte au-delà de `prof` publications,
    autant de publications programmées (envoi « auto ») à sortir, les plus lointaines d'abord, mais jamais une relancée ou
    reportée exprès tant qu'il en reste d'autres (28/10/2026 : les relances de l'agent réparateur, posées au bout de la
    file, partaient en réserve 5 min après). Regroupées par vidéo, la plus proche d'abord : [{video, publications, quand,
    titre}]. Elles attendent leur tour dans le dossier."""
    par_compte = {}
    for x in stock.file_des_comptes(comptes_ids):
        par_compte.setdefault(x["compte_id"], []).append(x)
    trop = {}
    for l in par_compte.values():
        if len(l) <= prof:
            continue
        candidates = sorted((x for x in l if x["auto"]), key=lambda x: x["quand"] or "", reverse=True)
        candidates.sort(key=lambda x: bool(x.get("relancee")))      # les relancées en dernier recours
        for x in candidates[:len(l) - prof]:
            e = trop.setdefault(x["video"], {"video": x["video"], "publications": [], "quand": x["quand"], "titre": x["titre"]})
            e["publications"].append(x["id"])
            e["quand"] = min(e["quand"] or "", x["quand"] or "") or None
    return sorted(trop.values(), key=lambda e: e["quand"] or "")


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
    """Met ces publications (un même groupe) ENSEMBLE au prochain créneau libre de leurs comptes, en attente, avec une
    étape qui dit pourquoi. Rend l'heure (UTC, « …Z »), ou None s'il n'y a aucun créneau."""
    if not pubs:
        return None
    _, dec = groupe_de(stock, stock.compte(pubs[0]["compte_id"]))
    quand = prochain_creneau(stock, sorted({x["compte_id"] for x in pubs}), dec, exclure={x["id"] for x in pubs})
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
