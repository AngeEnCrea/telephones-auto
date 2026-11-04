// Les vues des pages : les vues gagnées chaque jour par les comptes des pages, d'un relevé du soir
// au suivant, TikTok et Insta, avec les publications du jour ; puis le total de chaque semaine. Les données :
// /telephones/api/vues (sante.vues_par_jour). Chargé après calendrier.js et hub.js : il reprend leurs outils ($, esc, api, nb…).
let V = null, vTout = false;
const libJourMois = j => `${libJour(j)} ${MOIS[+j.slice(5, 7) - 1]}`;

function grapheVues(jours) {   // une barre par jour (les 35 derniers) : TikTok en bas, Insta au-dessus
  const l = jours.slice(-35);
  if (!l.some(x => x.vues)) return '';
  const max = Math.max(1, ...l.map(x => x.vues || 0)), W = 22, G = 6, H = 110, bas = 16, larg = l.length * (W + G) - G;
  return `<svg class="v-graphe" style="width:min(100%, ${l.length * 34}px)" viewBox="0 0 ${larg} ${H + bas}" role="img" aria-label="Vues gagnées par jour">${l.map((x, i) => {
    const hT = (x.tiktok || 0) / max * H, hI = (x.instagram || 0) / max * H, gx = i * (W + G), d = new Date(`${x.jour}T12:00:00Z`);
    return `<g><title>${libJourMois(x.jour)} : ${nb(x.vues)} vues (TikTok ${nb(x.tiktok)}, Insta ${nb(x.instagram)}) · ${x.publiees} publiée${x.publiees > 1 ? 's' : ''}</title>
      <rect x="${gx}" y="${H - hT}" width="${W}" height="${hT}" class="tt"/><rect x="${gx}" y="${H - hT - hI}" width="${W}" height="${hI}" class="ig"/>
      <text x="${gx + W / 2}" y="${H + 12}" class="${d.getUTCDay() === 1 ? 'lun' : ''}">${d.getUTCDate()}</text></g>`;
  }).join('')}</svg>
  <div class="v-legende"><span><i class="tt"></i>TikTok</span><span><i class="ig"></i>Insta</span><span>en gras : les lundis</span></div>`;
}

function tableJours() {
  const l = [...V.jours].reverse(), vus = vTout ? l : l.slice(0, 14);
  return `<table class="tv"><thead><tr><th>Jour</th><th>Vues</th><th>TikTok</th><th>Insta</th><th>Publiées</th></tr></thead><tbody>
    ${vus.map(x => `<tr${x.jour === V.aujourdhui ? ' class="auj"' : ''}><td>${libJourMois(x.jour)}${x.jour === V.aujourdhui && !V.soir_fait ? ' <small>en cours</small>' : ''}</td>
      <td><b>${nb(x.vues)}</b></td><td>${nb(x.tiktok)}</td><td>${nb(x.instagram)}</td><td>${x.publiees}</td></tr>`).join('')}</tbody></table>
    ${l.length > 14 ? `<button class="btn sm" id="v-tout">${vTout ? 'Les 14 derniers jours' : `Les ${l.length} jours`}</button>` : ''}`;
}

function tableSemaines() {
  const l = [...V.semaines].reverse();
  return `<table class="tv"><thead><tr><th>Semaine du</th><th>Vues</th><th>TikTok</th><th>Insta</th><th>Publiées</th><th>Par jour</th></tr></thead><tbody>
    ${l.map(s => `<tr><td>${libJourMois(s.lundi)}${!s.jours ? ' <small>pas de relevé</small>' : s.jours < 7 ? ` <small>${s.jours} j relevé${s.jours > 1 ? 's' : ''}</small>` : ''}</td>
      <td><b>${s.jours ? nb(s.vues) : '—'}</b></td><td>${s.jours ? nb(s.tiktok) : '—'}</td><td>${s.jours ? nb(s.instagram) : '—'}</td><td>${s.publiees}</td>
      <td>${s.jours ? nb(Math.round(s.vues / s.jours)) : '—'}</td></tr>`).join('')}</tbody></table>`;
}

function dessinerVues() {
  if (!V.jours.length) {
    $('#v-corps').innerHTML = '<div class="muted small">Pas encore de relevé : les vues arrivent avec le premier relevé des comptes (8 h et 21 h 45).</div>';
    return;
  }
  const s = V.semaines, cette = s[s.length - 1], avant = s[s.length - 2];
  $('#v-resume').innerHTML = `cette semaine <b>${nb(cette.vues)}</b> vues${cette.jours < 7 ? ` en ${cette.jours} jour${cette.jours > 1 ? 's' : ''}` : ''}`
    + `${avant ? ` · la semaine d’avant <b>${nb(avant.vues)}</b>${avant.jours < 7 ? ` en ${avant.jours} jour${avant.jours > 1 ? 's' : ''}` : ''}` : ''}`;
  $('#v-corps').innerHTML = `${grapheVues(V.jours)}
    <div class="v-tables"><div class="v-carte"><h3>Jour par jour</h3>${tableJours()}</div><div class="v-carte"><h3>Semaine par semaine</h3>${tableSemaines()}</div></div>
    <p class="muted small v-note">Les vues gagnées d’un relevé du soir (21 h 45) au suivant, sur les comptes TikTok et Insta des pages.
      Au premier relevé d’un compte, seuls ses posts de moins de 24 h comptent ; un post sorti des derniers relevés (Insta : les 12 derniers) ne compte plus.</p>`;
  const b = $('#v-tout');
  if (b) b.onclick = () => { vTout = !vTout; dessinerVues(); };
}

async function chargerVues() {
  try { V = await api(`vues?jours=120&projet=${encodeURIComponent(projet)}`); } catch (e) { $('#v-corps').innerHTML = `<div class="muted small">${esc(e.message)}</div>`; return; }
  dessinerVues();
}
chargerVues();
setInterval(() => { if (!document.hidden) chargerVues(); }, 5 * 60e3);
