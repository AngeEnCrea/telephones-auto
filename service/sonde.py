"""sonde.py : regarder comment s'affichent les commentaires d'une vidéo, sans rien toucher d'autre (14/10/2026, avant
d'écrire les likes de commentaires du warm-up demandés par Note : « liker des commentaires c'est fort aussi »).

Jouée par la file comme un inventaire (téléphone libre, une publication passe avant) : TikTok (le fil, ses commentaires)
puis Instagram (l'onglet Reels, ses commentaires). À chaque étape : une capture et l'arbre de l'écran, gardés dans
captures/sonde-commentaires. Aucun like, aucun abonnement, aucun commentaire écrit : on ouvre, on regarde, on ferme."""
import asyncio
import json
import logging
import time

import lieux
from recettes import APPS, instagram, tiktok
from recettes.base import RobotInventaire
from stock import maintenant
from wda import PROFONDEUR

log = logging.getLogger("sonde")


async def garder(r, nom, profondeur):
    t0 = time.monotonic()
    try:
        (r.dossier / f"{nom}.png").write_bytes(await r.a.capture())
    except Exception as e:
        r.journal.append(f"capture {nom} : {e}")
    try:
        await r.a.profondeur(profondeur)
        arbre = await asyncio.wait_for(r.a.arbre(), 150)
        (r.dossier / f"{nom}-{profondeur}.json").write_text(json.dumps(arbre, ensure_ascii=False), encoding="utf-8")
        r.journal.append(f"{nom} : arbre à {profondeur} niveaux en {time.monotonic() - t0:.0f} s")
    except Exception as e:
        r.journal.append(f"arbre {nom} : {type(e).__name__} {e}")


async def jouer(publieur, t):
    etat = publieur.sondes[t.udid] = {"telephone": t.nom, "etat": "en_cours", "debut": maintenant(), "fin": None, "journal": []}
    try:
        async with t.gestes:
            t.occupe = "sonde des commentaires"
            r = RobotInventaire(t, lieux.DONNEES / "captures" / "sonde-commentaires", etat["journal"])
            try:   # TikTok : sur une vidéo, jamais l'arbre (il y prend des minutes et bloque l'agent) : des captures
                await r.lancer_propre(tiktok.BUNDLE)
                await asyncio.sleep(5)
                png = await r.a.capture()
                (r.dossier / "tt-1-fil.png").write_bytes(png)
                bandes = [x for x in tiktok._bandes(png, lambda c: min(c[0], c[1], c[2]) >= 200, (338, 380, 380, 720))
                          if x["h"] <= 60]
                r.journal.append("TikTok : icônes blanches à droite (y) : " + ", ".join(f"{x['y']:.0f}/{x['h']:.0f}" for x in bandes))
                (r.dossier / "tt-bandes.json").write_text(json.dumps(bandes), encoding="utf-8")
                # les icônes (h ≥ 18) sans leurs chiffres : cœur, commentaires, favoris, partage ; un cœur déjà rouge
                # n'est pas blanc : la 1re icône blanche est alors les commentaires (14/10/2026 : le chiffre sous le
                # cœur, touché, a liké la vidéo)
                icones = [x for x in bandes if x["h"] >= 18]
                rouge = tiktok.coeur_rouge(tiktok.bandes_rouges(png))
                cible = icones[0] if rouge else (icones[1] if len(icones) >= 2 else None)
                r.journal.append(f"TikTok : icônes {[round(x['y']) for x in icones]}, cœur rouge {rouge}, commentaires à {cible and round(cible['y'])}")
                if cible:
                    await tiktok.toucher_fenetre(r, cible["x"], cible["y"])
                    await asyncio.sleep(3)
                    (r.dossier / "tt-2-commentaires.png").write_bytes(await r.a.capture())
                    await tiktok.glisser(r)   # fait défiler les commentaires (le panneau couvre le milieu de l'écran)
                    await asyncio.sleep(1)
                    (r.dossier / "tt-2b-commentaires.png").write_bytes(await r.a.capture())
                    await tiktok.toucher_fenetre(r, (t.taille or (390, 844))[0] / 2, 200)   # au-dessus du panneau, sur la vidéo
                    await asyncio.sleep(2)
                    (r.dossier / "tt-3-ferme.png").write_bytes(await r.a.capture())
                r.journal.append("TikTok : captures faites")
            except Exception as e:
                etat["journal"].append(f"TikTok : {type(e).__name__} {e}")
            finally:
                try:
                    await t.agent.fermer(APPS["tiktok"])
                except Exception:
                    pass
            try:   # Instagram : l'onglet Reels, puis les commentaires du reel
                await r.a.profondeur(instagram.PROFONDEUR)
                await r.lancer_propre(instagram.BUNDLE)
                await r.alertes()
                await instagram.fermer_intrus(r)
                await asyncio.sleep(3)
                await instagram.revenir_aux_onglets(r)
                await r.toucher("reels-tab", delai=10)
                await asyncio.sleep(4)
                await garder(r, "ig-1-reel", instagram.PROFONDEUR_PROFIL)
                b = await r.premier_touchable("name == 'comment-button' OR label CONTAINS[c] 'commentaire'")
                r.journal.append(f"Instagram : bouton des commentaires {'trouvé' if b else 'pas trouvé'}")
                if b:
                    await r.a.cliquer(b)
                    await asyncio.sleep(2.5)
                    await garder(r, "ig-2-commentaires", 30)
                    await r.a.toucher((t.taille or (390, 844))[0] / 2, 110)
                    await asyncio.sleep(1.5)
                    await garder(r, "ig-3-ferme", 8)
            except Exception as e:
                etat["journal"].append(f"Instagram : {type(e).__name__} {e}")
            finally:
                try:
                    await t.agent.fermer(APPS["instagram"])
                except Exception:
                    pass
            try:
                await t.agent.profondeur(PROFONDEUR)
                await t.agent.accueil()
            except Exception:
                pass
        etat["etat"] = "fini"
    except Exception as e:
        log.exception("sonde sur %s", t.nom)
        etat["etat"] = "echec"
        etat["journal"].append(str(e))
    finally:
        etat["fin"] = maintenant()
        t.occupe = None
        publieur.sondes_demandees.discard(t.udid)
        publieur.en_cours.pop(t.udid, None)
