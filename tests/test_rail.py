"""The rail leader (app/rail.py) on a small made-up roster: the league's clubs by name, Seattle when the roster has it
only as the custom team, free agents, the AHL with its NHL clubs, the ends of the list, the id maps, beta1's pickers,
and the followers (only the tab in view follows; every team tab hears of another roster)."""
import threading

import pytest

from overtime_core import rosterupdate, teams as T
from overtime_roster.app import controller as C, rail as R
from overtime_roster.app.save_ctl import SaveCtl
from overtime_roster.app.session import Change
from overtime_roster.app.shell import TEAM_TABS, Shell

NHL, AHL, FA = T.NHL_LEAGUE, R.AHL, R.FA
# index, league, abbr, nickname, ahlaffiliate, players
CLUBS = [(0, NHL, 'ANA', 'Ducks', 40, 23), (1, NHL, 'BOS', 'Bruins', 41, 23), (2, NHL, 'CHI', 'Blackhawks', 255, 22),
         (90, NHL, 'ATL', 'All-Stars Atlantic', None, 11),
         (40, AHL, 'SD', 'Gulls', 40, 25), (41, AHL, 'PRO', 'Bruins', 41, 24), (42, AHL, 'ROC', 'Americans', 42, 26)]


class Table:
    def __init__(self, teams):
        self.teams = teams
        self.count = len(teams)

    def get(self, i, field):
        return self.teams[i]


class Db:
    def __init__(self, seattle):
        self.ready = bool(seattle)
        self.tables = {rosterupdate.CUSTOM_ROSTER: Table([T.SEATTLE] * seattle + [T.SEATTLE + 1] * 2)}

    def __getitem__(self, name):
        return self.tables[name]


class Session:
    """What the rail reads of a RosterSession."""

    def __init__(self, seattle=0, free_agents=5):
        self.rows = {R.TEAMS: [{'index': i, 'league': lg, 'abbrname': ab, 'nickname': nick, 'cityname': '',
                                'ahlaffiliate': aff, 'feprimarycolor': 0x112233} for i, lg, ab, nick, aff, _n in CLUBS]}
        self.team_row = {i: k for k, (i, *_rest) in enumerate(CLUBS)}
        self.counts = {i: n for i, *_rest, n in CLUBS}
        self.free_agents = list(range(free_agents))
        self.history = []
        self.db = Db(seattle)

    def team_name(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['nickname'] if team in self.team_row else f'Team {team}'

    def team_abbr(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['abbrname'] if team in self.team_row else ''

    def leagues(self):
        return [(NHL, 'NHL', 4), (AHL, 'AHL', 3)] + ([(FA, 'Free agents', 1)] if self.free_agents else [])

    def teams(self, league):
        if league == FA:
            return [{'id': FA, 'name': 'Free agents', 'abbr': 'FA', 'count': len(self.free_agents)}]
        return [{'id': i, 'name': nick, 'abbr': ab, 'count': self.counts[i]}
                for i, lg, ab, nick, _aff, _n in CLUBS if lg == league]


class Follower:
    """A team tab's part as the rail sees it."""
    rail_unit = 'players'

    def __init__(self, tab):
        self.TAB = tab
        self.followed, self.hidden, self.rosters = [], 0, 0
        self.holding = set()    # teams with changes this tab holds, not applied yet

    def dirty(self, team):
        return team in self.holding

    def follow(self, team):
        self.followed.append(team)

    def hide(self):
        self.hidden += 1

    def roster_changed(self):
        self.rosters += 1

    def rail_number(self, team):
        return None


class FakeCtl:
    def __init__(self, session, tab='roster'):
        self.lock = threading.RLock()
        self.session, self.busy = session, None
        self.league, self.team, self.query = NHL, None, ''
        self.tab_name = tab
        self.seen = []
        self.tab_parts = {t: Follower(t) for t in TEAM_TABS}
        self.parts = dict(self.tab_parts)
        self.rail = self.parts['rail'] = R.Rail(self)
        self.shell = self.parts['shell'] = Shell(self)
        self.parts['save'] = SaveCtl(self)

    def changed(self, *names):
        self.seen.append(names)


@pytest.fixture(autouse=True)
def seattle_ready(monkeypatch):
    monkeypatch.setattr(R.rosterupdate, 'seattle_ready', lambda db: db.ready)


def opened(seattle=0, tab='roster'):
    c = FakeCtl(Session(seattle), tab)
    c.rail.roster_changed()
    return c


def ids(c):
    return [r['id'] for r in c.rail.view()['rows']]


def test_another_roster_starts_on_the_first_club_by_name():
    c = opened()
    assert (c.league, c.team) == (NHL, 2)                   # Blackhawks, Bruins, Ducks; the All-Stars last
    assert ids(c) == [2, 1, 0, 90]
    assert all(p.rosters == 1 for p in c.tab_parts.values())     # every team tab hears of it
    assert c.tab_parts['roster'].followed == [2]                  # only the tab in view follows
    assert all(not p.followed for t, p in c.tab_parts.items() if t != 'roster')
    v = c.rail.view()
    assert v['loaded'] and v['leagues'][0] == {'value': NHL, 'label': 'NHL'}
    assert [r['sel'] for r in v['rows']] == [True, False, False, False]
    assert v['rows'][3]['extra'] and v['rows'][0]['number'] == {'text': '22', 'tip': 'players'}


def test_no_roster_says_what_to_do():
    c = FakeCtl(None)
    v = c.rail.view()
    assert not v['loaded'] and v['rows'] == [] and v['status'] == 'Pick a roster in Setup first.'
    c.busy = 'Opening the roster...'
    assert c.rail.view()['status'] == 'Opening the roster...'
    assert c.rail.step(1) is None and c.rail.pick_league(AHL) is None and c.team is None


def test_seattle_only_as_the_custom_team_is_on_the_rail():
    c = opened(seattle=0)
    assert R.SEATTLE not in ids(c)                          # not ready: not listed
    c = opened(seattle=3)
    assert R.SEATTLE in ids(c)
    sea = next(r for r in c.rail.view()['rows'] if r['id'] == R.SEATTLE)
    assert (sea['code'], sea['name'], sea['number']['text']) == ('SEA', 'Seattle Kraken', '3')
    c.rail.pick_league(AHL)
    c.rail.pick_team(R.SEATTLE)                              # another league's team: the rail turns to the NHL
    assert (c.league, c.team) == (NHL, R.SEATTLE)
    assert c.tab_parts['roster'].followed[-1] == R.SEATTLE
    assert c.rail.map_id('strategy', R.SEATTLE) == T.SEATTLE == c.rail.map_id('jerseys', R.SEATTLE) == 499
    assert c.rail.map_id('calendar', R.SEATTLE) == 22     # nhl32schedule's place (calendar.SLOTS32)


def test_id_maps():
    c = opened()
    assert c.rail.map_id('strategy', 1) == 1 and c.rail.map_id('jerseys', FA) == FA
    assert [c.rail.map_id('calendar', t) for t in (0, 2, 90, 40, FA)] == [0, 2, None, None, None]
    assert c.rail.map_id('farm', 0) == 40 and c.rail.map_id('farm', 2) is None   # 255: no such AHL club
    assert c.rail.map_id('org', 41) == 1 and c.rail.map_id('org', 42) is None
    assert c.rail.map_id('calendar', None) is None
    with pytest.raises(ValueError):
        c.rail.map_id('nothing', 0)


def test_free_agents():
    c = opened()
    c.rail.pick_league(FA)
    assert (c.league, c.team) == (FA, FA) and ids(c) == [FA]
    row = c.rail.view()['rows'][0]
    assert (row['code'], row['name'], row['number']['text']) == ('FA', 'Free agents', '5')
    assert c.tab_parts['roster'].followed[-1] == FA
    c.rail.pick_team(0)                                      # back to a club: its league comes back
    assert (c.league, c.team) == (NHL, 0)


def test_ahl_rows_name_their_nhl_club():
    c = opened()
    c.rail.pick_league(AHL)
    v = c.rail.view()
    assert [r['id'] for r in v['rows']] == [42, 41, 40]     # Americans, Bruins, Gulls
    assert {r['id']: r['farm'] for r in v['rows']} == {40: 'ANA', 41: 'BOS', 42: ''}
    assert c.team == 42 and all(r['league'] == AHL for r in v['rows'])


def test_steps_stop_at_the_ends():
    c = opened()
    follows = c.tab_parts['roster'].followed
    c.rail.step(-1)                                          # first already: nothing moves, nobody follows
    assert c.team == 2 and follows == [2]
    for _ in range(5):
        c.rail.step(1)
    assert c.team == 90 and follows == [2, 1, 0, 90]        # the last one stops it
    c.rail.step(-1)
    assert c.team == 0


def test_a_league_keeps_its_last_pick():
    c = opened()
    c.rail.pick_team(1)
    c.rail.pick_league(AHL)
    assert c.team == 42
    c.rail.pick_team(40)
    c.rail.pick_league(NHL)
    assert c.team == 1
    c.rail.pick_league(AHL)
    assert c.team == 40


def test_beta1_pickers_move_the_rail():
    assert R.Rail.CALLS['league'] == 'pick_league' and R.Rail.CALLS['team'] == 'pick_team'
    assert C.OLD['pick_league'] == ('rail', 'pick_league') and C.OLD['pick_team'] == ('rail', 'pick_team')
    c = opened(tab='lines')
    for name, method in R.Rail.CALLS.items():               # the calls window/api.py runs for them
        assert callable(getattr(c.rail, method)), name
    getattr(c.rail, R.Rail.CALLS['team'])('41')            # the page sends text
    assert (c.league, c.team) == (AHL, 41) and c.tab_parts['lines'].followed[-1] == 41
    getattr(c.rail, R.Rail.CALLS['league'])(NHL)
    assert (c.league, c.team) == (NHL, 2)
    assert any('rail' in names and 'editor' in names for names in c.seen)   # beta1's editor slice moves too


def test_only_the_tab_in_view_follows():
    c = opened(tab='setup')
    roster = c.tab_parts['roster']
    c.rail.pick_team(0)
    assert all(not p.followed for p in c.tab_parts.values())
    c.shell.tab('roster')                                    # shown: it catches up with the rail
    assert roster.followed == [0]
    c.rail.step(-1)
    assert roster.followed == [0, 1]
    c.shell.tab('lines')                                     # the one it leaves hides; the new one follows
    assert roster.hidden == 1 and c.tab_parts['lines'].followed == [1]
    c.rail.pick_team(2)
    assert roster.followed == [0, 1] and c.tab_parts['lines'].followed == [1, 2]


def test_dots_for_unsaved_changes_and_held_ones():
    c = opened()
    dots = lambda: {r['id'] for r in c.rail.view()['rows'] if r['dirty']}     # noqa: E731
    assert dots() == set()
    c.session.history.append(Change('Edit a Bruin', team=1))     # applied on another team (a search)
    c.rail.pick_team(0)
    c.session.history.append(Change('Ducks C1'))                 # no team set: the rail's team when Save sees it
    assert dots() == {0, 1}
    assert [(ch.tab, ch.team) for ch, _undone in c.parts['save'].pending()] == [('Roster', 1), ('Roster', 0)]
    c.parts['save'].saved = list(c.session.history)               # saved
    assert dots() == set()
    c.session.history.pop()                                       # a saved change taken back: unsaved again
    assert dots() == {0} and c.parts['save'].unsaved() == 1
    c.tab_parts['lines'].holding.add(2)                           # a tab holds changes not applied yet
    assert dots() == {0, 2}
