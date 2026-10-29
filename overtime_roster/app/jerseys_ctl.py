"""Jerseys & gear: the rail's team's gear colours, its gear copied from another team, its sticks in the team colours.
docs/ui/jerseys.md.

Like Legacy's Jerseys & ice tab, the tab works on a draft per team ({copy, map, sticks} over the open roster): the
page's calls (gear_recolour, gear_propose, gear_copy, gear_sticks) change only the draft of the rail's team, and the
draft of a team the rail leaves is kept. Apply writes the draft into the roster as one change (the copy, then the
colours, then the sticks: My edits, the rail's dot); "Take back my gear" drops the draft and, while the team's applied
gear is not saved yet, takes it back out of the roster. Fitting the sticks of every NHL team asks first and then goes
into My edits at once (drafts are per team).

The gear tables know Seattle as the custom team 499 (Rail.map_id('jerseys')); the game's Play Now copy of it (399)
keeps the same rows in the stock table, so a recolour changes both. A team's gear is read 250 ms after the rail stops
on it; a read for a team the rail has left is dropped.

Beta1's team gear calls (EditorsController.gear_recolour, gear_propose, gear_copy, gear_sticks and the team half of
snap_equipment) are here too and still write at once, as before (re/scripts, tests/test_jerseys_app.py).
"""
import re
import threading

from overtime_core import equipment as EQ, teams as T

from . import labels as L
from .editors_controller import NHL_TEAMS, _colour, _hex
from .rail import FA, why_tip, why_view
from .registry import Part
from .session import BIOS, EditError

TAB = 'Jerseys & gear'                  # session.Change.tab (shell.TAB_LABELS)
LOAD_DELAY = 0.25                       # seconds after a pick before the team's gear is read
PIECES = ((7, 'Helmet'), (4, 'Gloves'), (2, 'Goalie pads'), (1, 'Blocker'), (0, 'Trapper'), (3, 'Goalie stick'))
TABLES = (EQ.CUSTOM, EQ.STOCK)          # a team's gear places, the custom teams' first (Seattle 499)
HEX = re.compile(r'#?[0-9A-Fa-f]{6}')

NOTE = 'The helmets, gloves and goalie gear of this team. Change a colour, then Apply.'
APPLIED = 'Applied. Save the roster to keep this gear in it.'
READING = "Reading the team's gear..."
FREE_AGENTS = 'Free agents have no team gear. Pick a team in the list.'
NO_TEAM = 'Pick a team in the list.'
NO_GEAR = 'This team has no gear of its own in the roster. Pick another team in the list.'
NOT_A_COLOUR = 'Pick a colour from the list or the colour box.'
WAIT = "Wait for the team's gear to show, then try again."
NOTHING = "Nothing to apply: change a colour, copy a team's gear or fit the sticks first."
SAME = 'The gear wears the team colours already.'
NO_GAME_COLOURS = 'NHL 19 has no team colours of its own for this team.'


def hx(c):
    """'RRGGBB' of a colour 0xRRGGBB."""
    return f'{int(c) & 0xFFFFFF:06X}'


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else many or one + 's'}"


def poss(name):
    """Anaheim Ducks' gear, Utah Mammoth's gear."""
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def counted(db, table, rows):
    """[(0xRRGGBB, zones)] of some gear rows, the most used first (equipment.palette's order)."""
    t, count = db[table], {}
    for i in rows:
        for z in EQ.ZONES:
            c = t.get(i, z)
            count[c] = count.get(c, 0) + 1
    return sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))


def laid_over(colours, mapping):
    """[(colour, zones)] with a colour map laid over it (two colours that become one are counted together)."""
    out = {}
    for c, n in colours:
        to = mapping.get(c, c)
        out[to] = out.get(to, 0) + n
    return sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))


def drop(s, changes):
    """Take `changes` (all in the history) back out of the roster and its history, newest first, when no other change
    after them would be lost: none touched one of their records or re-made the database, and none came after one of
    them that re-made it (a copy). False: nothing was done. RosterSession.drop when the session has it (docs/ui/
    jerseys.md, "Needs from the integrator")."""
    own = getattr(s, 'drop', None)
    if own is not None:
        return own(changes)
    at = [k for k, ch in enumerate(s.history) if any(ch is c for c in changes)]
    if not at or len(at) != len(changes):
        return False
    records = {key for ch in changes for key in ch.snaps}
    bulk = min((k for k in at if s.history[k].kept is not None), default=None)
    for k in range(at[0], len(s.history)):
        ch = s.history[k]
        if any(ch is c for c in changes):
            continue
        if ch.kept is not None or records & set(ch.snaps) or (bulk is not None and k > bulk):
            return False
    for k in reversed(at):
        s._rollback(s.history.pop(k))
    return True


def _later(delay, fn):
    timer = threading.Timer(delay, fn)
    timer.daemon = True
    timer.start()


class JerseysCtl(Part):
    SLICES = {'jerseys': 'view'}
    CALLS = {'gear_recolour': 'recolour', 'gear_propose': 'propose', 'gear_copy': 'copy', 'gear_sticks': 'sticks',
             'jerseys_apply': 'apply', 'jerseys_undo': 'take_back'}
    TAB = 'jerseys'

    def __init__(self, ctl):
        super().__init__(ctl)
        self.proposed = None    # beta1: (team, {old: new}) of the last gear_propose
        self.later = _later     # (seconds, fn): runs fn later (tests run it at once)
        self._fresh()

    def _fresh(self):
        self.held = {}          # rail team -> its draft {copy: rail team | None, map: {from: to}, sticks: bool}
        self.notes = {}         # rail team -> the note after Apply ('' : the usual one)
        self.errors = {}        # rail team -> the copy's refusal
        self.before = {}        # rail team -> {(table, gear id): [records]} from before its first Apply not saved
        self.values = []        # [(change, {game id: (old stick, new stick)})] of the applied changes
        self.taken = []         # [(take-back change, [the changes it took back])]: not "mine" while it is in the roster
        self.team = None        # the team the tab shows (follow), None: the rail's
        self.loading = False    # a pick waits to be read
        self.token = 0          # the newest pick: an older read is dropped
        self._book = None       # the open roster's gear index (book())
        self._last = None       # (session, slice) the tab drew last (sent again while another tab shows)

    # --- the rail's follower -----------------------------------------------------------------------------------------
    def follow(self, team):
        """The rail's team: the tab says it reads the team's gear and reads it LOAD_DELAY later, unless the rail has
        moved on by then. The same team again (the tab shown again) is not read again."""
        c = self.ctl
        with c.lock:
            if c.session is None or (team == self.team and not self.loading):
                self.team = team
                read = None
            else:
                self.team, self.loading = team, True
                self.token += 1
                read = self.token
        c.changed('jerseys')
        if read is not None:
            self.later(LOAD_DELAY, lambda: self._read(read, team))

    def _read(self, token, team):
        c = self.ctl
        with c.lock:
            if token != self.token or c.team != team or c.session is None:
                return              # stale: a newer pick owns the tab
            self.loading = False
            self.gear(team)          # reads the roster's gear index now, not in the push
        c.changed('jerseys')

    def roster_changed(self):
        self.proposed = None
        self.token += 1             # a read still waiting is for the old roster
        self._fresh()

    def dirty(self, team):
        return self.touched(team)

    def drafts(self):
        c = self.ctl
        with c.lock:
            if c.session is None:
                return ''
            codes = [self.code(t) for t in list(self.held) if self.touched(t)]
        return f"Gear not applied yet: {', '.join(codes)}." if codes else ''

    # --- the open roster's gear --------------------------------------------------------------------------------------
    def book(self):
        """{index: {table: {gear id: [rows]}}, sticks: {rail team: [(team, game id, old, new)]}, clubs} of the open
        roster, made again whenever its history changed. Under the lock."""
        s = self.ctl.session
        b, h = self._book, s.history
        if b is None or b['s'] is not s or len(b['h']) != len(h) or any(x is not y for x, y in zip(b['h'], h)):
            index = {}
            for table in TABLES:
                if table not in s.db:
                    continue
                t, rows = s.db[table], {}
                for i in range(t.count):
                    if t.get(i, 'equipment') in EQ.GEAR:
                        rows.setdefault(t.get(i, 'team'), []).append(i)
                index[table] = rows
            b = self._book = {'s': s, 'h': list(h), 'index': index, 'sticks': {}, 'clubs': None}
        return b

    def places(self, team):
        """[(table, gear id)] holding a rail team's gear, the one the tab shows first: Seattle's custom team (499)
        and its Play Now copy (399, stock); any other team's stock rows."""
        index = self.book()['index']
        gid = self.ctl.rail.map_id('jerseys', team)
        out = [(table, gid) for table in TABLES if gid != team and gid in index.get(table, {})][:1]
        if team in index.get(EQ.STOCK, {}):
            out.append((EQ.STOCK, team))
        return out

    def gear(self, team):
        """{table, gid, rows, palette: [(colour, zones)], pieces: {category: [(colour, zones)]}} of a rail team's gear
        as the roster holds it (the first of its places), or None."""
        if team is None or team == FA:
            return None
        places = self.places(team)
        if not places:
            return None
        table, gid = places[0]
        db = self.ctl.session.db
        rows = self.book()['index'][table][gid]
        by = {}
        for i in rows:
            by.setdefault(db[table].get(i, 'equipment'), []).append(i)
        return {'table': table, 'gid': gid, 'rows': len(rows), 'palette': counted(db, table, rows),
                'pieces': {cat: counted(db, table, by[cat]) for cat, _name in PIECES if cat in by}}

    def clubs(self):
        """The rail's NHL clubs (Seattle too, not the All-Stars teams): "Every NHL team"."""
        b = self.book()
        if b['clubs'] is None:
            c = self.ctl
            b['clubs'] = [t['id'] for t in c.rail.listed(c.session, T.NHL_LEAGUE) if not t['extra']]
        return b['clubs']

    def sticks_of(self, team):
        """[(team, game id, old, new)]: the team's skaters whose stick shows a colour the team does not wear and the
        stick each would get (equipment.team_sticks, nothing written)."""
        b = self.book()
        if team not in b['sticks']:
            db = self.ctl.session.db
            teams = self.clubs() if team in self.clubs() else [team]
            found = {t: [] for t in teams}
            for row in EQ.team_sticks(db, teams, setter=lambda *a: None):
                found[row[0]].append(row)
            b['sticks'].update(found)
        return b['sticks'][team]

    def nhl_sticks(self):
        """(sticks, teams) of every NHL club that do not fit the team colours."""
        for team in self.clubs():
            self.sticks_of(team)
        found = [len(self.book()['sticks'][t]) for t in self.clubs()]
        return sum(found), sum(1 for n in found if n)

    def code(self, team):
        chip = self.ctl.rail.chip(team)
        return chip['code'] if chip else str(team)

    def name(self, team):
        chip = self.ctl.rail.chip(team)
        return chip['name'] if chip else f'Team {team}'

    def player(self, gid):
        s = self.ctl.session
        i = s.bio_row.get(gid)
        return s.name(s.rows[BIOS][i]) if i is not None else f'Player {gid}'

    # --- the draft ---------------------------------------------------------------------------------------------------
    def draft(self, team):
        return self.held.get(team) or {'copy': None, 'map': {}, 'sticks': False}

    def start(self, team):
        """The gear the colour rows start from: the team's own, or the team's whose gear the draft copies."""
        d = self.draft(team)
        return self.gear(d['copy']) if d['copy'] is not None else self.gear(team)

    def mapping(self, team):
        """The draft's colour changes that apply to the gear the rows start from."""
        start = self.start(team)
        here = {c for c, _n in start['palette']} if start else set()
        return {a: b for a, b in self.draft(team)['map'].items() if a in here and a != b}

    def touched(self, team):
        """The team's draft would change the roster. Under the lock."""
        d = self.held.get(team)
        if not d or self.ctl.session is None:
            return False
        return d['copy'] is not None or bool(self.mapping(team)) or (d['sticks'] and bool(self.sticks_of(team)))

    def game_colours(self, team):
        """NHL 19's own team colours of a rail team (the game's default roster), or None."""
        try:
            return self.ctl.editors.default()[3].get(team) or None
        except Exception:  # noqa: BLE001 (no game files: the tab works without NHL 19's own colours)
            return None

    def proposal(self, team):
        """{gear colour: team colour} "Use the team colours" would put in the draft: the gear colours that still wear
        NHL 19's old team colours (equipment.proposal), not yet in the draft. Empty while the draft copies a team."""
        d = self.draft(team)
        own = self.gear(team)
        old = self.game_colours(team)
        if d['copy'] is not None or not own or not old:
            return {}
        new = EQ.team_colours(self.ctl.session.db, team)
        prop = EQ.proposal(self.ctl.session.db, own['gid'], new, old, own['table'])
        return {a: b for a, b in prop.items() if a != b and d['map'].get(a, a) != b}

    def taken_up(self, team):
        """How many of the proposal's colours the draft changes already."""
        d = self.draft(team)
        own = self.gear(team)
        old = self.game_colours(team)
        if d['copy'] is not None or not own or not old:
            return 0
        prop = EQ.proposal(self.ctl.session.db, own['gid'], EQ.team_colours(self.ctl.session.db, team), old,
                           own['table'])
        return sum(1 for a, b in prop.items() if a != b and d['map'].get(a) == b)

    def mine(self, team):
        """The team's changes from this tab that are not saved yet and not taken back, oldest first. Under the lock."""
        if self.ctl.session is None or team is None:
            return []
        s = self.ctl.session
        pending = [ch for ch, undone in self.ctl.parts['save'].pending() if not undone]
        gone = [x for back, xs in self.taken if any(back is h for h in s.history) for x in (back, *xs)]
        return [ch for ch in pending if ch.tab == TAB and ch.team == team and not any(ch is x for x in gone)]

    def describe(self, team):
        """The change's label in My edits: "Gear colour 132032 to 000A3E", "Anaheim Ducks' gear copied, 2 gear colours
        changed", "3 sticks fitted to the team colours"."""
        d = self.draft(team)
        parts = []
        if d['copy'] is not None:
            parts.append(f"{poss(self.name(d['copy']))} gear copied")
        moved = self.mapping(team)
        if len(moved) == 1 and not parts:
            (a, b), = moved.items()
            parts.append(f'gear colour {hx(a)} to {hx(b)}')
        elif moved:
            parts.append(f"{plural(len(moved), 'gear colour')} changed")
        n = len(self.sticks_of(team)) if d['sticks'] else 0
        if n:
            parts.append(f"{plural(n, 'stick')} fitted to the team colours")
        text = ', '.join(parts)
        return text[:1].upper() + text[1:]

    # --- the slice ---------------------------------------------------------------------------------------------------
    def view(self):
        c = self.ctl
        with c.lock:
            s = c.session
            if s is None:
                return why_view(c, 'jerseys', 'jerseys and gear', FREE_AGENTS, '')
            if c.tab_name != self.TAB and self._last is not None and self._last[0] is s:
                return self._last[1]        # another tab shows: what the tab drew last (follow reads it again)
            out = self.build(c.team if self.team is None else self.team)
            self._last = (s, out)
            return out

    def build(self, team):
        c = self.ctl
        s = c.session
        chip = c.rail.chip(team)
        head = {'id': c.rail.map_id('jerseys', team), 'team': team, 'view': chip,
                'title': f"{chip['name']}: jerseys and gear" if chip else 'Jerseys and gear'}
        if self.loading:
            return dict(head, why=READING, loading=True)
        if team is None or team == FA:
            return dict(head, why=FREE_AGENTS if team == FA else NO_TEAM, tip=why_tip(c))
        own = self.gear(team)
        if own is None:
            return dict(head, why=NO_GEAR, tip=why_tip(c))
        d = self.draft(team)
        start = self.start(team) or own
        moved = self.mapping(team)
        prop = self.proposal(team)
        taken = self.taken_up(team)
        old = self.game_colours(team)
        names = dict(PIECES)
        where = {}
        for cat, colours in start['pieces'].items():
            for colour, _n in colours:
                where.setdefault(colour, []).append(cat)
        order = [cat for cat, _name in PIECES]
        palette = [{'from': hx(a), 'to': hx(moved.get(a, a)), 'zones': n, 'changed': a in moved,
                    'pieces': [names[cat] for cat in sorted(where.get(a, []), key=order.index)],
                    'proposed': hx(prop[a]) if a in prop else None} for a, n in start['palette']]
        pieces = [{'name': name, 'colours': [{'hex': hx(x), 'n': n} for x, n in laid_over(start['pieces'][cat], moved)]}
                  for cat, name in PIECES if cat in start['pieces']]
        n_prop = len(prop)
        if d['copy'] is not None:
            cnote = "Copying another team's gear: recolour it in Gear colours."
        elif not old:
            cnote = NO_GAME_COLOURS
        elif n_prop:
            cnote = f"{plural(n_prop, 'gear colour')} still {'wears' if n_prop == 1 else 'wear'} NHL 19's old " \
                    'team colours.'
        elif taken:
            cnote = f"{plural(taken, 'gear colour')} {'changes' if taken == 1 else 'change'} to the team colours " \
                    'when you press Apply.'
        else:
            cnote = SAME
        league = c.rail.league_of(s, team)
        options = []
        for t in c.rail.listed(s, league) if league is not None else []:
            other = self.places(t['id']) if t['id'] != team else []
            if not other:
                continue
            if other[0][0] == own['table']:
                options.append({'value': t['id'], 'label': t['name']})
            else:
                options.append({'value': t['id'], 'label': f"{t['name']} (kept apart)", 'disabled': True})
        name = self.name(team)
        if d['copy'] is not None:
            copy_note = f"Takes {poss(self.name(d['copy']))} helmets, gloves and goalie gear when you press Apply. " \
                        'Recolour them next.'
        elif own['table'] == EQ.CUSTOM:
            copy_note = f"{poss(name)} gear is kept apart from the other teams' gear, so it cannot copy theirs yet. " \
                        'Change its colours instead.'
        else:
            copy_note = 'Gives this team the helmets, gloves and goalie gear of another team. Recolour them next.'
        sticks = self.sticks_of(team)
        nhl_count, nhl_teams = self.nhl_sticks()
        touched = self.touched(team)
        mine = bool(self.mine(team))
        note = self.notes.get(team) or ''
        return dict(
            head, why=None, note=note or NOTE, note_tone='good' if note else '',
            table='custom' if own['table'] == EQ.CUSTOM else 'stock', rows=start['rows'], palette=palette,
            pieces=pieces,
            colours={'now': [hx(x) for x in EQ.team_colours(s.db, team)], 'game': [hx(x) for x in old] if old else None,
                     'proposed': n_prop, 'can_propose': n_prop > 0, 'note': cnote},
            copy={'from': d['copy'], 'from_name': self.name(d['copy']) if d['copy'] is not None else '',
                  'options': options, 'error': self.errors.get(team) or '', 'note': copy_note},
            sticks={'rows': [{'name': self.player(gid), 'old': EQ.NAMES['stick'].get(o, f'Stick {o}'),
                              'new': EQ.NAMES['stick'].get(n, f'Stick {n}')} for _t, gid, o, n in sticks],
                    'fitted': bool(d['sticks'] and sticks), 'count': len(sticks), 'nhl_count': nhl_count,
                    'nhl_teams': nhl_teams},
            touched=touched, can_apply=touched, mine=mine, can_undo=mine or touched)

    # --- the page's calls (on the rail's team's draft) ---------------------------------------------------------------
    def _ready(self):
        """The rail's team, its gear shown: EditError when the tab cannot change it now. Under the lock."""
        c = self.ctl
        if c.session is None:
            raise EditError('Pick a roster in Setup first.')
        team = c.team
        if team is None or team == FA:
            raise EditError(FREE_AGENTS if team == FA else NO_TEAM)
        if self.loading:
            raise EditError(WAIT)
        if self.gear(team) is None:
            raise EditError(NO_GEAR)
        return team

    def _draft_call(self, fn):
        """Run a change of the draft under the lock: EditError -> {'error'} and the status line. fn(team, draft)
        returns (reply, status text, tone) and the draft is kept (or dropped when empty)."""
        c = self.ctl
        try:
            with c.lock:
                team = self._ready()
                d = self.held.setdefault(team, {'copy': None, 'map': {}, 'sticks': False})
                reply, text, tone = fn(team, d)
                if d['copy'] is None and not d['map'] and not d['sticks']:
                    self.held.pop(team, None)
                self._last = None
        except EditError as err:
            text = str(err)
            c.say(text, 'bad' if text != WAIT else 'info')
            return {'error': text}
        if text:
            c.say(text, tone)
        c.changed('jerseys', 'rail')
        return reply

    def _edited(self, team):
        """A draft change: the note after Apply and the copy's refusal go."""
        self.notes.pop(team, None)
        self.errors.pop(team, None)

    def recolour(self, mapping):
        """gear_recolour({from: to}): new colours into the draft; to == from takes that colour back."""
        pairs = []
        for a, b in (mapping.items() if isinstance(mapping, dict) else ()):
            if not (isinstance(a, str) and isinstance(b, str) and HEX.fullmatch(a) and HEX.fullmatch(b)):
                pairs = []
                break
            pairs.append((int(a.lstrip('#'), 16), int(b.lstrip('#'), 16)))
        if not pairs:
            self.ctl.say(NOT_A_COLOUR, 'caution')
            return {'error': NOT_A_COLOUR}

        def work(team, d):
            start = self.start(team)
            here = {c for c, _n in start['palette']}
            for a, b in pairs:
                if a not in here:
                    continue
                if a == b:
                    d['map'].pop(a, None)
                else:
                    d['map'][a] = b
            self._edited(team)
            return {'ok': True}, '', ''
        return self._draft_call(work)

    def propose(self):
        """gear_propose: "Use the team colours": every gear colour still in NHL 19's old team colours changes to the
        colours now, in the draft."""
        def work(team, d):
            prop = self.proposal(team)
            if not prop:
                return {'ok': False, 'count': 0}, SAME if self.game_colours(team) else NO_GAME_COLOURS, 'info'
            d['map'].update(prop)
            self._edited(team)
            return {'ok': True, 'count': len(prop)}, \
                f"{plural(len(prop), 'gear colour')} to change: check them, then Apply.", 'info'
        return self._draft_call(work)

    def copy(self, src=None):
        """gear_copy(team | None): the draft takes another team's gear (its colour changes start again); None (or the
        team itself) goes back to the team's own gear. Refused across the gear tables, with a sentence."""
        def work(team, d):
            try:
                frm = None if src in (None, '') else int(src)
            except (TypeError, ValueError):
                raise EditError('Pick a team in the list to copy from.') from None
            if frm is None or frm == team:
                if d['copy'] is not None:
                    d['copy'], d['map'] = None, {}
                self._edited(team)
                return {'ok': True}, '', ''
            theirs, own = self.places(frm), self.places(team)
            if frm == FA or not theirs:
                raise EditError('Pick a team in the list to copy from.')
            if theirs[0][0] != own[0][0]:
                if own[0][0] == EQ.CUSTOM:
                    text = f"{poss(self.name(team))} gear is kept apart from the other teams' gear, so it cannot " \
                           f"take {poss(self.name(frm))} yet. Change its colours instead."
                else:
                    text = f"{poss(self.name(frm))} gear is kept apart from the other teams' gear, so " \
                           f"{self.name(team)} cannot take it yet. Pick another team."
                self.errors[team] = text
                return {'error': text}, text, 'bad'
            d['copy'], d['map'] = frm, {}
            self._edited(team)
            return {'ok': True}, f"{poss(self.name(frm))} gear is in. Recolour it if you like, then Apply.", 'info'
        return self._draft_call(work)

    def sticks(self, every=False):
        """gear_sticks(false): fit this team's sticks in the draft (again: the sticks they have stay). gear_sticks(true):
        asks, then fits the sticks of every NHL team as one change at once."""
        if every:
            return self.ask_every()

        def work(team, d):
            if not self.sticks_of(team):
                d['sticks'] = False
                return {'ok': False}, 'Every stick of this team matches the team colours already.', 'info'
            d['sticks'] = not d['sticks']
            self._edited(team)
            return {'ok': True}, '', ''
        return self._draft_call(work)

    def ask_every(self):
        c = self.ctl
        with c.lock:
            if c.session is None:
                c.say('Pick a roster in Setup first.', 'bad')
                return {'error': 'Pick a roster in Setup first.'}
            n, teams = self.nhl_sticks()
        if not n:
            c.say("Every NHL team's sticks match its colours already.", 'info')
            return {'ok': False}
        c.shell.ask('Fit the sticks of every NHL team?',
                    [f"{plural(n, 'stick')} on {plural(teams, 'NHL team')} change to sticks in their team colours.",
                     'This goes into My edits at once. Save the roster to keep it.'],
                    [('Fit them all', 'fit', 'primary'), ('Cancel', 'cancel', 'plain')], {'fit': self.fit_every})
        return {'ok': True, 'asked': True}

    def fit_every(self):
        """Every NHL club's sticks in its team colours, as one change (My edits, no one team)."""
        c = self.ctl
        try:
            with c.lock:
                s = c.session
                if s is None:
                    raise EditError('Pick a roster in Setup first.')
                n, teams = self.nhl_sticks()
                if not n:
                    raise EditError("Every NHL team's sticks match its colours already.")
                clubs = list(self.clubs())
                label = f"{plural(n, 'stick')} on {plural(teams, 'NHL team')} fitted to the team colours"
                ch, changes = s.edit(label, lambda setter: EQ.team_sticks(s.db, clubs, setter=setter))
                ch.tab, ch.team = TAB, None
                for t, gid, old, new in changes:
                    ch.details.append((f'{self.code(t)} stick ({self.player(gid)})', EQ.NAMES['stick'].get(old, old),
                                       EQ.NAMES['stick'].get(new, new)))
                self._last = None
        except EditError as err:
            c.say(str(err), 'info')
            return {'error': str(err)}
        c.host.log(f'NHL sticks: {len(changes)} changed to fit the team colours.')
        self._logged(ch)
        c.say(f"{plural(len(changes), 'stick')} changed to fit the team colours. Save the roster to keep them.", 'good')
        c.changed('jerseys', 'rail', 'save', 'equipment')
        return {'ok': True}

    # --- Apply and Take back -----------------------------------------------------------------------------------------
    def snapshot(self, team):
        """{(table, gear id): [records]} of the team's gear now (Take back puts them back when its changes cannot
        just be dropped)."""
        db = self.ctl.session.db
        out = {}
        for table, gid in self.places(team):
            t = db[table]
            n = t.record_length
            out[(table, gid)] = [bytes(t.data[i * n:(i + 1) * n]) for i in self.book()['index'][table][gid]]
        return out

    def apply(self):
        """jerseys_apply: the draft into the roster as one change: the copy, then the colours, then the sticks."""
        c = self.ctl
        try:
            with c.lock:
                team = self._ready()
                if not self.touched(team):
                    self.held.pop(team, None)
                    c.say(NOTHING, 'info')
                    return {'ok': False}
                s = c.session
                d = self.draft(team)
                label = self.describe(team)
                code = self.code(team)
                places = self.places(team)
                moved = self.mapping(team)
                src = {table: gid for table, gid in self.places(d['copy'])} if d['copy'] is not None else {}
                fit = d['sticks'] and bool(self.sticks_of(team))
                first = team not in self.before or not self.mine(team)
                before = self.snapshot(team) if first else None

                def write(db, setter):
                    details, fitted = [], []
                    for table, gid in places:
                        if table in src:
                            n = EQ.copy_gear(db, src[table], gid, table)
                            details.append((f'{code} gear', 'own', f"{poss(self.name(d['copy']))} ({n} rows)"))
                    for table, gid in places:
                        EQ.recolour(db, gid, moved, table, setter=setter)
                    for a, b in moved.items():
                        details.append((f'{code} gear colour', hx(a), hx(b)))
                    if fit:
                        fitted = EQ.team_sticks(db, [team], setter=setter)
                        for _t, gid, old, new in fitted:
                            details.append((f'{code} stick ({self.player(gid)})', EQ.NAMES['stick'].get(old, old),
                                            EQ.NAMES['stick'].get(new, new)))
                    return details, fitted

                if src:     # a copy changes the number of records: the whole database is kept for Undo
                    ch, fitted = s.bulk(label, lambda db: write(db, None))
                else:
                    ch, (details, fitted) = s.edit(label, lambda setter: write(s.db, setter))
                    ch.details = details
                ch.tab, ch.team = TAB, team
                self.held.pop(team, None)
                self.errors.pop(team, None)
                self._last = None
                if not ch.snaps and ch.kept is None:
                    self.notes.pop(team, None)
                    c.say('Nothing changed: the gear looks like this already.', 'info')
                    c.changed('jerseys', 'rail')
                    return {'ok': False}
                if first:
                    self.before[team] = before
                self.values.append((ch, {gid: (old, new) for _t, gid, old, new in fitted}))
                self.notes[team] = APPLIED
                name = self.name(team)
                c.issues = None
        except (EditError, ValueError, KeyError, IndexError) as err:
            text = str(err).strip("'")
            c.say(text, 'bad')
            return {'error': text}
        c.host.log(f'{code} gear: {label}.')
        self._logged(ch)
        c.say(f'{name}: gear applied. Save the roster to keep it.', 'good')
        c.changed('jerseys', 'rail', 'save', 'equipment')
        return {'ok': True}

    def take_back(self):
        """jerseys_undo: "Take back my gear": drops the draft; while the team's applied gear is not saved yet, takes
        it back too (out of My edits; when a later change touched the same records, the gear from before the first
        Apply is put back as a new change)."""
        c = self.ctl
        try:
            with c.lock:
                team = self._ready()
                mine = self.mine(team)
                if not mine and not self.touched(team):
                    self.held.pop(team, None)
                    c.say('Nothing to take back on this team.', 'info')
                    return {'ok': False}
                self.held.pop(team, None)
                self.notes.pop(team, None)
                self.errors.pop(team, None)
                self._last = None
                code = self.code(team)
                text, how = 'Your changes are dropped.', None
                if mine:
                    how = 'dropped' if drop(c.session, mine) else self.restore(team, mine)
                    self.before.pop(team, None)
                    text = "Your gear changes are taken back. The team wears the roster's gear again."
                    c.issues = None
        except (EditError, ValueError, KeyError, IndexError) as err:
            text = str(err).strip("'")
            c.say(text, 'bad')
            return {'error': text}
        if how is not None:
            c.host.log(f'{code} gear: taken back.')
            if how != 'dropped':
                self._logged(how)
        c.say(text, 'info')
        c.changed('jerseys', 'rail', 'save', 'equipment')
        return {'ok': True}

    def restore(self, team, mine):
        """Put back the team's gear from before its first Apply (and each stick its changes fitted, where the roster
        still holds the new one) as one new change; its changes and this one are not "mine" any more."""
        s = self.ctl.session
        before = self.before.get(team)
        if before is None:
            raise EditError('Your gear cannot be taken back here any more. Use My edits to undo it.')
        code = self.code(team)
        sticks = {}
        for ch in mine:
            for gid, (old, new) in next((v for x, v in self.values if x is ch), {}).items():
                sticks[gid] = (sticks[gid][0] if gid in sticks else old, new)

        def work(db):
            details = []
            for (table, gid), records in before.items():
                t = db[table]
                for i in sorted(EQ.gear_rows(db, gid, table, EQ.GEAR), reverse=True):
                    t.delete(i)
                n = t.record_length
                for raw in records:
                    row = t.append()
                    t.data[row * n:(row + 1) * n] = raw
            details.append((f'{code} gear', 'yours', 'as before'))
            E = db[EQ.SKATER_TABLE]
            erow = {E.get(i, 'game_id'): i for i in range(E.count)}
            for gid, (old, new) in sticks.items():
                if gid in erow and E.get(erow[gid], 'stick') == new:
                    E.set(erow[gid], 'stick', old)
                    details.append((f'{code} stick ({self.player(gid)})', EQ.NAMES['stick'].get(new, new),
                                    EQ.NAMES['stick'].get(old, old)))
            return details, None
        ch, _ = s.bulk(f"{poss(self.name(team))} gear taken back", work)
        ch.tab, ch.team = TAB, team
        self.taken = [(back, xs) for back, xs in self.taken if any(back is h for h in s.history)] + [(ch, list(mine))]
        return ch

    def _logged(self, ch):
        for what, old, new in ch.details[:200]:
            self.ctl.host.log(f'  {what}: {old} -> {new}')

    # --- beta1's team gear (EditorsController's names): written at once ----------------------------------------------
    def gear_recolour(self, mapping):
        ed = self.ctl.editors

        def work():
            s, team = ed._team()
            m = {_colour(a): _colour(b) for a, b in (mapping or {}).items()}
            m = {a: b for a, b in m.items() if a != b}
            if not m:
                raise EditError('No colour to change.')
            ch, n = s.edit(f'{s.team_abbr(team)}: gear colours', lambda setter: EQ.recolour(s.db, team, m, setter=setter))
            for a, b in m.items():
                ch.details.append((f'{s.team_abbr(team)} gear colour', _hex(a), _hex(b)))
            self.proposed = None
            ed._logged(ch, self.ctl.host)
            return f'{s.team_name(team)}: {n} gear zone(s) recoloured (not saved yet).' if n else 'Nothing to recolour.'
        return ed._run(work, 'equipment')

    def gear_propose(self):
        """Work out (not write) the colours that move the team's gear from the game's colours of this team to its
        colours now; beta1's tab showed them to apply."""
        c = self.ctl
        ed = c.editors
        try:
            with c.lock:
                s, team = ed._team()
                _db, _p, _w, colours = ed.default()
                old = colours.get(team) or []
                new = EQ.team_colours(s.db, team)
                self.proposed = (team, EQ.proposal(s.db, team, new, old))
                n = len(self.proposed[1])
        except EditError as err:
            c.say(str(err), 'bad')
            return {'error': str(err)}
        c.say(f'{n} gear colour(s) to change: check them, then Apply.' if n else
              'The team gear already wears the team colours.', 'info')
        c.changed('equipment')
        return {'ok': True, 'count': n}

    def gear_copy(self, src):
        ed = self.ctl.editors

        def work():
            s, team = ed._team()
            src_team = int(src)
            if src_team == team:
                raise EditError('Pick another team to copy from.')
            if not EQ.gear_rows(s.db, src_team, categories=EQ.GEAR):
                raise EditError(f'{s.team_name(src_team)} has no gear rows to copy.')

            def bulk(db):
                n = EQ.copy_gear(db, src_team, team)
                return [(f'{s.team_abbr(team)} gear', 'own', f"{s.team_name(src_team)}'s ({n} rows)")], n
            ch, n = s.bulk(f"{s.team_abbr(team)}: {s.team_abbr(src_team)}'s gear", bulk)
            self.proposed = None
            ed._logged(ch, self.ctl.host)
            return f"{s.team_name(team)} wears {s.team_name(src_team)}'s gear rows now ({n}); recolour them next."
        return ed._run(work, 'equipment')

    def gear_sticks(self, every=False):
        ed = self.ctl.editors

        def work():
            s, team = ed._team()
            teams = NHL_TEAMS if every else [team]
            what = 'NHL' if every else s.team_abbr(team)
            ch, changes = s.edit(f'{what}: sticks in team colours',
                                 lambda setter: EQ.team_sticks(s.db, teams, setter=setter))
            for t, gid, old, new in changes[:200]:
                ch.details.append((f'{s.team_abbr(t)} stick ({gid})', EQ.NAMES['stick'].get(old, old),
                                   EQ.NAMES['stick'].get(new, new)))
            ed._logged(ch, self.ctl.host)
            return f'{len(changes)} stick(s) changed to fit the team colours (not saved yet).' if changes else \
                'Every stick already fits its team colours.'
        return ed._run(work, 'equipment')

    def snap_team(self):
        """The rail's team's gear (beta1's equipment slice, 'team' and 'teams'): {} without a team. Under the lock."""
        c = self.ctl
        s = c.session
        if s is None or c.team is None or c.team == L.FREE_AGENTS:
            return {}
        team = c.team
        _db, _p, _w, colours = c.editors.default()
        sticks = EQ.team_sticks(s.db, [team], setter=lambda *a: None)
        proposed = self.proposed[1] if self.proposed and self.proposed[0] == team else None
        return {
            'team': {
                'id': team, 'name': s.team_name(team), 'abbr': s.team_abbr(team),
                'colours': [_hex(x) for x in EQ.team_colours(s.db, team)],
                'game_colours': [_hex(x) for x in colours.get(team, [])],
                'palette': [[_hex(x), n] for x, n in EQ.palette(s.db, team)],
                'rows': len(EQ.gear_rows(s.db, team, categories=EQ.GEAR)),
                'proposal': None if proposed is None else [[_hex(a), _hex(b)] for a, b in proposed.items()],
                'sticks': [{'gid': gid, 'old': EQ.NAMES['stick'].get(o, str(o)),
                            'new': EQ.NAMES['stick'].get(n, str(n))} for _t, gid, o, n in sticks],
            },
            'teams': [{'id': t['id'], 'name': t['name']} for t in s.teams(0) if t['id'] != team],
        }
