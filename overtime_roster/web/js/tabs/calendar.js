// Calendar: the roster's own season as a month page (Monday to Sunday), the picked team's games (home "vs", away
// "@"), a day's games, the team's list of games, all games of its league (the NHL, the AHL for a farm club, the Liiga for a Liiga club), and
// "Sync with NHL.com" (84 or 82 games a team).
// Read only but for the sync, which waits in My edits like any edit; no Save bar here (Legacy's Calendar has none).
import { html, cls, useRef, useLayoutEffect } from '../lib.js';
import { useSlice } from '../store.js';
import { call } from '../bridge.js';
import { Button, Card, Segmented, Toggle, Tag, Field, Modal, ProgressBar, Why as UiWhy } from '../ui.js';
import { Code } from '../rail.js';

export const tip = 'Click a day for all its games. Click a game in the list to jump to its day.';

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function Day({ d, teamMode }) {
  const m = teamMode ? d.mine : null;
  const title = d.count ? plural(d.count, 'game', 'games') : 'No games';
  return html`<button type="button" title=${title}
      class=${cls('ca-day', d.out && 'out', d.today && 'today', d.sel && 'sel', m && (m.home ? 'home' : 'away'),
        !d.count && 'none')}
      onClick=${() => call('calendar_day', d.date)}>
    <span class="n">${d.n}</span>
    ${m ? html`<span class="g"><span class="at">${m.home ? 'vs' : '@'}</span> ${m.vs}</span>`
      : d.count > 0 && html`<span class=${cls('cnt', !teamMode && 'big')}>${d.count}<i>${d.count === 1 ? ' game' : ' games'}</i></span>`}
  </button>`;
}

// "My season": the results of the player's own Franchise or Season save on this calendar. Not in beta2.
function SeasonSwitch({ season }) {
  if (!season) return null;
  return html`<div class=${cls('ca-season', !season.available && 'off')} title=${season.note}>
    <${Toggle} on=${season.on} disabled=${!season.available} label=${season.label}
      onChange=${(v) => call('calendar_season', v)}/>
    <span>${season.label}</span>
    ${!season.available && html`<${Tag}>Comes after beta2<//>`}
  </div>`;
}

function SyncButton({ s }) {
  const sync = s.sync || {};
  return html`<div class="ca-sync-line">
    <${Tag} tone=${sync.tone} title=${sync.title}>${sync.text}<//>
    <${Button} small className="ca-sync-btn" disabled=${s.busy} onClick=${() => call('calendar_sync_open')}>Sync with NHL.com...<//>
  </div>`;
}

function Month({ s }) {
  const teamMode = s.mode === 'team';
  return html`<section class="card grow ca-month">
    <header class="card-head ca-head">
      <button type="button" class="ca-arrow" disabled=${!s.can_prev} title="The month before"
        onClick=${() => call('calendar_month', -1)}>‹</button>
      <span class="title ca-title">${s.title}</span>
      <button type="button" class="ca-arrow" disabled=${!s.can_next} title="The month after"
        onClick=${() => call('calendar_month', 1)}>›</button>
      <${Button} small onClick=${() => call('calendar_today')}>Today<//>
      <span class="sp"></span>
      <${Segmented} className="ca-mode" value=${s.mode} onChange=${(m) => call('calendar_mode', m)}
        options=${[{ value: 'team', label: s.team_mode ? `${s.team.code}'s games` : 'Team games', disabled: !s.team_mode,
          title: s.team_mode ? undefined : 'This team plays no games in the calendar.' },
        { value: 'league', label: s.league_label || 'All NHL games' }]}/>
    </header>
    <div class="ca-grid" style=${{ '--weeks': s.weeks.length }}>
      ${s.weekdays.map((w) => html`<div key=${w} class="ca-wd caps">${w}</div>`)}
      ${s.weeks.flat().map((d) => html`<${Day} key=${d.date} d=${d} teamMode=${teamMode}/>`)}
    </div>
    <footer class="ca-foot">
      ${teamMode ? html`<span class="ca-legend"><span class="ca-key home">vs</span>home game</span>
          <span class="ca-legend"><span class="ca-key away">@</span>away game</span>`
        : html`<span>${s.count_note}</span>`}
      <${SyncButton} s=${s}/>
      <span class="sp"></span>
      <${SeasonSwitch} season=${s.season}/>
    </footer>
  </section>`;
}

function TeamCard({ s }) {
  const sum = s.summary;
  return html`<${Card} className="ca-team" title=${html`<${Code} team=${s.team} small/><span>${s.team.name}</span>`}>
    <div class="card-body">
      <div class="ca-tiles">
        <div class="ca-tile"><b>${sum.gp}</b><span>games</span></div>
        <div class="ca-tile home"><b>${sum.home}</b><span>home</span></div>
        <div class="ca-tile away"><b>${sum.away}</b><span>away</span></div>
      </div>
      <div class="ca-next">${sum.next ? html`Next: <b>${sum.next}</b>` : 'No games left this season.'}</div>
    </div>
  <//>`;
}

function DayCard({ day }) {
  const n = day.games.length;
  const title = html`<span class="long">${day.title}</span><span class="short">${day.short}</span>`;
  return html`<${Card} className="ca-daycard" title=${title} aside=${html`<span>${n ? plural(n, 'game', 'games') : 'No games'}</span>
      <button type="button" class="ca-x" title="Close" onClick=${() => call('calendar_day', null)}>✕</button>`}>
    <div class="scroll"><div class="ca-games">
      ${day.games.map((g) => html`<div key=${g.key} class=${cls('ca-match', g.mine && 'mine')}>
        <${Code} team=${g.away} small/><span class="at">@</span><${Code} team=${g.home} small/>
        <span class="names" title=${`${g.away.name} at ${g.home.name}`}>${g.away.name} at ${g.home.name}</span>
      </div>`)}
      ${!n && html`<div class="empty small">No games this day.</div>`}
    </div></div>
  <//>`;
}

// the list follows the page: the open day's game stays in sight, else the month on the page starts the list
function useFollow(box, s) {
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const at = (n) => n.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop;
    const row = el.querySelector('.ca-row.sel');
    if (row) {
      const y = at(row);
      if (y < el.scrollTop + 30 || y + row.offsetHeight > el.scrollTop + el.clientHeight) el.scrollTop = y - el.clientHeight / 3;
      return;
    }
    const group = el.querySelector(`.ca-mgroup[data-ym="${s.month}"]`);
    if (group) el.scrollTop = at(group);
  }, [s.month, s.day && s.day.date, s.team && s.team.id, s.summary && s.summary.gp]);
}

function GameList({ s }) {
  const sum = s.summary;
  const box = useRef(null);
  useFollow(box, s);
  return html`<${Card} title="Games" aside=${`${sum.gp} · ${sum.home} H / ${sum.away} A`} grow className="ca-list">
    <div class="scroll" ref=${box}><div class="ca-months">
      ${s.months.map((m) => html`<div key=${m.ym} class="ca-mgroup" data-ym=${m.ym}>
        <div class="ca-mlabel caps">${m.label}</div>
        ${m.games.map((g) => html`<button type="button" key=${g.date} class=${cls('ca-row', g.sel && 'sel', g.past && 'past')}
            onClick=${() => call('calendar_day', g.date)}>
          <span class="d">${g.label}</span><span class=${cls('ha', g.home ? 'home' : 'away')}>${g.home ? 'vs' : '@'}</span>
          <span class="vs">${g.vs}</span>
        </button>`)}
      </div>`)}
    </div></div>
  <//>`;
}

function Why({ s }) {
  return html`<${UiWhy} className="ca-why" mark=${s.team && html`<${Code} team=${s.team}/>`} text=${s.why}>
    ${s.can_league && html`<${Button} small onClick=${() => call('calendar_mode', 'league')}>All NHL games<//>`}
  <//>`;
}

export default function Calendar() {
  const s = useSlice('calendar');
  if (!s) return null;
  if (s.why) return html`<${Why} s=${s}/>`;
  const teamMode = s.mode === 'team';
  return html`<div class="ca">
    <${Month} s=${s}/>
    <div class="ca-side">
      ${teamMode && html`<${TeamCard} s=${s}/>`}
      ${s.day && html`<${DayCard} day=${s.day}/>`}
      ${teamMode ? html`<${GameList} s=${s}/>`
        : !s.day && html`<div class="card ca-hint">
          ${s.why_note && html`<div class="ca-hint-team">${s.team && html`<${Code} team=${s.team} small/>`}<p>${s.why_note}</p></div>`}
          <p>Click a day to see its games.</p>
        </div>`}
    </div>
  </div>`;
}

// the pop-up of "Sync with NHL.com...": NHL.com's season against the roster's, 84 or 82 games a team, then write
function SyncWindow() {
  const s = useSlice('calendar_sync');
  if (!s || !s.open) return null;
  const close = () => call('calendar_sync_close');
  const checking = s.step === 'checking';
  return html`<${Modal} title="Sync with NHL.com" className="ca-sync" onClose=${close}
    buttons=${html`<${Button} kind="primary" disabled=${!s.can_apply} onClick=${() => call('calendar_sync_apply')}>Use this calendar<//>
      <${Button} onClick=${close}>Close<//>`}>
    <p>Gets NHL.com's ${s.season} regular season and puts it in this roster's calendar.</p>
    ${checking && html`<div class="ca-checking"><${ProgressBar} indeterminate/><span>Asking NHL.com...</span></div>`}
    ${s.error && html`<div class="ca-error"><span class="note bad">${s.error}</span>
      <${Button} small disabled=${s.busy} onClick=${() => call('calendar_sync_retry')}>Try again<//></div>`}
    ${s.real && html`<div class="ca-compare">
      <div class="ca-cmp"><span class="caps">NHL.com ${s.season}</span><b>${s.real.games.toLocaleString('en-US')} games</b>
        <span>${s.real.per_team} a team · ${s.real.range}</span></div>
      <div class="ca-cmp"><span class="caps">This roster</span><b>${s.roster.games.toLocaleString('en-US')} games</b>
        <span>${s.roster.per_team} a team</span></div>
      <div class="ca-verdict">${s.moved ? html`<${Tag} tone="caution">${s.moved} games differ<//>`
        : html`<${Tag} tone="good">Same games as NHL.com<//>`}</div>
    </div>`}
    <${Field} label="Games a team" hint=${s.hint} className="ca-length">
      <${Segmented} value=${s.games} disabled=${checking || !!s.error || s.busy} options=${s.options}
        onChange=${(n) => call('calendar_sync_games', n)}/>
    <//>
    <p class="small-note ca-others">${s.others}</p>
    ${s.apply_note && html`<p class=${cls('ca-apply', s.can_apply ? 'go' : 'faint')}>${s.apply_note}</p>`}
  <//>`;
}

export function Modals() {
  return html`<${SyncWindow}/>`;
}
