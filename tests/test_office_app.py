"""The Front office tab (app/office.py, app/office_ctl.py), read only. Money: contractdollars in $5,000 units, the
cap of the league layer or NHL 19's own, text as the game shows it. Years: the stored length less the expansion
career's extra season. On a small made-up roster: an organisation's NHL roster, farm club (the AHL club with most of
its players) and prospects, sorting, groups, the pick, the "why" cards and the rail's cap space. Through the
Controller on the game's default roster: every NHL club reads."""
import datetime
import json
import threading

import pytest

from overtime_core import overlay, rosterupdate as U, teams as T
from overtime_roster.app import controller as C, jobs, office, sources
from overtime_roster.app import rail as R, roster_card as RC
from overtime_roster.app.office_ctl import OfficeCtl
from overtime_roster.app.session import BIOS as SESSION_BIOS

NHL, AHL, FA = T.NHL_LEAGUE, R.AHL, R.FA
TODAY = datetime.date(2026, 10, 14)


def bio(game_id, first, last, pos, team, proteam, status=0, length=0, dollars=0, two_way=0, ext=(0, 0),
        born=(1989, 1, 13), ovr=80):
    return {'game_id': game_id, 'firstname': first, 'lastname': last, 'position': pos, 'team': team,
            'proteam': proteam, 'contractstatus': status, 'contractlength': length, 'contractdollars': dollars,
            'contractis2way': two_way, 'extensionlength': ext[0], 'extensiondollars': ext[1], 'extensionis2way': 0,
            'born': datetime.date(*born), 'ovr': ovr}


# --- money, years, ages, sorting ---------------------------------------------------------------------------------------
def test_money_is_real_dollars():
    assert office.cap_hit({'contractdollars': 2500}) == 12_500_000       # $5,000 units
    assert office.cap_hit({}) == 0
    assert [office.money(d) for d in (12_500_000, 20_400_000, 95_175_000, 850_000, 999_499, 999_500, 0)] == [
        '$12.5M', '$20.4M', '$95.175M', '$850K', '$999K', '$1M', '$0K']
    assert office.money(-1_250_000) == '-$1.25M'
    assert office.short(9_840_000) == '$9.8M' and office.short(-100_000) == '-$0.1M'
    assert [office.tone(s) for s in (-1, 0, 1_999_999, 2_000_000)] == ['bad', 'caution', 'caution', 'good']


def test_the_cap_of_five_seasons(tmp_path):
    served = office.league_money(2026)
    assert [m['label'] for m in served] == ['2026-27', '2027-28', '2028-29', '2029-30', '2030-31']
    assert [m['cap'] for m in served] == [104_000_000, 113_500_000, 127_500_000, 129_000_000, 130_500_000]
    assert [m['floor'] for m in served] == [76_900_000, 83_900_000, 94_350_000, 95_850_000, 97_350_000]
    stock = office.league_money(2026, served=False)
    assert (stock[0]['cap'], stock[0]['floor']) == (overlay.CAP_STOCK[1] * 100_000, overlay.CAP_STOCK[0] * 100_000)
    assert office.league_served(str(tmp_path), {'layers': {'league': {}}})
    assert not office.league_served(str(tmp_path), {'layers': {'text': {}}})
    assert not office.league_served(str(tmp_path))                      # no record of the patch: NHL 19's cap


def test_years_leave_out_the_expansion_season():
    deal = bio(1, 'A', 'B', 0, 11, 11, length=3, dollars=2500)
    assert office.lengthened(deal) and office.years_left(deal) == 2
    assert office.years_left(deal, expansion=False) == 3
    assert office.years_left(dict(deal, contractlength=1)) == 1         # never below one
    seattle = dict(deal, proteam=-1, team=T.SEATTLE)
    assert office.years_left(seattle) == 2
    assert office.years_left(dict(deal, proteam=-1, team=35)) == 3      # a minors deal: not lengthened
    assert office.years_left(dict(deal, game_id=office.rosterupdate.SPECIAL_IDS)) == 3
    assert office.years_left(dict(deal, contractstatus=1)) == 3
    deals = [bio(i, 'A', 'B', 0, 0, 0, length=2, dollars=200) for i in range(office.MARKER)]
    assert office.carries_expansion(deals)
    assert not office.carries_expansion(deals[1:])                      # too few to tell
    assert not office.carries_expansion(deals + [bio(99, 'A', 'B', 0, 0, 0, length=1, dollars=200)])


def test_ages_as_the_game_counts_them():
    assert office.age_on(datetime.date(1989, 1, 13), TODAY, 8) == 29   # stored 8 years back: born 1997
    assert office.age_on(datetime.date(1997, 1, 13), TODAY, 0) == 29
    assert office.age_on(datetime.date(1996, 2, 29), TODAY, 1) == 29   # 29 February: the 28th
    assert office.age_on(None, TODAY, 8) is None


def row(name, **kv):
    return {'name': name, 'pos': 'C', 'age': 25, 'ovr': 80, 'cap': 1_000_000, 'years': 1, 'ext': None, **kv}


def test_sorting_keeps_names_in_order():
    rows = [row('Zach Hyman', cap=5_500_000, pos='LW'), row('Élie Aho', pos='D', age=None),
            row('Adam Aho', pos='G', ext=[2, 3_000_000, False]), row('Connor McDavid', cap=12_500_000)]
    names = [r['name'] for r in office.sort_rows(rows, 'name', 1)]
    assert names == ['Adam Aho', 'Connor McDavid', 'Élie Aho', 'Zach Hyman']   # accents count as plain letters
    assert [r['name'] for r in office.sort_rows(rows, 'cap', -1)] == ['Connor McDavid', 'Zach Hyman', 'Adam Aho',
                                                                     'Élie Aho']   # ties by name either way
    assert [r['name'] for r in office.sort_rows(rows, 'cap', 1)] == ['Adam Aho', 'Élie Aho', 'Zach Hyman',
                                                                    'Connor McDavid']
    assert [r['pos'] for r in office.sort_rows(rows, 'pos', 1)] == ['C', 'LW', 'D', 'G']
    assert office.sort_rows(rows, 'ext', -1)[0]['name'] == 'Adam Aho'
    assert office.sort_rows(rows, 'age', -1)[-1]['name'] == 'Élie Aho'    # no age: last
    assert [office.first_dir(k) for k in office.SORTS] == [1, 1, -1, -1, -1, -1, -1]


def test_a_deal_in_words():
    deal = {'cap': 12_500_000, 'years': 2, 'two_way': False, 'ext': [8, 20_400_000, False]}
    assert office.deal_text(deal) == '$12.5M x 2 years, one-way, then 8 x $20.4M.'
    assert office.deal_text(dict(deal, years=1, two_way=True, ext=None)) == '$12.5M x 1 year, two-way.'
    assert office.deal_text(dict(deal, cap=0)) == 'No contract: his rights belong to the team.'
    assert [office.contract_type(dict(deal, cap=c, two_way=w)) for c, w in ((1, False), (1, True), (0, False))] == [
        'One-way', 'Two-way', 'Rights']


# --- a small made-up roster --------------------------------------------------------------------------------------------
# index, league, abbr, nickname, ahlaffiliate (ANA's is stale: its players are on no AHL club)
CLUBS = [(0, NHL, 'ANA', 'Ducks', 40), (11, NHL, 'EDM', 'Oilers', 35), (90, NHL, 'ATL', 'All-Stars Atlantic', None),
         (35, AHL, 'BAK', 'Condors', None), (40, AHL, 'SD', 'Gulls', None), (45, AHL, 'HER', 'Bears', None),
         (66, 2, 'BIF', 'Brynas', None)]
BIOS = [bio(1, 'Connor', 'McDavid', 0, 11, 11, length=3, dollars=2500, ext=(8, 4080), ovr=94),
        bio(2, 'Leon', 'Draisaitl', 0, 11, 11, length=4, dollars=1700, born=(1987, 10, 27), ovr=88),
        bio(3, 'Zach', 'Hyman', 1, 11, 11, length=3, dollars=1100, born=(1984, 6, 9), ovr=84),
        bio(4, 'Farm', 'Defender', 3, 35, 11, length=2, dollars=170, two_way=1, ovr=70),
        bio(5, 'Farm', 'Goalie', 4, 35, 11, length=2, dollars=180, two_way=1, ovr=68),
        bio(6, 'Young', 'Prospect', 2, 45, 11, status=1, ovr=60),
        bio(7, 'Euro', 'Rights', 0, 66, 11, status=1, ovr=55),
        bio(60000, 'Special', 'Id', 0, 11, 11, length=3, dollars=100)]
BIOS += [bio(100 + i, 'Duck', f'Number{i:02d}', i % 5, 0, 0, length=2, dollars=1200) for i in range(20)]


class Session:
    """What the office and the rail read of a RosterSession."""

    def __init__(self, bios=BIOS):
        self.rows = {R.TEAMS: [{'index': i, 'league': lg, 'abbrname': ab, 'nickname': nick, 'cityname': '',
                                'ahlaffiliate': aff, 'feprimarycolor': 0x112233} for i, lg, ab, nick, aff in CLUBS],
                     office.BIOS: bios, office.PLAYERS: []}
        self.team_row = {i: k for k, (i, *_rest) in enumerate(CLUBS)}
        self.free_agents = []
        self.history = []
        self.today = TODAY
        self.db = {}

    def team_name(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['nickname'] if team in self.team_row else f'Team {team}'

    def team_abbr(self, team):
        return self.rows[R.TEAMS][self.team_row[team]]['abbrname'] if team in self.team_row else ''

    def teams(self, league):
        return [{'id': i, 'name': nick, 'abbr': ab, 'count': 20} for i, lg, ab, nick, _aff in CLUBS if lg == league]

    def name(self, b):
        return f"{b['firstname']} {b['lastname']}"

    def birth(self, b):
        return b['born']

    def ai(self, b):
        return None, None, {'skill_overall': b['ovr']}


class Host:
    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)


class Ctl:
    def __init__(self, session, served=True):
        self.lock = threading.RLock()
        self.session = session
        self.busy = None
        self.team = 11
        self.upd_season = 2026
        self.game_dir = 'no game here'
        self.patch_status = {'layers': {'league': {}}} if served else {'layers': {}}
        self.status = {}
        self.pushed = []
        self.host = Host()
        self.rail = R.Rail(self)

    def say(self, text, tone='info', progress=None):
        self.status = {'text': text, 'tone': tone}

    def changed(self, *names):
        self.pushed += names


@pytest.fixture
def ctl():
    c = Ctl(Session())
    return c, OfficeCtl(c)


def test_an_organisation_in_three_groups(ctl):
    c, fo = ctl
    v = fo.view()
    assert (v['team']['code'], v['why'], v['from_farm']) == ('EDM', None, None)
    assert [(t['label'], t['value'], t['tone']) for t in v['tiles']] == [
        ('Payroll 2026-27', '$26.5M', ''), ('Salary cap', '$104M', ''), ('Cap space', '$77.5M', 'good'),
        ('Lowest payroll', '$76.9M', ''), ('NHL · farm · prospects', '3 · 2 · 2', '')]
    assert [(s['committed'], s['cap'], s['signed']) for s in v['seasons']] == [
        ('$26.5M', '$104M', 3), ('$26.5M', '$113.5M', 3), ('$28.9M', '$127.5M', 2), ('$20.4M', '$129M', 1),
        ('$20.4M', '$130.5M', 1)]
    assert v['seasons'][0]['share'] == pytest.approx(26.5 / 104) and v['seasons'][0]['tone'] == 'good'
    assert [(g['key'], g['title'], len(g['rows']), g['note']) for g in v['groups']] == [
        ('nhl', 'Oilers: NHL roster', 3, None), ('farm', 'Farm: Condors', 2, None),
        ('prospects', 'Prospects and rights', 2, None)]
    mc = v['groups'][0]['rows'][0]
    assert {k: mc[k] for k in ('key', 'name', 'pos', 'age', 'ovr', 'cap', 'cap_text', 'years', 'type', 'ext', 'where',
                               'rights', 'sel')} == {
        'key': 1, 'name': 'Connor McDavid', 'pos': 'C', 'age': 29, 'ovr': 94, 'cap': 12_500_000,
        'cap_text': '$12.5M', 'years': 2, 'type': 'One-way', 'ext': '8 x $20.4M', 'where': None, 'rights': False,
        'sel': False}
    farm = v['groups'][1]['rows'][0]
    assert (farm['cap_text'], farm['years'], farm['type'], farm['where']['text']) == ('$900K', 1, 'Two-way', 'Condors')
    young = next(r for r in v['groups'][2]['rows'] if r['key'] == 6)
    assert (young['cap_text'], young['type'], young['rights'], young['where']['text']) == (
        'No contract', 'Rights', True, 'Bears')
    assert v['contract'] == {'available': False, 'sign': False, 'note': office.PICK_FIRST} and v['note'] == office.NOTE
    assert v['window'] is None
    assert v['sort'] == {'key': 'cap', 'dir': -1} and v['group'] == 'all' and v['pick'] is None
    json.dumps(v)


def test_over_the_cap_and_no_farm_club(ctl):
    c, fo = ctl
    c.team = 0
    v = fo.view()
    assert v['tiles'][2] == {'label': 'Cap space', 'value': '-$16M', 'tone': 'bad'}
    assert v['seasons'][0]['tone'] == 'bad' and v['seasons'][0]['share'] == 1
    assert v['groups'][1]['note'] == 'This organisation has no farm club in this roster.'
    assert v['groups'][2]['note'] == 'No prospects or rights in this roster.'
    assert fo.rail_number({'id': 0}) == {'text': '-$16.0M', 'tone': 'bad', 'tip': 'cap space'}
    assert fo.rail_number({'id': 11}) == {'text': '$77.5M', 'tone': '', 'tip': 'cap space'}
    assert fo.rail_number({'id': 35}) is None and fo.rail_number({'id': FA}) is None


def test_a_farm_club_shows_its_organisation(ctl):
    c, fo = ctl
    fo.follow(11)
    fo.pick(1)
    c.team = 35
    fo.follow(35)
    v = fo.view()
    assert (v['team']['code'], v['from_farm']) == ('EDM', 'Their farm club: Condors')
    assert v['pick']['key'] == 1                        # the same organisation: the pick stays
    c.team = 0
    fo.follow(0)
    assert fo.view()['pick'] is None


def test_why_cards(ctl):
    c, fo = ctl
    for team, why in ((FA, 'Free agents belong to no NHL organisation. Pick an NHL club or its farm club.'),
                      (90, 'All-Star teams have no contracts. Pick an NHL club.'),
                      (45, 'Bears are the farm club of no NHL organisation in this roster. Pick an NHL club.'),
                      (66, 'The front office covers the 32 NHL organisations and their farm clubs. SHL clubs have '
                           'no NHL contracts. Pick an NHL club.'),
                      (R.SEATTLE, 'The Seattle Kraken have no players in this roster. Pick another NHL club.'),
                      (None, 'Pick a team on the left.')):
        c.team = team
        v = fo.view()
        assert v['why'] == why and 'tiles' not in v, team
    c.session = None
    v = fo.view()
    assert v['why'] == v['tip'] == 'Pick a roster in Setup first.' and v['team'] is None
    assert fo.rail_number({'id': 11}) is None


def test_contracts_that_cannot_be_read(ctl, monkeypatch):
    c, fo = ctl

    def broken(*a):
        raise KeyError('contractdollars')
    monkeypatch.setattr(office, 'read', broken)
    assert fo.view()['why'] == office.UNREAD
    assert fo.rail_number({'id': 11}) is None and 'could not be read' in c.host.lines[-1]


def test_sort_group_pick(ctl):
    c, fo = ctl
    fo.sort('age')
    assert fo.view()['sort'] == {'key': 'age', 'dir': -1}
    assert [r['name'] for r in fo.view()['groups'][0]['rows']] == ['Zach Hyman', 'Leon Draisaitl', 'Connor McDavid']
    fo.sort('age')                                      # again: turned round
    assert fo.view()['sort'] == {'key': 'age', 'dir': 1}
    fo.sort('name')
    assert fo.view()['sort'] == {'key': 'name', 'dir': 1}
    fo.sort('salary')
    assert fo.view()['sort'] == {'key': 'name', 'dir': 1}
    fo.group('farm')
    v = fo.view()
    assert v['group'] == 'farm' and [g['key'] for g in v['groups']] == ['farm']
    assert v['counts'] == {'nhl': 3, 'farm': 2, 'prospects': 2, 'free': 0}
    fo.group('everyone')
    assert fo.view()['group'] == 'all'
    fo.pick('1')
    v = fo.view()
    assert v['pick'] == {'key': 1, 'name': 'Connor McDavid', 'pos': 'C',
                         'deal': '$12.5M x 2 years, one-way, then 8 x $20.4M.'}
    assert next(r for r in v['groups'][0]['rows'] if r['key'] == 1)['sel']
    assert v['contract'] == {'available': True, 'sign': False, 'note': office.CONTRACT}
    fo.pick(1)                                          # the same player again lets go
    assert fo.view()['pick'] is None
    fo.pick(7)
    v = fo.view()
    assert v['pick']['deal'] == 'No contract: his rights belong to the team.'
    assert v['contract'] == {'available': False, 'sign': False, 'note': office.NO_DEAL}
    assert fo.contract() == {'ok': False, 'error': office.NO_DEAL}           # rights: not signed here yet
    assert c.status == {'text': office.NO_DEAL, 'tone': 'info'} and fo.view()['window'] is None
    fo.pick('nobody')
    assert fo.view()['pick'] is None
    assert fo.contract('x') == {'ok': False, 'error': office.PICK_FIRST}
    assert set(c.pushed) == {'office'}


def test_without_game_patch_the_game_s_own_cap():
    c = Ctl(Session(), served=False)
    v = OfficeCtl(c).view()
    assert v['note'] == office.NOTE_STOCK and v['tiles'][1]['value'] == office.money(overlay.CAP_STOCK[1] * 100_000)


def test_a_roster_without_the_expansion_season_shows_its_lengths():
    bios = BIOS + [bio(200, 'One', 'Year', 0, 0, 0, length=1, dollars=200)]
    c = Ctl(Session(bios))
    v = OfficeCtl(c).view()
    assert v['groups'][0]['rows'][0]['years'] == 3      # McDavid's stored 3


def test_contract_years_are_years_left_with_the_expansion_season():
    """The Roster card and the contract window write years left: + 1 stored in a roster with the extra season."""
    class S:
        history = []

    deal = lambda i, n: bio(i, 'P', str(i), 0, 11, 11, length=n, dollars=200)      # noqa: E731
    s, plain = S(), S()
    s.rows = {SESSION_BIOS: [deal(i, 3) for i in range(1, office.MARKER + 1)]}
    plain.rows = {SESSION_BIOS: s.rows[SESSION_BIOS] + [deal(999, 1)]}
    b = s.rows[SESSION_BIOS][0]
    assert RC.expansion(s) and not RC.expansion(plain)
    assert [RC.stored_years(s, b, n) for n in (0, 1, 4)] == [0, 2, 5]
    assert RC.stored_years(s, b, 4, 0) == 4                 # no money: expansion_contracts leaves it
    assert RC.stored_years(plain, b, 4) == 4
    assert office.years_left(dict(b, contractlength=5), RC.expansion(s)) == 4


@pytest.mark.game
def test_every_nhl_club_reads(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))

    def inline(work, done=None, failed=None, expected=()):
        return done and done(work())
    monkeypatch.setattr(jobs, 'run', inline)

    class Host:
        def __init__(self):
            self.snaps, self.lines = {}, []

        def register(self, name, fn):
            self.snaps[name] = fn

        def changed(self, *names):
            pass

        def log(self, msg):
            self.lines.append(msg)

    host = Host()
    c = C.Controller(host, game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    fo = c.parts['office']
    c.shell.tab('office')
    clubs = [t['id'] for t in c.rail.listed(c.session, NHL) if not t['extra']]
    assert len(clubs) >= 31
    for team in clubs:
        c.parts['rail'].pick_team(team)
        v = fo.view()
        assert v['why'] is None and len(v['seasons']) == 5 and v['counts']['nhl'] >= 18, team
        assert fo.rail_number({'id': team})['tip'] == 'cap space'
        json.dumps(host.snaps['office']())
    c.parts['rail'].pick_team(11)
    v = fo.view()
    assert v['team']['code'] == 'EDM' and v['groups'][0]['title'] == 'Edmonton Oilers: NHL roster'
    mc = next(r for r in v['groups'][0]['rows'] if r['name'] == 'Connor McDavid')
    assert mc['cap_text'] == '$12.5M' and mc['type'] == 'One-way'
    c.parts['rail'].pick_team(35)                       # Bakersfield: EDM's farm club
    assert fo.view()['from_farm'] == 'Their farm club: Bakersfield Condors'


@pytest.mark.game
def test_the_contract_window_changes_a_deal(game_dir, tmp_path, monkeypatch):
    """Contract... on the game's own roster: wrong values all at once, a change as one Undo on the Save bar, the
    Roster card's values, rights refused."""
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(jobs, 'run', lambda work, done=None, failed=None, expected=(): done and done(work()))

    class Host:
        def __init__(self):
            self.snaps, self.lines = {}, []

        def register(self, name, fn):
            self.snaps[name] = fn

        def changed(self, *names):
            pass

        def log(self, msg):
            self.lines.append(msg)

    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.shell.tab('office')
    c.parts['rail'].pick_team(11)
    fo, s = c.parts['office'], c.session
    v = fo.view()
    mc = next(r for r in v['groups'][0]['rows'] if r['name'] == 'Connor McDavid')
    years, space = mc['years'], v['tiles'][2]['value']
    assert v['window'] is None and years >= 1
    other = years - 1 if years > 1 else 2
    assert c.calls['office_contract'](mc['key']) == {'ok': True}
    w = fo.view()['window']
    assert (w['name'], w['values'], w['problems'], w['typed']) == (
        'Connor McDavid', {'cap': 12.5, 'years': years, 'twoway': False}, [], None)
    assert w['space']['now'] == space and w['space']['counts'] and w['space']['after'] is None

    bad = c.calls['office_contract_apply']({'cap': 'lots', 'years': 9, 'twoway': 'maybe'})
    assert not bad['ok'] and [p['key'] for p in bad['problems']] == ['cap', 'years', 'twoway']
    w = fo.view()['window']
    assert w['typed'] == {'cap': 'lots', 'years': 9, 'twoway': 'maybe'} and len(w['problems']) == 3
    assert [p['key'] for p in c.calls['office_contract_apply']({'cap': 0.05})['problems']] == ['cap']
    assert [p['key'] for p in c.calls['office_contract_apply']({'years': 0})['problems']] == ['years']
    assert len(s.history) == 0

    assert c.calls['office_contract_apply']({'cap': '11', 'years': other, 'twoway': True}) == {
        'ok': True, 'changes': 3}
    ch = s.history[-1]
    assert ch.tab == 'Front office' and ch.label == (
        f'Connor McDavid: cap hit $12.5M to $11M, contract years {years} to {other}, deal one-way to two-way')
    assert c.status['tone'] == 'good'
    v = fo.view()
    mc = next(r for r in v['groups'][0]['rows'] if r['name'] == 'Connor McDavid')
    assert v['window'] is None and (mc['cap_text'], mc['years'], mc['type']) == ('$11M', other, 'Two-way')
    pi = c.parts['office']._pi(mc['key'])
    b = s.bio(pi)[1]
    assert (b['contractdollars'], b['contractlength'], b['contractis2way']) == (2200, other + RC.expansion(s), 1)
    card = c.parts['roster']
    assert {k: RC.values(s, card.clock(s), pi)[k] for k in ('salary', 'years', 'twoway')} == {
        'salary': 11.0, 'years': other, 'twoway': 1}

    card.undo()                                        # the Save bar's Undo takes the whole deal back
    mc = next(r for r in fo.view()['groups'][0]['rows'] if r['name'] == 'Connor McDavid')
    assert (mc['cap_text'], mc['years'], mc['type']) == ('$12.5M', years, 'One-way') and not s.history

    rights = next((r for g in fo.view()['groups'] for r in g['rows'] if r['rights']), None)
    if rights is not None:
        assert c.calls['office_contract'](rights['key']) == {'ok': False, 'error': office.NO_DEAL}
        assert fo.view()['window'] is None


@pytest.mark.game
def test_a_free_agent_signs_through_the_front_office(game_dir, tmp_path, monkeypatch):
    """Sign... on the game's own roster: the Free agents group, a window with the lowest deal, wrong values at once,
    one Undo takes the player back, no Seattle organisation in the served default."""
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(jobs, 'run', lambda work, done=None, failed=None, expected=(): done and done(work()))

    class Host:
        def __init__(self):
            self.snaps, self.lines = {}, []

        def register(self, name, fn):
            self.snaps[name] = fn

        def changed(self, *names):
            pass

        def log(self, msg):
            self.lines.append(msg)

    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.shell.tab('office')
    c.parts['rail'].pick_team(11)
    fo, s = c.parts['office'], c.session
    c.calls['office_group']('free')
    v = fo.view()
    assert [g['key'] for g in v['groups']] == ['free'] and v['counts']['free'] > 20
    agent = v['groups'][0]['rows'][0]
    assert agent['rights'] and v['groups'][0]['title'] == 'Free agents: sign with Edmonton Oilers'
    c.calls['office_pick'](agent['key'])
    assert fo.view()['contract'] == {'available': True, 'sign': True, 'note': office.SIGN}
    assert c.calls['office_contract'](agent['key']) == {'ok': True}
    w = fo.view()['window']
    assert (w['sign'], w['club'], w['base'], w['values']) == (True, 'Edmonton Oilers', 0, {'cap': 0.85, 'years': 1,
                                                                                         'twoway': False})
    bad = c.calls['office_contract_apply']({'cap': 'lots', 'years': 12, 'twoway': False})
    assert not bad['ok'] and [p['key'] for p in bad['problems']] == ['cap', 'years']
    before, free_before = s.db.to_bytes(), len(s.free_agents)
    ok = c.calls['office_contract_apply']({'cap': 1.3, 'years': 2, 'twoway': True})
    assert ok == {'ok': True, 'changes': 1} and fo.view()['window'] is None
    assert len(s.free_agents) == free_before - 1 and c.session.history[-1].label.endswith('signs with EDM')
    c.calls['office_group']('nhl')
    nhl = next(g for g in fo.view()['groups'] if g['key'] == 'nhl')
    row = next(r for r in nhl['rows'] if r['key'] == agent['key'])
    assert row['cap'] == 1_300_000 and row['type'] == 'Two-way' and row['years'] == 2
    s.undo()
    assert s.db.to_bytes() == before and len(s.free_agents) == free_before
    c.parts['rail'].pick_team(office.SEATTLE)
    c.calls['office_group']('free')
    r = c.calls['office_contract'](agent['key'])
    assert r['ok'] is False      # the served default has no Seattle organisation, so nothing to sign with


@pytest.mark.game
def test_a_signing_stores_the_extra_season_on_a_roster_that_carries_it(game_dir, tmp_path, monkeypatch):
    """On a roster with the expansion season the bio stores years + 1; the Front office row still shows years."""
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(jobs, 'run', lambda work, done=None, failed=None, expected=(): done and done(work()))
    monkeypatch.setattr(office, 'carries_expansion', lambda bios: True)      # what RC.expansion and the rows read

    class Host:
        def register(self, name, fn):
            pass

        def changed(self, *names):
            pass

        def log(self, msg):
            pass

    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.shell.tab('office')
    c.parts['rail'].pick_team(11)
    fo, s = c.parts['office'], c.session
    c.calls['office_group']('free')
    agent = fo.view()['groups'][0]['rows'][0]
    assert c.calls['office_contract'](agent['key'])['ok']
    assert c.calls['office_contract_apply']({'cap': 1.0, 'years': 3, 'twoway': False}) == {'ok': True, 'changes': 1}
    st = U.State(s.db)
    assert st.bio(st.main_pi(agent['key']))['contractlength'] == 4
    c.calls['office_group']('nhl')
    row = next(r for g in fo.view()['groups'] for r in g['rows'] if r['key'] == agent['key'])
    assert row['years'] == 3
