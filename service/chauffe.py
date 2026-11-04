"""chauffe.py : le warm-up des comptes : un espace où on met des comptes, avec les mots-clés de leur niche (n'importe
quelle niche), et ils se « chauffent » tout seuls pendant N jours, avant de publier (40 min par jour par défaut ;
publications bloquées ou pas pendant ce temps, au choix, compte par compte).

Un compte en warm-up scrolle sa niche comme un humain, sur le téléphone où il est connecté, entre les publications :
- chaque jour, sa dose (40 min par défaut) en séances d'environ 13 min, une par tranche de la journée (9 h – 23 h),
  à une heure tirée au hasard ; la moitié de la dose le 1er jour, la dose pleine à mi-parcours ;
- une séance : la niche d'abord (un des mots-clés cherché, onglet Vidéos, les résultats regardés les uns après les
  autres : certains en entier, d'autres passés vite), puis le fil « Pour toi » (TikTok) ou les Reels (Instagram) ;
- le 1er jour, il regarde seulement ; dès le 2e, quelques likes sur des vidéos de la niche (jamais sur le fil, qui
  n'est pas forcément la niche) ; dès le 3e, quelques abonnements à des comptes de la niche (3 par jour au plus).
  Jamais de commentaire ni de message : c'est ce qui fait bannir un compte ;
- une publication passe toujours avant : pas de séance qui la retarderait, et une séance s'arrête 2 min avant la
  publication suivante ou quand la file est mise en pause ; ce qui manque est fait plus tard dans la même tranche ;
- une tranche passée sans séance (téléphone débranché, occupé) n'est pas rattrapée en rafale.
Au bout des N jours, le warm-up passe « terminé » ; si ses publications étaient bloquées, le compte rentre tout seul
dans la rotation des créneaux (programmation.py)."""
import asyncio
import datetime as dt
import logging
import os
import random
import time
from zoneinfo import ZoneInfo

import lieux
from recettes import APPS, CHAUFFES
from recettes.base import ErreurPublication, RobotSeance
from stock import maintenant
from wda import PROFONDEUR

log = logging.getLogger("chauffe")
PARIS = ZoneInfo("Europe/Paris")
JOURNEE = (9 * 60, 23 * 60)          # les séances tombent entre 9 h et 23 h, heure de Paris
MINUTES_SEANCE = 13                  # une séance dure environ 13 min (40 min par jour : 3 séances)
LIKES_JOUR = 12
# abonnements : relevés le 14/10/2026
ABONNEMENTS_JOUR, ABONNEMENTS_SEANCE = 10, 3
MARGE_PUBLICATION_S = 120            # une séance s'arrête 2 min avant la publication suivante
PLACE_MIN_S = 6 * 60                 # pas de séance si la prochaine publication tombe dans moins de 6 min (+ la marge)
ESSAIS_PAR_TRANCHE = 3
MO_PAR_MINUTE = 12                   # vidéo TikTok ou Reels en 5G : ~0,7 Go par heure (estimation affichée)
ECHELLE = float(os.environ.get("TELEPHONES_CHAUFFE_ECHELLE") or 1)   # les essais accélèrent le temps (0,02 : 13 min → 16 s)
P_LIKE = float(os.environ.get("TELEPHONES_CHAUFFE_P_LIKE") or 0.3)      # chances de liker une vidéo de la niche regardée
P_SUIVRE = float(os.environ.get("TELEPHONES_CHAUFFE_P_SUIVRE") or 0.2)  # … de s'abonner à son compte (les essais : 1)
# Le warm-up rapide :
# pas de journée 9 h – 23 h ni de dose par jour, des séances d'affilée de maintenant jusqu'à l'heure de fin (la nuit
# comprise), une petite pause entre deux séances d'un même compte ; plusieurs comptes d'un même téléphone se passent la
# main (la plus en retard d'abord). Likes dès la 2e séance, abonnements dès la 3e, et les plafonds (12 likes, 3
# abonnements) valent pour tout le warm-up rapide, pas par jour. Toujours jamais de commentaire ni de message.
# likes de commentaires : comme les likes, dès le 2e jour
# (la 2e séance en rapide), sur la niche seulement, quelques-uns par séance ; jamais un commentaire écrit
LIKES_COMMENTAIRES_JOUR, LIKES_COMMENTAIRES_SEANCE = 15, 4
P_COMMENTAIRES = float(os.environ.get("TELEPHONES_CHAUFFE_P_COMMENTAIRES") or 0.25)
RAPIDE_PAUSE_MIN = 4                 # entre deux séances d'un même compte
RAPIDE_FENETRE_MIN = 120             # une séance reste « due » 2 h (le téléphone sert les autres comptes entre-temps)


def utc(iso_):
    return dt.datetime.fromisoformat(iso_.replace("Z", "+00:00"))


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jour_paris(t=None):
    return (t or dt.datetime.now(dt.timezone.utc)).astimezone(PARIS).date()


def debut_du_jour(jour):
    return dt.datetime.combine(jour, dt.time(0, 0), tzinfo=PARIS)


def rang_du_jour(ch, jour):
    """Le jour du warm-up (0 : le premier), en jours de Paris."""
    return (jour - jour_paris(utc(ch["debut"]))).days


def mots_de(ch):
    vus, out = set(), []
    for m in (ch["mots"] or "").replace(",", "\n").replace(";", "\n").splitlines():
        m = " ".join(m.strip().lstrip("#").split())
        if m and m.lower() not in vus:
            vus.add(m.lower())
            out.append(m)
    return out


def minutes_du_jour(ch, j):
    """La dose du jour j : la moitié le 1er jour, la dose pleine à mi-parcours."""
    mi = max(1.0, (ch["jours"] - 1) / 2)
    return ch["minutes_jour"] * (0.5 + 0.5 * min(1.0, j / mi))


def plan_rapide(ch):
    """Les séances d'un warm-up rapide, de son début à sa fin (UTC) : [{rang, debut, fin_tranche, minutes}], toujours
    les mêmes pour ce warm-up (un redémarrage ne rebat rien)."""
    hasard = random.Random(f"{ch['id']}-rapide")
    t, fin, out, k = utc(ch["debut"]), utc(ch["fin"]), [], 0
    while True:
        minutes = MINUTES_SEANCE * hasard.uniform(0.85, 1.15)
        if t + dt.timedelta(minutes=minutes) > fin:
            break
        out.append({"rang": k, "debut": iso(t), "minutes": round(minutes, 1),
                    "fin_tranche": iso(min(fin, t + dt.timedelta(minutes=RAPIDE_FENETRE_MIN)))})
        t += dt.timedelta(minutes=minutes + RAPIDE_PAUSE_MIN * hasard.uniform(0.8, 1.4))
        k += 1
    return out


def plan_du_jour(ch, jour):
    """Les séances prévues ce jour-là, [{rang, debut, fin_tranche, minutes}] (UTC) : une par tranche de la journée, à
    une heure tirée au hasard, toujours la même pour ce warm-up et ce jour (un redémarrage ne rebat rien)."""
    j = rang_du_jour(ch, jour)
    if j < 0 or j >= ch["jours"]:
        return []
    n = max(1, round(ch["minutes_jour"] / MINUTES_SEANCE))
    total = minutes_du_jour(ch, j)
    hasard = random.Random(f"{ch['id']}-{jour.isoformat()}")
    a, b = JOURNEE
    tranche = (b - a) / n
    zero = debut_du_jour(jour)
    out = []
    for k in range(n):
        minutes = max(4.0, total / n * hasard.uniform(0.8, 1.2))
        t0 = a + k * tranche
        debut = t0 + hasard.uniform(0, max(0.0, tranche - minutes - 15))
        out.append({"rang": k, "debut": iso(zero + dt.timedelta(minutes=debut)),
                    "fin_tranche": iso(zero + dt.timedelta(minutes=t0 + tranche)), "minutes": round(minutes, 1)})
    return out


def etat_du_plan(stock, ch, maintenant_=None):
    """Le plan du jour avec ce qui en est fait : [{…, faites (min), etat : faite | en_cours | a_venir | due | manquee |
    echec}], et les séances du jour."""
    maintenant_ = maintenant_ or dt.datetime.now(dt.timezone.utc)
    jour = jour_paris(maintenant_)
    if ch.get("rapide"):
        seances, plan = stock.seances(ch["id"], depuis=ch["debut"], limite=1000), plan_rapide(ch)
    else:
        seances, plan = stock.seances(ch["id"], depuis=iso(debut_du_jour(jour))), plan_du_jour(ch, jour)
    out = []
    for s in plan:
        miennes = [x for x in seances if x["rang"] == s["rang"]]
        faites = sum(x["minutes_faites"] for x in miennes)
        if any(x["etat"] == "en_cours" for x in miennes):
            etat = "en_cours"
        elif faites >= 0.7 * s["minutes"]:
            etat = "faite"
        elif any(x["etat"] == "echec" for x in miennes) or len(miennes) >= ESSAIS_PAR_TRANCHE:
            etat = "echec" if any(x["etat"] == "echec" for x in miennes) else "faite"
        elif maintenant_ < utc(s["debut"]):
            etat = "a_venir"
        elif maintenant_ < utc(s["fin_tranche"]):
            etat = "due"
        else:
            etat = "manquee"
        out.append({**s, "faites": round(faites, 1), "etat": etat})
    return out, seances


def en_pause(stock):
    """Le bouton « ⏸ Pause » de la page warm-up : plus
    aucune séance ne part et celle en cours s'arrête ; les publications, elles, continuent."""
    return stock.reglage("pause_warmup", "0") == "1"


def a_lancer(stock, udid, maintenant_=None):
    """La séance à lancer maintenant sur ce téléphone, (warm-up, rang, minutes), ou None : la plus en retard des séances
    dues, s'il y a la place avant la prochaine publication."""
    if en_pause(stock):
        return None
    maintenant_ = maintenant_ or dt.datetime.now(dt.timezone.utc)
    prochaine = stock.prochaine_heure(udid)
    place = (utc(prochaine) - maintenant_).total_seconds() if prochaine else 1e9
    if place < (PLACE_MIN_S + MARGE_PUBLICATION_S) * ECHELLE:
        return None
    candidats = []
    for ch in stock.chauffes(("en_cours",)):
        if ch["udid"] != udid or utc(ch["fin"]) <= maintenant_:
            continue
        plan, _ = etat_du_plan(stock, ch, maintenant_)
        for s in plan:
            if s["etat"] == "due":
                reste = s["minutes"] - s["faites"]
                if reste >= 3:
                    candidats.append((s["debut"], ch, s["rang"], reste))
    if not candidats:
        return None
    # chacun son tour (14/10/2026 : 5 comptes sur un iPhone, la plus en retard seule avait servi 12 séances à l'un et 7 à
    # l'autre) : d'abord le compte qui a le moins scrollé (aujourd'hui, ou depuis le début pour un rapide), puis la plus
    # en retard
    jour = iso(debut_du_jour(jour_paris(maintenant_)))
    fait = {}
    for _, ch, _, _ in candidats:
        if ch["id"] not in fait:
            fait[ch["id"]] = sum(x["minutes_faites"] for x in stock.seances(ch["id"], depuis=ch["debut"] if ch.get("rapide") else jour,
                                                                             limite=1000))
    _, ch, rang, minutes = min(candidats, key=lambda c: (fait[c[1]["id"]], c[0]))
    return ch, rang, minutes


class Seance:
    """Le temps d'une séance et ses compteurs, que la recette consulte : `fini()` dit s'il faut s'arrêter (durée
    atteinte, publication qui approche, file en pause), `regarder(s)` laisse passer s secondes de vidéo."""

    def __init__(self, publieur, t, ch, seance, minutes, maintenant_=None):
        self.publieur, self.t, self.ch, self.id = publieur, t, ch, seance["id"]
        self.duree = minutes * 60 * ECHELLE
        self.t0 = time.monotonic()
        jour = jour_paris(maintenant_)
        self.j = rang_du_jour(ch, jour)
        du_jour = [x for x in publieur.stock.seances(ch["id"], depuis=iso(debut_du_jour(jour))) if x["id"] != seance["id"]]
        if ch.get("rapide"):     # rapide : la « journée », c'est tout le warm-up ; le rang, celui de la séance
            du_jour = [x for x in publieur.stock.seances(ch["id"], depuis=ch["debut"], limite=1000) if x["id"] != seance["id"]]
            self.j = len(du_jour)
        self.likes_jour = sum(x["likes"] for x in du_jour)
        self.likes_com_jour = sum(x.get("likes_commentaires") or 0 for x in du_jour)
        self.likes_com = 0
        self.abonnements_jour = sum(x["abonnements"] for x in du_jour)
        self.mots = mots_de(ch)
        deja = len(publieur.stock.seances(ch["id"])) - 1   # chaque séance part d'un autre mot-clé (la 1re : le 1er)
        self.mots = self.mots[deja % len(self.mots):] + self.mots[:deja % len(self.mots)] if self.mots else []
        self.vues = self.likes = self.abonnements = self.recherches = 0
        self.cherches = []
        self.coupee_par = None
        self._verif = 0.0

    def demarrer(self):
        """Le chrono part quand l'app est ouverte sur le bon compte : la dose, c'est du temps à regarder."""
        self.t0 = time.monotonic()

    def ecoule(self):
        return time.monotonic() - self.t0

    def reste(self):
        return max(0.0, self.duree - self.ecoule())

    def fini(self):
        if self.coupee_par:
            return True
        if self.ecoule() >= self.duree:
            return True
        if time.monotonic() >= self._verif:
            self._verif = time.monotonic() + 5 * ECHELLE
            if self.publieur.pause:
                self.coupee_par = "file des publications mise en pause"
            elif en_pause(self.publieur.stock):
                self.coupee_par = "warm-ups mis en pause"
            elif (self.publieur.stock.chauffe(self.ch["id"]) or {}).get("etat") != "en_cours":
                self.coupee_par = "warm-up arrêté"
            else:
                q = self.publieur.stock.prochaine_heure(self.t.udid)
                if q and (utc(q) - dt.datetime.now(dt.timezone.utc)).total_seconds() <= MARGE_PUBLICATION_S * ECHELLE:
                    self.coupee_par = "une publication arrive : la séance lui laisse le téléphone"
        return bool(self.coupee_par)

    async def regarder(self, secondes):
        """Laisse passer `secondes` de vidéo (accélérées dans les essais), en s'arrêtant net si la séance doit finir."""
        fin = time.monotonic() + secondes * ECHELLE
        while not self.fini():
            reste = fin - time.monotonic()
            if reste <= 0:
                return
            await asyncio.sleep(min(1.0, reste))

    @staticmethod
    def duree_video(niche):
        """Combien de secondes regarder une vidéo : comme un humain, certaines passées vite, d'autres en entier."""
        x = random.random()
        if niche:
            return random.uniform(2, 5) if x < 0.3 else random.uniform(8, 18) if x < 0.75 else random.uniform(25, 45)
        return random.uniform(1.5, 4) if x < 0.5 else random.uniform(5, 12) if x < 0.9 else random.uniform(15, 30)

    def peut_liker(self):
        return bool(self.ch["likes"]) and self.j >= 1 and self.likes_jour + self.likes < LIKES_JOUR

    def peut_suivre(self):
        return bool(self.ch["abonnements"]) and self.j >= 2 and self.abonnements < ABONNEMENTS_SEANCE \
            and self.abonnements_jour + self.abonnements < ABONNEMENTS_JOUR

    def envie_de_liker(self, secondes):
        """Liker cette vidéo de la niche ? Seulement une regardée un moment (8 s ou plus), et pas toutes."""
        return self.peut_liker() and secondes >= 8 and random.random() < P_LIKE

    def envie_de_liker_commentaires(self, secondes):
        """Ouvrir les commentaires de cette vidéo de la niche pour en aimer un ou deux ? Une regardée un moment, pas toutes."""
        return (bool(self.ch["likes"]) and self.j >= 1 and secondes >= 8 and self.likes_com < LIKES_COMMENTAIRES_SEANCE
                and self.likes_com_jour + self.likes_com < LIKES_COMMENTAIRES_JOUR and random.random() < P_COMMENTAIRES)

    def peut_liker_commentaire(self):
        return self.likes_com < LIKES_COMMENTAIRES_SEANCE and self.likes_com_jour + self.likes_com < LIKES_COMMENTAIRES_JOUR

    def envie_de_suivre(self):
        return self.peut_suivre() and random.random() < P_SUIVRE

    def mot(self):
        """Le prochain mot-clé à chercher (chaque séance en commence un autre), ou None."""
        if not self.mots:
            return None
        m = self.mots[self.recherches % len(self.mots)]
        return m

    def cherche(self, mot):
        self.recherches += 1
        self.cherches.append(mot)

    def resume(self):
        return (f"{self.vues} vidéo(s) vue(s), {self.likes} like(s), {self.likes_com} like(s) de commentaires, "
                f"{self.abonnements} abonnement(s), {self.recherches} recherche(s)")


def annoncer(publieur, ch, ctx, s):
    """Le résumé de la séance sur 🔥 warm-up (Discord, salons.py) ; le projet principal seulement (26/10/2026)."""
    import salons
    import sante
    compte = publieur.stock.compte(ch["compte_id"])
    if compte and not sante.du_projet(publieur.stock, compte):
        return
    etat = {"faite": "🔥", "coupee": "✂️", "echec": "❌"}.get(s["etat"], "🔥")
    quand = f"séance {ctx.j + 1} (rapide)" if ch.get("rapide") else f"jour {ctx.j + 1}/{ch['jours']}"
    texte = (f"{etat} {salons.ligne_compte(ch['plateforme'], ch['identifiant'], ch['groupe'])} · {quand}"
             f" · {s['minutes_faites']:g} min · {s['vues']} vidéo(s)" + (f" · {s['likes']} ❤️" if s["likes"] else "")
             + (f" · {s['abonnements']} ➕" if s["abonnements"] else "")
             + (f" · {s.get('likes_commentaires')} 💬❤️" if s.get("likes_commentaires") else "") + (f" · 🔎 {s['mots']}" if s["mots"] else ""))
    if s["etat"] in ("echec", "coupee") and s["erreur"]:
        texte += f"\n{'Ratée' if s['etat'] == 'echec' else 'Coupée'} : {s['erreur'][:300]}"
    publieur.discord.envoyer("WARMUP", texte)


async def jouer(publieur, t, ch, rang, minutes):
    """Une séance de warm-up sur ce téléphone (le verrou des gestes pris : rien d'autre ne touche l'iPhone)."""
    stock = publieur.stock
    s = stock.creer_seance(ch["id"], rang, round(minutes, 1))
    ctx = None
    try:
        async with t.gestes:
            t.occupe = f"warm-up @{ch['identifiant']}"
            r = RobotSeance(t, stock, s, lieux.DONNEES / "captures" / f"seance-{s['id']}")
            ctx = Seance(publieur, t, ch, s, minutes)
            log.info("warm-up @%s : séance %s (%.0f min, jour %s du warm-up)", ch["identifiant"], s["id"], minutes, ctx.j + 1)
            try:
                compte = stock.compte(ch["compte_id"])
                await CHAUFFES[ch["plateforme"]](r, compte, ctx)
                stock.maj_seance(s["id"], etat="coupee" if ctx.coupee_par else "faite", erreur=ctx.coupee_par or "")
                if ctx.coupee_par:
                    await r.etape(f"Séance coupée : {ctx.coupee_par}", capture=False)
            except Exception as e:
                connue = isinstance(e, (ErreurPublication, RuntimeError))
                msg = str(e) if connue else f"{type(e).__name__} : {e}"
                if not connue:
                    log.exception("warm-up, séance %s", s["id"])
                await r.etape(f"Échec : {msg}")
                await r.garder_arbre()
                stock.maj_seance(s["id"], etat="echec", erreur=msg)
            finally:
                stock.maj_seance(s["id"], fin=maintenant(), minutes_faites=round(ctx.ecoule() / 60 / ECHELLE, 1),
                                 vues=ctx.vues, likes=ctx.likes, abonnements=ctx.abonnements, recherches=ctx.recherches,
                                 likes_commentaires=ctx.likes_com,
                                 mots=", ".join(ctx.cherches))
                try:
                    annoncer(publieur, ch, ctx, stock.seance(s["id"]))
                except Exception:
                    log.exception("warm-up, résumé Discord de la séance %s", s["id"])
                try:                      # l'app fermée : plus rien ne se charge en 5G ; l'iPhone sur l'écran d'accueil
                    await t.agent.fermer(APPS[ch["plateforme"]])
                except Exception:
                    pass
                try:
                    await t.agent.profondeur(PROFONDEUR)
                    await t.agent.accueil()
                except Exception:
                    pass
    except Exception:
        log.exception("warm-up, séance %s", s["id"])
        if ctx is None:
            stock.maj_seance(s["id"], etat="echec", fin=maintenant(), erreur="séance pas lancée (voir le journal du service)")
    finally:
        t.occupe = None
        publieur.en_cours.pop(t.udid, None)
