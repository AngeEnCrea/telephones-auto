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

async function charger() {
  try { D = await api(`calendrier?jours=7${debut ? '&debut=' + debut : ''}`); }
  catch (e) { $('#cal').innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  debut = D.debut;
  dessiner();
}

function dessiner() {
  const fin = plusJours(D.debut, D.jours - 1);
  $('#periode').textContent = libPeriode(D.debut, fin);
  const groupes = D.projets.flatMap(p => p.groupes.map(g => ({ ...g, projet: p.slug })));
  const decal = groupes.filter(g => g.decalage_min).map(g => `${esc(g.nom)} +${g.decalage_min} min`).join(' · ');
  $('#info').innerHTML = `<span>Créneaux : <b>${D.creneaux.map(c => c.replace(':00', ' h').replace(':', ' h ')).join(', ')}</b> (± ${D.variation_min} min au hasard)${decal ? ' · ' + decal : ''}</span>
    <span>Programmation automatique : <b>${D.auto ? 'activée' : 'coupée'}</b></span>
    ${D.chauffes ? `<a class="lien" href="warmup">🔥 ${D.chauffes} compte${D.chauffes > 1 ? 's' : ''} en warm-up</a>` : ''}
    <span class="legende"><span class="res en_attente">⏳ prévue</span><span class="res en_cours">🔄 en cours</span><span class="res publie">✓ en ligne</span><span class="res echec">✕ raté</span></span>
    ${D.wifi_obligatoire ? D.telephones.filter(t => t.pret && !t.wifi).map(t => `<span class="res echec">⚠️ ${esc(t.nom)} sans Wi-Fi : les publications attendent</span>`).join('') : ''}`;
  const maintenant = Date.now(), cols = [];
  for (let i = 0; i < D.jours; i++) {
    const jour = plusJours(D.debut, i);
    const ents = D.entrees.filter(e => aParis(e.quand).jour === jour);
    // les créneaux encore libres de chaque groupe, ce jour-là (à venir seulement)
    const libres = [];
    for (const g of groupes) for (const c of D.creneaux) {
      const t = instantParis(jour, c).getTime() + g.decalage_min * 60e3;
      if (t < maintenant) continue;
      if (D.entrees.some(e => e.groupe === g.nom && (!e.projet || e.projet === g.projet) && Math.abs(Date.parse(e.quand) - t) < PRIS_MIN * 60e3)) continue;
      libres.push({ t, groupe: g.nom });
    }
    const items = [...ents.map(e => ({ t: Date.parse(e.quand), e })), ...libres.map(l => ({ t: l.t, l }))].sort((a, b) => a.t - b.t);
    const passe = instantParis(jour, '23:59').getTime() < maintenant, auj = jour === D.aujourdhui;
    cols.push(`<div class="jour ${auj ? 'auj' : ''} ${passe ? 'passe' : ''}"><h3>${libJour(jour)}${auj ? ' · aujourd’hui' : ''}<span class="n">${ents.length} vidéo${ents.length > 1 ? 's' : ''}</span></h3>
      <div class="liste">${items.map(x => x.e ? carte(x.e) : `<div class="libre">${aParis(new Date(x.t).toISOString()).heure} · ${esc(x.l.groupe)} · libre</div>`).join('')
        || '<div class="vide">Rien ce jour-là.</div>'}</div></div>`);
  }
  $('#cal').innerHTML = cols.join('');
  document.querySelectorAll('.ent').forEach(b => b.onclick = () => ouvrir(D.entrees[+b.dataset.i]));
}

function carte(e) {
  const i = D.entrees.indexOf(e), pire = e.comptes.some(c => c.etat === 'echec') ? 'echec' : e.comptes.some(c => c.etat === 'en_cours') ? 'en_cours' : '';
  return `<button class="ent ${pire}" data-i="${i}">${e.vignette ? `<img src="${esc(e.vignette)}" loading="lazy" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'sans'}))">` : '<div class="sans"></div>'}
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
    try { for (const c of prevues) await api(`publications/${c.publication}/annuler`, {}); toast('Annulée : le créneau est libre.'); }
    catch (err) { toast(err.message); }
    $('#fiche').hidden = true;
    charger();
  };
}
$('#fiche').onclick = ev => { if (ev.target.id === 'fiche') $('#fiche').hidden = true; };


$('#prec').onclick = () => { debut = plusJours(debut, -7); charger(); };
$('#suiv').onclick = () => { debut = plusJours(debut, 7); charger(); };
$('#auj').onclick = () => { debut = null; charger(); };
charger();
setInterval(() => { if ($('#fiche').hidden) charger(); }, 60e3);
