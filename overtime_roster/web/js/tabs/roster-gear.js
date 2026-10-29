// Roster's Equipment window: what the player uses (the Creation Zone's own models) and his tape colours. A helmet,
// gloves, visor, tint, the tucks, pants and tape can go to the whole team. Picks wait in Python until Apply; closing
// the window keeps them (Save asks about them). Slice roster_gear; calls roster_gear_*.
import { html, cls, useEffect, useRef } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Modal, TextField, Empty } from '../ui.js';

const pick = (r, v) => call('roster_gear_pick', r.key, v);

// a long list of models: tiles that scroll, the one in use brought into view when the window opens
function Grid({ r, off }) {
  const box = useRef(null);
  useEffect(() => {
    const el = box.current && box.current.querySelector('.ro-eq-opt.on');
    if (el) box.current.scrollTop += el.getBoundingClientRect().top - box.current.getBoundingClientRect().top;
  }, [r.key]);
  return html`<div class="ro-eq-grid scroll" ref=${box}>${r.options.map(([n, label]) => html`<button type="button" key=${n}
      class=${cls('ro-eq-opt', n === r.value && 'on', n === r.current && 'was')} disabled=${off} title=${`${label} (model ${n})`}
      onClick=${() => pick(r, n)}>${label}</button>`)}</div>`;
}

function Colour({ r, swatches, off }) {
  return html`<div class="ro-eq-colour">
    <span class="ro-swatch-big" style=${{ background: r.value }} title=${r.value}></span>
    ${swatches.map((c) => html`<button type="button" key=${c} class=${cls('ro-swatch', c === r.value && 'on')} disabled=${off}
      style=${{ background: c }} title=${c} onClick=${() => pick(r, c)}></button>`)}
    <${TextField} className="ro-hex" value=${r.value} disabled=${off} delay=${600} onChange=${(t) => pick(r, t)}/>
  </div>`;
}

function GearRow({ r, swatches, off }) {
  return html`<div class=${cls('ro-eq-row', r.changed && 'changed', `show-${r.show}`)}>
    <div class="ro-eq-head">
      <span class="caps">${r.label}</span>
      ${r.changed && html`<span class="pill">changed</span>`}
      ${r.team_wide && html`<span class="ro-shared faint" title="Apply to the whole team gives this to every teammate">team can share</span>`}
    </div>
    ${r.show === 'buttons' && html`<div class="ro-eq-buttons">${r.options.map(([n, label]) => html`<button type="button" key=${n}
        class=${cls('ro-eq-opt', n === r.value && 'on', n === r.current && 'was')} disabled=${off} onClick=${() => pick(r, n)}>${label}</button>`)}</div>`}
    ${r.show === 'grid' && html`<${Grid} r=${r} off=${off}/>`}
    ${r.show === 'colour' && html`<${Colour} r=${r} swatches=${swatches} off=${off}/>`}
    ${r.show === 'number' && html`<div class="ro-eq-number">
      <${TextField} className="ro-num" value=${String(r.value)} disabled=${off} delay=${600} onChange=${(t) => pick(r, t)}/>
      <span class="small-note">The game's own mask numbers. A picture of your own comes later.</span></div>`}
  </div>`;
}

export function GearWindow() {
  const g = useSlice('roster_gear');
  if (!g || !g.open) return null;
  const close = () => call('roster_gear_close');
  const off = g.busy;
  return html`<${Modal} full className="ro-gear" title=${`Equipment: ${g.name}`} onClose=${close} buttons=${html`
      <span class="ro-mnote">${g.can_apply ? 'Picked, not applied yet. Closing keeps the picks.' : ''}</span>
      <${Button} kind="pick" className="ro-apply" disabled=${!g.can_apply || off} onClick=${() => call('roster_gear_apply', false)}>Apply to this player<//>
      <${Button} className="ro-team-apply" disabled=${!g.can_team || off} title=${g.team_title}
        onClick=${() => call('roster_gear_apply', true)}>${g.team_label}<//>
      <${Button} className="ro-take-back" disabled=${!g.can_take_back || off} onClick=${() => call('roster_gear_undo')}
        title="His equipment as it was before your edits">Take back my equipment edits<//>
      <${Button} onClick=${close}>Close<//>`}>
    <p class="small-note">Pick what ${g.kind === 'goalie' ? 'the goalie' : 'he'} uses: the models are the game's own, so a
      stick of 2026 is the nearest one the game has. Apply puts it on the roster; Save writes it.</p>
    ${g.none ? html`<${Empty}>${g.none}<//>` : html`<div class="ro-eq">
      ${g.rows.map((r) => html`<${GearRow} key=${r.key} r=${r} swatches=${g.swatches} off=${off}/>`)}
    </div>`}
  <//>`;
}
