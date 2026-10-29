"""What the editors beyond the player card share: player type and face (faces_ctl: the Roster tab's Face & type
window), a player's gear (gear_ctl: its Equipment window) and a team's gear colours and sticks (jerseys_ctl: the
Jerseys & gear tab).

`EditorsController(controller)` hangs off the main Controller (`ctl.editors`): it holds what the three parts share
(the game's own default roster, the ratings models of the open roster, the open player and team, one edit under the
lock) and keeps beta1's calls and snapshots (type_set ... gear_sticks, snap_faces, snap_equipment), which now go to
the parts. Every edit is one undoable change of the RosterSession, so it goes into the save like the card's edits.
What the game can show is taken from its own default roster (faces.parts, equipment.worn) and its Creation Zone lists
(equipment.NAMES).
"""
from overtime_core import equipment as EQ, faces as F, ratings

from . import labels as L
from .session import EditError

NHL_TEAMS = range(32)


def _hex(c):
    return f'#{int(c) & 0xFFFFFF:06x}'


def _colour(v):
    """0xRRGGBB of '#rrggbb' / 'rrggbb' / a number."""
    if isinstance(v, int):
        n = v
    else:
        try:
            n = int(str(v).strip().lstrip('#'), 16)
        except ValueError:
            raise EditError(f'{v!r} is not a colour (#rrggbb).') from None
    if not 0 <= n <= 0xFFFFFF:
        raise EditError(f'{v!r} is not a colour (#rrggbb).')
    return n


class EditorsController:
    def __init__(self, ctl):
        self.ctl = ctl
        self._default = None   # (default roster db, faces.parts, equipment.worn, {team: colours})
        self._models = {}      # ratings table -> ratings.Model of the open roster
        self._model_of = None  # the session the models were fitted on

    # --- what the parts share ----------------------------------------------------------------------------------------
    def default(self):
        if self._default is None:
            db = self.ctl.game.default_db()
            colours = {}
            T = db[EQ.TEAMS]
            for i in range(T.count):
                colours[T.get(i, 'index')] = [T.get(i, f) for f in EQ.TEAM_COLOURS]
            self._default = (db, F.parts(db), EQ.worn(db), colours)
        return self._default

    def _player(self):
        """(session, playerindex, faces.Player) of the open player; EditError without one."""
        c = self.ctl
        if not c.session or c.player is None:
            raise EditError('Pick a player on the Roster tab first.')
        try:
            return c.session, c.player, F.Player(c.session.db, c.player)
        except KeyError as err:
            raise EditError(str(err).strip("'")) from None

    def _team(self):
        c = self.ctl
        if not c.session or c.team is None or c.team == L.FREE_AGENTS:
            raise EditError('Pick a team in the list first.')
        return c.session, c.team

    def _model(self, session, table):
        if self._model_of is not session:
            self._models, self._model_of = {}, session
        if table not in self._models:
            self._models[table] = ratings.Model.fit(session.db[table])
        return self._models[table]

    def _run(self, fn, *slices):
        """Run an edit under the lock; EditError -> {'error'} and the status line."""
        c = self.ctl
        try:
            with c.lock:
                text = fn()
                c.issues = None
        except (EditError, ValueError, KeyError, TypeError) as err:
            text = str(err).strip("'")
            c.say(text, 'bad')
            return {'error': text}
        if text:
            c.say(text, 'good')
        c.changed('editor', 'lines', 'save', *slices)
        return {'ok': True}

    @staticmethod
    def _logged(ch, host):
        for what, old, new in ch.details:
            host.log(f'  {what}: {old} -> {new}')

    # --- beta1's calls, now in the parts -----------------------------------------------------------------------------
    @property
    def proposed(self):
        return self.ctl.parts['jerseys'].proposed

    def type_set(self, style):
        return self.ctl.parts['faces'].type_set(style)

    def face_set(self, values):
        return self.ctl.parts['faces'].face_set(values)

    def face_copy(self, ident):
        return self.ctl.parts['faces'].face_copy(ident)

    def snap_faces(self):
        return self.ctl.parts['faces'].snap_faces()

    def gear_set(self, values):
        return self.ctl.parts['gear'].gear_set(values)

    def gear_team_wide(self, choice):
        return self.ctl.parts['gear'].gear_team_wide(choice)

    def gear_recolour(self, mapping):
        return self.ctl.parts['jerseys'].gear_recolour(mapping)

    def gear_propose(self):
        return self.ctl.parts['jerseys'].gear_propose()

    def gear_copy(self, src):
        return self.ctl.parts['jerseys'].gear_copy(src)

    def gear_sticks(self, every=False):
        return self.ctl.parts['jerseys'].gear_sticks(every)

    def snap_equipment(self):
        """Beta1's 'equipment' slice: the open player's gear (gear_ctl) and the team's (jerseys_ctl)."""
        c = self.ctl
        with c.lock:
            if c.session is None:
                return {'ready': False}
            out = {'ready': True, 'player': c.parts['gear'].snap_player(), 'team': None}
            out.update(c.parts['jerseys'].snap_team())
            return out
