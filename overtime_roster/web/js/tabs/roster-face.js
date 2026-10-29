// Roster's Face & type window: the player's type (his ratings follow it), his face parts from the lists the game's
// own roster wears, or another player's whole face. Picks wait in Python until Apply to this player; closing the
// window keeps them (Save asks about them). Slice roster_face; calls roster_face_*.
import { html, cls, useEffect, useRef } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Modal, TextField, Select, Empty, Tag } from '../ui.js';

const PARTS = ['head', 'hair', 'brows', 'beard'];
const COLOURS = ['skin', 'eyes', 'hair_colour', 'brow_colour', 'beard_colour'];
const range = ([lo, hi]) => Array.from({ length: hi - lo + 1 }, (_, k) => lo + k);
const word = (f, k) => (f.words[k] || k).replace(/^./, (x) => x.toUpperCase());

const optionLabel = (f, k, n) => (k === 'head' && n >= f.generic_from ? `${n} (generic)`
  : k === 'hair' && n < 0 ? "Head's own" : String(n));

function PartRow({ f, k, options }) {
  const changed = f.changed.includes(k);
  return html`<div class=${cls('ro-frow', changed && 'changed')} data-k=${k}>
    <span class="ro-lab">${word(f, k)}</span>
    <${Select} className="ro-fsel" value=${f.face[k]} disabled=${f.busy} title=${`Was ${f.current[k]}`}
      options=${options.map((n) => ({ value: n, label: optionLabel(f, k, n) }))}
      onChange=${(v) => call('roster_face_pick', k, v)}/>
    <span class="ro-was">${changed ? html`<span class="pill">changed</span>` : ''}</span>
  </div>`;
}

export function FaceWindow() {
  const f = useSlice('roster_face');
  const list = useRef(null);
  useEffect(() => { if (list.current) list.current.scrollTop = 0; }, [f && f.query]);
  if (!f || !f.open) return null;
  const close = () => call('roster_face_close');
  return html`<${Modal} full className="ro-face" title=${`Face & type: ${f.name}`} onClose=${close} buttons=${html`
      <span class="ro-mnote">${f.can_apply ? 'Picked, not applied yet. Closing keeps the picks.' : ''}</span>
      <${Button} kind="pick" className="ro-apply" disabled=${!f.can_apply || f.busy} onClick=${() => call('roster_face_apply')}>Apply to this player<//>
      <${Button} className="ro-take-back" disabled=${!f.can_take_back || f.busy} onClick=${() => call('roster_face_undo')}
        title="His type and face as they were before your edits">Take back my face edits<//>
      <${Button} onClick=${close}>Close<//>`}>
    <p class="small-note">Pick his type, change parts of his face, or take another player's whole face. The lists hold what
      the game's own roster wears, so the game can draw it. Apply puts it on the roster; Save writes it.</p>
    ${f.note && html`<div class="note caution">${f.note}</div>`}
    <div class="ro-fw">
      <section class="ro-fcol ro-type">
        <div class="ro-fhead caps">Player type ${f.type.changed && html`<span class="pill">changed</span>`}</div>
        <div class="small-note">The game shows it next to his overall. A new type moves his ratings the way the game's
          own players of that type have them, so his overall follows.</div>
        <div class="ro-items">
          ${f.type.choices.map((t) => html`<button type="button" key=${t.value}
              class=${cls('item', t.value === f.type.value && 'sel')} disabled=${f.busy}
              onClick=${() => call('roster_face_type', t.value)}>
            <span class="ro-short">${t.short}</span><span class="main"><span class="title">${t.label}</span>
              <span class="sub">${t.value === f.type.current ? 'His type now' : t.move > 0 ? `About +${t.move} overall`
                : t.move < 0 ? `About ${t.move} overall` : 'About the same overall'}</span></span>
          </button>`)}
        </div>
        ${!f.type.fits && html`<div class="note caution">His type now does not fit his position. Pick one of these.</div>`}
      </section>
      <section class="ro-fcol ro-parts">
        <div class="ro-fhead caps">Face ${f.from && html`<${Tag} tone="info">${f.from}'s face<//>`}</div>
        <div class="ro-fform">
          ${PARTS.map((k) => html`<${PartRow} key=${k} f=${f} k=${k} options=${f.parts[k]}/>`)}
          ${COLOURS.map((k) => html`<${PartRow} key=${k} f=${f} k=${k} options=${range(f.colours[k] || [0, 0])}/>`)}
        </div>
        <div class="small-note">Heads from ${f.generic_from} up are the game's generic heads. The hair comes with a head;
          pick another hair to change it.</div>
      </section>
      <section class="ro-fcol ro-copy">
        <div class="ro-fhead caps">Another player's face</div>
        <${TextField} className="ro-fsearch" value=${f.query} placeholder="Find a player" delay=${220}
          onChange=${(t) => call('roster_face_search', t)}/>
        <div class="ro-ftitle faint">${f.found_title}</div>
        <div class="ro-found scroll" ref=${list}>
          ${f.found.length === 0 && html`<${Empty} small>Nobody by that name.<//>`}
          ${f.found.map((p) => html`<button type="button" key=${p.id} class="item" disabled=${f.busy}
              title=${`Take ${p.name}'s face`} onClick=${() => call('roster_face_copy', p.id)}>
            <span class="main"><span class="title">${p.name}</span><span class="sub">${p.pos} · ${p.team}</span></span>
            <span class=${cls('ro-head', p.generic && 'generic')}>${p.generic ? 'generic' : 'own face'}</span>
          </button>`)}
        </div>
      </section>
    </div>
  <//>`;
}
