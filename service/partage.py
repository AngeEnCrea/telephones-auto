"""partage.py : des iPhone partagés entre projets sans se gêner.

Un téléphone publie une vidéo à la fois (3 à 6 min par réseau, un groupe TikTok + Insta ≈ 7 à 13 min). Le projet déjà en
place (le projet principal) garde sa grille : chaque groupe à son créneau + son décalage, tiré à ± 15 min (programmation.py, inchangé).
Un autre projet sur le même téléphone ne prend que les TROUS de cette grille : au moins MARGE_MIN de toute heure de la
grille des autres projets sur ce téléphone, et de toute publication d'un autre projet déjà prévue dessus. Ainsi la
programmation automatique du projet principal, qui ne vise que sa grille, ne tombe jamais sur une vidéo d'un autre projet, et l'inverse."""
import datetime as dt
import random

import programmation

MARGE_MIN = 28          # ± 15 min de variation de l'autre + ~13 min de publication (TikTok + Insta)
PLAGE_MIN = 60          # on cherche un trou à une heure au plus du créneau demandé


def _udids(comptes):
    return {c["udid"] for c in comptes if c["udid"]}


def _anciennete(stock, slug):
    return min((c["id"] for c in stock.comptes_du_projet(slug)), default=10 ** 9)


def grille_autres(stock, udids, projet):
    """Les heures nominales (minutes depuis minuit, Paris) où les projets arrivés AVANT celui-ci (son premier compte est
    plus ancien) publient sur ces téléphones. Le premier arrivé (le projet principal) garde sa grille sans rien regarder."""
    out = set()
    rang = _anciennete(stock, projet)
    for slug in stock.projets_des_comptes():
        if slug == projet or _anciennete(stock, slug) > rang:
            continue
        comptes = stock.comptes_du_projet(slug)
        noms = programmation.ordre_groupes(programmation.nom_groupe(c) for c in comptes)
        for g in noms:
            if _udids([c for c in comptes if programmation.nom_groupe(c) == g]) & udids:
                dec = programmation.decalage(stock, noms, g)
                out |= {(h * 60 + m + dec) % 1440 for h, m in programmation.creneaux(stock)}
    return sorted(out)


def _distance(m, interdits):
    """La distance (minutes, sur le cadran de 24 h) de m à l'heure interdite la plus proche."""
    return min((min(abs(m - x), 1440 - abs(m - x)) for x in interdits), default=1440)


def creneaux_groupe(stock, projet, groupe):
    """Les créneaux nominaux (« HH:MM ») d'un groupe dont les téléphones portent aussi un autre projet : dans chaque
    tranche de la grille, la minute la plus loin de tout autre projet (les groupes du projet déjà placés comptent
    aussi). None si ses téléphones ne sont qu'à lui (il garde la grille commune et son décalage)."""
    comptes = stock.comptes_du_projet(projet)
    noms = programmation.ordre_groupes(programmation.nom_groupe(c) for c in comptes)
    if groupe not in noms:
        return None
    pris = []
    for g in noms[:noms.index(groupe) + 1]:
        udids = _udids([c for c in comptes if programmation.nom_groupe(c) == g])
        interdits = grille_autres(stock, udids, projet)
        if not interdits:
            if g == groupe:
                return None
            continue
        bases = [h * 60 + m for h, m in programmation.creneaux(stock)]
        pas = programmation.pas_creneaux(stock)
        a_moi = []
        for b in bases:
            # le premier trou de la tranche assez large pour la variation, sinon le premier trou tout court
            m = next((x for x in range(b, b + pas) if _distance(x, interdits + pris) >= MARGE_MIN + programmation.VARIATION_MIN),
                     next((x for x in range(b, b + pas) if _distance(x, interdits + pris) >= MARGE_MIN), None))
            if m is not None:
                a_moi.append(m % 1440)
        pris += a_moi
        if g == groupe:
            return [f"{m // 60:02d}:{m % 60:02d}" for m in sorted(a_moi)]
    return None


def ajuster(stock, comptes, projet, t, varier=True, variation=None):
    """L'heure (datetime UTC) où ces comptes peuvent publier près de `t` sans gêner un autre projet sur leurs téléphones :
    `t` (tiré à ± 15 min si `varier`, sans sortir du trou) ou le moment libre le plus proche à une heure près ; None
    s'il n'y en a pas. Jamais avant maintenant + 2 min."""
    udids = _udids(comptes)
    interdits = grille_autres(stock, udids, projet)
    autres = [dt.datetime.fromisoformat(p["quand"].replace("Z", "+00:00"))
              for p in stock.publications_des_comptes([c["id"] for s in stock.projets_des_comptes() if s != projet
                                                       for c in stock.comptes_du_projet(s) if c["udid"] in udids])
              if p["etat"] in programmation.OCCUPE and p["quand"]]
    plancher = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)

    def marge(x):
        m = x.astimezone(programmation.PARIS)
        d = _distance(m.hour * 60 + m.minute, interdits)
        return min([d] + [abs((x - y).total_seconds()) / 60 for y in autres])

    if varier:
        v = programmation.VARIATION_MIN if variation is None else variation
        essai = t + dt.timedelta(minutes=random.randint(-v, v))
        if essai >= plancher and marge(essai) >= MARGE_MIN:
            return essai
    for k in range(PLAGE_MIN + 1):
        for x in (t + dt.timedelta(minutes=k), t - dt.timedelta(minutes=k)):
            if x >= plancher and marge(x) >= MARGE_MIN:
                return x
    return None

