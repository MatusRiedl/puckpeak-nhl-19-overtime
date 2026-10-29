// Front office: an NHL organisation's money (payroll, cap and space for five seasons, real dollars) and its players in
// three groups: the NHL roster, the farm club, prospects and rights. A click on a player shows his deal in words;
// Contract... (or a double click) opens the contract window: cap hit, years left, one-way or two-way, applied as one
// change (Undo on the Save bar takes it back). An AHL club on the rail shows its organisation.
import { html, cls, useState } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Modal, Segmented, Select, Why, money } from '../ui.js';
import { Code } from '../rail.js';

export const tip = 'Click a column to sort. Click a player to read his contract; double-click to change it.';

// [sort key or null, label, grid track, cell class]
const COLUMNS = [['name', 'Player', 'minmax(150px, 2.2fr)', 'b'], ['pos', 'Pos', '44px', 'm'], ['age', 'Age', '44px', 'r n'],
  ['ovr', 'OVR', '46px', 'r n b'], ['cap', 'Cap hit', '84px', 'r n'], ['years', 'Years', '50px', 'm n'],
  [null, 'Type', '78px', ''], ['ext', 'Extension', 'minmax(96px, 1fr)', 'n'], [null, 'Where', 'minmax(120px, 1.4fr)', '']];
const GRID = COLUMNS.map((c) => c[2]).join(' ');

function Head({ sort }) {
  return html`<div class="tbl-head fo-head" role="row">
    ${COLUMNS.map(([key, label, , align]) => html`<div key=${label} role="columnheader"
        class=${cls('th', align.replace(/\b[nb]\b/g, '').trim(), key && 'sortable', key && sort.key === key && 'on')}
        title=${key ? 'Click to sort; again turns the order round.' : undefined}
        onClick=${key ? () => call('office_sort', key) : undefined}>
      ${label}${key && sort.key === key && html`<i class="arrow">${sort.dir < 0 ? '▼' : '▲'}</i>`}</div>`)}
  </div>`;
}

function Where({ w }) {
  if (!w) return null;
  return html`${w.team && html`<${Code} team=${w.team} small/>`}<span title=${w.text}>${w.text}</span>`;
}

function Row({ r }) {
  const pick = () => call('office_pick', r.key);
  return html`<div role="row" tabindex="0" class=${cls('tbl-row', 'fo-row', r.sel && 'sel', r.rights && 'rights')}
      onClick=${pick} onDblClick=${() => call('office_contract', r.key)}
      onKeyDown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } }}>
    <div class="c b name" title=${r.name}>${r.name}</div>
    <div class="c m">${r.pos}</div>
    <div class="c r n">${r.age ?? ''}</div>
    <div class="c r n b ovr">${r.ovr ?? ''}</div>
    <div class="c r n money">${r.cap_text}</div>
    <div class="c m n">${r.years || ''}</div>
    <div class=${cls('c', 'type', r.type === 'Two-way' && 'two')}>${r.type}</div>
    <div class="c n ext">${r.ext}</div>
    <div class="c where"><${Where} w=${r.where}/></div>
  </div>`;
}

function Group({ g }) {
  return html`<div class="fo-group">
    <div class="fo-gtitle"><span class="caps">${g.title}</span><span class="n">${g.rows.length}</span></div>
    ${g.note && html`<div class="fo-note">${g.note}</div>`}
    ${g.rows.map((r) => html`<${Row} key=${r.key} r=${r}/>`)}
  </div>`;
}

function Season({ y }) {
  return html`<div class="fo-season">
    <div class="l"><b class="caps">${y.label}</b><span class=${y.tone}>${y.space}<i class="w"> space</i></span></div>
    <div class="bar"><span class=${y.tone} style=${{ width: `${Math.round(y.share * 100)}%` }}></span></div>
    <div class="s">${y.committed} of ${y.cap} · ${y.signed} signed</div>
  </div>`;
}

const DEALS = [{ value: false, label: 'One-way' }, { value: true, label: 'Two-way' }];
const twoWay = (v) => v === true || v === 1 || v === '1' || v === 'two-way';

// the contract window: what is typed stays here until Apply (Python checks it; wrong values come back with the
// slice's typed values and problems, the window stays open)
function ContractWindow({ w }) {
  const start = w.typed || w.values;
  const [cap, setCap] = useState(String(start.cap ?? w.values.cap));
  const [years, setYears] = useState(Number(start.years ?? w.values.years) || w.values.years);
  const [deal, setDeal] = useState(twoWay(start.twoway ?? w.values.twoway));
  const close = () => call('office_contract_close');
  const apply = () => call('office_contract_apply', { cap, years, twoway: deal });
  const wrong = (k) => w.problems.filter((p) => p.key === k).map((p) => html`<div key=${p.text} class="note bad">${p.text}</div>`);
  const typed = Number(cap);
  const after = w.space.counts && cap.trim() !== '' && !Number.isNaN(typed) && typed !== w.base
    ? w.space.dollars / 1e6 - (typed - w.base) : null;
  const tone = after == null ? '' : after < 0 ? 'bad' : after < 2 ? 'caution' : 'good';
  const changed = w.sign || typed !== w.values.cap || years !== w.values.years || deal !== w.values.twoway;
  const yearOptions = Array.from({ length: w.years_max }, (_, i) => ({ value: i + 1, label: i ? `${i + 1} years` : '1 year' }));
  return html`<${Modal} className="fo-cw" title=${w.sign ? `Sign: ${w.name} with ${w.club}` : `Contract: ${w.name}`} onClose=${close} buttons=${html`
      <span class="fo-cw-now">${w.sign ? 'Free agent' : `Now ${money(w.values.cap)} x ${w.values.years}, ${w.values.twoway ? 'two-way' : 'one-way'}`}</span>
      <${Button} kind="pick" disabled=${!changed} onClick=${apply}>${w.sign ? 'Sign' : 'Apply'}<//>
      <${Button} onClick=${close}>Close<//>`}>
    <p class="small-note">${w.pos} · ${w.age ?? ''} years old · overall ${w.ovr ?? ''}. ${w.note}</p>
    <div class="fo-cw-form">
      <label class="fo-cw-row"><span class="field-label">Cap hit ($M)</span>
        <input class="field" inputMode="decimal" spellcheck="false" value=${cap}
          title=${`${money(w.cap_min)} to ${money(w.cap_max)}, in $5K steps`}
          onInput=${(e) => setCap(e.target.value)} onKeyDown=${(e) => { if (e.key === 'Enter' && changed) apply(); }}/></label>
      ${wrong('cap')}
      <label class="fo-cw-row"><span class="field-label">Years left</span>
        <${Select} value=${years} options=${yearOptions} onChange=${setYears}
          title="Seasons left on his deal, this one included"/></label>
      ${wrong('years')}
      <div class="fo-cw-row"><span class="field-label">Deal</span>
        <${Segmented} value=${deal} options=${DEALS} onChange=${setDeal}/></div>
      ${wrong('twoway')}${wrong('')}
    </div>
    ${w.ext && html`<div class="note info">${w.ext}</div>`}
    <div class="fo-cw-space">${w.space.counts ? html`Cap space this season: <b class=${w.space.tone}>${w.space.now}</b>
      ${after != null && html`<span> → <b class=${tone}>${money(after)}</b></span>`}`
      : 'He is not on the NHL roster: his cap hit does not count against the cap this season.'}</div>
  <//>`;
}

export default function Office() {
  const s = useSlice('office');
  if (!s) return null;
  if (s.why) return html`<${Why} className="fo-why" mark=${s.team && html`<${Code} team=${s.team}/>`} text=${s.why}/>`;
  const n = s.counts;
  const groups = [{ value: 'all', label: 'All' }, { value: 'nhl', label: `NHL roster (${n.nhl})` },
    { value: 'farm', label: `Farm (${n.farm})` }, { value: 'prospects', label: `Prospects (${n.prospects})` },
    { value: 'free', label: `Free agents (${n.free})` }];
  return html`<div class="fo">
    <div class="fo-top">
      <div class="fo-team"><${Code} team=${s.team}/>
        <div><b class="caps" title=${s.team.name}>${s.team.name}</b>${s.from_farm && html`<span class="fo-from" title=${s.from_farm}>${s.from_farm}</span>`}</div>
      </div>
      ${s.tiles.map((t) => html`<div key=${t.label} class=${cls('fo-tile', t.minor && 'minor')}>
        <b class=${t.tone}>${t.value}</b><span title=${t.label}>${t.label}</span></div>`)}
    </div>
    <div class="fo-seasons">${s.seasons.map((y) => html`<${Season} key=${y.label} y=${y}/>`)}</div>
    <section class="card grow fo-table">
      <header class="card-head"><span class="title">Contracts</span>
        <${Segmented} className="fo-groups" value=${s.group} options=${groups} onChange=${(g) => call('office_group', g)}/>
        <span class="sp"></span>
        <span class="fo-later" title=${s.contract.note}>
          <${Button} small disabled=${!s.contract.available} title=${s.contract.note}
            onClick=${() => call('office_contract', s.pick && s.pick.key)}>${s.contract.sign ? 'Sign...' : 'Contract...'}<//></span>
      </header>
      <div class="tbl fo-tbl" style=${{ '--cols': GRID }}>
        <${Head} sort=${s.sort}/>
        <div class="tbl-body" role="rowgroup">${s.groups.map((g) => html`<${Group} key=${g.key} g=${g}/>`)}</div>
      </div>
      <footer class="fo-foot">
        ${s.pick ? html`<span class="fo-pick"><b>${s.pick.name}</b> ${s.pick.deal}</span>`
          : html`<span class="fo-hint">Click a player to read his contract.</span>`}
        <span class="fo-money" title=${s.note}>${s.note}</span>
      </footer>
    </section>
    ${s.window && html`<${ContractWindow} key=${s.window.key} w=${s.window}/>`}
  </div>`;
}
