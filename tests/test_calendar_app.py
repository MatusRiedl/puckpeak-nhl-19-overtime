"""The Calendar tab (app/calendar_ctl.py). On a small made-up roster: the month page from Monday to Sunday, a team's
games (home "vs", away "@"), Seattle as slot 31, an AHL club's games from the AHL calendar, the "why" cards and all
games, days, months and Today, the rail numbers, and "Sync with NHL.com" (compare, errors, write) with NHL.com
replaced. Through the Controller on the game's default roster: beta1's slice follows the update, and the sync writes
the recorded 2026-27 season (84 or 82 games a team) in one edit (jobs run inline; no network)."""
import datetime
import json
import os
import threading
from calendar import Calendar

import pytest

from overtime_core import calendar as core
from overtime_core import teams as T
from overtime_roster.app import calendar_ctl as CC
from overtime_roster.app import controller as C, jobs, sources, update
from overtime_roster.app import rail as R
from overtime_roster.app.session import Change

DATA = os.path.join(os.path.dirname(__file__), 'data')


class Host:
    def __init__(self):
        self.snaps, self.lines = {}, []

    def register(self, name, fn):
        self.snaps[name] = fn

    def changed(self, *names):
        pass

    def log(self, msg):
        self.lines.append(msg)

    def send(self, *a):
        pass

    def open_path(self, path):
        pass

    def snap(self, name):
        return self.snaps[name]()


def fixtures():
    with open(os.path.join(DATA, 'nhl_rosters_20262027.json'), encoding='utf-8') as f:
        real = json.load(f)
    with open(os.path.join(DATA, 'nhl_schedule_20262027.json'), encoding='utf-8') as f:
        games = [tuple(g) for g in json.load(f)]
    return real, games


def inline(work, done=None, failed=None, expected=()):
    try:
        out = work()
    except expected as err:
        return failed and failed(str(err))
    return done and done(out)


@pytest.fixture
def app(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(jobs, 'run', inline)
    real, games = fixtures()
    rating = [{'name': 'Leo Carlsson', 'position': 'C', 'birth': [2004, 12, 26], 'attrs': {'Passing': 90}}]

    def gather(client, season, pack_dir, fetch=None, offline=False, step=None, log=None):
        for k in update.GATHER_STEPS:
            step(k, 'ok', 'fixture')
        return update.Gathered(season, real, games, rating, [], {'rosters': 'fixture', 'calendar': 'fixture'})
    monkeypatch.setattr(update, 'gather', gather)
    monkeypatch.setattr(CC, 'real_season', lambda season, offline=False, log=None: (games, 'NHL.com'))
    host = Host()
    c = C.Controller(host, game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    assert c.session is not None
    return c, host


@pytest.mark.game
def test_calendar_follows_the_update(app):
    c, host = app
    assert c.update_check() is None
    cal = c.snap_calendar()
    assert cal['ready'] and cal['sync']['same'] is False  # the default roster has the 2018-19 calendar
    c.update_apply()
    cal = c.snap_calendar()
    assert cal['games'] == 1344 and cal['sync']['same'] and len(cal['teams']) == 32
    c.calendar_team(T.UTAH_SLOT)
    sched = c.snap_calendar()['schedule']
    assert len(sched) == 84 and sum(g['home'] for g in sched) == 42
    json.dumps(host.snap('calendar'))


@pytest.mark.game
def test_sync_writes_the_season_in_one_edit(app):
    c, host = app
    cal = c.parts['calendar']
    c.shell.tab('calendar')
    c.parts['rail'].pick_team(11)
    v = cal.view()
    assert v['count_note'] == '1,312 games, 82 per team.' and v['sync']['state'] == 'unknown'
    assert v['summary']['gp'] == 82 and cal.rail_number({'id': 11}) == {'text': '82', 'tip': 'games'}

    cal.sync_open()
    s = cal.sync_view()
    assert s['step'] == 'ready' and s['real']['games'] == 1344 and s['real']['per_team'] == '84'
    assert s['games'] == 82 and s['moved'] > 1000 and s['can_apply']       # the 2018-19 calendar
    assert cal.view()['sync']['state'] == 'differs'
    cal.sync_games(84)
    assert cal.sync_view()['apply_note'].startswith("Puts 1,344 games in this roster's calendar.")
    cal.sync_apply()
    ch = c.session.history[-1]
    assert (ch.label, ch.tab, ch.team) == ('Calendar: NHL.com 2026-27, 84 games a team', 'Calendar', None)
    assert [d[0] for d in ch.details] == [f'Calendar {t}' for t in (core.TABLE32, *core.TABLES31)]
    assert c.status['text'].startswith('Calendar ready: 84 games a team.')
    v = cal.view()
    assert v['count_note'] == '1,344 games, 84 per team.' and v['sync']['state'] == 'same'
    assert cal.sync_view() == {'open': False}
    assert cal.rail_number({'id': 11})['text'] == '84' and cal.rail_number({'id': R.SEATTLE})['text'] == '84'

    cal.sync_open()
    assert cal.sync_view()['same'] and not cal.sync_view()['can_apply']
    cal.sync_games(82)
    cal.sync_apply()
    assert c.session.history[-1].label == 'Calendar: NHL.com 2026-27, 82 games a team'
    assert cal.view()['sync']['state'] == 'cut' and cal.rail_number({'id': 11})['text'] == '82'
    c.session.undo()
    assert cal.view()['sync']['state'] == 'same'

    c.parts['rail'].pick_team(35)                       # EDM's farm club: the AHL calendar
    v = cal.view()
    assert v['league'] == 'AHL' and v['slot'] == 11 and v['summary']['gp'] == 82
    json.dumps(host.snap('calendar'))
    json.dumps(host.snap('calendar_sync'))


# --- a small made-up roster ------------------------------------------------------------------------------------------
NHL, AHL, FA = T.NHL_LEAGUE, R.AHL, R.FA
# index, league, abbr, nickname, ahlaffiliate
CLUBS = [(0, NHL, 'ANA', 'Ducks', 40), (11, NHL, 'EDM', 'Oilers', 35), (22, NHL, 'UTA', 'Mammoth', None),
         (90, NHL, 'ATL', 'All-Stars Atlantic', None),
         (35, AHL, 'BAK', 'Condors', None), (40, AHL, 'SD', 'Gulls', None), (45, AHL, 'HER', 'Bears', None),
         (66, 2, 'BIF', 'Brynas', None), (80, 3, 'ASS', 'Assat', None), (81, 3, 'HPK', 'HPK', None)]
SEA, UTA = core.SLOTS32['SEA'], core.SLOTS32['UTA']     # nhl32schedule's places: 22 and 31
# (date, home place, away place): everyone plays 4, 2 at home
SEASON = [('2026-10-06', 11, 0), ('2026-10-06', UTA, SEA), ('2026-10-14', 0, 11), ('2026-10-14', SEA, UTA),
          ('2026-11-03', 11, SEA), ('2026-11-03', 0, UTA), ('2027-04-10', SEA, 11), ('2027-04-10', UTA, 0)]
FARM = [('2026-10-09', 11, 0), ('2026-10-10', core.EXPANSION, 11)]     # AHL places: 31 = Seattle's farm club
LIIGA = [('2026-09-11', 1, 0), ('2026-09-12', 0, 1), ('2026-09-19', 0, 1)]  # Liiga places: 0 = Assat (80), 1 = HPK (81)
REAL = [(d, core.CODES32[h], core.CODES32[a]) for d, h, a in SEASON]


def rows(games):
    out = []
    for d, h, a in games:
        d = datetime.date.fromisoformat(d)
        out.append({'month': d.month - 1, 'day': d.day - 1, 'home': h, 'away': a})
    return out


class Table:
    def __init__(self, records):
        self.records = records

    @property
    def count(self):
        return len(self.records)

    def get(self, i, field):
        return self.records[i][field]


class Session:
    """What the calendar and the rail read of a RosterSession."""

    def __init__(self, nhl=SEASON, farm=FARM, today=datetime.date(2026, 10, 14)):
        self.rows = {R.TEAMS: [{'index': i, 'league': lg, 'abbrname': ab, 'nickname': nick, 'cityname': '',
                                'ahlaffiliate': aff, 'feprimarycolor': 0x112233} for i, lg, ab, nick, aff in CLUBS]}
        self.team_row = {i: k for k, (i, *_rest) in enumerate(CLUBS)}
        self.free_agents = [1, 2]
        self.history = []
        self.today = today
        # Feb 29 has no day in 2027: the row is left out
        self.db = {core.TABLE32: Table(rows(nhl) + [{'month': 1, 'day': 28, 'home': 0, 'away': 11}]),
                   CC.AHL_TABLE: Table(rows(farm)), CC.LIIGA_TABLE: Table(rows(LIIGA))}

    def team_name(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['nickname'] if team in self.team_row else f'Team {team}'

    def team_abbr(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['abbrname'] if team in self.team_row else ''

    def teams(self, league):
        return [{'id': i, 'name': nick, 'abbr': ab, 'count': 20} for i, lg, ab, nick, _aff in CLUBS if lg == league]

    def bulk(self, label, work):
        details, out = work(self.db)
        ch = Change(label, details=list(details))
        self.history.append(ch)
        return ch, out


class Ctl:
    """The Controller's shared state as the calendar uses it."""

    def __init__(self, session):
        self.lock = threading.RLock()
        self.session = session
        self.busy = None
        self.team = 11
        self.cal_team = None
        self.upd_season, self.upd_offline, self.upd_gathered = 2026, False, None
        self.status = {}
        self.pushed = []
        self.host = Host()
        self.rail = R.Rail(self)
        self.game = type('Game', (), {'schema': staticmethod(lambda: None)})()

    def say(self, text, tone='info', progress=None):
        self.status = {'text': text, 'tone': tone, 'progress': progress}

    def changed(self, *names):
        self.pushed += names


@pytest.fixture
def ctl(monkeypatch):
    monkeypatch.setattr(jobs, 'run', inline)
    c = Ctl(Session())
    return c, CC.CalendarCtl(c)


NO_GAMES = {'text': '–', 'tip': 'No games in this tab'}


def day(v, date):
    return next(d for w in v['weeks'] for d in w if d['date'] == date)


def test_the_month_page_runs_monday_to_sunday(ctl):
    c, cal = ctl
    v = cal.view()
    assert v['weekdays'] == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    assert (v['month'], v['title'], v['can_prev'], v['can_next']) == ('2026-10', 'October 2026', False, True)
    want = Calendar(0).monthdatescalendar(2026, 10)
    assert [[d['date'] for d in w] for w in v['weeks']] == [[d.isoformat() for d in w] for w in want]
    assert all(datetime.date.fromisoformat(w[0]['date']).weekday() == 0 for w in v['weeks'])
    first = v['weeks'][0][0]
    assert (first['date'], first['n'], first['out']) == ('2026-09-28', 28, True)
    assert day(v, '2026-10-06')['mine'] == {'vs': 'ANA', 'home': True} and day(v, '2026-10-06')['count'] == 2
    assert day(v, '2026-10-14')['mine'] == {'vs': 'ANA', 'home': False} and day(v, '2026-10-14')['today']
    assert day(v, '2026-10-07')['count'] == 0 and day(v, '2026-10-07')['mine'] is None


def test_the_team_card_and_its_games(ctl):
    c, cal = ctl
    v = cal.view()
    assert (v['team']['code'], v['slot'], v['league'], v['mode'], v['team_mode']) == ('EDM', 11, 'NHL', 'team', True)
    assert v['summary'] == {'gp': 4, 'home': 2, 'away': 2, 'next': 'Wed 14 Oct @ ANA'}
    assert [(m['label'], len(m['games'])) for m in v['months']] == [('October', 2), ('November', 1), ('April', 1)]
    assert v['months'][0]['games'][0] == {'date': '2026-10-06', 'label': 'Tue 6 Oct', 'home': True, 'vs': 'ANA',
                                          'sel': False, 'past': True}
    assert v['count_note'] == '8 games, 4 per team.' and v['tip'] is None and v['why'] is None
    assert v['season'] == {'on': False, 'available': False, 'label': 'My season', 'note': CC.SEASON['note']}
    assert cal.rail_number({'id': 11}) == {'text': '4', 'tip': 'games'}
    cal.follow(11)
    assert c.cal_team == 11 and 'calendar' in c.pushed


def test_seattle_is_place_22(ctl):
    c, cal = ctl
    c.team = R.SEATTLE
    v = cal.view()
    assert v['slot'] == SEA and v['team']['name'] == 'Seattle Kraken' and v['summary']['gp'] == 4
    assert day(v, '2026-10-06')['mine'] == {'vs': 'UTA', 'home': False}
    cal.pick_day('2026-11-03')
    games = cal.view()['day']['games']
    assert [(g['away']['code'], g['home']['code'], g['mine']) for g in games] == [('SEA', 'EDM', True),
                                                                                  ('UTA', 'ANA', False)]
    assert cal.rail_number({'id': R.SEATTLE}) == {'text': '4', 'tip': 'games'}
    cal.follow(R.SEATTLE)
    assert c.cal_team == SEA


def test_a_farm_club_plays_the_ahl_calendar(ctl):
    c, cal = ctl
    c.team = 35                                         # EDM's farm club
    v = cal.view()
    assert (v['league'], v['league_label'], v['slot'], v['why']) == ('AHL', 'All AHL games', 11, None)
    assert v['summary'] == {'gp': 2, 'home': 1, 'away': 1, 'next': None}
    assert v['count_note'] == '2 games, 1 to 2 per team.'
    assert day(v, '2026-10-09')['mine'] == {'vs': 'SD', 'home': True}
    cal.pick_day('2026-10-10')
    g = cal.view()['day']['games'][0]
    assert (g['home']['code'], g['home']['name'], g['home']['id'], g['away']['code']) == (
        'CV', 'Coachella Valley Firebirds', None, 'BAK')
    assert cal.rail_number({'id': 35}) == {'text': '2', 'tip': 'games'}
    c.team = 45                                         # the farm club of no organisation
    v = cal.view()
    assert v['why'].startswith('Bears have no games here') and v['can_league'] and v['league'] == 'NHL'
    assert cal.rail_number({'id': 45}) == NO_GAMES


def test_a_liiga_club_plays_the_liiga_calendar(ctl):
    c, cal = ctl
    c.team = 81                                         # HPK: the Liiga's second club, place 1
    v = cal.view()
    assert (v['league'], v['league_label'], v['slot'], v['why']) == ('Liiga', 'All Liiga games', 1, None)
    assert v['summary']['gp'] == 3 and (v['summary']['home'], v['summary']['away']) == (1, 2)
    assert day(v, '2026-09-11')['mine'] == {'vs': 'ASS', 'home': True}
    assert cal.rail_number({'id': 80}) == {'text': '3', 'tip': 'games'}


def test_teams_without_games_get_a_card_and_all_games(ctl):
    c, cal = ctl
    c.team = FA
    v = cal.view()
    assert v['why'] == 'Free agents play no games. Pick an NHL club to see its games.' and v['can_league']
    assert v['tip'].startswith('Pick a team in the list.') and 'weeks' not in v
    assert cal.rail_number({'id': FA}) == NO_GAMES
    c.team = 90
    assert cal.view()['why'] == ('The All-Stars Atlantic play only the All-Star Game, which is not in this calendar. '
                                 'Pick an NHL club.')
    c.team = 66
    assert cal.view()['why'] == ('Brynas have no games here: this tab shows the NHL, AHL and Liiga calendars. Pick a '
                                 'club of those leagues, or see all NHL games.')
    c.team = None
    v = cal.view()
    assert v['why'] == 'Pick a team on the left.' and not v['can_league']

    c.team = FA
    cal.set_mode('league')
    v = cal.view()
    assert v['why'] is None and v['why_note'].startswith('Free agents play no games')
    assert (v['mode'], v['team_mode'], v['summary'], v['months']) == ('league', False, None, [])
    assert v['tip'] == 'Click a day for all its games.' and day(v, '2026-10-06')['mine'] is None
    c.team = 11
    v = cal.view()
    assert (v['mode'], v['team_mode'], v['why_note'], v['tip']) == ('league', True, None, CC.LEAGUE_TIP)
    cal.set_mode('team')
    assert cal.view()['mode'] == 'team'


def test_days_months_and_today(ctl):
    c, cal = ctl
    cal.pick_day('2026-11-03')
    v = cal.view()
    assert v['month'] == '2026-11' and day(v, '2026-11-03')['sel']
    assert {k: v['day'][k] for k in ('date', 'title', 'short')} == {'date': '2026-11-03',
                                                                    'title': 'Tuesday 3 November', 'short': 'Tue 3 Nov'}
    assert [g['mine'] for g in v['day']['games']] == [True, False]
    assert v['months'][1]['games'][0]['sel']
    cal.pick_day('2026-11-03')                          # the same day again closes it
    assert cal.view()['day'] is None
    cal.pick_day('2026-11-04')
    assert cal.view()['day']['games'] == []
    cal.pick_day('not a day')
    assert cal.view()['day'] is None
    for _k in range(5):
        cal.month_step(-1)
    v = cal.view()
    assert v['month'] == '2026-10' and not v['can_prev']
    for _k in range(9):
        cal.month_step(1)
    v = cal.view()
    assert (v['month'], v['title'], v['can_next']) == ('2027-04', 'April 2027', False)
    cal.month_step('x')
    assert cal.view()['month'] == '2027-04'
    cal.today()
    v = cal.view()
    assert v['month'] == '2026-10' and v['day']['date'] == '2026-10-14'
    c.session.today = datetime.date(2026, 8, 1)         # before the season: its first month
    cal.month = None
    assert cal.view()['month'] == '2026-10'
    c.session.today = datetime.date(2027, 6, 30)        # after: its last
    cal.today()
    assert cal.view()['month'] == '2027-04'
    cal.season(True)
    assert c.status['text'] == CC.SEASON_LATER


def test_no_roster_and_no_calendar(monkeypatch):
    c = Ctl(None)
    cal = CC.CalendarCtl(c)
    v = cal.view()
    assert v['why'] == v['tip'] == 'Pick a roster in Setup first.' and v['team'] is None
    assert cal.sync_view() == {'open': False} and cal.rail_number({'id': 11}) is None
    cal.sync_open()
    assert cal.sync_view() == {'open': False}
    c = Ctl(Session(nhl=[], farm=[]))
    v = CC.CalendarCtl(c).view()
    assert v['why'] == CC.NO_CALENDAR and not v['can_league']


def test_sync_compares_with_nhl_com(ctl, monkeypatch):
    c, cal = ctl
    asked = []

    def real_season(season, offline=False, log=None):
        asked.append((season, offline))
        return REAL, 'NHL.com'
    monkeypatch.setattr(CC, 'real_season', real_season)
    assert cal.view()['sync'] == {'state': 'unknown', 'text': 'Not compared with NHL.com yet', 'tone': '',
                                  'title': 'Sync with NHL.com compares this calendar with the real season.'}
    cal.sync_open()
    assert asked == [(2026, False)] and c.busy is None
    s = cal.sync_view()
    assert (s['open'], s['step'], s['season'], s['games'], s['moved'], s['same']) == (True, 'ready', '2026-27', 84,
                                                                                      0, True)
    assert s['real'] == {'source': 'NHL.com', 'games': 8, 'per_team': '4', 'range': 'Tue 6 Oct to Sat 10 Apr'}
    assert s['roster'] == {'games': 8, 'per_team': '4'}
    assert not s['can_apply'] and s['apply_note'] == 'Nothing to change: this roster already has this calendar.'
    assert s['hint'] == CC.HINT_84 and s['others'] == CC.OTHERS
    assert [o['value'] for o in s['options']] == [84, 82]
    assert c.status['text'] == CC.SAME and cal.view()['sync']['state'] == 'same'
    cal.sync_games(82)                                  # 4 games a team cannot be cut to 82
    s = cal.sync_view()
    assert not s['can_apply'] and 'cannot be cut' in s['apply_note']

    moved = [('2026-11-04', h, a) if d == '2026-11-03' and h == 'EDM' else (d, h, a) for d, h, a in REAL]
    monkeypatch.setattr(CC, 'real_season', lambda season, offline=False, log=None: (moved, 'data pack 2026-10-02'))
    cal.sync_games(84)
    cal.sync_retry()
    s = cal.sync_view()
    assert s['moved'] == 1 and not s['same'] and s['can_apply'] and s['real']['source'] == 'data pack 2026-10-02'
    assert s['apply_note'] == "Puts 8 games in this roster's calendar. Save on any team tab (Ctrl+S) keeps them."
    assert cal.view()['sync']['text'] == '1 game differs from NHL.com'
    assert c.status['text'] == "NHL.com's calendar differs in 1 game. Use it to bring this roster up to date."

    def offline(season, offline=False, log=None):
        raise CC.SyncError(CC.SYNC_ERROR)
    monkeypatch.setattr(CC, 'real_season', offline)
    cal.sync_retry()
    s = cal.sync_view()
    assert (s['step'], s['error'], s['real'], s['can_apply']) == ('error', CC.SYNC_ERROR, None, False)
    assert c.status == {'text': CC.SYNC_ERROR, 'tone': 'bad', 'progress': None} and c.busy is None

    def unknown_team(season, offline=False, log=None):
        return core.season_games(type('Client', (), {'club_schedule': lambda self, code, s: {'games': [
            {'id': 1, 'gameType': 2, 'gameDate': '2026-10-01', 'homeTeam': {'abbrev': 'ARI'},
             'awayTeam': {'abbrev': 'SEA'}}]}})(), season, codes=['SEA']), 'NHL.com'
    monkeypatch.setattr(CC, 'real_season', unknown_team)
    cal.sync_retry()
    assert cal.sync_view()['error'] == "NHL.com's calendar cannot be used: no NHL 19 team for ARI."
    cal.sync_close()
    assert cal.sync_view() == {'open': False}


def test_sync_writes_one_edit(ctl, monkeypatch):
    c, cal = ctl
    moved = [('2026-11-04', h, a) if d == '2026-11-03' and h == 'EDM' else (d, h, a) for d, h, a in REAL]
    monkeypatch.setattr(CC, 'real_season', lambda season, offline=False, log=None: (moved, 'NHL.com'))
    wrote = []

    def apply(db, schema, games, per32=None, per31=None):
        wrote.append(per32)
        db[core.TABLE32] = Table(rows(core.rows_for(games, 32)))
        return {core.TABLE32: {'games': 8, 'per_team': (4, 4), 'first': '2026-10-06', 'last': '2027-04-10'}}
    monkeypatch.setattr(core, 'apply', apply)
    monkeypatch.setattr(core, 'check', lambda db, schema, expected, start_year=None: [])
    cal.sync_apply()                                    # nothing checked yet: nothing to write
    assert c.session.history == []
    cal.sync_open()
    c.team = 35                                         # the rail's team plays no part in the edit
    cal.sync_apply()
    ch = c.session.history[-1]
    assert (ch.label, ch.tab, ch.team, wrote) == ('Calendar: NHL.com 2026-27, 84 games a team', 'Calendar', None,
                                                  [None])
    assert ch.details == [('Calendar nhl32schedule', '-', '8 games, 2026-10-06 to 2027-04-10')]
    assert c.status['text'] == ('Calendar ready: 84 games a team. It is in My edits: save it with the Save bar on '
                                'any other team tab.')
    assert cal.sync_view() == {'open': False} and c.busy is None
    c.team = 11
    cal.pick_day('2026-11-04')
    v = cal.view()
    assert v['sync']['state'] == 'same' and day(v, '2026-11-04')['mine'] == {'vs': 'SEA', 'home': True}
    assert {'calendar', 'calendar_sync', 'save'} <= set(c.pushed)

    monkeypatch.setattr(core, 'check', lambda db, schema, expected, start_year=None: ['nhl32schedule: 7 games'])
    monkeypatch.setattr(CC, 'real_season', lambda season, offline=False, log=None: (REAL, 'NHL.com'))
    cal.sync_open()
    cal.sync_apply()
    assert len(c.session.history) == 1 and c.status['tone'] == 'bad'
    assert c.status['text'].startswith('The calendar was not written: 1 problem(s)')


def test_the_update_s_calendar_counts_as_compared(ctl):
    c, cal = ctl
    c.upd_gathered = update.Gathered(2026, [], REAL, sources={'calendar': 'NHL.com'})
    assert cal.view()['sync']['state'] == 'same'
    c.upd_season = 2027                                 # another season: not compared yet
    assert cal.view()['sync']['state'] == 'unknown'


def test_leaving_the_tab_closes_the_pop_up(ctl, monkeypatch):
    c, cal = ctl
    monkeypatch.setattr(CC, 'real_season', lambda season, offline=False, log=None: (REAL, 'NHL.com'))
    cal.sync_open()
    assert cal.sync_view()['open']
    cal.hide()
    assert cal.sync_view() == {'open': False}
    cal.pick_day('2026-10-06')
    cal.roster_changed()
    assert cal.view()['day'] is None
