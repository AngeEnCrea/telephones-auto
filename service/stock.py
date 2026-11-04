"""stock.py : ce que le service retient, dans SQLite (donnees/telephones.db) : les comptes
et le téléphone où chacun est connecté, la file des publications, et le déroulé de chacune (une ligne et une capture
d'écran par étape). Heures en UTC ISO (« 2026-10-01T08:00:00Z ») : l'interface les montre à l'heure de Paris."""
import datetime as dt
import json
import sqlite3

import lieux

PLATEFORMES = ("tiktok", "instagram", "youtube")
ETATS = ("en_attente", "en_cours", "publie", "repete", "echec", "annule")

SCHEMA = """
create table if not exists comptes (
  id integer primary key,
  plateforme text not null check (plateforme in ('tiktok', 'instagram', 'youtube')),
  identifiant text not null,                 -- le @ du compte
  udid text,                                 -- le téléphone où il est connecté
  client text not null default '',           -- à qui il sert
  note text not null default '',
  actif integer not null default 1,
  cree_le text not null,
  unique (plateforme, identifiant)
);
create table if not exists publications (
  id integer primary key,
  compte_id integer not null references comptes(id),
  video text not null,                       -- « dossier:<chemin dans videos/> » (videos.py)
  titre text not null default '',            -- le titre de la production, pour s'y retrouver
  legende text not null default '',
  quand text,                                -- UTC ISO ; vide : dès que possible
  repetition integer not null default 0,     -- 1 : tout le parcours, sans toucher le dernier « Publier »
  etat text not null default 'en_attente'
    check (etat in ('en_attente', 'en_cours', 'publie', 'repete', 'echec', 'annule')),
  etape text not null default '',
  erreur text not null default '',
  lien text not null default '',
  cree_le text not null,
  debut text, fin text,
  tentatives integer not null default 0
);
create table if not exists etapes (
  id integer primary key,
  publication_id integer not null references publications(id),
  n integer not null,
  le text not null,
  message text not null,
  capture text                               -- fichier JPEG dans captures/<publication>/
);
create table if not exists reglages (cle text primary key, valeur text not null);
create table if not exists pages (             -- les pages de niche : un groupe de comptes (TikTok + Insta)
  projet text not null,
  groupe text not null,
  niche text not null default '',              -- ce que la page publie (« cuisine »…)
  debut text,                                  -- son jour 1 (AAAA-MM-JJ, Paris) : 1 vidéo ce jour-là, 2 le lendemain… jusqu'à 5
  maj_le text not null,
  primary key (projet, groupe)
);
create table if not exists envois (          -- une vidéo envoyée à plusieurs comptes d'un coup (bouton du centre)
  id integer primary key,
  video text not null,
  titre text not null default '',
  ecart_min integer not null default 30,     -- un groupe de comptes toutes les N minutes
  cree_le text not null
);
create index if not exists publications_etat on publications (etat, quand);
create table if not exists chauffes (          -- un compte en warm-up : il scrolle sa niche N jours
  id integer primary key,
  compte_id integer not null references comptes(id),
  mots text not null default '',              -- les mots-clés de la niche, un par ligne
  jours integer not null default 7,
  minutes_jour integer not null default 40,
  likes integer not null default 1,           -- like des vidéos de la niche (à partir du 2e jour)
  abonnements integer not null default 1,     -- suit quelques comptes de la niche (à partir du 3e jour)
  bloque integer not null default 1,          -- aucune publication sur ce compte tant que le warm-up dure
  debut text not null, fin text not null,     -- UTC ISO
  etat text not null default 'en_cours' check (etat in ('en_cours', 'termine', 'arrete')),
  cree_le text not null
);
create table if not exists seances (            -- une séance de scroll d'un warm-up
  id integer primary key,
  chauffe_id integer not null references chauffes(id),
  rang integer,                               -- la séance du jour prévue (0, 1, 2…) ; vide : lancée à la main
  debut text not null, fin text,
  etat text not null default 'en_cours' check (etat in ('en_cours', 'faite', 'coupee', 'echec')),
  minutes real not null default 0,            -- durée visée
  minutes_faites real not null default 0,     -- durée regardée pour de vrai
  vues integer not null default 0, likes integer not null default 0, abonnements integer not null default 0,
  recherches integer not null default 0,
  mots text not null default '',              -- ce qui a été cherché
  journal text not null default '',           -- « HH:MM:SS message [capture] », une ligne par étape
  erreur text not null default ''
);
create table if not exists releves (            -- les vues des derniers posts d'un compte (sante.py, Scrape Creators)
  id integer primary key,
  compte_id integer not null references comptes(id),
  jour text not null,                         -- jour de Paris (AAAA-MM-JJ) : un relevé par compte et par jour, le dernier gardé
  releve_le text not null,
  abonnes integer,
  posts text not null default '[]',           -- [{id, vues, ts, desc}] des posts récents, du plus récent au plus ancien
  erreur text not null default '',
  unique (compte_id, jour)
);
create table if not exists alertes (            -- les alertes envoyées sur Discord : une par sujet, par type et par jour au plus
  id integer primary key,
  cle text not null,                          -- « compte:12 », « telephone:<udid> », « scrape »
  type text not null,                         -- shadowban, zero_vue, chute, echecs, deconnecte, hors_ligne, signature, credits…
  jour text not null,
  niveau text not null default 'rouge',       -- rouge, orange, info
  message text not null,
  cree_le text not null,
  unique (cle, type, jour)
);
create index if not exists chauffes_etat on chauffes (etat, compte_id);
create index if not exists seances_chauffe on seances (chauffe_id, debut);
"""

# colonnes ajoutées après la première version (02/10/2026) : une base existante les reçoit au démarrage
MIGRATIONS = [
    ("comptes", "projet", "alter table comptes add column projet text not null default ''"),   # « perso » (videos.PROJET)
    ("comptes", "groupe", "alter table comptes add column groupe text not null default ''"),   # « Clips 1 » : TikTok + Insta d'un même compte clip
    ("publications", "envoi_id", "alter table publications add column envoi_id integer references envois(id)"),
    # 1 : mis en file par la programmation (programmation.py), qui reporte ses créneaux manqués (06/10/2026) ; avant
    # cette colonne, ses envois étaient les seuls à écart 0 (ceux du bouton 📤 Publier : 30 min)
    ("envois", "auto", ("alter table envois add column auto integer not null default 0",
                        "update envois set auto = 1 where ecart_min = 0")),
    # le message Discord de la publication (salon 📤 publications), complété par son lien quand il arrive (08/10/2026)
    ("publications", "discord", "alter table publications add column discord text not null default ''"),
    # le warm-up rapide (13/10/2026, « un fast warm-up ce soir + cette nuit ») : des séances d'affilée jusqu'à la fin
    ("chauffes", "rapide", "alter table chauffes add column rapide integer not null default 0"),
    # les likes de commentaires du warm-up
    ("seances", "likes_commentaires", "alter table seances add column likes_commentaires integer not null default 0"),
    # les choix d'une publication pour la recette, en JSON 
    ("publications", "options", "alter table publications add column options text not null default ''"),
    # La corbeille ne contient que les suppressions manuelles, jamais la réserve ou les annulations du robot.
    ("publications", "supprime_le", (
        "alter table publications add column supprime_le text",
        """update publications set supprime_le = fin where etat = 'annule' and repetition = 0
             and not exists (select 1 from etapes e where e.publication_id = publications.id
                             and (e.message like 'Mise en réserve :%' or e.message like 'Annulée : la vidéo%'))""")),
]


def maintenant():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def il_y_a(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Stock:
    def __init__(self, chemin=None):
        self.chemin = chemin or lieux.DONNEES / "telephones.db"
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.chemin, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode = wal")
        self.db.execute("pragma foreign_keys = on")
        self.db.executescript(SCHEMA)
        for table, colonne, sql in MIGRATIONS:
            if colonne not in {r["name"] for r in self.db.execute(f"pragma table_info({table})")}:
                for requete in ((sql,) if isinstance(sql, str) else sql):
                    self.db.execute(requete)
        self.db.execute("create index if not exists publications_envoi on publications (envoi_id)")
        try:   # les @ en minuscules (TikTok et Instagram ne font pas la différence) ; un doublon de casse resterait tel quel
            self.db.execute("update comptes set identifiant = lower(identifiant) where identifiant <> lower(identifiant)")
        except sqlite3.IntegrityError:
            pass

    def _l(self, sql, *a):
        return [dict(r) for r in self.db.execute(sql, a)]

    def _1(self, sql, *a):
        r = self.db.execute(sql, a).fetchone()
        return dict(r) if r else None

    # ── réglages ────────────────────────────────────────────────────────────────────────────────────────
    def reglage(self, cle, defaut=None):
        r = self._1("select valeur from reglages where cle = ?", cle)
        return r["valeur"] if r else defaut

    def reglages_prefixe(self, prefixe):
        return {r["cle"]: r["valeur"] for r in self._l("select cle, valeur from reglages where cle like ?", prefixe + "%")}

    def legendes_en_file(self, projet, plateforme, legende):
        """Les publications pas encore parties d'un projet sur une plateforme prennent cette légende ; rend leur nombre."""
        cur = self.db.execute("""update publications set legende = ? where etat = 'en_attente'
                                 and compte_id in (select id from comptes where projet = ? and plateforme = ?)""",
                              (legende, projet, plateforme))
        return cur.rowcount

    def poser_reglage(self, cle, valeur):
        self.db.execute("insert into reglages (cle, valeur) values (?, ?) on conflict (cle) do update set valeur = excluded.valeur",
                        (cle, str(valeur)))

    # ── comptes ─────────────────────────────────────────────────────────────────────────────────────────
    def comptes(self):
        return self._l("""select c.*, (select max(fin) from publications p where p.compte_id = c.id and p.etat = 'publie') as derniere
                          from comptes c order by c.actif desc, c.plateforme, c.identifiant""")

    def compte(self, cid):
        return self._1("select * from comptes where id = ?", cid)

    def ajouter_compte(self, plateforme, identifiant, udid=None, client="", note="", projet="", groupe=""):
        identifiant = identifiant.strip().lstrip("@").lower()
        if plateforme not in PLATEFORMES or not identifiant:
            raise ValueError("plateforme ou identifiant invalide")
        cur = self.db.execute("""insert into comptes (plateforme, identifiant, udid, client, note, projet, groupe, cree_le)
                                 values (?, ?, ?, ?, ?, ?, ?, ?)""",
                              (plateforme, identifiant, udid or None, client.strip(), note.strip(), projet.strip(),
                               groupe.strip(), maintenant()))
        return self.compte(cur.lastrowid)

    def pages(self, projet=None):
        if projet is None:
            return self._l("select * from pages order by projet, groupe")
        return self._l("select * from pages where projet = ? order by groupe", projet)

    def page(self, projet, groupe):
        return self._1("select * from pages where projet = ? and groupe = ?", projet, groupe)

    def poser_page(self, projet, groupe, niche, debut):
        self.db.execute("""insert into pages (projet, groupe, niche, debut, maj_le) values (?, ?, ?, ?, ?)
                           on conflict (projet, groupe) do update set niche = excluded.niche, debut = excluded.debut,
                             maj_le = excluded.maj_le""", (projet, groupe, niche, debut or None, maintenant()))
        return self.page(projet, groupe)

    def comptes_du_projet(self, projet):
        return self._l("select * from comptes where projet = ? and actif = 1 order by groupe, plateforme, identifiant", projet)

    def modifier_compte(self, cid, **champs):
        permis = {k: v for k, v in champs.items() if k in ("udid", "client", "note", "actif", "projet", "groupe")}
        if permis:
            self.db.execute(f"update comptes set {', '.join(k + ' = ?' for k in permis)} where id = ?", (*permis.values(), cid))
        return self.compte(cid)

    # ── publications ───────────────────────────────────────────────────────────────────────────────────
    def publications(self, limite=200):
        return self._l("""select p.*, c.plateforme, c.identifiant, c.udid from publications p join comptes c on c.id = p.compte_id
                          order by case p.etat when 'en_cours' then 0 when 'en_attente' then 1 else 2 end,
                                   coalesce(p.fin, p.quand, p.cree_le) desc limit ?""", limite)

    def publications_entre(self, t0, t1):
        """Les vraies publications (ni répétitions ni annulées) dont l'heure (prévue, sinon de départ, de fin ou de
        création) tombe dans [t0, t1[ (UTC, « …Z ») : le calendrier."""
        return self._l("""select p.id, p.envoi_id, p.video, p.titre, p.etat, p.erreur, p.lien, p.quand, p.debut, p.fin, p.cree_le,
                                 coalesce(p.quand, p.debut, p.fin, p.cree_le) as moment,
                                 c.id as compte_id, c.plateforme, c.identifiant, c.groupe, c.projet
                          from publications p join comptes c on c.id = p.compte_id
                          where p.repetition = 0 and p.etat != 'annule'
                            and coalesce(p.quand, p.debut, p.fin, p.cree_le) >= ? and coalesce(p.quand, p.debut, p.fin, p.cree_le) < ?
                          order by moment, c.groupe, c.plateforme""", t0, t1)

    def projets_des_comptes(self):
        return [r["projet"] for r in self._l("select distinct projet from comptes where actif = 1 and projet is not null and projet != ''")]

    def corbeille(self, projet):
        return self._l("""select p.*, c.plateforme, c.identifiant, c.groupe, c.projet,
                                 (select q.etat from publications q where q.compte_id = p.compte_id and q.video = p.video
                                    and q.id != p.id and q.repetition = 0 and q.etat in ('en_attente', 'en_cours', 'publie')
                                    order by (q.etat = 'publie') desc, q.id desc limit 1) as deja
                          from publications p join comptes c on c.id = p.compte_id
                          where p.etat = 'annule' and p.supprime_le is not null and p.repetition = 0 and c.projet = ?
                          order by p.supprime_le desc, p.id desc""", projet)

    def publication(self, pid):
        return self._1("""select p.*, c.plateforme, c.identifiant, c.udid from publications p join comptes c on c.id = p.compte_id
                          where p.id = ?""", pid)

    def creer_publication(self, compte_id, video, titre="", legende="", quand=None, repetition=False, envoi_id=None, options=""):
        if not self.compte(compte_id):
            raise ValueError("compte inconnu")
        cur = self.db.execute("""insert into publications (compte_id, video, titre, legende, quand, repetition, envoi_id, cree_le, options)
                                 values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (compte_id, video, titre, legende, quand or None, 1 if repetition else 0, envoi_id, maintenant(), options))
        return self.publication(cur.lastrowid)

    def creer_envoi(self, video, titre, ecart_min, auto=False):
        return self.db.execute("insert into envois (video, titre, ecart_min, auto, cree_le) values (?, ?, ?, ?, ?)",
                               (video, titre, ecart_min, 1 if auto else 0, maintenant())).lastrowid

    def envoi(self, eid):
        return self._1("select * from envois where id = ?", eid)

    def publications_de_envoi(self, eid):
        return self._l("""select p.*, c.plateforme, c.identifiant, c.udid from publications p join comptes c on c.id = p.compte_id
                          where p.envoi_id = ? order by p.id""", eid)

    def publications_des_comptes(self, ids):
        """L'état, l'heure prévue et la vidéo des publications de ces comptes (les créneaux déjà pris, programmation.py ;
        ce qu'une page a déjà, /api/pages)."""
        if not ids:
            return []
        return self._l(f"select id, compte_id, etat, quand, video from publications where compte_id in ({', '.join('?' * len(ids))})", *ids)

    def file_des_comptes(self, ids):
        """Les vraies publications en file de ces comptes (ni répétition ni reel d'essai), la plus proche d'abord : la
        profondeur de la file d'une page, ce qui la dépasse, et la remplaçante d'une vidéo pas publiable (programmation.py)."""
        if not ids:
            return []
        # « relancee » : relancée ou reportée exprès (relance automatique, agent réparateur, retouche, calendrier) : elle
        # reste en file quand la page en a trop (programmation.en_trop)
        return self._l(f"""select p.id, p.compte_id, p.video, p.titre, p.quand, p.envoi_id, p.etape, p.options, e.auto,
                                  exists (select 1 from etapes x where x.publication_id = p.id and (x.message like 'Relance automatique%'
                                          or x.message like 'Relancée par l''agent réparateur%' or x.message like 'En retouche%'
                                          or x.message like 'Ratée, remise en file%' or x.message like 'Restaurée depuis la corbeille%')) as relancee
                           from publications p left join envois e on e.id = p.envoi_id
                           where p.compte_id in ({', '.join('?' * len(ids))}) and p.etat = 'en_attente' and p.repetition = 0
                             and p.options not like '%"essai": true%'
                           order by coalesce(p.quand, p.cree_le), p.id""", *ids)

    def publications_de_video(self, video):
        """Toutes les publications d'une vidéo, la plus récente d'abord."""
        return self._l("""select p.id, p.envoi_id, p.etat, p.etape, p.erreur, p.lien, p.quand, p.debut, p.fin, p.repetition, p.cree_le,
                                 c.plateforme, c.identifiant, c.groupe, c.id as compte_id
                          from publications p join comptes c on c.id = p.compte_id where p.video = ?
                          order by p.id desc""", video)

    def maj_publication(self, pid, **champs):
        if champs:
            self.db.execute(f"update publications set {', '.join(k + ' = ?' for k in champs)} where id = ?", (*champs.values(), pid))

    def prochaine(self, udid, intervalle_min=30):
        """La prochaine publication due sur ce téléphone. Un compte qui a publié il y a moins de `intervalle_min`
        minutes attend son tour (rythme normal, pas de rafale), sauf un reel d'essai ; un compte en warm-up « publications bloquées » attend
        la fin du warm-up (une répétition passe : elle ne publie rien)."""
        dues = self._l("""select p.* from publications p join comptes c on c.id = p.compte_id
                          where p.etat = 'en_attente' and c.udid = ? and c.actif = 1 and (p.quand is null or p.quand <= ?)
                            and (p.repetition = 1 or not exists (select 1 from chauffes ch where ch.compte_id = c.id
                                                                 and ch.etat = 'en_cours' and ch.bloque = 1))
                          order by coalesce(p.quand, p.cree_le), p.id""", udid, maintenant())
        for p in dues:
            # un reel d'essai n'attend pas les 30 min : des versions partent à la suite sur un même créneau (25/10/2026)
            if p["repetition"] or '"essai": true' in (p.get("options") or "") or not self._1("""select 1 from publications where compte_id = ? and etat = 'publie' and fin > ?""",
                                              p["compte_id"], il_y_a(intervalle_min)):
                return p
        return None

    def prochaine_heure(self, udid):
        """L'heure (UTC, « …Z ») de la prochaine publication en attente sur ce téléphone (maintenant si « dès que
        possible »), ou None : un warm-up ne commence pas une séance qui la retarderait."""
        r = self._1("""select min(coalesce(p.quand, ?)) as q from publications p join comptes c on c.id = p.compte_id
                       where p.etat = 'en_attente' and c.udid = ? and c.actif = 1
                         and (p.repetition = 1 or not exists (select 1 from chauffes ch where ch.compte_id = c.id
                                                              and ch.etat = 'en_cours' and ch.bloque = 1))""", maintenant(), udid)
        return r["q"] if r else None

    # ── warm-up (chauffe.py) ───────────────────────────────────────────────────────────────────────────
    def creer_chauffe(self, compte_id, mots, jours, minutes_jour, likes, abonnements, bloque, debut, fin, rapide=False):
        cur = self.db.execute("""insert into chauffes (compte_id, mots, jours, minutes_jour, likes, abonnements, bloque, debut, fin,
                                                       cree_le, rapide)
                                 values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (compte_id, mots, jours, minutes_jour, 1 if likes else 0, 1 if abonnements else 0,
                               1 if bloque else 0, debut, fin, maintenant(), 1 if rapide else 0))
        return self.chauffe(cur.lastrowid)

    def chauffe(self, cid):
        return self._1("""select ch.*, c.plateforme, c.identifiant, c.udid, c.projet, c.groupe from chauffes ch
                          join comptes c on c.id = ch.compte_id where ch.id = ?""", cid)

    def chauffes(self, etats=("en_cours", "termine", "arrete")):
        return self._l(f"""select ch.*, c.plateforme, c.identifiant, c.udid, c.projet, c.groupe from chauffes ch
                           join comptes c on c.id = ch.compte_id where ch.etat in ({', '.join('?' * len(etats))})
                           order by case ch.etat when 'en_cours' then 0 else 1 end, ch.debut desc""", *etats)

    def maj_chauffe(self, cid, **champs):
        if champs:
            self.db.execute(f"update chauffes set {', '.join(k + ' = ?' for k in champs)} where id = ?", (*champs.values(), cid))

    def comptes_bloques(self):
        """Les comptes en warm-up « publications bloquées » : la programmation les saute, l'envoi à la main est refusé."""
        return {r["compte_id"]: r["fin"] for r in self._l("select compte_id, fin from chauffes where etat = 'en_cours' and bloque = 1")}

    def finir_chauffes(self):
        """Les warm-ups arrivés au bout passent « terminé » : le compte rentre dans la rotation des publications."""
        return self.db.execute("update chauffes set etat = 'termine' where etat = 'en_cours' and fin <= ?", (maintenant(),)).rowcount

    def creer_seance(self, chauffe_id, rang, minutes):
        cur = self.db.execute("insert into seances (chauffe_id, rang, debut, minutes) values (?, ?, ?, ?)",
                              (chauffe_id, rang, maintenant(), minutes))
        return self.seance(cur.lastrowid)

    def seance(self, sid):
        return self._1("select * from seances where id = ?", sid)

    def seances(self, chauffe_id, depuis=None, limite=200):
        return self._l("""select * from seances where chauffe_id = ? and debut >= ? order by debut desc limit ?""",
                       chauffe_id, depuis or "", limite)

    def maj_seance(self, sid, **champs):
        if champs:
            self.db.execute(f"update seances set {', '.join(k + ' = ?' for k in champs)} where id = ?", (*champs.values(), sid))

    def noter_seance(self, sid, ligne):
        self.db.execute("update seances set journal = journal || ? where id = ?", (ligne + "\n", sid))

    def retirer_chauffe(self, cid):
        """Efface un warm-up fini et ses séances (bouton « Retirer ») ; rend les ids des séances effacées."""
        ids = [r["id"] for r in self._l("select id from seances where chauffe_id = ?", cid)]
        self.db.execute("delete from seances where chauffe_id = ?", (cid,))
        self.db.execute("delete from chauffes where id = ? and etat != 'en_cours'", (cid,))
        return ids

    # ── santé des comptes et alertes (sante.py, vigie.py, salons.py) ───────────────────────────────────
    def noter_alerte(self, cle, type_, niveau, message, jour):
        """Note une alerte ; rend True si elle est nouvelle (pas déjà envoyée ce jour-là pour ce sujet et ce type)."""
        try:
            self.db.execute("insert into alertes (cle, type, jour, niveau, message, cree_le) values (?, ?, ?, ?, ?, ?)",
                            (cle, type_, jour, niveau, message, maintenant()))
            return True
        except sqlite3.IntegrityError:
            return False

    def alertes_recentes(self, depuis):
        return self._l("select * from alertes where cree_le >= ? order by cree_le desc limit 200", depuis)

    def noter_releve(self, compte_id, jour, abonnes, posts, erreur=""):
        """Le relevé du jour d'un compte (le dernier gagne) ; un relevé raté garde les vues du précédent, avec l'erreur."""
        self.db.execute("""insert into releves (compte_id, jour, releve_le, abonnes, posts, erreur) values (?, ?, ?, ?, ?, ?)
                           on conflict (compte_id, jour) do update set
                             releve_le = case when excluded.erreur = '' then excluded.releve_le else releves.releve_le end,
                             abonnes = coalesce(excluded.abonnes, releves.abonnes),
                             posts = case when excluded.erreur = '' then excluded.posts else releves.posts end,
                             erreur = excluded.erreur""",
                        (compte_id, jour, maintenant(), abonnes, json.dumps(posts, ensure_ascii=False), erreur))

    def releves(self, compte_id, depuis_jour):
        l = self._l("select * from releves where compte_id = ? and jour >= ? order by jour", compte_id, depuis_jour)
        for r in l:
            r["posts"] = json.loads(r["posts"] or "[]")
        return l

    def dernieres_publications(self, compte_id, n=5):
        """Les n dernières VRAIES publications jouées d'un compte (publiées ou ratées), la plus récente d'abord."""
        return self._l("""select * from publications where compte_id = ? and repetition = 0 and etat in ('publie', 'echec')
                          order by coalesce(fin, debut, cree_le) desc limit ?""", compte_id, n)

    def prevues(self, compte_id):
        """Les vraies publications en file d'un compte, la plus proche d'abord (le hub)."""
        return self._l("""select id, quand from publications where compte_id = ? and etat = 'en_attente' and repetition = 0
                          order by coalesce(quand, cree_le)""", compte_id)

    def publications_du_jour(self, debut_utc):
        return self._l("""select p.*, c.plateforme, c.identifiant, c.groupe from publications p join comptes c on c.id = p.compte_id
                          where p.repetition = 0 and coalesce(p.fin, p.debut, p.quand, p.cree_le) >= ?""", debut_utc)

    def seances_interrompues(self):
        """Au démarrage : une séance restée « en cours » (service coupé net) est notée coupée."""
        self.db.execute("update seances set etat = 'coupee', fin = ?, erreur = 'service redémarré' where etat = 'en_cours'",
                        (maintenant(),))

    def interrompues(self):
        """Au démarrage : les publications restées « en cours » (service coupé net) passent en échec. Pas de relance
        automatique : une vidéo peut-être déjà en ligne ne doit pas partir deux fois."""
        for p in self._l("select id from publications where etat = 'en_cours'"):
            self.maj_publication(p["id"], etat="echec", fin=maintenant(),
                                 erreur="Interrompue (service redémarré) : vérifie sur le compte avant de la relancer.")

    def etape(self, pid, message, capture=None):
        n = (self._1("select max(n) as n from etapes where publication_id = ?", pid)["n"] or 0) + 1
        self.db.execute("insert into etapes (publication_id, n, le, message, capture) values (?, ?, ?, ?, ?)",
                        (pid, n, maintenant(), message, capture))
        self.maj_publication(pid, etape=message)
        return n

    def etapes(self, pid):
        return self._l("select n, le, message, capture from etapes where publication_id = ? order by n", pid)
