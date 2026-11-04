"""publication.py : la file des publications. Toutes les 5 s, pour chaque téléphone prêt et libre, la prochaine
publication due est jouée :
  1. la vidéo est prise dans le dossier des vidéos, après avoir relu qu'elle y est toujours (le verrou) ;
  2. elle est rangée dans Photos par le câble (photos.py) ;
  3. la recette de la plateforme la publie, une capture par étape ;
  4. en ligne, le lien repart au centre, d'où le tracking la suit.
Une publication ratée n'est jamais relancée toute seule, sauf un échec passager
d'une page avant le dernier bouton : une fois, au créneau libre suivant (27/10/2026)."""
import asyncio
import logging
import os
import time

import chauffe
import inventaire
import sonde
import liens
import lieux
import photos
import programmation
import salons
import videos
import sante
from recettes import RECETTES
from recettes.base import ErreurPublication, Robot
from stock import maintenant
from wda import PROFONDEUR

log = logging.getLogger("publication")
PROGRAMMATION_S = int(os.environ.get("TELEPHONES_PROGRAMMATION_S") or 60)   # les essais le raccourcissent


class Publieur:
    def __init__(self, parc, stock, http):
        self.parc, self.stock, self.http = parc, stock, http
        self.en_cours = {}          # udid → tâche
        self.taches = set()         # les liens cherchés en arrière-plan (gardés ici le temps qu'ils tournent)
        self.sans_wifi = set()      # les téléphones dont la file attend le Wi-Fi
        self.discord = salons.Discord(http)   # les salons du service sur Discord (📤 publications, 🩺 santé-pages…)
        self.inventaires = {}       # udid → le dernier inventaire des comptes (inventaire.py, bouton « Rafraîchir »)
        self.inventaires_demandes = set()
        self.sondes, self.sondes_demandees = {}, set()   # sonde.py : les commentaires vus, avant leurs likes (14/10/2026)

    @property
    def pause(self):
        return self.stock.reglage("pause", "0") == "1"

    def sans_reseau(self, t):
        """Publier seulement en Wi-Fi (réglage « wifi_obligatoire », oui par défaut) : le 05/10/2026 à 18 h 39, le
        partage de connexion parti, l'iPhone n'avait plus que le réseau mobile sans données ; l'envoi Instagram a tenu
        3 min puis « Une erreur s'est produite ». Sans Wi-Fi, les publications attendent en file au lieu d'échouer."""
        return self.stock.reglage("wifi_obligatoire", "1") == "1" and not getattr(t, "ip", None)

    async def boucle(self):
        self.stock.interrompues()
        self.stock.seances_interrompues()
        prochaine_programmation = 0
        while True:
            if time.monotonic() >= prochaine_programmation:   # les vidéos des dossiers de groupe, aux créneaux (programmation.py)
                prochaine_programmation = time.monotonic() + PROGRAMMATION_S
                if self.stock.finir_chauffes():
                    log.info("warm-up terminé : le compte rentre dans la rotation des publications")
                try:
                    await programmation.programmer(self.stock, self.http)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("programmation automatique : %s", e)
            try:
                if not self.pause:
                    for t in list(self.parc.telephones.values()):
                        if self.sans_reseau(t):
                            if t.udid not in self.sans_wifi:
                                self.sans_wifi.add(t.udid)
                                log.warning("%s sans Wi-Fi : les publications attendent en file", t.nom)
                            continue
                        if t.udid in self.sans_wifi:
                            self.sans_wifi.discard(t.udid)
                            log.info("%s de nouveau en Wi-Fi : la file repart", t.nom)
                        if t.pret and not t.occupe and t.udid not in self.en_cours:
                            p = self.prochaine(t)
                            if p:
                                self.en_cours[t.udid] = asyncio.create_task(self.jouer(t, p))
                            elif t.udid in self.inventaires_demandes:   # « Rafraîchir les comptes » : avant le warm-up
                                self.en_cours[t.udid] = asyncio.create_task(inventaire.jouer(self, t))
                            elif t.udid in self.sondes_demandees:
                                self.en_cours[t.udid] = asyncio.create_task(sonde.jouer(self, t))
                            else:                # rien à publier : une séance de warm-up, s'il y en a une de due
                                d = chauffe.a_lancer(self.stock, t.udid)
                                if d:
                                    self.en_cours[t.udid] = asyncio.create_task(chauffe.jouer(self, t, *d))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("file des publications")
            await asyncio.sleep(5)

    def lancer_seance(self, t, ch, minutes):
        """Une séance de warm-up tout de suite (bouton « Séance maintenant ») : seulement si le téléphone est libre."""
        if not t.pret or t.occupe or t.udid in self.en_cours:
            raise RuntimeError(f"{t.nom} est occupé ({t.occupe or 'pas prêt'}) : réessaie dans un moment")
        self.en_cours[t.udid] = asyncio.create_task(chauffe.jouer(self, t, ch, None, minutes))

    def prochaine(self, t):
        """La prochaine publication à jouer sur ce téléphone. Une publication programmée qui a manqué son créneau de
        plus de 30 min (téléphone débranché ou sans réseau, file en pause) ne se rattrape pas en rafale : elle part,
        avec sa sœur du même groupe, au prochain créneau libre (programmation.py ; 06/10/2026)."""
        for _ in range(50):
            p = self.stock.prochaine(t.udid, int(self.stock.reglage("intervalle_min", "30")))
            retard = p and programmation.en_retard(self.stock, p)
            if not retard:
                return p
            lot = [x for x in programmation.lot_de(self.stock, p) if x["id"] == p["id"] or programmation.en_retard(self.stock, x)]
            prevue = programmation.a_paris(p["quand"]).strftime("%H:%M")
            if not programmation.reporter(self.stock, lot, f"Créneau de {prevue} manqué ({retard} min de retard)"):
                return p   # aucun créneau libre : elle part quand même
        return None

    async def jouer(self, t, p):
        pid = p["id"]
        debut = time.time()
        try:
            async with t.gestes:
                t.occupe = f"publication n° {pid}"
                self.stock.maj_publication(pid, etat="en_cours", debut=maintenant(), fin=None, erreur="",
                                           tentatives=p["tentatives"] + 1)
                compte = self.stock.compte(p["compte_id"])
                r = Robot(t, p, self.stock, lieux.DONNEES / "captures" / str(pid))
                try:
                    fichier = await self.video(p)
                    await photos.importer(t, fichier, f"auto-{pid}.mp4")
                    await r.etape("Vidéo rangée dans Photos")
                    lien = await RECETTES[compte["plateforme"]](r, compte, p["legende"])
                    if r.repetition:
                        self.stock.maj_publication(pid, etat="repete", fin=maintenant())
                        await r.etape("Répétition finie : rien n'a été publié")
                    else:
                        self.stock.maj_publication(pid, etat="publie", fin=maintenant(), lien=lien or "")
                        self.annoncer(pid, compte, p, "publie", lien=lien)
                        if lien:
                            await self.noter_lien(pid, p, lien)
                        else:
                            self.chercher_lien(pid, p, compte, debut)
                except videos.PasPubliable as e:
                    await self.pas_publiable(pid, e)
                except Exception as e:
                    connue = isinstance(e, (ErreurPublication, photos.ErreurImport, RuntimeError))
                    msg = str(e) if connue else f"{type(e).__name__} : {e}"
                    if not connue:
                        log.exception("publication %s", pid)
                    await r.etape(f"Échec : {msg}")
                    await r.garder_arbre()
                    self.stock.maj_publication(pid, etat="echec", fin=maintenant(), erreur=msg)
                    if not p["repetition"]:
                        self.surveiller_echecs(compte, msg)
                        self.annoncer(pid, compte, p, "echec", erreur=msg, relance=self.relancer_si_passager(pid, compte, msg))
                finally:
                    try:
                        await t.agent.profondeur(PROFONDEUR)
                        await t.agent.accueil()
                    except Exception:
                        pass
        finally:
            t.occupe = None
            self.en_cours.pop(t.udid, None)

    async def pas_publiable(self, pid, e):
        """La vidéo n'est pas publiable au moment de partir (17/10/2026 : un contrôle renvoie un remontage mal cadré « en retours », puis le refait, sous un autre nom). Ce n'est
        pas un échec (ni message ❌, ni alerte d'échecs). Le créneau ne reste pas vide (27/10/2026) : la prochaine
        publication prête de chaque compte de la page prend sa place (programmation.remplacer). La vidéo fautive, en
        retouche, est reportée avec ses sœurs du même groupe au créneau libre suivant, annulée au 4e report ; refusée, ou
        plus dans le dossier, elle est annulée."""
        p = self.stock.publication(pid)
        lot = programmation.lot_de(self.stock, p)
        motif = "en retouche" if e.etat in videos.EN_RETOUCHE else programmation.raison_pas_publiable(e.etat)
        await programmation.remplacer(self.stock, self.http, lot, f"à la place de « {p['titre']} » ({motif})")
        if e.etat in videos.EN_RETOUCHE:
            reports = sum(1 for x in self.stock.etapes(pid) if (x.get("message") or "").startswith("En retouche"))
            if reports < 3 and programmation.reporter(self.stock, lot, f"En retouche (état : {e.etat})"):
                return
        raison = programmation.raison_pas_publiable(e.etat)
        programmation.annuler(self.stock, lot, raison)
        log.info("publication %s annulée (avec %s) : la vidéo est %s", pid, len(lot) - 1, raison)

    def relancer_si_passager(self, pid, compte, msg):
        """Un échec passager d'une publication programmée sur une page (l'agent ou la base injoignables, la
        pellicule, la liste des comptes, un bouton pas trouvé) est relancé UNE fois, au créneau libre suivant de son compte
        (27/10/2026 : 6 échecs de ce genre en 4 jours, jamais relancés). Jamais pour un compte déconnecté ou bloqué, ni
        pour une publication qui a pu partir : « Prêt à publier » passé, le dernier bouton a peut-être été touché. Rend
        l'heure de la relance (« …Z ») ou None."""
        p = self.stock.publication(pid)
        compte = compte or {}
        if not programmation.passager(msg) or compte.get("plateforme") not in ("tiktok", "instagram") or not programmation.de_page(self.stock, p):
            return None
        etapes = [x.get("message") or "" for x in self.stock.etapes(pid)]
        if any(m.startswith("Prêt à publier") for m in etapes) or any(m.startswith(programmation.RELANCE) for m in etapes):
            return None
        quand = programmation.reporter(self.stock, [p], programmation.RELANCE)
        if quand:
            log.info("publication %s : échec passager (%s), relancée au %s", pid, msg[:80], programmation.a_paris(quand).strftime("%d/%m à %H:%M"))
        return quand

    def chercher_lien(self, pid, p, compte, depuis):
        """Le lien de la vidéo, retrouvé à part par Scrape Creators (liens.py) : le téléphone est déjà libre pour la
        publication suivante (04/10/2026)."""
        async def tache():
            try:
                cid = p.get("compte_id")
                pris = {x["lien"] for x in self.stock.dernieres_publications(cid, 30) if x["lien"]} if cid else set()
                lien = await liens.retrouver(compte["plateforme"], compte["identifiant"], p["legende"], depuis, pris)
            except Exception as e:
                log.warning("publication %s : lien pas retrouvé (%s)", pid, e)
                lien = None
            if not lien:
                self.stock.etape(pid, "Lien pas retrouvé par Scrape Creators : vérifie sur le compte et colle-le à la "
                                      "main dans le calendrier")
                self.annoncer_lien(pid, None)
                return
            self.stock.maj_publication(pid, lien=lien)
            self.stock.etape(pid, f"En ligne : {lien}")
            self.annoncer_lien(pid, lien)
            await self.noter_lien(pid, p, lien)

        tache_lien = asyncio.create_task(tache())
        self.taches.add(tache_lien)
        tache_lien.add_done_callback(self.taches.discard)

    # ── Discord (salons.py) : 📤 publications, 🩺 santé-pages ─────────────────────────────────────────────────
    def texte_publication(self, pid, etat, lien=None, erreur=None, relance=None):
        p = self.stock.publication(pid)
        compte = self.stock.compte(p["compte_id"])
        base = f"{salons.ligne_compte(compte['plateforme'], compte['identifiant'], compte['groupe'])} · « {p['titre']} » · n° {pid}"
        if etat == "echec":
            suite = (f"\n🔁 Échec passager : relancée une fois, le {programmation.a_paris(relance).strftime('%d/%m à %H:%M')}"
                     if relance else "")
            return f"❌ {base}\n{(erreur or p['erreur'] or '')[:400]}{suite}"
        if lien:
            return f"✅ {base}\n{lien}"
        return f"✅ {base}\n" + ("🔎 lien en cours de recherche…" if etat == "publie" else "⚠️ lien pas retrouvé : vérifie sur le compte")

    def annoncer(self, pid, compte, p, etat, lien=None, erreur=None, relance=None):
        """La publication sur 📤 publications (complétée par son lien quand il arrive) ; un échec relancé le dit."""
        if not sante.du_projet(self.stock, compte):
            return                    # Discord = le projet principal seulement : rien pour un autre projet
        def apres(mid):
            self.stock.maj_publication(pid, discord=mid)
            x = self.stock.publication(pid)
            if etat == "publie" and x["lien"] and x["lien"] != lien:     # le lien est arrivé pendant l'envoi du message
                self.discord.completer("PUBLICATIONS", mid, self.texte_publication(pid, "lien", x["lien"]))
        self.discord.envoyer("PUBLICATIONS", self.texte_publication(pid, etat, lien, erreur, relance), apres=apres)

    def annoncer_lien(self, pid, lien):
        p = self.stock.publication(pid)
        if p and p.get("discord"):
            self.discord.completer("PUBLICATIONS", p["discord"], self.texte_publication(pid, "lien" if lien else "sans_lien", lien))

    def surveiller_echecs(self, compte, msg):
        """Un compte plus connecté dans l'app, ou 2 publications ratées d'affilée : 🩺 santé-pages."""
        if not sante.du_projet(self.stock, compte):
            return                    # Discord = le projet principal seulement
        nom = f"{salons.PLATEFORME.get(compte['plateforme'], compte['plateforme'])} @{compte['identifiant']}"
        page = f"\nPage : {compte['groupe']}" if compte["groupe"] else ""
        if "n'est pas parmi" in msg or "pas connecté" in msg:
            sante.alerter(self.stock, self.discord, f"compte:{compte['id']}", "deconnecte", "rouge", f"🔴 Compte déconnecté · {nom}",
                          f"{msg[:500]}{page}\nReconnecte-le à la main dans l'app, sur l'iPhone.")
            return
        derniers = self.stock.dernieres_publications(compte["id"], 2)
        if len(derniers) == 2 and all(x["etat"] == "echec" for x in derniers):
            sante.alerter(self.stock, self.discord, f"compte:{compte['id']}", "echecs", "rouge", f"🔴 2 publications ratées d'affilée · {nom}",
                          f"dernière erreur : {msg[:500]}{page}\nRegarde les captures du déroulé dans l'onglet Téléphones.")

    async def noter_lien(self, pid, p, lien):
        try:
            await videos.signaler_publication(self.http, p["video"], lien)
            self.stock.etape(pid, "Lien noté dans donnees/liens.csv")
        except Exception as e:
            log.warning("publication %s : lien pas noté dans liens.csv (%s)", pid, e)

    async def video(self, p):
        """Le fichier à publier : seules les vidéos du dossier partent (« dossier:<chemin> ») ; sa présence est relue à
        cet instant, puis il est copié une fois dans donnees/videos/ (de nouveau s'il a changé depuis)."""
        v = p["video"]
        if not v.startswith(videos.PREFIXE):
            raise ErreurPublication("seules les vidéos du dossier des vidéos peuvent partir")
        return await videos.copie_locale(self.http, v, lieux.DONNEES / "videos")
