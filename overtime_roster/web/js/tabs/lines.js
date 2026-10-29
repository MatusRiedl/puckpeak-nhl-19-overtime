// The Lines tab: Legacy's Lines tab (click a place, then a player) in NHL 19's look. Python keeps a draft of the team's
// lines; Apply hands it to My edits. Slice `lines`, calls in docs/ui/lines.md.
import { html, cls } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Segmented, Why as UiWhy } from '../ui.js';
import { Code } from '../rail.js';

export const tip = 'Click a place in a line, then the player for it. Apply when the lines are right.';

let picked = null;                       // for Escape: the place picked in the slice drawn last

// Escape lets go of a picked place (before the shell's Escape closes the details)
export function onKey(e) {
  if (e.key !== 'Escape' || !picked || e.altKey || e.ctrlKey) return false;
  call('lines_slot', picked);
  return true;
}

// a team the tab cannot show, or the roster still being read (Legacy's Why)
function Why({ s }) {
  return html`<${UiWhy} className="ln-why" mark=${s.view && html`<${Code} team=${s.view}/>`} text=${s.why} busy=${s.loading}/>`;
}

function Who({ p }) {
  if (!p) return html`<span class="ln-who ln-none"><b>Empty</b><span class="faint">Pick a player</span></span>`;
  const hand = p.shoots ? ` · ${p.pos === 'G' ? 'catches' : 'shoots'} ${p.shoots}` : '';
  return html`<span class="ln-who"><b>${p.name}</b><span class="faint">${p.pos}${hand} · ${p.ovr}</span></span>`;
}

function Units({ s }) {
  return html`<div class="ln-units scroll">${s.units.map((u) => html`<div key=${u.title} class=${`ln-unit n${u.slots.length}`}>
      <div class="ln-unit-title subhead">${u.title}</div>
      <div class="ln-slots">${u.slots.map((sl) => html`<button type="button" key=${sl.slot}
          class=${cls('ln-slot', sl.picked && 'on', sl.changed && 'changed', !sl.player && 'hole')}
          title=${`${sl.full[0].toUpperCase()}${sl.full.slice(1)}${sl.changed ? ' (changed)' : ''}`}
          onClick=${() => call('lines_slot', sl.slot)}>
          <span class="k caps">${sl.label}</span><${Who} p=${sl.player}/></button>`)}</div>
    </div>`)}</div>`;
}

function Side({ s }) {
  const head = s.picked ? `Who plays ${s.picked_label}?` : 'Players';
  return html`<div class="ln-side">
    <div class=${cls('ln-side-head', s.picked && 'picked')}>
      <span class="ln-side-title caps" title=${head}>${head}</span>
      ${s.picked ? html`<${Button} small onClick=${() => call('set_slot', s.picked, null)} disabled=${!s.can_empty}
          title="Nobody plays in this place">Leave empty<//>`
        : html`<span class="faint ln-count">${s.dressed} dressed</span>`}
    </div>
    ${!s.picked && html`<p class="small-note faint ln-hint">Click a place first, then the player for it.</p>`}
    <div class="list scroll ln-list">${s.players.map((p) => html`<button type="button" key=${p.id}
        class=${cls('ln-row', !p.dressed && 'scratch', s.picked && !p.fits && 'off', p.here && 'here')}
        disabled=${!s.picked || !p.fits} title=${p.why || (s.picked ? `Put ${p.name} here` : '')}
        onClick=${() => call('set_slot', s.picked, p.id)}>
        <${Who} p=${p}/>
        ${p.letter ? html`<span class="ln-letter">${p.letter}</span>` : html`<span></span>`}
        <span class="faint ln-where" title=${p.where}>${p.places.length ? p.places.map((w) => html`<span key=${w}>${w}</span>`)
          : p.dressed ? '' : 'Scratched'}</span>
      </button>`)}</div>
  </div>`;
}

const LETTER_OPTIONS = [{ value: 1, label: 'C' }, { value: 2, label: 'A' }, { value: 0, label: 'None' }];
const LETTER_VALUE = { C: 1, A: 2, '': 0 };

function Letters({ s }) {
  return html`<div class="list scroll ln-letters">${s.players.map((p) => html`<div key=${p.id}
      class=${cls('ln-row', 'ln-letter-row', !p.dressed && 'scratch', p.letter_changed && 'changed')}>
      <${Who} p=${p}/>
      <span class="faint ln-where">${p.dressed ? (p.letter_changed ? 'Changed' : '') : 'Scratched'}</span>
      <${Segmented} options=${LETTER_OPTIONS} value=${LETTER_VALUE[p.letter || '']}
        onChange=${(v) => call('set_captain', p.id, v)}/>
    </div>`)}</div>`;
}

export default function Lines() {
  const s = useSlice('lines');
  picked = s && s.picked;
  if (!s) return null;
  if (s.why) return html`<${Why} s=${s}/>`;
  const letters = s.page === 'Letters';
  return html`<section class="card grow ln-tab">
    <header class="card-head ln-head">
      ${s.view && html`<${Code} team=${s.view} small/>`}
      <span class="title ln-title">${s.title}</span>
      <${Segmented} className="ln-pages" options=${s.pages.map((p) => ({ value: p.id, label: p.label }))} value=${s.page}
        onChange=${(v) => call('lines_section', v)}/>
      ${s.touched && html`<span class="aside"><span class="pill">Not applied</span></span>`}
    </header>
    <div class="card-body fill ln-body">
      <p class=${cls('small-note ln-note', s.note_tone)}>${s.note}</p>
      ${letters ? html`<div class="ln-main letters"><${Letters} s=${s}/></div>`
        : html`<div class="ln-main"><${Units} s=${s}/><${Side} s=${s}/></div>`}
      ${s.problems.length > 0 && html`<div class="note caution ln-problems">
        ${s.problems.slice(0, 3).map((t) => html`<div key=${t}>${t}</div>`)}
        ${s.problems.length > 3 && html`<div>... and ${s.problems.length - 3} more.</div>`}
        <div class="faint">The game plays it like this, so Apply works anyway. To fill it, click the place, then a
          player.</div>
      </div>`}
    </div>
    <div class="card-foot ln-foot">
      <${Button} kind="primary" disabled=${!s.can_apply} onClick=${() => call('lines_apply')}
        title=${s.problems.length ? 'The game plays it like this too' : ''}>Apply<//>
      <${Button} disabled=${!s.can_undo} onClick=${() => call('lines_undo')}
        title="Drop your changes and put back the lines the roster had">Take back my lines<//>
      <span class="small-note faint ln-foot-note">${s.mine ? 'This team plays your lines. Save the roster to keep them.'
        : 'Changes wait here until you press Apply.'}</span>
      ${s.can_auto && html`<${Button} kind="ghost" className="ln-auto" onClick=${() => call('auto_group', s.page)}
        title="Deal the places of this page again by the players' ratings">${s.auto_label}<//>`}
    </div>
  </section>`;
}
