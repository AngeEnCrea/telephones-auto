"""journal.py : le journal du service. Dans le fichier du réglage « journal » (tourne à 5 Mo), sinon la console ; les dernières
lignes restent aussi en mémoire pour l'onglet Journal de l'interface."""
import collections
import logging
import logging.handlers
import sys

import lieux

DERNIERES = collections.deque(maxlen=500)


class _Memoire(logging.Handler):
    def emit(self, r):
        DERNIERES.append({"t": r.created, "niveau": r.levelname, "qui": r.name, "msg": r.getMessage()})


def installer():
    racine = logging.getLogger()
    racine.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s", "%Y-%m-%d %H:%M:%S")
    if lieux.JOURNAL:
        h = logging.handlers.RotatingFileHandler(lieux.JOURNAL, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    else:
        h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmt)
    racine.addHandler(h)
    racine.addHandler(_Memoire())
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
