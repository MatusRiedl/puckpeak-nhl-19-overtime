"""The Lines and Strategy tabs driven through the Controller the way the page does (the game's roster read only, a
throwaway home and saves folder): each team's draft waits for Apply and is kept while the rail moves, Take back (the
draft, the applied changes dropped or put back value by value), the Why cards, the rail's number, Game defaults and
the hidden values; beta1's names on the draft; a group edit going through the roster save path; the tabs' words."""
import json

import pytest

from overtime_core import lines as L, strategy as S, tdb
from overtime_core.roster import ES_SLOTS
from overtime_roster.app import (controller as C, install, jobs, labels, lines_ctl as LC, settings, sources,
                                 strategy_ctl as SC)
from overtime_roster.app.session import EditError, RosterSession

EDM, FLA, TOR = 11, 12, 27
MASCOTS_EAST = 380      # 2 goalies, 13 skaters in NHL 19's roster
SEATTLE, FA = 399, -1   # the rail's ids (the strategies table knows Seattle as 499)


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

    def snap(self, name):
        return self.snaps[name]()


@pytest.fixture(scope='module')
def game(game_dir):
    return sources.GameData(game_dir)


@pytest.fixture
def app(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('OVERTIME_SAVE_DIR', str(tmp_path / 'saves'))

    def inline(work, done=None, failed=None, expected=()):
        try:
            out = work()
        except expected as err:
            return failed and failed(str(err))
        return done and done(out)
    monkeypatch.setattr(jobs, 'run', inline)
    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.pick_team(EDM)
    return c, c.host


def rail_row(host, team):
    return next(r for r in host.snap('rail')['rows'] if r['id'] == team)


def places(view):
    return {s['slot']: s for u in view['units'] for s in u['slots']}


def shown(view):
    return {r['field']: r for sec in view['sections'] for r in sec['rows']}


def errors(c):
    return [i for i in c.session.verify() if i.level == 'error']


# --- the tabs' words (no game) ---------------------------------------------------------------------------------------
def test_line_sections_cover_every_group():
    assert sorted(g for gs in labels.LINE_SECTIONS.values() for g in gs) == sorted(L.GROUPS)
    sections = {s for s, _, _ in labels.LINE_GROUPS}
    assert sections == set(labels.LINE_SECTIONS)
    for section, groups in labels.LINE_SECTIONS.items():
        page = {sl for s, _, units in labels.LINE_GROUPS if s == section for _, slots in units for sl, _ in slots}
        assert page == {sl for g in groups for sl in L.GROUPS[g]}, section


def test_every_place_has_words_a_unit_and_a_page():
    assert set(LC.PLACES) == set(L.SLOTS) and list(LC.PAGE_UNITS) == list(labels.LINE_SECTIONS)
    assert LC.PAGES == tuple(labels.LINE_SECTIONS) + ('Letters',) and set(LC.PAGE_NOTES) == set(labels.LINE_SECTIONS)
    assert LC.PLACES['l1lw'] == ('LW', 'left wing on forward line 1', 'Forward line 1', 'Even strength')
    assert LC.PLACES['g1'][1] == 'starting goalie' and LC.PLACES['s1'][1] == 'shooter 1'
    assert LC.PLACES['pp1c'][1] == 'centre on unit 1: 5 on 4' and LC.PLACES['three_c'][1] == 'centre in NHL Threes'
    units = [title for title, _row in LC.PAGE_UNITS['Even strength']]
    assert units[0] == 'Forward line 1' and 'Defence pair 1' in units and 'Goalies' in units


def test_lineup_problems_and_who_fits_in_words():
    full = {slot: [1] for slot in ES_SLOTS}
    assert LC.LinesCtl.problems(full) == []
    assert LC.LinesCtl.problems(dict(full, l1c=[])) == ['Centre on forward line 1 is empty.']
    assert LC.LinesCtl.problems(dict(full, l1c=[1, 2])) == [
        'Centre on forward line 1 has 2 players. Click it and pick the one who plays there.']
    fits = LC.LinesCtl.fits
    skater, goalie = {'id': 1, 'pos': 'C'}, {'id': 2, 'pos': 'G'}
    assert fits(None, skater, True, {}) == (False, '')
    assert fits('l1c', skater, True, {'l1c': [1]}) == (False, 'He plays here now.')
    assert fits('g1', skater, True, {}) == (False, 'Only goalies play in this place.')
    assert fits('l1c', goalie, True, {}) == (False, 'Goalies play only in goal.')
    assert fits('pp1c', skater, False, {}) == (False, 'Scratched: give him a place on the Even strength page first.')
    assert fits('l1c', skater, False, {}) == (True, '')         # brought in: he dresses
    assert fits('three_c', skater, False, {}) == (True, '')     # NHL Threes: he need not dress


def test_strategy_words():
    assert set(SC.ROWS) == set(S.FIELDS) and set(SC.HIDDEN) <= set(SC.ROWS)
    assert SC.SECTIONS[0][0] == 'Team strategies' == SC.TEAM_SECTION
    assert SC.where('forward1_bias1') == 'Carry or Dump on forward line 1' and SC.where('oz_forecheck') == 'Forecheck'
    assert SC.words('oz_forecheck', 1) == '2-3' and SC.words('forward1_bias1', 6) == '6'
    assert [SC.number(v) for v in (3, 3.0, '3', ' 3 ', 3.5, True, 'x', None)] == [3, 3, 3, 3, None, None, None, None]
    assert not SC.bad('forward2_bias2', 10) and SC.bad('forward2_bias2', 13) and SC.bad('oz_forecheck', 4)
    assert SC.problems({'forward2_bias2': 13, 'oz_forecheck': 1}) == [
        "Line 2 tendency 2 holds 13, but the game's values go from 0 to 10."]
    assert SC.describe({'oz_forecheck': 0}, {'oz_forecheck': 1}) == 'Forecheck: 2-3'
    assert SC.describe({'oz_forecheck': 0, 'forward1_bias1': 5}, {'oz_forecheck': 1, 'forward1_bias1': 6}) == \
        '2 strategies changed'
    assert SC.describe({'not_on_the_menu': 0}, {'not_on_the_menu': 1}) == '1 strategy changed'


# --- Lines ----------------------------------------------------------------------------------------------------------
@pytest.mark.game
def test_lines_draft_waits_for_apply(app):
    c, host = app
    c.tab('lines')
    lp = c.parts['lines']
    before = c.session.db.to_bytes()
    v = host.snap('lines')
    assert v['why'] is None and v['id'] == EDM and v['title'] == 'Edmonton Oilers: lines'
    assert v['page'] == 'Even strength' and [p['id'] for p in v['pages']] == list(LC.PAGES)
    assert v['dressed'] == 20 and v['problems'] == [] and v['auto_label'] == 'Deal all lines again'
    assert not (v['touched'] or v['can_apply'] or v['mine'] or v['can_undo']) and v['can_auto']
    json.dumps(v)
    assert host.snap('rail')['unit'] == 'dressed'
    assert rail_row(host, EDM)['number'] == {'text': '20', 'tip': 'dressed'} and not rail_row(host, EDM)['dirty']

    # click a place, then a player: the left wings of lines 1 and 2 swap in the draft
    a, b = places(v)['l1lw']['player']['id'], places(v)['l2lw']['player']['id']
    assert c.calls['lines_slot']('l1lw') == {'ok': True}
    v = host.snap('lines')
    assert v['picked'] == 'l1lw' and v['picked_label'] == 'left wing on forward line 1' and v['can_empty']
    who = {p['id']: p for p in v['players']}
    assert who[a]['here'] and not who[a]['fits'] and who[b]['fits']
    goalie = next(p for p in v['players'] if p['pos'] == 'G')
    assert (goalie['fits'], goalie['why']) == (False, 'Goalies play only in goal.')
    assert c.calls['set_slot'](None, b) == {'ok': True}
    v = host.snap('lines')
    assert v['picked'] is None and v['touched'] and v['can_apply'] and v['problems'] == []
    assert places(v)['l1lw']['player']['id'] == b and places(v)['l2lw']['player']['id'] == a
    assert places(v)['l1lw']['changed'] and not places(v)['l1c']['changed']
    assert c.session.history == [] and c.session.db.to_bytes() == before        # nothing written yet
    assert lp.dirty(EDM) and lp.drafts() == 'Lines not applied yet: EDM.' and rail_row(host, EDM)['dirty']

    # the rail moves on and back: each team keeps its own draft
    c.pick_team(FLA)
    assert host.snap('lines')['id'] == FLA and not host.snap('lines')['touched'] and not lp.dirty(FLA)
    c.pick_team(EDM)
    assert host.snap('lines')['touched'] and lp.dirty(EDM)

    assert c.calls['lines_apply']() == {'ok': True}
    (ch,) = c.session.history
    assert (ch.tab, ch.team, ch.label) == ('Lines', EDM, '2 places changed')
    assert ('EDM left wing on forward line 1', c.session.summary(a)['name'], c.session.summary(b)['name']) in ch.details
    h = c.session.slot_holders(EDM)
    assert h['l1lw'] == [b] and h['l2lw'] == [a]
    v = host.snap('lines')
    assert (v['note'], v['note_tone']) == (LC.APPLIED, 'good') and v['mine'] and v['can_undo'] and not v['touched']
    assert not lp.dirty(EDM) and lp.drafts() == '' and rail_row(host, EDM)['dirty']    # Save's dot now
    assert [(x.tab, x.team) for x, _undone in c.parts['save'].pending()] == [('Lines', EDM)]
    assert any('EDM lines: 2 places changed.' in line for line in host.lines)

    # Take back my lines: nothing else touched those rows since, so the change leaves My edits
    assert c.calls['lines_undo']() == {'ok': True}
    assert c.session.history == [] and c.session.db.to_bytes() == before
    v = host.snap('lines')
    assert not (v['mine'] or v['can_undo']) and v['note'] == LC.PAGE_NOTES['Even strength']
    assert c.calls['lines_undo']() == {'ok': False} and c.status['text'] == 'Nothing to take back on this team.'


@pytest.mark.game
def test_lines_refusals_letters_and_save(app):
    c, host = app
    c.tab('lines')
    before = c.session.db.to_bytes()
    v = host.snap('lines')
    goalie = next(p['id'] for p in v['players'] if p['pos'] == 'G')
    skater = next(p['id'] for p in v['players'] if p['pos'] != 'G' and p['dressed'])
    scratch = next(p for p in v['players'] if p['pos'] != 'G' and not p['dressed'])
    assert c.calls['set_slot']('pp1c', scratch['id']) == {
        'error': f"{scratch['name']} is scratched. Give him a place on the Even strength page first."}
    assert c.calls['set_slot']('l1c', 99999) == {'error': 'That player is not on this team.'}
    assert c.calls['set_slot'](None, skater) == {'error': 'Click a place first, then the player for it.'}
    assert c.calls['lines_slot']('nope') == {'error': 'There is no such place here.'}
    assert c.calls['lines_section']('Nope') == {'error': 'There is no such page.'}
    assert c.calls['lines_apply']() == {'error': 'Nothing to apply: change a place or a letter first.'}
    assert c.status['text'] == 'Nothing to apply: change a place or a letter first.'

    # a goalie at centre or a skater in goal: the game crashes loading that roster (roster-checks.md)
    assert c.calls['set_slot']('l1c', goalie) == {'error': 'Goalies play only in goal.'}
    assert c.calls['set_slot']('g1', skater) == {'error': 'Only goalies play in that place.'}
    assert not host.snap('lines')['touched']

    # an empty place of the lineup is shown, and Apply still goes (the game plays a line short)
    assert c.calls['set_slot']('l1c', None) == {'ok': True}
    v = host.snap('lines')
    assert v['problems'] == ['Centre on forward line 1 is empty.'] and v['touched'] and v['can_apply']
    assert c.calls['lines_apply']() == {'ok': True}
    assert c.session.slot_holders(EDM).get('l1c', []) == []
    assert c.calls['lines_undo']() == {'ok': True}
    assert not host.snap('lines')['touched'] and c.session.history == [] and c.session.db.to_bytes() == before

    # a scratched skater brought in on the Even strength page dresses; the one he replaces sits
    out = places(v)['l4c']['player']['id']
    assert c.calls['set_slot']('l4c', scratch['id']) == {'ok': True}
    who = {p['id']: p for p in host.snap('lines')['players']}
    assert who[scratch['id']]['dressed'] and not who[out]['dressed'] and host.snap('lines')['dressed'] == 20
    assert rail_row(host, EDM)['number']['text'] == '20'
    c.calls['lines_undo']()

    # Letters: skaters only, one C; more than three letters are allowed
    assert c.calls['lines_section']('Letters') == {'ok': True}
    v = host.snap('lines')
    assert v['note'] == LC.LETTERS_RULE and all(p['pos'] != 'G' for p in v['players']) and not v['can_auto']
    assert c.calls['lines_slot']('l1c') == {'error': 'There is no such place here.'}
    letters = {p['id']: p['letter'] for p in v['players']}
    captain = next(i for i, x in letters.items() if x == 'C')
    plain = [i for i, x in letters.items() if not x]
    assert sorted(x for x in letters.values() if x) == ['A', 'A', 'C']
    assert c.calls['set_captain'](plain[0], 7) == {'error': 'Pick C, A or none.'}
    assert c.calls['set_captain'](plain[1], 2) == {'ok': True}       # a fourth letter: the game wears it
    assert sorted(p['letter'] for p in host.snap('lines')['players'] if p['letter']) == ['A', 'A', 'A', 'C']
    assert c.calls['lines_undo']() == {'ok': True}
    assert c.calls['set_captain'](plain[0], 1) == {'ok': True}       # a new C takes the C from the old one
    v = host.snap('lines')
    letters = {p['id']: p for p in v['players']}
    assert letters[plain[0]]['letter'] == 'C' and letters[captain]['letter'] == ''
    assert letters[plain[0]]['letter_changed'] and v['touched'] and v['can_apply']
    assert c.calls['lines_apply']() == {'ok': True}
    (ch,) = c.session.history
    assert (ch.tab, ch.team, ch.label) == ('Lines', EDM, '2 letters changed')

    # saved: the roster's lines are the new base, nothing of this tab's to take back
    c.parts['save'].saved = list(c.session.history)
    v = host.snap('lines')
    assert not (v['mine'] or v['can_undo']) and v['note'] == LC.LETTERS_RULE
    assert c.calls['lines_undo']() == {'ok': False}
    c.undo()
    assert c.session.db.to_bytes() == before


@pytest.mark.game
def test_take_back_after_another_change_puts_values_back_one_by_one(app):
    c, host = app
    c.tab('lines')
    s = c.session
    before, holders = s.db.to_bytes(), s.slot_holders(EDM)
    v = host.snap('lines')
    a, b = places(v)['l1lw']['player']['id'], places(v)['l2lw']['player']['id']
    c.calls['set_slot']('l1lw', b)
    assert c.calls['lines_apply']() == {'ok': True}
    # the Roster tab changes another field of one of the same rows after it
    row = s.entry_row[a]
    number = 98 if s.rows[LC.ROSTER][row]['jersey'] != 98 else 97
    other, _ = s.edit('Number', lambda setter: setter(LC.ROSTER, row, 'jersey', number))
    other.tab, other.team = 'Roster', EDM
    assert c.calls['lines_undo']() == {'ok': True}
    assert [ch.label for ch in s.history] == ['2 places changed', 'Number', 'Edmonton Oilers: lines taken back']
    back = s.history[-1]
    assert (back.tab, back.team) == ('Lines', EDM)
    assert s.slot_holders(EDM) == holders and s.rows[LC.ROSTER][row]['jersey'] == number     # the number stays
    v = host.snap('lines')
    assert not (v['mine'] or v['can_undo'] or v['touched'])
    assert c.calls['lines_undo']() == {'ok': False}
    assert any(line == 'EDM lines: taken back.' for line in host.lines)
    for _ in range(3):
        c.undo()
    assert s.db.to_bytes() == before


@pytest.mark.game
def test_deal_again(app):
    c, host = app
    c.tab('lines')
    before = c.session.db.to_bytes()
    asked = c.calls['auto_group']('Even strength')
    q = host.snap('question')
    assert asked == {'ok': True, 'asked': q['id']} and q['title'] == 'Deal all lines again?'
    assert [b['answer'] for b in q['buttons']] == ['deal', 'cancel'] and not host.snap('lines')['touched']
    c.calls['answer'](q['id'], 'deal')
    v = host.snap('lines')
    assert v['problems'] == [] and v['dressed'] == 20 and v['touched'] and c.session.history == []
    assert c.status['text'] == 'Every line is dealt again by ratings. Check it, then Apply.'
    for page in labels.LINE_SECTIONS:                   # every other page deals at once, from the players who dress
        if page != 'Even strength':
            assert c.calls['lines_section'](page) == {'ok': True}
            assert c.calls['auto_group']() == {'ok': True}, page
            v = host.snap('lines')
            assert v['problems'] == [] and v['auto_label'] == f'Deal the {page.lower()} again', page
    assert c.calls['lines_apply']() == {'ok': True} and errors(c) == []
    assert c.calls['lines_undo']() == {'ok': True} and c.session.db.to_bytes() == before

    # the answer comes after the rail moved: nothing is dealt
    c.calls['lines_section']('Even strength')
    asked = c.calls['auto_group']()
    c.pick_team(FLA)
    c.calls['answer'](asked['asked'], 'deal')
    assert not c.parts['lines'].dirty(FLA) and not c.parts['lines'].dirty(EDM)
    c.calls['lines_section']('Letters')
    assert c.calls['auto_group']() == {'error': 'Pick a page with places first.'}
    assert c.session.db.to_bytes() == before


@pytest.mark.game
def test_lines_why_cards_and_the_rail_number(app):
    c, host = app
    c.tab('lines')
    for team, why in ((FA, LC.FREE_AGENTS), (SEATTLE, LC.SEATTLE_CUSTOM),
                      (MASCOTS_EAST, LC.SHORT.format('2 goalies, 13 skaters'))):
        c.pick_team(team)
        v = host.snap('lines')
        assert (v['id'], v['why'], v['tip']) == (team, why, LC.WHY_TIP), team
        assert 'units' not in v
        json.dumps(v)
        for name, args in (('set_slot', ('l1c', None)), ('set_captain', (1, 0)), ('auto_group', ('Power play',)),
                           ('lines_apply', ()), ('lines_undo', ())):
            assert c.calls[name](*args) == {'error': LC.NO_TEAM}, (team, name)
    assert c.parts['lines'].rail_number({'id': FA}) is None                 # free agents: the player count
    assert c.parts['lines'].rail_number({'id': SEATTLE}) is None
    assert c.parts['lines'].rail_number({'id': MASCOTS_EAST})['tip'] == 'dressed'
    c.pick_team(EDM)
    rows = host.snap('rail')['rows']
    assert all(r['number']['tip'] == 'dressed' and r['number']['text'] == '20' for r in rows if not r['extra'])
    assert c.snap_lines()['ready'] and c.parts['lines'].why(c.session, EDM) == ''


# --- Strategy -------------------------------------------------------------------------------------------------------
@pytest.mark.game
def test_strategy_draft_waits_for_apply(app):
    c, host = app
    c.tab('strategy')
    sp = c.parts['strategy']
    before = c.session.db.to_bytes()
    v = host.snap('strategy')
    assert v['why'] is None and v['id'] == EDM == v['team'] and v['title'] == 'Edmonton Oilers: strategies'
    assert v['note'] == SC.NOTE and [x['title'] for x in v['sections']] == [t for t, _rows in SC.SECTIONS]
    rows = shown(v)
    assert len(rows) == len(S.FIELDS) - len(SC.HIDDEN) and not set(rows) & set(SC.HIDDEN)
    assert rows['oz_forecheck']['options'][1] == {'value': 1, 'label': '2-3'}
    assert (rows['forward1_bias1']['left'], rows['forward1_bias1']['right']) == ('Carry', 'Dump')
    assert (v['can_defaults'], v['defaults_why']) == (False, SC.SAME_AS_GAME)
    assert not (v['touched'] or v['can_apply'] or v['mine'] or v['can_undo']) and v['problems'] == []
    json.dumps(v)

    field = 'forward1_bias1'
    old = rows[field]['value']
    new = 0 if old else 1
    assert c.calls['strategy_set'](field, 11) == {'error': 'Pick a value from 0 to 10.'}
    assert c.calls['strategy_set'](field, 'x') == {'error': 'Pick a value from 0 to 10.'}
    assert c.calls['strategy_set']('nope', 1) == {'error': 'There is no such strategy.'}
    assert c.calls['strategy_set'](field, str(new)) == {'ok': True}          # the page may send text
    v = host.snap('strategy')
    assert shown(v)[field]['value'] == new and shown(v)[field]['changed'] and v['touched'] and v['can_apply']
    assert v['can_defaults'] and v['defaults_why'] == ''
    assert c.session.history == [] and c.session.db.to_bytes() == before        # nothing written yet
    assert sp.dirty(EDM) and sp.drafts() == 'Strategies not applied yet: EDM.' and rail_row(host, EDM)['dirty']
    c.pick_team(FLA)
    assert host.snap('strategy')['id'] == FLA and not host.snap('strategy')['touched']
    c.pick_team(EDM)
    assert host.snap('strategy')['touched']

    assert c.calls['strategy_apply']() == {'ok': True}
    (ch,) = c.session.history
    assert (ch.tab, ch.team, ch.label) == ('Strategy', EDM, f'Carry or Dump on forward line 1: {new}')
    assert ('EDM strategy: Carry or Dump on forward line 1', str(old), str(new)) in ch.details
    assert S.read(c.session.db, EDM)[field] == new
    v = host.snap('strategy')
    assert (v['note'], v['note_tone']) == (SC.APPLIED, 'good') and v['mine'] and v['can_undo'] and not v['touched']
    assert sp.drafts() == ''
    assert c.calls['strategy_apply']() == {'error': 'Nothing to apply: change a strategy first.'}

    # Game defaults: NHL 19's own values come back into the draft (not the roster)
    assert c.calls['strategy_reset']() == {'ok': True}
    assert c.status['text'] == "The game's own strategies are in. Check them, then Apply."
    v = host.snap('strategy')
    assert shown(v)[field]['value'] == old and v['touched'] and S.read(c.session.db, EDM)[field] == new

    # Take back my strategies: the draft and the applied change both go
    assert c.calls['strategy_undo']() == {'ok': True}
    assert c.session.history == [] and c.session.db.to_bytes() == before
    assert c.status['text'] == "Your strategies are taken back. The team plays the roster's strategies again."
    assert c.calls['strategy_reset']() == {'ok': False} and c.status['text'] == SC.SAME_AS_GAME
    assert c.calls['strategy_undo']() == {'ok': False}


@pytest.mark.game
def test_strategy_hidden_and_bad_values_seattle_and_free_agents(app):
    c, host = app
    c.tab('strategy')
    s = c.session
    before = s.db.to_bytes()
    assert c.calls['strategy_show_hidden'](True) == {'ok': True}
    v = host.snap('strategy')
    assert v['show_hidden'] and len(shown(v)) == len(S.FIELDS) and shown(v)['team_bias2']['hidden']
    assert settings.load().get('strategy_hidden') is True                   # kept in the (throwaway) home
    c.calls['strategy_show_hidden'](False)
    assert len(shown(host.snap('strategy'))) == len(S.FIELDS) - len(SC.HIDDEN)

    # a value the game does not use (written by another tool) shows even while hidden, and Apply waits for it
    table, row = S.locate(s.db, EDM)
    bad, _ = s.edit('Bad value', lambda setter: setter(table.name, row, 'forward2_bias2', 13))
    bad.tab, bad.team = 'Roster', EDM
    v = host.snap('strategy')
    assert shown(v)['forward2_bias2']['bad'] and v['problems'] == [
        "Line 2 tendency 2 holds 13, but the game's values go from 0 to 10."]
    assert c.calls['strategy_set']('oz_forecheck', 3) == {'ok': True}
    v = host.snap('strategy')
    assert v['touched'] and not v['can_apply'] and v['can_defaults']
    assert c.calls['strategy_apply']() == {
        'error': "Line 2 tendency 2 holds 13, but the game's values go from 0 to 10. Pick a value, then Apply."}
    assert c.calls['strategy_reset']() == {'ok': True}
    v = host.snap('strategy')
    assert v['problems'] == [] and 'forward2_bias2' not in shown(v) and v['can_apply']
    assert c.calls['strategy_apply']() == {'ok': True}
    assert S.read(s.db, EDM, every=True)['forward2_bias2'] == 5 and errors(c) == []
    assert c.calls['strategy_undo']() == {'ok': True}       # dropped: the bad value's change stays
    assert [ch.label for ch in s.history] == ['Bad value']
    c.undo()
    assert s.db.to_bytes() == before

    # Game defaults puts back the values the menu does not show too (one line in the Details for them)
    extra = next(f for f in S.read(s.db, EDM, every=True) if f not in S.FIELDS)
    old = S.read(s.db, EDM, every=True)[extra]
    other, _ = s.edit('Other value', lambda setter: setter(table.name, row, extra, old ^ 1))
    other.tab, other.team = 'Roster', EDM
    v = host.snap('strategy')
    assert v['can_defaults'] and not v['touched']
    assert c.calls['strategy_reset']() == {'ok': True} and host.snap('strategy')['touched']
    assert c.calls['strategy_apply']() == {'ok': True}
    assert s.history[-1].label == '1 strategy changed' and s.history[-1].details == [
        ('EDM strategy: 1 value the menu does not show', "the roster's", "the game's own")]
    assert S.read(s.db, EDM, every=True)[extra] == old
    assert c.calls['strategy_undo']() == {'ok': True}
    c.undo()
    assert s.db.to_bytes() == before

    # Seattle: the rail's 399 is the strategies table's 499 (the game's custom team)
    c.pick_team(SEATTLE)
    v = host.snap('strategy')
    assert (v['id'], v['team'], v['why']) == (S.FIRST_CUSTOM + 99, SEATTLE, None)
    old = shown(v)['oz_forecheck']['value']
    new = 0 if old else 1
    assert c.calls['strategy_set']('oz_forecheck', new) == {'ok': True}
    beta1 = c.snap_strategy()                                                # beta1's snapshot shows the draft
    assert beta1['team'] == 499 and beta1['values']['oz_forecheck'] == new
    assert c.calls['strategy_apply']() == {'ok': True}
    assert S.read(s.db, 499)['oz_forecheck'] == new and s.history[-1].team == SEATTLE
    assert c.calls['strategy_undo']() == {'ok': True} and s.db.to_bytes() == before

    # free agents and no team: the Why card with the tab's tip; the calls refuse
    c.pick_team(FA)
    v = host.snap('strategy')
    assert (v['why'], v['tip']) == (SC.FREE_AGENTS, SC.WHY_TIP) and 'sections' not in v
    assert c.calls['strategy_set']('oz_forecheck', 1) == {'error': SC.NO_TEAM}
    assert c.calls['strategy_apply']() == {'error': SC.NO_TEAM}
    assert c.calls['strategy_reset']() == {'error': SC.NO_TEAM}


# --- beta1's names ---------------------------------------------------------------------------------------------------
@pytest.mark.game
def test_lines_pages_through_the_controller(app):
    c, host = app
    before = c.session.db.to_bytes()
    lines = c.snap_lines()
    assert lines['ready'] and lines['page'] == 'Even strength' and lines['problems'] == []
    assert lines['pages'] == list(labels.LINE_SECTIONS) + ['Letters']
    assert sum(p['dressed'] for p in lines['players']) == 20
    json.dumps(lines)

    c.lines_section('Power play')
    lines = c.snap_lines()
    assert lines['page'] == 'Power play'
    slots = {s['slot']: s for g in lines['groups'] if g['section'] == 'Power play'
             for u in g['units'] for s in u['slots']}
    a, b = slots['pp1c']['holders'][0], slots['pp2c']['holders'][0]
    assert any(p['id'] == a and 'PP1 C' in p['where'] for p in lines['players'])
    assert c.set_slot('pp2c', a) == {'ok': True}
    draft = {s['slot']: s['holders'] for g in c.snap_lines()['groups'] for u in g['units'] for s in u['slots']}
    assert draft['pp2c'] == [a] and draft['pp1c'] == [b]                     # the snapshot shows the draft
    assert c.session.slot_holders(EDM)['pp2c'] == [b]                         # the roster waits for Apply
    assert c.calls['lines_apply']() == {'ok': True}
    h = c.session.slot_holders(EDM)
    assert h['pp2c'] == [a] and h['pp1c'] == [b]
    scratch = next(p['id'] for p in c.snap_lines()['players'] if not p['dressed'] and not p['goalie'])
    assert 'error' in c.set_slot('pp1c', scratch)
    assert c.auto_group() == {'ok': True}
    assert c.snap_lines()['problems'] == []
    c.lines_section('Nope')
    assert c.snap_lines()['page'] == 'Power play'
    for page in labels.LINE_SECTIONS:
        c.lines_section(page)
        reply = c.auto_group()
        if page == 'Even strength':                                          # asks first
            c.calls['answer'](reply['asked'], 'deal')
        else:
            assert reply == {'ok': True}, page
        assert c.snap_lines()['problems'] == [], page
    assert c.calls['lines_apply']() == {'ok': True} and errors(c) == []
    while c.session.history:
        c.undo()
    assert c.session.db.to_bytes() == before


@pytest.mark.game
def test_group_edits_round_trip_through_the_save(game):
    session = RosterSession(game.default_db(), 'NHL 19 default roster')
    h = session.slot_holders(11)
    a, b = h['pk4_1c'][0], h['pk4_2c'][0]
    session.set_slot(11, 'pk4_2c', a)
    session.set_slot(11, 's1', h['s5'][0])
    session.set_slot(11, 'x1', None)
    scratch = next(pi for pi, d in session.dressed(11).items() if not d and session.summary(pi)['pos'] != 'G')
    gone = h['l4c'][0]
    session.set_slot(11, 'l4c', scratch)
    with pytest.raises(EditError):
        session.set_slot(11, 'ot_1c', session.players_of(12)[0])
    want = session.slot_holders(11)
    assert want['pk4_2c'] == [a] and want['pk4_1c'] == [scratch if b == gone else b] and 'x1' not in want
    assert want['l4c'] == [scratch]
    assert gone not in {p for sl, ps in want.items() if L.GROUP_OF[sl] != L.THREES for p in ps}
    assert session.lineup_problems(11) == [] and not [i for i in session.verify() if i.level == 'error']
    for target in (install.TARGET_EXPORT, install.TARGET_SAVE):
        blob = install.build_database(session, game, target).to_bytes()
        back = RosterSession(tdb.Database.parse(blob, game.schema()))
        assert back.slot_holders(11) == want, target
        assert back.dressed(11)[scratch] and not back.dressed(11)[gone]


@pytest.mark.game
def test_strategy_edit_reset_and_auto_lines(app):
    c, host = app
    before = c.session.db.to_bytes()
    st = c.snap_strategy()
    assert st['ready'] and st['values'] and len(st['sections']) == len(S.SECTIONS)
    c.strategy_team(TOR)
    assert c.team == TOR and c.snap_strategy()['team'] == TOR                # the rail follows beta1's list
    field = S.FIELDS[0]
    old = S.read(c.session.db, TOR)[field]
    new = 0 if old else 1
    assert c.strategy_set(field, new) == {'ok': True}
    assert c.snap_strategy()['values'][field] == new and S.read(c.session.db, TOR)[field] == old
    assert 'error' in c.strategy_set(field, 99)
    assert c.strategy_reset() == {'ok': True}
    assert c.snap_strategy()['values'][field] == old
    assert c.strategy_set(field, new) == {'ok': True}
    assert c.calls['strategy_apply']() == {'ok': True}
    assert S.read(c.session.db, TOR)[field] == new
    c.undo()
    assert c.session.db.to_bytes() == before
    c.strategy_team(S.FIRST_CUSTOM + 99)
    assert c.team == SEATTLE and c.snap_strategy()['name'] == 'Seattle (custom team)'

    c.pick_team(TOR)
    assert c.auto_lines() == {'ok': True}
    assert c.calls['lines_apply']() == {'ok': True}
    assert errors(c) == []
    c.undo()
    assert c.session.db.to_bytes() == before
