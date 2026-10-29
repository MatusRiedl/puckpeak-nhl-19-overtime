// The team list left of the six team tabs: a league, its teams with a code chip in their colours and one small number
// for the tab in view (players, games or cap space). Drawn once, outside the panes, so it keeps its scroll and its
// pick across tab changes. The list is Python's (the rail leader's `rail` slice); a pick goes back there with
// rail_team / rail_league / rail_step and every team tab follows it.
import { html, cls, useEffect, useRef } from './lib.js';
import { call } from './bridge.js';

function light(hex) {
  const n = parseInt(String(hex || '#000000').slice(1), 16);
  const [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 165;
}

// a team's short code in its colours (no logos): {code, name, colours: [primary, secondary, ...]}
export function Code({ team, small }) {
  if (!team) return null;
  const [c1, c2] = team.colours || ['#45484C', '#838E96'];
  return html`<span class=${cls('code', small && 'small')} title=${team.name}
    style=${{ background: c1, color: light(c1) ? '#080A0C' : '#fff', boxShadow: `inset 0 -3px 0 ${c2}` }}>${team.code}</span>`;
}

// s: {leagues: [{value, label}], league, unit (the word over the numbers), tip (the head's title), loaded, status, rows: [{id, code, name, colours, sel, extra, farm,
//     dirty, number: {text, tone, tip} | null}]}
export function Rail({ s }) {
  const list = useRef(null);
  const picked = s && s.rows ? (s.rows.find((r) => r.sel) || {}).id : null;
  useEffect(() => {
    const el = list.current && list.current.querySelector('.rteam.sel');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [picked, s && s.league]);
  if (!s) return html`<aside class="card rail"></aside>`;
  const pick = (id) => call('rail_team', id);
  const items = [];
  s.rows.forEach((r) => {
    if (r.extra && !items.some((x) => x.key === 'sep')) items.push(html`<div key="sep" class="rsep">${s.extra_label || 'All-Stars'}</div>`);
    items.push(html`<div key=${r.id} role="option" aria-selected=${!!r.sel} tabindex="0"
        class=${cls('rteam', r.sel && 'sel', r.extra && 'extra')} onClick=${() => pick(r.id)}
        onKeyDown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(r.id); } }}>
      <${Code} team=${r}/>
      <span class="rname" title=${r.name}>${r.name}${r.farm && html`<span class="rfarm">${r.farm}</span>`}</span>
      ${r.dirty && html`<span class="rdot" title="Changed, not saved yet"></span>`}
      ${r.number && html`<span class=${cls('rnum', r.number.tone)} title=${r.number.tip}>${r.number.text}</span>`}
    </div>`);
  });
  return html`<aside class="card rail">
    <header class="card-head"><span class="title">Teams</span><span class="aside" title=${s.tip}>${s.unit}</span></header>
    <div class="rail-league">
      <select class="field" value=${String(s.league)} disabled=${!s.loaded} aria-label="League"
        onChange=${(e) => call('rail_league', Number(e.target.value))}>
        ${s.leagues.map((l) => html`<option key=${l.value} value=${String(l.value)}>${l.label}</option>`)}
      </select>
    </div>
    <div class="scroll" ref=${list}><div class="rlist" role="listbox" aria-label="Teams">
      ${items}
      ${!s.loaded && html`<div class="empty small">${s.status}</div>`}
    </div></div>
  </aside>`;
}
