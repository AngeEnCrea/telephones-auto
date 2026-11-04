# S'en servir

La page : http://127.0.0.1:4330/telephones/ (sur l'ordinateur). Trois pages, reliées en haut : **📱 Téléphones**,
**📅 Calendrier**, **🔥 Warm-up**.

## La page Téléphones

- **À gauche** : le téléphone, ses étapes de préparation (toutes vertes = prêt), sa batterie. Un bouton « Essai : une
  vidéo dans Photos » prouve le câble, VLC et le Raccourci.
- **Au milieu** : l'écran de l'iPhone en direct. Clic = toucher, glisser = swipe, appui long, molette = défiler,
  clavier = écrire. Le bouton **Arbre** montre les éléments de l'écran avec leur nom (pour recaler une recette).
  Quand le robot travaille, l'écran se voile : les gestes à la main attendent la fin.
- **En haut** : **⏸ Pause** met la file en pause (rien ne démarre ; une séance de warm-up s'arrête).
- **À droite**, trois onglets :
  - **Publications** : la programmation automatique, une nouvelle publication, la liste (en cours, en attente,
    faites, ratées). Une publication ouverte montre son déroulé, une capture par étape, et les boutons utiles
    (Relancer, Publier pour de vrai, C'est en ligne ✓…) ;
  - **Comptes** : ajouter un compte (plateforme, @ exact, téléphone, groupe), changer son groupe, le désactiver ;
  - **Journal** : ce que fait le service.

## Le dossier des vidéos

```
videos/
  ma-video.mp4            à publier à la main (Publications › Nouvelle publication)
  ma-video.txt            sa légende (même nom ; émojis et retours à la ligne compris)
  Groupe 1/               le nom exact d'un groupe de comptes
    autre.mp4             part TOUTE SEULE sur les comptes du groupe, au prochain créneau libre
    autre.txt
  _archives/              un dossier qui commence par « _ » est ignoré
```

- Formats : `.mp4`, `.mov`, `.m4v` (vertical 9:16 pour TikTok et les Reels).
- Une vidéo d'un dossier de groupe n'est programmée **qu'une fois** (sur tous les comptes du groupe ensemble), dans
  l'ordre où tu les as déposées. La renommer ou la déplacer en fait une nouvelle vidéo.
- C'est le verrou : seul ce qui est dans `videos/` peut partir, et le fichier est relu au moment de publier (retiré
  entre-temps, il ne part pas). Ne mets dans un dossier de groupe que ce qui doit sortir.
- Le service n'abîme jamais l'original : il en fait une copie de travail dans `donnees/videos/`.

## La programmation automatique

Onglet Publications › « Programmation automatique » : case **Activée**, et les **créneaux** (heure de Paris ;
`09:00,12:00,15:00,18:00,21:00` par défaut).

- Chaque vidéo d'un dossier de groupe prend le **prochain créneau libre** du groupe, à **± 15 min tirées au hasard**
  (jamais deux jours pareils : 12 h 11, 14 h 56…).
- Plusieurs groupes se **répartissent entre deux créneaux** (2 groupes : le 2e à +1 h 30), pour que le téléphone ne
  publie pas tout d'un coup.
- Un même compte publie **au plus une fois toutes les 30 min**.
- **Un créneau manqué** de plus de 30 min (ordinateur éteint, iPhone débranché ou sans réseau, file en pause) n'est
  pas rattrapé en rafale : la vidéo passe au prochain créneau libre de son groupe. Les envois à la main ne sont
  jamais reportés.
- **Publier seulement en Wi-Fi** (case) : sans Wi-Fi, les publications attendent au lieu d'échouer (utile si l'iPhone
  n'a pas de forfait de données ; à décocher s'il en a un).

## Le hub

En tête de la page **📅 Calendrier** : un tableau de bord par projet.

- une tuile par page : ses vues, ses abonnés, ses alertes ; l'état des téléphones et de l'agent ; les crédits ;
- **Vues des pages** : les vues gagnées jour par jour et semaine par semaine ;
- les règles de santé, compte par compte : shadowban probable (médiane sous 30 vues sur au moins 3 posts de 24 h à 7
  jours), zéro vue, chute des vues, 2 échecs d'affilée, compte déconnecté.

Il faut une clé Scrape Creators pour les vues, et des webhooks Discord pour recevoir les alertes
([`INSTALLATION.md`](INSTALLATION.md)). Sans eux, la vigie des téléphones et les échecs restent visibles ici.

## Les pages et le rythme

Une **page** est un groupe de comptes (le TikTok et l'Insta d'une même marque, par exemple) avec une **niche** et un
**jour 1**, réglés par `POST /telephones/api/pages`. Claude Code peut le faire pour toi : « règle la page Groupe 1 ».

- **Montée en charge** : 1 vidéo le jour 1, 2 le jour 2… jusqu'à 5 par jour (réglage `dose`). TikTok et Insta d'une même
  vidéo comptent pour une.
- **La file** garde 3 jours d'avance par compte ; le reste attend dans le dossier, sans perdre sa place.
- **Une vidéo retirée du dossier** est annulée partout, sans échec ; son créneau redevient libre.
- **L'objectif** (`objectifs` de `POST /telephones/api/programmation`) : un total de publications par jour pour un projet ;
  ce qui manque à la dose normale part en renfort sur les pages déjà pleines. Ne le pousse pas sur des comptes jeunes.
- **Plusieurs iPhone** : chaque compte est rattaché au sien, et chaque iPhone travaille de son côté. **Plusieurs
  projets** sur un même iPhone ne se gênent pas : le second se place dans les trous de la grille du premier.

## Le calendrier

Une semaine, un jour par colonne ; chaque vidéo avec son heure, son groupe et l'état de chaque réseau (⏳ prévue,
🔄 en cours, ✓ en ligne, ✕ ratée) ; les créneaux encore libres en pointillés. Une entrée ouverte :

- **⏭ Reporter au prochain créneau** (une publication prévue) ;
- **Reprogrammer au prochain créneau** (une ratée : TikTok et Insta ensemble) ;
- **Annuler** (le créneau redevient libre) ;
- **Pas en ligne ✕** (notée publiée mais rien sur le compte : elle passe en ratée, à reprogrammer).

Et aussi : **🗑** sur une publication prévue (elle va à la **corbeille**, d'où on la restaure), **▶ Publier maintenant**, la
colonne **À programmer** (les vidéos à la racine de `videos/`, à poser sur un créneau libre), les **reels d'essai**
d'Instagram et le partage sur Facebook, projet par projet.

## Le warm-up des comptes

Page **🔥 Warm-up**. Un compte neuf qui publie tout de suite est souvent peu montré : le warm-up le fait d'abord
« vivre » quelques jours dans sa niche.

1. **Rafraîchir les comptes** : chaque iPhone lit ses comptes TikTok et Insta et ajoute ceux qui manquent. Coche-en un
   ou plusieurs.
2. Les **mots-clés de la niche**, un par ligne (ce que le compte va chercher puis regarder).
3. La **durée** (7 jours par défaut) et les **minutes par jour** (40 par défaut : 3 séances d'environ 13 min).
4. Les cases : liker (dès le 2e jour, 12 par jour au plus, seulement des vidéos de la niche ; sur Instagram aussi quelques
   commentaires du haut, 15 par jour au plus), s'abonner (dès le 3e jour, 10 par jour et 3 par séance au plus),
   **bloquer les publications** du compte pendant le warm-up (au choix).

**Plusieurs comptes** sur un iPhone passent chacun leur tour (celui qui a le moins scrollé d'abord). **⏸ Pause** arrête
tous les warm-ups sans toucher aux publications.

**⚡ Warm-up rapide** : pas de dose par jour, des séances d'affilée jusqu'à l'heure de fin, la nuit comprise, pour un compte
à lancer vite. Les plafonds valent alors pour tout le warm-up, pas par jour. C'est moins naturel qu'un warm-up de
7 jours : à garder pour un besoin précis.

Chaque jour, les séances tombent à des heures tirées au hasard entre 9 h et 23 h, toujours entre deux publications
(une publication passe avant : une séance s'arrête 2 min avant). Une séance : un mot-clé cherché, les vidéos de la
niche regardées (certaines en entier, d'autres passées vite), puis le fil « Pour toi » ou les Reels. **Jamais de
commentaire ni de message.** Chaque compte montre son jour (X sur N), ses séances du jour, ses chiffres, et le journal
de chaque séance avec ses captures. Au bout des N jours, le warm-up passe « terminé » et, si ses publications étaient
bloquées, le compte rentre dans la rotation des créneaux.

Les vidéos se chargent sur le réseau de l'iPhone : ≈ 0,7 Go par heure de scroll (la page affiche l'estimation).

## Les liens et les vues

Avec une clé Scrape Creators (voir [`INSTALLATION.md`](INSTALLATION.md)), le lien de chaque vidéo publiée est
retrouvé à part (le téléphone passe tout de suite à la suite), affiché dans la publication et le calendrier, et noté
dans `donnees/liens.csv`.
