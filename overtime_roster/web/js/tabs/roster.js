// Roster: find a player, the team's players, the picked player's card (Apply, Undo my edit), and the windows
// Face & type... and Equipment... (roster-face.js, roster-gear.js). Python holds the roster; what is typed on the card
// stays here until Apply, Enter, Save or a pick of another player sends it along (cardDraft).
import { html, cls, useState, useEffect, useRef, Fragment } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Card, Button, Table, TextField, Segmented, Select, Empty, Tag, money } from '../ui.js';
import { Code } from '../rail.js';
import { cardDraft } from '../savebar.js';
import { FaceWindow } from './roster-face.js';
import { GearWindow } from './roster-gear.js';

export const tip = 'Pick a player, change his card, then Apply. Ctrl+F finds a player.';   // Alt+Up / Down: the rail's title

// Ctrl+F: the search field
export function onKey(e) {
  if (!(e.ctrlKey && !e.altKey && e.key.toLowerCase() === 'f')) return false;
  const box = document.querySelector('.tab-roster .ro-search');
  if (!box || box.offsetParent === null) return false;
  box.focus();
  box.select();
  return true;
}

export function Modals() {
  return html`<${Fragment}><${FaceWindow}/><${GearWindow}/><//>`;
}

// --- the players --------------------------------------------------------------------------------------------------
const POS_ORDER = { C: 0, LW: 1, RW: 2, D: 3, G: 4 };
const COL = {
  pos: { key: 'pos', label: 'Pos', width: '44px', align: 'm', sort: (r) => POS_ORDER[r.pos] },
  num: { key: 'num', label: '#', width: '34px', align: 'r', num: true },
  name: { key: 'name', label: 'Name', width: 'minmax(120px, 2fr)', bold: true,
    cell: (r) => html`<span class="ro-nm">${r.name}</span>${r.cap && html`<span class="ro-letter">${r.cap}</span>`}${r.tag === 'edited'
      && html`<i class="ro-dot" title=${r.note}></i>`}${r.copy && html`<span class="ro-copy" title=${r.copy.tip}>${r.copy.text}</span>`}` },
  team: { key: 'team', label: 'Team', width: '52px', sort: (r) => r.team && r.team.code,
    cell: (r) => html`<span title=${r.team ? r.team.name : ''}><${Code} team=${r.team} small/></span>` },
  age: { key: 'age', label: 'Age', width: '40px', align: 'r', num: true },
  shoots: { key: 'shoots', label: 'Shoots', width: '54px', align: 'm' },
  nat: { key: 'nat', label: 'Country', width: 'minmax(72px, 1fr)' },
  type: { key: 'type', label: 'Type', width: '46px', align: 'm', title: 'Player type' },
  ovr: { key: 'ovr', label: 'OVR', width: '44px', align: 'r', num: true, cell: (r) => html`<span class="ovr">${r.ovr}</span>` },
  salary: { key: 'salary', label: 'Cap hit', width: '84px', align: 'r', num: true, cell: (r) => (r.salary ? money(r.salary) : '') },
  note: { key: 'note', label: 'Change', width: 'minmax(96px, 1.3fr)', cell: (r) => html`<span class="ro-note" title=${r.note}>${r.note}</span>` },
};
// the columns that fit the table's width (the edited mark stays on the name when Change does not fit)
// (narrow first drops Shoots and Country, then Change, then Type; Cap hit stays longest)
function columnsFor(width, searching, notes) {
  const wide = width >= 780, mid = width >= 600, type = width >= 520, small = width >= 420;
  const keys = ['pos', 'num', 'name', searching && 'team', (small || !searching) && 'age', wide && 'shoots', wide && 'nat',
    type && 'type', 'ovr', small && 'salary', notes && mid && 'note'].filter(Boolean);
  return keys.map((k) => COL[k]);
}

function useWidth() {
  const box = useRef(null);
  const [width, setWidth] = useState(900);
  useEffect(() => {
    const watch = new ResizeObserver(() => { if (box.current && box.current.offsetWidth) setWidth(box.current.offsetWidth); });
    watch.observe(box.current);
    return () => watch.disconnect();
  }, []);
  return [box, width];
}

// the search ("Find a player": every league), then the team's players or what was found
function Players({ s, onPick }) {
  const [box, width] = useWidth();
  const notes = s.rows.some((r) => r.note);
  const columns = columnsFor(width, s.searching, notes);
  return html`<${Card} title=${s.title} className="ro-players"
      aside=${html`${!s.searching && html`<${Code} team=${s.team} small/>`}<span>${s.count}</span>`}>
    <div class="ro-find">
      <${TextField} className="ro-search" value=${s.query} placeholder="Find a player" delay=${220} disabled=${s.busy}
        onChange=${(t) => call('roster_search', t)}/>
      ${s.searching && html`<${Button} small onClick=${() => call('roster_search', '')}>Show the team<//>`}
      ${s.note && html`<span class="ro-teamnote" title=${s.note}>${s.note}</span>`}
    </div>
    <div class="card-body fill ro-table" ref=${box}>
      <${Table} columns=${columns} rows=${s.rows} sel=${s.selected} onPick=${(r) => onPick(r.id)} empty=${s.empty}/>
    </div>
  <//>`;
}

// --- the card -----------------------------------------------------------------------------------------------------
const imperial = (cm) => {
  const inches = Math.round(Number(cm) / 2.54);
  return Number.isFinite(inches) && inches > 0 ? `${Math.floor(inches / 12)}'${inches % 12}"` : '';
};
const pounds = (kg) => { const n = Math.round(Number(kg) * 2.20462); return Number.isFinite(n) && n > 0 ? `${n} lbs` : ''; };
const digits = (text) => String(text).replace(/[^0-9]/g, '');

// typed, not applied yet: differs from his card
const typedHere = (form, c, k) => form[k] != null && String(form[k]) !== String(c.values[k] ?? '');
const typedRating = (form, c, k) => form.ratings && form.ratings[k] != null && String(form.ratings[k]) !== String(c.values.ratings[k]);

// one row of the card: the label, the control, a note right of it, what is wrong under it
function Row({ label, k, c, form, edited, children, aside }) {
  const problem = c.problems.find((p) => p.key === k);
  return html`<div class=${cls('ro-row', problem && 'bad', !problem && typedHere(form, c, k) && 'typed')}>
    <span class="ro-lab">${label}${edited.has(k) && html`<i class="ro-dot" title="Applied, not saved yet"></i>`}</span>
    <span class="ro-ctl">${children}</span>
    ${aside != null && html`<span class="ro-aside">${aside}</span>`}
    ${problem && html`<span class="ro-problem">${problem.text}</span>`}
  </div>`;
}

function Input({ k, form, set, off, numeric, placeholder }) {
  return html`<input class="field" data-k=${k} value=${form[k] == null ? '' : form[k]} disabled=${off} spellcheck="false"
    inputmode=${numeric ? 'numeric' : undefined} placeholder=${placeholder}
    onInput=${(e) => set(k, numeric ? digits(e.target.value) : e.target.value)}/>`;
}

function Summary({ c }) {
  return html`<div class="ro-sum">${c.summary.slice(1).map((x) => html`<div key=${x.label} class="ro-bar">
    <span>${x.label}</span><span class="ro-track"><i style=${{ width: `${x.value}%` }}></i></span><b>${x.value}</b>
  </div>`)}</div>`;
}

function PlayerCard({ s, c, form, set, setRating, dirty, onApply, onUndo }) {
  const body = useRef(null);
  const problems = c ? c.problems.map((p) => p.key).join(' ') : '';
  // what is wrong comes into view (Apply, Enter, Save)
  useEffect(() => {
    const el = body.current && body.current.querySelector('.ro-row.bad, .ro-rt.bad, .ro-problem-block');
    if (!el) return;
    const box = body.current.getBoundingClientRect(), at = el.getBoundingClientRect();
    if (at.top < box.top || at.bottom > box.bottom) body.current.scrollTop += at.top - box.top - 8;
  }, [problems]);
  if (!c) {
    return html`<${Card} title="Player" className="ro-card">
      <div class="card-body fill"><${Empty}>${s.card_why || (s.rows.length ? 'Pick a player in the list to see his card.' : '')}<//></div><//>`;
  }
  const off = c.busy;
  const edited = new Set(c.edited);
  const head = c.team ? c.team.colours[0] : '#45484C';
  const ratingProblem = c.problems.filter((p) => p.key.startsWith('ratings.'));
  const from = (c.choices.countries.find(([n]) => n === c.values.country) || [])[1];
  const status = dirty ? html`<span class="pill" title="Press Apply or Enter">not applied</span>`
    : c.edited.length ? html`<span class="ro-unsaved" title="Applied. Save writes it to the roster.">edited</span>` : '';
  return html`<${Card} title=${c.title} className="ro-card" aside=${status}>
    <div class="card-body scroll ro-card-body" key=${c.key} ref=${body}
      onKeyDown=${(e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); onApply(); } }}>
      <div class="ro-hero">
        <div class="ro-ovr" style=${{ '--team': head }}><b>${c.ovr}</b><span>OVR</span></div>
        <div class="ro-who">
          <div class="ro-sub ro-strong">${c.note}</div>
          <div class="ro-sub">${[c.age != null && `${c.age} years`, from].filter(Boolean).join(' · ')}</div>
          <div class="ro-sub ro-teamline">${c.team && html`<${Code} team=${c.team} small/>`}<span>${c.free_agent ? 'Free agent' : c.team ? c.team.name : ''}</span></div>
        </div>
      </div>
      ${c.copy_note && html`<div class="small-note ro-copy-note">${c.copy_note}</div>`}
      <${Summary} c=${c}/>
      <div class="ro-buttons">
        <${Button} small className="ro-face-btn" disabled=${off} onClick=${() => call('roster_face_open')}
          title="His player type, head, hair, beard and colours, or another player's face">Face & type...<//>
        <${Button} small className="ro-gear-btn" disabled=${off || !c.gear.length} onClick=${() => call('roster_gear_open')}
          title=${c.gear_note || 'Stick, helmet, gloves, skates, visor, the tucks and the tape'}>Equipment...<//>
        <span class="ro-pair"><${Button} small kind="gold-line" disabled title=${c.contract.title}>Contract...<//>
          <span class="ro-later">comes later</span></span>
      </div>
      ${c.waiting.length > 0 && html`<div class="note caution ro-waiting">${c.waiting.join(' and ')}: picked, not applied yet.
        Open the window and press Apply to this player.</div>`}

      <div class="ro-sec caps">Player</div>
      <div class="ro-form">
        <${Row} label="First name" k="first" c=${c} form=${form} edited=${edited}><${Input} k="first" form=${form} set=${set} off=${off}/><//>
        <${Row} label="Last name" k="last" c=${c} form=${form} edited=${edited}><${Input} k="last" form=${form} set=${set} off=${off}/><//>
        <${Row} label="Number" k="num" c=${c} form=${form} edited=${edited}><${Input} k="num" form=${form} set=${set} off=${off} numeric/><//>
        <${Row} label="Position" k="pos" c=${c} form=${form} edited=${edited}>
          <${Select} value=${form.pos} disabled=${off || c.goalie} options=${c.choices.positions.map((p) => ({ value: p, label: p }))}
            title=${c.goalie ? 'A goalie stays a goalie.' : 'A skater cannot become a goalie.'} onChange=${(v) => set('pos', v)}/><//>
        <${Row} label=${c.goalie ? 'Catches' : 'Shoots'} k="shoots" c=${c} form=${form} edited=${edited}>
          <${Segmented} className="ro-seg" value=${form.shoots} disabled=${off}
            options=${[{ value: 'L', label: 'Left' }, { value: 'R', label: 'Right' }]} onChange=${(v) => set('shoots', v)}/><//>
        <${Row} label="Letter" k="captain" c=${c} form=${form} edited=${edited}>
          <${Segmented} className="ro-seg" value=${Number(form.captain) || 0} disabled=${off || !!c.locked.captain}
            options=${c.choices.letters.map(([value, label]) => ({ value, label, title: c.locked.captain || undefined }))}
            onChange=${(v) => set('captain', v)}/><//>
        <${Row} label="Born" k="born" c=${c} form=${form} edited=${edited}><${Input} k="born" form=${form} set=${set} off=${off} placeholder="1997-01-13"/><//>
        <${Row} label="Country" k="country" c=${c} form=${form} edited=${edited}>
          <${Select} value=${form.country} disabled=${off} options=${c.choices.countries.map(([value, label]) => ({ value, label }))}
            onChange=${(v) => set('country', v)}/><//>
        <${Row} label="Height (cm)" k="height" c=${c} form=${form} edited=${edited} aside=${imperial(form.height)}>
          <${Input} k="height" form=${form} set=${set} off=${off} numeric/><//>
        <${Row} label="Weight (kg)" k="weight" c=${c} form=${form} edited=${edited} aside=${pounds(form.weight)}>
          <${Input} k="weight" form=${form} set=${set} off=${off} numeric/><//>
        <${Row} label="Cap hit ($M)" k="salary" c=${c} form=${form} edited=${edited} aside=${Number(form.salary) ? money(Number(form.salary)) : ''}>
          <${Input} k="salary" form=${form} set=${set} off=${off}/><//>
        <${Row} label="Years left" k="years" c=${c} form=${form} edited=${edited}><${Input} k="years" form=${form} set=${set} off=${off} numeric/><//>
      </div>

      <div class="ro-sec caps">Face & type</div>
      <div class="ro-form ro-read">
        <div class="ro-row"><span class="ro-lab">Type${edited.has('type') && html`<i class="ro-dot"></i>`}</span><span class="ro-val">${c.type.label}</span></div>
        <div class="ro-row"><span class="ro-lab">Face${edited.has('face') && html`<i class="ro-dot"></i>`}</span>
          <span class="ro-val">${c.face.text}${c.face.generic && html` <${Tag} tone="caution">generic<//>`}</span></div>
        <div class="ro-row"><span class="ro-lab">Colours</span><span class="ro-val">${c.face.colours}</span></div>
        ${c.face.hint && html`<div class="small-note ro-hint">${c.face.hint}</div>`}
      </div>

      <div class="ro-sec caps">Equipment</div>
      <div class="ro-form ro-read">
        ${c.gear.map((g) => html`<div key=${g.label} class="ro-row"><span class="ro-lab">${g.label}${edited.has('gear') && html`<i class="ro-dot"></i>`}</span>
          <span class="ro-val" title=${g.value}>${g.value}</span></div>`)}
        ${c.gear_note && html`<div class="small-note ro-hint">${c.gear_note}</div>`}
      </div>

      <div class="ro-sec caps">Ratings <span class="faint">0-99</span></div>
      ${ratingProblem.length > 0 && html`<div class="ro-problem ro-problem-block">${ratingProblem.map((p) => p.text).join(' ')}</div>`}
      ${c.rating_groups.map((g) => html`<${Fragment} key=${g.title}>
        <div class="ro-group">${g.title}</div>
        <div class="ro-ratings">${g.items.map(([k, label]) => html`<label key=${k}
            class=${cls('ro-rt', ratingProblem.some((p) => p.key === `ratings.${k}`) ? 'bad' : typedRating(form, c, k) && 'typed')}>
          <span title=${label}>${label}${edited.has(`ratings.${k}`) && html`<i class="ro-dot"></i>`}</span>
          <input class="field" data-k=${`ratings.${k}`} inputmode="numeric" maxlength="2" disabled=${off}
            value=${(form.ratings || {})[k] ?? ''} onInput=${(e) => setRating(k, digits(e.target.value))}/></label>`)}
        </div><//>`)}
    </div>
    <div class="card-foot ro-foot">
      <${Button} kind="primary" className="ro-apply" disabled=${off || !dirty} onClick=${onApply}>Apply<//>
      <${Button} className="ro-undo" disabled=${off || !(dirty || c.can_undo)} onClick=${onUndo}
        title=${dirty ? 'Forget what you typed' : c.undo_label}>Undo my edit<//>
      <span class="sp"></span>
      <span class="ro-enter faint">Enter applies</span>
    </div>
  <//>`;
}

// --- the tab ------------------------------------------------------------------------------------------------------
const startForm = (c) => (c ? { ...c.values, ...(c.typed || {}), ratings: { ...c.values.ratings, ...((c.typed || {}).ratings || {}) } } : {});

export default function Roster({ go }) {
  const s = useSlice('roster');
  const c = useSlice('roster_card');
  const [form, setForm] = useState({});
  const [dirty, setDirty] = useState(false);
  const was = useRef({ id: null, form: {}, dirty: false });
  const key = c ? c.key : null;

  // a card filled again by Python: what was typed was applied or dropped there. Another player now (the rail moved
  // on): what was typed on the last one goes to Python to keep (it keeps only what differs from his card).
  useEffect(() => {
    const old = was.current;
    if (old.dirty && old.id != null && (!c || old.id !== c.id)) call('roster_keep', old.id, old.form);
    setForm(startForm(c));
    setDirty(!!(c && c.typed));
  }, [key]);
  useEffect(() => { was.current = { id: c ? c.id : null, form, dirty }; });

  const draft = dirty && c ? { id: c.id, values: form } : null;
  cardDraft.current = draft;

  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setDirty(true); };
  const setRating = (k, v) => { setForm((f) => ({ ...f, ratings: { ...(f.ratings || {}), [k]: v } })); setDirty(true); };
  const apply = () => { if (dirty) call('roster_apply', form); };
  const undo = () => call('roster_undo', dirty ? 'typed' : 'applied');
  const pick = (id) => { if (!c || id !== c.id) call('roster_player', id, draft); };

  if (!s) return null;
  if (!s.loaded) {
    return html`<${Card} title="Roster" className="ro-none"><div class="card-body fill ro-none-body">
      <div class="ro-none-box"><b>No roster is open yet.</b><span>Pick one in Setup, then come back to edit its players.</span>
        <${Button} kind="primary" onClick=${() => go('setup')}>Go to Setup<//></div></div><//>`;
  }
  return html`<div class=${cls('ro-tab', s.busy && 'busy')}>
    <${Players} s=${s} onPick=${pick}/>
    <${PlayerCard} s=${s} c=${c} form=${form} set=${set} setRating=${setRating} dirty=${dirty} onApply=${apply} onUndo=${undo}/>
  </div>`;
}
