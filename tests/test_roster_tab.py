"""The Roster tab through the Controller the way the page drives it (docs/ui/roster.md): the list and the card, every
wrong field at once, one change per Apply, each player's own Undo, typed values kept for later, and the Face & type
and Equipment windows (picks held until Apply, Take back per player). The game's own roster, nothing written."""
import pytest

from overtime_core import equipment as EQ, faces as F
from overtime_roster.app import controller as C, jobs, roster_card as RC, sources

from test_editors_app import Host

TEAM = 11   # Edmonton

pytestmark = pytest.mark.game


@pytest.fixture
def app(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))

    def inline(work, done=None, failed=None, expected=()):
        try:
            out = work()
        except expected as err:
            return failed and failed(str(err))
        return done and done(out)
    monkeypatch.setattr(jobs, 'run', inline)
    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    c.load_source(sources.GAME_ID)
    c.tab('roster')
    c.pick_team(TEAM)
    return c


def snap(c, name):
    return c.host.snap(name)


def skaters(c):
    s = c.session
    return [p for p in s.players_of(TEAM) if s.bio(p)[1]['position'] != F.GOALIE]


def raw(c):
    """The roster's tables as bytes (an Undo puts back exactly what was there)."""
    s = c.session
    return {t: bytes(s.db[t].data) for t in ('exhibitionplayerbiotable', 'exhibitionrostertable', 'exhibitionskaterai',
                                             EQ.SKATER_TABLE)}


def test_the_list_and_the_card(app):
    c = app
    r = snap(c, 'roster')
    assert r['loaded'] and r['team']['id'] == TEAM and r['count'].endswith('players')
    order = [RC.POS_ORDER[x['pos']] for x in r['rows']]
    assert order == sorted(order)                          # C, LW, RW, D, G
    assert r['selected'] == r['rows'][0]['id'] == c.player  # the rail picked the team: its first player
    card = snap(c, 'roster_card')
    assert card['id'] == c.player and card['problems'] == [] and card['typed'] is None
    assert set(card['values']) >= {'first', 'last', 'num', 'pos', 'shoots', 'captain', 'born', 'country', 'height',
                                   'weight', 'salary', 'years', 'ratings'}
    assert card['summary'][0]['label'] == 'Overall' and card['rating_groups'] and len(card['gear']) == 4
    assert card['choices']['positions'] == ['C', 'LW', 'RW', 'D'] and not card['can_undo']
    assert snap(c, 'roster_face') == {'open': False} and snap(c, 'roster_gear') == {'open': False}


def test_search_finds_every_league_without_accents(app):
    c = app
    s = c.session
    pi = skaters(c)[0]
    last = s.bio(pi)[1]['lastname']
    c.calls['roster_search'](RC.plain(last).upper())
    r = snap(c, 'roster')
    assert r['searching'] and pi in [x['id'] for x in r['rows']] and r['rows'][0]['team']
    assert c.player in [x['id'] for x in r['rows']]
    c.calls['roster_search']('zzzzqq')
    assert snap(c, 'roster')['rows'] == []
    c.calls['roster_search']('')
    assert not snap(c, 'roster')['searching']


def test_a_refused_apply_names_every_wrong_field_and_changes_nothing(app):
    c = app
    a, b = skaters(c)[:2]
    c.calls['roster_player'](a, None)
    taken = snap(c, 'roster_card')['values']['num']
    c.calls['roster_player'](b, None)
    assert c.calls['roster_apply']({'num': taken})['ok']        # a teammate's number: the game shows both
    assert c.calls['roster_undo']('applied')['ok']
    before, n = raw(c), len(c.session.history)
    reply = c.calls['roster_apply']({'num': 0, 'height': 250, 'born': '1997-13-40', 'last': ''})
    assert reply['ok'] is False
    keys = [p['key'] for p in reply['problems']]
    assert keys == ['last', 'num', 'born', 'height']
    assert reply['problems'][1]['text'] == 'Numbers go from 1 to 99.'
    assert raw(c) == before and len(c.session.history) == n
    card = snap(c, 'roster_card')
    assert card['typed']['height'] == 250 and [p['key'] for p in card['problems']] == keys
    c.calls['roster_undo']('typed')
    card = snap(c, 'roster_card')
    assert card['typed'] is None and card['problems'] == []


def test_apply_is_one_change_and_undo_takes_back_his_own(app):
    c = app
    a, b = skaters(c)[:2]
    start = raw(c)
    c.calls['roster_player'](a, None)
    va = snap(c, 'roster_card')['values']
    used = {x['num'] for x in snap(c, 'roster')['rows']}
    free = next(n for n in range(1, 100) if n not in used)
    rating = next(iter(va['ratings']))
    reply = c.calls['roster_apply']({**va, 'num': free, 'ratings': {**va['ratings'], rating: min(99, va['ratings'][rating] + 3)}})
    assert reply == {'ok': True, 'changes': 2} and len(c.session.history) == 1
    card = snap(c, 'roster_card')
    assert card['values']['num'] == free and set(card['edited']) == {'num', f'ratings.{rating}'} and card['can_undo']
    row = next(x for x in snap(c, 'roster')['rows'] if x['id'] == a)
    assert row['tag'] == 'edited' and row['note'] == 'Edited: number, a rating'
    ch = c.session.history[-1]
    assert ch.tab == 'Roster' and ch.team == TEAM and str(free) in ch.label

    # a pick of another player applies the old card first
    c.calls['roster_player'](b, {'id': a, 'values': {'height': va['height'] + 3}})
    assert c.player == b and len(c.session.history) == 2
    vb = snap(c, 'roster_card')['values']
    assert c.calls['roster_apply']({'weight': vb['weight'] + 2}) == {'ok': True, 'changes': 1}
    # Undo my edit on a: his newest (the height), not the roster's newest (b's weight)
    c.calls['roster_player'](a, None)
    assert c.calls['roster_undo']('applied') == {'ok': True}
    assert snap(c, 'roster_card')['values']['height'] == va['height'] and len(c.session.history) == 2
    assert c.calls['roster_undo']('applied') == {'ok': True}
    assert snap(c, 'roster_card')['values']['num'] == va['num'] and not snap(c, 'roster_card')['can_undo']
    assert c.calls['roster_undo']('applied') == {'ok': False}
    c.calls['roster_player'](b, None)
    assert c.calls['roster_undo']('applied') == {'ok': True}
    assert raw(c) == start and c.session.history == []


def test_typed_values_kept_for_later(app):
    c = app
    a, b = skaters(c)[:2]
    c.calls['roster_player'](a, None)
    va = snap(c, 'roster_card')['values']
    assert c.calls['roster_keep'](a, {**va, 'weight': va['weight'] + 3}) == {'ok': True, 'kept': True}
    c.calls['roster_player'](b, None)
    part = c.parts['roster']
    with c.lock:
        assert part.dirty(TEAM) and not part.dirty(TEAM + 1)
    assert 'the card of' in part.drafts()
    c.calls['roster_player'](a, None)
    assert snap(c, 'roster_card')['typed']['weight'] == va['weight'] + 3
    assert c.calls['roster_keep'](a, va) == {'ok': True, 'kept': False}      # the same as his card: nothing kept
    assert part.drafts() == '' and c.session.history == []


def test_face_and_type_window(app):
    c = app
    a, b = skaters(c)[:2]
    start = raw(c)
    c.calls['roster_player'](a, None)
    assert c.calls['roster_face_open']() == {'ok': True}
    f = snap(c, 'roster_face')
    assert f['open'] and f['id'] == a and f['found_title'] == 'His teammates' and f['found']
    assert not f['can_apply'] and len(f['type']['choices']) in (4, 6)
    other = next(t['value'] for t in f['type']['choices'] if t['value'] != f['type']['current'])
    hair = next(h for h in f['parts']['hair'] if h != f['current']['hair'])
    assert c.calls['roster_face_type'](other) == {'ok': True}
    assert c.calls['roster_face_pick']('hair', hair) == {'ok': True}
    assert c.calls['roster_face_pick']('skin', 99) == {'ok': False}
    assert c.calls['roster_face_type'](0)['ok'] is False                     # a goalie's type
    f = snap(c, 'roster_face')
    assert f['can_apply'] and f['changed'] == ['hair'] and f['type']['changed']
    assert snap(c, 'roster_card')['waiting'] == ['Face & type'] and c.session.history == []
    assert 'Face & type of' in c.parts['roster'].drafts()
    c.calls['roster_face_close']()
    assert snap(c, 'roster_face') == {'open': False} and a in c.parts['faces'].picks   # closing keeps the picks
    c.calls['roster_face_open']()
    assert c.calls['roster_face_apply']() == {'ok': True} and len(c.session.history) == 1
    card = snap(c, 'roster_card')
    assert card['type']['value'] == other and set(card['edited']) == {'type', 'face'} and card['waiting'] == []
    assert F.read(c.session.bio(a)[1])['hair'] == hair
    c.calls['roster_face_search'](c.session.bio(b)[1]['lastname'])
    f = snap(c, 'roster_face')
    assert b in [x['id'] for x in f['found']] and f['found_title'].endswith('found')
    assert c.calls['roster_face_copy'](b) == {'ok': True}
    assert snap(c, 'roster_face')['from'] == c.session.name(c.session.bio(b)[1])
    assert c.calls['roster_face_undo']() == {'ok': True, 'taken': 1}
    assert raw(c) == start and c.parts['faces'].picks == {} and c.session.history == []


def test_equipment_window_for_him_and_the_team(app):
    c = app
    s = c.session
    a = skaters(c)[0]
    start = raw(c)
    c.calls['roster_player'](a, None)
    assert c.calls['roster_gear_open']() == {'ok': True}
    g = snap(c, 'roster_gear')
    assert g['open'] and g['kind'] == 'skater' and {r['key'] for r in g['rows']} == set(EQ.SKATER)
    assert '#FFFFFF' in g['swatches'] and not g['can_apply'] and not g['can_team']
    rows = {r['key']: r for r in g['rows']}
    assert rows['blade_tape']['show'] == 'colour' and rows['stick']['show'] == 'grid'
    tuck = next(n for n, _l in rows['jersey_tuck']['options'] if n != rows['jersey_tuck']['current'])
    assert c.calls['roster_gear_pick']('jersey_tuck', tuck) == {'ok': True}
    assert c.calls['roster_gear_pick']('blade_tape', '00ff00') == {'ok': True}
    assert c.calls['roster_gear_pick']('gloves', 4242) == {'ok': False}
    assert c.calls['roster_gear_pick']('shaft_tape', 'red') == {'ok': False}
    g = snap(c, 'roster_gear')
    assert g['can_apply'] and g['can_team'] and 'EDM' in g['team_label']
    assert {r['key'] for r in g['rows'] if r['changed']} == {'jersey_tuck', 'blade_tape'}
    reply = c.calls['roster_gear_apply'](True)
    assert reply['ok'] and reply['players'] > 1 and len(s.history) == 1
    for m in skaters(c):
        row = EQ.row_of(s.db, s.bio(m)[1]['game_id'])
        if row is not None:
            assert EQ.read(s.db, row)['jersey_tuck'] == tuck
    me = EQ.read(s.db, EQ.row_of(s.db, s.bio(a)[1]['game_id']))
    assert me['blade_tape'] == 0x00FF00
    assert 'gear' in snap(c, 'roster_card')['edited']
    assert c.calls['roster_gear_undo']() == {'ok': True, 'taken': 1}
    assert raw(c) == start and s.history == []


def test_leaving_the_tab_closes_the_windows_and_save_applies_the_card(app, monkeypatch):
    c = app
    monkeypatch.setattr(c.parts['save'], 'write', lambda then=None: None)   # nothing is written
    a = skaters(c)[0]
    c.calls['roster_player'](a, None)
    c.calls['roster_face_open']()
    c.calls['roster_gear_open']()
    c.tab('lines')
    assert snap(c, 'roster_face') == {'open': False} and snap(c, 'roster_gear') == {'open': False}
    c.tab('roster')
    assert c.player == a                                     # the same team again keeps the pick
    v = snap(c, 'roster_card')['values']
    c.parts['save'].save({'id': a, 'values': {**v, 'height': v['height'] + 3}})
    assert snap(c, 'roster_card')['values']['height'] != v['height']
