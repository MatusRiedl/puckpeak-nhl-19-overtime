"""The Jerseys & gear tab's team gear (palette, recolour, copy, sticks) driven through the Controller the way the page
does. Beta1's calls (EditorsController.gear_*) write at once: each edit one Undo, refused values leave the roster alone,
and a recolour goes through the roster save path. The tab's calls (docs/ui/jerseys.md) work on a draft per team that
Apply writes as one change and "Take back my gear" takes back out of the roster."""
import pytest

from overtime_core import equipment as EQ, tdb
from overtime_roster.app import controller as C, install, jerseys_ctl as J, jobs, sources

TEAM = 11


class Host:
    def __init__(self):
        self.snaps, self.lines, self.seen = {}, [], []

    def register(self, name, fn):
        self.snaps[name] = fn

    def changed(self, *names):
        self.seen.append(names)

    def log(self, msg):
        self.lines.append(msg)

    def send(self, *a):
        pass

    def snap(self, name):
        return self.snaps[name]()


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
    c.pick_team(TEAM)
    return c, c.host


@pytest.mark.game
def test_team_gear_tab(app):
    c, host = app
    s = c.session
    t = c.editors.snap_equipment()['team']
    assert t['id'] == TEAM and t['rows'] and t['palette'] and len(t['colours']) == 3
    assert c.editors.gear_propose()['count'] == 0          # the game's colours: nothing to move
    T = s.db[EQ.TEAMS]
    row = next(i for i in range(T.count) if T.get(i, 'index') == TEAM)
    T.set(row, EQ.TEAM_COLOURS[0], 0x010101)               # as a colour edit would
    T.set(row, EQ.TEAM_COLOURS[1], 0x6CACE4)
    c.editors.gear_propose()
    prop = c.editors.snap_equipment()['team']['proposal']
    if prop:
        assert c.editors.gear_recolour(dict(prop)) == {'ok': True}
        pal = {x for x, _ in c.editors.snap_equipment()['team']['palette']}
        assert not {a for a, _ in prop} & pal
        c.undo()
        assert {x for x, _ in c.editors.snap_equipment()['team']['palette']} == {x for x, _ in t['palette']}
    first = t['palette'][0][0]
    assert c.editors.gear_recolour({first: '#123456'}) == {'ok': True}
    assert '#123456' in {x for x, _ in c.editors.snap_equipment()['team']['palette']}
    assert 'error' in c.editors.gear_recolour({'#zz': '#000000'})
    src = c.editors.snap_equipment()['teams'][0]['id']
    assert c.editors.gear_copy(src) == {'ok': True}
    assert c.editors.snap_equipment()['team']['palette'] == [[EQ_hex, n] for EQ_hex, n in
                                                          [(f'#{x:06x}', k) for x, k in EQ.palette(s.db, src)]]
    assert 'error' in c.editors.gear_copy(TEAM)
    c.undo()
    assert c.editors.snap_equipment()['team']['rows'] == t['rows']
    sticks = c.editors.snap_equipment()['team']['sticks']
    assert c.editors.gear_sticks() == {'ok': True}
    assert c.editors.snap_equipment()['team']['sticks'] == [] or not sticks


@pytest.mark.game
def test_team_gear_round_trips_through_the_save(app):
    c, host = app
    s, game = c.session, c.game
    first = c.editors.snap_equipment()['team']['palette'][0][0]
    assert c.editors.gear_recolour({first: '#123456'}) == {'ok': True}
    for target in (install.TARGET_EXPORT, install.TARGET_SAVE):
        db = tdb.Database.parse(install.build_database(s, game, target).to_bytes(), game.schema())
        assert 0x123456 in {x for x, _ in EQ.palette(db, TEAM)}, target


# --- the tab: a draft per team, Apply, Take back ----------------------------------------------------------------------
SEATTLE, SEATTLE_GEAR = 399, 499


@pytest.fixture
def tab(app):
    """The Jerseys & gear tab in view on Edmonton; the reads a pick waits for run when the test calls run()."""
    c, host = app
    part = c.parts['jerseys']
    waiting = []
    part.later = lambda delay, fn: waiting.append((delay, fn))

    def run():
        while waiting:
            waiting.pop(0)[1]()
    c.shell.tab('jerseys')
    run()
    return c, part, run, waiting


def view(c):
    return c.host.snaps['jerseys']()


def palette(db, team, table=EQ.STOCK):
    return EQ.palette(db, team, table)


def colours_of(v):
    return [(int(r['from'], 16), r['zones']) for r in v['palette']]


@pytest.mark.game
def test_no_roster_says_pick_one(game_dir, tmp_path, monkeypatch):
    monkeypatch.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    c = C.Controller(Host(), game_dir=game_dir, save_dir=str(tmp_path / 'saves'))
    v = c.parts['jerseys'].view()
    assert v['why'] == 'Pick a roster in Setup first.' and v['tip'] == 'Pick a roster in Setup first.'
    assert c.parts['jerseys'].drafts() == '' and 'error' in c.parts['jerseys'].recolour({'000000': '111111'})


@pytest.mark.game
def test_edmonton_gear(tab):
    c, part, run, _waiting = tab
    s = c.session
    v = view(c)
    assert v['why'] is None and v['team'] == TEAM and v['id'] == TEAM and v['table'] == 'stock'
    assert v['title'] == 'Edmonton Oilers: jerseys and gear' and v['note'] == J.NOTE and v['note_tone'] == ''
    assert v['rows'] == len(EQ.gear_rows(s.db, TEAM, categories=EQ.GEAR))
    assert colours_of(v) == palette(s.db, TEAM)
    assert all(r['to'] == r['from'] and not r['changed'] and r['pieces'] for r in v['palette'])
    names = [p['name'] for p in v['pieces']]
    assert names == [n for _c, n in J.PIECES if n in names] and names[0] == 'Helmet'
    assert v['colours']['now'] == [J.hx(x) for x in EQ.team_colours(s.db, TEAM)]
    assert v['colours']['game'] == v['colours']['now'] and not v['colours']['can_propose']   # the game's own roster
    assert v['colours']['note'] == J.SAME
    options = {o['value']: o for o in v['copy']['options']}
    assert TEAM not in options and options[0]['label'] == 'Anaheim Ducks' and not options[0].get('disabled')
    k = v['sticks']
    assert k['count'] == len(k['rows']) == len(part.sticks_of(TEAM)) and not k['fitted']
    assert k['nhl_count'] >= k['count'] and k['nhl_teams'] >= 1
    assert not v['touched'] and not v['can_apply'] and not v['can_undo'] and not v['mine']
    assert part.apply() == {'ok': False} and c.status['text'] == J.NOTHING
    assert part.take_back() == {'ok': False} and not s.history


@pytest.mark.game
def test_a_pick_is_read_later_and_a_stale_read_is_dropped(tab):
    c, part, run, waiting = tab
    c.rail.pick_team(28)
    v = view(c)
    assert v['loading'] and v['why'] == J.READING and v['team'] == 28
    assert waiting[-1][0] == J.LOAD_DELAY == 0.25
    assert part.recolour({'E7E7E7': '000000'}) == {'error': J.WAIT}
    c.rail.pick_team(0)
    waiting.pop(0)[1]()                     # the read for Vancouver: the rail left it
    assert view(c)['loading']
    run()
    v = view(c)
    assert not v.get('loading') and v['team'] == 0 and v['why'] is None
    c.shell.tab('roster')                   # hidden: the rail moves, the tab keeps what it drew
    c.rail.pick_team(28)
    assert not waiting and view(c)['team'] == 0
    c.shell.tab('jerseys')
    assert view(c)['loading']
    run()
    assert view(c)['team'] == 28
    c.shell.tab('roster')
    c.shell.tab('jerseys')                  # the same team again: nothing to read
    assert not waiting and not view(c).get('loading')


@pytest.mark.game
def test_free_agents_have_no_gear(tab):
    c, part, run, _waiting = tab
    c.rail.pick_team(-1)
    run()
    v = view(c)
    assert v['why'] == J.FREE_AGENTS and v['tip'].startswith('Pick a team in the list.')
    assert part.recolour({'E7E7E7': '000000'}) == {'error': J.FREE_AGENTS}


@pytest.mark.game
def test_a_recolour_waits_in_the_draft(tab):
    c, part, run, _waiting = tab
    s = c.session
    was = palette(s.db, TEAM)
    first = view(c)['palette'][0]['from']
    assert part.recolour({first: '123456'}) == {'ok': True}
    assert palette(s.db, TEAM) == was and not s.history          # nothing written yet
    v = view(c)
    row = v['palette'][0]
    assert row['changed'] and row['to'] == '123456' and row['from'] == first
    assert any(x['hex'] == '123456' for p in v['pieces'] for x in p['colours'])
    assert v['touched'] and v['can_apply'] and v['can_undo'] and not v['mine']
    assert part.dirty(TEAM) and not part.dirty(28)
    assert part.drafts() == 'Gear not applied yet: EDM.'
    assert next(r for r in c.rail.view()['rows'] if r['id'] == TEAM)['dirty']
    assert part.recolour({'ABCDEF': '000000'}) == {'ok': True}       # a colour the gear does not wear
    assert len(part.draft(TEAM)['map']) == 1
    assert part.recolour({'#zz': '000000'}) == {'error': J.NOT_A_COLOUR}
    assert part.recolour('E7E7E7') == {'error': J.NOT_A_COLOUR}
    c.rail.pick_team(28)                                               # the draft stays with its team
    run()
    assert not view(c)['touched'] and part.dirty(TEAM)
    c.rail.pick_team(TEAM)
    run()
    assert view(c)['palette'][0]['to'] == '123456'
    assert part.recolour({first: first}) == {'ok': True}              # Back
    assert not part.dirty(TEAM) and part.drafts() == '' and not view(c)['touched']
    part.recolour({first: '123456'})
    assert part.take_back() == {'ok': True} and not part.dirty(TEAM) and not s.history
    assert c.status['text'] == 'Your changes are dropped.'


@pytest.mark.game
def test_apply_is_one_change_and_take_back_drops_it(tab):
    c, part, run, _waiting = tab
    s = c.session
    was, sticks = palette(s.db, TEAM), part.sticks_of(TEAM)
    first = view(c)['palette'][0]['from']
    part.recolour({first: '123456'})
    if sticks:
        assert part.sticks(False) == {'ok': True} and view(c)['sticks']['fitted']
    assert part.apply() == {'ok': True}
    assert len(s.history) == 1
    ch = s.history[0]
    assert ch.tab == 'Jerseys & gear' and ch.team == TEAM and ch.kept is None
    assert ch.label.startswith(f'Gear colour {first} to 123456') or ch.label.startswith('1 gear colour')
    assert 0x123456 in dict(palette(s.db, TEAM)) and int(first, 16) not in dict(palette(s.db, TEAM))
    assert EQ.team_sticks(s.db, [TEAM], setter=lambda *a: None) == []
    v = view(c)
    assert v['note'] == J.APPLIED and v['note_tone'] == 'good' and v['mine'] and v['can_undo'] and not v['touched']
    assert not part.dirty(TEAM) and TEAM in c.parts['save'].teams()
    assert c.status['text'] == 'Edmonton Oilers: gear applied. Save the roster to keep it.'
    assert part.take_back() == {'ok': True}
    assert not s.history and palette(s.db, TEAM) == was
    assert EQ.team_sticks(s.db, [TEAM], setter=lambda *a: None) == sticks
    v = view(c)
    assert not v['mine'] and not v['can_undo'] and v['note'] == J.NOTE


@pytest.mark.game
def test_take_back_after_another_edit_puts_the_gear_back(tab):
    c, part, run, _waiting = tab
    s = c.session
    was = palette(s.db, TEAM)
    first = view(c)['palette'][0]['from']
    part.recolour({first: '123456'})
    part.apply()
    row = EQ.gear_rows(s.db, TEAM, categories=EQ.GEAR)[0]
    other, _ = s.edit('Another edit', lambda setter: setter(EQ.STOCK, row, 'zone2', 0x111111))
    other.tab, other.team = 'Roster', TEAM
    assert part.take_back() == {'ok': True}
    assert len(s.history) == 3 and s.history[-1].kept is not None and s.history[-1].team == TEAM
    assert palette(s.db, TEAM) == was and not part.mine(TEAM) and not view(c)['mine']
    c.undo()                                   # My edits takes the take-back back: the gear is the team's again
    assert part.mine(TEAM) and view(c)['mine']


@pytest.mark.game
def test_copy_another_teams_gear(tab):
    c, part, run, _waiting = tab
    s = c.session
    was, theirs = palette(s.db, TEAM), palette(s.db, 0)
    rows = len(EQ.gear_rows(s.db, TEAM, categories=EQ.GEAR))
    assert 'error' in part.copy('Anaheim')
    assert part.copy(0) == {'ok': True}
    v = view(c)
    assert v['copy']['from'] == 0 and v['copy']['from_name'] == 'Anaheim Ducks' and v['touched']
    assert colours_of(v) == theirs and v['rows'] == len(EQ.gear_rows(s.db, 0, categories=EQ.GEAR))
    assert v['colours']['note'] == "Copying another team's gear: recolour it in Gear colours."
    assert v['copy']['note'].startswith("Takes Anaheim Ducks' helmets")
    assert part.drafts() == 'Gear not applied yet: EDM.' and palette(s.db, TEAM) == was
    a = v['palette'][0]['from']
    part.recolour({a: '123456'})
    assert part.apply() == {'ok': True}
    ch = s.history[-1]
    assert ch.kept is not None and ch.label == "Anaheim Ducks' gear copied, 1 gear colour changed"
    assert palette(s.db, TEAM) == J.laid_over(theirs, {int(a, 16): 0x123456})
    assert view(c)['copy']['from'] is None and view(c)['mine']
    assert part.take_back() == {'ok': True}
    assert not s.history and palette(s.db, TEAM) == was
    assert len(EQ.gear_rows(s.db, TEAM, categories=EQ.GEAR)) == rows
    part.copy(0)
    assert part.copy(None) == {'ok': True} and not part.dirty(TEAM)     # back to the team's own gear


@pytest.mark.game
def test_seattle_gear_is_the_custom_team_and_its_play_now_copy(tab):
    c, part, run, _waiting = tab
    s = c.session
    if EQ.CUSTOM not in s.db or not EQ.gear_rows(s.db, SEATTLE_GEAR, EQ.CUSTOM, EQ.GEAR):
        pytest.skip('this roster has no Seattle gear')
    refused = part.copy(SEATTLE)
    assert refused['error'] == "Seattle Kraken's gear is kept apart from the other teams' gear, so Edmonton Oilers " \
                               'cannot take it yet. Pick another team.'
    assert view(c)['copy']['error'] == refused['error']
    c.rail.pick_team(SEATTLE)
    run()
    v = view(c)
    assert v['id'] == SEATTLE_GEAR and v['team'] == SEATTLE and v['table'] == 'custom'
    assert colours_of(v) == palette(s.db, SEATTLE_GEAR, EQ.CUSTOM)
    assert v['copy']['options'] and all(o.get('disabled') and o['label'].endswith('(kept apart)')
                                        for o in v['copy']['options'])
    assert v['copy']['note'].startswith("Seattle Kraken's gear is kept apart")
    assert part.copy(0)['error'].startswith("Seattle Kraken's gear is kept apart")
    T = s.db[EQ.TEAMS]                                     # Seattle's colours now, as an update would set them
    row = next(i for i in range(T.count) if T.get(i, 'index') == SEATTLE)
    for f, x in zip(EQ.TEAM_COLOURS, (0x001628, 0x99D9D9, 0x355464)):
        T.set(row, f, x)
    prop = part.proposal(SEATTLE)
    v = view(c)
    if not prop:
        assert not v['colours']['can_propose']
        return
    assert v['colours']['can_propose'] and v['colours']['proposed'] == len(prop)
    assert part.propose() == {'ok': True, 'count': len(prop)}
    v = view(c)
    assert not v['colours']['can_propose'] and v['touched'] and 'when you press Apply' in v['colours']['note']
    twin = palette(s.db, SEATTLE, EQ.STOCK)
    assert part.apply() == {'ok': True}
    custom, stock = dict(palette(s.db, SEATTLE_GEAR, EQ.CUSTOM)), dict(palette(s.db, SEATTLE, EQ.STOCK))
    for a, b in prop.items():
        assert a not in custom and b in custom
        if a in dict(twin):
            assert a not in stock and b in stock
    assert part.take_back() == {'ok': True}
    assert palette(s.db, SEATTLE, EQ.STOCK) == twin and not s.history


@pytest.mark.game
def test_team_sticks_in_the_draft(tab):
    c, part, run, _waiting = tab
    team = next((t for t in part.clubs() if part.sticks_of(t)), None)
    if team is None:
        pytest.skip('every stick fits')
    c.rail.pick_team(team)
    run()
    assert part.sticks(False) == {'ok': True} and view(c)['sticks']['fitted'] and part.dirty(team)
    assert part.sticks(False) == {'ok': True} and not view(c)['sticks']['fitted'] and not part.dirty(team)
    quiet = next((t for t in part.clubs() if not part.sticks_of(t)), None)
    if quiet is not None:
        c.rail.pick_team(quiet)
        run()
        assert part.sticks(False) == {'ok': False}
        assert c.status['text'] == 'Every stick of this team matches the team colours already.'


@pytest.mark.game
def test_every_nhl_team_asks_first(tab):
    c, part, run, _waiting = tab
    s = c.session
    n, k = part.nhl_sticks()
    if not n:
        pytest.skip('every stick fits')
    assert part.sticks(True) == {'ok': True, 'asked': True}
    q = c.shell.asking
    assert q['title'] == 'Fit the sticks of every NHL team?'
    assert q['lines'][0].startswith(f'{n} stick') and f'on {k} NHL team' in q['lines'][0]
    assert [b['answer'] for b in q['buttons']] == ['fit', 'cancel']
    c.shell.answer(q['id'], 'cancel')
    assert not s.history
    part.sticks(True)
    c.shell.answer(c.shell.asking['id'], 'fit')
    assert len(s.history) == 1 and s.history[0].team is None and s.history[0].tab == 'Jerseys & gear'
    assert len(s.history[0].snaps) == n
    assert part.nhl_sticks() == (0, 0) and view(c)['sticks']['nhl_count'] == 0
    assert part.sticks(True) == {'ok': False} and c.shell.asking is None


@pytest.mark.game
def test_another_roster_drops_the_drafts(tab):
    c, part, run, _waiting = tab
    first = view(c)['palette'][0]['from']
    part.recolour({first: '123456'})
    assert part.dirty(TEAM)
    c.load_source(sources.GAME_ID)
    run()
    assert part.drafts() == '' and not part.dirty(TEAM) and not part.held
    assert not view(c).get('touched')
