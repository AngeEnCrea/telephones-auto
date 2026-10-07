// Le warm-up des comptes (07/10/2026) : on y met des comptes avec les mots-clés de leur niche, et on suit
// chaque warm-up (jour X sur N, séances du jour, chiffres, journal de chaque séance avec ses captures).
// Les données : /telephones/api/chauffes (service Téléphones, chauffe.py).
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const PLAT = { tiktok: 'TikTok', instagram: 'Insta', youtube: 'YouTube' };
const ETAT = { en_cours: 'en cours', termine: 'terminé', arrete: 'arrêté' };
const ETAT_SE = { faite: '✓', en_cours: '🔄', a_venir: '⏳', due: '⏰', manquee: '—', echec: '✕' };
const MO_PAR_MINUTE = 12;

async function api(chemin, corps) {
  const o = corps === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) };
  const r = await fetch('api/' + chemin, o);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erreur || `HTTP ${r.status}`);
  return d;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3600); }

const fmt = new Intl.DateTimeFormat('fr-FR', { timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
function aParis(iso) {
  const p = Object.fromEntries(fmt.formatToParts(new Date(iso)).map(x => [x.type, x.value]));
  return { date: `${p.day}/${p.month}`, heure: `${p.hour}:${p.minute}` };
}
const duree = min => min >= 60 ? `${Math.floor(min / 60)} h ${String(Math.round(min % 60)).padStart(2, '0')}` : `${Math.round(min)} min`;
const seancesParJour = min => Math.max(1, Math.round(min / 13));

let D = null;

async function charger() {
  try { D = await api('chauffes'); }
  catch (e) { $('#en-cours').innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  dessiner();
}

function dessiner() {
  const actifs = D.chauffes.filter(c => c.etat === 'en_cours'), finis = D.chauffes.filter(c => c.etat !== 'en_cours');
  $('#info').innerHTML = `<span><b>${actifs.length}</b> compte${actifs.length > 1 ? 's' : ''} en warm-up</span>
    <span>≈ <b>${String(D.go_jour).replace('.', ',')} Go</b> de 5G par jour</span>
    <span>Séances de ~${D.minutes_seance} min entre ${D.journee[0].replace(':00', ' h')} et ${D.journee[1].replace(':00', ' h')}, entre les publications</span>`;
  // le formulaire : les comptes qu'on peut mettre en warm-up (connectés à un téléphone, TikTok ou Insta)
  const coches = new Set([...document.querySelectorAll('#f-comptes input:checked')].map(i => +i.value));
  $('#f-comptes').innerHTML = D.comptes.length ? D.comptes.map(c => {
    const non = !c.possible || c.en_chauffe, pourquoi = c.en_chauffe ? 'déjà en warm-up' : !c.telephone && !c.possible ? 'pas de téléphone' : !c.possible ? 'pas encore' : esc(c.telephone || '');
    return `<label class="${non ? 'non' : ''}"><input type="checkbox" value="${c.id}" ${non ? 'disabled' : ''} ${coches.has(c.id) && !non ? 'checked' : ''}>
      <span class="plat">${PLAT[c.plateforme] || c.plateforme}</span> @${esc(c.identifiant)}${c.groupe ? ` <span class="muted small">${esc(c.groupe)}</span>` : ''}<span class="q">${pourquoi}</span></label>`;
  }).join('') : '<div class="vide-l">Aucun compte : ajoute-les dans l’onglet Comptes de Téléphones (connecte-les d’abord sur l’iPhone).</div>';
  $('#en-cours').innerHTML = actifs.map(carte).join('') || '<div class="vide-l">Aucun compte en warm-up. Coche des comptes à gauche, donne les mots-clés de leur niche, et lance.</div>';
  $('#finis').innerHTML = finis.map(carte).join('') || '<div class="vide-l">Rien pour l’instant.</div>';
  document.querySelectorAll('[data-a]').forEach(b => b.onclick = () => action(b.dataset.a, +b.dataset.id));
  estimer();
}

function carte(c) {
  const fini = c.etat !== 'en_cours', pct = Math.min(100, Math.round(100 * (fini ? c.jours : c.jour - 0.5) / c.jours));
  const der = c.seances[0], t = c.totaux;
  const plan = c.plan.map(s => `<span class="se ${s.etat}" title="${esc(s.etat.replace('_', ' '))} · ${duree(s.minutes)} prévues${s.faites ? ', ' + duree(s.faites) + ' faites' : ''}">${ETAT_SE[s.etat] || ''} ${aParis(s.debut).heure}</span>`).join('');
  return `<div class="wc ${fini ? 'fini' : ''}">
    <div class="l1"><span class="plat">${PLAT[c.plateforme] || c.plateforme}</span><span class="nom">@${esc(c.identifiant)}</span>
      ${c.groupe ? `<span class="g">${esc(c.groupe)}</span>` : ''}<span class="grow"></span><span class="chip ${c.etat}">${ETAT[c.etat]}</span></div>
    <div class="barre-p"><div style="width:${pct}%"></div></div>
    <div class="g">${fini ? `${c.jours} jour${c.jours > 1 ? 's' : ''} · fini le ${aParis(c.fin).date}` : `Jour ${c.jour} sur ${c.jours} · jusqu’au ${aParis(c.fin).date} à ${aParis(c.fin).heure}`} · ${c.minutes_jour} min/jour</div>
    <div class="mots">${c.mots.map(m => `<span>${esc(m)}</span>`).join('')}</div>
    ${fini ? '' : `<div class="seances"><span class="g">Aujourd’hui ${duree(c.aujourdhui.minutes)} / ${duree(c.aujourdhui.cible)} :</span>${plan || '<span class="g">rien de prévu</span>'}</div>`}
    <div class="chiffres"><span>👀 ${t.vues} vidéos</span><span>❤️ ${t.likes} likes</span><span>➕ ${t.abonnements} abonnements</span><span>🔎 ${t.recherches} recherches</span><span>⏱ ${duree(t.minutes)}</span></div>
    ${fini ? '' : c.bloque ? `<div class="bloquee">🚫 Publications bloquées jusqu’à la fin du warm-up</div>` : '<div class="bloquee non">Publie en parallèle (publications pas bloquées)</div>'}
    ${der ? `<div class="derniere">Dernière séance : ${aParis(der.debut).date} à ${aParis(der.debut).heure} · ${der.etat === 'faite' ? 'faite' : der.etat === 'en_cours' ? 'en cours' : der.etat === 'coupee' ? 'coupée' : 'ratée'}
      · ${der.vues} vidéos${der.likes ? `, ${der.likes} likes` : ''}${der.abonnements ? `, ${der.abonnements} abonnements` : ''}${der.erreur ? ` · <span class="${der.etat === 'echec' ? 'err' : ''}">${esc(der.erreur)}</span>` : ''}</div>` : ''}
    <div class="actions">
      ${fini ? `<button class="btn" data-a="prolonger" data-id="${c.id}">Reprendre +3 jours</button>` : `
      <button class="btn" data-a="seance" data-id="${c.id}" ${c.telephone && c.telephone.pret && !c.telephone.occupe ? '' : 'disabled'} title="${c.telephone ? esc(c.telephone.occupe || '') : 'téléphone pas branché'}">▶ Séance maintenant</button>
      <button class="btn" data-a="modifier" data-id="${c.id}">Modifier</button>
      <button class="btn" data-a="prolonger" data-id="${c.id}">+3 jours</button>`}
      ${c.seances.length ? `<button class="btn" data-a="journal" data-id="${c.id}">Séances (${t.seances})</button>` : ''}
      ${fini ? `<button class="btn danger" data-a="retirer" data-id="${c.id}">Retirer</button>` : `<button class="btn danger" data-a="arreter" data-id="${c.id}">Arrêter</button>`}
    </div></div>`;
}

async function action(a, id) {
  const c = D.chauffes.find(x => x.id === id);
  try {
    if (a === 'seance') { await api(`chauffes/${id}/seance`, {}); toast(`Séance lancée sur @${c.identifiant} : regarde l’écran dans Téléphones.`); }
    if (a === 'prolonger') { const r = await api(`chauffes/${id}/prolonger`, { jours: 3 }); toast(`@${c.identifiant} : jusqu’au ${aParis(r.fin).date}.`); }
    if (a === 'arreter') {
      if (!confirm(`Arrêter le warm-up de @${c.identifiant} ?${c.bloque ? ' Ses publications reprennent.' : ''}`)) return;
      await api(`chauffes/${id}/arreter`, {}); toast('Warm-up arrêté.');
    }
    if (a === 'retirer') {
      if (!confirm(`Retirer le warm-up de @${c.identifiant} de la liste ? Ses séances et leurs captures sont effacées.`)) return;
      await api(`chauffes/${id}/retirer`, {}); toast('Retiré.');
    }
    if (a === 'modifier') return modifier(c);
    if (a === 'journal') return seances(c);
  } catch (e) { toast(e.message); }
  charger();
}

function fermer() { $('#fiche').hidden = true; }
$('#fiche').onclick = ev => { if (ev.target.id === 'fiche') fermer(); };

function modifier(c) {
  $('#boite').innerHTML = `<h3>@${esc(c.identifiant)}</h3><div class="muted small">${PLAT[c.plateforme]} · warm-up commencé le ${aParis(c.debut).date}</div>
    <form id="f-mod" class="bloc" style="margin-top:12px">
      <label>Mots-clés de la niche (un par ligne)</label><textarea name="mots" rows="4">${esc(c.mots.join('\n'))}</textarea>
      <div class="deux"><div><label>Durée (jours)</label><input class="in" name="jours" type="number" min="1" max="60" value="${c.jours}"></div>
        <div><label>Minutes par jour</label><input class="in" name="minutes_jour" type="number" min="5" max="180" value="${c.minutes_jour}"></div></div>
      <label class="case"><input type="checkbox" name="likes" ${c.likes ? 'checked' : ''}> Liker des vidéos de la niche</label>
      <label class="case"><input type="checkbox" name="abonnements" ${c.abonnements ? 'checked' : ''}> S'abonner à quelques comptes de la niche</label>
      <label class="case"><input type="checkbox" name="bloque" ${c.bloque ? 'checked' : ''}> Bloquer les publications pendant le warm-up</label>
      <div class="actions"><button class="btn prim">Enregistrer</button><span class="grow"></span><button type="button" class="btn" id="m-fermer">Fermer</button></div></form>`;
  $('#fiche').hidden = false;
  $('#m-fermer').onclick = fermer;
  $('#f-mod').onsubmit = async ev => {
    ev.preventDefault();
    const f = ev.target;
    try {
      await api(`chauffes/${c.id}`, { mots: f.mots.value, jours: +f.jours.value, minutes_jour: +f.minutes_jour.value,
        likes: f.likes.checked, abonnements: f.abonnements.checked, bloque: f.bloque.checked });
      toast('Enregistré.'); fermer(); charger();
    } catch (e) { toast(e.message); }
  };
}

function seances(c) {
  const ligne = s => `<div class="ls" data-s="${s.id}"><span class="se ${s.etat === 'coupee' ? 'due' : s.etat}">${s.etat === 'faite' ? '✓' : s.etat === 'en_cours' ? '🔄' : s.etat === 'coupee' ? '✂' : '✕'}</span>
    <span>${aParis(s.debut).date} ${aParis(s.debut).heure}</span><span class="muted">${duree(s.minutes_faites)} · ${s.vues} vidéos${s.likes ? ` · ${s.likes} ❤️` : ''}${s.abonnements ? ` · ${s.abonnements} ➕` : ''}</span>
    <span class="grow"></span><span class="muted small">${esc(s.mots)}</span></div>`;
  $('#boite').innerHTML = `<h3>Séances de @${esc(c.identifiant)}</h3><div class="muted small">Les ${c.seances.length} dernières · touche une séance pour son journal</div>
    <div style="margin-top:10px">${c.seances.map(ligne).join('')}</div><div id="j"></div>
    <div class="actions"><span class="grow"></span><button class="btn" id="m-fermer">Fermer</button></div>`;
  $('#fiche').hidden = false;
  $('#m-fermer').onclick = fermer;
  document.querySelectorAll('.ls').forEach(l => l.onclick = () => journal(+l.dataset.s));
}

async function journal(sid) {
  try {
    const s = await api(`seances/${sid}`);
    $('#j').innerHTML = `<h3 style="margin-top:16px;font-size:14px">Séance du ${aParis(s.debut).date} à ${aParis(s.debut).heure}${s.erreur ? ` · <span style="color:var(--urgent)">${esc(s.erreur)}</span>` : ''}</h3>
      ${s.journal.map(l => `<div class="jl"><span class="h">${esc(l.heure)}</span><div>${esc(l.message)}${l.capture ? `<a href="api/seances/${sid}/captures/${esc(l.capture)}" target="_blank" rel="noopener"><img loading="lazy" src="api/seances/${sid}/captures/${esc(l.capture)}" alt=""></a>` : ''}</div></div>`).join('')}`;
    $('#j').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { toast(e.message); }
}

function estimer() {
  const f = $('#f-new'), n = document.querySelectorAll('#f-comptes input:checked').length || 1, min = +f.minutes_jour.value || 0;
  $('#f-estim').textContent = `${seancesParJour(min)} séance${seancesParJour(min) > 1 ? 's' : ''} par jour · ≈ ${String(Math.round(min * MO_PAR_MINUTE / 100) / 10).replace('.', ',')} Go de 5G par jour et par compte`
    + (n > 1 ? ` (${String(Math.round(n * min * MO_PAR_MINUTE / 100) / 10).replace('.', ',')} Go pour les ${n})` : '');
}
$('#f-new').oninput = estimer;
$('#f-new').onsubmit = async ev => {
  ev.preventDefault();
  const f = ev.target, comptes = [...document.querySelectorAll('#f-comptes input:checked')].map(i => +i.value);
  try {
    const r = await api('chauffes', { comptes, mots: f.mots.value, jours: +f.jours.value, minutes_jour: +f.minutes_jour.value,
      likes: f.likes.checked, abonnements: f.abonnements.checked, bloque: f.bloque.checked });
    toast(`${r.chauffes.length} compte${r.chauffes.length > 1 ? 's' : ''} en warm-up.`);
    document.querySelectorAll('#f-comptes input:checked').forEach(i => i.checked = false);
    charger();
  } catch (e) { toast(e.message); }
};

charger();
setInterval(() => { if ($('#fiche').hidden) charger(); }, 15000);
