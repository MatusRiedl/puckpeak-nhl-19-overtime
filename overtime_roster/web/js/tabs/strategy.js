// The Strategy tab: Legacy's Strategy tab (the team's strategies in sections) in NHL 19's look: a choice is NHL 19's
// arrows round the value, a tendency a slider between its two words. Python keeps a draft per team; Apply hands it to
// My edits. Slice `strategy`, calls in docs/ui/strategy.md.
import { html, cls } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Select, Checkbox, Why as UiWhy } from '../ui.js';
import { Code } from '../rail.js';

export const tip = 'Change a strategy, then Apply. Save writes it into the roster.';

const set = (field, value) => call('strategy_set', field, value);

// a team the tab cannot show, or the roster still being read (Legacy's Why)
function Why({ s }) {
  return html`<${UiWhy} className="st-why" mark=${s.view && html`<${Code} team=${s.view}/>`} text=${s.why} busy=${s.loading}/>`;
}

const Arrow = ({ left }) => html`<svg viewBox="0 0 8 12" aria-hidden="true">
  <path d=${left ? 'M8 0v12L0 6z' : 'M0 0v12l8-6z'} fill="currentColor"/></svg>`;

// a choice: NHL 19's arrows round the value; the value opens the whole list
function Choice({ r }) {
  const options = r.bad ? [...r.options, { value: r.value, label: `${r.value}: not a game value`, disabled: true }] : r.options;
  return html`<div class="st-step">
    <button type="button" class="st-arrow prev" disabled=${r.value <= 0 || r.bad} title="The one before"
      onClick=${() => set(r.field, r.value - 1)}><${Arrow} left/></button>
    <${Select} className="st-select" value=${r.value} options=${options} title=${r.label}
      onChange=${(v) => set(r.field, v)}/>
    <button type="button" class="st-arrow next" disabled=${r.value >= r.top && !r.bad} title="The one after"
      onClick=${() => set(r.field, r.bad ? r.top : r.value + 1)}><${Arrow}/></button>
  </div>`;
}

// a tendency: a slider with its two words under its ends, the value at the end
function Slider({ r }) {
  const v = Math.max(0, Math.min(r.top, r.value));
  return html`<div class="st-slider">
    <div class="st-track">
      <input type="range" min="0" max=${r.top} step="1" value=${v} aria-label=${r.label}
        style=${{ '--p': `${(v / r.top) * 100}%` }} onChange=${(e) => set(r.field, Number(e.target.value))}/>
      <div class="st-words"><span title=${r.left}>${r.left}</span><span title=${r.right}>${r.right}</span></div>
    </div>
    <b class="st-v" title=${r.bad ? `${r.value} is not a game value: pick one from 0 to ${r.top}` : ''}>${r.value}</b>
  </div>`;
}

function Section({ sec }) {
  return html`<div class="st-sec">
    <div class="st-sec-title subhead">${sec.title}</div>
    ${sec.rows.map((r) => html`<div key=${r.field}
        class=${cls('st-row', r.changed && 'changed', r.hidden && 'hidden', r.bad && 'bad')}
        title=${r.changed ? 'Changed, not applied' : ''}>
        <span class="st-label">${r.label}${r.hidden && html`<span class="st-tag faint">Not in the game's menu</span>`}</span>
        ${r.kind === 'choice' ? html`<${Choice} r=${r}/>` : html`<${Slider} r=${r}/>`}
      </div>`)}
  </div>`;
}

export default function Strategy() {
  const s = useSlice('strategy');
  if (!s) return null;
  if (s.why) return html`<${Why} s=${s}/>`;
  return html`<section class="card grow st-tab">
    <header class="card-head st-head">
      ${s.view && html`<${Code} team=${s.view} small/>`}
      <span class="title">${s.title}</span>
      ${s.touched && html`<span class="aside"><span class="pill">Not applied</span></span>`}
    </header>
    <div class="card-body scroll st-body">
      <p class=${cls('small-note st-note', s.note_tone)}>${s.note}</p>
      ${s.problems.length > 0 && html`<div class="note bad st-problems">
        ${s.problems.map((t) => html`<div key=${t}>${t}</div>`)}
        <div class="faint">Pick a value in the red row, or press Game defaults. Apply waits until every value is one the game uses.</div>
      </div>`}
      <div class="st-grid">${s.sections.map((sec) => html`<${Section} key=${sec.title} sec=${sec}/>`)}</div>
    </div>
    <div class="card-foot st-foot">
      <${Button} kind="primary" disabled=${!s.can_apply} onClick=${() => call('strategy_apply')}
        title=${s.problems.length ? 'Pick a game value in the red row first' : ''}>Apply<//>
      <${Button} disabled=${!s.can_defaults} onClick=${() => call('strategy_reset')}
        title=${s.defaults_why || 'Put NHL 19\'s own strategies for this team in; Apply writes them'}>Game defaults<//>
      <${Button} disabled=${!s.can_undo} onClick=${() => call('strategy_undo')}
        title="Drop your changes and put back the strategies the roster had">Take back my strategies<//>
      <span class="small-note faint st-foot-note">${s.mine ? 'This team plays your strategies. Save the roster to keep them.'
        : 'Changes wait here until you press Apply.'}</span>
      <span class="st-hidden-box"><${Checkbox} on=${s.show_hidden} onChange=${(on) => call('strategy_show_hidden', on)}
        title="Values the game keeps but its strategy menu does not show">
        <span class="st-hidden">Show the ${s.hidden_count} hidden values</span><//></span>
    </div>
  </section>`;
}
