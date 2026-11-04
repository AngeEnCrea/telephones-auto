"""Les recettes de publication, une par plateforme : `publier(robot, compte, legende)` rend le lien de la
publication (ou None en répétition). TikTok d'abord (01/10/2026), Instagram le 04/10/2026, YouTube Shorts par l'app YT Studio le 25/10/2026."""
from recettes import instagram, tiktok, youtube
from recettes.base import ErreurPublication


async def _youtube_chauffe(r, compte, s):
    raise ErreurPublication("le warm-up YouTube n'est pas encore écrit")


RECETTES = {"tiktok": tiktok.publier, "instagram": instagram.publier, "youtube": youtube.publier}
CHAUFFES = {"tiktok": tiktok.chauffer, "instagram": instagram.chauffer, "youtube": _youtube_chauffe}   # warm-up (chauffe.py)
LISTES = {"tiktok": tiktok.lister_comptes, "instagram": instagram.lister_comptes}   # les comptes connectés (inventaire.py)
PRETES = {"tiktok": True, "instagram": True, "youtube": True}   # recette écrite (le bouton du centre ne propose que celles-là) ; YouTube = app YT Studio (25/10/2026)
APPS = {"tiktok": tiktok.BUNDLE, "instagram": instagram.BUNDLE, "youtube": youtube.BUNDLE}
PROFONDEURS = {tiktok.BUNDLE: tiktok.PROFONDEUR, instagram.BUNDLE: instagram.PROFONDEUR_PROFIL}   # apps dont l'arbre se lit moins profond (wda.PROFONDEUR)
