"""Calendar: the rail's team's games month by month, every game of its league, and "Sync with NHL.com".
docs/ui/calendar.md.

The roster's own season, read from its schedule tables (overtime_core.calendar: one row a game, a month and a day but
no year; the year comes from the Update's season): the 32-team NHL calendar (nhl32schedule, the expansion Franchise's)
for the NHL clubs, in its own places (calendar.SLOTS32: Seattle 22, Utah 31); the 32-team AHL calendar (ahl32schedule) for an AHL club, whose teams are the
NHL organisations' slots (31: Seattle's farm club); the Liiga calendar (finnishschedule) for a Liiga club, whose teams are
the Liiga clubs in team order (leaguecal.LIIGA_SLOTS). Free agents, All-Stars and other leagues play no games here.

"Sync with NHL.com" asks NHL.com for the season (the data pack's copy when it can't), compares it with the roster's
32-team calendar and writes it into the four NHL schedule tables (calendar.apply: 84 games a team, or 82) in one edit
in My edits, as the Update does; the Save bar of another tab saves it. Beta1's calendar_team and snap_calendar
(update.calendar_view on `cal_team`) work as before. While the tab shows, `cal_team` follows the rail.
"""
import datetime
from calendar import Calendar    # the standard library's: whole weeks, Monday first

from overtime_core import calendar, leaguecal, nhlcom, ratings as R, teams as T

from . import jobs, labels as L, paths, update
from .rail import AHL, COLOURS, FA, GREY, SEATTLE, TEAMS, colour, why_tip
from .registry import Part
from .shell import TAB_LABELS

WEEKS = Calendar(0)
WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December')
AHL_TABLE = 'ahl32schedule'
LIIGA, LIIGA_TABLE = leaguecal.LIIGA_LEAGUE, leaguecal.LIIGA
LENGTHS = (84, 82)
COACHELLA = {'id': None, 'code': 'CV', 'name': 'Coachella Valley Firebirds',
             'colours': [colour(T.COACHELLA[k]) for k in COLOURS], 'league': 'AHL'}
DATA_ERRORS = (KeyError, IndexError, TypeError, ValueError, AttributeError)

NO_CALENDAR = 'This roster has no calendar. Open another roster in Setup.'
SEASON = {'on': False, 'available': False, 'label': 'My season',
          'note': 'Coming in a later version: the results of your own Franchise or Season on this calendar.'}
SEASON_LATER = 'My season comes in a later version: the results of your own Franchise or Season will show here.'
LEAGUE_TIP = "Click a day for all its games. Pick a team's games at the top right for its season."
SYNC_ERROR = 'NHL.com did not answer. Check your internet connection, then try again.'
SAME = 'Same as NHL.com. Pick 82 games if you want the shorter season.'
DIFFERS = "NHL.com's calendar differs in {n}. Use it to bring this roster up to date."
HINT_84 = 'Every real game. Franchise with Seattle plays all 84.'
HINT_82 = '{n} games come out, from the middle of the season. The first and last weeks stay as they are.'
OTHERS = ("Season, Be a Pro and Classic Franchise use the game's 31-team calendars: they get 82 games a team, "
          "without Seattle's games.")
WRITTEN = 'Calendar ready: {n} games a team. It is in My edits: save it with the Save bar on any other team tab.'


class SyncError(RuntimeError):
    """NHL.com's season could not be had (the message is for the player)."""


def short_day(d):
    return f'{WEEKDAYS[d.weekday()][:3]} {d.day} {MONTHS[d.month - 1][:3]}'


def long_day(d):
    return f'{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}'


def season_label(season):
    return f'{season}-{(season + 1) % 100:02d}'


def n_games(n):
    return f"{n:,} {'game' if n == 1 else 'games'}"


def shift(ym, n):
    k = ym[0] * 12 + ym[1] - 1 + n
    return k // 12, k % 12 + 1


def per_text(counts):
    """'84' when every team plays as many games, else '80 to 84'."""
    if not counts:
        return '0'
    lo, hi = min(counts.values()), max(counts.values())
    return str(lo) if lo == hi else f'{lo} to {hi}'


class Games:
    """One schedule table of the open roster as dated games: `list` [(key, date, home, away)] in date order (key: the
    row), by day and by team. Rows whose day does not exist in the season's years are left out."""

    def __init__(self, rows, start_year):
        self.list = []
        for i, (month, day, home, away) in enumerate(rows):
            try:
                self.list.append((i, calendar.season_date(month, day, start_year), home, away))
            except ValueError:
                continue
        self.list.sort(key=lambda g: g[1])      # stable: a day's games keep the table's order
        self.by_date, self.by_slot = {}, {}
        for g in self.list:
            self.by_date.setdefault(g[1], []).append(g)
            self.by_slot.setdefault(g[2], []).append(g)
            self.by_slot.setdefault(g[3], []).append(g)
        self.counts = {slot: len(games) for slot, games in self.by_slot.items()}
        self.keys = {(d.isoformat(), h, a) for _k, d, h, a in self.list}   # as calendar.rows_for gives them
        self.first = self.list[0][1] if self.list else None
        self.last = self.list[-1][1] if self.list else None

    def uniform(self):
        """Games per team when every team plays as many, else None."""
        values = set(self.counts.values())
        return values.pop() if len(values) == 1 else None


def targets(games):
    """{84: rows, 82: rows or None}: what calendar.apply writes into nhl32schedule from NHL.com's season `games`
    [(date, home code, away code)], as a set of (date, home slot, away slot) (None: no 82-game cut can be made)."""
    full = set(calendar.rows_for(games, 32))
    try:
        cut = set(calendar.rows_for(games, 32, 82))
    except calendar.CalendarError:
        cut = None
    return {84: full, 82: cut}


def real_season(season, offline=False, log=lambda msg: None):
    """(games, source) of the regular season starting in `season`: NHL.com's (cached a while), else the data pack's
    copy. Raises SyncError when neither has it."""
    if not offline:
        try:
            games = calendar.season_games(nhlcom.Client(cache_dir=paths.app_dir('cache')), season, log=log)
            if games:
                return games, 'NHL.com'
        except (nhlcom.NhlComError, OSError, ValueError) as err:
            log(f'NHL.com calendar: {err}')
    try:
        pack = R.load_pack(paths.app_dir('cache'), fetch=None if offline else update.fetch, offline=offline, log=log)
    except R.PackError as err:
        log(f'Data pack: {err}')
        pack = None
    games = update._pack_games(pack, season)
    if games:
        return games, f"data pack {(pack.get('generated') or '')[:10]}".strip()
    raise SyncError(SYNC_ERROR)


class CalendarCtl(Part):
    SLICES = {'calendar': 'view', 'calendar_sync': 'sync_view'}
    CALLS = {'calendar_month': 'month_step', 'calendar_day': 'pick_day', 'calendar_today': 'today',
             'calendar_mode': 'set_mode', 'calendar_season': 'season', 'calendar_sync_open': 'sync_open',
             'calendar_sync_retry': 'sync_retry', 'calendar_sync_games': 'sync_games',
             'calendar_sync_close': 'sync_close', 'calendar_sync_apply': 'sync_apply',
             'calendar_team': 'calendar_team'}
    TAB = 'calendar'
    rail_unit = 'games'

    def __init__(self, ctl):
        super().__init__(ctl)
        self.month = None           # (year, month) of the page; None: today's (kept inside the season)
        self.day = None             # the open day (a date)
        self.mode = 'team'          # 'team': the rail's team's games; 'league': every game of its league
        self.sync = {'open': False, 'step': 'ready', 'games': 84, 'error': None}
        self.real = None            # this tab's last check: {season, games, source, rows (targets)}
        self._gathered = None       # the same of the Update's gathered calendar
        self._key, self._tables = None, {}  # (session, edits, last change, season) -> {table: Games}

    # --- the open roster's calendars -----------------------------------------------------------------------------
    def games(self, table):
        """Games of one schedule table of the open roster, read again after any change to it. Call under the lock."""
        c = self.ctl
        s = c.session
        last = s.history[-1] if s.history else None
        key = (s, len(s.history), last, c.upd_season)
        if key != self._key:
            self._key, self._tables = key, {}
        if table not in self._tables:
            try:
                rows = calendar.read(s.db[table]) if table in s.db else []
            except DATA_ERRORS as err:
                c.host.log(f'Calendar: {table} could not be read ({err!r}).')
                rows = []
            self._tables[table] = Games(rows, c.upd_season)
        return self._tables[table]

    def where(self, tid):
        """(table, slot, league) of a rail team: its schedule table, its team there (None: no games) and 'NHL',
        'AHL' or 'Liiga'. Call under the lock."""
        c = self.ctl
        slot = c.rail.map_id('calendar', tid)
        if slot is not None or tid is None:
            return calendar.TABLE32, slot, 'NHL'
        league = c.rail.league_of(c.session, tid)
        if league == AHL:
            org = c.rail.map_id('org', tid)
            org = calendar.EXPANSION if org == SEATTLE else org
            if org is not None and 0 <= org <= calendar.EXPANSION and self.games(AHL_TABLE).counts.get(org):
                return AHL_TABLE, org, 'AHL'
        if league == LIIGA:
            clubs = self.liiga_clubs()
            slot = clubs.index(tid) if tid in clubs else None
            if slot is not None and self.games(LIIGA_TABLE).counts.get(slot):
                return LIIGA_TABLE, slot, 'Liiga'
        return calendar.TABLE32, None, 'NHL'

    def liiga_clubs(self):
        """The Liiga clubs' ids in the Liiga calendar's place order (league 3 by team index, leaguecal._league)."""
        return sorted(r['index'] for r in self.ctl.session.rows[TEAMS] if r['league'] == LIIGA)

    def chip(self, tid):
        """{id, code, name, colours, league} of a rail team, or None."""
        c = self.ctl
        s = c.session
        if s is None or tid is None:
            return None
        t = c.rail.team(s, tid)
        league = 'FA' if tid == FA else L.LEAGUES.get(t['league'], '')
        return {'id': t['id'], 'code': t['code'], 'name': t['name'], 'colours': t['colours'], 'league': league}

    def slot_team(self, slot, league):
        """The chip of a team of a schedule table: the NHL club (31: Seattle), or for the AHL the farm club of that
        organisation (31: Coachella Valley, a custom team the rail does not list), or the Liiga club at that place."""
        s = self.ctl.session
        if league == 'AHL':
            if slot == calendar.EXPANSION:
                return COACHELLA
            tid = self.ctl.rail.farm_of(s, slot)
        elif league == 'Liiga':
            clubs = self.liiga_clubs()
            tid = clubs[slot] if 0 <= slot < len(clubs) else None
        else:
            slot = calendar.PLACE32.get(slot, slot)     # the table's place -> the team index (31: Seattle)
            tid = SEATTLE if slot == calendar.EXPANSION else slot
            tid = tid if tid == SEATTLE or tid in s.team_row else None
        if tid is not None:
            return self.chip(tid)
        code = calendar.CODES.get(slot, str(slot))
        return {'id': None, 'code': code, 'name': code, 'colours': GREY, 'league': league}

    def month_of(self, g):
        """The page's (year, month): the picked one or today's, kept inside the season's first and last month."""
        today = self.ctl.session.today
        ym = self.month or (today.year, today.month)
        lo, hi = (g.first.year, g.first.month), (g.last.year, g.last.month)
        return max(lo, min(hi, ym))

    # --- NHL.com's season against the roster's ---------------------------------------------------------------------
    def real_now(self):
        """{season, games, source, rows} of NHL.com's season for the Update's season: this tab's last check, else the
        Update's calendar step; None: not asked yet. Call under the lock."""
        c = self.ctl
        if self.real is not None and self.real['season'] == c.upd_season:
            return self.real
        g = c.upd_gathered
        if g is None or g.season != c.upd_season or not g.games:
            return None
        if self._gathered is None or self._gathered['games'] is not g.games:
            try:
                rows = targets(g.games)
            except calendar.CalendarError as err:
                c.host.log(f"Calendar: the Update's calendar cannot be compared ({err}).")
                return None
            self._gathered = {'season': g.season, 'games': g.games, 'rows': rows,
                              'source': (g.sources or {}).get('calendar') or 'NHL.com'}
        return self._gathered

    def compare(self):
        """(real, moved, length) of the roster's 32-team calendar against NHL.com's season: length 84 when it holds
        every real game, 82 when it holds the 82-game cut, else None and `moved` the games that differ (against the
        84 or the 82 the roster plays). None when the season was never asked for. Call under the lock."""
        real = self.real_now()
        if real is None:
            return None
        g = self.games(calendar.TABLE32)
        rows = real['rows']
        if g.keys == rows[84]:
            return real, 0, 84
        if rows[82] is not None and g.keys == rows[82]:
            return real, 0, 82
        want = rows[82] if rows[82] is not None and g.uniform() == 82 else rows[84]
        return real, max(len(want - g.keys), len(g.keys - want)), None

    def sync_tag(self):
        cmp = self.compare()
        if cmp is None:
            return {'state': 'unknown', 'text': 'Not compared with NHL.com yet', 'tone': '',
                    'title': 'Sync with NHL.com compares this calendar with the real season.'}
        real, moved, length = cmp
        title = f"Compared with {real['source']}, season {season_label(real['season'])}."
        if moved:
            text = f"{n_games(moved)} {'differs' if moved == 1 else 'differ'} from NHL.com"
            return {'state': 'differs', 'text': text, 'tone': 'caution', 'title': title}
        if length == 82:
            return {'state': 'cut', 'text': 'NHL.com, cut to 82 games', 'tone': 'info', 'title': title}
        return {'state': 'same', 'text': 'Same as NHL.com', 'tone': 'good', 'title': title}

    # --- the rail's followers ------------------------------------------------------------------------------------
    def follow(self, team):
        """The rail's team; the month, the open day and the mode stay."""
        c = self.ctl
        with c.lock:
            c.cal_team = c.rail.map_id('calendar', team)
        c.changed('calendar')

    def hide(self):
        """Leaving the tab closes the sync pop-up (a running check finishes in the status bar)."""
        self.sync['open'] = False
        self.ctl.changed('calendar_sync')

    def roster_changed(self):
        self.day = None
        self._key, self._tables = None, {}
        if self.sync['step'] != 'checking':
            self.sync['open'] = False

    def rail_number(self, team):
        """Each team's games in its calendar ('84'); a dash for a team with no games (not the rail's player count)."""
        c = self.ctl
        tid = team['id'] if isinstance(team, dict) else team
        if c.session is None:
            return None
        table, slot, _league = self.where(tid)
        n = self.games(table).counts.get(slot) if slot is not None else None
        return {'text': str(n), 'tip': 'games'} if n else {'text': '–', 'tip': 'No games in this tab'}

    # --- the slices ----------------------------------------------------------------------------------------------
    def why_text(self, tid):
        c = self.ctl
        if tid is None:
            return 'Pick a team on the left.'
        if tid == FA:
            return 'Free agents play no games. Pick an NHL club to see its games.'
        t = c.rail.team(c.session, tid)
        if t['extra']:
            return f"The {t['name']} play only the All-Star Game, which is not in this calendar. Pick an NHL club."
        return (f"{t['name']} have no games here: this tab shows the NHL, AHL and Liiga calendars. Pick a club of "
                'those leagues, or see all NHL games.')

    def view(self):
        c = self.ctl
        with c.lock:
            s = c.session
            if s is None:
                why = c.busy or 'Pick a roster in Setup first.'
                return {'team': None, 'why': why, 'loading': bool(c.busy), 'can_league': False, 'tip': why_tip(c)}
            table, slot, league = self.where(c.team)
            base = {'team': self.chip(c.team), 'slot': slot, 'league': league, 'league_label': f'All {league} games',
                    'season': dict(SEASON), 'sync': self.sync_tag(), 'busy': bool(c.busy)}
            g = self.games(table)
            if not g.list:
                return dict(base, why=NO_CALENDAR, can_league=False, tip=why_tip(c))
            why = self.why_text(c.team) if slot is None else None
            if why and self.mode != 'league':
                return dict(base, why=why, can_league=c.team is not None, tip=why_tip(c))
            return dict(base, **self.page(g, slot, league), why=None, why_note=why)

    def page(self, g, slot, league):
        """The month page, the open day, the team's games: the rest of the `calendar` slice."""
        today = self.ctl.session.today
        ym = self.month_of(g)
        team_mode = slot is not None and self.mode == 'team'

        def opponent(x):
            return self.slot_team(x[3] if x[2] == slot else x[2], league)['code']
        weeks = []
        for week in WEEKS.monthdatescalendar(*ym):
            row = []
            for d in week:
                day = g.by_date.get(d, ())
                mine = next((x for x in day if slot in (x[2], x[3])), None) if slot is not None else None
                row.append({'date': d.isoformat(), 'n': d.day, 'out': d.month != ym[1], 'today': d == today,
                            'sel': d == self.day, 'count': len(day),
                            'mine': {'vs': opponent(mine), 'home': mine[2] == slot} if mine else None})
            weeks.append(row)
        day = None
        if self.day is not None:
            day = {'date': self.day.isoformat(), 'title': long_day(self.day), 'short': short_day(self.day),
                   'games': [{'key': x[0], 'home': self.slot_team(x[2], league), 'away': self.slot_team(x[3], league),
                              'mine': slot in (x[2], x[3])} for x in g.by_date.get(self.day, ())]}
        summary, months = None, []
        if slot is not None:
            mine = g.by_slot.get(slot, [])
            home = sum(1 for x in mine if x[2] == slot)
            nxt = next((x for x in mine if x[1] >= today), None)
            at = ('vs' if nxt[2] == slot else '@') if nxt else ''
            summary = {'gp': len(mine), 'home': home, 'away': len(mine) - home,
                       'next': f'{short_day(nxt[1])} {at} {opponent(nxt)}' if nxt else None}
            for x in mine:
                key = f'{x[1].year}-{x[1].month:02d}'
                if not months or months[-1]['ym'] != key:
                    months.append({'ym': key, 'label': MONTHS[x[1].month - 1], 'games': []})
                months[-1]['games'].append({'date': x[1].isoformat(), 'label': short_day(x[1]), 'home': x[2] == slot,
                                            'vs': opponent(x), 'sel': x[1] == self.day, 'past': x[1] < today})
        first, last = (g.first.year, g.first.month), (g.last.year, g.last.month)
        return {
            'team_mode': slot is not None, 'mode': 'team' if team_mode else 'league',
            'month': f'{ym[0]}-{ym[1]:02d}', 'title': f'{MONTHS[ym[1] - 1]} {ym[0]}',
            'can_prev': ym > first, 'can_next': ym < last,
            'weekdays': [w[:3] for w in WEEKDAYS], 'weeks': weeks, 'day': day, 'summary': summary, 'months': months,
            'count_note': f'{len(g.list):,} games, {per_text(g.counts)} per team.',
            'tip': None if team_mode else LEAGUE_TIP if slot is not None else 'Click a day for all its games.',
        }

    def sync_view(self):
        c = self.ctl
        with c.lock:
            st = self.sync
            if not st['open'] or c.session is None:
                return {'open': False}
            g = self.games(calendar.TABLE32)
            cmp = self.compare()
            real = cmp[0] if cmp else None
            rows = real['rows'] if real else None
            pick = st['games']
            want = rows.get(pick) if rows else None
            same = want is not None and g.keys == want
            if rows and rows[82] is not None:
                hint = HINT_84 if pick == 84 else HINT_82.format(n=len(rows[84]) - len(rows[82]))
            else:
                hint = HINT_84 if pick == 84 else HINT_82.format(n='Some')
            ready = st['step'] == 'ready' and real is not None
            if not ready:
                note = ''
            elif want is None:
                note = "NHL.com's season cannot be cut to 82 games a team. Pick 84."
            elif same:
                note = 'Nothing to change: this roster already has this calendar.'
            else:
                note = f"Puts {len(want):,} games in this roster's calendar. Save on any team tab (Ctrl+S) keeps them."
            out = {'open': True, 'step': st['step'], 'busy': bool(c.busy), 'season': season_label(c.upd_season),
                   'real': None, 'roster': {'games': len(g.list), 'per_team': per_text(g.counts)},
                   'moved': cmp[1] if cmp else 0, 'same': same, 'games': pick,
                   'options': [{'value': n, 'label': '84 games (real)' if n == 84 else '82 games'} for n in LENGTHS],
                   'hint': hint, 'others': OTHERS, 'error': st['error'] if st['step'] == 'error' else None,
                   'can_apply': ready and want is not None and not same and not c.busy, 'apply_note': note}
            if ready:
                days = sorted({d for d, _h, _a in real['games']})
                counts = calendar.per_team(calendar.slot_games(real['games']))
                out['real'] = {'source': real['source'], 'games': len(real['games']), 'per_team': per_text(counts),
                               'range': f'{short_day(datetime.date.fromisoformat(days[0]))} to '
                                        f'{short_day(datetime.date.fromisoformat(days[-1]))}'}
            return out

    # --- calls: the page -----------------------------------------------------------------------------------------
    def month_step(self, step):
        """The month before (-1) or after (1), kept inside the season."""
        c = self.ctl
        try:
            step = (int(step) > 0) - (int(step) < 0)
        except (TypeError, ValueError):
            return
        with c.lock:
            if c.session is None:
                return
            g = self.games(self.where(c.team)[0])
            if g.list:
                self.month = shift(self.month_of(g), step)
                self.month = self.month_of(g)       # kept inside the season
        c.changed('calendar')

    def pick_day(self, date):
        """Open a day (and turn to its month); the same day again, or null, closes it."""
        c = self.ctl
        try:
            d = datetime.date.fromisoformat(date) if date else None
        except (TypeError, ValueError):
            d = None
        with c.lock:
            if d is None or d == self.day:
                self.day = None
            else:
                self.day = d
                self.month = (d.year, d.month)
                if c.session is not None:
                    g = self.games(self.where(c.team)[0])
                    if g.list:
                        self.month = self.month_of(g)
        c.changed('calendar')

    def today(self):
        """Today's month with today open; before or after the season its first or last month."""
        c = self.ctl
        with c.lock:
            if c.session is None:
                return
            today = c.session.today
            g = self.games(self.where(c.team)[0])
            if g.list and g.first <= today <= g.last:
                self.month, self.day = (today.year, today.month), today
            elif g.list:
                self.month = (g.first.year, g.first.month) if today < g.first else (g.last.year, g.last.month)
        c.changed('calendar')

    def set_mode(self, mode):
        c = self.ctl
        with c.lock:
            self.mode = 'league' if mode == 'league' else 'team'
        c.changed('calendar')

    def season(self, on=False):
        """After beta2: the player's own Franchise or Season results. Today it only says so."""
        if on:
            self.ctl.say(SEASON_LATER, 'info')
        self.ctl.changed('calendar')

    # --- calls: Sync with NHL.com --------------------------------------------------------------------------------
    def sync_open(self):
        c = self.ctl
        with c.lock:
            st = self.sync
            if c.session is None or c.busy or (st['open'] and st['step'] == 'checking'):
                return None
            st['open'] = True
            st['games'] = 82 if self.games(calendar.TABLE32).uniform() == 82 else 84
        c.host.log('Calendar: Sync with NHL.com')
        return self.check()

    def sync_retry(self):
        return self.check()

    def sync_games(self, n):
        c = self.ctl
        with c.lock:
            try:
                self.sync['games'] = 82 if int(n) == 82 else 84
            except (TypeError, ValueError):
                self.sync['games'] = 84
        c.changed('calendar_sync')

    def sync_close(self):
        c = self.ctl
        with c.lock:
            self.sync['open'] = False
        c.changed('calendar_sync')

    def check(self):
        """The job "Checking the calendar": NHL.com's season (else the data pack's), compared with this roster's."""
        c = self.ctl
        st = self.sync
        with c.lock:
            if c.session is None or c.busy:
                return None
            season, offline = c.upd_season, c.upd_offline
            c.busy = f'Asking NHL.com for the {season_label(season)} season...'
            st['step'], st['error'] = 'checking', None
        c.say(c.busy, 'info', -1)
        c.changed('calendar', 'calendar_sync')

        def work():
            games, source = real_season(season, offline, log=c.host.log)
            c.say('Comparing it with this roster...', 'info', -1)
            return {'season': season, 'games': games, 'source': source, 'rows': targets(games)}

        def done(real):
            with c.lock:
                c.busy = None
                self.real = real
                st['step'] = 'ready'
                cmp = self.compare()
            moved = cmp[1] if cmp else 0
            c.host.log(f"Calendar: {real['source']} {season_label(season)}, {len(real['games'])} games; "
                       f'{moved} differ from this roster')
            c.say(DIFFERS.format(n=n_games(moved)) if moved else SAME, 'good')
            c.changed('calendar', 'calendar_sync')

        def failed(message):
            with c.lock:
                c.busy = None
                st['step'] = 'error'
                st['error'] = message if message == SYNC_ERROR else f"NHL.com's calendar cannot be used: {message}."
            c.host.log(f'Calendar: {message}')
            c.say(st['error'], 'bad')
            c.changed('calendar', 'calendar_sync')
        jobs.run(work, done, failed, expected=(SyncError, calendar.CalendarError, nhlcom.NhlComError, OSError,
                                               ValueError))
        return None

    def sync_apply(self):
        """The job "Writing the calendar": NHL.com's season into the four NHL schedule tables (calendar.apply, then
        calendar.check), one edit in My edits (no one team); the Save bar of another tab saves it."""
        c = self.ctl
        st = self.sync
        with c.lock:
            s, n = c.session, st['games']
            real = self.real_now()
            if s is None or c.busy or not st['open'] or st['step'] != 'ready' or real is None:
                return None
            want = real['rows'].get(n)
            if want is None or self.games(calendar.TABLE32).keys == want:
                return None
            season = real['season']
            c.busy = f'Writing {len(want):,} games into the 32-team calendar...'
        c.say(c.busy, 'info', -1)
        c.changed('calendar', 'calendar_sync')
        label = f'Calendar: NHL.com {season_label(season)}, {n} games a team'

        def write(db):
            schema = c.game.schema()
            out = calendar.apply(db, schema, real['games'], per32=82 if n == 82 else None)
            c.say('Checking every team plays the same number...', 'info', -1)
            problems = calendar.check(db, schema, out, season)
            if problems:
                raise calendar.CalendarError(f'{len(problems)} problem(s), first: {problems[0]}')
            return [(f'Calendar {t}', '-', f"{e['games']} games, {e['first']} to {e['last']}")
                    for t, e in out.items()], out

        def work():
            with c.lock:
                ch, out = s.bulk(label, write)
                ch.tab, ch.team = TAB_LABELS['calendar'], None     # My edits: Calendar, no one team
                return out

        def done(out):
            with c.lock:
                c.busy = None
                st['open'] = False
            for t, e in out.items():
                c.host.log(f"Calendar: {t} {e['games']} games, {e['first']} to {e['last']}")
            c.say(WRITTEN.format(n=n), 'good')
            c.changed('calendar', 'calendar_sync', 'editor', 'save')

        def failed(message):
            with c.lock:
                c.busy = None
            c.host.log(f'Calendar: not written ({message})')
            c.say(f'The calendar was not written: {message}', 'bad')
            c.changed('calendar', 'calendar_sync')
        jobs.run(work, done, failed, expected=(calendar.CalendarError, ValueError, KeyError))
        return None

    # --- beta1's calendar --------------------------------------------------------------------------------------------
    def calendar_team(self, team):
        c = self.ctl
        with c.lock:
            c.cal_team = None if team in (None, '') else int(team)
        c.changed('calendar')

    def snap_calendar(self):
        c = self.ctl
        with c.lock:
            s = c.session
            if s is None:
                return {'ready': False}
            g = c.upd_gathered
            view = update.calendar_view(s.db, c.game.schema(), team=c.cal_team,
                                        real=g.games if g else None, start_year=c.upd_season)
            view['season_label'] = f'{c.upd_season}-{(c.upd_season + 1) % 100:02d}'
            view['checked'] = g is not None
            view['selected'] = c.cal_team
            return view
