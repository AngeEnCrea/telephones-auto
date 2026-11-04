"""essai_partage.py : deux projets sur les mêmes iPhone sans se gêner (partage.py, 25/10/2026, un autre projet à côté du projet principal).

uv run --with aiohttp==3.14.3 --with pillow==12.3.0 --with tzdata python tests/essai_partage.py   (quelques secondes)"""
import datetime as dt
import pathlib
import random
import sys
import tempfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "service"))
import partage            # noqa: E402
import programmation      # noqa: E402
from stock import Stock   # noqa: E402

echecs = 0


def verifier(nom, ok, detail=""):
    global echecs
    print(("✓ " if ok else "✗ ") + nom + ("" if ok else f" — {detail}"))
    echecs += 0 if ok else 1


with tempfile.TemporaryDirectory() as tmp:
    st = Stock(pathlib.Path(tmp) / "t.db")
    A, B = "udid-A", "udid-B"
    # comme au 25/10/2026 : le projet principal d'abord (Comptes 1-5 sur A, 6-8 sur B), puis un autre projet sur les mêmes téléphones
    for i in range(1, 9):
        for p in ("tiktok", "instagram"):
            st.ajouter_compte(p, f"page{i}{p}", A if i <= 5 else B, projet="perso", groupe=f"Compte {i}")
    for p in ("tiktok", "instagram"):
        st.ajouter_compte(p, f"autre1{p}", A, projet="autre-projet", groupe="un autre projet 1")
        st.ajouter_compte(p, f"autre2{p}", B, projet="autre-projet", groupe="un autre projet 2")
    P = programmation.PARIS
    demain = (dt.datetime.now(P) + dt.timedelta(days=1)).date()
    a = lambda h, m: dt.datetime(demain.year, demain.month, demain.day, h, m, tzinfo=P).astimezone(dt.timezone.utc)  # noqa: E731

    verifier("le projet principal, arrivé le premier, garde sa grille (pas de créneaux à part)",
             all(partage.creneaux_groupe(st, "perso", f"Compte {i}") is None for i in range(1, 9)))
    grille_a = partage.grille_autres(st, {A}, "autre-projet")
    verifier("la grille du projet principal sur A : ses 5 groupes × 5 créneaux", len(grille_a) == 25, grille_a)
    d1, d2 = partage.creneaux_groupe(st, "autre-projet", "un autre projet 1"), partage.creneaux_groupe(st, "autre-projet", "un autre projet 2")
    hors = lambda cr, g: all(partage._distance(int(c[:2]) * 60 + int(c[3:]), g) >= partage.MARGE_MIN for c in cr)  # noqa: E731
    verifier("un autre projet 1 (sur A) a des créneaux, tous à ≥ 28 min de la grille du projet principal", bool(d1) and hors(d1, grille_a), d1)
    verifier("un autre projet 2 (sur B) aussi", bool(d2) and hors(d2, partage.grille_autres(st, {B}, "autre-projet")), d2)

    autre1 = [c for c in st.comptes_du_projet("autre-projet") if c["groupe"] == "un autre projet 1"]
    x = partage.ajuster(st, autre1, "autre-projet", a(9, 0), varier=False)
    xm = x.astimezone(P) if x else None
    verifier("un autre projet posé en pleine grille du projet principal (9 h) : poussé dans un trou",
             bool(x) and partage._distance(xm.hour * 60 + xm.minute, grille_a) >= partage.MARGE_MIN, x)
    ok = True
    for _ in range(300):
        c = random.choice(d1)
        z = partage.ajuster(st, autre1, "autre-projet", a(int(c[:2]), int(c[3:])))
        if z:
            zm = z.astimezone(P)
            ok &= partage._distance(zm.hour * 60 + zm.minute, grille_a) >= partage.MARGE_MIN
    verifier("300 tirages à ± 15 min sur les créneaux d'un autre projet 1 : jamais dans la grille du projet principal", ok)

    f1 = [c for c in st.comptes_du_projet("perso") if c["groupe"] == "Compte 1"][0]
    st.creer_publication(f1["id"], "dossier:x", "x", "", a(11, 10).strftime("%Y-%m-%dT%H:%M:%SZ"))
    y = partage.ajuster(st, autre1, "autre-projet", a(11, 14), varier=False)
    verifier("une vidéo du projet principal envoyée à la main à 11 h 10 sur A : un autre projet ne se pose pas à moins de 28 min",
             y is None or abs((y - a(11, 10)).total_seconds()) >= partage.MARGE_MIN * 60, y)
    f6 = [c for c in st.comptes_du_projet("perso") if c["groupe"] == "Compte 6"][0]
    st.creer_publication(f6["id"], "dossier:y", "y", "", a(14, 11).strftime("%Y-%m-%dT%H:%M:%SZ"))
    z = partage.ajuster(st, autre1, "autre-projet", a(14, 11), varier=False)
    verifier("une vidéo du projet principal sur l'AUTRE téléphone ne gêne pas un autre projet 1", z == a(14, 11), z)

    # les versions en essai d'un même créneau partent à la suite : pas d'attente de 30 min entre deux essais (25/10/2026)
    import json as json_
    from stock import maintenant
    ig = [c for c in st.comptes_du_projet("autre-projet") if c["groupe"] == "un autre projet 1" and c["plateforme"] == "instagram"][0]
    p0 = st.creer_publication(ig["id"], "dossier:a", "a", "", maintenant())
    st.maj_publication(p0["id"], etat="publie", fin=maintenant())
    normale = st.creer_publication(ig["id"], "dossier:b", "b", "", maintenant())
    verifier("une publication normale attend 30 min après la précédente du compte",
             all(x["id"] != normale["id"] for x in [st.prochaine(A)] if x), st.prochaine(A))
    st.maj_publication(normale["id"], etat="annule")
    essai = st.creer_publication(ig["id"], "dossier:c", "c", "", maintenant(), options=json_.dumps({"essai": True}))
    x = st.prochaine(A)
    verifier("un reel d'essai part tout de suite derrière", bool(x) and x["id"] == essai["id"], x)

print(f"\n{'tout bon' if not echecs else f'{echecs} échec(s)'}")
sys.exit(1 if echecs else 0)
