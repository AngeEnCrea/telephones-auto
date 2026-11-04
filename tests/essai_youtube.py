"""essai_youtube.py : les règles de la recette YT Studio (recettes/youtube.py, 25/10/2026) sans iPhone.

uv run --with aiohttp==3.14.3 --with pillow==12.3.0 --with tzdata python tests/essai_youtube.py   (une seconde)"""
import asyncio
import datetime as dt
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "service"))
from recettes import PRETES, youtube          # noqa: E402
from recettes.base import ErreurPublication   # noqa: E402

echecs = 0


def verifier(nom, ok, detail=""):
    global echecs
    print(("✓ " if ok else "✗ ") + nom + ("" if ok else f" — {detail}"))
    echecs += 0 if ok else 1


P = youtube.PARIS
maintenant = dt.datetime(2026, 10, 25, 16, 10, tzinfo=P)
verifier("date d'une case du sélecteur", youtube.moment_de("Vidéo, dix-huit secondes, 25 octobre, 15:37", maintenant)
         == dt.datetime(2026, 10, 25, 15, 37, tzinfo=P))
verifier("une date de décembre vue en janvier = l'année d'avant",
         youtube.moment_de("Vidéo, neuf secondes, 31 décembre, 23:10", dt.datetime(2027, 1, 1, 0, 5, tzinfo=P)).year == 2026)
verifier("label illisible → None", youtube.moment_de("Photo", maintenant) is None)
verifier("titre = 1re ligne avec ses hashtags, 100 caractères",
         youtube.titre_de("The beach wasn't prepared 🇫🇷 #aura\nsuite", "x") == "The beach wasn't prepared 🇫🇷 #aura"
         and len(youtube.titre_de("a" * 300)) == 100 and youtube.titre_de("", "052-v1") == "052-v1")
verifier("la recette YouTube est prête, l'app est YT Studio", PRETES["youtube"] and youtube.BUNDLE == "com.google.ios.ytcreator")


class FauxAgent:
    def __init__(self, cases):
        self.cases, self.touches = cases, []

    async def chercher(self, using, valeur):
        return list(self.cases) if "PXGGridLayout-Info" in valeur else []

    async def rect(self, eid):
        return self.cases[eid][1]

    async def attribut(self, eid, nom):
        return self.cases[eid][0]

    async def toucher(self, x, y):
        self.touches.append((x, y))


class FauxRobot:
    def __init__(self, cases):
        self.a, self.etapes = FauxAgent(cases), []

    async def etape(self, m):
        self.etapes.append(m)


def case(label, x, y):
    return (label, {"x": x, "y": y, "width": 129, "height": 129})


async def essayer(cases):
    r = FauxRobot(cases)
    try:
        await youtube.choisir_video(r, maintenant)
        return r, None
    except ErreurPublication as e:
        return r, str(e)


r, err = asyncio.run(essayer({"b": case("Vidéo, neuf secondes, 25 octobre, 12:15", 130, 317),
                              "a": case("Vidéo, dix-huit secondes, 25 octobre, 16:02", 0, 317),
                              "c": case("Vidéo, vingt secondes, 24 octobre, 21:00", 0, 447)}))
verifier("la case en haut à gauche, rangée il y a 8 min : touchée", err is None and r.a.touches == [(64.5, 381.5)], (err, r.a.touches))
r, err = asyncio.run(essayer({"a": case("Vidéo, dix-huit secondes, 25 octobre, 15:20", 0, 317)}))
verifier("la plus récente a 50 min : rien n'est choisi", err and "rien n'est choisi" in err and not r.a.touches, err)
r, err = asyncio.run(essayer({"a": case("Photo, 25 octobre, 16:05", 0, 317)}))
verifier("la plus récente est une photo : rien n'est choisi", err and not r.a.touches, err)

print(f"\n{'tout bon' if not echecs else f'{echecs} échec(s)'}")
sys.exit(1 if echecs else 0)
