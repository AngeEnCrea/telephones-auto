"""inventaire.py : les comptes connectés sur chaque iPhone, ajoutés tout seuls à la liste des comptes.

Le bouton « 🔄 Rafraîchir les comptes » (page warm-up) demande un inventaire à chaque téléphone branché ; la file le
joue dès que le téléphone est libre (une publication passe avant, une séance de warm-up après). Il ouvre TikTok puis
Instagram, lit les comptes connectés (recettes.LISTES) et ajoute ceux qui manquent, rattachés à ce téléphone, SANS
projet ni groupe : un compte tout neuf ne rentre dans aucune rotation de publication tant que l'utilisateur ne l'a pas mis en
warm-up (le formulaire lui donne alors son projet et son groupe) ou rangé à la main (onglet Comptes)."""
import logging

import lieux
from recettes import APPS, LISTES
from recettes.base import RobotInventaire
from stock import maintenant
from wda import PROFONDEUR

log = logging.getLogger("inventaire")


async def jouer(publieur, t):
    stock = publieur.stock
    etat = publieur.inventaires[t.udid] = {"telephone": t.nom, "etat": "en_cours", "debut": maintenant(), "fin": None,
                                            "trouves": {}, "ajoutes": [], "erreurs": [], "journal": []}
    try:
        async with t.gestes:
            t.occupe = "inventaire des comptes"
            r = RobotInventaire(t, lieux.DONNEES / "captures" / f"inventaire-{t.udid[:8]}", etat["journal"])
            for plateforme, lister in LISTES.items():
                try:
                    etat["trouves"][plateforme] = await lister(r)
                except Exception as e:
                    log.exception("inventaire %s sur %s", plateforme, t.nom)
                    etat["erreurs"].append(f"{plateforme} : {e}")
                    await r.etape(f"{plateforme} : échec ({e})")
                finally:
                    try:
                        await t.agent.fermer(APPS[plateforme])
                    except Exception:
                        pass
            connus = {(c["plateforme"], c["identifiant"].lower()) for c in stock.comptes()}
            for plateforme, noms in etat["trouves"].items():
                for nom in noms:
                    if (plateforme, nom) not in connus:
                        c = stock.ajouter_compte(plateforme, nom, udid=t.udid,
                                                 note=f"trouvé sur {t.nom} le {maintenant()[:10]} (Rafraîchir)")
                        connus.add((plateforme, nom))
                        etat["ajoutes"].append({"id": c["id"], "plateforme": plateforme, "identifiant": nom})
                        log.info("compte ajouté : %s @%s (sur %s)", plateforme, nom, t.nom)
            try:
                await t.agent.profondeur(PROFONDEUR)
                await t.agent.accueil()
            except Exception:
                pass
        etat["etat"] = "fini" if not etat["erreurs"] else "en_partie"
    except Exception as e:
        log.exception("inventaire sur %s", t.nom)
        etat["etat"], etat["erreurs"] = "echec", etat["erreurs"] + [str(e)]
    finally:
        etat["fin"] = maintenant()
        t.occupe = None
        publieur.inventaires_demandes.discard(t.udid)
        publieur.en_cours.pop(t.udid, None)
