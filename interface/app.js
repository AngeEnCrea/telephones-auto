// Téléphones — interface (JavaScript simple, sans outil de build). Servie sous /telephones/ : toutes les adresses
// sont relatives (api/…).
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
async function api(chemin, corps) {
  const o = corps === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) };
  const r = await fetch('api/' + chemin, o);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erreur || `HTTP ${r.status}`);
  return d;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3200); }
function copier(texte) {   // le presse-papiers moderne n'existe qu'en https ou sur localhost ; par un relais en http, l'ancien geste
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texte).then(() => toast('Copié.'));
  const t = document.createElement('textarea'); t.value = texte; t.style.position = 'fixed'; t.style.opacity = '0';
  document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); toast('Copié.');
}
const memo = { lire: k => { try { return localStorage.getItem(k); } catch { return null; } }, ecrire: (k, v) => { try { localStorage.setItem(k, v); } catch { } } };
const heure = iso => iso ? new Date(iso).toLocaleString('fr-FR', { timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
const seconde = iso => iso ? new Date(iso).toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' }) : '';
const PLAT = { tiktok: 'TikTok', instagram: 'Instagram', youtube: 'YouTube' };
const ETATS = { en_attente: 'En file', en_cours: 'En cours', publie: 'Publié', repete: 'Répété', echec: 'Échec', annule: 'Annulé' };
const ICONES = { ok: '✓', ko: '✕', attente: '…', inutile: '–' };
const APPS_SYSTEME = [['Raccourcis', 'com.apple.shortcuts'], ['Photos', 'com.apple.mobileslideshow'], ['Réglages', 'com.apple.Preferences']];

let E = null;                          // le dernier /api/etat
let choisi = memo.lire('telephone');   // le téléphone affiché
let onglet = 'publications';
let fluxDe = null;                     // le téléphone dont le flux d'écran est branché sur l'image
const tel = () => (E && (E.parc.telephones.find(t => t.udid === choisi) || E.parc.telephones[0])) || null;
const chemin = t => `t/${encodeURIComponent(t.udid)}`;

// ───────────────────────── état général, toutes les 2 s
async function rafraichir() {
  try { E = await api('etat'); }
  catch (e) { $('#pilote').className = 'puce ko'; $('#pilote').textContent = 'Service Téléphones injoignable'; return; }
  const p = E.parc.pilote;
  $('#pilote').className = 'puce ' + ({ ok: 'ok', ko: 'ko' }[p.etat] || 'attente');
  $('#pilote').textContent = p.etat === 'ok' ? 'Pilote Apple ✓' : p.message;
  $('#pause').textContent = E.pause ? '▶ Relancer la file' : '⏸ Mettre la file en pause';
  $('#pause').classList.toggle('on', E.pause);
  rendreTelephone();
}
$('#pause').onclick = async () => {
  try { const d = await api('pause', { pause: !E.pause }); E.pause = d.pause; rafraichir(); toast(d.pause ? 'File en pause : rien ne part.' : 'File relancée.'); }
  catch (e) { toast(e.message); }
};

function rendreTelephone() {
  const tels = E.parc.telephones, t = tel();
  $('#choix-tel').innerHTML = tels.length > 1 ? tels.map(x => `<a data-udid="${esc(x.udid)}" class="${t && x.udid === t.udid ? 'on' : ''}">${esc(x.nom)}${x.pret ? '' : ' …'}</a>`).join('') : '';
  $$('#choix-tel a').forEach(a => a.onclick = () => { choisi = a.dataset.udid; memo.ecrire('telephone', choisi); fluxDe = null; rendreTelephone(); });
  if (!t) {
    $('#fiche').innerHTML = `<div class="carte vide"><h2>Aucun iPhone branché</h2>
      <div class="muted">${esc(E.parc.pilote.etat === 'ko' ? E.parc.pilote.message : 'Le pilote Apple tourne sur le PC et attend un iPhone.')}</div>
      <ol><li>Branche l'iPhone sur l'ordinateur, avec un câble de données.</li><li>Déverrouille-le et touche « Se fier ».</li><li>La suite s'affiche ici, étape par étape.</li></ol></div>`;
    ecran(null); rendreApps(null); return;
  }
  const bloque = t.etapes.find(e => e.etat === 'ko') || t.etapes.find(e => e.etat === 'attente');
  const b = t.batterie, batt = b && typeof b.level === 'number' ? ` · 🔋 ${Math.round(b.level * 100)} %${b.state === 2 ? ' ⚡' : ''}` : '';
  $('#fiche').innerHTML = `<div class="carte">
    <div class="tel-nom">${esc(t.nom)}</div>
    <div class="muted small">${esc([t.modele, t.ios && 'iOS ' + t.ios].filter(Boolean).join(' · '))}${batt}</div>
    ${t.occupe ? `<div class="aide">🤖 ${esc(t.occupe)}</div>` : ''}
    <ul class="etapes">${t.etapes.map(e => `<li class="${e.etat}"><span class="ic">${ICONES[e.etat] || '·'}</span><div>
      <div class="t">${esc(e.titre)}</div>${e.message ? `<div class="m">${esc(e.message)}</div>` : ''}
      ${e.aide && e === bloque ? `<div class="aide">${esc(e.aide)}</div>` : ''}</div></li>`).join('')}</ul>
    ${t.pret ? '<div style="margin-top:12px"><button class="btn" id="b-essai" title="Range la première vidéo validée dans Photos, sans rien publier">Essai : une vidéo dans Photos</button></div>' : ''}
  </div>`;
  const essai = $('#b-essai');
  if (essai) essai.onclick = essaiPhotos;
  ecran(t, bloque);
  rendreApps(t);
}

async function essaiPhotos() {
  const t = tel(); if (!t) return;
  try {
    const videos = await api('videos');
    if (!videos.length) return toast('Aucune vidéo dans le dossier videos/ pour l’essai : déposes-en une.');
    toast(`Essai avec « ${videos[0].titre} »… (jusqu’à 2 min)`);
    await api(`${chemin(t)}/essai-photos`, { video: videos[0].cle });
    toast('La vidéo est dans Photos : le câble, VLC et le Raccourci marchent.');
  } catch (e) { toast(e.message); }
}

// ───────────────────────── l'écran en direct
function ecran(t, bloque) {
  const img = $('#ecran'), voile = $('#voile');
  if (t && t.taille && t.taille[0]) $('#cadre').style.aspectRatio = `${t.taille[0]} / ${t.taille[1]}`;
  if (t && t.pret) {
    voile.hidden = !t.occupe;
    if (t.occupe) voile.textContent = `🤖 ${t.occupe} : les gestes à la main attendent la fin.`;
    if (fluxDe !== t.udid) { fluxDe = t.udid; img.src = `api/${chemin(t)}/flux?${Date.now()}`; }
  } else {
    fluxDe = null; img.removeAttribute('src'); voile.hidden = false;
    voile.textContent = !t ? 'Aucun iPhone' : bloque ? `${bloque.titre} : ${bloque.message || '…'}` : 'Préparation…';
  }
}
$('#ecran').onerror = () => {         // le flux coupé (agent relancé) : on le rebranche 2 s plus tard
  const u = fluxDe; if (!u) return; fluxDe = null;
  setTimeout(() => { const t = tel(); if (t && t.pret && t.udid === u && !fluxDe) { fluxDe = u; $('#ecran').src = `api/${chemin(t)}/flux?${Date.now()}`; } }, 2000);
};

async function geste(g) {
  const t = tel(); if (!t) return;
  try { await api(`${chemin(t)}/geste`, g); } catch (e) { toast(e.message); }
}
function points(ev) {                  // la position du pointeur, en points iOS
  const t = tel(), r = $('#calque').getBoundingClientRect();
  const [w, h] = t && t.taille && t.taille[0] ? t.taille : [390, 844];
  const cadrer = v => Math.min(Math.max(v, 0), 1);
  return { x: Math.round(cadrer((ev.clientX - r.left) / r.width) * w), y: Math.round(cadrer((ev.clientY - r.top) / r.height) * h) };
}
let appui = null;
const calque = $('#calque');
calque.addEventListener('pointerdown', ev => {
  ev.preventDefault(); calque.focus(); calque.setPointerCapture(ev.pointerId);
  appui = { p: points(ev), t: performance.now(), x: ev.clientX, y: ev.clientY };
});
calque.addEventListener('pointerup', ev => {
  if (!appui) return;
  const a = appui, p = points(ev), duree = (performance.now() - a.t) / 1000;
  appui = null;
  if (Math.hypot(ev.clientX - a.x, ev.clientY - a.y) > 8) geste({ type: 'glisser', x1: a.p.x, y1: a.p.y, x2: p.x, y2: p.y, duree: Math.min(Math.max(duree, 0.1), 1.5) });
  else if (duree > 0.5) geste({ type: 'appui_long', x: a.p.x, y: a.p.y, duree: Math.min(duree, 3) });
  else geste({ type: 'toucher', x: a.p.x, y: a.p.y });
});
calque.addEventListener('pointercancel', () => { appui = null; });
let molette = 0, moletteT = null;
calque.addEventListener('wheel', ev => {          // la molette fait défiler : un swipe vertical depuis le centre
  ev.preventDefault(); molette += ev.deltaY; clearTimeout(moletteT);
  moletteT = setTimeout(() => {
    const t = tel(); if (!t || !t.taille) return;
    const [w, h] = t.taille, d = Math.max(Math.min(molette, 700), -700) * 0.5; molette = 0;
    geste({ type: 'glisser', x1: w / 2, y1: h / 2 + d / 2, x2: w / 2, y2: h / 2 - d / 2, duree: 0.25 });
  }, 120);
}, { passive: false });
let tampon = '', tamponT = null;
calque.addEventListener('keydown', ev => {        // le clavier du Mac écrit sur l'iPhone quand l'écran a le focus
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const c = ev.key.length === 1 ? ev.key : ev.key === 'Enter' ? '\n' : ev.key === 'Backspace' ? '\b' : null;
  if (c === null) return;
  ev.preventDefault(); tampon += c; clearTimeout(tamponT);
  tamponT = setTimeout(() => { const s = tampon; tampon = ''; geste({ type: 'ecrire', texte: s }); }, 350);
});

$$('[data-geste]').forEach(b => b.onclick = () => geste({ type: b.dataset.geste }));
$('#clavier').onsubmit = ev => { ev.preventDefault(); const v = $('#texte').value; if (!v) return; geste({ type: 'ecrire', texte: v }); $('#texte').value = ''; };
$('#b-coller').onclick = async () => {
  const v = $('#texte').value; if (!v) return toast('Écris d’abord le texte à mettre dans le presse-papiers.');
  await geste({ type: 'coller', texte: v }); toast('Dans le presse-papiers de l’iPhone : appui long dans un champ › Coller.');
};
$('#b-capture').onclick = () => { const t = tel(); if (t) window.open(`api/${chemin(t)}/capture`, '_blank'); };
$('#b-relancer').onclick = async () => {
  const t = tel(); if (!t) return;
  try { await api(`${chemin(t)}/relancer`, {}); toast('Agent relancé : il revient dans quelques secondes.'); } catch (e) { toast(e.message); }
};

function rendreApps(t) {
  const cle = t ? t.udid + (t.apps || []).join() : '';
  if ($('#apps').dataset.cle === cle) return;
  $('#apps').dataset.cle = cle;
  if (!t) { $('#apps').innerHTML = ''; return; }
  const installees = new Set(t.apps || []);
  const liste = [...Object.entries(E.apps).map(([p, b]) => [PLAT[p], b, true]), ['VLC', 'org.videolan.vlc-ios', true], ...APPS_SYSTEME];
  $('#apps').innerHTML = liste.map(([n, b, tierce]) => {
    const absente = tierce && installees.size && !installees.has(b);
    return `<button class="btn" data-bundle="${esc(b)}" ${absente ? 'disabled title="pas installée sur cet iPhone"' : `title="${esc(b)}"`}>${esc(n)}</button>`;
  }).join('');
  $$('#apps [data-bundle]').forEach(x => x.onclick = () => geste({ type: 'lancer', bundle: x.dataset.bundle }));
}

// ───────────────────────── l'inspecteur : le nom exact de chaque élément de l'écran
let elements = [];
$('#b-arbre').onclick = async () => {
  const on = $('#boites').hidden;
  $('#boites').hidden = !on; $('#detail').hidden = !on; $('#b-arbre').classList.toggle('on', on);
  if (on) lireArbre();
};
async function lireArbre() {
  const t = tel(); if (!t) return;
  $('#detail').textContent = 'Lecture de l’écran…';
  try {
    const d = await api(`${chemin(t)}/arbre`);
    elements = d.elements;
    const [w, h] = d.taille || t.taille;
    $('#boites').innerHTML = elements.map((e, i) => `<div data-i="${i}" style="left:${e.rect.x / w * 100}%;top:${e.rect.y / h * 100}%;width:${e.rect.width / w * 100}%;height:${e.rect.height / h * 100}%" title="${esc(e.type + ' · ' + (e.label || e.name || ''))}"></div>`).join('');
    $$('#boites div').forEach(b => b.onclick = ev => {
      ev.stopPropagation(); $$('#boites .sel').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); montrer(elements[+b.dataset.i]);
    });
    $('#detail').innerHTML = `${elements.length} éléments à l’écran. Clique une boîte pour voir son nom exact. <button class="btn" id="b-relire">Relire l’écran</button>`;
    $('#b-relire').onclick = lireArbre;
  } catch (e) { $('#detail').textContent = e.message; }
}
function montrer(e) {
  $('#detail').innerHTML = `<div><b>${esc(e.type)}</b>${e.actif === false ? ' (inactif)' : ''}</div>
    <div>label : <code>${esc(e.label ?? '')}</code></div><div>name : <code>${esc(e.name ?? '')}</code></div>
    ${e.value ? `<div>value : <code>${esc(e.value)}</code></div>` : ''}
    <div class="muted">x ${e.rect.x}, y ${e.rect.y} · ${e.rect.width} × ${e.rect.height} points</div>
    <div class="commandes" style="justify-content:flex-start"><button class="btn" id="b-copier">Copier le nom</button><button class="btn" id="b-toucher">Toucher</button><button class="btn" id="b-relire">Relire l’écran</button></div>`;
  $('#b-copier').onclick = () => copier(e.label || e.name || '');
  $('#b-toucher').onclick = async () => { await geste({ type: 'toucher', x: e.rect.x + e.rect.width / 2, y: e.rect.y + e.rect.height / 2 }); setTimeout(lireArbre, 1200); };
  $('#b-relire').onclick = lireArbre;
}

// ───────────────────────── colonne de droite : publications, comptes, journal
$$('.onglets a').forEach(a => a.onclick = () => {
  onglet = a.dataset.onglet; $$('.onglets a').forEach(x => x.classList.toggle('on', x === a)); $('#panneau').innerHTML = ''; panneau();
});
function panneau() { return onglet === 'publications' ? vuePublications() : onglet === 'comptes' ? vueComptes() : vueJournal(); }

async function vuePublications() {
  if (!$('#f-pub')) {
    $('#panneau').innerHTML = `<form id="f-prog" class="bloc"><h3>Programmation automatique</h3>
      <div class="muted small">Une vidéo déposée dans <code>videos/&lt;groupe&gt;/</code> (le nom d’un groupe de comptes, onglet Comptes) part toute seule sur les comptes de ce groupe, une fois, au prochain créneau libre, à ± 15 min tirées au hasard pour ne jamais poster à heure fixe (heure de Paris). Les groupes se répartissent entre deux créneaux : chaque groupe suivant décalé de <span id="p-ecart">90</span> min. Un créneau manqué de plus de 30 min (téléphone débranché, sans réseau, file en pause) n'est pas rattrapé en rafale : il passe au prochain créneau libre.</div>
      <label class="case"><input type="checkbox" name="auto"> Activée</label>
      <label class="case"><input type="checkbox" name="wifi"> Publier seulement en Wi-Fi (sans Wi-Fi, les publications attendent en file)</label>
      <label>Créneaux</label><input class="in" name="creneaux" placeholder="09:00,12:00,15:00,18:00,21:00">
      <div style="margin-top:8px"><button class="btn sm">Enregistrer</button></div></form>
      <form id="f-pub" class="bloc"><h3>Nouvelle publication</h3>
      <div class="muted small">Les vidéos du dossier <code>videos/</code> (et de ses dossiers de groupe). Un fichier <code>.txt</code> du même nom donne la légende.</div>
      <label>Compte</label><select name="compte_id"></select>
      <label>Vidéo</label><select name="video"></select>
      <label>Légende</label><textarea name="legende" placeholder="Légende, hashtags…"></textarea>
      <label>Quand</label><input class="in" type="datetime-local" name="quand">
      <div class="muted small">Vide : dès que le téléphone est libre. Un compte publie au plus une fois toutes les 30 min.</div>
      <label class="case"><input type="checkbox" name="repetition" checked> Répétition : tout le parcours, sans toucher le dernier « Publier »</label>
      <div style="margin-top:12px"><button class="btn prim">Mettre en file</button></div></form><div id="l-pub"></div>`;
    const fp = $('#f-prog');
    const montrer = d => { fp.auto.checked = d.auto; fp.wifi.checked = d.wifi_obligatoire; fp.creneaux.value = d.creneaux.join(', '); $('#p-ecart').textContent = d.ecart_min; };
    api('programmation').then(montrer).catch(e => toast(e.message));
    fp.onsubmit = async ev => {
      ev.preventDefault();
      try { montrer(await api('programmation', { auto: fp.auto.checked, wifi_obligatoire: fp.wifi.checked, creneaux: fp.creneaux.value.replace(/\s+/g, '') })); toast('Programmation enregistrée.'); }
      catch (e) { toast(e.message); }
    };
    const f = $('#f-pub');
    try {
      const [comptes, videos] = await Promise.all([api('comptes'), api('videos')]);
      const actifs = comptes.filter(c => c.actif);
      f.compte_id.innerHTML = actifs.length ? actifs.map(c => `<option value="${c.id}">${esc(PLAT[c.plateforme])} · @${esc(c.identifiant)}${c.udid ? '' : ' (sans téléphone)'}</option>`).join('')
        : '<option value="">Ajoute d’abord un compte (onglet Comptes)</option>';
      f.video.innerHTML = videos.length ? videos.map(v => `<option value="${esc(v.cle)}">${esc(`${v.groupe ? v.groupe + ' · ' : ''}${v.titre}`)}${v.description ? ' ✍' : ''}</option>`).join('')
        : '<option value="">Aucune vidéo dans le dossier videos/</option>';
      // la légende du .txt à côté de la vidéo, tant qu'on n'en a pas tapé une autre
      let auto = '';
      const preremplir = () => {
        const v = videos.find(x => x.cle === f.video.value), d = (v && v.description) || '';
        if (!f.legende.value.trim() || f.legende.value === auto) { f.legende.value = d; auto = d; }
      };
      f.video.onchange = preremplir;
      preremplir();
    } catch (e) { toast(e.message); }
    f.onsubmit = async ev => {
      ev.preventDefault();
      const corps = { compte_id: +f.compte_id.value, video: f.video.value, legende: f.legende.value, repetition: f.repetition.checked,
                      quand: f.quand.value ? new Date(f.quand.value).toISOString() : null };
      if (!corps.compte_id || !corps.video) return toast('Choisis un compte et une vidéo.');
      try { const p = await api('publications', corps); toast(`Publication n° ${p.id} en file${p.repetition ? ' (répétition)' : ''}.`); f.legende.value = ''; listePublications(); }
      catch (e) { toast(e.message); }
    };
  }
  listePublications();
}

async function listePublications() {
  const l = $('#l-pub'); if (!l) return;
  try {
    const pubs = await api('publications');
    l.innerHTML = pubs.length ? pubs.map(p => `<div class="pub" data-id="${p.id}">
      <div class="l1"><span class="etat ${p.etat}">${ETATS[p.etat]}</span><span class="titre">${esc(p.titre || p.video)}</span><span class="muted small">n° ${p.id}</span></div>
      <div class="l2">${esc(PLAT[p.plateforme])} · @${esc(p.identifiant)} · ${p.etat === 'en_attente' ? (p.quand ? 'prévue le ' + heure(p.quand) : 'dès que possible') : heure(p.fin || p.debut || p.cree_le)}${p.repetition ? ' · répétition' : ''}${p.etat === 'en_cours' && p.etape ? ' · ' + esc(p.etape) : ''}</div>
      ${p.erreur ? `<div class="err">${esc(p.erreur)}</div>` : ''}
      ${p.lien ? `<div class="l2"><a href="${esc(p.lien)}" target="_blank" rel="noopener">${esc(p.lien)} ↗</a></div>` : ''}</div>`).join('')
      : '<p class="muted">Aucune publication pour l’instant.</p>';
    $$('.pub', l).forEach(x => x.onclick = ev => { if (!ev.target.closest('a')) ouvrir(+x.dataset.id); });
  } catch (e) { l.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

let ouverte = null;
async function ouvrir(id) {
  let p;
  try { p = await api(`publications/${id}`); } catch (e) { return toast(e.message); }
  ouverte = id;
  const t = $('#tiroir'); t.hidden = false;
  t.innerHTML = `<div class="commandes" style="justify-content:flex-end;margin:0"><button class="btn" id="b-fermer">Fermer ✕</button></div>
    <h2>n° ${p.id} · ${esc(p.titre)}</h2>
    <div class="muted">${esc(PLAT[p.plateforme])} · @${esc(p.identifiant)} · <span class="etat ${p.etat}">${ETATS[p.etat]}</span>${p.repetition ? ' · répétition' : ''}</div>
    ${p.legende ? `<p style="white-space:pre-wrap">${esc(p.legende)}</p>` : ''}
    ${p.erreur ? `<div class="aide">${esc(p.erreur)}</div>` : ''}
    ${p.lien ? `<p><a href="${esc(p.lien)}" target="_blank" rel="noopener">${esc(p.lien)} ↗</a></p>` : ''}
    <div class="commandes" style="justify-content:flex-start">
      ${p.etat === 'en_attente' ? '<button class="btn danger" id="b-annuler">Annuler</button>' : ''}
      ${['echec', 'repete', 'annule'].includes(p.etat) ? `<button class="btn" id="b-rejouer">Relancer${p.repetition ? ' en répétition' : ''}</button>` : ''}
      ${['echec', 'repete', 'annule'].includes(p.etat) && p.repetition ? '<button class="btn prim" id="b-vrai">Publier pour de vrai</button>' : ''}
      ${p.etat === 'echec' && !p.repetition ? '<button class="btn" id="b-en-ligne" title="La vidéo est bien en ligne sur le compte : la marquer publiée et chercher son lien">C\'est en ligne ✓</button>' : ''}
    </div>
    <ul class="deroule">${p.etapes.map(e => `<li>${e.capture ? `<a href="api/publications/${p.id}/captures/${e.capture}" target="_blank"><img src="api/publications/${p.id}/captures/${e.capture}" loading="lazy" alt=""></a>` : '<div class="sans"></div>'}
      <div><div>${esc(e.message)}</div><div class="muted small">${seconde(e.le)}</div></div></li>`).join('') || '<li><div></div><div class="muted">Pas encore commencée.</div></li>'}</ul>`;
  $('#b-fermer').onclick = () => { t.hidden = true; ouverte = null; };
  const agir = async (route, corps, msg) => { try { await api(`publications/${p.id}/${route}`, corps); toast(msg); ouvrir(p.id); listePublications(); } catch (e) { toast(e.message); } };
  if ($('#b-annuler')) $('#b-annuler').onclick = () => agir('annuler', {}, 'Publication annulée.');
  if ($('#b-rejouer')) $('#b-rejouer').onclick = () => agir('relancer', {}, 'Remise en file.');
  if ($('#b-en-ligne')) $('#b-en-ligne').onclick = () => confirm('La vidéo est bien en ligne sur @' + p.identifiant + ' ?') && agir('en-ligne', {}, 'Marquée publiée : lien cherché.');
  if ($('#b-vrai')) $('#b-vrai').onclick = () => confirm('Publier pour de vrai sur @' + p.identifiant + ' ?') && agir('relancer', { repetition: false }, 'En file, pour de vrai.');
  clearTimeout(ouvrir.t);
  if (['en_cours', 'en_attente'].includes(p.etat)) ouvrir.t = setTimeout(() => ouverte === p.id && !t.hidden && ouvrir(p.id), 3000);
}

async function vueComptes() {
  if (!$('#f-compte')) {
    $('#panneau').innerHTML = `<form id="f-compte" class="bloc"><h3>Ajouter un compte</h3>
      <div class="muted small">Connecte-toi d’abord toi-même au compte dans l’app, sur l’iPhone : le logiciel ne tape jamais de mot de passe.</div>
      <label>Plateforme</label><select name="plateforme"><option value="tiktok">TikTok</option><option value="instagram">Instagram</option><option value="youtube">YouTube</option></select>
      <label>Identifiant</label><input class="in" name="identifiant" placeholder="@compte" required>
      <label>Téléphone</label><select name="udid"></select>
      <label>Groupe</label><input class="in" name="groupe" list="groupes" placeholder="Groupe 1">
      <div class="muted small">Un groupe = les comptes qui publient les mêmes vidéos (par exemple le TikTok et l’Insta d’une même page). Les vidéos de <code>videos/&lt;groupe&gt;/</code> partent sur tous ses comptes ; les groupes se relaient entre les créneaux.</div>
      <datalist id="groupes"></datalist>
      <div style="margin-top:12px"><button class="btn prim">Ajouter</button></div></form><div id="l-comptes"></div>`;
    const f = $('#f-compte');
    f.udid.innerHTML = (E ? E.parc.telephones : []).map(t => `<option value="${esc(t.udid)}">${esc(t.nom)}</option>`).join('') + '<option value="">Aucun pour l’instant</option>';
    f.onsubmit = async ev => {
      ev.preventDefault();
      try {
        await api('comptes', { plateforme: f.plateforme.value, identifiant: f.identifiant.value, udid: f.udid.value || null,
                               groupe: f.groupe.value });
        f.identifiant.value = ''; toast('Compte ajouté.'); listeComptes();
      } catch (e) { toast(e.message); }
    };
  }
  listeComptes();
}

async function listeComptes() {
  const l = $('#l-comptes'); if (!l) return;
  try {
    const comptes = await api('comptes'), tels = E ? E.parc.telephones : [];
    $('#groupes').innerHTML = [...new Set(comptes.map(c => c.groupe).filter(Boolean))].map(g => `<option value="${esc(g)}">`).join('');
    l.innerHTML = comptes.length ? comptes.map(c => `<div class="compte" data-id="${c.id}"><div>
        <div><b>${esc(PLAT[c.plateforme])}</b> · @${esc(c.identifiant)}${c.actif ? '' : ' <span class="muted">(désactivé)</span>'}</div>
        <div class="muted small">${c.groupe ? esc(c.groupe) : 'sans groupe'}${c.derniere ? ' · dernière publication le ' + heure(c.derniere) : ''}</div>
        <div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">
          <select data-champ="udid">${tels.map(t => `<option value="${esc(t.udid)}" ${t.udid === c.udid ? 'selected' : ''}>${esc(t.nom)}</option>`).join('')}
            ${c.udid && !tels.some(t => t.udid === c.udid) ? `<option value="${esc(c.udid)}" selected>${esc(c.udid.slice(0, 8))} (débranché)</option>` : ''}
            <option value="" ${c.udid ? '' : 'selected'}>Aucun téléphone</option></select>
          <input class="in" data-champ="groupe" list="groupes" value="${esc(c.groupe || '')}" placeholder="Groupe" style="width:120px"></div></div>
      <div><button class="btn" data-actif="${c.actif ? 0 : 1}">${c.actif ? 'Désactiver' : 'Activer'}</button></div></div>`).join('')
      : '<p class="muted">Aucun compte. Connecte-le d’abord dans l’app sur l’iPhone, puis ajoute-le ici.</p>';
    $$('.compte', l).forEach(x => {
      const id = x.dataset.id;
      const changer = async (champs, msg) => { try { await api(`comptes/${id}`, champs); toast(msg); listeComptes(); } catch (e) { toast(e.message); } };
      $('[data-champ="udid"]', x).onchange = ev => changer({ udid: ev.target.value || null }, 'Téléphone du compte changé.');
      const g = $('[data-champ="groupe"]', x);
      g.onchange = () => changer({ groupe: g.value.trim() }, 'Groupe du compte changé.');
      g.onkeydown = ev => { if (ev.key === 'Enter') g.blur(); };
      $('[data-actif]', x).onclick = ev => changer({ actif: ev.target.dataset.actif === '1' }, ev.target.dataset.actif === '1' ? 'Compte activé.' : 'Compte désactivé.');
    });
  } catch (e) { l.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

async function vueJournal() {
  try {
    const l = await api('journal');
    $('#panneau').innerHTML = `<div class="journal">${l.slice().reverse().map(x => `<div class="${esc(x.niveau)}">${seconde(new Date(x.t * 1000).toISOString())} ${esc(x.qui)} : ${esc(x.msg)}</div>`).join('') || 'Rien pour l’instant.'}</div>`;
  } catch (e) { $('#panneau').innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

rafraichir();
setInterval(rafraichir, 2000);
panneau();
setInterval(() => { if (!document.hidden && !$('#panneau').contains(document.activeElement)) panneau(); }, 5000);
