"""essai_projets.py : le projet principal et un autre projet séparés dans les vues, le hub et Discord (26/10/2026 : les comptes d'un autre projet s'étaient
mêlés aux vues des pages du projet principal).

uv run --with aiohttp==3.14.3 --with pillow==12.3.0 --with tzdata python tests/essai_projets.py   (une seconde)"""
import pathlib
import sys
import tempfile
import time

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "service"))
import sante              # noqa: E402
from stock import Stock   # noqa: E402

echecs = 0


def verifier(nom, ok, detail=""):
    global echecs
    print(("✓ " if ok else "✗ ") + nom + ("" if ok else f" — {detail}"))
    echecs += 0 if ok else 1


with tempfile.TemporaryDirectory() as tmp:
    st = Stock(pathlib.Path(tmp) / "t.db")
    principal = st.ajouter_compte("tiktok", "mapageclip", "A", projet="perso", groupe="Compte 1")
    neuf = st.ajouter_compte("instagram", "pageneuve", "A")                       # sans projet : un compte clip neuf
    autre = st.ajouter_compte("instagram", "autrepage", "A", projet="autre-projet", groupe="un autre projet 1")
    c = lambda x: st.compte(x["id"])  # noqa: E731
    verifier("le projet principal par défaut : son compte et le compte neuf, pas un autre projet",
             sante.du_projet(st, c(principal)) and sante.du_projet(st, c(neuf)) and not sante.du_projet(st, c(autre)))
    verifier("un autre projet choisi : seulement son compte",
             sante.du_projet(st, c(autre), "autre-projet") and not sante.du_projet(st, c(principal), "autre-projet")
             and not sante.du_projet(st, c(neuf), "autre-projet"))
    jour = sante.jour_paris()
    maintenant = time.time()
    st.noter_releve(principal["id"], jour, 100, [{"id": "f1", "vues": 1000, "ts": maintenant - 3600, "lien": "", "desc": ""}])
    st.noter_releve(neuf["id"], jour, 10, [{"id": "n1", "vues": 50, "ts": maintenant - 3600, "lien": "", "desc": ""}])
    st.noter_releve(autre["id"], jour, 50000, [{"id": "d1", "vues": 1_000_000, "ts": maintenant - 3600, "lien": "", "desc": ""}])
    vf = sante.vues_par_jour(st, jour).get(jour, {})
    vd = sante.vues_par_jour(st, jour, "autre-projet").get(jour, {})
    verifier("vues des pages du projet principal : 1 050, sans le million d'un autre projet", vf.get("tiktok", 0) + vf.get("instagram", 0) == 1050, vf)
    verifier("vues d'un autre projet à part : 1 000 000", vd.get("tiktok", 0) + vd.get("instagram", 0) == 1_000_000, vd)

print(f"\n{'tout bon' if not echecs else f'{echecs} échec(s)'}")
sys.exit(1 if echecs else 0)
