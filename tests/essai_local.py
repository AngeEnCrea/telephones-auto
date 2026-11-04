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


def essais_unitaires(tmp):
    """Les règles de santé (sante.py), l'alerte « 2 échecs d'affilée » et le relevé raté, sans le service."""
    import logging
    import types
    logging.getLogger("sante").setLevel(logging.ERROR)        # l'alerte attendue ne s'affiche pas au milieu des résultats
    sys.path.insert(0, str(RACINE / "service"))
    import publication
    import sante
    from stock import Stock
    t = time.time()

    def post(age_h, vues):
        return {"id": f"p{age_h}", "vues": vues, "ts": t - age_h * 3600, "desc": "", "lien": ""}
    d = sante.diagnostic([post(30, 5), post(50, 40), post(80, 10), post(120, 2)], t)
    verifier("santé : shadowban probable sous 30 vues de médiane (4 posts de 1 à 7 jours)", [x[0] for x in d] == ["shadowban"], d)
    d = sante.diagnostic([post(2, 0), post(13, 0), post(30, 0)], t)
    verifier("santé : zéro vue sur tous les posts de 12 h à 48 h (un post de 2 h à 0 vue ne compte pas)", [x[0] for x in d] == ["zero_vue"], d)

    def releve(il_y_a_h, posts):          # un relevé gardé d'il y a tant d'heures : [(âge du post à ce relevé en h, vues)]
        r = t - il_y_a_h * 3600
        return {"releve_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r)),
                "posts": [{"id": f"q{round((r - a * 3600) / 60)}", "vues": v, "ts": r - a * 3600, "desc": "", "lien": ""}
                          for a, v in posts]}
    mois = [releve(j * 24 - 30, [(30, 1000)]) for j in range(5, 16)]        # 11 posts du mois à 1 000 vues au bout d'un jour
    dernier = releve(0, [(30, 100), (40, 80), (50, 120), (60, 90)])
    d = sante.diagnostic(dernier["posts"], t, mois + [dernier])
    verifier("santé : chute des vues (100 vues au bout d'un jour sur les 4 derniers posts, contre 1 000 d'habitude au même âge)",
             [x[0] for x in d] == ["chute"], d)
    dernier = releve(0, [(16, 18000), (30, 100), (40, 80), (50, 120), (60, 90)])
    d = sante.diagnostic(dernier["posts"], t, mois + [dernier])
    verifier("santé : pas de chute quand un post de moins de 3 jours part (18 000 vues à 16 h)", d == [], d)
    mois = [releve(j * 24 - 30, [(30, 193)]) for j in range(5, 17)]
    dernier = releve(0, [(11, 161), (13, 237), (23, 437), (35, 186), (38, 142), (41, 140), (71, 167), (83, 2264), (86, 138), (89, 2285)])
    d = sante.diagnostic(dernier["posts"], t, mois + [dernier])
    verifier("santé : pas de chute parce que 2 des 3 posts de plus de 3 jours étaient des pépites (Insta @mapage, 29/10/2026)",
             d == [], d)
    d = sante.diagnostic([post(30, 3000), post(50, 4000), post(80, 2500), post(10, 0)], t)
    verifier("santé : une page en forme ne lève rien (même avec un post tout neuf à 0 vue)", d == [], d)

    st = Stock(tmp / "unitaire" / "telephones.db")
    c = st.ajouter_compte("tiktok", "page_test", udid="U1", groupe="Page test")

    class FauxDiscord:
        envois = []

        def envoyer(self, salon, texte=None, embeds=None, apres=None):
            self.envois.append((salon, (embeds or [{}])[0].get("title") or texte))
    ns = types.SimpleNamespace(stock=st, discord=FauxDiscord())

    def rate(i):
        p = st.creer_publication(c["id"], "dossier:x.mp4", "x")
        st.maj_publication(p["id"], etat="echec", fin=f"2026-10-08T0{i}:00:00Z", erreur="TikTok ne répond plus")
        publication.Publieur.surveiller_echecs(ns, c, "TikTok ne répond plus")
    rate(1)
    un = list(ns.discord.envois)
    rate(2)
    rate(3)
    verifier("santé : 2 publications ratées d'affilée → une alerte 🩺 santé-pages, une seule fois dans la journée",
             not un and ns.discord.envois == [("SANTE", "🔴 2 publications ratées d'affilée · TikTok @page_test")], ns.discord.envois)
    import programmation
    st.poser_reglage("legende_instagram:perso", "@moncompte")
    ig_ = st.ajouter_compte("instagram", "page.ig", udid="U1", projet="perso", groupe="Page test")
    tt_ = st.ajouter_compte("tiktok", "page_tt", udid="U1", projet="perso", groupe="Page test")
    autre = st.ajouter_compte("instagram", "autre.ig", udid="U1", projet="autre-projet")
    verifier("légende Instagram : la règle du projet remplace la description ; TikTok, un autre projet et une légende tapée à la main restent",
             programmation.legende_pour(st, ig_, "desc du centre") == "@moncompte"
             and programmation.legende_pour(st, ig_, "desc", "desc") == "@moncompte"
             and programmation.legende_pour(st, ig_, "ma légende", "desc") == "ma légende"
             and programmation.legende_pour(st, tt_, "desc du centre") == "desc du centre"
             and programmation.legende_pour(st, autre, "desc du centre") == "desc du centre")
    # les pages de niche : montée en charge
    import datetime as dt_
    from zoneinfo import ZoneInfo as Zi
    aujourdhui = dt_.datetime.now(Zi("Europe/Paris")).date()
    pg = st.poser_page("perso", "Page test", "grossiste", aujourdhui.isoformat())
    q = [programmation.quota(st, pg, aujourdhui + dt_.timedelta(days=i)) for i in (-1, 0, 1, 2, 3, 4, 5, 9)]
    verifier("page de niche : 1 vidéo le jour 1, une de plus chaque jour, 5 au plus (le nombre de créneaux) ; rien avant ; sans jour 1, pas de limite",
             q == [0, 1, 2, 3, 4, 5, 5, 5] and programmation.quota(st, None, aujourdhui) is None, q)
    midi = dt_.datetime.combine(aujourdhui, dt_.time(6, 0), tzinfo=Zi("Europe/Paris")).astimezone(dt_.timezone.utc)
    p1 = st.creer_publication(ig_["id"], "dossier:x", "x", "", (midi + dt_.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    p2 = st.creer_publication(tt_["id"], "dossier:x", "x", "", p1["quand"])
    suivant = programmation.prochain_creneau(st, [ig_["id"], tt_["id"]], 0, maintenant=midi, varier=False)
    verifier("page de niche au jour 1, sa vidéo du jour déjà en file (TikTok + Insta) : la suivante part le lendemain",
             suivant and programmation.a_paris(suivant).date() == aujourdhui + dt_.timedelta(days=1), suivant)
    ici = programmation.prochain_creneau(st, [ig_["id"], tt_["id"]], 0, maintenant=midi, varier=False, exclure={p1["id"], p2["id"]})
    verifier("une vidéo qu'on déplace (créneau manqué, « Reporter ») ne compte pas dans la dose de son jour : elle reste le jour même, "
             "hors de son ancien créneau",
             ici and programmation.a_paris(ici).date() == aujourdhui and ici != p1["quand"], (ici, p1["quand"]))
    import liens
    base = 1_000_000
    pl = [(base + 7260, "@moncompte", "L3"), (base + 60, "@moncompte", "L1"), (base + 3630, "@moncompte", "L2")]
    verifier("lien retrouvé avec une légende commune (« @moncompte ») : le post le plus ancien après le départ, jamais un déjà pris ni hors des 2 h",
             liens.choisir_post(pl, base, "@moncompte") == "L1" and liens.choisir_post(pl, base, "@moncompte", {"L1"}) == "L2"
             and liens.choisir_post(pl, base + 3600, "@moncompte") == "L2" and liens.choisir_post(pl, base - 3 * 3600, "@moncompte") is None)
    import goios
    vrai_ios, appels = goios.ios, []

    async def ios_bloque(*args, udid=None, delai=60, entree=None):    # la pellicule qui ne répond pas (23/10/2026)
        appels.append(delai)
        if len(appels) == 1:
            raise goios.ErreurIos(args, None, [{"level": "ERROR", "msg": f"pas de réponse en {delai} s"}])
        return 0, "|-DCIM/\n|  |-100APPLE/\n|  |  |-IMG_0001.MP4\n", []
    goios.ios = ios_bloque
    logging.getLogger("go-ios").setLevel(logging.ERROR)
    from concurrent.futures import ThreadPoolExecutor

    def lancer(coro):                    # essais_unitaires tourne déjà dans la boucle d'asyncio du test
        with ThreadPoolExecutor(1) as x:
            return x.submit(asyncio.run, coro).result()
    try:
        noms = lancer(goios.lister("U1", None, "/DCIM"))
        appels_ok = list(appels)

        async def toujours_bloque(*args, udid=None, delai=60, entree=None):
            appels.append(delai)
            raise goios.ErreurIos(args, None, [{"level": "ERROR", "msg": f"pas de réponse en {delai} s"}])
        goios.ios, appels[:] = toujours_bloque, []
        try:
            lancer(goios.lister("U1", None, "/DCIM"))
            leve = False
        except goios.ErreurIos:
            leve = len(appels) == 3
    finally:
        goios.ios = vrai_ios
    verifier("pellicule : une lecture bloquée est refaite (la publication ne rate plus), et l'erreur ne remonte qu'au 3e blocage",
             noms == ["IMG_0001.MP4"] and appels_ok == [30, 30] and leve, (noms, appels_ok, leve))
    st.noter_releve(c["id"], "2026-10-08", 100, [post(30, 5)])
    st.noter_releve(c["id"], "2026-10-08", None, [], "Scrape Creators : HTTP 500")
    r = st.releves(c["id"], "2026-10-01")[-1]
    verifier("santé : un relevé raté garde les vues du précédent et note l'erreur",
             r["abonnes"] == 100 and len(r["posts"]) == 1 and r["erreur"].endswith("500"), r)


def essais_file(tmp):
    """Cinq par jour sur chaque compte (27/10/2026) : les créneaux comptés compte par compte, la file d'une page limitée à
    3 jours, les vidéos disparues annulées d'avance, la suivante prête au créneau d'une vidéo pas publiable, la relance
    unique d'un échec passager. Sans le service (le centre est simulé)."""
    import types
    import videos
    import programmation
    import publication
    from stock import Stock
    from concurrent.futures import ThreadPoolExecutor

    def lancer(coro):
        with ThreadPoolExecutor(1) as x:
            return x.submit(asyncio.run, coro).result()
    paris = ZoneInfo("Europe/Paris")
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
    st = Stock(tmp / "file" / "telephones.db")
    tt = st.ajouter_compte("tiktok", "page_a_tt", udid="U1", projet="perso", groupe="Compte A")
    ig = st.ajouter_compte("instagram", "page_a_ig", udid="U1", projet="perso", groupe="Compte A")
    st.poser_page("perso", "Compte A", "", "2026-10-01")
    jour = dt.date(2026, 11, 2)
    matin = dt.datetime.combine(jour, dt.time(6, 0), tzinfo=paris).astimezone(dt.timezone.utc)
    a = lambda h: iso(dt.datetime.combine(jour, dt.time(h, 0), tzinfo=paris).astimezone(dt.timezone.utc))   # noqa: E731
    for h in (9, 12):
        e = st.creer_envoi(f"dossier:v{h}", f"v{h}", 0, auto=True)
        for c in (tt, ig):
            st.creer_publication(c["id"], f"dossier:v{h}", f"v{h}", "", a(h), False, e)
    e = st.creer_envoi("dossier:seul", "seul", 0, auto=True)
    st.creer_publication(ig["id"], "dossier:seul", "seul", "", a(15), False, e)   # un Insta relancé seul
    seul_tt = programmation.prochain_creneau(st, [tt["id"]], 0, maintenant=matin, varier=False)
    les_deux = programmation.prochain_creneau(st, [tt["id"], ig["id"]], 0, maintenant=matin, varier=False)
    verifier("créneaux compte par compte : un Insta seul à 15 h laisse le créneau libre à son TikTok ; TikTok + Insta "
             "ensemble vont à 18 h (27/10/2026 : Compte 3, 21 Insta en file pour 13 TikTok)",
             seul_tt == a(15) and les_deux == a(18), (seul_tt, les_deux))

    # les trous de la file d'un compte comblés par sa publication la plus lointaine (TikTok du Compte 1 sans rien le 29/10)
    te = st.ajouter_compte("tiktok", "page_e_tt", udid="U5", projet="perso", groupe="Compte E")
    ie = st.ajouter_compte("instagram", "page_e_ig", udid="U5", projet="perso", groupe="Compte E")
    st.poser_page("perso", "Compte E", "", "2026-10-01")
    dec_e = programmation.groupe_de(st, te)[1]
    for i in range(3):
        programmation.placer(st, f"dossier:e{i}", f"e{i}", "", [te, ie], dec_e)
    ig_e = programmation.placer(st, "dossier:e3", "e3", "", [ie], dec_e)[0]   # un Insta seul : TikTok y a un trou
    e = st.creer_envoi("dossier:loin", "loin", 0, auto=True)
    p_loin = st.creer_publication(te["id"], "dossier:loin", "loin", "",
                                  iso(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=40)), False, e)
    avancees = [x for x in programmation.compacter(st) if x["compte_id"] in (te["id"], ie["id"])]
    x_loin = st.publication(p_loin["id"])
    ecart = abs((dt.datetime.fromisoformat(x_loin["quand"][:-1]) - dt.datetime.fromisoformat(ig_e["quand"][:-1])).total_seconds())
    verifier("file trouée : la publication la plus lointaine du TikTok avancée dans son trou (le créneau de l'Insta seul, ± 15 min), "
             "l'étape le dit ; l'Insta, sans trou, ne bouge pas ; au passage suivant plus rien ne bouge",
             [x["id"] for x in avancees] == [p_loin["id"]] and ecart <= 30 * 60
             and st.etapes(p_loin["id"])[-1]["message"].startswith("Avancée dans un trou de la file")
             and not [x for x in programmation.compacter(st) if x["compte_id"] in (te["id"], ie["id"])],
             (avancees, x_loin["quand"], ig_e["quand"]))

    # la file d'une page : au-delà de 15 par compte, en trop (le centre les met en réserve)
    tb = st.ajouter_compte("tiktok", "page_b_tt", udid="U2", projet="perso", groupe="Compte B")
    ib = st.ajouter_compte("instagram", "page_b_ig", udid="U2", projet="perso", groupe="Compte B")
    st.poser_page("perso", "Compte B", "", "2026-10-01")
    for i in range(17):
        e = st.creer_envoi(f"dossier:b{i:02d}", f"b{i}", 0, auto=True)
        q = iso(matin + dt.timedelta(days=30, hours=3 * i))
        for c in ((tb, ib) if i < 16 else (tb,)):
            st.creer_publication(c["id"], f"dossier:b{i:02d}", f"b{i}", "", q, False, e)
    trop = programmation.en_trop(st, [tb["id"], ib["id"]], 15)
    verifier("file d'une page : au-delà de 15 publications par compte, le surplus regroupé par vidéo, le plus proche d'abord",
             [x["video"] for x in trop] == ["dossier:b15", "dossier:b16"]
             and len(trop[0]["publications"]) == 2 and len(trop[1]["publications"]) == 1, trop)
    # une relance (agent réparateur, 28/10/2026) posée au bout de la file ne part pas en réserve : la plus lointaine des autres y va
    b16 = next(x for x in st.publications_de_video("dossier:b16") if x["compte_id"] == tb["id"])
    st.etape(b16["id"], "Relancée par l'agent réparateur : agent WDA coupé (passager) : reportée au 31/10 à 13:13")
    trop = programmation.en_trop(st, [tb["id"], ib["id"]], 15)
    verifier("surplus d'une file : une publication relancée exprès reste en file (28/10/2026 : les relances du réparateur partaient "
             "en réserve 5 min après) ; c'est la plus lointaine des autres qui sort",
             [x["video"] for x in trop] == ["dossier:b14", "dossier:b15"]
             and len(trop[0]["publications"]) == 1 and len(trop[1]["publications"]) == 2, trop)

    # une pépite passe devant la file : sur chaque compte,
    # l'heure de sa prochaine publication à plus de 20 min, reportée au bout ; une deuxième pépite ne déloge pas la première
    td = st.ajouter_compte("tiktok", "page_p_tt", udid="U6", projet="perso", groupe="Compte P")
    id_ = st.ajouter_compte("instagram", "page_p_ig", udid="U6", projet="perso", groupe="Compte P")
    st.poser_page("perso", "Compte P", "", "2026-10-01")
    dec_d = programmation.groupe_de(st, td)[1]
    for i in range(5):
        programmation.placer(st, f"dossier:p{i}", f"p{i}", "", [td, id_], dec_d)
    limite = iso(dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=21))
    avant = {c["id"]: st.file_des_comptes([c["id"]]) for c in (td, id_)}
    pep = programmation.placer_en_tete(st, "dossier:pep1", "pep1", "", [td, id_], dec_d)
    ok, vu = len(pep) == 2, []
    for c in (td, id_):
        visee = next(y for y in avant[c["id"]] if y["quand"] >= limite)
        mien = next(p for p in pep if p["compte_id"] == c["id"])
        delogee = st.publication(visee["id"])
        ok = ok and mien["quand"] == visee["quand"] and delogee["quand"] > max(y["quand"] for y in avant[c["id"]] if y["id"] != visee["id"])
        ok = ok and st.etapes(delogee["id"])[-1]["message"].startswith("Laisse sa place à une pépite")
        ok = ok and st.etapes(mien["id"])[-1]["message"].startswith("Pépite : passe devant la file")
        vu.append((visee["quand"], mien["quand"], delogee["quand"]))
    pep2 = programmation.placer_en_tete(st, "dossier:pep2", "pep2", "", [td, id_], dec_d)
    ok = ok and len(pep2) == 2 and all(st.publication(p["id"])["quand"] == p["quand"] for p in pep)
    ok = ok and all(p2["quand"] != p["quand"] for p2 in pep2 for p in pep)
    verifier("pépite : elle prend l'heure de la prochaine publication de chaque compte (à plus de 20 min), qui part au bout "
             "de la file ; une deuxième pépite ne déloge pas la première (31/10/2026)", ok, vu)

    # la programmation : file pleine, le remontage attend ; une place se libère, il la prend (TikTok + Insta ensemble)
    tc = st.ajouter_compte("tiktok", "page_c_tt", udid="U3", projet="perso", groupe="Compte C")
    ic = st.ajouter_compte("instagram", "page_c_ig", udid="U3", projet="perso", groupe="Compte C")
    st.poser_page("perso", "Compte C", "", "2026-10-01")
    dec_c = programmation.groupe_de(st, tc)[1]
    for i in range(15):
        programmation.placer(st, f"dossier:c{i:02d}", f"c{i}", "desc", [tc, ic], dec_c)
    centre_ = {"valides": [], "partis": set(), "retouche": set(), "vus": []}

    async def publiables(http):
        return [{"cle": k, "titre": k, "statut": "valide", "groupe": g, "description": "d"} for k, g in centre_["valides"]]

    async def verifier_publiable(http, cle):
        centre_["vus"].append(cle)
        if cle in centre_["partis"]:
            raise videos.PasPubliable("plus dans le centre")
        if cle in centre_["retouche"]:
            raise videos.PasPubliable("en retouche", "retours")
        return {}
    vrais = videos.videos_publiables, videos.verifier_publiable
    retouche_vraie, videos.EN_RETOUCHE = videos.EN_RETOUCHE, ("retours",)   # le dossier n'a pas de relecture : simulée ici
    videos.videos_publiables, videos.verifier_publiable = publiables, verifier_publiable
    try:
        file_c = [f"dossier:c{i:02d}" for i in range(15)]
        centre_["valides"] = [(k, "Compte C") for k in file_c] + [("dossier:neuve.mp4", "Compte C")]
        faits = lancer(programmation.programmer(st, None))
        verifier("file pleine (15 par compte) : le remontage validé attend son tour, rien n'est programmé",
                 faits == [] and not st.publications_de_video("dossier:neuve.mp4"), faits)
        trou = st.publications_de_video(file_c[2])
        for x in trou:
            st.maj_publication(x["id"], etat="annule")
        faits = lancer(programmation.programmer(st, None))
        neuve = st.publications_de_video("dossier:neuve.mp4")
        verifier("une place se libère dans la file : le remontage la prend, TikTok + Insta à la même heure, à ± 15 min du trou",
                 len(faits) == 1 and len(neuve) == 2 and len({x["quand"] for x in neuve}) == 1
                 and abs((dt.datetime.fromisoformat(neuve[0]["quand"][:-1]) - dt.datetime.fromisoformat(trou[0]["quand"][:-1])).total_seconds()) <= 30 * 60,
                 (faits, neuve, trou[0]["quand"]))

        # les vidéos disparues annulées d'avance (pas au jour J) ; en retouche, elles gardent leur place
        centre_["partis"], centre_["retouche"] = {file_c[5]}, {file_c[6]}
        centre_["valides"] = [(k, "Compte C") for k in file_c if k not in (file_c[5], file_c[6])]
        lancer(programmation.purger(st, None, lancer(publiables(None))))
        e5 = {x["etat"] for x in st.publications_de_video(file_c[5])}
        e6 = {x["etat"] for x in st.publications_de_video(file_c[6])}
        msg5 = [st.etapes(x["id"])[-1]["message"] for x in st.publications_de_video(file_c[5])]
        vus = len(centre_["vus"])
        lancer(programmation.purger(st, None, []))
        verifier("purge d'avance : une vidéo disparue annulée partout où elle attend, une en retouche gardée ; "
                 "liste vide → rien n'est relu ni touché",
                 e5 == {"annule"} and e6 == {"en_attente"} and all("vu d'avance" in m for m in msg5) and len(centre_["vus"]) == vus,
                 (e5, e6, msg5))

        # au créneau, la vidéo n'est plus là : la suivante PRÊTE de la file prend sa place (la disparue sautée et annulée)
        maint = dt.datetime.now(dt.timezone.utc)
        td = st.ajouter_compte("tiktok", "page_d_tt", udid="U4", projet="perso", groupe="Compte D")
        idd = st.ajouter_compte("instagram", "page_d_ig", udid="U4", projet="perso", groupe="Compte D")
        st.poser_page("perso", "Compte D", "", "2026-10-01")
        lots = {}
        for nom, h in (("d-faute", -0.02), ("d-partie", 3), ("d-prete", 6), ("d-apres", 9)):
            e = st.creer_envoi(f"dossier:{nom}", nom, 0, auto=True)
            lots[nom] = [st.creer_publication(c["id"], f"dossier:{nom}", nom, "", iso(maint + dt.timedelta(hours=h)), False, e)
                         for c in (td, idd)]
        centre_["partis"] = {"dossier:d-faute", "dossier:d-partie"}
        st.maj_publication(lots["d-faute"][0]["id"], etat="en_cours")
        lot = programmation.lot_de(st, st.publication(lots["d-faute"][0]["id"]))
        av = lancer(programmation.remplacer(st, None, lot, "à la place de « d-faute » (plus dans le centre)", maintenant=maint))
        prete = [st.publication(x["id"]) for x in lots["d-prete"]]
        partie = {st.publication(x["id"])["etat"] for x in lots["d-partie"]}
        apres = {st.publication(x["id"])["quand"] for x in lots["d-apres"]}
        verifier("créneau d'une vidéo disparue : la suivante prête de la page (TikTok + Insta) avancée à maintenant, la disparue "
                 "d'après sautée et annulée, la suite ne bouge pas",
                 len(av) == 2 and all(x["quand"] == iso(maint) for x in prete) and partie == {"annule"}
                 and apres == {lots["d-apres"][0]["quand"]} and all(st.etapes(x["id"])[-1]["message"].startswith("Avancée à maintenant") for x in prete),
                 (av, [(x["etat"], x["quand"]) for x in prete], partie))
        autre_c = st.ajouter_compte("tiktok", "autre_test", udid="U4", projet="autre-projet", groupe="un autre projet test")
        e = st.creer_envoi("dossier:x", "x", 0, auto=True)
        pdx = st.creer_publication(autre_c["id"], "dossier:x", "x", "", iso(maint), False, e)
        st.creer_publication(autre_c["id"], "dossier:y", "y", "", iso(maint + dt.timedelta(hours=3)), False, e)
        verifier("pas de remplaçante hors des pages réglées (un autre projet se place à la main dans le calendrier)",
                 lancer(programmation.remplacer(st, None, [pdx], "x", maintenant=maint)) == [])
    finally:
        videos.videos_publiables, videos.verifier_publiable = vrais
        videos.EN_RETOUCHE = retouche_vraie

    # les échecs passagers : relancés une fois, au créneau libre suivant ; jamais un compte déconnecté, ni ce qui a pu partir
    oui = ["l'agent ne répond pas (ClientPayloadError)", "base du service injoignable (ETIMEDOUT)",
           "ios fsync tree --path=/DCIM : pas de réponse en 60 s", "la vidéo n'est pas arrivée dans le dossier de VLC",
           "la liste des comptes de TikTok ne s'est pas ouverte (flèche à côté du nom, en haut du profil) : voir la capture",
           "introuvable à l'écran : « creation-reel »", "toujours pas à l'écran après 1 s : « user-switch-title-button »",
           "le profil de TikTok ne s'ouvre pas : une fenêtre de TikTok gêne ? (voir la capture)"]
    non = ["@mapage.fun n'est pas parmi les comptes connectés à Instagram sur ce téléphone",
           "Instagram est bloqué sur « Nettoyage du compte » (il croit que quelqu'un d'autre s'est servi du compte)",
           "ma_page : la liste des comptes de TikTok tourne sans le trouver (compte actif : x)",
           "toujours sur l'écran « Publier » 12 s après : un écran inattendu (voir la capture) ; vérifie sur le compte avant de relancer",
           "Interrompue (service redémarré) : vérifie sur le compte avant de la relancer.",
           "reel d'essai demandé, mais l'interrupteur « Essai » ne se coche pas (voir la capture)"]
    verifier("échecs passagers reconnus (agent, base injoignable, DCIM, liste des comptes, bouton introuvable) ; jamais un compte "
             "déconnecté ou bloqué, ni ce qui a pu partir",
             all(programmation.passager(m) for m in oui) and not any(programmation.passager(m) for m in non),
             ([m for m in oui if not programmation.passager(m)], [m for m in non if programmation.passager(m)]))

    class FauxDiscord:
        envois = []

        def envoyer(self, salon, texte=None, embeds=None, apres=None):
            self.envois.append((salon, texte))
    ns = types.SimpleNamespace(stock=st, discord=FauxDiscord())
    ns.texte_publication = types.MethodType(publication.Publieur.texte_publication, ns)
    relancer = lambda pid, msg: publication.Publieur.relancer_si_passager(ns, pid, st.compte(st.publication(pid)["compte_id"]), msg)   # noqa: E731

    def ratee(nom, etapes):
        e = st.creer_envoi(f"dossier:{nom}", nom, 0, auto=True)
        x = st.creer_publication(tt["id"], f"dossier:{nom}", nom, "", iso(dt.datetime.now(dt.timezone.utc)), False, e)
        for m in etapes:
            st.etape(x["id"], m)
        st.maj_publication(x["id"], etat="echec", erreur="l'agent ne répond pas (ServerDisconnectedError)")
        return x["id"]
    r1 = ratee("passager", ["Ouverture de TikTok", "Compte @page_a_tt"])
    q1 = relancer(r1, "l'agent ne répond pas (ServerDisconnectedError)")
    x1 = st.publication(r1)
    texte = ns.texte_publication(r1, "echec", erreur="l'agent ne répond pas", relance=q1)
    st.maj_publication(r1, etat="echec")
    q1b = relancer(r1, "l'agent ne répond pas (ServerDisconnectedError)")
    r2 = ratee("parti", ["Ouverture de TikTok", "Légende", "Prêt à publier"])
    r3 = ratee("deconnecte", ["Ouverture de TikTok"])
    verifier("échec passager : relancé une fois au créneau libre suivant (l'étape et le message Discord le disent), pas deux ; "
             "jamais après « Prêt à publier », ni pour un compte déconnecté",
             q1 and x1["etat"] == "en_attente" and x1["quand"] == q1 and st.etapes(r1)[-1]["message"].startswith(programmation.RELANCE)
             and "🔁" in texte and "relancée une fois" in texte and q1b is None
             and relancer(r2, "introuvable à l'écran : « share-sheet-share-button »") is None
             and relancer(r3, "@page_a_tt n'est pas parmi les comptes connectés à TikTok") is None,
             (q1, x1["etat"], texte, q1b))


async def faux_centre(port, lire_iphone):
    recus = []
    # faux Discord (webhooks des salons du service) et réglages du faux Scrape Creators, que les essais changent
    faux = {"discord": [], "vues": {}, "abonnes": {}, "vieux": {}, "credits": 5000}
    prods = faux["prods"] = {"abc": {"id": "abc", "titre": "Short validé", "type": "short", "etat": {"statut": "valide"}},
             "def": {"id": "def", "titre": "Short à valider", "type": "short", "etat": {"statut": "a_valider"}},
             "ghi": {"id": "ghi", "titre": "Autre short validé", "type": "short", "etat": {"statut": "valide"}},
             # un remontage automatique de « abc » pour le groupe Clips 1 (centre, 04/10/2026), validé par l'utilisateur
             "rem": {"id": "rem", "titre": "Short validé - 05 - 9x16", "type": "short", "etat": {"statut": "valide"},
                     "origine": "abc", "groupe": "Clips 1", "description": "Remontage 🔁 #vinted"}}
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
        h = req.query["handle"]
        posts = [x for x in lire_iphone().get("tt_posts", []) if x["compte"] == h] + faux["vieux"].get(h, [])
        posts.sort(key=lambda x: x["t"])
        return web.json_response({"aweme_list": [{"aweme_id": x["id"], "desc": x["desc"], "create_time": x["t"],
                                                  "statistics": {"play_count": x.get("vues", faux["vues"].get(x["id"], 0))},
                                                  "author": {"follower_count": faux["abonnes"].get(h)}} for x in reversed(posts)]})

    @r.get("/scrape/v1/instagram/profile")
    async def sc_instagram(req):
        if req.headers.get("x-api-key") != "cle-de-test":
            return web.json_response({"error": "cle"}, status=401)
        h = req.query["handle"]
        posts = sorted(lire_iphone().get("ig_pubs", {}).get(h, []) + faux["vieux"].get(h, []), key=lambda x: -x["t"])
        return web.json_response({"data": {"user": {"edge_followed_by": {"count": faux["abonnes"].get(h)}, "edge_owner_to_timeline_media": {"edges": [
            {"node": {"shortcode": x["id"], "product_type": "clips", "is_video": True, "taken_at_timestamp": x["t"],
                      "video_play_count": x.get("vues", faux["vues"].get(x["id"], 0)),
                      "edge_media_to_caption": {"edges": [{"node": {"text": x["desc"]}}]}}} for x in posts]}}}})

    @r.get("/scrape/v1/credit-balance")
    async def sc_credits(req):
        return web.json_response({"creditCount": faux["credits"]})

    # le faux Discord : un webhook par salon (?wait=true rend l'id du message), et la modification d'un message
    @r.post("/discord/{salon}")
    async def dc_poster(req):
        mid = str(900000 + len(faux["discord"]))
        faux["discord"].append({**await req.json(), "salon": req.match_info["salon"], "id": mid, "op": "post", "wait": req.query.get("wait")})
        return web.json_response({"id": mid})

    @r.patch("/discord/{salon}/messages/{mid}")
    async def dc_modifier(req):
        faux["discord"].append({**await req.json(), "salon": req.match_info["salon"], "id": req.match_info["mid"], "op": "patch"})
        return web.json_response({"id": req.match_info["mid"]})

    @r.get("/api/projets")
    async def projets(req):
        return web.json_response([{"slug": "perso", "nom": "Mes vidéos", "emoji": "🧢", "sections": ["", "production"]},
                                  {"slug": "sans-prod", "nom": "Sans production", "sections": ["", "tracking"]}])

    @r.get("/api/projets/perso/productions")
    async def productions(req):
        return web.json_response({"productions": list(prods.values())})

    @r.get("/api/projets/perso/productions/{pid}")
    async def production(req):
        # « introuvables » : encore dans la liste (), mais sa fiche est partie
        p = prods.get(req.match_info["pid"]) if req.match_info["pid"] not in faux.get("introuvables", ()) else None
        return web.json_response(p) if p else web.json_response({"erreur": "?"}, status=404)

    @r.get("/media/perso/production/{pid}")
    async def media(req):
        return web.Response(body=b"\x00\x00\x00\x18ftypmp42" + os.urandom(200_000), content_type="video/mp4")

    @r.post("/api/projets/perso/productions/{pid}/publication")
    async def publication(req):
        recus.append((req.match_info["pid"], (await req.json())["url"]))
        return web.json_response({"etat": {"statut": "publie"}})

    app = web.Application()
    app.add_routes(r)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    return runner, recus, faux


async def principal():
    tmp = Path(tempfile.mkdtemp(prefix="essai-telephones-"))
    p_service, p_centre = port_libre(), port_libre()
    env = dict(os.environ, FAUX_IOS_DIR=str(tmp / "iphone"), FAUX_PYTHON=sys.executable,
               TELEPHONES_IOS=str(ICI / "faux-ios"), TELEPHONES_PMD3=str(ICI / "faux-pymobiledevice3"),
               TELEPHONES_DONNEES=str(tmp / "donnees"), TELEPHONES_PORT=str(p_service), TELEPHONES_VIDEOS=str(tmp / "videos"),
               TELEPHONES_PORT_AGENT=str(port_libre()), TELEPHONES_PORT_FLUX=str(port_libre()),
               TELEPHONES_JOURNAL=str(tmp / "service.log"), TELEPHONES_SCRAPE=f"http://127.0.0.1:{p_centre}/scrape/",
               TELEPHONES_SECRETS=str(tmp / "secrets"), TELEPHONES_ATTENTES_LIENS="1,1,2", TELEPHONES_ATTENTES_META="1,1,1",
               TELEPHONES_CHAUFFE_ECHELLE="0.02", TELEPHONES_CHAUFFE_P_LIKE="1", TELEPHONES_CHAUFFE_P_SUIVRE="1",
               TELEPHONES_PROGRAMMATION_S="2", TELEPHONES_SANTE_S="1", TELEPHONES_HORS_LIGNE_MIN="0.05")
    (tmp / "secrets").mkdir(parents=True, exist_ok=True)
    (tmp / "secrets" / "scrapecreators.env").write_text("SCRAPECREATORS_API_KEY=cle-de-test\n", encoding="utf-8")
    (tmp / "secrets" / "discord.env").write_text("".join(f"DISCORD_{x}=http://127.0.0.1:{p_centre}/discord/{x}\n" for x in
                                                         ("SANTE", "RAPPORT", "PUBLICATIONS", "TELEPHONES", "WARMUP")), encoding="utf-8")
    # le dossier des vidéos : deux à publier à la main, une dans le dossier du groupe « Clips 1 » (programmée seule)
    (tmp / "videos" / "Clips 1").mkdir(parents=True, exist_ok=True)
    (tmp / "videos" / "_archives").mkdir(parents=True, exist_ok=True)
    for nom in ("abc.mp4", "ghi.mp4", "Clips 1/rem.mp4"):
        (tmp / "videos" / nom).write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(200_000))
    (tmp / "videos" / "abc.txt").write_text("Short validé", encoding="utf-8")
    (tmp / "videos" / "Clips 1" / "rem.txt").write_text("Remontage 🔁 #vinted", encoding="utf-8")
    (tmp / "videos" / "_archives" / "vieille.mp4").write_bytes(b"x")          # dossier en « _ » : ignoré
    essais_unitaires(tmp)
    essais_file(tmp)
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

    runner, recus, faux = await faux_centre(p_centre, lambda: json.loads(etat_iphone.read_text(encoding="utf-8")))

    def discord(salon=None, depuis=0, op="post"):
        """Les messages reçus par le faux Discord (le texte et les titres des cartes mis bout à bout dans « tout »)."""
        return [{**m, "tout": (m.get("content") or "") + " ".join((e.get("title") or "") + " " + (e.get("description") or "")
                                                               + " ".join(f"{x.get('name')} {x.get('value')}" for x in e.get("fields") or [])
                                                               for e in m.get("embeds") or [])}
                for m in faux["discord"][depuis:] if (salon is None or m["salon"] == salon) and m["op"] == op]
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

            modifier_iphone(tt_shop=True,         # la fenêtre TikTok Shop au lancement (14/10/2026, sur tous les comptes)
                            raccourci_demande=True, tt_public=True,   # iPhone 2, 16/10/2026 : la demande d'iOS, 1re vidéo
                            tt_avertissement=True)  # « La situation évolue rapidement… » (28/10/2026, publication 1735)
            s, p2 = await post(f"/api/publications/{p['id']}/relancer", {"repetition": False})
            verifier("« Publier pour de vrai » remet en file sans répétition", s == 200 and p2["repetition"] == 0 and p2["etat"] == "en_attente", p2)
            x = await attendre(lambda: fini(p["id"]), 120, 1)
            verifier("publication pour de vrai : publiée", x and x["etat"] == "publie", x and (x["etat"], x["erreur"], [e["message"] for e in x["etapes"]]))
            ip = lire_iphone()
            verifier("le faux TikTok a la vidéo sur le bon compte, avec la légende (émoji compris)",
                     (ip.get("dernier_post") or {}).get("compte") == "ma_page" and "👀" in (ip.get("dernier_post") or {}).get("desc", ""),
                     ip.get("dernier_post"))
            verifier("son ajouté par TikTok retiré avant de publier", ip.get("dernier_post", {}).get("son") is None, ip.get("dernier_post"))
            verifier("fenêtre « TikTok Shop » (hors de l'arbre) reconnue sur la capture : « plus personnalisé » touché par la fenêtre (14/10/2026)",
                     ip.get("tt_shop_choix") == "personnalise" and not [j for j in ip["journal"] if j.startswith("piège:")]
                     and x and any("TikTok Shop" in e_["message"] for e_ in x["etapes"]), (ip.get("tt_shop_choix"), [j for j in ip["journal"] if "shop" in j or "piège" in j]))
            verifier("« Publier » touché sur la pastille rouge du haut (clavier ouvert, hors de l'arbre, vu le 04/10/2026)",
                     "tt_poster:pastille Publier" in ip["journal"], [j for j in ip["journal"] if j.startswith("tt_poster")])
            verifier("« Autoriser « Auto importer » à produire 1 photo ? », arrivée APRÈS la vidéo : « Toujours autoriser », "
                     "avant d'ouvrir TikTok (iPhone 2, 16/10/2026)",
                     "autorisation:Toujours autoriser" in ip["journal"] and not ip.get("raccourci_demande")
                     and not [j for j in ip["journal"] if j.startswith("piège:")],
                     [j for j in ip["journal"] if j.startswith(("autorisation", "piège"))])
            verifier("1re vidéo d'un compte : « Publier la vidéo publiquement ? » → « Publier maintenant », l'étape le dit",
                     "tt_public:publier maintenant" in ip["journal"] and x and any("publiquement" in e_["message"] for e_ in x["etapes"]),
                     [j for j in ip["journal"] if j.startswith("tt_public")])
            verifier("avertissement de TikTok « La situation évolue rapidement dans ton pays » → « Publier » de la fenêtre, "
                     "l'étape le dit, pas celui du bas caché dessous (28/10/2026, publications 1735, 1395 et 1523)",
                     "tt_avert:publier" in ip["journal"] and "piège:tt_avert:Publier du bas touché, sans effet" not in ip["journal"]
                     and x and any("La situation évolue" in e_["message"] for e_ in x["etapes"]),
                     [j for j in ip["journal"] if "tt_avert" in j])
            async def avec_lien(pid):
                _, y = await get(f"/api/publications/{pid}")
                return y if y.get("lien") else None

            x = await attendre(lambda: avec_lien(p["id"]), 30, 1) or x
            verifier("lien de la vidéo retrouvé à part par Scrape Creators, à sa légende (le téléphone était déjà libre)",
                     x and x["lien"] == f"https://www.tiktok.com/@ma_page/video/{ip['tt_posts'][-1]['id']}", x and x["lien"])
            await asyncio.sleep(1)
            verifier("compte choisi au @ exact (ma_page2.4 était actif et contient ma_page), lu sur la capture, après le « chargement… » de 6 s",
                     (ip.get("dernier_post") or {}).get("compte") == "ma_page" and any(j.startswith("tt_comptes:toucher") for j in ip["journal"]),
                     ip["journal"][-12:])
            verifier("« Ajouter un compte » jamais touché", not ip.get("tt_ajout_touche"))
            # TikTok réordonne sa liste après chaque changement de compte (18/10/2026, iPhone 2) : touchées dans l'ordre,
            # les lignes ne passaient jamais par le compte voulu ; elles se reconnaissent maintenant à leur photo
            # avec, en plus, les pastilles des notifications (prises pour des coches le 19/10/2026 : plus aucun TikTok ne
            # partait) et deux comptes à la même photo (@mapage et @mapage2.0)
            modifier_iphone(tt_comptes=["ma_page2.4", "trois", "ma_page"], tt_reordonne=True, tt_bascules=0,
                            tt_actif="ma_page2.4", tt_badges=True, tt_meme_photo=["ma_page2.4", "ma_page"])
            s, pr3 = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:abc.mp4",
                                                      "legende": "x", "repetition": True})
            x3 = await attendre(lambda: fini(pr3["id"]), 180, 1)
            ip3 = lire_iphone()
            verifier("liste des comptes TikTok réordonnée à chaque changement, pastilles de notifications, deux comptes à la même "
                     "photo : le bon compte retrouvé, jamais « Ajouter un compte »",
                     x3 and x3["etat"] == "repete" and ip3.get("tt_actif") == "ma_page" and not ip3.get("tt_ajout_touche"),
                     x3 and (x3["etat"], x3["erreur"], ip3.get("tt_actif"), [e_["message"] for e_ in x3["etapes"]][-6:]))
            modifier_iphone(tt_comptes=["ma_page2.4", "ma_page"], tt_reordonne=False, tt_badges=False, tt_meme_photo=[])
            pr = ip.get("profondeurs") or []
            verifier("arbre lu sur 15 niveaux sur le fil de TikTok, 40 dans la création, 40 remis après", 15 in pr and 25 in pr and pr[-1] == 40, pr)
            liens_csv = lambda: (tmp / "donnees" / "liens.csv").read_text(encoding="utf-8") if (tmp / "donnees" / "liens.csv").exists() else ""   # noqa: E731
            verifier("lien noté dans donnees/liens.csv", bool(x) and f"abc.mp4;{x['lien']}" in liens_csv(), liens_csv())
            # une vidéo refaite dans le centre (même nom, autre rendu, 16/10/2026) : la copie gardée est retéléchargée
            cache = tmp / "donnees" / "videos" / "abc.mp4"
            avant = cache.read_bytes() if cache.exists() else b""
            (tmp / "videos" / "abc.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(200_001))
            s, ess = await post(f"/api/t/{udid}/essai-photos", {"video": "dossier:abc.mp4"})
            verifier("vidéo refaite dans le dossier (autre taille) : recopiée avant de partir, pas l'ancienne copie",
                     s == 200 and bool(avant) and cache.exists() and cache.read_bytes() != avant, (s, ess, len(avant)))
            # une vidéo renvoyée en retouche au moment de partir (contrôle image, 17/10/2026) : reportée, pas ratée ; plus
            # dans le centre (retirée du dossier) : annulée ; dans les deux cas, ni ❌ ni alerte

            async def bougee(pid, mot):
                _, y = await get(f"/api/publications/{pid}")
                return y if any(mot in (e_["message"] or "") for e_ in y.get("etapes", [])) else None

            bientot = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            s, pb = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:ghi.mp4", "legende": "x",
                                                     "repetition": True, "quand": bientot})
            ghi = (tmp / "videos" / "ghi.mp4").read_bytes()
            (tmp / "videos" / "ghi.mp4").unlink()
            yb = await attendre(lambda: bougee(pb["id"], "Annulée"), 60, 1)
            (tmp / "videos" / "ghi.mp4").write_bytes(ghi)
            verifier("vidéo retirée du dossier au moment de partir : annulée, sans échec",
                     s == 200 and yb and yb["etat"] == "annule" and not yb["erreur"],
                     yb and (yb["etat"], [e_["message"] for e_ in yb["etapes"]]))

            async def message_complete(pid, lien):
                m = [y for y in discord("PUBLICATIONS") if f"n° {pid}" in y["tout"]]
                pa = [y for y in discord("PUBLICATIONS", op="patch") if m and y["id"] == m[0]["id"] and lien in (y.get("content") or "")]
                return (m, pa) if pa else None
            mc = await attendre(lambda: message_complete(p["id"], x["lien"] if x else "?"), 10)
            verifier("Discord 📤 publications : un message à la publication (pas à la répétition), complété par son lien",
                     mc and len(mc[0]) == 1 and mc[0][0]["tout"].startswith("✅ TikTok **@ma_page**") and mc[0][0]["wait"] == "true",
                     (mc, discord("PUBLICATIONS")))

            s, p3 = await post("/api/publications", {"compte_id": c["id"], "video": "dossier:abc.mp4", "legende": "encore"})
            await asyncio.sleep(8)
            _, x3 = await get(f"/api/publications/{p3['id']}")
            verifier("rythme : le même compte attend 30 min avant de republier", x3["etat"] == "en_attente", x3["etat"])
            s, _ = await post(f"/api/publications/{p3['id']}/annuler", {})
            verifier("annuler une publication en file", s == 200)

            # sans Wi-Fi (partage de connexion parti, 05/10/2026), rien ne part : la publication attend, puis part au retour du Wi-Fi
            modifier_iphone(wifi=False)

            async def sans_wifi():          # le service relit le Wi-Fi toutes les 10 s : on attend qu'il l'ait vu
                _, c_ = await get("/api/calendrier")
                return any(not t["wifi"] for t in c_.get("telephones", []))
            await attendre(sans_wifi, 30, 1)
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
            # la légende Instagram de tous les comptes du projet : le compte principal du projet principal
            s, prg = await post("/api/programmation", {"legendes_instagram": {"perso": "@moncompte"}})
            leg = {x["identifiant"]: (await get(f"/api/publications/{x['id']}"))[1].get("legende") for x in pr}
            _, cal_l = await get("/api/calendrier")
            verifier("légende Instagram du projet : « @moncompte » sur l'Insta déjà en file, TikTok garde la description du centre",
                     s == 200 and prg.get("legendes_instagram") == {"perso": "@moncompte"} and leg.get("ma.page.ig") == "@moncompte"
                     and leg.get("ma_page") == "Remontage 🔁 #vinted" and cal_l.get("legendes_instagram") == {"perso": "@moncompte"}, (prg, leg))
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
            # la réserve d'une page (centre, 16/10/2026) : annulées, puis reprises ensemble au prochain créneau libre, raison écrite
            for i in ids_pr:
                await post(f"/api/publications/{i}/annuler", {})
            s, rres = await post("/api/publications/reporter", {"ids": ids_pr, "raison": "Réserve de la page Clips 1"})
            pubs_r = [(await get(f"/api/publications/{i}"))[1] for i in ids_pr] if s == 200 else []
            verifier("Reporter avec une raison (réserve d'une page) : les annulées reprises ENSEMBLE, en attente, l'étape le dit",
                     s == 200 and len({x["quand"] for x in pubs_r}) == 1 and all(x["etat"] == "en_attente" for x in pubs_r)
                     and all(x["etapes"][-1]["message"].startswith("Réserve de la page Clips 1 : reportée au") for x in pubs_r),
                     (s, rres, [(x["etat"], x["quand"], x["etapes"][-1:]) for x in pubs_r]))
            s, pc2 = await post("/api/publications", {"compte_id": c2["id"], "video": "dossier:ghi.mp4", "legende": "x",
                                                      "quand": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            s, mele = await post("/api/publications/reporter", {"ids": [ids_pr[0], pc2["id"]]})
            verifier("Reporter : refusé pour deux groupes à la fois", s == 400, (s, mele))
            await post(f"/api/publications/{pc2['id']}/annuler", {})
            # un envoi À LA MAIN en retard part quand même (son rythme : un compte toutes les 30 min, jamais reporté)
            _, c3 = await post("/api/comptes", {"plateforme": "tiktok", "identifiant": "ma_page2.4", "udid": udid,
                                                "groupe": "Clips 2"})   # connu du faux TikTok
            s, envm = await post("/api/envois", {"video": "dossier:ghi.mp4", "comptes": [c3["id"]], "debut": passe,
                                                 "legende": "Envoi à la main en retard"})
            pm = (envm.get("publications") or [{}])[0]
            xm = await attendre(lambda: fini(pm["id"]), 120, 1) if pm.get("id") else None
            verifier("envoi à la main en retard : il part (jamais reporté)", xm and xm["etat"] == "publie" and xm["quand"] == passe
                     and not any("reportée" in e["message"] for e in xm["etapes"]), xm and (xm["etat"], xm["quand"], xm["erreur"]))
            await post(f"/api/comptes/{c3['id']}", {"actif": False})
            verifier("programmé une seule fois (les passages suivants ne doublent rien)", len(d2["publications"]) == 2, d2["publications"])
            if pr:   # le calendrier : la vidéo, à son heure, une fois pour le groupe (TikTok + Insta), et les créneaux du projet
                # le jour de leur heure ACTUELLE (reportées deux fois plus haut : le soir, elles passent au lendemain)
                actuelles = [(await get(f"/api/publications/{x['id']}"))[1] for x in pr]
                jour = min(dt.datetime.fromisoformat(y["quand"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris"))
                           for y in actuelles).date().isoformat()
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
            # une page réglée (une niche, ou un jour 1 sans niche : généraliste) se remplit depuis le centre : « page » le dit
            s, _ = await post("/api/pages", {"projet": "perso", "groupe": "Clips 2", "niche": "", "debut": "2026-10-01"})
            _, dest_p = await get("/api/destinations?video=dossier:abc.mp4")
            par_nom = {g["nom"]: g for g in dest_p.get("groupes", [])}
            verifier("destinations : une page généraliste réglée (jour 1, sans niche) est marquée « page », pas les autres",
                     s == 200 and par_nom.get("Clips 2", {}).get("page") is True and par_nom.get("Clips 1", {}).get("page") is False
                     and par_nom.get("Clips 2", {}).get("niche") is None, dest_p.get("groupes"))
            await post("/api/pages", {"projet": "perso", "groupe": "Clips 2", "niche": "", "debut": ""})
            _, pages_p = await get("/api/pages?projet=perso")
            pp = {x["groupe"]: x for x in pages_p.get("pages", [])}
            verifier("pages : les vidéos qui ont déjà une publication sur la page (le remontage programmé sur Clips 1)",
                     "Clips 1/rem.mp4" in pp.get("Clips 1", {}).get("videos", []) and "Clips 1/rem.mp4" not in pp.get("Clips 2", {}).get("videos", ["rem"]),
                     {k: v.get("videos") for k, v in pp.items()})
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
            modifier_iphone(ig_volet=True)       # 1er reel d'un compte public : le volet qui couvre la légende (18/10/2026)
            s, _ = await post(f"/api/publications/{pi['id']}/relancer", {"repetition": False})
            xi = await attendre(lambda: fini(pi["id"]), 120, 1)
            ip = lire_iphone()
            post_ig = (ip["ig_pubs"].get("ma.page.ig") or [{}])[0]
            verifier("Instagram, 1er reel d'un compte public : le volet « … télécharger et partager vos reels » passé par "
                     "« Continuer » avant la légende, « Gérer les paramètres » jamais touché (18/10/2026)",
                     "ig_volet:continuer" in ip["journal"] and not ip.get("ig_volet_gerer"),
                     [j for j in ip["journal"] if j.startswith(("ig_volet", "ig_final"))])
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

            # ── Instagram, les écrans de Meta par-dessus tout au lancement (21/10/2026, iPhone 1 : 6 reels ratés en
            # « user-switch-title-button ») : jamais touchés, Instagram rouvert ; s'ils restent, un échec clair pour l'utilisateur
            for ecran, titre, piege in (("ig_pubmeta", "fins publicitaires", "ig_pubmeta_touche"),
                                        ("ig_comptemeta", "Votre Compte Meta est disponible", "ig_comptemeta_touche")):
                modifier_iphone(**{ecran: 1, piege: False})
                s, pm = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4",
                                                         "legende": "écran de Meta", "repetition": True})
                xm = await attendre(lambda: fini(pm["id"]), 120, 1)
                ip = lire_iphone()
                verifier(f"Instagram : l'écran de Meta « {titre} » au lancement → Instagram rouvert sans y toucher, la "
                         "publication continue (21/10/2026)",
                         xm and xm["etat"] == "repete" and not ip.get(piege)
                         and any(titre.split()[0] in e["message"] and "rouvert" in e["message"] for e in xm["etapes"]),
                         xm and (xm["etat"], xm["erreur"], [e["message"] for e in xm["etapes"]][:6], ip.get(piege)))
            modifier_iphone(ig_pubmeta=-1, ig_pubmeta_touche=False)
            s, pm = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4",
                                                     "legende": "écran de Meta", "repetition": True})
            xm = await attendre(lambda: fini(pm["id"]), 120, 1)
            ip = lire_iphone()
            modifier_iphone(ig_pubmeta=0)
            verifier("Instagram : l'écran de Meta à chaque lancement → échec qui dit à l'utilisateur quoi faire, « Démarrer » jamais touché",
                     xm and xm["etat"] == "echec" and "réouvertures" in (xm["erreur"] or "") and "Ouvre Instagram" in (xm["erreur"] or "")
                     and not ip.get("ig_pubmeta_touche"),
                     xm and (xm["etat"], xm["erreur"], ip.get("ig_pubmeta_touche")))

            # ── Instagram bloqué sur « Nettoyage du compte » (24/10/2026, iPhone 1, ~40 échecs en « profile-tab ») :
            # échec immédiat qui dit à l'utilisateur de sortir SANS RIEN SUPPRIMER ; ses boutons jamais touchés
            modifier_iphone(ig_nettoyage=True, ig_nettoyage_touche=False)
            s, pn = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4",
                                                     "legende": "nettoyage", "repetition": True})
            xn = await attendre(lambda: fini(pn["id"]), 120, 1)
            ip = lire_iphone()
            modifier_iphone(ig_nettoyage=False)
            verifier("Instagram bloqué sur « Nettoyage du compte » → échec clair (sortir sans rien supprimer), « Tout supprimer » "
                     "et « Choisir le contenu à supprimer » jamais touchés, pas de réouvertures inutiles (24/10/2026)",
                     xn and xn["etat"] == "echec" and "Nettoyage du compte" in (xn["erreur"] or "") and "SANS RIEN SUPPRIMER" in (xn["erreur"] or "")
                     and not ip.get("ig_nettoyage_touche") and not any("rouvert" in e["message"] for e in xn["etapes"]),
                     xn and (xn["etat"], xn["erreur"], [e["message"] for e in xn["etapes"]], ip.get("ig_nettoyage_touche")))

            # ── santé : un compte qui n'est plus connecté dans l'app (clips_deux n'est pas dans le faux TikTok) ─────
            s, pd = await post("/api/publications", {"compte_id": c2["id"], "video": "dossier:ghi.mp4", "legende": "pas connecté"})
            xd = await attendre(lambda: fini(pd["id"]), 120, 1) if s == 200 else None
            alerte_d = await attendre(lambda: asyncio.sleep(0, [y for y in discord("SANTE") if "Compte déconnecté · TikTok @clips_deux" in y["tout"]]), 10)
            verifier("publication ratée (compte plus connecté) : ❌ sur 📤 publications, 🔴 « Compte déconnecté » sur 🩺 santé-pages",
                     xd and xd["etat"] == "echec" and "n'est pas parmi" in xd["erreur"] and alerte_d and len(alerte_d) == 1
                     and any(y["tout"].startswith("❌ TikTok **@clips_deux** · Clips 2") for y in discord("PUBLICATIONS")),
                     (xd and xd["erreur"], discord("SANTE"), [y["tout"][:80] for y in discord("PUBLICATIONS")]))

            # ── la copie d'un essai raté restée dans VLC depuis 3 jours (déposée le 23/10, relancée le 26/10/2026) :
            # réécrite, elle gardait sa date et Photos datait la vidéo du 23/10 ; Instagram refusait « pas celle du jour »
            _, toutes = await get("/api/publications")
            prochain = max(x["id"] for x in toutes) + 1
            reste = tmp / "iphone" / "apps" / "org.videolan.vlc-ios" / "Documents" / "import" / f"auto-{prochain}.mp4"
            reste.parent.mkdir(parents=True, exist_ok=True)
            reste.write_bytes(b"ancien essai")
            il_y_a_3j_ = (dt.date.today() - dt.timedelta(days=3)).isoformat()
            modifier_iphone(vlc_nes={**lire_iphone().get("vlc_nes", {}), reste.name: il_y_a_3j_})
            s, pv = await post("/api/publications", {"compte_id": ig["id"], "video": "dossier:ghi.mp4",
                                                     "legende": "copie restée dans VLC", "repetition": True})
            xv = await attendre(lambda: fini(pv["id"]), 120, 1)
            ip = lire_iphone()
            verifier("Instagram : la copie d'un essai raté restée dans VLC est effacée avant le dépôt, la vidéo est du jour (26/10/2026)",
                     s == 200 and pv["id"] == prochain and xv and xv["etat"] != "echec"
                     and (ip.get("photos_jours") or {}).get(reste.name) == dt.date.today().isoformat(),
                     xv and (pv.get("id"), prochain, xv["etat"], xv["erreur"], ip.get("photos_jours")))

            # ── le créneau d'une vidéo disparue (26/10/2026 : les Comptes 1 et 2 à 0-1 vidéo, leurs vidéos refaites sous un
            # autre nom avant leur tour) : annulée sans échec, et la suivante prête de la page part à sa place, tout de suite
            await post("/api/pages", {"projet": "perso", "groupe": "Clips 1", "niche": "", "debut": "2026-10-01"})
            with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:   # le rythme d'un compte (30 min) : pas l'objet ici
                db.execute("insert or replace into reglages (cle, valeur) values ('intervalle_min', '0')")
            dans = lambda j: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=j)).strftime("%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
            s1, pl1 = await post("/api/calendrier/placer", {"video": "dossier:ghi.mp4", "groupe": "Clips 1", "quand": dans(2)})
            s2, pl2 = await post("/api/calendrier/placer", {"video": "dossier:abc.mp4", "groupe": "Clips 1", "quand": dans(3),
                                                            "legende": "La suivante 🔁"})
            ids1, ids2 = [x["id"] for x in pl1.get("publications", [])], [x["id"] for x in pl2.get("publications", [])]
            _, pg1 = await get("/api/pages?projet=perso")
            c1 = next((x for x in pg1.get("pages", []) if x["groupe"] == "Clips 1"), {})
            verifier("pages : la file compte par compte (l'avance = le compte le moins servi), la profondeur (15), les téléphones",
                     c1.get("a_venir") == 2 and c1.get("profondeur") == 15 and c1.get("telephones") == [udid] and c1.get("en_trop") == [],
                     c1)
            ghi = (tmp / "videos" / "ghi.mp4").read_bytes()
            (tmp / "videos" / "ghi.mp4").unlink()
            bientot = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:
                db.execute(f"update publications set quand = ? where id in ({', '.join('?' * len(ids1))})", (bientot, *ids1))

            async def toutes_annulees(ids):
                ps = [(await get(f"/api/publications/{i}"))[1] for i in ids]
                return ps if ps and all(x["etat"] == "annule" for x in ps) else None
            y1 = await attendre(lambda: toutes_annulees(ids1), 120, 1) or []
            (tmp / "videos" / "ghi.mp4").write_bytes(ghi)
            x2 = [(await get(f"/api/publications/{i}"))[1] for i in ids2]
            verifier("vidéo retirée du dossier : annulée partout sans échec, la suivante de la page garde son créneau",
                     s1 == 200 and s2 == 200 and len(ids1) == 2 and len(x2) == 2 and len(y1) == 2 and all(not y["erreur"] for y in y1)
                     and all(x["etat"] == "en_attente" for x in x2),
                     ([(y["etat"], y["erreur"]) for y in y1], [(x["etat"], x["erreur"]) for x in x2]))
            for i in ids2:
                await post(f"/api/publications/{i}/annuler", {})
            with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:
                db.execute("delete from reglages where cle = 'intervalle_min'")
            await post("/api/pages", {"projet": "perso", "groupe": "Clips 1", "niche": "", "debut": ""})

            # ── le warm-up (chauffe.py, l'utilisateur 07/10/2026 : « un espace où on met les comptes en warm-up et ça warm-up
            # automatiquement pendant une certaine durée », mots-clés de la niche demandés, 40 min par jour) ──────────
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
            wt = [y["tout"] for y in discord("WARMUP") if "@ma_page**" in y["tout"]]
            verifier("Discord 🔥 warm-up : le résumé de la séance (jour, minutes, vidéos, likes, abonnements, mots cherchés)",
                     wt and wt[0].startswith("🔥 TikTok **@ma_page** · Clips 1 · jour 4/7 · ") and "vidéo(s)" in wt[0] and "❤️" in wt[0]
                     and "➕" in wt[0] and "🔎 " in wt[0], (wt, [y["tout"] for y in discord("WARMUP")]))
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
            verifier("Discord 🔥 warm-up : la séance coupée le dit (✂️, et pourquoi)",
                     any(y["tout"].startswith("✂️ TikTok **@ma_page**") and "Coupée : " in y["tout"] for y in discord("WARMUP")),
                     [y["tout"] for y in discord("WARMUP")])

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

            # ── santé des pages (sante.py, l'utilisateur 08/10/2026) : relevé, alertes, hub, rapport du soir, test des salons ───
            t_ = time.time()
            faux["vieux"]["ma_page"] = [{"id": f"vx{i}", "desc": f"ancienne vidéo {i}", "t": int(t_ - 86400 * (2 + i) - 600), "vues": v}
                                            for i, v in enumerate((4, 12, 7, 9))]          # médiane 8 vues : shadowban probable
            faux["vieux"]["ma.page.ig"] = [{"id": f"rx{i}", "desc": f"ancien reel {i}", "t": int(t_ - 3600 * (14 + 6 * i)), "vues": 0}
                                               for i in range(3)]                          # 0 vue sur les reels de 12 h à 48 h
            faux["abonnes"].update({"ma_page": 1234, "ma.page.ig": 567})
            faux["credits"] = 250
            hier = (dt.datetime.now(ZoneInfo("Europe/Paris")).date() - dt.timedelta(days=1)).isoformat()
            with sqlite3.connect(tmp / "donnees" / "telephones.db") as db:      # le relevé de la veille : 1 200 abonnés, 300 vues
                db.execute("insert into releves (compte_id, jour, releve_le, abonnes, posts, erreur) values (?, ?, ?, ?, ?, '')",
                           (c["id"], hier, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_ - 86400)), 1200,
                            json.dumps([{"id": "hx", "vues": 300, "ts": int(t_ - 86400 - 3600), "desc": "", "lien": ""}])))
            n0 = len(faux["discord"])
            s, bilan = await post("/api/sante/relever", {})
            # les messages partent à côté (tâches Discord) : on les attend avant de compter
            await attendre(lambda: asyncio.sleep(0, len(discord("SANTE", n0)) >= 2 and discord("TELEPHONES", n0)), 10)
            await asyncio.sleep(1)
            sa = discord("SANTE", n0)
            verifier("relevé : chaque compte lu (un appel Scrape Creators par compte), les crédits aussi",
                     s == 200 and bilan["comptes"] >= 3 and not bilan["erreurs"] and bilan.get("credits") == 250, bilan)
            verifier("🩺 santé-pages : « Shadowban probable » (médiane 8 vues, 4 posts de 1 à 7 jours) et « Zéro vue » (reels de 12 h à 48 h)",
                     any(y["tout"].startswith("🔴 Shadowban probable · TikTok @ma_page") and "médiane de 8 vues sur ses 4 posts" in y["tout"] for y in sa)
                     and any(y["tout"].startswith("🔴 Zéro vue · Insta @ma.page.ig") for y in sa) and len(sa) == 2, [y["tout"] for y in sa])
            verifier("🛠️ téléphones : crédits Scrape Creators bas (250, sous 300)",
                     any("Crédits Scrape Creators bas" in y["tout"] and "250" in y["tout"] for y in discord("TELEPHONES", n0)),
                     [y["tout"] for y in discord("TELEPHONES", n0)])
            n1 = len(faux["discord"])
            s, _ = await post("/api/sante/relever", {})
            await asyncio.sleep(2)
            verifier("une alerte par compte, par sujet et par jour : le 2e relevé ne répète rien",
                     s == 200 and not discord("SANTE", n1) and not discord("TELEPHONES", n1), [y["tout"] for y in discord(None, n1)])
            s, hb = await get("/api/hub")
            pages_ = {pg["nom"]: pg for pg in hb.get("pages", [])}
            ct = next((x for x in pages_.get("Clips 1", {}).get("comptes", []) if x["identifiant"] == "ma_page"), {})
            verifier("hub : Clips 1 en alerte, en tête ; son TikTok : shadowban, 1 234 abonnés (+34 sur la veille), médiane 7 j, courbe",
                     s == 200 and hb["pages"][0]["nom"] == "Clips 1" and pages_["Clips 1"]["etat"] == "rouge" and ct.get("etat") == "rouge"
                     and any("Shadowban probable" in r for r in ct["raisons"]) and ct["abonnes"] == 1234 and ct["abonnes_delta"] == 34
                     and ct["mediane_7j"] == 8 and len(ct["serie"]) == 2 and ct["serie"][0]["vues_24h"] == 300 and ct["telephone"]["pret"],
                     (hb.get("pages"), ct))
            cd = next((x for x in pages_.get("Clips 2", {}).get("comptes", []) if x["identifiant"] == "clips_deux"), {})
            verifier("hub : le compte déconnecté en rouge avec sa raison, son échec du jour ; alertes, crédits, salons, totaux",
                     cd.get("etat") == "rouge" and any("déconnecté" in r for r in cd["raisons"]) and cd["jour"]["echec"] >= 1
                     and hb["scrape"]["credits"] == 250 and hb["scrape"]["cle"] and len(hb["discord"]) == 5
                     and any("Shadowban" in a["message"] for a in hb["alertes"]) and hb["jour"]["ok"] >= 2,
                     (cd, hb.get("scrape"), hb.get("jour"), hb.get("alertes")))
            s, vj = await get("/api/vues?jours=14")
            jv, auj_ = {x["jour"]: x for x in vj.get("jours", [])}, dt.datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
            verifier("vues des pages : la veille, les 300 vues du post de moins de 24 h (premier relevé du compte) ; aujourd'hui "
                     "relevé, les publications du jour ; chaque semaine additionne ses jours",
                     s == 200 and jv.get(hier, {}).get("tiktok") == 300 and jv.get(hier, {}).get("comptes") == 1
                     and jv.get(auj_, {}).get("comptes", 0) >= 1 and jv.get(auj_, {}).get("publiees", 0) >= 2
                     and sum(x["vues"] for x in vj["semaines"]) == sum(x["vues"] or 0 for x in vj["jours"]), vj)
            n2 = len(faux["discord"])
            s, _ = await post("/api/sante/rapport", {})
            rap = await attendre(lambda: asyncio.sleep(0, discord("RAPPORT", n2)), 10)
            verifier("📊 rapport-du-jour : le bilan, une carte par page (Clips 1 : 🔴, abonnés et écart sur la veille)",
                     s == 200 and rap and rap[0]["tout"].startswith("📊 **Bilan du") and "📄 Clips 1" in rap[0]["tout"]
                     and "TikTok @ma_page 🔴" in rap[0]["tout"] and "👥 1 234 (+34)" in rap[0]["tout"], rap and rap[0]["tout"])
            n4 = len(faux["discord"])
            s, ag = await post("/api/sante/agent", {"titre": "Réparé : TikTok", "texte": "La coche…", "niveau": "vert"})
            msg = discord("SANTE", n4)
            verifier("le compte rendu de l'agent réparateur dans 🩺 santé-pages (le webhook reste sur le PC)",
                     s == 200 and ag.get("ok") and msg and msg[0]["tout"].startswith("🛠️ Réparé : TikTok"), (s, ag, msg[:1]))
            s, td = await post("/api/sante/test-discord", {})
            verifier("tester Discord : un message dans chacun des 5 salons",
                     s == 200 and td == {k: True for k in ("PUBLICATIONS", "RAPPORT", "SANTE", "TELEPHONES", "WARMUP")}, td)
            async with h.get(f"{base}/calendrier") as rh, h.get(f"{base}/i/hub.js") as rj, h.get(f"{base}/i/vues.js") as rv:
                page_ = await rh.text()
                verifier("le hub servi en tête de l'onglet Calendrier, et les vues des pages",
                         rh.status == 200 and "hub.js" in page_ and "vues.js" in page_ and rj.status == 200 and rv.status == 200)

            n3 = len(faux["discord"])
            modifier_iphone(branche=False)

            async def debranche():
                _, e = await get("/api/etat")
                t = e["parc"]["telephones"][0]
                return t if not t["branche"] else None

            t = await attendre(debranche, 15)
            verifier("débranchement vu, avec la consigne", t and t["etapes"][0]["etat"] == "ko" and "Rebranche" in t["etapes"][0]["aide"], t)
            de_jour = 9 <= dt.datetime.now(ZoneInfo("Europe/Paris")).hour < 23
            if de_jour:
                hl = await attendre(lambda: asyncio.sleep(0, [y for y in discord("TELEPHONES", n3) if "hors ligne" in y["tout"]]), 15)
                verifier("vigie : iPhone hors ligne (30 min ; 3 s ici) → 📵 sur 🛠️ téléphones, avec l'étape bloquée et la consigne",
                         hl and len(hl) == 1 and "Rebranche" in hl[0]["tout"], [y["tout"] for y in discord("TELEPHONES", n3)])
            modifier_iphone(branche=True)
            verifier("rebranché : de nouveau prêt", await attendre(pret, 60))
            if de_jour:
                rv = await attendre(lambda: asyncio.sleep(0, [y for y in discord("TELEPHONES", n3) if "de nouveau prêt" in y["tout"]]), 10)
                verifier("vigie : le retour annoncé (🟢 de nouveau prêt)", rv, [y["tout"] for y in discord("TELEPHONES", n3)])
            else:
                await asyncio.sleep(5)
                verifier("vigie : la nuit (23 h – 9 h), pas d'alerte hors ligne",
                         not [y for y in discord("TELEPHONES", n3) if "hors ligne" in y["tout"]], [y["tout"] for y in discord("TELEPHONES", n3)])
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
