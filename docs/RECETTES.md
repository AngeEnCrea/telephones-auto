# Recaler une recette (quand TikTok ou Instagram changent)

Une **recette** (`service/recettes/tiktok.py`, `instagram.py`) est le parcours que fait le robot dans une app :
ouvrir, passer sur le bon compte, créer, choisir la vidéo, écrire la légende, publier ; et, pour le warm-up, chercher,
regarder, liker, s'abonner. Les apps changent leurs écrans : un jour, une étape casse. Le service le dit (« introuvable
à l'écran : … », « toujours pas à l'écran après 20 s : … ») et garde la capture et l'arbre de l'écran.

## Les principes

- **Les boutons par leur nom, pas par leurs coordonnées.** Chaque élément a un nom d'accessibilité (ce que VoiceOver
  lirait) : `label` (le texte, dans la langue de l'iPhone) ou `name` (un identifiant, souvent stable : Instagram en
  a partout : `profile-tab`, `creation-reel`, `like-button`…). Un bouton déplacé reste trouvé ; un bouton renommé
  casse net et le dit.
- **Le nom EXACT des comptes** : `mapage` est contenu dans `mapage2.0` ; un « contient » publierait sur le mauvais
  compte.
- **Lire l'arbre peu profond.** L'arbre de TikTok est immense : au-delà de ~15 niveaux sur le fil, l'agent met plus
  d'une minute. Chaque recette fixe sa profondeur (`r.a.profondeur(n)`) écran par écran.
- **Sur un fil vidéo de TikTok, aucun geste aux coordonnées** : ni toucher ni glisser à (x, y) (plus de 2 min, l'agent
  bloqué). Les gestes passent par la fenêtre de l'app (`await r.a.fenetre()` sur 2 niveaux, puis `glisser_sur`,
  `toucher_sur`, `double_sur`). Ce qui n'est pas dans l'arbre se lit sur la capture (couleur, taches).
- **Toujours une preuve** : après un geste, relire l'écran (le bouton a changé, l'écran suivant est là), sinon
  s'arrêter avec un message clair. Jamais de « ça devrait marcher ».
- **Les pièges se notent en tête de la recette, avec la date** où ils ont été vus.

## La méthode (avec Claude)

1. **La publication qui casse** : ouvre-la dans la page ; sa dernière capture montre l'écran inattendu, et
   `donnees/captures/<n°>/arbre-echec.json` son arbre.
2. **Sur l'iPhone** (file en pause, ⏸) : amène l'app sur cet écran à la main (écran en direct), puis le bouton
   **Arbre** : chaque élément avec son nom, son type et sa place. (Ou `GET /api/t/<udid>/arbre`.)
3. **Corrige la recette** avec ce nom, et note le piège en tête du fichier.
4. **Mets le piège dans le faux iPhone** (`tests/faux_iphone.py`) : le même écran, les mêmes noms, le même piège.
   Ainsi il ne reviendra jamais sans que les essais le voient.
5. **`python tests/essai_local.py`** doit repasser entièrement au vert (macOS ou Linux).
6. **Une Répétition sur le vrai iPhone** (relance le service si besoin), regarde le déroulé ; puis une vraie
   publication.

## Ajouter une plateforme

Une recette = une fonction `publier(r, compte, legende)` (et `chauffer(r, compte, seance)` pour le warm-up), déclarée
dans `service/recettes/__init__.py` (`RECETTES`, `PRETES`, `APPS`, `CHAUFFES`). YouTube n'est pas écrit : sa place est
prête (`_youtube`).
