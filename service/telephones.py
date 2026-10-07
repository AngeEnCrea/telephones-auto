"""telephones.py : le service Téléphones. Il tient les iPhone branchés prêts à piloter (parc.py), joue la file des
publications et le warm-up (publication.py, chauffe.py), et sert l'interface et son API (serveur.py) :

  python service/telephones.py          puis http://127.0.0.1:4330/telephones/

Une seule instance à la fois : si le port est déjà pris, il s'arrête tout seul (on peut donc le relancer sans crainte,
par exemple toutes les 5 min depuis le Planificateur de tâches de Windows ou un LaunchAgent de macOS)."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

import journal  # noqa: E402
import lieux  # noqa: E402
import processus  # noqa: E402
import serveur  # noqa: E402
from parc import Parc  # noqa: E402
from publication import Publieur  # noqa: E402
from stock import Stock  # noqa: E402

log = logging.getLogger("service")


async def principal():
    journal.installer()
    processus.attacher_au_service()
    lieux.DONNEES.mkdir(parents=True, exist_ok=True)
    lieux.VIDEOS.mkdir(parents=True, exist_ok=True)
    log.info("démarrage (go-ios : %s, données : %s, vidéos : %s)", lieux.IOS, lieux.DONNEES, lieux.VIDEOS)
    http = aiohttp.ClientSession()
    stock = Stock()
    parc = Parc(http)
    publieur = Publieur(parc, stock, http)
    runner = web.AppRunner(serveur.creer(parc, stock, publieur, http), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, lieux.HOTE, lieux.PORT).start()
    except OSError as e:
        log.info("port %s déjà pris (%s) : une autre instance tourne, on s'arrête", lieux.PORT, e)
        await http.close()
        return
    log.info("interface : http://%s:%s%s/", lieux.HOTE, lieux.PORT, lieux.PREFIXE)
    taches = [asyncio.create_task(parc.boucle()), asyncio.create_task(publieur.boucle())]
    try:
        await asyncio.gather(*taches)
    finally:
        for t in taches:
            t.cancel()
        await parc.arreter()
        await runner.cleanup()
        await http.close()


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
