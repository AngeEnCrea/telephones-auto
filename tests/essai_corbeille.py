"""Corbeille du calendrier : migration, isolation, restauration groupée, créneau libre et double clic.
uv run --with aiohttp==3.14.3 --with pillow==12.3.0 --with tzdata python tests/essai_corbeille.py
"""
import asyncio
import datetime as dt
import pathlib
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "service"))
import serveur
from stock import Stock, maintenant


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = pathlib.Path(tmp) / "t.db"
        st = Stock(chemin)
        comptes = [st.ajouter_compte(plat, f"autre_{plat}", "U1", projet="autre-projet", groupe="un autre projet")
                   for plat in ("tiktok", "instagram")]
        principal = st.ajouter_compte("tiktok", "mapage", "U2", projet="perso", groupe="un autre projet")
        futur = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        eid = st.creer_envoi("dossier:video", "Vidéo à garder", 0)
        pubs = [st.creer_publication(c["id"], "dossier:video", "Vidéo à garder", "Légende exacte", futur,
                                    envoi_id=eid, options='{"essai": true}') for c in comptes]
        reserve = st.creer_publication(comptes[0]["id"], "dossier:reserve", quand=futur)
        auto = st.creer_publication(comptes[0]["id"], "dossier:auto", quand=futur)
        autre = st.creer_publication(principal["id"], "dossier:autre", quand=futur)
        for p in pubs + [reserve, auto, autre]:
            st.maj_publication(p["id"], etat="annule", fin=maintenant())
        st.etape(reserve["id"], "Mise en réserve : réserve de la page")
        st.etape(auto["id"], "Annulée : la vidéo est refusée")
        # Une base existante avant cette fonctionnalité, avec des suppressions déjà faites.
        st.db.execute("alter table publications drop column supprime_le")
        st.db.close()
        st = Stock(chemin)
        assert {x["id"] for x in st.corbeille("autre-projet")} == {p["id"] for p in pubs}
        print("✓ Anciennes suppressions récupérées ; réserve et robot exclus ; projets séparés")
        async with TestClient(TestServer(serveur.creer(SimpleNamespace(telephones={}), st, SimpleNamespace(), None))) as cli:
            async def post(route, data):
                r = await cli.post("/telephones/api/" + route, json=data)
                return r.status, await r.json()

            r = await cli.get("/telephones/api/corbeille?projet=autre-projet")
            entrees = (await r.json())["entrees"]
            assert len(entrees) == 1 and len(entrees[0]["comptes"]) == 2
            ids = [p["id"] for p in pubs]
            corps = {"projet": "autre-projet", "ids": ids}
            assert (await post("corbeille/restaurer", {**corps, "projet": "perso"}))[0] == 409
            code, d = await post("corbeille/restaurer", corps)
            assert code == 200 and d["origine"] and d["quand"] == futur, d
            for pid in ids:
                p = st.publication(pid)
                assert p["etat"] == "en_attente" and p["supprime_le"] is None and p["quand"] == futur
                assert p["legende"] == "Légende exacte" and p["options"] == '{"essai": true}'
            assert (await post("corbeille/restaurer", corps))[0] == 409
            print("✓ TikTok et Insta restaurés ensemble, mêmes identifiants, légende et options ; double clic sans doublon")
            for pid in ids:
                assert (await post(f"publications/{pid}/annuler", {}))[0] == 200
            assert len(st.corbeille("autre-projet")) == 2
            doublon = st.creer_publication(comptes[0]["id"], "dossier:video", quand=futur)
            assert (await post("corbeille/restaurer", corps))[0] == 409
            assert all(st.publication(i)["etat"] == "annule" for i in ids)
            st.maj_publication(doublon["id"], etat="annule")
            print("✓ Vidéo déjà programmée sur le même compte : restauration refusée sans doublon")
            conflit = st.creer_publication(comptes[0]["id"], "autre vidéo", quand=futur)
            code, d = await post("corbeille/restaurer", corps)
            assert code == 200 and not d["origine"] and d["quand"] > maintenant() and d["quand"] != futur, d
            assert len({st.publication(i)["quand"] for i in ids}) == 1
            print("✓ Créneau d'origine occupé : prochain créneau libre commun aux réseaux")
            for pid in ids:
                await post(f"publications/{pid}/annuler", {})
                st.maj_publication(pid, quand="2020-01-01T12:00:00Z")
            with patch("programmation.prochain_creneau", return_value=None):
                assert (await post("corbeille/restaurer", corps))[0] == 409
            assert all(st.publication(i)["etat"] == "annule" for i in ids)
            code, d = await post("corbeille/restaurer", corps)
            assert code == 200 and not d["origine"] and d["quand"] > maintenant(), d
            print("✓ Heure passée : prochain créneau futur ; aucun créneau : rien n'est perdu")
            assert (await cli.get("/telephones/api/corbeille?projet=autre-projet")).status == 200
            # Les restaurations manuelles sont protégées de la remise en réserve automatique.
            st.maj_publication(ids[0], options="")
            restauree = next(p for p in st.file_des_comptes([c["id"] for c in comptes]) if p["id"] == ids[0])
            assert restauree["relancee"]
        st.db.close()
        st = Stock(chemin)
        assert not st.corbeille("autre-projet")
        assert st.corbeille("perso")
        st.db.close()
        print("✓ Sauvegarde persistante après redémarrage")


asyncio.run(main())
