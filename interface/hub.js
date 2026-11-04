// Le hub de gestion : au-dessus du
// calendrier, la santé de chaque page et de ses comptes (vues, abonnés, alertes), les téléphones, les crédits Scrape
// Creators. Les données : /telephones/api/hub (sante.py relève les comptes à 8 h et 21 h 45 ; chaque alerte part aussi
// sur Discord, catégorie de ton choix). Chargé après calendrier.js : il reprend ses outils ($, esc, api, toast, aParis…).
const NIVEAU = { rouge: 'en alerte', orange: 'à surveiller', ok: 'en forme', inconnu: 'pas encore relevé' };
const nb = n => n == null ? '—' : Number(n).toLocaleString('fr-FR');
const profil = c => c.plateforme === 'tiktok' ? `https://www.tiktok.com/@${encodeURIComponent(c.identifiant)}`
  : c.plateforme === 'instagram' ? `https://www.instagram.com/${encodeURIComponent(c.identifiant)}/` : null;
let H = null, releveEnCours = false;

function heureCourte(iso) {   // « 18 h 07 », « demain 9 h 02 », « mer. 7 21 h 45 »
  const p = aParis(iso), h = p.heure.replace(':', ' h ');
  return p.jour === H.aujourdhui ? h : p.jour === plusJours(H.aujourdhui, 1) ? `demain ${h}` : `${libJour(p.jour)} ${h}`;
}

function courbe(serie) {      // les vues des posts de moins de 24 h, relevé par relevé (8 jours au plus)
  if (!serie || serie.length < 2) return '';
  const max = Math.max(1, ...serie.map(x => x.vues_24h)), w = 6, g = 3, h = 20, l = serie.length * (w + g) - g;
  return `<svg class="courbe" width="${l}" height="${h}" viewBox="0 0 ${l} ${h}" aria-hidden="true">${serie.map((x, i) => {
    const bh = Math.max(2, Math.round(x.vues_24h / max * h));
    return `<rect x="${i * (w + g)}" y="${h - bh}" width="${w}" height="${bh}" rx="1.5" class="${i === serie.length - 1 ? 'der' : ''}"><title>${libJour(x.jour)} : ${nb(x.vues_24h)} vues sur les posts de moins de 24 h</title></rect>`;
  }).join('')}</svg>`;
}

function compte(c) {
  const lien = profil(c), j = c.jour;
  const delta = c.abonnes_delta ? `<em class="${c.abonnes_delta > 0 ? 'plus' : 'moins'}">${c.abonnes_delta > 0 ? '+' : ''}${nb(c.abonnes_delta)}</em>` : '';
  const jour = [j.ok ? `${j.ok} en ligne` : '', j.echec ? `<span class="ko">${j.echec} ratée${j.echec > 1 ? 's' : ''}</span>` : '',
    j.prevues ? `${j.prevues} prévue${j.prevues > 1 ? 's' : ''}` : ''].filter(Boolean).join(' · ') || 'rien';
  const tel = c.telephone && !c.telephone.pret ? `<span class="badge ko" title="le téléphone de ce compte n'est pas prêt : ses publications attendent">📵 ${esc(c.telephone.nom)}</span>`
    : !c.telephone ? '<span class="badge ko" title="ce compte n\'est rattaché à aucun téléphone">sans téléphone</span>' : '';
  return `<div class="cpt ${c.etat}">
    <div class="l1"><span class="pastille ${c.etat}" title="${NIVEAU[c.etat]}"></span><span class="plat">${PLAT[c.plateforme] || esc(c.plateforme)}</span>
      ${lien ? `<a href="${esc(lien)}" target="_blank" rel="noopener" title="ouvrir le compte">@${esc(c.identifiant)}</a>` : `<b>@${esc(c.identifiant)}</b>`}
      ${c.warmup ? `<a class="badge chauffe" href="warmup" title="${c.warmup.bloque ? 'warm-up : publications bloquées' : 'warm-up : il publie quand même'}">🔥 jour ${c.warmup.jour}/${c.warmup.jours}</a>` : ''}
      ${tel}<span class="grow"></span>${courbe(c.serie)}</div>
    <div class="chiffres"><span title="abonnés (et l'écart avec le relevé de la veille)">👥 ${nb(c.abonnes)}${delta}</span>
      <span title="vues des posts de moins de 24 h, au dernier relevé">👀 ${nb(c.vues_24h)} <small>24 h</small></span>
      <span title="médiane des vues des posts de 1 à 7 jours (sous 30 : shadowban probable)">médiane 7 j : ${nb(c.mediane_7j)}</span></div>
    <div class="jour-c">Aujourd’hui : ${jour}${c.prochaine ? ` · prochaine ${heureCourte(c.prochaine)}` : ''}</div>
    ${c.raisons.length ? `<ul class="raisons">${c.raisons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
    ${c.erreur_releve ? `<div class="muted small" style="margin-top:5px">Dernier relevé raté : ${esc(c.erreur_releve)}</div>` : ''}
  </div>`;
}

function tuiles() {
  const j = H.jour, n = k => H.pages.filter(p => p.etat === k).length, sc = H.scrape;
  const prets = H.telephones.filter(t => t.pret).length;
  const tel = t => {
    const b = t.batterie && typeof t.batterie.level === 'number' ? ` · 🔋 ${Math.round(t.batterie.level * 100)} %${[2, 3].includes(t.batterie.state) ? ' ⚡' : ''}` : '';
    const etat = t.pret ? (t.occupe ? 'occupé' : 'prêt') : t.branche ? '<span class="ko">pas prêt</span>' : '<span class="ko">débranché</span>';
    return `${esc(t.nom)} ${etat}${b}`;
  };
  const releves = sc.releves.map(r => `${r.heure} ${r.fait ? '✓' : '⏳'}`).join(' · ');
  return `<div class="tuile"><div class="k">Aujourd’hui</div><div class="v">${j.ok}<small>publiée${j.ok > 1 ? 's' : ''}</small></div>
      <div class="s">${j.echec ? `<span class="ko">${j.echec} ratée${j.echec > 1 ? 's' : ''}</span> · ` : ''}${j.prevues} prévue${j.prevues > 1 ? 's' : ''} d’ici minuit</div></div>
    <div class="tuile"><div class="k">Vues · 24 h</div><div class="v">${nb(j.vues_24h)}</div><div class="s">posts de moins de 24 h, au dernier relevé</div></div>
    <div class="tuile"><div class="k">Pages</div><div class="v etats">${['ok', 'orange', 'rouge'].map(k => `<span title="${NIVEAU[k]}"><span class="pastille ${k}"></span>${n(k)}</span>`).join('')}</div>
      <div class="s">${n('rouge') ? `<span class="ko">${n('rouge')} en alerte</span>` : 'aucune en alerte'}${n('inconnu') ? ` · ${n('inconnu')} sans relevé` : ''}</div></div>
    <div class="tuile"><div class="k">Téléphones</div><div class="v">${prets}<small>/ ${H.telephones.length} prêt${prets > 1 ? 's' : ''}</small></div>
      <div class="s">${H.telephones.map(tel).join(' · ') || 'aucun branché'}</div></div>
    <div class="tuile"><div class="k">Scrape Creators</div>
      <div class="v">${!sc.cle ? '<span class="ko" style="font-size:16px">pas de clé</span>' : sc.credits == null ? '—' : `<span class="${sc.credits < 300 ? 'ko' : ''}">${nb(sc.credits)}</span><small>crédits</small>`}</div>
      <div class="s" title="${sc.cle ? 'les relevés du jour (vues, abonnés, alertes)' : 'la clé va dans donnees/secrets/scrapecreators-telephones.env'}">${sc.cle ? `relevés ${releves}` : 'à poser dans secrets\\scrapecreators-telephones.env'}</div></div>`;
}

function alertes() {
  if (!H.alertes.length) return '<div class="muted small">Aucune alerte : tout roule.</div>';
  return H.alertes.slice(0, 40).map(a => `<div class="alerte ${a.niveau}"><span class="h">${heureCourte(a.cree_le)}</span><span>${esc(a.message)}</span></div>`).join('');
}

function dessinerHub() {
  $('#h-tuiles').innerHTML = tuiles();
  $('#h-pages').innerHTML = H.pages.map(pg => `<article class="page ${pg.etat}"><header><span class="pastille ${pg.etat}" title="${NIVEAU[pg.etat]}"></span>
      <h3>${esc(pg.nom)}</h3><span class="grow"></span><span class="muted small">${pg.comptes.length} compte${pg.comptes.length > 1 ? 's' : ''}</span></header>
      ${pg.comptes.map(compte).join('')}</article>`).join('') || '<div class="muted small">Aucun compte actif : ajoute-les dans Téléphones.</div>';
  $('#h-alertes').innerHTML = alertes();
  const d = H.discord.length;
  $('#h-actions').innerHTML = `<span class="muted small">Discord : ${d ? `${d} salon${d > 1 ? 's' : ''} branché${d > 1 ? 's' : ''} (de ton choix)` : '<span class="ko">pas branché</span> (secrets\\discord.env)'}</span>
    <span class="grow"></span>
    <button class="btn" id="h-relever" ${H.scrape.cle ? '' : 'disabled'} title="Lit tout de suite les vues et les abonnés de chaque compte (1 crédit Scrape Creators par compte)">⟳ Relever maintenant</button>
    <button class="btn" id="h-rapport" ${H.discord.includes('RAPPORT') ? '' : 'disabled'} title="Le bilan de la journée sur 📊 rapport-du-jour">📊 Envoyer le rapport</button>
    <button class="btn" id="h-test" ${d ? '' : 'disabled'} title="Un message de test dans chaque salon du service">🧪 Tester Discord</button>`;
  $('#h-relever').onclick = async ev => {
    ev.target.disabled = true; ev.target.textContent = '⟳ Relevé en cours…'; releveEnCours = true;
    try {
      const b = await api('sante/relever', {});
      toast(b.sans_cle ? 'Pas de clé Scrape Creators.' : `Relevé : ${b.comptes} compte${b.comptes > 1 ? 's' : ''}, ${b.alertes} alerte${b.alertes > 1 ? 's' : ''}`
        + `${b.liens ? `, ${b.liens} lien${b.liens > 1 ? 's' : ''} retrouvé${b.liens > 1 ? 's' : ''}` : ''}${b.erreurs.length ? ` · ${b.erreurs.length} erreur${b.erreurs.length > 1 ? 's' : ''}` : ''}`);
    } catch (e) { toast(e.message); }
    releveEnCours = false;
    chargerHub();
  };
  $('#h-rapport').onclick = async () => {
    try { await api('sante/rapport', {}); toast('Rapport posté sur 📊 rapport-du-jour.'); } catch (e) { toast(e.message); }
  };
  $('#h-test').onclick = async () => {
    try {
      const r = await api('sante/test-discord', {}), ok = Object.values(r).filter(Boolean).length;
      toast(`${ok}/${Object.keys(r).length} salon${ok > 1 ? 's' : ''} OK${ok < Object.keys(r).length ? ' : ' + Object.keys(r).filter(k => !r[k]).join(', ') + ' en panne' : ''}`);
    } catch (e) { toast(e.message); }
  };
}

// les comptes dès que le hub répond ; la tuile du
// garde-fou (le centre, plus lent) se pose ensuite
async function chargerHub() {
  try { H = await api(`hub?projet=${encodeURIComponent(projet)}`); } catch (e) { $('#h-tuiles').innerHTML = `<div class="tuile"><div class="k">Hub</div><div class="s">${esc(e.message)}</div></div>`; return; }
  dessinerHub();
  dessinerHub();
}
chargerHub();
setInterval(() => { if (!document.hidden && !releveEnCours) chargerHub(); }, 60e3);
