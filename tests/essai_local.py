"""essai_local.py : le service entier contre le faux iPhone (faux_iphone.py), un dossier de vidéos et un faux Scrape
Creators, sur le Mac (ou Linux), en une dizaine de minutes. Ce qu'il prouve : la préparation jusqu'à « prêt », l'écran en
direct, les gestes, l'inspecteur, la garde anti-page-piégée, le verrou du dossier des vidéos, une publication en
répétition (rien ne part) puis pour de vrai (lien récupéré et noté), TikTok et Instagram, la programmation, le
calendrier, le warm-up, le débranchement. Ce qu'il ne prouve pas : les vrais noms des boutons des apps.

  python tests/essai_local.py            (le Python doit avoir aiohttp et pillow)
"""
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aiohttp
from aiohttp import web

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
RESULTATS = []


def port_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok)))
    print(f"{'PASSE' if ok else 'ÉCHEC'}  {nom}{'  — ' + str(detail) if detail and not ok else ''}", flush=True)


def preparer_signature(tmp, env):
    """Le certificat exporté d'Impactor et l'IPA de l'agent, factices, là où le service les cherche."""
    (tmp / "certificats").mkdir(parents=True, exist_ok=True)
    (tmp / "certificats" / "TEAMFAUX_certificate.p12").write_bytes(b"p12 factice")
    (tmp / "agent").mkdir(parents=True, exist_ok=True)
    (tmp / "agent" / "WebDriverAgent-16.13.6.ipa").write_bytes(b"ipa factice")
    env.update(TELEPHONES_CERTIFICATS=str(tmp / "certificats"), TELEPHONES_AGENT=str(tmp / "agent"))


async def faux_scrape(port, lire_iphone):
    r = web.RouteTableDef()

    # le faux Scrape Creators (liens.py) : les dernières vidéos TikTok d'un compte, lues sur le faux iPhone
    @r.get("/scrape/v1/tiktok/profile")
    async def sc_profil(req):
        if req.headers.get("x-api-key") != "cle-de-test":
            return web.json_response({"error": "cle"}, status=401)
        return web.json_response({"user": {"id": "U" + req.query["handle"]}})

    @r.get("/scrape/v3/tiktok/profile/videos")
    async def sc_videos(req):
        if req.headers.get("x-api-key") != "cle-de-test":
            return web.json_response({"error": "cle"}, status=401)
        posts = [x for x in lire_iphone().get("tt_posts", []) if x["compte"] == req.query["handle"]]
        return web.json_response({"aweme_list": [{"aweme_id": x["id"], "desc": x["desc"], "create_time": x["t"]} for x in reversed(posts)]})

    @r.get("/scrape/v1/instagram/profile")
    async def sc_instagram(req):
        if req.headers.get("x-api-key") != "cle-de-test":
            return web.json_response({"error": "cle"}, status=401)
        posts = lire_iphone().get("ig_pubs", {}).get(req.query["handle"], [])
        return web.json_response({"data": {"user": {"edge_owner_to_timeline_media": {"edges": [
            {"node": {"shortcode": x["id"], "product_type": "clips", "taken_at_timestamp": x["t"],
                      "edge_media_to_caption": {"edges": [{"node": {"text": x["desc"]}}]}}} for x in posts]}}}})

    app = web.Application()
    app.add_routes(r)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return runner


async def principal():
    tmp = Path(tempfile.mkdtemp(prefix="essai-telephones-"))
    p_service, p_scrape = port_libre(), port_libre()
    env = dict(os.environ, FAUX_IOS_DIR=str(tmp / "iphone"), FAUX_PYTHON=sys.executable,
               TELEPHONES_IOS=str(ICI / "faux-ios"), TELEPHONES_PMD3=str(ICI / "faux-pymobiledevice3"),
               TELEPHONES_DONNEES=str(tmp / "donnees"), TELEPHONES_PORT=str(p_service), TELEPHONES_VIDEOS=str(tmp / "videos"),
               TELEPHONES_PORT_AGENT=str(port_libre()), TELEPHONES_PORT_FLUX=str(port_libre()),
               TELEPHONES_JOURNAL=str(tmp / "service.log"), TELEPHONES_SCRAPE=f"http://127.0.0.1:{p_scrape}/scrape/",
               TELEPHONES_SECRETS=str(tmp / "secrets"), TELEPHONES_ATTENTES_LIENS="1,1,2",
               TELEPHONES_CHAUFFE_ECHELLE="0.02", TELEPHONES_CHAUFFE_P_LIKE="1", TELEPHONES_CHAUFFE_P_SUIVRE="1",
               TELEPHONES_PROGRAMMATION_S="2")
    # le dossier des vidéos : deux à publier à la main, une dans le dossier du groupe « Clips 1 » (programmée seule)
    for nom in ("abc.mp4", "ghi.mp4", "Clips 1/rem.mp4"):
        (tmp / "videos" / nom).parent.mkdir(parents=True, exist_ok=True)
        (tmp / "videos" / nom).write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(200_000))
    (tmp / "videos" / "Clips 1" / "rem.txt").write_text("Remontage 🔁 #vinted", encoding="utf-8")
    (tmp / "videos" / "_archives").mkdir()
    (tmp / "videos" / "_archives" / "vieille.mp4").write_bytes(b"x")          # dossier en « _ » : ignoré
    (tmp / "secrets").mkdir(parents=True, exist_ok=True)
    (tmp / "secrets" / "scrapecreators.env").write_text("SCRAPECREATORS_API_KEY=cle-de-test\n", encoding="utf-8")
    os.chmod(ICI / "faux-ios", 0o755)
    os.chmod(ICI / "faux-pymobiledevice3", 0o755)
    preparer_signature(tmp, env)
    subprocess.run([sys.executable, str(ICI / "faux_iphone.py"), "--reinitialiser"], env=env, check=True)
    etat_iphone = tmp / "iphone" / "etat.json"
    lire_iphone = lambda: json.loads(etat_iphone.read_text(encoding="utf-8"))

    def modifier_iphone(**k):
        e = lire_iphone()
        e.update(k)
        etat_iphone.write_text(json.dumps(e), encoding="utf-8")

    runner = await faux_scrape(p_scrape, lambda: json.loads(etat_iphone.read_text(encoding="utf-8")))
    service = subprocess.Popen([sys.executable, str(RACINE / "service" / "telephones.py")], env=env)
    base = f"http://127.0.0.1:{p_service}/telephones"
    json_ = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as h:
            async def get(chemin):
                async with h.get(base + chemin) as r:
                    return r.status, await r.json(content_type=None)

            async def post(chemin, corps, **kw):
                async with h.post(base + chemin, data=json.dumps(corps), headers={**json_, **kw.get("entetes", {})}) as r:
                    return r.status, await r.json(content_type=None)

            async def attendre(test, delai, pas=0.5):
                fin = time.monotonic() + delai
                while time.monotonic() < fin:
                    try:
                        v = await test()
                        if v:
                            return v
                    except (aiohttp.ClientError, KeyError, IndexError):
                        pass
                    await asyncio.sleep(pas)
                return None

            async def pret():
                _, e = await get("/api/etat")
                t = e["parc"]["telephones"]
                return t[0] if t and t[0]["pret"] else None

            t = await attendre(pret, 60)
            verifier("le faux iPhone devient prêt (confiance, mode dév, tunnel, image, agent, écran)", t,
                     (await get("/api/etat"))[1] if not t else "")
            if not t:
                return
            udid = t["udid"]
            verifier("image développeur : go-ios refusé par Apple en HTTPS, pymobiledevice3 prend le relais",
                     lire_iphone()["image_par"] == "pymobiledevice3", lire_iphone()["image_par"])
            verifier("agent posé par Impactor (module de test pas signé) : re-signé tout seul par go-ios",
                     lire_iphone()["agent_signe_par"] == "go-ios", lire_iphone()["agent_signe_par"])
            verifier("un ancien agent resté sur l'iPhone est arrêté avant d'en lancer un neuf",
                     "com.faux.WebDriverAgentRunner.xctrunner" in lire_iphone().get("tues", []), lire_iphone().get("tues"))
            agent = next(e for e in t["etapes"] if e["cle"] == "agent")
            verifier("échéance de la signature lue sur l'iPhone et affichée", t["expire"] and agent["message"].startswith("Signé jusqu'au"),
                     (t["expire"], agent["message"]))
            verifier("taille de l'écran lue en points", t["taille"] == [390, 844], t["taille"])
            verifier("toutes les étapes au vert", all(e["etat"] in ("ok", "inutile") for e in t["etapes"]), t["etapes"])

            async with h.get(f"{base}/api/t/{udid}/flux") as r:
                debut = await r.content.read(3000)
            verifier("écran en direct : le flux MJPEG arrive (image JPEG)", b"\xff\xd8" in debut, debut[:80])

            async with h.get(f"{base}/api/t/{udid}/capture") as r:
                verifier("capture PNG", r.status == 200 and (await r.read())[:4] == b"\x89PNG")

            s, _ = await post(f"/api/t/{udid}/geste", {"type": "lancer", "bundle": "com.zhiliaoapp.musically"})
            verifier("geste : lancer une app", s == 200 and lire_iphone()["ecran"] == "tt_intrus")
            s, _ = await post(f"/api/t/{udid}/geste", {"type": "toucher", "x": 195, "y": 536})
            verifier("geste : toucher un point (« J'ai compris »)", s == 200 and lire_iphone()["ecran"] == "tt_fil")
            s, a = await get(f"/api/t/{udid}/arbre")
            verifier("inspecteur : l'arbre donne les boutons et leur place",
                     s == 200 and any(x["label"] == "Profil" for x in a["elements"]), a)
            s, _ = await post(f"/api/t/{udid}/geste", {"type": "accueil"})

            async with h.post(f"{base}/api/t/{udid}/geste", data=json.dumps({"type": "accueil"}), headers={"Content-Type": "text/plain"}) as r:
                verifier("garde : un POST qui n'est pas du JSON est refusé (415)", r.status == 415)
            s, _ = await post(f"/api/t/{udid}/geste", {"type": "accueil"}, entetes={"Origin": "http://piege.example"})
            verifier("garde : une autre origine est refusée (403)", s == 403)

            s, prog = await post("/api/programmation", {"auto": False})
            verifier("programmation : créneaux par défaut 9 h, 12 h, 15 h, 18 h, 21 h", s == 200 and prog["creneaux"] == ["09:00", "12:00", "15:00", "18:00", "21:00"], prog)
            s, c = await post("/api/comptes", {"plateforme": "tiktok", "identifiant": "@ma_page", "udid": udid, "client": "Moi"})
            verifier("compte ajouté", s == 200 and c["identifiant"] == "ma_page", c)
            s, dbl = await post("/api/comptes", {"plateforme": "tiktok", "identifiant": "ma_page", "udid": udid})
            verifier("un compte ne s'ajoute pas deux fois (409)", s == 409, dbl)
            s, v = await get("/api/videos")
            verifier("seules les vidéos du dossier sont proposées (pas celles d'un dossier en « _ »), la légende lue dans le .txt",
                     s == 200 and sorted(x["titre"] for x in v) == ["abc", "ghi", "rem"]
                     and next(x for x in v if x["titre"] == "rem")["description"] == "Remontage 🔁 #vinted"
                     and next(x for x in v if x["titre"] == "rem")["groupe"] == "Clips 1", v)
            s, refus = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:def.mp4"})
            verifier("verrou : une vidéo absente du dossier est refusée", s == 400, refus)

            modifier_iphone(tt_lancements=0)          # TikTok rouvre sur sa fenêtre « J'ai compris »
            n0 = len(lire_iphone()["journal"])
            s, p = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:abc.mp4",
                                                    "legende": "Le stock se lit dans les favoris 👀 #vinted", "repetition": True})
            verifier("publication en répétition mise en file", s == 200 and p["repetition"] == 1, p)

            async def fini(pid):
                _, x = await get(f"/api/publications/{pid}")
                return x if x["etat"] not in ("en_attente", "en_cours") else None

            x = await attendre(lambda: fini(p["id"]), 120, 1)
            verifier("répétition : parcours complet sans publier", x and x["etat"] == "repete", x and (x["etat"], x["erreur"], [e["message"] for e in x["etapes"]]))
            verifier("répétition : rien n'a été publié chez le faux TikTok", not lire_iphone()["tt_videos"].get("ma_page"))
            ip = lire_iphone()
            verifier("caméra et micro refusés à TikTok, photos accordées en entier (vu le 04/10/2026)",
                     not ip.get("tt_camera_accordee") and ip.get("tt_photos_ok") and not ip.get("tt_photos_limite")
                     and sum(1 for j in ip["journal"] if j.startswith("alerte camera") or j.startswith("alerte micro")) == 2,
                     [j for j in ip["journal"] if j.startswith("alerte")])
            verifier("galerie de TikTok : la DERNIÈRE vidéo (la plus récente) choisie par son rond, jamais une vidéo personnelle",
                     any(j.startswith("tt_galerie:rond auto-") for j in ip["journal"]) and not any("perso" in j for j in ip["journal"]),
                     [j for j in ip["journal"] if j.startswith("tt_galerie")])
            verifier("répétition TikTok : le son ajouté par TikTok retiré, puis sortie sans publier (TikTok garde un brouillon)",
                     any(j.startswith("tt_editeur:son retiré") for j in ip["journal"]) and ip["tt_brouillons"].get("ma_page", 0) >= 1,
                     (ip["tt_brouillons"], ip["journal"][-14:]))
            verifier("fenêtre « J'ai compris » de TikTok fermée par la recette (vue le 03/10/2026)",
                     "tt_intrus:J'ai compris" in lire_iphone()["journal"][n0:], lire_iphone()["journal"][n0:n0 + 8])
            verifier("répétition : une capture par étape", x and sum(1 for e in x["etapes"] if e["capture"]) >= 8,
                     x and [(e["message"], e["capture"]) for e in x["etapes"]])
            if x and x["etapes"] and x["etapes"][0]["capture"]:
                async with h.get(f"{base}/api/publications/{p['id']}/captures/{x['etapes'][0]['capture']}") as r:
                    verifier("capture d'étape lisible (JPEG)", r.status == 200 and (await r.read())[:2] == b"\xff\xd8")
            verifier("la vidéo est passée par Photos (VLC → Raccourci à 2 actions → une vidéo de plus dans la pellicule : preuve)",
                     any(n.startswith("auto-") for n in lire_iphone()["photos"]))
            restes = list((tmp / "iphone" / "apps" / "org.videolan.vlc-ios" / "Documents" / "import").glob("*"))
            verifier("la copie déposée dans VLC est effacée par le service", not restes, restes)

            s, p2 = await post(f"/api/publications/{p['id']}/relancer", {"repetition": False})
            verifier("« Publier pour de vrai » remet en file sans répétition", s == 200 and p2["repetition"] == 0 and p2["etat"] == "en_attente", p2)
            x = await attendre(lambda: fini(p["id"]), 120, 1)
            verifier("publication pour de vrai : publiée", x and x["etat"] == "publie", x and (x["etat"], x["erreur"], [e["message"] for e in x["etapes"]]))
            ip = lire_iphone()
            verifier("le faux TikTok a la vidéo sur le bon compte, avec la légende (émoji compris)",
                     (ip.get("dernier_post") or {}).get("compte") == "ma_page" and "👀" in (ip.get("dernier_post") or {}).get("desc", ""),
                     ip.get("dernier_post"))
            verifier("son ajouté par TikTok retiré avant de publier", ip.get("dernier_post", {}).get("son") is None, ip.get("dernier_post"))
            verifier("« Publier » touché sur la pastille rouge du haut (clavier ouvert, hors de l'arbre, vu le 04/10/2026)",
                     "tt_poster:pastille Publier" in ip["journal"], [j for j in ip["journal"] if j.startswith("tt_poster")])
            async def avec_lien(pid):
                _, y = await get(f"/api/publications/{pid}")
                return y if y.get("lien") else None

            x = await attendre(lambda: avec_lien(p["id"]), 30, 1) or x
            verifier("lien de la vidéo retrouvé à part par Scrape Creators, à sa légende (le téléphone était déjà libre)",
                     x and x["lien"] == f"https://www.tiktok.com/@ma_page/video/{ip['tt_posts'][-1]['id']}", x and x["lien"])
            await asyncio.sleep(1)
            verifier("compte choisi au @ exact (ma_page2.0 était actif et contient ma_page), lu sur la capture, après le « chargement… » de 6 s",
                     (ip.get("dernier_post") or {}).get("compte") == "ma_page" and any(j.startswith("tt_comptes:toucher") for j in ip["journal"]),
                     ip["journal"][-12:])
            verifier("« Ajouter un compte » jamais touché", not ip.get("tt_ajout_touche"))
            pr = ip.get("profondeurs") or []
            verifier("arbre lu sur 15 niveaux sur le fil de TikTok, 40 dans la création, 40 remis après", 15 in pr and 25 in pr and pr[-1] == 40, pr)
            liens_csv = lambda: (tmp / "donnees" / "liens.csv").read_text(encoding="utf-8") if (tmp / "donnees" / "liens.csv").exists() else ""   # noqa: E731
            verifier("lien noté dans donnees/liens.csv", bool(x) and f"abc.mp4;{x['lien']}" in liens_csv(), liens_csv())

            s, p3 = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:abc.mp4", "legende": "encore"})
            await asyncio.sleep(8)
            _, x3 = await get(f"/api/publications/{p3['id']}")
            verifier("rythme : le même compte attend 30 min avant de republier", x3["etat"] == "en_attente", x3["etat"])
            s, _ = await post(f"/api/publications/{p3['id']}/annuler", {})
            verifier("annuler une publication en file", s == 200)

            # sans Wi-Fi (partage de connexion parti, 05/10/2026), rien ne part : la publication attend, puis part au retour du Wi-Fi
            modifier_iphone(wifi=False)
            await asyncio.sleep(6)
            s, pw = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:abc.mp4", "legende": "wifi", "repetition": True})
            await asyncio.sleep(10)
            _, xw = await get(f"/api/publications/{pw['id']}")
            _, calw = await get("/api/calendrier")
            verifier("sans Wi-Fi : la publication attend en file (pas d'échec), le calendrier le signale",
                     xw["etat"] == "en_attente" and any(not t["wifi"] for t in calw.get("telephones", [])), (xw["etat"], calw.get("telephones")))
            modifier_iphone(wifi=True)
            xw = await attendre(lambda: fini(pw["id"]), 120, 1)
            verifier("Wi-Fi revenu : la file repart toute seule", xw and xw["etat"] == "repete", xw and (xw["etat"], xw["erreur"]))

            # les comptes groupés (Clips 1 = TikTok + Insta, Clips 2), envoi étalé (un groupe toutes les N min)
            s1, _ = await post(f"/api/comptes/{c['id']}", {"groupe": "Clips 1"})
            _, ig = await post("/api/comptes", {"plateforme": "instagram", "identifiant": "ma.page.ig", "udid": udid,
                                                "groupe": "Clips 1"})
            _, c2 = await post("/api/comptes", {"plateforme": "tiktok", "identifiant": "clips_deux", "udid": udid,
                                                "groupe": "Clips 2"})
            # la vidéo du dossier « Clips 1 » part toute seule au prochain créneau de son groupe (TikTok + Insta), pas sur Clips 2
            s, _ = await post("/api/programmation", {"auto": True})

            async def programme():
                _, d = await get("/api/destinations?video=dossier:Clips 1/rem.mp4")
                return d["publications"] if len(d.get("publications") or []) >= 2 else None

            pr = await attendre(programme, 15, 1) or []
            heures = {dt.datetime.fromisoformat(x["quand"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris")) for x in pr}

            def ecart_au_creneau(h):   # en minutes, au créneau le plus proche (9, 12, 15, 18, 21 h ; ceux du lendemain compris)
                return min(abs((h - h.replace(hour=c, minute=0, second=0, microsecond=0) - dt.timedelta(days=j)).total_seconds()) / 60
                           for c in (9, 12, 15, 18, 21) for j in (-1, 0, 1))
            verifier("vidéo du dossier de groupe programmée toute seule sur SON groupe (TikTok + Insta de Clips 1), au hasard à ± 15 min d'un créneau, pour de vrai",
                     len(pr) == 2 and {x["identifiant"] for x in pr} == {"ma_page", "ma.page.ig"} and len(heures) == 1
                     and all(ecart_au_creneau(h) <= 15 for h in heures) and not any(x["repetition"] for x in pr)
                     and all(x["etat"] == "en_attente" for x in pr), (pr, heures))
            await asyncio.sleep(3)
            _, d2 = await get("/api/destinations?video=dossier:Clips 1/rem.mp4")
            # une publication ratée, remise au prochain créneau libre de son groupe (bouton du calendrier)
            s, pr0 = await post("/api/publications", {"compte_id": c2["id"], "video": "dossier:ghi.mp4", "legende": "x"})
            await post(f"/api/publications/{pr0['id']}/annuler", {})
            s, pr1 = await post(f"/api/publications/{pr0['id']}/relancer", {"creneau": True})
            h1 = dt.datetime.fromisoformat(pr1["quand"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris")) if s == 200 and pr1.get("quand") else None
            verifier("relancer « au prochain créneau » : à ± 15 min d'un créneau de Clips 2 (décalé de 1 h 30 : à mi-chemin), en file",
                     h1 is not None and pr1["etat"] == "en_attente"
                     and min(abs((h1 - h1.replace(hour=c, minute=30, second=0, microsecond=0) - dt.timedelta(days=j)).total_seconds()) / 60
                             for c in (10, 13, 16, 19, 22) for j in (-1, 0, 1)) <= 15, (s, pr1))
            await post(f"/api/publications/{pr0['id']}/annuler", {})

            # un créneau manqué de 45 min (téléphone débranché, sans réseau) ne se rattrape pas en rafale : TikTok + Insta
            # du groupe ENSEMBLE au prochain créneau libre (06/10/2026 : celles de 8 h 58 et 9 h 18 seraient sorties à
            # 11 h, une heure avant celles de midi )
            ids_pr = sorted(x["id"] for x in pr)
            passe = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if ids_pr:
                with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:
                    db.execute(f"update publications set quand = ? where id in ({', '.join('?' * len(ids_pr))})", (passe, *ids_pr))

            async def reportees():
                ps = [(await get(f"/api/publications/{i}"))[1] for i in ids_pr]
                return ps if ps and all(x["quand"] and x["quand"] > passe for x in ps) else None
            rp = await attendre(reportees, 60, 1) or []
            hr = {dt.datetime.fromisoformat(x["quand"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris")) for x in rp}
            verifier("créneau manqué de 45 min : pas rattrapé, TikTok + Insta reportés ENSEMBLE au prochain créneau de Clips 1, l'étape le dit",
                     len(rp) == 2 and len(hr) == 1 and all(x["etat"] == "en_attente" for x in rp) and all(ecart_au_creneau(h) <= 15 for h in hr)
                     and all("manqué" in x["etapes"][-1]["message"] and "reportée au" in x["etapes"][-1]["message"] for x in rp),
                     [(x["etat"], x["quand"], [e["message"] for e in x["etapes"]]) for x in rp])
            # le bouton « Reporter » du calendrier : les deux ensemble, au créneau libre suivant ; pas deux groupes à la fois
            s, rep = await post("/api/publications/reporter", {"ids": ids_pr})
            q2 = {x["quand"] for x in rep.get("publications", [])} if s == 200 else set()
            verifier("Reporter (calendrier) : TikTok + Insta ensemble, au créneau libre suivant de leur groupe",
                     s == 200 and len(q2) == 1 and rep["quand"] in q2 and bool(rp) and rep["quand"] > rp[0]["quand"], (s, rep))
            s, pc2 = await post("/api/publications", {"compte_id": c2["id"], "video": "dossier:ghi.mp4", "legende": "x",
                                                      "quand": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            s, mele = await post("/api/publications/reporter", {"ids": [ids_pr[0], pc2["id"]]})
            verifier("Reporter : refusé pour deux groupes à la fois", s == 400, (s, mele))
            await post(f"/api/publications/{pc2['id']}/annuler", {})
            # un envoi À LA MAIN en retard part quand même (son rythme : un compte toutes les 30 min, jamais reporté)
            _, c3 = await post("/api/comptes", {"plateforme": "tiktok", "identifiant": "ma_page2.0", "udid": udid,
                                                "groupe": "Clips 2"})   # connu du faux TikTok
            s, envm = await post("/api/envois", {"video": "dossier:ghi.mp4", "comptes": [c3["id"]], "debut": passe,
                                                 "legende": "Envoi à la main en retard"})
            pm = (envm.get("publications") or [{}])[0]
            xm = await attendre(lambda: fini(pm["id"]), 120, 1) if pm.get("id") else None
            verifier("envoi à la main en retard : il part (jamais reporté)", xm and xm["etat"] == "publie" and xm["quand"] == passe
                     and not any("reportée" in e["message"] for e in xm["etapes"]), xm and (xm["etat"], xm["quand"], xm["erreur"]))
            await post(f"/api/comptes/{c3['id']}", {"actif": False})
            verifier("programmé une seule fois (les passages suivants ne doublent rien)", len(d2["publications"]) == 2, d2["publications"])
            if pr:   # le calendrier : la vidéo, à son heure (reportée plus haut : on relit son heure), une fois pour le groupe
                _, p_actuelle = await get(f"/api/publications/{pr[0]['id']}")
                jour = dt.datetime.fromisoformat(p_actuelle["quand"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris")).date().isoformat()
                s, cal = await get(f"/api/calendrier?debut={jour}&jours=1")
                ent = [e for e in cal.get("entrees", []) if e["video"] == "dossier:Clips 1/rem.mp4"]
                grp = {g["nom"]: g["decalage_min"] for p_ in cal.get("projets", []) for g in p_["groupes"]}
                verifier("calendrier : la vidéo du groupe à son heure, une entrée pour son groupe (TikTok + Insta), prévue ; groupes décalés",
                         s == 200 and len(ent) == 1 and ent[0]["groupe"] == "Clips 1" and len(ent[0]["comptes"]) == 2 and ent[0]["etat"] == "prevue"
                         and grp.get("Clips 1") == 0 and grp.get("Clips 2") == 90 and cal.get("creneaux") == ["09:00", "12:00", "15:00", "18:00", "21:00"],
                         (s, ent, grp))
                async with h.get(f"{base}/calendrier") as r:
                    verifier("page du calendrier servie", r.status == 200 and "calendrier.js" in await r.text())
            for x in pr:
                await post(f"/api/publications/{x['id']}/annuler", {})
            s, dest = await get("/api/destinations?video=dossier:abc.mp4")
            noms = [g["nom"] for g in dest.get("groupes", [])]
            igd = next((x for g in dest.get("groupes", []) for x in g["comptes"] if x["plateforme"] == "instagram"), {})
            verifier("destinations : les comptes du projet, groupés (Clips 1 = TikTok + Insta, Clips 2)",
                     s == 200 and noms == ["Clips 1", "Clips 2"] and len(dest["groupes"][0]["comptes"]) == 2, dest)
            verifier("destinations : Insta proposé (recette écrite le 04/10/2026)", igd.get("recette") is True, igd)
            demain = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            s, envig = await post("/api/envois", {"video": "dossier:abc.mp4", "comptes": [c["id"], ig["id"]], "debut": demain,
                                                  "repetition": True})
            verifier("envoi : TikTok + Insta d'un même groupe acceptés", s == 200 and len(envig.get("publications", [])) == 2, envig)
            for x in envig.get("publications", []):
                await post(f"/api/publications/{x['id']}/annuler", {})
            s, refus = await post("/api/envois", {"video": "dossier:def.mp4", "comptes": [c["id"]], "debut": demain})
            verifier("envoi : une vidéo pas validée est refusée", s == 400, refus)
            s, env = await post("/api/envois", {"video": "dossier:abc.mp4", "comptes": [c["id"], c2["id"]],
                                                "ecart_min": 30, "repetition": True, "debut": demain, "legende": "envoi groupé"})
            q = sorted(x["quand"] for x in env.get("publications", []))
            ecart = (dt.datetime.fromisoformat(q[1].replace("Z", "+00:00")) - dt.datetime.fromisoformat(q[0].replace("Z", "+00:00"))) if len(q) == 2 else None
            verifier("envoi : un groupe toutes les 30 min", s == 200 and ecart == dt.timedelta(minutes=30), (s, env))
            s, dest = await get("/api/destinations?video=dossier:abc.mp4")
            verifier("destinations : la relecture voit les envois de la vidéo",
                     sum(1 for x in dest["publications"] if x["etat"] == "en_attente") >= 2, dest["publications"][:3])
            for x in env.get("publications", []):
                await post(f"/api/publications/{x['id']}/annuler", {})

            # Instagram, sur une autre vidéo : ma.page.ig2 est actif (il contient ma.page.ig), galerie en
            # sélection multiple, champ de légende caché sous le mode « Légende », lien lu en le collant dans la recherche
            modifier_iphone(ig_brouillon_coupe=True)   # une création Instagram coupée net la fois d'avant
            s, pi = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4",
                                                     "legende": "Le stock d'Insta 👀\n#vinted", "repetition": True})
            xi = await attendre(lambda: fini(pi["id"]), 120, 1)
            ip = lire_iphone()
            verifier("Instagram, répétition : parcours complet sans publier, sans brouillon",
                     xi and xi["etat"] == "repete" and not ip["ig_pubs"].get("ma.page.ig") and ip["ig_brouillons"] == 0,
                     xi and (xi["etat"], xi["erreur"], [e["message"] for e in xi["etapes"]]))
            verifier("Instagram : compte choisi au nom exact (ma.page.ig2 était actif)", ip["ig_actif"] == "ma.page.ig")
            verifier("Instagram : brouillon d'une création coupée → « Commencer une nouvelle vidéo », jamais « Continuer » (vu le 05/10/2026)",
                     not ip.get("ig_brouillon_coupe") and not ip.get("ig_continuer_touche"))
            s, _ = await post(f"/api/publications/{pi['id']}/relancer", {"repetition": False})
            xi = await attendre(lambda: fini(pi["id"]), 120, 1)
            ip = lire_iphone()
            post_ig = (ip["ig_pubs"].get("ma.page.ig") or [{}])[0]
            verifier("Instagram, pour de vrai : publié sur le bon compte, légende relue identique (émoji, retour à la ligne)",
                     xi and xi["etat"] == "publie" and post_ig.get("desc") == "Le stock d'Insta 👀\n#vinted"
                     and (post_ig.get("video") or "").startswith("auto-"),
                     xi and (xi["etat"], xi["erreur"], post_ig, [e["message"] for e in xi["etapes"]][-6:]))
            verifier("Instagram : fenêtre « À propos de Reels » passée par « Partager » (vue à la 1re vraie publication, 04/10/2026)",
                     "ig_apropos:Partager" in ip["journal"], [j for j in ip["journal"] if j.startswith("ig_final") or j.startswith("ig_apropos")])
            xi = await attendre(lambda: avec_lien(pi["id"]), 30, 1) or xi
            await asyncio.sleep(1)
            verifier("Instagram : lien du reel retrouvé à part par Scrape Creators, à sa légende",
                     xi and xi["lien"] == f"https://www.instagram.com/reel/{post_ig.get('id')}/", xi and xi["lien"])
            verifier("Instagram : le téléphone reste sur Instagram jusqu'à la fin de l'envoi (sinon il se fige, vu le 05/10/2026)",
                     "ig_envoi:fini" in ip["journal"] and not any(j.startswith("ig_envoi:bloqué") for j in ip["journal"])
                     and not any(j.startswith("ig_explorer") for j in ip["journal"]), [j for j in ip["journal"] if j.startswith("ig_envoi")])
            verifier("Instagram : la pub « Edits » par-dessus l'éditeur fermée par sa poignée, puis « Suivant » (vue le 05/10/2026)",
                     "ig_promo:Fermer" in ip["journal"] and not ip.get("ig_appstore_touche"), [j for j in ip["journal"] if j.startswith("ig_promo") or j.startswith("ig_editeur")])
            verifier("Instagram : jamais touchés : audio suggéré, j'aime, contact, Ajouter un compte, App Store",
                     not (ip.get("ig_audio_touche") or ip.get("ig_like_touche") or ip.get("ig_contact_touche") or ip.get("ig_ajout_touche")
                          or ip.get("ig_appstore_touche")))
            verifier("Instagram : lien noté dans donnees/liens.csv", bool(xi) and f"ghi.mp4;{xi['lien']}" in liens_csv(), liens_csv())

            # ── le warm-up (chauffe.py, 07/10/2026, mots-clés de la niche demandés, 40 min par jour) ──────────
            async with h.get(f"{base}/warmup") as rw:
                verifier("page du warm-up servie", rw.status == 200 and "warmup.js" in await rw.text())
            s, wu = await post("/api/chauffes", {"comptes": [c["id"], ig["id"]], "mots": "vinted\nachat revente\n#resell",
                                                 "jours": 7, "minutes_jour": 40})
            ids_wu = {x["identifiant"]: x["id"] for x in wu.get("chauffes", [])}
            verifier("warm-up : TikTok + Insta mis en warm-up, mots-clés de la niche gardés (sans #)",
                     s == 200 and set(ids_wu) == {"ma_page", "ma.page.ig"} and wu["chauffes"][0]["mots"] == "vinted\nachat revente\nresell", wu)
            s1, refus1 = await post("/api/chauffes", {"comptes": [c["id"]], "mots": "vinted"})
            s2, refus2 = await post("/api/chauffes", {"comptes": [c2["id"]], "mots": " \n "})
            verifier("warm-up : refusé pour un compte déjà en warm-up, ou sans mot-clé", s1 == 409 and s2 == 400, (refus1, refus2))
            il_y_a_3j = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:      # au 4e jour : likes et abonnements permis
                db.execute("update chauffes set debut = ? where etat = 'en_cours'", (il_y_a_3j,))
            _, lw = await get("/api/chauffes")
            ch_tt = next((x for x in lw.get("chauffes", []) if x["id"] == ids_wu.get("ma_page")), {})
            verifier("warm-up : 40 min par jour = 3 séances à des heures tirées entre 9 h et 23 h, dose pleine au 4e jour",
                     len(ch_tt.get("plan", [])) == 3 and ch_tt["aujourdhui"]["cible"] == 40 and ch_tt["jour"] == 4, ch_tt.get("plan"))
            s, bl = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:ghi.mp4", "legende": "x"})
            verifier("warm-up : publication refusée sur un compte en warm-up (publications bloquées)",
                     s == 409 and "warm-up" in (bl.get("erreur") or ""), bl)

            async def lancer_seance(cid, minutes):
                for _ in range(90):               # une séance automatique peut occuper le téléphone : on attend qu'il se libère
                    s_, _ = await post(f"/api/chauffes/{cid}/seance", {"minutes": minutes})
                    if s_ == 200:
                        return True
                    await asyncio.sleep(1)
                return False

            async def seance_finie(cid, apres=0):
                _, l_ = await get("/api/chauffes")
                ch = next((x for x in l_.get("chauffes", []) if x["id"] == cid), None)
                se = ch and ch["seances"] and ch["seances"][0]
                return (se, ch) if se and se["id"] > apres and se["etat"] != "en_cours" else None

            async def derniere_seance(cid):
                _, l_ = await get("/api/chauffes")
                ch = next((x for x in l_.get("chauffes", []) if x["id"] == cid), None)
                return ch["seances"][0]["id"] if ch and ch["seances"] else 0

            avant = await derniere_seance(ids_wu.get("ma_page"))
            fin_tt = await attendre(lambda: seance_finie(ids_wu["ma_page"], avant), 120, 1) \
                if await lancer_seance(ids_wu.get("ma_page"), 40) else None
            st, ch_tt = fin_tt or (None, {})
            ip = lire_iphone()
            verifier("warm-up TikTok : séance faite (mot-clé de la niche cherché, onglet Vidéos, vidéos regardées, puis « Pour toi »)",
                     st and st["etat"] == "faite" and st["recherches"] >= 1 and st["vues"] >= 3 and ip["tt_recherches"]
                     and set(ip["tt_recherches"]) <= {"vinted", "achat revente", "resell"} and ip["tt_vues_niche"] >= 1 and ip["tt_fil_vues"] >= 1,
                     (st, ip["tt_recherches"], ip["tt_vues_niche"], ip["tt_fil_vues"]))
            verifier("warm-up TikTok : likes (cœur devenu rouge) et abonnements (« + » disparu) comptés, jamais sur le fil",
                     ch_tt and ch_tt["totaux"]["likes"] == len(ip["tt_aimes"]) >= 1 and ch_tt["totaux"]["abonnements"] == len(ip["tt_suivis"]) >= 1
                     and ip["tt_fil_likes"] == 0, (ch_tt and ch_tt["totaux"], ip["tt_aimes"], ip["tt_suivis"], ip["tt_fil_likes"]))
            verifier("warm-up TikTok : jamais touchés : la publicité des résultats, le bouton LIVE, le cœur, la photo du compte",
                     not [j for j in ip["journal"] if j.startswith("piège:")], [j for j in ip["journal"] if j.startswith("piège:")])
            verifier("warm-up TikTok : la fenêtre glissée sur le fil fermée (« Pas maintenant »)",
                     ip["tt_pop_vue"] and "tt_pop:Pas maintenant" in ip["journal"], (ip["tt_pop_vue"], [j for j in ip["journal"] if "tt_pop" in j]))
            if st:
                _, jw = await get(f"/api/seances/{st['id']}")
                cap = next((l_["capture"] for l_ in jw.get("journal", []) if l_["capture"]), None)
                async with h.get(f"{base}/api/seances/{st['id']}/captures/{cap}") as rc:
                    ok_cap = rc.status == 200
                verifier("warm-up : journal de la séance (recherche, fin) avec ses captures",
                         any(l_["message"].startswith("Recherche « ") for l_ in jw.get("journal", []))
                         and any(l_["message"].startswith("Fin de la séance") for l_ in jw.get("journal", [])) and ok_cap,
                         [l_["message"] for l_ in jw.get("journal", [])][:12])

            avant = await derniere_seance(ids_wu.get("ma.page.ig"))
            fin_ig = await attendre(lambda: seance_finie(ids_wu["ma.page.ig"], avant), 120, 1) \
                if await lancer_seance(ids_wu.get("ma.page.ig"), 40) else None
            st, ch_ig = fin_ig or (None, {})
            ip = lire_iphone()
            verifier("warm-up Instagram : séance faite (Explorer, mot-clé de la niche, reels des résultats, puis onglet Reels)",
                     st and st["etat"] == "faite" and ip["ig_recherches"] and set(ip["ig_recherches"]) <= {"vinted", "achat revente", "resell"}
                     and ip["ig_vues"] >= 3, (st, ip["ig_recherches"], ip["ig_vues"]))
            verifier("warm-up Instagram : likes et abonnements comptés ; jamais une pub likée, un like retiré ni un profil ouvert",
                     ch_ig and ch_ig["totaux"]["likes"] == len(ip["ig_aimes"]) >= 1 and ch_ig["totaux"]["abonnements"] == len(ip["ig_suivis"]) >= 1
                     and not ip["ig_unlike"] and not [j for j in ip["journal"] if j.startswith("piège:")],
                     (ch_ig and ch_ig["totaux"], ip["ig_aimes"], ip["ig_suivis"], [j for j in ip["journal"] if j.startswith("piège:")]))

            # une publication qui arrive coupe la séance (2 min avant) et passe
            avant = await derniere_seance(ids_wu.get("ma_page"))
            lancee = await lancer_seance(ids_wu.get("ma_page"), 30)
            await asyncio.sleep(4)
            bientot = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
            s, pc = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4", "legende": "x",
                                                     "repetition": True, "quand": bientot})
            fin_c = await attendre(lambda: seance_finie(ids_wu["ma_page"], avant), 60, 1) if lancee else None
            xp = await attendre(lambda: fini(pc["id"]), 120, 1) if s == 200 else None
            se = (fin_c or (None, None))[0]
            verifier("warm-up : une publication qui arrive coupe la séance et passe (la publication d'abord, toujours)",
                     se and se["etat"] == "coupee" and "publication" in se["erreur"] and xp and xp["etat"] == "repete",
                     (se, xp and xp["etat"]))

            for cid in ids_wu.values():
                await post(f"/api/chauffes/{cid}/arreter", {})
            _, lw = await get("/api/chauffes")
            s, pl = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:ghi.mp4", "legende": "x",
                                                     "quand": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            verifier("warm-up arrêté : plus en cours, le compte peut de nouveau publier",
                     all(x["etat"] == "arrete" for x in lw.get("chauffes", []) if x["id"] in ids_wu.values()) and s == 200, (s, pl))
            if s == 200:
                await post(f"/api/publications/{pl['id']}/annuler", {})
            s, _ = await post(f"/api/chauffes/{ids_wu.get('ma_page')}/retirer", {})
            _, lw = await get("/api/chauffes")
            verifier("warm-up fini retiré de la liste (séances comprises)",
                     s == 200 and ids_wu.get("ma_page") not in [x["id"] for x in lw.get("chauffes", [])], (s, [x["id"] for x in lw.get("chauffes", [])]))

            modifier_iphone(branche=False)

            async def debranche():
                _, e = await get("/api/etat")
                t = e["parc"]["telephones"][0]
                return t if not t["branche"] else None

            t = await attendre(debranche, 15)
            verifier("débranchement vu, avec la consigne", t and t["etapes"][0]["etat"] == "ko" and "Rebranche" in t["etapes"][0]["aide"], t)
            modifier_iphone(branche=True)
            verifier("rebranché : de nouveau prêt", await attendre(pret, 60))
    finally:
        service.terminate()
        try:
            service.wait(10)
        except subprocess.TimeoutExpired:
            service.kill()
        await runner.cleanup()
        subprocess.run(["pkill", "-f", str(ICI / "faux_iphone.py")], check=False)
        ok = sum(1 for _, v in RESULTATS if v)
        print(f"\n{ok}/{len(RESULTATS)} passés. Journal du service : {tmp / 'service.log'}")
        sys.exit(0 if ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    asyncio.run(principal())
