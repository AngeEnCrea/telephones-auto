"""videos.py : les vidéos à publier, dans un dossier (réglage « videos » de lieux.json ; par défaut videos/ à côté du
code). C'est le verrou : seul ce qui est dans ce dossier peut partir, et le fichier est relu au moment de publier.

  videos/
    ma-video.mp4                 une vidéo à publier à la main (onglet Publications › Nouvelle publication)
    ma-video.txt                 sa légende (même nom : texte, émojis, retours à la ligne)
    Groupe 1/                    le nom d'un groupe de comptes (onglet Comptes, champ « groupe »)
      autre-video.mp4            part TOUTE SEULE sur les comptes du groupe, au prochain créneau libre
      autre-video.txt            (si la programmation automatique est activée ; une seule fois par vidéo)
    _archives/                   un dossier qui commence par « _ » ou « . » est ignoré

Une vidéo est reconnue à son chemin dans le dossier (« dossier:Groupe 1/autre-video.mp4 ») : la renommer ou la
déplacer en fait une nouvelle vidéo."""
import csv
import logging
import shutil
import time
from pathlib import Path

import lieux

log = logging.getLogger("videos")
PREFIXE = "dossier:"
PROJET = "perso"              # un seul « projet » : tous les comptes et toutes les vidéos de ce téléphone
EXTENSIONS = (".mp4", ".mov", ".m4v")


def dossier():
    lieux.VIDEOS.mkdir(parents=True, exist_ok=True)
    return lieux.VIDEOS


def cle_de(chemin):
    return PREFIXE + chemin.relative_to(dossier()).as_posix()


def decouper(cle):
    """« dossier:<chemin> » → (projet, chemin dans le dossier)."""
    return PROJET, cle[len(PREFIXE):]


def fichier(cle):
    """Le fichier d'une vidéo, toujours DANS le dossier des vidéos (un chemin qui en sortirait est refusé)."""
    if not cle.startswith(PREFIXE):
        raise RuntimeError("vidéo inconnue : seules les vidéos du dossier peuvent partir")
    base = dossier().resolve()
    f = (base / cle[len(PREFIXE):]).resolve()
    if base not in f.parents:
        raise RuntimeError("chemin de vidéo refusé")
    return f


def legende(f):
    t = f.with_suffix(".txt")
    try:
        return t.read_text(encoding="utf-8-sig").strip()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


async def projets(http=None):
    return [{"slug": PROJET, "nom": "Mes vidéos", "emoji": "🎬"}]


async def videos_publiables(http=None):
    """Les vidéos du dossier, des plus anciennes aux plus récentes (la programmation les prend dans cet ordre)."""
    base = dossier()
    out = []
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(base)
        if f.suffix.lower() not in EXTENSIONS or not f.is_file() or len(rel.parts) > 2 \
                or any(p.startswith(("_", ".")) for p in rel.parts):
            continue
        out.append({"cle": cle_de(f), "projet": "Mes vidéos", "emoji": "🎬", "titre": f.stem, "type": "short",
                    "statut": "valide", "description": legende(f), "groupe": rel.parts[0] if len(rel.parts) == 2 else None,
                    "origine": None, "vignette": None, "modifiee": f.stat().st_mtime})
    out.sort(key=lambda v: v["modifiee"])
    return out


async def verifier_publiable(http, cle):
    """Relue au moment de publier : une vidéo retirée du dossier entre-temps ne part pas."""
    f = fichier(cle)
    if not f.is_file():
        raise RuntimeError("la vidéo n'est plus dans le dossier des vidéos : rien ne part")
    return {"fichier": str(f)}


async def telecharger(http, cle, destination):
    """La copie de travail de la vidéo (le service ne touche jamais l'original)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fichier(cle), destination)
    return destination


def nom_de_travail(cle):
    """Un nom de fichier sûr pour la copie de travail (le chemin dans le dossier, aplati)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in decouper(cle)[1])


async def signaler_publication(http, cle, url):
    """Le lien d'une vidéo en ligne, noté dans donnees/liens.csv (date, vidéo, lien) : à garder, ou à suivre ailleurs."""
    f = lieux.DONNEES / "liens.csv"
    neuf = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        if neuf:
            w.writerow(["date", "video", "lien"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), decouper(cle)[1], url])
    return {"ok": True}
