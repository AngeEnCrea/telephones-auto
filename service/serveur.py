"""serveur.py : l'interface (dossier interface/) et son API, sous /telephones/. N'écoute que 127.0.0.1 (réglage
« hote ») : on y entre depuis l'ordinateur lui-même, ou par un relais que tu choisis (un VPN privé, par exemple).

Garde : toute requête qui change quelque chose doit être en JSON (Content-Type application/json) et, si le
navigateur dit d'où elle vient (Origin), venir de la même adresse. Une page web piégée ne peut donc pas faire
toucher l'écran de l'iPhone à distance depuis ton navigateur."""
import asyncio
import datetime as dt
import io
import json
import logging
import re
import statistics
import time
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

import chauffe
import goios
import journal
import lieux
import photos
import programmation
import salons
import videos
import sante
import liens
import partage
from recettes import APPS, CHAUFFES, PRETES, PROFONDEURS
from stock import PLATEFORMES, maintenant
from wda import PROFONDEUR, ErreurAgent

log = logging.getLogger("serveur")
P = lieux.PREFIXE
INTERFACE = lieux.RACINE / "interface"
BOUTONS = ("home", "volumeUp", "volumeDown")


def erreur(code, message):
    return web.json_response({"erreur": message}, status=code)


def recompresser(jpg, qualite, largeur=0):
    """Une image du flux, réencodée (et réduite si `largeur`) ; telle quelle si elle ne se lit pas."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(jpg))
        im.load()
    except Exception:
        return jpg
    if largeur and im.width > largeur:
        im = im.resize((largeur, round(im.height * largeur / im.width)))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=qualite)
    return out.getvalue()


def iso_utc(valeur):
    """Une heure envoyée par l'interface (ISO avec fuseau) → UTC ISO à la seconde, comme stock.maintenant()."""
    if not valeur:
        return None
    d = dt.datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("heure sans fuseau")
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@web.middleware
async def garde(req, handler):
    if req.method not in ("GET", "HEAD", "OPTIONS"):
        if req.content_type != "application/json":
            return erreur(415, "requête en JSON seulement")
        origine = req.headers.get("Origin")
        hotes = {req.host, req.headers.get("X-Forwarded-Host", "")}   # un relais garde l'hôte d'origine
        if origine and urlparse(origine).netloc not in hotes:
            log.warning("requête refusée : origine %s, hôte %s", origine, hotes)
            return erreur(403, "origine refusée")
    try:
        return await handler(req)
    except web.HTTPException:
        raise
    except ErreurAgent as e:
        return erreur(502, f"agent de l'iPhone : {e}")
    except goios.ErreurIos as e:
        return erreur(502, str(e))
    except (ValueError, KeyError, TypeError) as e:
        return erreur(400, f"requête invalide : {e}")


def creer(parc, stock, publieur, http):
    app = web.Application(middlewares=[garde], client_max_size=2 * 1024 ** 2)
    r = web.RouteTableDef()
    cache = {"videos": (0, [])}

    def telephone(req):
        t = parc.telephone(req.match_info["udid"])
        if not t:
            raise web.HTTPNotFound(text=json.dumps({"erreur": "téléphone inconnu"}), content_type="application/json")
        return t

    def pour_la_main(req):
        """Le téléphone, prêt et pas occupé par un robot (sauf ?force=1)."""
        t = telephone(req)
        if not t.pret:
            raise web.HTTPConflict(text=json.dumps({"erreur": "le téléphone n'est pas prêt"}), content_type="application/json")
        if t.occupe and not req.query.get("force"):
            raise web.HTTPConflict(text=json.dumps({"erreur": f"le robot travaille ({t.occupe}) : attends la fin ou mets la file en pause"}),
                                   content_type="application/json")
        return t

    # ── l'interface ─────────────────────────────────────────────────────────────────────────────────────
    @r.get("/")
    @r.get(P)
    async def racine(req):
        raise web.HTTPFound(P + "/")

    @r.get(P + "/")
    async def page(req):
        return web.FileResponse(INTERFACE / "index.html", headers={"Cache-Control": "no-cache"})

    @r.get(P + "/calendrier")
    async def page_calendrier(req):
        return web.FileResponse(INTERFACE / "calendrier.html", headers={"Cache-Control": "no-cache"})

    @r.get(P + "/warmup")
    async def page_warmup(req):
        return web.FileResponse(INTERFACE / "warmup.html", headers={"Cache-Control": "no-cache"})

    @r.get(P + "/i/{nom}")
    async def fichier(req):
        f = INTERFACE / req.match_info["nom"]
        if f.parent != INTERFACE or not f.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "no-cache"})

    # ── état ────────────────────────────────────────────────────────────────────────────────────────────
    @r.get(P + "/api/etat")
    async def etat(req):
        return web.json_response({"parc": parc.dict(), "pause": publieur.pause, "sur_le_pc": lieux.SUR_LE_PC,
                                  "apps": APPS, "maintenant": maintenant()})

    @r.get(P + "/api/journal")
    async def lignes(req):
        return web.json_response(list(journal.DERNIERES)[-250:])

    @r.get(P + "/api/calendrier")
    async def calendrier(req):
        """Ce qui sort quand (04/10/2026) : les vraies
        publications de `jours` jours à partir de `debut` (AAAA-MM-JJ, heure de Paris ; lundi de cette semaine par
        défaut), regroupées par vidéo et par groupe de comptes (le TikTok et l'Insta d'un groupe partent ensemble), et,
        par projet, ses groupes avec leur décalage : l'interface y dessine les créneaux encore libres."""
        paris = programmation.PARIS
        try:
            jour = dt.date.fromisoformat(req.query["debut"]) if req.query.get("debut") else None
        except ValueError:
            return erreur(400, "debut : AAAA-MM-JJ")
        if not jour:
            auj = dt.datetime.now(paris).date()
            jour = auj - dt.timedelta(days=auj.weekday())
        jours = min(max(int(req.query.get("jours") or 7), 1), 42)
        t0 = dt.datetime(jour.year, jour.month, jour.day, tzinfo=paris)
        t1 = t0 + dt.timedelta(days=jours)
        z = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
        entrees = {}
        for x in stock.publications_entre(z(t0), z(t1)):
            groupe = x["groupe"] or "@" + x["identifiant"]
            # un envoi (📤 Publier, programmation) et son groupe ; sinon la même vidéo, le même groupe, la même minute
            cle = ("e", x["envoi_id"], groupe) if x["envoi_id"] else ("v", x["video"], groupe, (x["moment"] or "")[:16])
            e = entrees.get(cle)
            if not e:
                slug, pid = videos.decouper(x["video"]) if x["video"].startswith(videos.PREFIXE) else (None, None)
                e = entrees[cle] = {"video": x["video"], "titre": x["titre"] or x["video"], "projet": x["projet"] or slug, "groupe": groupe,
                                    "quand": x["moment"], "vignette": None, "comptes": []}
            e["quand"] = min(e["quand"], x["moment"])
            e["comptes"].append({"publication": x["id"], "plateforme": x["plateforme"], "identifiant": x["identifiant"],
                                 "etat": x["etat"], "lien": x["lien"] or None, "erreur": x["erreur"] or None, "quand": x["moment"]})
        for e in entrees.values():
            etats = {c["etat"] for c in e["comptes"]}
            e["etat"] = ("publiee" if etats == {"publie"} else "en_cours" if "en_cours" in etats else "prevue" if etats == {"en_attente"}
                         else "echec" if "echec" in etats and "en_attente" not in etats and "publie" not in etats else "partielle")
        projets = []
        for slug in stock.projets_des_comptes():
            comptes = stock.comptes_du_projet(slug)
            noms = programmation.ordre_groupes(programmation.nom_groupe(c) for c in comptes)
            projets.append({"slug": slug, "groupes": [{"nom": g, "decalage_min": programmation.decalage(stock, noms, g),
                                                        # téléphones partagés avec un autre projet : ses propres créneaux (partage.py)
                                                        "creneaux": partage.creneaux_groupe(stock, slug, g),
                                                        "comptes": [{"plateforme": c["plateforme"], "identifiant": c["identifiant"]}
                                                                    for c in comptes if programmation.nom_groupe(c) == g]}
                                                       for g in noms]})
        return web.json_response({"debut": jour.isoformat(), "jours": jours, "aujourdhui": dt.datetime.now(paris).date().isoformat(),
                                  "telephones": [{"nom": t.nom, "pret": t.pret, "wifi": bool(t.ip)} for t in parc.telephones.values()],
                                  "wifi_obligatoire": stock.reglage("wifi_obligatoire", "1") == "1",
                                  "creneaux": [f"{h:02d}:{m:02d}" for h, m in programmation.creneaux(stock)],
                                  "auto": stock.reglage("programmation_auto", "1") == "1", "variation_min": programmation.VARIATION_MIN,
                                  "projets": projets, "entrees": sorted(entrees.values(), key=lambda e: e["quand"]),
                                  "chauffes": len(stock.chauffes(("en_cours",))),
                                  "legendes_instagram": programmation.legendes_instagram(stock),
                                  "facebook_instagram": {p: stock.reglage(f"facebook_instagram:{p}", "0") == "1" for p in stock.projets_des_comptes()}})

    # ── le hub de gestion : la santé de
    # chaque page (ses comptes), les téléphones, les alertes des dernières 48 h, les crédits Scrape Creators ──────────
    @r.get(P + "/api/hub")
    async def hub(req):
        maintenant_ = dt.datetime.now(dt.timezone.utc)
        t0 = maintenant_.timestamp()
        aujourdhui = maintenant_.astimezone(sante.PARIS).date()
        debut = dt.datetime.combine(aujourdhui, dt.time(0, 0), tzinfo=sante.PARIS).astimezone(dt.timezone.utc)
        fin = dt.datetime.combine(aujourdhui + dt.timedelta(days=1), dt.time(0, 0), tzinfo=sante.PARIS).astimezone(dt.timezone.utc)
        z = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        projet = req.query.get("projet") or sante.projet_principal(stock)   # le projet principal ou un autre projet (sélecteur du hub, 26/10/2026)
        miens = {c["id"] for c in stock.comptes() if sante.du_projet(stock, c, projet)}
        pubs = [p for p in stock.publications_du_jour(z(debut)) if p["compte_id"] in miens]
        alertes = [a for a in stock.alertes_recentes(z(maintenant_ - dt.timedelta(hours=48)))
                   if not a["cle"].startswith("compte:") or not a["cle"].split(":")[1].isdigit() or int(a["cle"].split(":")[1]) in miens]
        chauffes = {ch["compte_id"]: ch for ch in stock.chauffes(("en_cours",))}
        tels = {t.udid: t for t in parc.telephones.values()}
        pages = {}
        for c in stock.comptes():
            if not c["actif"] or c["id"] not in miens:
                continue
            rel = stock.releves(c["id"], (aujourdhui - dt.timedelta(days=sante.CHUTE_JOURS)).isoformat())
            dernier = rel[-1] if rel else None
            posts = dernier["posts"] if dernier else []
            ref = dt.datetime.fromisoformat(dernier["releve_le"].replace("Z", "+00:00")).timestamp() if dernier else t0
            soucis = sante.diagnostic(posts, ref, rel) if posts else []
            miennes = [a for a in alertes if a["cle"] == f"compte:{c['id']}" and a["jour"] == aujourdhui.isoformat()
                       and a["type"] not in sante.DIAGNOSTICS]        # ceux-là sont recalculés juste au-dessus, règle du jour
            raisons = [f"{titre} : {details}" for _, _, titre, details in soucis]
            raisons += [a["message"] for a in miennes if a["type"] not in {x for x, _, _, _ in soucis}]
            niveaux = [n for _, n, _, _ in soucis] + [a["niveau"] for a in miennes]
            etat = "rouge" if "rouge" in niveaux else "orange" if niveaux else "ok" if posts or (dernier and not dernier["erreur"]) else "inconnu"

            def vues(x, de=0, a=24):
                r_ = dt.datetime.fromisoformat(x["releve_le"].replace("Z", "+00:00")).timestamp()
                return sum(p["vues"] for p in x["posts"] if de * 3600 <= r_ - p["ts"] < a * 3600)
            semaine = [p["vues"] for p in posts if 86400 < ref - p["ts"] < 7 * 86400]
            veille = next((x for x in reversed(rel[:-1]) if x["abonnes"] is not None), None)
            jour_c = [p for p in pubs if p["compte_id"] == c["id"]]
            prevues = stock.prevues(c["id"])
            derniere = (stock.dernieres_publications(c["id"], 1) or [None])[0]
            t, ch = tels.get(c["udid"]), chauffes.get(c["id"])
            pages.setdefault(c["groupe"] or "Sans page", []).append({
                "id": c["id"], "plateforme": c["plateforme"], "identifiant": c["identifiant"], "etat": etat, "raisons": raisons,
                "vues_24h": vues(dernier) if dernier and not (dernier["erreur"] and not posts) else None,
                "vues_7j": vues(dernier, 0, 24 * 7) if posts else None,
                "mediane_7j": int(statistics.median(semaine)) if semaine else None,
                "posts_7j": sum(1 for p in posts if ref - p["ts"] < 7 * 86400),
                "abonnes": dernier["abonnes"] if dernier else None,
                "abonnes_delta": dernier["abonnes"] - veille["abonnes"] if dernier and veille and dernier["abonnes"] is not None else None,
                "releve_le": dernier["releve_le"] if dernier else None, "erreur_releve": (dernier or {}).get("erreur") or None,
                "serie": [{"jour": x["jour"], "vues_24h": vues(x)} for x in rel if x["posts"]][-8:],
                "jour": {"ok": sum(p["etat"] == "publie" for p in jour_c), "echec": sum(p["etat"] == "echec" for p in jour_c),
                         "prevues": sum(1 for p in prevues if p["quand"] and p["quand"] < z(fin))},
                "prochaine": min((p["quand"] for p in prevues if p["quand"]), default=None),
                "derniere": {"quand": derniere["fin"] or derniere["debut"], "etat": derniere["etat"], "lien": derniere["lien"]} if derniere else None,
                "telephone": {"nom": t.nom, "pret": t.pret} if t else None,
                "warmup": {"jour": max(1, min(chauffe.rang_du_jour(ch, aujourdhui) + 1, ch["jours"])), "jours": ch["jours"],
                           "bloque": bool(ch["bloque"])} if ch else None})
        ordre = {"rouge": 0, "orange": 1, "inconnu": 2, "ok": 3}
        pages = [{"nom": nom, "etat": min((x["etat"] for x in l), key=lambda e: ordre[e]),
                  "comptes": sorted(l, key=lambda x: (x["plateforme"] != "tiktok", x["identifiant"].lower()))} for nom, l in pages.items()]
        pages.sort(key=lambda pg: (ordre[pg["etat"]], pg["nom"].lower()))
        credits = stock.reglage("scrape_credits")
        return web.json_response({
            "maintenant": maintenant(), "aujourdhui": aujourdhui.isoformat(), "projet": projet, "pages": pages,
            "jour": {"ok": sum(p["etat"] == "publie" for p in pubs), "echec": sum(p["etat"] == "echec" for p in pubs),
                     "prevues": sum(x["jour"]["prevues"] for pg in pages for x in pg["comptes"]),
                     "vues_24h": sum(x["vues_24h"] or 0 for pg in pages for x in pg["comptes"])},
            "telephones": [{"nom": t.nom, "branche": t.branche, "pret": t.pret, "occupe": t.occupe, "wifi": bool(t.ip),
                            "expire": t.expire.isoformat() if t.expire else None, "batterie": t.batterie} for t in parc.telephones.values()],
            "alertes": [{k: a[k] for k in ("cle", "type", "niveau", "message", "cree_le")} for a in alertes[:60]],
            "scrape": {"cle": bool(liens.cle()), "credits": int(credits) if (credits or "").isdigit() else None,
                       "releves": [{"heure": f"{h} h {m:02d}" if m else f"{h} h", "fait": stock.reglage(f"sante_releve_{nom}") == aujourdhui.isoformat()}
                                   for h, m, nom in sante.RELEVES]},
            "discord": sorted(publieur.discord.urls)})

    @r.post(P + "/api/sante/relever")
    async def sante_relever(req):
        """Le relevé tout de suite (bouton du hub) : vues, abonnés, liens manquants, alertes ; puis les crédits."""
        bilan = await sante.relever(publieur, "à la main")
        if not bilan["sans_cle"]:
            bilan["credits"] = await sante.credits(publieur)
        return web.json_response(bilan)

    @r.post(P + "/api/sante/rapport")
    async def sante_rapport(req):
        if not publieur.discord.actif("RAPPORT"):
            return erreur(409, "le salon 📊 rapport-du-jour n'est pas branché (secrets\\discord.env)")
        sante.rapport(publieur)
        return web.json_response({"ok": True})

    @r.post(P + "/api/sante/agent")
    async def sante_agent(req):
        """Le compte rendu de l'agent réparateur (tâche planifiée du Mac, toutes les heures ; l'utilisateur, 19/10/2026 : « quand
        y'a des alertes faut un agent pour les réparer ») dans le salon 🩺 santé-pages : {titre, texte, niveau : « vert »
        (réparé), « orange » (en cours, à surveiller), « rouge » (besoin de l'utilisateur)}. Le webhook reste ici (jamais montré)."""
        d = await req.json()
        titre, texte = str(d.get("titre") or "").strip()[:250], str(d.get("texte") or "").strip()[:3900]
        if not titre:
            return erreur(400, "titre attendu")
        if not publieur.discord.actif("SANTE"):
            return erreur(409, "le salon 🩺 santé-pages n'est pas branché (secrets\\discord.env)")
        couleur = {"vert": salons.VERT, "orange": salons.ORANGE, "rouge": salons.ROUGE}.get(str(d.get("niveau") or "vert"), salons.VERT)
        mid = await publieur.discord.poster("SANTE", embeds=[{"color": couleur, "title": f"🛠️ {titre}", "description": texte}])
        return web.json_response({"ok": bool(mid), "id": mid})

    @r.post(P + "/api/sante/test-discord")
    async def sante_test_discord(req):
        """Un message dans chaque salon du service, pour voir que tout est branché."""
        if not publieur.discord.urls:
            return erreur(409, "aucun salon Discord branché (secrets\\discord.env)")
        envoyes = {}
        for salon in sorted(publieur.discord.urls):
            envoyes[salon] = bool(await publieur.discord.poster(salon, "🧪 Test du service : ce salon est bien branché."))
        return web.json_response(envoyes)

    @r.get(P + "/api/programmation")
    async def programmation_get(req):
        return web.json_response({"auto": stock.reglage("programmation_auto", "1") == "1",
                                  "legendes_instagram": programmation.legendes_instagram(stock),
                                  "legendes_tiktok": programmation.legendes(stock, "tiktok"),
                                  "objectifs": {p: programmation.reglage_entier(stock, f"objectif:{p}", 0) for p in stock.projets_des_comptes()},
                                  "dose": programmation.reglage_entier(stock, "dose", programmation.DOSE),
                                  "facebook_instagram": {p: stock.reglage(f"facebook_instagram:{p}", "0") == "1" for p in stock.projets_des_comptes()},
                                  "creneaux": [f"{h:02d}:{m:02d}" for h, m in programmation.creneaux(stock)],
                                  "ecart_min": programmation.ecart_groupes(stock, max([2] + [len({programmation.nom_groupe(c) for c in stock.comptes_du_projet(p)})
                                                                                               for p in stock.projets_des_comptes()])),
                                  "wifi_obligatoire": stock.reglage("wifi_obligatoire", "1") == "1",
                                  "profondeur": programmation.profondeur(stock)})

    @r.post(P + "/api/programmation")
    async def programmation_post(req):
        """Les vidéos des dossiers de groupe partent-elles toutes seules, et à quelles heures (« 09:00,12:00,… », heure de Paris)."""
        d = await req.json()
        if "auto" in d:
            stock.poser_reglage("programmation_auto", "1" if d["auto"] else "0")
        if "wifi_obligatoire" in d:
            stock.poser_reglage("wifi_obligatoire", "1" if d["wifi_obligatoire"] else "0")
        if "profondeur" in d:                                 # la file d'une page, par compte (15 : 3 jours à 5 par jour)
            try:
                stock.poser_reglage("profondeur", max(1, int(d["profondeur"])))
            except (TypeError, ValueError):
                return erreur(400, "profondeur : un nombre de publications par compte")
        for pf in programmation.LEGENDES:                     # legendes_instagram, legendes_tiktok : {projet: légende} ; vide : la description du centre
            if isinstance(d.get(f"legendes_{pf}"), dict):
                for projet, texte in d[f"legendes_{pf}"].items():
                    texte = str(texte or "").strip()[:2200]
                    stock.poser_reglage(f"legende_{pf}:{projet}", texte)
                    if texte:
                        n = stock.legendes_en_file(projet, pf, texte)
                        log.info("légende %s de %s : « %s » (%s publication(s) en file mise(s) à jour)", pf, projet, texte, n)
        if isinstance(d.get("objectifs"), dict):              # {projet: publications par jour} ; 0 : la dose normale seule
            for projet, n in d["objectifs"].items():
                try:
                    stock.poser_reglage(f"objectif:{projet}", max(0, int(n or 0)))
                except (TypeError, ValueError):
                    return erreur(400, "objectifs : un nombre de publications par jour")
        for cle in ("dose", "ecart_groupes"):                 # la dose normale d'une page ; l'écart fixe entre groupes (0 : réparti)
            if cle in d:
                try:
                    stock.poser_reglage(cle, max(0, int(d[cle] or 0)))
                except (TypeError, ValueError):
                    return erreur(400, f"{cle} : un nombre")
        if isinstance(d.get("tiktok_confirmation_musique"), dict):   # {projet: bool} : accepter la confirmation de musique de TikTok
            for projet, oui in d["tiktok_confirmation_musique"].items():
                stock.poser_reglage(f"tiktok_confirmation_musique:{projet}", "1" if oui else "0")
        if isinstance(d.get("facebook_instagram"), dict):     # {projet: bool} : « Partager aussi sur Facebook » coché
            for projet, oui in d["facebook_instagram"].items():
                stock.poser_reglage(f"facebook_instagram:{projet}", "1" if oui else "0")
        if "creneaux" in d:
            brut = ",".join(d["creneaux"]) if isinstance(d["creneaux"], list) else str(d["creneaux"])
            stock.poser_reglage("creneaux", brut)
            if not programmation.creneaux(stock):
                stock.poser_reglage("creneaux", programmation.CRENEAUX)
                return erreur(400, "créneaux illisibles : « 09:00,12:00,… »")
        log.info("programmation : %s, créneaux %s", "auto" if stock.reglage("programmation_auto", "1") == "1" else "coupée",
                 stock.reglage("creneaux", programmation.CRENEAUX))
        return await programmation_get(req)

    @r.post(P + "/api/pause")
    async def pause(req):
        d = await req.json()
        stock.poser_reglage("pause", "1" if d.get("pause") else "0")
        log.info("file des publications %s", "en pause" if d.get("pause") else "relancée")
        return web.json_response({"pause": publieur.pause})

    # ── un téléphone : l'écran, les gestes ─────────────────────────────────────────────────────────────────
    @r.get(P + "/api/t/{udid}/flux")
    async def flux(req):
        """L'écran en direct : le flux MJPEG de WebDriverAgent (port 9100 de l'iPhone, relayé par `ios forward`),
        recompressé ici. WebDriverAgent réencode toujours ses images réduites à 90 % de qualité au moins (227 Ko
        l'image, 2,6 Mo/s mesurés le 01/10/2026 sur l'iPhone 12) : on les ramène à ?q= (50 par défaut), on ne garde
        que la plus récente et on en envoie ?fps= par seconde au plus (10). Un navigateur lent saute des images au
        lieu de prendre du retard."""
        t = telephone(req)
        if not t.pret:
            return erreur(409, "écran pas encore disponible")
        qualite = min(max(int(req.query.get("q", 50)), 20), 90)
        fps = min(max(float(req.query.get("fps", 10)), 1), 15)
        largeur = min(max(int(req.query.get("l", 0)), 0), 1200)        # 0 : la taille envoyée par l'agent
        derniere = {"jpg": None, "n": 0}
        fini = asyncio.Event()

        async def lire():
            try:
                async with http.get(f"http://127.0.0.1:{t.port_flux}/",
                                    timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=30)) as amont:
                    tampon = b""
                    async for bloc in amont.content.iter_any():
                        tampon += bloc
                        while True:                  # « --BoundaryString … Content-Length: N\r\n\r\n » + N octets
                            fin_entete = tampon.find(b"\r\n\r\n")
                            if fin_entete < 0:
                                break
                            entete = tampon[:fin_entete].lower()
                            i = entete.find(b"content-length:")
                            if i < 0:
                                tampon = tampon[fin_entete + 4:]
                                continue
                            n = int(entete[i + 15:].split(b"\r\n")[0].strip())
                            if len(tampon) < fin_entete + 4 + n:
                                break
                            derniere["jpg"] = tampon[fin_entete + 4:fin_entete + 4 + n]
                            derniere["n"] += 1
                            tampon = tampon[fin_entete + 4 + n:].lstrip(b"\r\n")
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionResetError, ValueError):
                pass
            finally:
                fini.set()

        lecteur = asyncio.create_task(lire())
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "multipart/x-mixed-replace; boundary=image"
        resp.headers["Cache-Control"] = "no-cache, no-store"
        resp.headers["X-Accel-Buffering"] = "no"
        await resp.prepare(req)
        vue = 0
        try:
            while not fini.is_set():
                if derniere["n"] != vue and derniere["jpg"]:
                    vue = derniere["n"]
                    jpg = await asyncio.to_thread(recompresser, derniere["jpg"], qualite, largeur)
                    await resp.write(b"--image\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                await asyncio.sleep(1 / fps)
        except (ConnectionResetError, RuntimeError):
            pass
        finally:
            lecteur.cancel()
        return resp

    @r.get(P + "/api/t/{udid}/capture")
    async def capture(req):
        t = telephone(req)
        if t.pret:
            png = await t.agent.capture()
        else:                                   # sans l'agent : go-ios, plus lent
            f = lieux.DONNEES / f"capture-{t.rang}.png"
            await goios.capture(t.udid, f)
            png = f.read_bytes()
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-cache"})

    @r.post(P + "/api/t/{udid}/geste")
    async def geste(req):
        t = pour_la_main(req)
        d, a = await req.json(), t.agent
        g = d.get("type")
        if g == "toucher":
            await a.toucher(float(d["x"]), float(d["y"]))
        elif g == "glisser":
            await a.glisser(float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"]),
                            min(max(float(d.get("duree", 0.35)), 0.05), 3.0))
        elif g == "appui_long":
            await a.appui_long(float(d["x"]), float(d["y"]), min(max(float(d.get("duree", 1.0)), 0.3), 5.0))
        elif g == "ecrire":
            await a.ecrire(str(d["texte"])[:5000])
        elif g == "coller":                     # met un texte dans le presse-papiers de l'iPhone
            texte = str(d["texte"])[:5000]
            try:
                await goios.presse_papiers_ecrire(t.udid, texte)
            except goios.ErreurIos:
                await a.presse_papiers(texte)
        elif g == "bouton" and d.get("nom") in BOUTONS:
            await a.bouton(d["nom"])
        elif g == "accueil":
            await a.accueil()
        elif g == "deverrouiller":
            await a.deverrouiller()
        elif g in ("lancer", "fermer") and isinstance(d.get("bundle"), str):
            await (a.lancer if g == "lancer" else a.fermer)(d["bundle"])
        else:
            return erreur(400, "geste inconnu")
        return web.json_response({"ok": True})

    @r.get(P + "/api/t/{udid}/arbre")
    async def arbre(req):
        """Les éléments de l'écran (bouton, texte, champ…) avec leur nom et leur place : l'inspecteur de l'interface,
        pour écrire et recaler les recettes."""
        t = telephone(req)
        if not t.pret:
            return erreur(409, "le téléphone n'est pas prêt")
        niveaux = None
        if not t.occupe:                 # une recette en cours a déjà posé la profondeur de son app
            try:
                niveaux = PROFONDEURS.get(((await t.agent.app_active()) or {}).get("bundleId"))
            except ErreurAgent:
                pass
        if niveaux:
            await t.agent.profondeur(niveaux)
        try:
            racine_ = await t.agent.arbre()
        finally:
            if niveaux:
                await t.agent.profondeur(PROFONDEUR)
        out = []

        def parcourir(n, profondeur=0):
            rect = n.get("rect") or {}
            nom = n.get("label") or n.get("name") or n.get("value")
            if rect.get("width") and rect.get("height") and (nom or n.get("type") in ("Button", "TextField", "TextView", "Cell", "Switch")):
                out.append({"type": n.get("type"), "label": n.get("label"), "name": n.get("name"), "value": n.get("value"),
                            "rect": rect, "actif": n.get("isEnabled", True), "profondeur": profondeur})
            for e in n.get("children") or []:
                parcourir(e, profondeur + 1)

        parcourir(racine_ or {})
        return web.json_response({"taille": t.taille, "elements": out})

    @r.post(P + "/api/t/{udid}/relancer")
    async def relancer(req):
        t = telephone(req)
        await t.relancer_agent()
        return web.json_response({"ok": True})

    @r.post(P + "/api/t/{udid}/essai-photos")
    async def essai_photos(req):
        """Range une vidéo du dossier dans Photos, sans rien publier : prouve le câble, VLC et le Raccourci."""
        t = pour_la_main(req)
        d = await req.json()
        cle = str(d["video"])
        async with t.gestes:
            t.occupe = "essai d'import dans Photos"
            try:
                dest = await videos.copie_locale(http, cle, lieux.DONNEES / "videos")
                await photos.importer(t, dest, f"essai-{int(time.time())}.mp4")
            except (photos.ErreurImport, RuntimeError) as e:
                return erreur(502, str(e))
            finally:
                t.occupe = None
        return web.json_response({"ok": True})

    # ── comptes ─────────────────────────────────────────────────────────────────────────────────────────
    @r.get(P + "/api/comptes")
    async def comptes(req):
        return web.json_response(stock.comptes())

    @r.post(P + "/api/comptes")
    async def ajouter_compte(req):
        d = await req.json()
        try:
            return web.json_response(stock.ajouter_compte(d.get("plateforme"), str(d.get("identifiant", "")),
                                                          d.get("udid"), str(d.get("client", "")), str(d.get("note", "")),
                                                          str(d.get("projet") or videos.PROJET), str(d.get("groupe", ""))))
        except ValueError as e:
            return erreur(400, str(e))
        except Exception as e:
            if "UNIQUE" in str(e):
                return erreur(409, "ce compte existe déjà")
            raise

    @r.post(P + "/api/comptes/{cid:\\d+}")
    async def modifier_compte(req):
        d = await req.json()
        champs = {k: d[k] for k in ("udid", "client", "note", "actif", "projet", "groupe") if k in d}
        if "actif" in champs:
            champs["actif"] = 1 if champs["actif"] else 0
        return web.json_response(stock.modifier_compte(int(req.match_info["cid"]), **champs))

    # ── vidéos publiables et publications ────────────────────────────────────────────────────────────────
    async def videos_publiables():
        t, l = cache["videos"]
        if time.time() - t > 5:
            l = await videos.videos_publiables(http)
            cache["videos"] = (time.time(), l)
        return l

    @r.get(P + "/api/videos")
    async def liste_videos(req):
        return web.json_response(await videos_publiables())

    @r.get(P + "/api/projets")
    async def projets(req):
        return web.json_response(await videos.projets(http))

    # ── envoyer une vidéo à plusieurs comptes d'un coup : les comptes groupés, chaque groupe sur tous ses réseaux,
    # étalé (un groupe toutes les N minutes, ses réseaux ensemble)
    @r.get(P + "/api/destinations")
    async def destinations(req):
        cle = req.query.get("video", "")
        if not cle.startswith(videos.PREFIXE):
            return erreur(400, "vidéo du dossier attendue (dossier:<chemin>)")
        slug, _ = videos.decouper(cle)
        tels = {t.udid: t for t in parc.telephones.values()}
        pubs = stock.publications_de_video(cle)
        derniere = {}
        for x in pubs:
            derniere.setdefault(x["compte_id"], x)
        groupes = {}
        for c in stock.comptes_du_projet(slug):
            t, d = tels.get(c["udid"]), derniere.get(c["id"])
            groupes.setdefault(c["groupe"] or "@" + c["identifiant"], []).append({
                "id": c["id"], "plateforme": c["plateforme"], "identifiant": c["identifiant"],
                "telephone": t.nom if t else None, "pret": bool(t and t.pret), "recette": PRETES.get(c["plateforme"], False),
                "deja": {"etat": d["etat"], "lien": d["lien"]} if d and d["etat"] in ("en_attente", "en_cours", "publie") else None})
        # « page » : une page réglée (une niche, ou un jour 1 : les comptes 1 et 2, généralistes, depuis le 16/10/2026),
        # que le centre remplit lui-même (3 jours d'avance, 3 neuves pour 1 réutilisée) : rien ne s'y remonte à la validation
        reglees = {p["groupe"]: p for p in stock.pages(slug)}
        return web.json_response({"projet": slug, "groupes": [{"nom": k, "comptes": v, "niche": (reglees.get(k) or {}).get("niche") or None,
                                                              "page": bool(reglees.get(k) and (reglees[k]["niche"] or reglees[k]["debut"]))}
                                                             for k, v in groupes.items()],
                                  "publications": pubs[:40], "ecart_min": int(stock.reglage("ecart_envoi_min", "30")),
                                  "repetition": stock.reglage("repetition_defaut", "1") == "1"})

    # ── les pages de niche : la niche d'un groupe de comptes et sa montée en charge ──────────────
    @r.get(P + "/api/vues")
    async def vues_pages(req):
        """Les vues des pages jour par jour et semaine par semaine (la section « Vues des pages » de l'onglet
        Calendrier) : les vues gagnées d'un relevé à l'autre (sante.vues_par_jour) et les publications en ligne du jour."""
        aujourdhui = dt.datetime.now(sante.PARIS).date()
        try:
            n = min(max(int(req.query.get("jours") or 56), 7), 400)
        except ValueError:
            n = 56
        depuis = aujourdhui - dt.timedelta(days=n - 1)
        projet = req.query.get("projet") or sante.projet_principal(stock)
        miens = {c["id"] for c in stock.comptes() if sante.du_projet(stock, c, projet)}
        vues = sante.vues_par_jour(stock, depuis.isoformat(), projet)
        debut = dt.datetime.combine(depuis, dt.time(0, 0), tzinfo=sante.PARIS).astimezone(dt.timezone.utc)
        publiees = {}
        for p in stock.publications_du_jour(debut.strftime("%Y-%m-%dT%H:%M:%SZ")):
            if p["etat"] == "publie" and p["compte_id"] in miens:
                j = sante.jour_paris(dt.datetime.fromisoformat((p["fin"] or p["debut"] or p["quand"] or p["cree_le"]).replace("Z", "+00:00")))
                publiees[j] = publiees.get(j, 0) + 1
        jours = []
        for i in range(n):
            j = (depuis + dt.timedelta(days=i)).isoformat()
            v = vues.get(j)
            if not v and not publiees.get(j) and not jours:     # rien avant le premier relevé ni la première publication
                continue
            jours.append({"jour": j, "vues": v["tiktok"] + v["instagram"] if v else None, "tiktok": v["tiktok"] if v else None,
                          "instagram": v["instagram"] if v else None, "comptes": v["comptes"] if v else 0, "publiees": publiees.get(j, 0)})
        semaines = {}
        for x in jours:
            d = dt.date.fromisoformat(x["jour"])
            s = semaines.setdefault((d - dt.timedelta(days=d.weekday())).isoformat(),
                                    {"vues": 0, "tiktok": 0, "instagram": 0, "publiees": 0, "jours": 0})
            if x["vues"] is not None:
                s["jours"] += 1
                for k in ("vues", "tiktok", "instagram"):
                    s[k] += x[k]
            s["publiees"] += x["publiees"]
        return web.json_response({
            "aujourdhui": aujourdhui.isoformat(), "soir_fait": stock.reglage("sante_releve_soir") == aujourdhui.isoformat(),
            "jours": jours, "semaines": [{"lundi": k, **v} for k, v in sorted(semaines.items())]})

    @r.get(P + "/api/pages")
    async def pages(req):
        """Chaque groupe de comptes d'un projet (une page : son TikTok et son Insta), sa niche, son jour 1, sa dose du jour
        et ce qu'il a en file ."""
        slug = req.query.get("projet", "")
        aujourdhui = dt.datetime.now(sante.PARIS).date()
        reglees = {p["groupe"]: p for p in stock.pages(slug)}
        groupes = {}
        for c in stock.comptes_du_projet(slug):
            groupes.setdefault(programmation.nom_groupe(c), []).append(c)
        out = []
        prof = programmation.profondeur(stock)
        bloques = stock.comptes_bloques()
        for nom, comptes in sorted(groupes.items()):
            page = reglees.get(nom)
            ids = [c["id"] for c in comptes]
            pubs = stock.publications_des_comptes(ids)
            quand = sorted({p["quand"] for p in pubs if p["quand"] and p["etat"] in programmation.OCCUPE})
            jours = [programmation.a_paris(q).date() for q in quand]
            # ce qui attend d'être publié, compte par compte (27/10/2026) : la page a l'avance de son compte le moins servi
            # (un compte en warm-up « publications bloquées » ne compte pas)
            file = {i: 0 for i in ids if i not in bloques}
            for x in stock.file_des_comptes(list(file)):
                file[x["compte_id"]] += 1
            out.append({"groupe": nom, "niche": (page or {}).get("niche") or "", "debut": (page or {}).get("debut"),
                        "jour": (aujourdhui - dt.date.fromisoformat(page["debut"])).days + 1 if page and page.get("debut") else None,
                        "quotas": [programmation.quota(stock, page, aujourdhui + dt.timedelta(days=i)) for i in range(4)],
                        "aujourdhui": sum(1 for j in jours if j == aujourdhui),
                        "a_venir": min(file.values()) if file else 0,
                        "file": {str(i): n for i, n in file.items()}, "profondeur": prof,
                        "telephones": sorted({c["udid"] for c in comptes if c["udid"]}),
                        # au-delà de la profondeur
                        "en_trop": [{**e, "video": e["video"].split("/", 1)[1]} for e in programmation.en_trop(stock, ids, prof)
                                    if e["video"].startswith(videos.PREFIXE)] if page and (page["niche"] or page["debut"]) else [],
                        # les vidéos du projet qui ont déjà une publication sur la page, quel qu'en soit l'état : le centre
                        # compte à part celles qui attendent encore d'être programmées (son avance)
                        "videos": sorted({videos.decouper(p["video"])[1] for p in pubs if p["video"].startswith(videos.PREFIXE)}),
                        "comptes": [{"id": c["id"], "plateforme": c["plateforme"], "identifiant": c["identifiant"]} for c in comptes]})
        return web.json_response({"projet": slug, "creneaux": len(programmation.creneaux(stock)), "pages": out})

    @r.get(P + "/api/performances")
    async def performances(req):
        """Les vues de chaque vidéo publiée du projet (le meilleur de ses publications, au dernier relevé qui la voit) :
        le centre choisit d'après elles quoi remonter sur les pages de niche."""
        slug = req.query.get("projet", "")
        vues, mediane, comptes = {}, {}, {c["id"]: c for c in stock.comptes_du_projet(slug)}
        for c in comptes.values():
            mois = {}                     # ses posts du mois (dernières vues vues) : la médiane du compte
            for r_ in stock.releves(c["id"], "2000-01-01"):
                for p in r_["posts"]:
                    if p.get("lien"):
                        vues[p["lien"].rstrip("/")] = p["vues"]
                    if time.time() - p["ts"] < 30 * 86400:
                        mois[p["id"]] = p["vues"]
            mediane[c["id"]] = statistics.median(mois.values()) if mois else None
        out = {}
        for p in stock.publications(5000):
            if p["etat"] != "publie" or p["repetition"] or not p["lien"] or not p["video"].startswith(videos.PREFIXE):
                continue
            v = vues.get(p["lien"].rstrip("/"))
            if v is None:
                continue
            x = out.setdefault(p["video"].split("/", 1)[1], {"vues": 0, "publications": 0, "meilleure": None})
            if x["meilleure"] is None or v > x["vues"]:   # sa meilleure publication : de quoi repérer une pépite (centre, 31/10/2026)
                c = comptes.get(p["compte_id"])
                x["meilleure"] = {"vues": v, "compte_id": p["compte_id"], "plateforme": c and c["plateforme"],
                                  "groupe": c and programmation.nom_groupe(c), "publie_le": p["fin"], "mediane": mediane.get(p["compte_id"])}
            x["vues"] = max(x["vues"], v)
            x["publications"] += 1
        return web.json_response({"projet": slug, "videos": out})

    @r.get(P + "/api/performances/publications")
    async def performances_publications(req):
        """Chaque publication du projet avec ses vues au dernier relevé qui la voit, son compte et son âge à ce relevé (la
        boucle des performances, 22/10/2026 : le centre les écrit dans la base du service, pour
        que les vues des comptes clips fassent voter leurs clips et apprendre ce qui marche : style, musique, accroche…).
        Les comptes retirés comptent aussi : leurs vues restent vraies. Instagram ne montre que ses 12 derniers posts : sur
        une page qui publie beaucoup, le dernier relevé d'un post peut tomber avant 48 h (« age_h » le dit)."""
        slug = req.query.get("projet", "")
        cle = lambda u: (re.search(r"/video/(\d+)|/(?:reel|reels|p)/([^/?#]+)", u or "") or [None, None, None])  # noqa: E731
        vus, comptes = {}, {}
        for c in stock.comptes():
            if c["projet"] != slug:
                continue
            comptes[c["id"]] = c
            for r_ in stock.releves(c["id"], "2000-01-01"):
                for p in r_["posts"]:
                    m = cle(p.get("lien"))
                    if m[1] or m[2]:
                        vus[(c["id"], m[1] or m[2])] = (p["vues"], r_["releve_le"], p.get("ts") or 0)
        out = []
        for p in stock.publications(5000):
            if p["etat"] != "publie" or p["repetition"] or not p["lien"] or not p["video"].startswith(videos.PREFIXE):
                continue
            m = cle(p["lien"])
            v = vus.get((p["compte_id"], m[1] or m[2])) if (m[1] or m[2]) else None
            ts, vues, vu_le, age = None, None, None, None
            if v:
                vues, vu_le, ts = v
                age = round((dt.datetime.fromisoformat(vu_le.replace("Z", "+00:00")).timestamp() - ts) / 3600, 1) if ts else None
            out.append({"publication": p["id"], "video": p["video"].split("/", 1)[1], "lien": p["lien"], "plateforme": p["plateforme"],
                        "compte": p["identifiant"], "groupe": (comptes.get(p["compte_id"]) or {}).get("groupe") or None,
                        "publie_le": p["fin"] or p["debut"] or p["quand"],
                        "poste_le": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None,
                        "vues": vues, "vu_le": vu_le, "age_h": age})
        return web.json_response({"projet": slug, "publications": out})

    @r.post(P + "/api/pages")
    async def poser_page(req):
        d = await req.json()
        projet, groupe = str(d.get("projet") or "").strip(), str(d.get("groupe") or "").strip()
        if not projet or not groupe:
            return erreur(400, "projet et groupe attendus")
        debut = str(d.get("debut") or "").strip() or None
        if debut:
            try:
                dt.date.fromisoformat(debut)
            except ValueError:
                return erreur(400, "jour 1 attendu au format AAAA-MM-JJ")
        p = stock.poser_page(projet, groupe, str(d.get("niche") or "").strip()[:500], debut)
        log.info("page %s / %s : niche « %s », jour 1 %s", projet, groupe, p["niche"], p["debut"] or "—")
        return web.json_response(p)

    @r.post(P + "/api/envois")
    async def creer_envoi(req):
        d = await req.json()
        cle = str(d.get("video", ""))
        video = next((v for v in await videos_publiables() if v["cle"] == cle), None)
        if not video:
            return erreur(400, "cette vidéo n'est pas dans le dossier des vidéos : elle ne peut pas partir")
        slug, _ = videos.decouper(cle)
        comptes = [stock.compte(int(i)) for i in d.get("comptes") or []]
        if not comptes:
            return erreur(400, "choisis au moins un compte")
        for c in comptes:
            if not c or not c["actif"] or c["projet"] != slug:
                return erreur(400, "un des comptes n'est pas un compte actif de ce projet")
            if not c["udid"]:
                return erreur(400, f"@{c['identifiant']} n'est rattaché à aucun téléphone")
            if not PRETES.get(c["plateforme"]):
                return erreur(400, f"la recette {c['plateforme']} n'est pas encore écrite : décoche @{c['identifiant']}")
        bloque = bloque_par_chauffe(comptes, d.get("repetition"))
        if bloque:
            return bloque
        ecart = min(max(int(d.get("ecart_min", 30)), 0), 24 * 60)
        t0 = dt.datetime.fromisoformat((iso_utc(d.get("debut")) or maintenant()).replace("Z", "+00:00"))
        legende = str(d["legende"] if d.get("legende") is not None else video.get("description") or "")[:2200]
        ordre = []
        for c in comptes:
            g = c["groupe"] or "@" + c["identifiant"]
            if g not in ordre:
                ordre.append(g)
        envoi = stock.creer_envoi(cle, video["titre"], ecart)
        pubs = [stock.creer_publication(c["id"], cle, video["titre"], programmation.legende_pour(stock, c, legende, video.get("description") or ""),
                                        (t0 + dt.timedelta(minutes=ordre.index(c["groupe"] or "@" + c["identifiant"]) * ecart)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        bool(d.get("repetition")), envoi)
                for c in comptes]
        log.info("envoi %s : « %s » vers %s compte(s), %s groupe(s), un groupe toutes les %s min%s", envoi, video["titre"],
                 len(pubs), len(ordre), ecart, " (répétition)" if d.get("repetition") else "")
        return web.json_response({"envoi": envoi, "publications": pubs})

    # ── le calendrier façon planificateur : les vidéos validées d'un projet pas
    # encore programmées, qu'on glisse sur le créneau libre d'un groupe ─────────────────────────────────────────────
    @r.get(P + "/api/a-programmer")
    async def a_programmer(req):
        slug = req.query.get("projet", "")
        try:
            prets = [v for v in await videos_publiables() if videos.decouper(v["cle"])[0] == slug and not v.get("groupe")]
        except (aiohttp.ClientError, RuntimeError, asyncio.TimeoutError) as e:
            return erreur(502, f"dossier des vidéos illisible : {e}")
        out = []
        for v in prets:
            pubs = [x for x in stock.publications_de_video(v["cle"]) if x["etat"] in ("en_attente", "en_cours", "publie")]
            out.append({**v, "places": len(pubs), "groupes": sorted({x["groupe"] or "@" + x["identifiant"] for x in pubs})})
        out.sort(key=lambda v: (v["places"] > 0, v["titre"]))   # les jamais programmées en tête
        return web.json_response(out)

    @r.post(P + "/api/calendrier/placer")
    async def placer(req):
        """Une vidéo glissée sur un créneau : elle part sur les comptes prêts de ce groupe (TikTok + Insta ensemble), à
        l'heure du créneau tirée à ± 15 min comme la programmation (jamais deux jours pareils), jamais dans le passé.
        Reel d'essai (« creneau_essai », Insta seul) : « pile » = une version de plus sur un créneau déjà pris, à la suite
        de ce qui y part ; « exact » = à l'heure choisie par l'utilisateur (décalée seulement si elle tombe sur le projet principal)."""
        d = await req.json()
        cle, groupe = str(d.get("video", "")), str(d.get("groupe", ""))
        video = next((v for v in await videos_publiables() if v["cle"] == cle), None)
        if not video:
            return erreur(400, "cette vidéo n'est pas dans le dossier des vidéos : elle ne peut pas partir")
        slug, _ = videos.decouper(cle)
        comptes = [c for c in stock.comptes_du_projet(slug) if programmation.nom_groupe(c) == groupe]
        if not comptes:
            return erreur(400, f"aucun compte actif dans le groupe {groupe}")
        if d.get("creneau_essai"):          # un créneau de reel d'essai : l'Instagram du groupe seulement
            comptes = [c for c in comptes if c["plateforme"] == "instagram"]
            d["essai"] = True
        prets = [c for c in comptes if c["udid"] and PRETES.get(c["plateforme"])]
        if not prets:
            return erreur(400, f"{groupe} : aucun compte rattaché à un téléphone avec une recette prête")
        bloque = bloque_par_chauffe(prets, False)
        if bloque:
            return bloque
        try:
            t = dt.datetime.fromisoformat(iso_utc(d.get("quand")).replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            return erreur(400, "quand : une heure ISO avec fuseau")
        # les téléphones partagés avec un autre projet (le projet principal) : on ne prend que les trous de sa grille (partage.py)
        pile = bool(d.get("creneau_essai") and d.get("pile"))
        if pile:
            # une version de plus sur ce créneau : elle
            # part à la suite de ce qui est déjà prévu autour sur ce téléphone, ~5 min par publication
            udids = {c["udid"] for c in prets}
            autour = [p for p in stock.publications_des_comptes([c["id"] for s_ in stock.projets_des_comptes()
                                                                   for c in stock.comptes_du_projet(s_) if c["udid"] in udids])
                      if p["etat"] in programmation.OCCUPE and p["quand"]
                      and -20 * 60 <= (dt.datetime.fromisoformat(p["quand"].replace("Z", "+00:00")) - t).total_seconds() <= 60 * 60]
            t += dt.timedelta(minutes=5 * len(autour))
        voulu = t
        t = partage.ajuster(stock, prets, slug, t, varier=not (d.get("exact") or pile))
        if not t:
            return erreur(409, f"{groupe} : pas de trou à une heure près sur ses téléphones sans gêner les publications "
                               "d'un autre projet : choisis un autre créneau")
        if pile and abs((t - voulu).total_seconds()) > 10 * 60:
            return erreur(409, f"Plus de place pour une version sur ce créneau : elle déborderait sur les publications du projet principal "
                               f"(prochain moment libre : {programmation.a_paris(t.strftime('%Y-%m-%dT%H:%M:%SZ')):%H:%M}). "
                               "Pose-la à une heure précise ou sur un autre créneau")
        quand = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        # la légende : celle que le calendrier envoie (écrite à l'instant, la liste du centre est en cache 1 min), sinon le centre
        legende = (str(d.get("legende") or "").strip() or video.get("description") or "")[:2200]
        envoi = stock.creer_envoi(cle, video["titre"], 0, auto=True)   # « auto » : un créneau manqué est reporté, pas rattrapé en rafale
        # « Reel d'essai » coché dans le calendrier : seulement sur Instagram (TikTok n'a pas d'équivalent)
        essai = lambda c: json.dumps({"essai": True}) if d.get("essai") and c["plateforme"] == "instagram" else ""  # noqa: E731
        pubs = [stock.creer_publication(c["id"], cle, video["titre"], programmation.legende_pour(stock, c, legende), quand, False, envoi,
                                        essai(c))
                for c in prets]
        log.info("calendrier : « %s » placée sur %s (%s compte(s)) le %s", video["titre"], groupe, len(pubs),
                 programmation.a_paris(quand).strftime("%d/%m à %H:%M"))
        return web.json_response({"envoi": envoi, "quand": quand, "publications": pubs,
                                  "ignores": [c["identifiant"] for c in comptes if c not in prets]})

    def bloque_par_chauffe(comptes, repetition):
        """Un envoi vers un compte en warm-up « publications bloquées » est refusé (une répétition passe)."""
        if repetition:
            return None
        bloques = stock.comptes_bloques()
        for c in comptes:
            if c["id"] in bloques:
                fin = dt.datetime.fromisoformat(bloques[c["id"]].replace("Z", "+00:00")).astimezone(chauffe.PARIS)
                return erreur(409, f"@{c['identifiant']} est en warm-up jusqu'au {fin:%d/%m à %H:%M}, publications bloquées : "
                                   "arrête son warm-up ou décoche « Bloquer les publications » (page Warm-up)")
        return None

    @r.get(P + "/api/publications")
    async def publications(req):
        return web.json_response(stock.publications())

    @r.post(P + "/api/publications")
    async def creer_publication(req):
        d = await req.json()
        cle = str(d.get("video", ""))
        video = next((v for v in await videos_publiables() if v["cle"] == cle), None)
        if not video:
            return erreur(400, "cette vidéo n'est pas dans le dossier des vidéos : elle ne peut pas partir")
        compte = stock.compte(int(d["compte_id"]))
        if not compte or not compte["actif"]:
            return erreur(400, "compte inconnu ou désactivé")
        if not compte["udid"]:
            return erreur(400, "ce compte n'est rattaché à aucun téléphone")
        bloque = bloque_par_chauffe([compte], d.get("repetition"))
        if bloque:
            return bloque
        legende = str(d["legende"] if d.get("legende") is not None else video.get("description") or "")[:2200]
        p = stock.creer_publication(compte["id"], cle, video["titre"],
                                    programmation.legende_pour(stock, compte, legende, video.get("description") or ""),
                                    iso_utc(d.get("quand")), bool(d.get("repetition")))
        log.info("publication %s mise en file : %s sur @%s%s", p["id"], video["titre"], compte["identifiant"],
                 " (répétition)" if p["repetition"] else "")
        return web.json_response(p)

    @r.get(P + "/api/publications/{pid:\\d+}")
    async def publication(req):
        pid = int(req.match_info["pid"])
        p = stock.publication(pid)
        if not p:
            return erreur(404, "publication inconnue")
        return web.json_response({**p, "etapes": stock.etapes(pid)})

    @r.post(P + "/api/publications/{pid:\\d+}/annuler")
    async def annuler(req):
        pid = int(req.match_info["pid"])
        p = stock.publication(pid)
        if not p or p["etat"] != "en_attente":
            return erreur(409, "seule une publication en attente s'annule")
        stock.maj_publication(pid, etat="annule", fin=maintenant(), supprime_le=maintenant())
        return web.json_response(stock.publication(pid))

    @r.get(P + "/api/corbeille")
    async def corbeille(req):
        projet = req.query.get("projet", "").strip()
        if not projet:
            return erreur(400, "choisis un projet")
        entrees = {}
        for p in stock.corbeille(projet):
            groupe = p["groupe"] or "@" + p["identifiant"]
            cle = (p["envoi_id"], p["video"], groupe, (p["quand"] or "")[:16])
            if cle not in entrees:
                entrees[cle] = {"titre": p["titre"] or p["video"], "groupe": groupe, "quand": p["quand"],
                                "supprime_le": p["supprime_le"], "comptes": []}
            entrees[cle]["comptes"].append({"publication": p["id"], "plateforme": p["plateforme"], "identifiant": p["identifiant"], "deja": p["deja"]})
        return web.json_response({"entrees": list(entrees.values())})

    @r.post(P + "/api/corbeille/restaurer")
    async def restaurer(req):
        d = await req.json()
        ids = sorted({int(i) for i in d.get("ids") or []})
        disponibles = {p["id"]: p for p in stock.corbeille(str(d.get("projet") or ""))}
        if not ids or any(i not in disponibles for i in ids):
            return erreur(409, "ces publications ne sont plus dans la corbeille de ce projet ; actualise la liste")
        pubs = [disponibles[i] for i in ids]
        if any(p["deja"] for p in pubs):
            return erreur(409, "cette vidéo est déjà programmée ou publiée sur un des comptes ; elle ne sera pas remise en double")
        p = pubs[0]
        groupe, dec = programmation.groupe_de(stock, stock.compte(p["compte_id"]))
        if any(x["compte_id"] not in groupe or x["video"] != p["video"] or x["envoi_id"] != p["envoi_id"] for x in pubs):
            return erreur(400, "restaure une seule vidéo d'un même groupe à la fois")
        # Garde les heures d'origine si elles restent à venir et libres. Sinon, un créneau commun libre, jamais « maintenant ».
        anciennes = [x["quand"] for x in pubs]
        limite = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        autres = [x for x in stock.publications_des_comptes(groupe) if x["id"] not in ids and x["etat"] in ("en_attente", "en_cours", "publie")]
        origine = all(t and t > limite for t in anciennes) and not any(
            x["quand"] and abs((programmation.a_paris(x["quand"]) - programmation.a_paris(t)).total_seconds()) < 25 * 60
            for x in autres for t in anciennes if t)
        quand = min(anciennes) if origine else programmation.prochain_creneau(stock, groupe, dec, exclure=set(ids))
        if not quand:
            return erreur(409, "aucun créneau libre ; les publications restent dans la corbeille")
        stock.db.execute("begin immediate")
        try:
            for x in pubs:
                stock.maj_publication(x["id"], etat="en_attente", quand=x["quand"] if origine else quand,
                                     fin=None, erreur="", etape="", supprime_le=None)
                stock.etape(x["id"], "Restaurée depuis la corbeille : " + (x["quand"] if origine else quand))
            stock.db.execute("commit")
        except Exception:
            stock.db.execute("rollback")
            raise
        return web.json_response({"quand": quand, "origine": origine, "ids": ids})

    @r.post(P + "/api/publications/{pid:\\d+}/relancer")
    async def relancer_publication(req):
        """Remet en file une publication ratée, répétée ou annulée (la répétition peut être retirée ici)."""
        pid = int(req.match_info["pid"])
        d = await req.json()
        p = stock.publication(pid)
        if not p or p["etat"] not in ("echec", "repete", "annule"):
            return erreur(409, "seule une publication ratée, répétée ou annulée se relance")
        champs = {"etat": "en_attente", "erreur": "", "etape": "", "fin": None, "quand": None}
        if "repetition" in d:
            champs["repetition"] = 1 if d["repetition"] else 0
        if d.get("creneau"):   # au prochain créneau libre de son compte plutôt que tout de suite (calendrier, 05/10/2026)
            _, decalage = programmation.groupe_de(stock, stock.compte(p["compte_id"]))
            champs["quand"] = programmation.prochain_creneau(stock, [p["compte_id"]], decalage, exclure={pid})
        stock.maj_publication(pid, **champs)
        return web.json_response(stock.publication(pid))

    @r.post(P + "/api/publications/reporter")
    async def reporter(req):
        """Ces publications d'un même groupe (TikTok + Insta d'une entrée du calendrier), en attente ou ratées, ENSEMBLE
        au prochain créneau libre du groupe (calendrier : « Reporter », « Reprogrammer » ; 06/10/2026). Avant, chaque ratée relancée prenait son créneau : TikTok et Insta séparés."""
        d = await req.json()
        pubs = [stock.publication(int(i)) for i in d.get("ids") or []]
        if not pubs or not all(pubs):
            return erreur(400, "publications inconnues")
        if any(p["etat"] not in ("en_attente", "echec", "annule") or p["repetition"] for p in pubs):
            return erreur(409, "seule une vraie publication en attente, ratée ou annulée se reporte")
        du_groupe, _ = programmation.groupe_de(stock, stock.compte(pubs[0]["compte_id"]))
        if any(p["compte_id"] not in du_groupe for p in pubs):
            return erreur(400, "ces publications ne sont pas du même groupe de comptes")
        # la raison, écrite dans l'étape de chaque publication : celle de l'appelant (la réserve d'une page, centre), sinon
        # le bouton du calendrier
        raison = str(d.get("raison") or "").strip()[:80] or ("Depuis le calendrier" if pubs[0]["etat"] == "en_attente"
                                                             else "Ratée, remise en file depuis le calendrier")
        quand = programmation.reporter(stock, pubs, raison)
        if not quand:
            return erreur(409, "aucun créneau libre dans les 90 jours (réglage « créneaux » vide ?)")
        return web.json_response({"quand": quand, "publications": [stock.publication(p["id"]) for p in pubs]})

    @r.post(P + "/api/publications/reserver")
    async def reserver(req):
        """Ces publications en file sortent de la file (annulées, l'étape dit pourquoi) : le centre les a mises dans la
        réserve de leur page, d'où « Reporter » les reprendra (27/10/2026 : 3 jours de file par page,
        pas deux semaines)."""
        d = await req.json()
        pubs = [stock.publication(int(i)) for i in d.get("ids") or []]
        if not pubs or not all(pubs):
            return erreur(400, "publications inconnues")
        if any(p["etat"] != "en_attente" or p["repetition"] for p in pubs):
            return erreur(409, "seule une vraie publication en attente se met en réserve")
        raison = str(d.get("raison") or "").strip()[:120] or "réserve de la page"
        for p in pubs:
            stock.maj_publication(p["id"], etat="annule", fin=maintenant())
            stock.etape(p["id"], f"Mise en réserve : {raison}")
        log.info("mises en réserve (%s) : n° %s", raison, ", ".join(str(p["id"]) for p in pubs))
        return web.json_response({"publications": [stock.publication(p["id"]) for p in pubs]})

    @r.post(P + "/api/pages/donner")
    async def donner(req):
        """Un remontage d'une autre page (sa réserve) part sur cette page, chaque compte à son prochain créneau libre
        (27/10/2026 : le surplus des Comptes 1 et 2 sert les pages qui manquent). Jamais deux fois la même vidéo sur un
        même téléphone : refusé si elle a déjà une publication (autre qu'annulée) sur un compte d'un téléphone de la page."""
        d = await req.json()
        cle, groupe = str(d.get("video", "")), str(d.get("groupe", ""))
        video = next((v for v in await videos_publiables() if v["cle"] == cle), None)
        if not video:
            return erreur(400, "cette vidéo n'est pas dans le dossier des vidéos : elle ne peut pas partir")
        slug, _ = videos.decouper(cle)
        comptes = stock.comptes_du_projet(slug)
        bloques = stock.comptes_bloques()
        prets = [c for c in comptes if programmation.nom_groupe(c) == groupe and c["udid"] and PRETES.get(c["plateforme"])
                 and c["id"] not in bloques]
        if not prets or not programmation.page_reglee(stock, slug, groupe):
            return erreur(400, f"{groupe} : pas une page réglée avec des comptes prêts")
        udids = {c["udid"] for c in prets}
        voisins = {c["id"] for s_ in stock.projets_des_comptes() for c in stock.comptes_du_projet(s_) if c["udid"] in udids}
        if any(x["etat"] != "annule" and x["compte_id"] in voisins for x in stock.publications_de_video(cle)):
            return erreur(409, f"cette vidéo a déjà une publication sur un compte du même téléphone que {groupe}")
        noms = programmation.ordre_groupes(programmation.nom_groupe(c) for c in comptes)
        pubs = programmation.placer(stock, cle, video["titre"], video.get("description"), prets, programmation.decalage(stock, noms, groupe))
        if not pubs:
            return erreur(409, "aucun créneau libre dans les 90 jours")
        raison = str(d.get("raison") or "").strip()[:80] or "Donnée par une autre page"
        for x in pubs:
            stock.etape(x["id"], f"{raison} : prévue le {programmation.a_paris(x['quand']).strftime('%d/%m à %H:%M')}")
        log.info("%s : « %s » donnée à %s, le %s", raison, video["titre"], groupe, programmation.a_paris(pubs[0]["quand"]).strftime("%d/%m à %H:%M"))
        return web.json_response({"quand": min(x["quand"] for x in pubs), "publications": pubs})

    @r.post(P + "/api/publications/{pid:\\d+}/pas-en-ligne")
    async def pas_en_ligne(req):
        """L'inverse : notée publiée, mais rien n'est en ligne (vérifié sur le compte ; vu le 05/10/2026, un envoi
        Instagram figé puis en erreur). Elle passe en échec : elle se reprogramme alors comme les autres."""
        pid = int(req.match_info["pid"])
        p = stock.publication(pid)
        if not p or p["etat"] != "publie" or p["lien"]:
            return erreur(409, "seule une publication notée publiée, sans lien, se marque pas en ligne")
        stock.maj_publication(pid, etat="echec", erreur="pas en ligne (vérifié sur le compte) : à reprogrammer")
        stock.etape(pid, "Marquée pas en ligne à la main")
        return web.json_response(stock.publication(pid))

    @r.post(P + "/api/publications/{pid:\\d+}/en-ligne")
    async def en_ligne(req):
        """Une publication marquée en échec alors que la vidéo est bien en ligne (vérifié sur le compte) : elle passe
        en publiée, avec son lien s'il est donné ({"lien": …}), sinon cherché comme pour les autres (sans toucher au
        téléphone)."""
        pid = int(req.match_info["pid"])
        p = stock.publication(pid)
        if not p or p["etat"] != "echec" or p["repetition"]:
            return erreur(409, "seule une vraie publication en échec se marque en ligne")
        lien = str((await req.json() if req.can_read_body else {}).get("lien") or "").strip()
        if lien and not re.match(r"^https://(www\.)?(instagram\.com/(reel|p)/[\w-]+/?|tiktok\.com/@[\w.]+/video/\d+)", lien):
            return erreur(400, "colle le lien du reel Instagram ou de la vidéo TikTok")
        stock.maj_publication(pid, etat="publie", erreur="")
        stock.etape(pid, "Marquée en ligne à la main (vérifiée sur le compte)")
        if lien:
            stock.maj_publication(pid, lien=lien)
            stock.etape(pid, f"En ligne : {lien}")
            await publieur.noter_lien(pid, stock.publication(pid), lien)
            return web.json_response(stock.publication(pid))
        depuis = dt.datetime.fromisoformat(p["debut"].replace("Z", "+00:00")).timestamp() if p.get("debut") else 0
        publieur.chercher_lien(pid, stock.publication(pid), {"plateforme": p["plateforme"], "identifiant": p["identifiant"]}, depuis)
        return web.json_response(stock.publication(pid))

    @r.get(P + "/api/publications/{pid:\\d+}/captures/{nom}")
    async def capture_etape(req):
        nom = req.match_info["nom"]
        f = lieux.DONNEES / "captures" / req.match_info["pid"] / nom
        if "/" in nom or "\\" in nom or ".." in nom or not f.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})

    # ── warm-up (chauffe.py) ───────────────────────────────────────────────────────────────────────────
    def seance_resumee(x):
        return {k: x[k] for k in ("id", "rang", "debut", "fin", "etat", "minutes", "minutes_faites", "vues", "likes",
                                  "abonnements", "recherches", "mots", "erreur")}

    @r.get(P + "/api/chauffes")
    async def chauffes(req):
        """Les comptes en warm-up (en cours d'abord), leur plan du jour et leurs chiffres ; les comptes qu'on peut y mettre."""
        maintenant_ = dt.datetime.now(dt.timezone.utc)
        tels = {t.udid: t for t in parc.telephones.values()}
        out = []
        for ch in stock.chauffes():
            toutes = stock.seances(ch["id"], limite=1000)
            j = chauffe.rang_du_jour(ch, chauffe.jour_paris(maintenant_))
            plan, du_jour = chauffe.etat_du_plan(stock, ch, maintenant_) if ch["etat"] == "en_cours" else ([], [])
            t = tels.get(ch["udid"])
            cible = (round(sum(s["minutes"] for s in chauffe.plan_rapide(ch)), 1) if ch.get("rapide")
                     else round(chauffe.minutes_du_jour(ch, j), 1) if 0 <= j < ch["jours"] else 0)
            out.append({**ch, "mots": chauffe.mots_de(ch), "jour": max(1, min(j + 1, ch["jours"])), "plan": plan,
                        "aujourdhui": {"minutes": round(sum(x["minutes_faites"] for x in du_jour), 1), "cible": cible},
                        "totaux": {"minutes": round(sum(x["minutes_faites"] for x in toutes), 1),
                                   **{k: sum(x.get(k) or 0 for x in toutes) for k in ("vues", "likes", "abonnements", "recherches", "likes_commentaires")},
                                   "seances": len(toutes)},
                        "seances": [seance_resumee(x) for x in toutes[:15]],
                        "telephone": {"nom": t.nom, "pret": t.pret, "occupe": t.occupe} if t else None})
        en_chauffe = {c["compte_id"] for c in out if c["etat"] == "en_cours"}
        comptes = [{"id": c["id"], "plateforme": c["plateforme"], "identifiant": c["identifiant"], "projet": c["projet"],
                    "groupe": c["groupe"], "telephone": tels[c["udid"]].nom if c["udid"] in tels else None,
                    "possible": bool(c["udid"]) and c["plateforme"] in ("tiktok", "instagram"), "en_chauffe": c["id"] in en_chauffe}
                   for c in stock.comptes() if c["actif"]]
        actives = [c for c in out if c["etat"] == "en_cours"]
        return web.json_response({"chauffes": out, "comptes": comptes, "maintenant": maintenant(),
                                  "projets": stock.projets_des_comptes(), "inventaires": etat_inventaires(),
                                  "pause": chauffe.en_pause(stock),
                                  "go_jour": round(sum(c["minutes_jour"] for c in actives) * chauffe.MO_PAR_MINUTE / 1000, 1),
                                  "journee": [f"{m // 60:02d}:{m % 60:02d}" for m in chauffe.JOURNEE],
                                  "minutes_seance": chauffe.MINUTES_SEANCE, "likes_jour": chauffe.LIKES_JOUR,
                                  "abonnements_jour": chauffe.ABONNEMENTS_JOUR})

    def reglages_chauffe(d, ancien=None):
        """Les réglages d'un warm-up, lus et bornés ; (réglages, erreur)."""
        mots = d.get("mots", ancien["mots"] if ancien else "")
        mots = "\n".join(mots) if isinstance(mots, list) else str(mots or "")
        if not chauffe.mots_de({"mots": mots}):
            return None, erreur(400, "donne au moins un mot-clé de la niche (un par ligne : « cuisine », « achat revente »…)")
        try:
            jours = int(d.get("jours", ancien["jours"] if ancien else 7))
            minutes = int(d.get("minutes_jour", ancien["minutes_jour"] if ancien else 40))
        except (TypeError, ValueError):
            return None, erreur(400, "durée ou minutes par jour illisibles")
        if not 1 <= jours <= 60 or not 5 <= minutes <= 180:
            return None, erreur(400, "entre 1 et 60 jours, entre 5 et 180 minutes par jour")
        oui = lambda k, defaut: bool(d[k]) if k in d else (bool(ancien[k]) if ancien else defaut)   # noqa: E731
        return {"mots": "\n".join(chauffe.mots_de({"mots": mots})), "jours": jours, "minutes_jour": minutes,
                "likes": oui("likes", True), "abonnements": oui("abonnements", True), "bloque": oui("bloque", True)}, None

    def ranger_nouveaux(comptes, projet):
        """Un compte trouvé par « Rafraîchir » n'a ni projet ni groupe : en warm-up, il prend le projet choisi (sinon celui
        des autres comptes de son téléphone) et un groupe neuf « Compte N » ; son TikTok et son Insta de même nom vont
        ensemble. Bloqué pendant le warm-up, il rentre dans la rotation à la fin (programmation.py)."""
        neufs = [c for c in comptes if not c["projet"]]
        if not neufs:
            return
        cle = lambda c: c["identifiant"].replace(".", "").replace("_", "")   # noqa: E731
        groupes = {}
        for c in neufs:
            p = projet or next((x["projet"] for x in stock.comptes() if x["udid"] == c["udid"] and x["projet"]), "")
            if not p:
                continue
            # son jumeau de l'autre réseau déjà rangé (même nom) : même groupe (14/10/2026 : le TikTok @mapage.style,
            # mis en warm-up après son Insta, était parti seul dans un groupe à lui)
            jumeau = next((x for x in stock.comptes_du_projet(p) if x["groupe"] and x["plateforme"] != c["plateforme"]
                           and cle(x) == cle(c)), None)
            if jumeau and (p, cle(c)) not in groupes:
                groupes[(p, cle(c))] = jumeau["groupe"]
            if (p, cle(c)) not in groupes:
                pris = [int(g.split()[-1]) for g in {x["groupe"] for x in stock.comptes_du_projet(p)} | {g for (q_, _), g in groupes.items() if q_ == p}
                        if g and g.split()[-1].isdigit()]
                groupes[(p, cle(c))] = f"Compte {max(pris + [0]) + 1}"
            stock.modifier_compte(c["id"], projet=p, groupe=groupes[(p, cle(c))])
            c.update(stock.compte(c["id"]))
            log.info("compte neuf @%s (%s) : projet %s, groupe %s", c["identifiant"], c["plateforme"], p, c["groupe"])

    @r.post(P + "/api/chauffes")
    async def creer_chauffes(req):
        """Met des comptes en warm-up, avec les mêmes réglages (mots-clés de la niche, jours, minutes par jour…)."""
        d = await req.json()
        reglages, err = reglages_chauffe(d)
        if err:
            return err
        comptes = [stock.compte(int(i)) for i in d.get("comptes") or []]
        if not comptes:
            return erreur(400, "choisis au moins un compte")
        en_cours = {c["compte_id"] for c in stock.chauffes(("en_cours",))}
        for c in comptes:
            if not c or not c["actif"]:
                return erreur(400, "un des comptes est inconnu ou désactivé")
            if not c["udid"]:
                return erreur(400, f"@{c['identifiant']} n'est rattaché à aucun téléphone (onglet Comptes)")
            if c["plateforme"] not in ("tiktok", "instagram"):
                return erreur(400, f"le warm-up {c['plateforme']} n'est pas encore écrit (TikTok et Instagram seulement)")
            if c["id"] in en_cours:
                return erreur(409, f"@{c['identifiant']} est déjà en warm-up")
        debut = dt.datetime.now(dt.timezone.utc)
        fin = debut + dt.timedelta(days=reglages["jours"])
        rapide = bool(d.get("rapide"))
        if rapide:   # « ⚡ Rapide jusqu'à 07:00 » (heure de Paris ; passée, c'est le lendemain)
            try:
                h, m = (int(x) for x in str(d.get("jusqua") or "07:00").split(":")[:2])
                fin = dt.datetime.combine(chauffe.jour_paris(debut), dt.time(h, m), tzinfo=chauffe.PARIS)
            except (TypeError, ValueError):
                return erreur(400, "heure de fin illisible (ex. 07:00)")
            if fin <= debut + dt.timedelta(minutes=30):
                fin += dt.timedelta(days=1)
            reglages["jours"] = (chauffe.jour_paris(fin) - chauffe.jour_paris(debut)).days + 1
        ranger_nouveaux(comptes, (d.get("projet") or "").strip())
        faits = [stock.creer_chauffe(c["id"], reglages["mots"], reglages["jours"], reglages["minutes_jour"], reglages["likes"],
                                     reglages["abonnements"], reglages["bloque"], chauffe.iso(debut), chauffe.iso(fin), rapide)
                 for c in comptes]
        log.info("warm-up : %s compte(s) pour %s jours, %s min par jour (%s)", len(faits), reglages["jours"],
                 reglages["minutes_jour"], ", ".join("@" + c["identifiant"] for c in comptes))
        return web.json_response({"chauffes": faits})

    def chauffe_de(req):
        ch = stock.chauffe(int(req.match_info["cid"]))
        if not ch:
            raise web.HTTPNotFound(text=json.dumps({"erreur": "warm-up inconnu"}), content_type="application/json")
        return ch

    @r.post(P + "/api/chauffes/{cid:\\d+}")
    async def modifier_chauffe(req):
        ch = chauffe_de(req)
        reglages, err = reglages_chauffe(await req.json(), ch)
        if err:
            return err
        if reglages["jours"] != ch["jours"]:
            reglages["fin"] = chauffe.iso(chauffe.utc(ch["debut"]) + dt.timedelta(days=reglages["jours"]))
        stock.maj_chauffe(ch["id"], **{k: (1 if v is True else 0 if v is False else v) for k, v in reglages.items()})
        return web.json_response(stock.chauffe(ch["id"]))

    @r.post(P + "/api/chauffes/{cid:\\d+}/prolonger")
    async def prolonger_chauffe(req):
        ch = chauffe_de(req)
        n = min(max(int((await req.json()).get("jours", 3)), 1), 30)
        fin = max(chauffe.utc(ch["fin"]), dt.datetime.now(dt.timezone.utc)) + dt.timedelta(days=n)
        jours = (chauffe.jour_paris(fin) - chauffe.jour_paris(chauffe.utc(ch["debut"]))).days
        stock.maj_chauffe(ch["id"], jours=jours, fin=chauffe.iso(fin), etat="en_cours")
        return web.json_response(stock.chauffe(ch["id"]))

    @r.post(P + "/api/chauffes/{cid:\\d+}/arreter")
    async def arreter_chauffe(req):
        ch = chauffe_de(req)
        if ch["etat"] != "en_cours":
            return erreur(409, "ce warm-up est déjà fini")
        stock.maj_chauffe(ch["id"], etat="arrete", fin=maintenant())
        log.info("warm-up de @%s arrêté à la main", ch["identifiant"])
        return web.json_response(stock.chauffe(ch["id"]))

    @r.post(P + "/api/chauffes/{cid:\\d+}/retirer")
    async def retirer_chauffe(req):
        """Retire de la liste un warm-up fini (terminé ou arrêté), avec ses séances et leurs captures."""
        import shutil
        ch = chauffe_de(req)
        if ch["etat"] == "en_cours":
            return erreur(409, "arrête d'abord ce warm-up")
        for sid in stock.retirer_chauffe(ch["id"]):
            shutil.rmtree(lieux.DONNEES / "captures" / f"seance-{sid}", ignore_errors=True)
        log.info("warm-up de @%s retiré de la liste", ch["identifiant"])
        return web.json_response({"ok": True})

    def etat_inventaires():
        return {u: {**e, "journal": e.get("journal", [])[-12:]} for u, e in publieur.inventaires.items()}

    @r.post(P + "/api/t/{udid}/sonde-commentaires")
    async def sonde_commentaires(req):
        """Ouvre les commentaires d'une vidéo TikTok et d'un reel, captures et arbres gardés (sonde.py) ; rien n'est liké."""
        t = parc.telephones.get(req.match_info["udid"])
        if not t or not t.pret:
            return erreur(409, "téléphone pas prêt")
        publieur.sondes[t.udid] = {"telephone": t.nom, "etat": "en_file", "journal": []}
        publieur.sondes_demandees.add(t.udid)
        return web.json_response({"ok": True})

    @r.get(P + "/api/t/{udid}/sonde-commentaires")
    async def sonde_etat(req):
        return web.json_response(publieur.sondes.get(req.match_info["udid"]) or {})

    @r.post(P + "/api/comptes/rafraichir")
    async def rafraichir_comptes(req):
        """« 🔄 Rafraîchir les comptes » : chaque téléphone branché lit les comptes connectés à TikTok et Instagram (dès qu'il
        est libre : une publication passe avant) et ajoute ceux qui manquent (inventaire.py)."""
        lances, absents = [], []
        for t in parc.telephones.values():
            if not t.pret:
                absents.append(t.nom)
                continue
            if publieur.inventaires.get(t.udid, {}).get("etat") in ("en_file", "en_cours"):
                lances.append(t.nom)
                continue
            publieur.inventaires[t.udid] = {"telephone": t.nom, "etat": "en_file", "debut": maintenant(), "fin": None,
                                            "trouves": {}, "ajoutes": [], "erreurs": [], "journal": []}
            publieur.inventaires_demandes.add(t.udid)
            lances.append(t.nom)
        if not lances:
            return erreur(409, "aucun téléphone prêt : branche-le et attends qu'il soit prêt")
        return web.json_response({"lances": lances, "absents": absents, "pause": publieur.pause})

    @r.post(P + "/api/chauffes/pause")
    async def pause_chauffes(req):
        """« ⏸ Pause » / « ▶ Reprendre » : tous les warm-ups d'un coup (la séance en cours s'arrête dans les 5 s)."""
        pause = bool((await req.json()).get("pause"))
        stock.poser_reglage("pause_warmup", "1" if pause else "0")
        log.info("warm-ups %s", "mis en pause" if pause else "repris")
        return web.json_response({"pause": pause})

    @r.post(P + "/api/chauffes/{cid:\\d+}/seance")
    async def seance_maintenant(req):
        """Une séance tout de suite (pour voir le warm-up tourner), si le téléphone est libre et la file pas en pause."""
        ch = chauffe_de(req)
        d = await req.json()
        if ch["etat"] != "en_cours":
            return erreur(409, "ce warm-up est fini : prolonge-le d'abord")
        t = parc.telephones.get(ch["udid"])
        if not t:
            return erreur(409, "le téléphone de ce compte n'est pas branché")
        if publieur.pause:
            return erreur(409, "la file est en pause : relance-la d'abord (une séance s'arrête quand la file est en pause)")
        if chauffe.en_pause(stock):
            return erreur(409, "les warm-ups sont en pause : appuie sur « ▶ Reprendre » d'abord")
        minutes = min(max(float(d.get("minutes") or chauffe.MINUTES_SEANCE), 2), 60)
        try:
            publieur.lancer_seance(t, ch, minutes)
        except RuntimeError as e:
            return erreur(409, str(e))
        return web.json_response({"ok": True})

    @r.get(P + "/api/seances/{sid:\\d+}")
    async def seance_detail(req):
        x = stock.seance(int(req.match_info["sid"]))
        if not x:
            return erreur(404, "séance inconnue")
        lignes = []
        for l in (x["journal"] or "").splitlines():
            heure, _, reste = l.partition(" ")
            capture = None
            if reste.endswith("]") and " [" in reste:
                reste, _, capture = reste.rpartition(" [")
                capture = capture[:-1]
            lignes.append({"heure": heure, "message": reste, "capture": capture})
        return web.json_response({**seance_resumee(x), "journal": lignes})

    @r.get(P + "/api/seances/{sid:\\d+}/captures/{nom}")
    async def capture_seance(req):
        nom = req.match_info["nom"]
        f = lieux.DONNEES / "captures" / f"seance-{req.match_info['sid']}" / nom
        if "/" in nom or "\\" in nom or ".." in nom or not f.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})

    app.add_routes(r)
    app["plateformes"] = PLATEFORMES
    return app
