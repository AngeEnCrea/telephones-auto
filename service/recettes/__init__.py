"""Les recettes de publication, une par plateforme : `publier(robot, compte, legende)` rend le lien de la
publication (ou None en répétition). TikTok d'abord (01/10/2026), Instagram le 04/10/2026, YouTube plus tard."""
from recettes import instagram, tiktok
from recettes.base import ErreurPublication


async def _youtube(r, compte, legende):
    raise ErreurPublication("la recette YouTube n'est pas encore écrite : TikTok d'abord")


async def _youtube_chauffe(r, compte, s):
    raise ErreurPublication("le warm-up YouTube n'est pas encore écrit")


RECETTES = {"tiktok": tiktok.publier, "instagram": instagram.publier, "youtube": _youtube}
CHAUFFES = {"tiktok": tiktok.chauffer, "instagram": instagram.chauffer, "youtube": _youtube_chauffe}   # warm-up (chauffe.py)
PRETES = {"tiktok": True, "instagram": True, "youtube": False}   # recette écrite (l'interface ne propose que celles-là)
APPS = {"tiktok": tiktok.BUNDLE, "instagram": instagram.BUNDLE, "youtube": "com.google.ios.youtube"}
PROFONDEURS = {tiktok.BUNDLE: tiktok.PROFONDEUR, instagram.BUNDLE: instagram.PROFONDEUR_PROFIL}   # apps dont l'arbre se lit moins profond (wda.PROFONDEUR)
