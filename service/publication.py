"""publication.py : la file des publications. Toutes les 5 s, pour chaque téléphone prêt et libre, la prochaine
publication due est jouée :
  1. la vidéo est prise dans le dossier des vidéos, après avoir relu qu'elle y est toujours (le verrou) ;
  2. elle est rangée dans Photos par le câble (photos.py) ;
  3. la recette de la plateforme la publie, une capture par étape ;
  4. en ligne, son lien est noté (base, et donnees/liens.csv).
Une publication ratée n'est jamais relancée toute seule : l'utilisateur regarde le déroulé et décide."""
import asyncio
import logging
import os
import time

import chauffe
import liens
import lieux
import photos
import programmation
import videos
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
                        if lien:
                            await self.noter_lien(pid, p, lien)
                        else:
                            self.chercher_lien(pid, p, compte, debut)
                except Exception as e:
                    connue = isinstance(e, (ErreurPublication, photos.ErreurImport, RuntimeError))
                    msg = str(e) if connue else f"{type(e).__name__} : {e}"
                    if not connue:
                        log.exception("publication %s", pid)
                    await r.etape(f"Échec : {msg}")
                    await r.garder_arbre()
                    self.stock.maj_publication(pid, etat="echec", fin=maintenant(), erreur=msg)
                finally:
                    try:
                        await t.agent.profondeur(PROFONDEUR)
                        await t.agent.accueil()
                    except Exception:
                        pass
        finally:
            t.occupe = None
            self.en_cours.pop(t.udid, None)

    def chercher_lien(self, pid, p, compte, depuis):
        """Le lien de la vidéo, retrouvé à part par Scrape Creators (liens.py) : le téléphone est déjà libre pour la
        publication suivante (04/10/2026)."""
        async def tache():
            try:
                lien = await liens.retrouver(compte["plateforme"], compte["identifiant"], p["legende"], depuis)
            except Exception as e:
                log.warning("publication %s : lien pas retrouvé (%s)", pid, e)
                lien = None
            if not lien:
                self.stock.etape(pid, "Lien pas retrouvé (Scrape Creators absent ou sans réponse) : vérifie sur le "
                                      "compte")
                return
            self.stock.maj_publication(pid, lien=lien)
            self.stock.etape(pid, f"En ligne : {lien}")
            await self.noter_lien(pid, p, lien)

        tache_lien = asyncio.create_task(tache())
        self.taches.add(tache_lien)
        tache_lien.add_done_callback(self.taches.discard)

    async def noter_lien(self, pid, p, lien):
        try:
            await videos.signaler_publication(self.http, p["video"], lien)
            self.stock.etape(pid, "Lien noté dans donnees/liens.csv")
        except Exception as e:
            log.warning("publication %s : lien pas noté dans liens.csv (%s)", pid, e)

    async def video(self, p):
        """Le fichier à publier : seules les vidéos du dossier des vidéos partent (« dossier:<chemin> ») ; sa présence
        est relue à cet instant, puis il est copié une fois dans donnees/videos/."""
        v = p["video"]
        if not v.startswith(videos.PREFIXE):
            raise ErreurPublication("seules les vidéos du dossier des vidéos peuvent partir")
        await videos.verifier_publiable(self.http, v)
        dest = lieux.DONNEES / "videos" / f"{p['id']}-{videos.nom_de_travail(v)}"
        if not dest.exists():
            await videos.telecharger(self.http, v, dest)
        return dest
