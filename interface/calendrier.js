// Le calendrier des publications (04/10/2026) : une semaine,
// un jour par colonne ; chaque vidéo avec son heure, son groupe et l'état de chaque réseau ; les créneaux encore libres
// de chaque groupe en pointillés. Les données : /telephones/api/calendrier (service Téléphones).
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const PLAT = { tiktok: 'TikTok', instagram: 'Insta', youtube: 'YouTube' };
const ETAT = { en_attente: 'prévue', en_cours: 'en cours', publie: 'en ligne', echec: 'raté', annule: 'annulée' };
const SIGNE = { en_attente: '⏳', en_cours: '🔄', publie: '✓', echec: '✕' };
const JOURS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'];
const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const PRIS_MIN = 25;   // un créneau est pris si une vidéo du groupe part à moins de 25 min (± 15 min de variation)

async function api(chemin, corps) {
  const o = corps === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) };
  const r = await fetch('api/' + chemin, o);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erreur || `HTTP ${r.status}`);
  return d;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3200); }

// les heures à Paris, quelle que soit l'heure de la machine qui regarde
const fmt = new Intl.DateTimeFormat('fr-FR', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
function aParis(iso) {
  const p = Object.fromEntries(fmt.formatToParts(new Date(iso)).map(x => [x.type, x.value]));
  return { jour: `${p.year}-${p.month}-${p.day}`, heure: `${p.hour}:${p.minute}` };
}
// l'instant (UTC) de « jour à hh:mm, heure de Paris » : on part de midi UTC et on corrige du décalage de Paris ce jour-là
function instantParis(jour, hhmm) {
  const [h, m] = hhmm.split(':').map(Number), base = new Date(`${jour}T12:00:00Z`);
  const p = aParis(base.toISOString()), decalage = (Number(p.heure.slice(0, 2)) - 12) * 60;
  return new Date(Date.parse(`${jour}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00Z`) - decalage * 60e3);
}
const plusJours = (jour, n) => { const d = new Date(`${jour}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const libJour = jour => { const d = new Date(`${jour}T12:00:00Z`); return `${JOURS[d.getUTCDay()]} ${d.getUTCDate()}`; };
const libPeriode = (a, b) => { const x = new Date(`${a}T12:00:00Z`), y = new Date(`${b}T12:00:00Z`);
  return `${x.getUTCDate()}${x.getUTCMonth() !== y.getUTCMonth() ? ' ' + MOIS[x.getUTCMonth()] : ''} – ${y.getUTCDate()} ${MOIS[y.getUTCMonth()]} ${y.getUTCFullYear()}`; };

let debut = null, D = null;
// le projet regardé et la vidéo prise pour
// la poser sur un créneau (glisser à la souris, ou toucher la vidéo puis le créneau sur téléphone)
// ?projet=<slug>&seul=1 : l'onglet Calendrier d'un projet dans le centre (25/10/2026) : ce projet seulement, sans le hub
const URLP = new URLSearchParams(location.search), FIXE = URLP.get('projet') || '';
if (URLP.get('seul')) document.body.classList.add('seul');
// le projet principal par défaut
let projet = FIXE || (() => { try { return localStorage.getItem('cal-projet') || 'perso'; } catch { return 'perso'; } })();
let choisie = null, NOMS = {}, AP = [], essai = false;
// la programmation à la main (colonne « À programmer », créneaux où glisser, essais) : pas pour le projet principal, dont les
// remontages partent tout seuls (programmation.py)
const aLaMain = () => !!projet && projet !== 'perso';

async function charger() {
  try { D = await api(`calendrier?jours=7${debut ? '&debut=' + debut : ''}`); }
  catch (e) { $('#cal').innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  debut = D.debut;
  if (!FIXE && !D.projets.some(p => p.slug === projet)) projet = (D.projets[0] || {}).slug || 'perso';
  dessiner();
  aProgrammer();
  chargerCorbeille();
}

let supprimees = [], projetCorbeille = null, corbeilleOuverte = false;
async function chargerCorbeille() {
  const demande = projet;
  try {
    const r = await api(`corbeille?projet=${encodeURIComponent(demande)}`);
    if (demande !== projet) return;
    supprimees = r.entrees; projetCorbeille = demande;
    $('#corbeille').textContent = `🗑 Corbeille${supprimees.length ? ` (${supprimees.length})` : ''}`;
  } catch (e) { if (corbeilleOuverte) throw e; }
}
async function ouvrirCorbeille() {
  corbeilleOuverte = true;
  $('#fiche').hidden = false;
  $('#boite').innerHTML = '<h2>Corbeille</h2><p>Chargement…</p><button class="btn" id="c-fermer">Fermer</button>';
  $('#c-fermer').onclick = fermerCorbeille;
  try { await chargerCorbeille(); }
  catch (e) { toast(e.message); fermerCorbeille(); return; }
  if (!corbeilleOuverte) return;
  $('#boite').innerHTML = `<h2>Corbeille · ${esc(NOMS[projet] || projet)}</h2>
    <p class="muted small">Les publications supprimées restent ici. Restaurer les remet à leur heure d’origine si elle est encore à venir et libre, sinon au prochain créneau libre du groupe.</p>
    ${supprimees.map((e, i) => `<div class="corbeille-item"><div class="grow"><b>${esc(e.titre)}</b>
      <p>${esc(e.groupe)} · ${e.comptes.map(c => `${esc(PLAT[c.plateforme] || c.plateforme)} @${esc(c.identifiant)}`).join(' · ')}</p>
      <p>${e.quand ? `Prévue le ${esc(aParis(e.quand).jour)} à ${esc(aParis(e.quand).heure)} · ` : ''}Supprimée le ${esc(aParis(e.supprime_le).jour)} à ${esc(aParis(e.supprime_le).heure)}</p></div>
      ${e.comptes.some(c => c.deja) ? '<span class="muted small">Déjà programmée ou publiée</span>' : `<button class="btn prim" data-restaurer="${i}">↶ Restaurer</button>`}</div>`).join('') || '<p class="muted">La corbeille est vide pour ce projet.</p>'}
    <button class="btn" id="c-fermer">Fermer</button>`;
  $('#c-fermer').onclick = fermerCorbeille;
  document.querySelectorAll('[data-restaurer]').forEach(b => b.onclick = async () => {
    const e = supprimees[+b.dataset.restaurer];
    if (!confirm(`Restaurer « ${e.titre} » sur ${e.comptes.map(c => PLAT[c.plateforme] || c.plateforme).join(' et ')} ? Elle sera remise dans le calendrier à son heure d’origine si elle est encore à venir et libre, sinon au prochain créneau libre.`)) return;
    document.querySelectorAll('[data-restaurer]').forEach(x => x.disabled = true);
    try {
      const r = await api('corbeille/restaurer', { projet: projetCorbeille, ids: e.comptes.map(c => c.publication) });
      debut = aParis(r.quand).jour;
      fermerCorbeille();
      toast(`Restaurée : ${libJour(debut)} à ${aParis(r.quand).heure}`);
      await charger();
    } catch (err) { toast(err.message); await ouvrirCorbeille(); }
  });
}
function fermerCorbeille() { corbeilleOuverte = false; $('#fiche').hidden = true; }

function dessiner() {
  const fin = plusJours(D.debut, D.jours - 1);
  $('#periode').textContent = libPeriode(D.debut, fin);
  selecteur();
  const groupes = D.projets.filter(p => !projet || p.slug === projet).flatMap(p => p.groupes.map(g => ({ ...g, projet: p.slug })));
  const decal = groupes.filter(g => g.decalage_min).map(g => `${esc(g.nom)} +${g.decalage_min} min`).join(' · ');
  $('#info').innerHTML = `<span>Créneaux : <b>${D.creneaux.map(c => c.replace(':00', ' h').replace(':', ' h ')).join(', ')}</b> (± ${D.variation_min} min au hasard)${decal ? ' · ' + decal : ''}</span>
    <span>Programmation automatique : <b>${D.auto ? 'activée' : 'coupée'}</b></span>
    ${Object.entries(D.legendes_instagram || {}).map(([, t]) => `<span title="la légende de toutes les publications Instagram du projet (à la place de la le fichier .txt ; une légende tapée à la main reste)">Légende Insta : <b>${esc(t)}</b></span>`).join('')}
    ${D.chauffes ? `<a class="lien" href="warmup">🔥 ${D.chauffes} compte${D.chauffes > 1 ? 's' : ''} en warm-up</a>` : ''}
    <span class="legende"><span class="res en_attente">⏳ prévue</span><span class="res en_cours">🔄 en cours</span><span class="res publie">✓ en ligne</span><span class="res echec">✕ raté</span></span>
    ${D.wifi_obligatoire ? D.telephones.filter(t => t.pret && !t.wifi).map(t => `<span class="res echec">⚠️ ${esc(t.nom)} sans Wi-Fi : les publications attendent</span>`).join('') : ''}`;
  const maintenant = Date.now(), cols = [];
  for (let i = 0; i < D.jours; i++) {
    const jour = plusJours(D.debut, i);
    const ents = D.entrees.filter(e => aParis(e.quand).jour === jour && (!projet || e.projet === projet));
    // les créneaux encore libres de chaque groupe, ce jour-là (à venir seulement)
    const libres = [];
    for (const g of groupes) for (const c of (g.creneaux || D.creneaux)) {
      const t = instantParis(jour, c).getTime() + (g.creneaux ? 0 : g.decalage_min) * 60e3;
      if (t < maintenant) continue;
      if (D.entrees.some(e => e.groupe === g.nom && (!e.projet || e.projet === g.projet) && Math.abs(Date.parse(e.quand) - t) < PRIS_MIN * 60e3)) continue;
      libres.push({ t, groupe: g.nom, projet: g.projet });
    }
    const items = [...ents.map(e => ({ t: Date.parse(e.quand), e })), ...libres.map(l => ({ t: l.t, l }))].sort((a, b) => a.t - b.t);
    const passe = instantParis(jour, '23:59').getTime() < maintenant, auj = jour === D.aujourdhui;
    cols.push(`<div class="jour ${auj ? 'auj' : ''} ${passe ? 'passe' : ''}"><h3>${libJour(jour)}${auj ? ' · aujourd’hui' : ''}<span class="n">${ents.length} vidéo${ents.length > 1 ? 's' : ''}</span></h3>
      ${aLaMain() && !passe ? `<button class="essai-heure" data-jour="${jour}" title="Un reel d’essai Insta à l’heure que tu choisis">＋ essai à une heure</button>` : ''}
      <div class="liste">${items.map(x => x.e ? carte(x.e) : `<div class="libre${aLaMain() ? ' cible' : ''}" data-t="${x.t}" data-groupe="${esc(x.l.groupe)}">${aParis(new Date(x.t).toISOString()).heure} · ${esc(x.l.groupe)} · libre${aLaMain() ? '<span class="pose"> · poser ici</span>' : ''}</div>`).join('')
        || '<div class="vide">Rien ce jour-là.</div>'}</div></div>`);
  }
  $('#cal').innerHTML = cols.join('');
  document.querySelectorAll('.ent').forEach(b => {
    const e = D.entrees[+b.dataset.i];
    const version = aLaMain() && e.projet === projet && Date.parse(e.quand) > Date.now();
    b.classList.toggle('cible-version', !!version);
    b.onclick = () => { if (version && choisie) poserVersion(choisie, e); else ouvrir(e); };
    if (!version) return;
    b.ondragover = ev => { ev.preventDefault(); b.classList.add('survol'); };
    b.ondragleave = () => b.classList.remove('survol');
    b.ondrop = ev => { ev.preventDefault(); b.classList.remove('survol'); poserVersion(ev.dataTransfer.getData('text/plain'), e); };
  });
  document.querySelectorAll('.essai-heure').forEach(b => b.onclick = () => essaiAUneHeure(b.dataset.jour));
  // 🗑 sur chaque publication prévue : ses réseaux encore en attente sont annulés, le créneau redevient libre
  document.querySelectorAll('[data-suppr]').forEach(x => x.onclick = async ev => {
    ev.stopPropagation();
    const e = D.entrees[+x.dataset.suppr], prevues = e.comptes.filter(c => c.etat === 'en_attente');
    if (!confirm(`Supprimer « ${e.titre} » de ${aParis(e.quand).heure} (${prevues.map(c => PLAT[c.plateforme] || c.plateforme).join(' et ')}) ? Elle ne partira pas.`)) return;
    try { for (const c of prevues) await api(`publications/${c.publication}/annuler`, {}); toast('Déplacée dans la corbeille. Tu peux la restaurer.'); }
    catch (err) { toast(err.message); }
    charger();
  });
  document.querySelectorAll('.libre.cible').forEach(z => {
    z.ondragover = ev => { ev.preventDefault(); z.classList.add('survol'); };
    z.ondragleave = () => z.classList.remove('survol');
    z.ondrop = ev => { ev.preventDefault(); z.classList.remove('survol'); poser(ev.dataTransfer.getData('text/plain'), z); };
    z.onclick = () => { if (choisie) poser(choisie, z); else toast('Prends d’abord une vidéo dans « À programmer ».'); };
  });
  $('#cal').classList.toggle('pose-active', !!choisie);
}

// ── façon planificateur : le projet, ses vidéos validées à programmer, posées sur un créneau libre ──────────────────
function selecteur() {
  const z = $('#choix-projet');
  if (!z || FIXE) return;
  z.innerHTML = D.projets.map(p => `<button data-p="${esc(p.slug)}" class="${p.slug === projet ? 'on' : ''}">${esc(NOMS[p.slug] || p.slug)}</button>`).join('');
  z.querySelectorAll('button').forEach(b => b.onclick = () => {
    if (b.dataset.p === projet) return;
    projet = b.dataset.p; choisie = null;
    try { localStorage.setItem('cal-projet', projet); } catch {}
    dessiner(); aProgrammer(); chargerCorbeille();
    if (typeof chargerHub === 'function') chargerHub();
    if (typeof chargerVues === 'function') chargerVues();
  });
}

async function aProgrammer(garder) {
  const z = $('#ap');
  document.body.classList.toggle('avec-ap', aLaMain());
  if (!aLaMain()) { z.innerHTML = ''; return; }
  const ecrites = Object.fromEntries(AP.filter(v => v.description).map(v => [v.cle, v.description]));
  try { if (!garder) AP = (await api(`a-programmer?projet=${encodeURIComponent(projet)}`)).map(v => ({ ...v, description: v.description || ecrites[v.cle] || '' })); }
  catch (e) { z.innerHTML = `<h2>À programmer</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  const libres = AP.filter(v => !v.places).length;
  z.innerHTML = `<h2>À programmer <span class="n">${libres} / ${AP.length}</span></h2>
    <p class="muted small">Glisse une vidéo sur un créneau « libre » (sur téléphone : touche-la puis touche le créneau). Elle part sur les comptes du groupe (TikTok, Insta, YouTube Shorts par YT Studio), à ± ${D.variation_min} min.
      <b>Reels d’essai</b> (Insta seul) : glisse-la sur une vidéo déjà programmée pour en ajouter une version sur ce créneau, ou touche « ＋ essai à une heure » sur un jour.</p>
    <label class="opt"><input type="checkbox" id="ap-essai"${essai ? ' checked' : ''}> Insta en <b>reel d’essai</b> <span class="muted">(montré d’abord aux non-abonnés)</span></label>
    <label class="opt"><input type="checkbox" id="ap-fb"${(D.facebook_instagram || {})[projet] ? ' checked' : ''}> Partager les Insta sur <b>Facebook</b></label>
    ${AP.map((v, i) => `<div class="apv${v.places ? ' deja' : ''}${choisie === v.cle ? ' prise' : ''}" draggable="true" data-i="${i}">
      <img src="${esc(v.vignette)}" loading="lazy" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'sans'}))">
      <div><div class="t">${esc(v.titre)}</div><div class="muted small">${v.places ? `déjà : ${esc(v.groupes.join(', '))}` : 'jamais programmée'}</div>
        ${v.description ? `<div class="leg" title="La légende (le fichier .txt)">${esc(v.description)}</div>` : ''}
        <button class="btn sm gen" data-maintenant="${i}" title="Tout de suite sur les comptes du groupe, sans attendre un créneau (décalée seulement si le projet principal publie dans la foulée sur le même iPhone)">▶ Publier maintenant</button></div></div>`).join('')
      || '<p class="muted small">Aucune vidéo à la racine du dossier videos/.</p>'}`;
  $('#ap-essai').onchange = ev => { essai = ev.target.checked; };
  $('#ap-fb').onchange = async ev => {
    try { await api('programmation', { facebook_instagram: { [projet]: ev.target.checked } }); D.facebook_instagram = { ...(D.facebook_instagram || {}), [projet]: ev.target.checked };
      toast(ev.target.checked ? 'Les Insta de ce projet seront aussi partagés sur Facebook.' : 'Plus de partage sur Facebook.'); }
    catch (e) { ev.target.checked = !ev.target.checked; toast(e.message); }
  };
  // « Publier maintenant »
  z.querySelectorAll('[data-maintenant]').forEach(b => b.onclick = async ev => {
    ev.stopPropagation();
    const v = AP[+b.dataset.maintenant];
    const groupes = (D.projets.find(p => p.slug === projet) || { groupes: [] }).groupes;
    if (!groupes.length) { toast('Aucun compte dans ce projet.'); return; }
    let g = groupes[0];
    if (groupes.length > 1) {
      const k = prompt(`Quel groupe ? ${groupes.map((x, i) => `${i + 1} = ${x.nom}`).join(', ')}`, '1');
      if (k === null) return;
      g = groupes[(+k || 1) - 1] || groupes[0];
    }
    if (!v.description && !confirm(`« ${v.titre} » n’a pas de légende : elle partira sans texte. La publier quand même ?`)) return;
    if (!confirm(`Publier « ${v.titre} » maintenant sur ${g.nom} (${g.comptes.map(c => c.plateforme).join(', ')}) ?`)) return;
    b.disabled = true;
    try {
      const r = await api('calendrier/placer', { video: v.cle, groupe: g.nom, quand: new Date(Date.now() + 60e3).toISOString(), exact: true, essai, legende: v.description || '' });
      toast(`Part sur ${g.nom} à ${aParis(r.quand).heure}${r.ignores.length ? ` (pas prêts : @${r.ignores.join(', @')})` : ''}`);
    } catch (e) { toast(e.message); b.disabled = false; return; }
    charger();
  });
  z.querySelectorAll('.apv').forEach(el => {
    const v = AP[+el.dataset.i];
    el.ondragstart = ev => { ev.dataTransfer.setData('text/plain', v.cle); choisie = v.cle; $('#cal').classList.add('pose-active'); };
    el.ondragend = () => { choisie = null; $('#cal').classList.remove('pose-active'); };
    el.onclick = () => { choisie = choisie === v.cle ? null : v.cle; aProgrammerSurligner(); };
  });
}
function aProgrammerSurligner() {
  document.querySelectorAll('.apv').forEach(el => el.classList.toggle('prise', AP[+el.dataset.i].cle === choisie));
  $('#cal').classList.toggle('pose-active', !!choisie);
}

async function poser(cle, zone) {
  const v = AP.find(x => x.cle === cle);
  if (!v) return;
  const t = new Date(+zone.dataset.t), g = zone.dataset.groupe;
  if (!v.description && !confirm(`« ${v.titre} » n’a pas de légende : elle partira sans texte. La poser quand même ? (sinon : « ✍ Générer la légende »)`)) return;
  if (v.places && !confirm(`« ${v.titre} » est déjà programmée sur ${v.groupes.join(', ')}. La poser aussi sur ${g} ?`)) return;
  try {
    const r = await api('calendrier/placer', { video: cle, groupe: g, quand: t.toISOString(), essai, legende: v.description || '' });
    toast(`Programmée sur ${g}${essai ? ' (Insta en reel d’essai)' : ''} : ${libJour(aParis(r.quand).jour)} à ${aParis(r.quand).heure}${r.ignores.length ? ` (pas prêts : @${r.ignores.join(', @')})` : ''}`);
  } catch (e) { toast(e.message); }
  choisie = null;
  charger();
}

function carte(e) {
  const i = D.entrees.indexOf(e), pire = e.comptes.some(c => c.etat === 'echec') ? 'echec' : e.comptes.some(c => c.etat === 'en_cours') ? 'en_cours' : '';
  const prevues = e.comptes.filter(c => c.etat === 'en_attente').length;
  return `<button class="ent ${pire}" data-i="${i}">${prevues ? `<span class="suppr" data-suppr="${i}" role="button" title="Supprimer : elle ne partira pas (${prevues} réseau${prevues > 1 ? 'x' : ''})">🗑</span>` : ''}${e.vignette ? `<img src="${esc(e.vignette)}" loading="lazy" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'sans'}))">` : '<div class="sans"></div>'}
    <div><div class="h">${aParis(e.quand).heure}</div><div class="g">${esc(e.groupe)}</div><div class="t">${esc(e.titre)}</div>
    <div class="reseaux">${e.comptes.map(c => `<span class="res ${c.etat}" title="@${esc(c.identifiant)} · ${ETAT[c.etat] || c.etat}">${SIGNE[c.etat] || ''} ${PLAT[c.plateforme] || c.plateforme}</span>`).join('')}</div></div></button>`;
}

function ouvrir(e) {
  const prevues = e.comptes.filter(c => c.etat === 'en_attente'), ratees = e.comptes.filter(c => c.etat === 'echec');
  const sansLien = e.comptes.filter(c => c.etat === 'publie' && !c.lien);
  $('#boite').innerHTML = `<h2>${esc(e.titre)}</h2>
    <div class="muted small">${esc(e.groupe)} · ${libJour(aParis(e.quand).jour)} à ${aParis(e.quand).heure}</div>
    <div style="margin-top:12px">${e.comptes.map(c => `<div class="compte"><span class="res ${c.etat}">${SIGNE[c.etat] || ''} ${ETAT[c.etat] || c.etat}</span>
      <div class="grow"><div>${PLAT[c.plateforme] || c.plateforme} · @${esc(c.identifiant)} <span class="muted small">n° ${c.publication} · ${aParis(c.quand).heure}</span></div>
      ${c.lien ? `<a class="lien" href="${esc(c.lien)}" target="_blank" rel="noopener">${esc(c.lien)} ↗</a>` : ''}${c.erreur ? `<div class="err">${esc(c.erreur)}</div>` : ''}</div></div>`).join('')}</div>
    <div class="row" style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
      ${sansLien.length ? `<button class="btn" id="f-pas-en-ligne" title="Notée publiée mais rien sur le compte : elle passe en raté, à reprogrammer">Pas en ligne ✕ (${sansLien.map(c => PLAT[c.plateforme]).join(', ')})</button>` : ''}
      ${ratees.length ? `<button class="btn prim" id="f-reprog">Reprogrammer ${ratees.map(c => PLAT[c.plateforme]).join(' et ')} au prochain créneau</button>` : ''}
      ${prevues.length ? `<button class="btn" id="f-reporter" title="${esc(e.groupe)} : TikTok et Insta ensemble, au prochain créneau libre du groupe">⏭ Reporter au prochain créneau</button>` : ''}
      ${prevues.length ? `<button class="btn danger" id="f-annuler">Annuler (${prevues.length} réseau${prevues.length > 1 ? 'x' : ''})</button>` : ''}
      <a class="btn" href="./">Détail dans Téléphones</a><span class="grow"></span><button class="btn" id="f-fermer">Fermer</button></div>`;
  $('#fiche').hidden = false;
  $('#f-fermer').onclick = () => { $('#fiche').hidden = true; };
  if ($('#f-pas-en-ligne')) $('#f-pas-en-ligne').onclick = async () => {
    if (!confirm(`Tu as vérifié sur le compte : « ${e.titre} » n'est pas en ligne sur ${sansLien.map(c => PLAT[c.plateforme]).join(' et ')} ?`)) return;
    try { for (const c of sansLien) await api(`publications/${c.publication}/pas-en-ligne`, {}); toast('Marquée ratée : tu peux la reprogrammer.'); }
    catch (err) { toast(err.message); }
    $('#fiche').hidden = true;
    charger();
  };
  if ($('#f-reprog')) $('#f-reprog').onclick = async () => {
    if (!confirm(`Remettre « ${e.titre} » en file sur ${ratees.map(c => PLAT[c.plateforme]).join(' et ')}, au prochain créneau libre de ${e.groupe} ?`)) return;
    try {   // ensemble sur le même créneau (une par une, chacune prenait le sien : TikTok et Insta séparés)
      const { quand } = await api('publications/reporter', { ids: ratees.map(c => c.publication) });
      toast(`Reprogrammée : ${libJour(aParis(quand).jour)} à ${aParis(quand).heure}`);
    } catch (err) { toast(err.message); }
    $('#fiche').hidden = true;
    charger();
  };
  if ($('#f-reporter')) $('#f-reporter').onclick = async () => {
    if (!confirm(`Reporter « ${e.titre} » (${prevues.map(c => PLAT[c.plateforme]).join(' et ')}) au prochain créneau libre de ${e.groupe} ?`)) return;
    try {
      const { quand } = await api('publications/reporter', { ids: prevues.map(c => c.publication) });
      toast(`Reportée : ${libJour(aParis(quand).jour)} à ${aParis(quand).heure}`);
    } catch (err) { toast(err.message); }
    $('#fiche').hidden = true;
    charger();
  };
  if ($('#f-annuler')) $('#f-annuler').onclick = async () => {
    if (!confirm(`Annuler « ${e.titre} » sur ${prevues.map(c => PLAT[c.plateforme]).join(' et ')} ? Le créneau redevient libre.`)) return;
    try { for (const c of prevues) await api(`publications/${c.publication}/annuler`, {}); toast('Déplacée dans la corbeille. Tu peux la restaurer.'); }
    catch (err) { toast(err.message); }
    $('#fiche').hidden = true;
    charger();
  };
}
// ── les reels d'essai : Insta seul, en reel d'essai ──────────────────────────────────────────────────────────────
async function essaiPose(cle, groupe, quand, mode) {
  const v = AP.find(x => x.cle === cle);
  if (!v) return;
  if (!v.description && !confirm(`« ${v.titre} » n’a pas de légende : le reel d’essai partira sans texte. Continuer ?`)) return;
  try {
    const r = await api('calendrier/placer', { video: cle, groupe, quand, creneau_essai: true, legende: v.description || '', ...(mode === 'pile' ? { pile: true } : { exact: true }) });
    toast(`Reel d’essai Insta (${groupe}) : ${libJour(aParis(r.quand).jour)} à ${aParis(r.quand).heure}`);
  } catch (e) { toast(e.message); }
  choisie = null;
  charger();
}
function poserVersion(cle, e) {
  if (!cle) return;
  const v = AP.find(x => x.cle === cle);
  if (v && !confirm(`Ajouter « ${v.titre} » en reel d’essai sur le créneau de ${aParis(e.quand).heure} (${e.groupe}) ? Elle part juste après ce qui est déjà prévu.`)) return;
  essaiPose(cle, e.groupe, e.quand, 'pile');
}
function essaiAUneHeure(jour) {
  if (!choisie) { toast('Prends d’abord une vidéo dans « À programmer » (touche-la), puis « ＋ essai à une heure ».'); return; }
  const groupes = (D.projets.find(p => p.slug === projet) || { groupes: [] }).groupes.filter(g => g.comptes.some(c => c.plateforme === 'instagram'));
  if (!groupes.length) { toast('Aucun compte Instagram dans ce projet.'); return; }
  let g = groupes[0];
  if (groupes.length > 1) {
    const k = prompt(`Quel groupe ? ${groupes.map((x, i) => `${i + 1} = ${x.nom}`).join(', ')}`, '1');
    g = groupes[(+k || 1) - 1] || groupes[0];
  }
  const h = (prompt(`Heure du reel d’essai le ${libJour(jour)} (HH:MM, heure de Paris)`, '') || '').trim();
  if (!/^\d{1,2}:\d{2}$/.test(h)) { if (h) toast('Heure illisible : HH:MM'); return; }
  const t = instantParis(jour, h.padStart(5, '0'));
  if (t.getTime() < Date.now()) { toast('Cette heure est déjà passée.'); return; }
  essaiPose(choisie, g.nom, t.toISOString(), 'heure');
}

$('#fiche').onclick = ev => { if (ev.target.id === 'fiche') fermerCorbeille(); };
$('#corbeille').onclick = ouvrirCorbeille;
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') fermerCorbeille(); });

api('projets').then(l => { NOMS = Object.fromEntries(l.map(p => [p.slug, `${p.emoji ? p.emoji + ' ' : ''}${p.nom || p.slug}`])); if (D) selecteur(); }).catch(() => {});
$('#prec').onclick = () => { debut = plusJours(debut, -7); charger(); };
$('#suiv').onclick = () => { debut = plusJours(debut, 7); charger(); };
$('#auj').onclick = () => { debut = null; charger(); };
charger();
setInterval(() => { if ($('#fiche').hidden) charger(); }, 60e3);
