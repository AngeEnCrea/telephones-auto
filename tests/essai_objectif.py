"""essai_objectif.py : l'objectif de publications par jour d'un projet (programmation.doses, 03/11/2026, Note : « on post
100 fois sur les comptes qu'on a déjà », puis « dès que les autres ont atteint leur max […] tu réorganises »), les
créneaux pris dans l'ordre du réglage, l'écart fixe entre groupes, « Compte 10 » après « Compte 9 », la légende TikTok.

uv run --with aiohttp==3.14.3 --with pillow==12.3.0 --with tzdata python tests/essai_objectif.py   (quelques secondes)"""
import datetime as dt
import pathlib
import sys
import tempfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "service"))
import programmation      # noqa: E402
from stock import Stock   # noqa: E402

echecs = 0


def verifier(nom, ok, detail=""):
    global echecs
    print(("✓ " if ok else "✗ ") + nom + ("" if ok else f" — {detail}"))
    echecs += 0 if ok else 1


with tempfile.TemporaryDirectory() as tmp:
    st = Stock(pathlib.Path(tmp) / "t.db")
    F = "perso"
    for i in range(1, 9):
        for p in ("tiktok", "instagram"):
            st.ajouter_compte(p, f"page{i}{p}", "udid-A" if i <= 5 else "udid-B", projet=F, groupe=f"Compte {i}")
        st.poser_page(F, f"Compte {i}", "grossiste" if i == 3 else "", "2026-10-15")
    st.poser_reglage("creneaux", "09:00,12:00,15:00,18:00,21:00,19:30,16:30")
    jour = dt.date(2026, 11, 3)
    total = lambda d: sum(v * 2 for v in d.values())   # noqa: E731

    d = programmation.doses(st, F, jour)
    verifier("sans objectif : 5 par page, comme avant", set(d.values()) == {5}, d)

    st.poser_reglage(f"objectif:{F}", 100)
    d = programmation.doses(st, F, jour)
    verifier("objectif 100 sur 16 comptes : 100 publications, 6 ou 7 par page", total(d) == 100 and set(d.values()) == {6, 7}, d)
    verifier("les 7 vont aux pages sans niche", d["Compte 3"] == 6, d)
    lendemain = programmation.doses(st, F, jour + dt.timedelta(days=1))
    verifier("le tour des pages renforcées change chaque jour",
             {g for g, v in d.items() if v == 7} != {g for g, v in lendemain.items() if v == 7}, lendemain)

    # deux pages neuves qui montent en charge à partir du 04/11 : les renforts des autres baissent, le total reste 100
    for i in (9, 10):
        for p in ("tiktok", "instagram"):
            st.ajouter_compte(p, f"page{i}{p}", "udid-B", projet=F, groupe=f"Compte {i}")
        st.poser_page(F, f"Compte {i}", "", "2026-11-04")
    suite = [programmation.doses(st, F, jour + dt.timedelta(days=j)) for j in range(8)]
    verifier("Comptes 9 et 10 : 0 le 03/11, puis 1, 2, 3, 4, 5", [x["Compte 9"] for x in suite[:6]] == [0, 1, 2, 3, 4, 5],
             [x["Compte 9"] for x in suite])
    verifier("le total reste à 100 pendant la montée en charge", all(total(x) == 100 for x in suite), [total(x) for x in suite])
    verifier("montée finie : 20 comptes à 5, plus aucun renfort", set(suite[6].values()) == {5}, suite[6])

    # une page remise sans jour 1 (montée en charge pas commencée)
    st.poser_page(F, "Compte 10", "", None)
    verifier("une page sans jour 1 sort de l'objectif", "Compte 10" not in programmation.doses(st, F, jour))

    verifier("créneaux d'une page à 6 : les 6 premiers du réglage, dans l'ordre des heures",
             programmation.creneaux_du_jour(st, 6) == [(9, 0), (12, 0), (15, 0), (18, 0), (19, 30), (21, 0)],
             programmation.creneaux_du_jour(st, 6))
    verifier("créneaux d'une page à 1 : 9 h", programmation.creneaux_du_jour(st, 1) == [(9, 0)])

    st.poser_reglage("ecart_groupes", 19)
    noms = programmation.ordre_groupes(programmation.nom_groupe(c) for c in st.comptes_du_projet(F))
    verifier("« Compte 10 » après « Compte 9 »", noms[-2:] == ["Compte 9", "Compte 10"], noms)
    verifier("l'écart fixe entre groupes : Compte 8 à 7 × 19 min", programmation.decalage(st, noms, "Compte 8") == 133,
             programmation.decalage(st, noms, "Compte 8"))

    tt = next(c for c in st.comptes_du_projet(F) if c["plateforme"] == "tiktok")
    verifier("TikTok sans règle : la description du centre", programmation.legende_pour(st, tt, "desc", "desc") == "desc")
    st.poser_reglage(f"legende_tiktok:{F}", "Envoie « STOCK »")
    verifier("TikTok avec règle : la règle", programmation.legende_pour(st, tt, "desc", "desc") == "Envoie « STOCK »")
    verifier("une légende tapée à la main reste", programmation.legende_pour(st, tt, "à la main", "desc") == "à la main")

print("\n" + ("tout est bon" if not echecs else f"{echecs} échec(s)"))
sys.exit(1 if echecs else 0)
