"""demo.py : l'interface, branchée sur le faux iPhone et un dossier de vidéos d'exemple, pour voir et essayer sans
téléphone : http://127.0.0.1:4330/telephones/ (Ctrl-C pour arrêter).

  python tests/demo.py        (le Python doit avoir aiohttp et pillow)
  python tests/demo.py --calendrier   (avec des comptes et des publications prévues : http://127.0.0.1:4330/telephones/calendrier)
  python tests/demo.py --warmup       (des comptes en warm-up, avec quelques jours de séances : http://127.0.0.1:4330/telephones/warmup)
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from essai_local import ICI, RACINE, port_libre, preparer_signature  # noqa: E402


async def principal():
    tmp = Path(tempfile.mkdtemp(prefix="demo-telephones-"))
    env = dict(os.environ, FAUX_IOS_DIR=str(tmp / "iphone"), FAUX_PYTHON=sys.executable,
               TELEPHONES_IOS=str(ICI / "faux-ios"), TELEPHONES_PMD3=str(ICI / "faux-pymobiledevice3"), TELEPHONES_DONNEES=str(tmp / "donnees"),
               TELEPHONES_PORT="4330", TELEPHONES_VIDEOS=str(tmp / "videos"), TELEPHONES_PORT_AGENT=str(port_libre()),
               TELEPHONES_PORT_FLUX=str(port_libre()))
    os.chmod(ICI / "faux-ios", 0o755)
    os.chmod(ICI / "faux-pymobiledevice3", 0o755)
    preparer_signature(tmp, env)
    for nom in ("abc.mp4", "ghi.mp4", "Groupe 1/exemple.mp4"):          # des vidéos d'exemple
        (tmp / "videos" / nom).parent.mkdir(parents=True, exist_ok=True)
        (tmp / "videos" / nom).write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(50_000))
    (tmp / "videos" / "Groupe 1" / "exemple.txt").write_text("Une légende d'exemple 👀 #exemple", encoding="utf-8")
    subprocess.run([sys.executable, str(ICI / "faux_iphone.py"), "--reinitialiser"], env=env, check=True)
    service = subprocess.Popen([sys.executable, str(RACINE / "service" / "telephones.py")], env=env)
    print("Onglet Téléphones (faux iPhone) : http://127.0.0.1:4330/telephones/", flush=True)
    if "--calendrier" in sys.argv:
        await semer_calendrier()
    if "--warmup" in sys.argv:
        await semer_warmup(tmp)
    try:
        while service.poll() is None:
            await asyncio.sleep(1)
    finally:
        service.terminate()
        subprocess.run(["pkill", "-f", str(ICI / "faux_iphone.py")], check=False)


async def semer_calendrier():
    """Deux groupes de comptes et quelques publications prévues dans la semaine, pour voir le calendrier."""
    import datetime as dt
    import aiohttp
    from zoneinfo import ZoneInfo
    base = "http://127.0.0.1:4330/telephones/api"
    async with aiohttp.ClientSession() as h:
        for _ in range(60):
            try:
                async with h.get(base + "/etat") as r:
                    if r.status == 200:
                        break
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(1)
        async with h.get(base + "/etat") as r:
            udid = ((await r.json())["parc"]["telephones"] or [{}])[0].get("udid")
        ids = {}
        for plat, ident, groupe in (("tiktok", "ma_page", "Compte 1"), ("instagram", "ma.page.ig", "Compte 1"),
                                    ("tiktok", "ma_page2.0", "Compte 2"), ("instagram", "ma.page2", "Compte 2")):
            async with h.post(base + "/comptes", json={"plateforme": plat, "identifiant": ident, "udid": udid,
                                                        "groupe": groupe}) as r:
                ids[ident] = (await r.json()).get("id")
        paris = ZoneInfo("Europe/Paris")
        jour = dt.datetime.now(paris).date()
        prevues = [(1, "12:07", ("ma_page2.0", "ma.page2"), "abc"), (1, "15:11", ("ma_page", "ma.page.ig"), "ghi"),
                   (2, "09:04", ("ma_page", "ma.page.ig"), "abc"), (2, "18:52", ("ma_page2.0", "ma.page2"), "ghi")]
        for j, hhmm, comptes, video in prevues:
            d = jour + dt.timedelta(days=j)
            h_, m_ = map(int, hhmm.split(":"))
            quand = dt.datetime(d.year, d.month, d.day, h_, m_, tzinfo=paris).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for c in comptes:
                await h.post(base + "/publications", json={"compte_id": ids[c], "video": f"dossier:{video}.mp4",
                                                            "legende": "démo", "quand": quand, "repetition": False})
    print("Calendrier : http://127.0.0.1:4330/telephones/calendrier", flush=True)


async def semer_warmup(tmp):
    """Trois comptes en warm-up : deux au 3e jour (séances faites hier et ce matin), un terminé."""
    import datetime as dt
    import random
    import sqlite3
    import aiohttp
    base = "http://127.0.0.1:4330/telephones/api"
    async with aiohttp.ClientSession() as h:
        for _ in range(60):
            try:
                async with h.get(base + "/etat") as r:
                    if r.status == 200 and (await r.json())["parc"]["telephones"]:
                        break
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(1)
        async with h.get(base + "/etat") as r:
            udid = (await r.json())["parc"]["telephones"][0]["udid"]
        async with h.get(base + "/comptes") as r:
            ids = {c["identifiant"]: c["id"] for c in await r.json()}
        for plat, ident, groupe in (("tiktok", "nouveau.clips", ""), ("instagram", "nouveau.clips.ig", ""), ("tiktok", "ma_page", "Compte 1")):
            if ident not in ids:
                async with h.post(base + "/comptes", json={"plateforme": plat, "identifiant": ident, "udid": udid,
                                                            "groupe": groupe}) as r:
                    ids[ident] = (await r.json()).get("id")
        async with h.post(base + "/chauffes", json={"comptes": [ids["nouveau.clips"], ids["nouveau.clips.ig"]], "jours": 7, "minutes_jour": 40,
                                                     "mots": "vinted\nachat revente\nresell\nfriperie"}) as r:
            en_cours = [c["id"] for c in (await r.json())["chauffes"]]
        async with h.post(base + "/chauffes", json={"comptes": [ids["ma_page"]], "jours": 5, "minutes_jour": 20, "bloque": False,
                                                     "mots": "business en ligne\nentrepreneur"}) as r:
            fini = (await r.json())["chauffes"][0]["id"]
    from zoneinfo import ZoneInfo
    paris = ZoneInfo("Europe/Paris")
    maintenant = dt.datetime.now(dt.timezone.utc)
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
    with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:
        db.execute(f"update chauffes set debut = ? where id in ({', '.join('?' * len(en_cours))})", (iso(maintenant - dt.timedelta(days=2, hours=3)), *en_cours))
        db.execute("update chauffes set debut = ?, fin = ?, etat = 'termine' where id = ?",
                   (iso(maintenant - dt.timedelta(days=7)), iso(maintenant - dt.timedelta(days=2)), fini))
        hasard = random.Random(7)
        for cid, jours in [(c, (2, 1, 0)) for c in en_cours] + [(fini, (6, 5, 4, 3, 2))]:
            for j in jours:
                for k in range(3 if j else 1):
                    debut = maintenant - dt.timedelta(days=j, hours=10 - 4 * k)
                    vues = hasard.randint(25, 60)
                    likes, abos = (0, 0) if j == 2 and cid in en_cours else (hasard.randint(1, 4), hasard.randint(0, 1))
                    db.execute("""insert into seances (chauffe_id, rang, debut, fin, etat, minutes, minutes_faites, vues, likes, abonnements,
                                  recherches, mots, journal) values (?, ?, ?, ?, 'faite', 13, ?, ?, ?, ?, 2, 'vinted, achat revente', ?)""",
                               (cid, k, iso(debut), iso(debut + dt.timedelta(minutes=13)), round(hasard.uniform(11, 14), 1), vues, likes, abos,
                                f"{debut.astimezone(paris):%H:%M:%S} Ouverture\n{debut.astimezone(paris):%H:%M:%S} Recherche « vinted » : 4 vidéo(s) à l'écran\n"
                                f"{debut.astimezone(paris):%H:%M:%S} Fin de la séance : {vues} vidéo(s) vue(s)\n"))
    print("Warm-up : http://127.0.0.1:4330/telephones/warmup", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
