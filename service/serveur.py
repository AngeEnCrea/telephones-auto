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
import videos
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
            noms = sorted({programmation.nom_groupe(c) for c in comptes})
            projets.append({"slug": slug, "groupes": [{"nom": g, "decalage_min": programmation.decalage(stock, noms, g),
                                                        "comptes": [{"plateforme": c["plateforme"], "identifiant": c["identifiant"]}
                                                                    for c in comptes if programmation.nom_groupe(c) == g]}
                                                       for g in noms]})
        return web.json_response({"debut": jour.isoformat(), "jours": jours, "aujourdhui": dt.datetime.now(paris).date().isoformat(),
                                  "telephones": [{"nom": t.nom, "pret": t.pret, "wifi": bool(t.ip)} for t in parc.telephones.values()],
                                  "wifi_obligatoire": stock.reglage("wifi_obligatoire", "1") == "1",
                                  "creneaux": [f"{h:02d}:{m:02d}" for h, m in programmation.creneaux(stock)],
                                  "auto": stock.reglage("programmation_auto", "1") == "1", "variation_min": programmation.VARIATION_MIN,
                                  "projets": projets, "entrees": sorted(entrees.values(), key=lambda e: e["quand"]),
                                  "chauffes": len(stock.chauffes(("en_cours",)))})

    @r.get(P + "/api/programmation")
    async def programmation_get(req):
        return web.json_response({"auto": stock.reglage("programmation_auto", "1") == "1",
                                  "creneaux": [f"{h:02d}:{m:02d}" for h, m in programmation.creneaux(stock)],
                                  "ecart_min": programmation.ecart_groupes(stock, max([2] + [len({programmation.nom_groupe(c) for c in stock.comptes_du_projet(p)})
                                                                                               for p in stock.projets_des_comptes()])),
                                  "wifi_obligatoire": stock.reglage("wifi_obligatoire", "1") == "1"})

    @r.post(P + "/api/programmation")
    async def programmation_post(req):
        """Les vidéos des dossiers de groupe partent-elles toutes seules, et à quelles heures (« 09:00,12:00,… », heure de Paris)."""
        d = await req.json()
        if "auto" in d:
            stock.poser_reglage("programmation_auto", "1" if d["auto"] else "0")
        if "wifi_obligatoire" in d:
            stock.poser_reglage("wifi_obligatoire", "1" if d["wifi_obligatoire"] else "0")
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
                await videos.verifier_publiable(http, cle)
                dest = lieux.DONNEES / "videos" / f"essai-{videos.nom_de_travail(cle)}"
                if not dest.exists():
                    await videos.telecharger(http, cle, dest)
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
        return web.json_response({"projet": slug, "groupes": [{"nom": k, "comptes": v} for k, v in groupes.items()],
                                  "publications": pubs[:40], "ecart_min": int(stock.reglage("ecart_envoi_min", "30")),
                                  "repetition": stock.reglage("repetition_defaut", "1") == "1"})

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
        pubs = [stock.creer_publication(c["id"], cle, video["titre"], legende,
                                        (t0 + dt.timedelta(minutes=ordre.index(c["groupe"] or "@" + c["identifiant"]) * ecart)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        bool(d.get("repetition")), envoi)
                for c in comptes]
        log.info("envoi %s : « %s » vers %s compte(s), %s groupe(s), un groupe toutes les %s min%s", envoi, video["titre"],
                 len(pubs), len(ordre), ecart, " (répétition)" if d.get("repetition") else "")
        return web.json_response({"envoi": envoi, "publications": pubs})

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
        p = stock.creer_publication(compte["id"], cle, video["titre"], str(d.get("legende", ""))[:2200],
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
        stock.maj_publication(pid, etat="annule", fin=maintenant())
        return web.json_response(stock.publication(pid))

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
        if d.get("creneau"):   # au prochain créneau libre de son groupe plutôt que tout de suite (calendrier, 05/10/2026)
            du_groupe, decalage = programmation.groupe_de(stock, stock.compte(p["compte_id"]))
            champs["quand"] = programmation.prochain_creneau(stock, du_groupe, decalage)
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
        quand = programmation.reporter(stock, pubs, "Depuis le calendrier" if pubs[0]["etat"] == "en_attente"
                                       else "Ratée, remise en file depuis le calendrier")
        if not quand:
            return erreur(409, "aucun créneau libre dans les 90 jours (réglage « créneaux » vide ?)")
        return web.json_response({"quand": quand, "publications": [stock.publication(p["id"]) for p in pubs]})

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
        en publiée, et son lien est cherché comme pour les autres (sans toucher au téléphone)."""
        pid = int(req.match_info["pid"])
        p = stock.publication(pid)
        if not p or p["etat"] != "echec" or p["repetition"]:
            return erreur(409, "seule une vraie publication en échec se marque en ligne")
        stock.maj_publication(pid, etat="publie", erreur="")
        stock.etape(pid, "Marquée en ligne à la main (vérifiée sur le compte)")
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
            out.append({**ch, "mots": chauffe.mots_de(ch), "jour": max(1, min(j + 1, ch["jours"])), "plan": plan,
                        "aujourdhui": {"minutes": round(sum(x["minutes_faites"] for x in du_jour), 1),
                                       "cible": round(chauffe.minutes_du_jour(ch, j), 1) if 0 <= j < ch["jours"] else 0},
                        "totaux": {"minutes": round(sum(x["minutes_faites"] for x in toutes), 1),
                                   **{k: sum(x[k] for x in toutes) for k in ("vues", "likes", "abonnements", "recherches")},
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
                                  "go_jour": round(sum(c["minutes_jour"] for c in actives) * chauffe.MO_PAR_MINUTE / 1000, 1),
                                  "journee": [f"{m // 60:02d}:{m % 60:02d}" for m in chauffe.JOURNEE],
                                  "minutes_seance": chauffe.MINUTES_SEANCE, "likes_jour": chauffe.LIKES_JOUR,
                                  "abonnements_jour": chauffe.ABONNEMENTS_JOUR})

    def reglages_chauffe(d, ancien=None):
        """Les réglages d'un warm-up, lus et bornés ; (réglages, erreur)."""
        mots = d.get("mots", ancien["mots"] if ancien else "")
        mots = "\n".join(mots) if isinstance(mots, list) else str(mots or "")
        if not chauffe.mots_de({"mots": mots}):
            return None, erreur(400, "donne au moins un mot-clé de la niche (un par ligne : « vinted », « achat revente »…)")
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
        faits = [stock.creer_chauffe(c["id"], reglages["mots"], reglages["jours"], reglages["minutes_jour"], reglages["likes"],
                                     reglages["abonnements"], reglages["bloque"], chauffe.iso(debut),
                                     chauffe.iso(debut + dt.timedelta(days=reglages["jours"])))
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
