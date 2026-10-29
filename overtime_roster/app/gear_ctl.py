"""The Roster tab's Equipment window: the picked player's gear (models, tape colours), for him or his whole team.
docs/ui/roster.md (roster_gear, calls roster_gear_*).

Picks wait here per player (`picks`: {choice: model number or '#RRGGBB'}) until Apply, which writes them as one
change; "Apply to the whole team" also gives the team-wide picks (equipment.TEAM_WIDE) to every teammate of his kind.
Closing the window keeps the picks (RosterCtl.drafts / dirty); Take back drops them and takes back his applied
equipment edits (RosterCtl.take_back). Beta1's edits (gear_set, gear_team_wide) and the player half of beta1's
'equipment' snapshot stay as before.
"""
import re

from overtime_core import equipment as EQ, faces as F

from . import labels as L, roster_card as RC
from .editors_controller import _colour, _hex
from .registry import Part
from .session import EditError

BUTTONS = 8     # a model list this long or shorter shows as buttons, a longer one as a grid
SWATCHES = ('#FFFFFF', '#000000', '#C9C9C9')
MORE_SWATCHES = ('#C8102E', '#003087', '#FFB81C')
HEX = re.compile(r'^#?([0-9A-Fa-f]{6})$')


def _up(v):
    return _hex(v).upper()


class GearCtl(Part):
    SLICES = {'roster_gear': 'view'}
    CALLS = {'roster_gear_open': 'open_window', 'roster_gear_close': 'close', 'roster_gear_pick': 'pick',
             'roster_gear_apply': 'apply', 'roster_gear_undo': 'take_back',
             'gear_set': 'gear_set', 'gear_team_wide': 'gear_team_wide'}

    def __init__(self, ctl):
        super().__init__(ctl)
        self.open = None        # the player the window shows (None: closed)
        self.picks = {}        # {pi: {choice: number | '#RRGGBB'}}

    def roster_changed(self):
        self.open, self.picks = None, {}

    # --- reading -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _his(s, pi):
        """(kind, his equipment row or None, {choice: value} as the window shows them: colours '#RRGGBB')."""
        _, b = s.bio(pi)
        kind = EQ.kind_of(b['position'])
        row = EQ.row_of(s.db, b['game_id'], kind)
        if row is None:
            return kind, None, {}
        values = EQ.read(s.db, row, kind)
        return kind, row, {k: (_up(v) if k in EQ.COLOUR_CHOICES else v) for k, v in values.items()}

    def view(self):
        c = self.ctl
        with c.lock:
            s, pi = c.session, self.open
            if s is None or pi is None or s.bio(pi)[1] is None:
                return {'open': False}
            _, b = s.bio(pi)
            kind, row, now = self._his(s, pi)
            team = RC.rail_team(s, pi)
            free = team == L.FREE_AGENTS
            chip = c.rail.chip(team) if not free else None
            d = self.picks.get(pi, {})
            rows = []
            for k, (_f, label, names) in EQ.KINDS[kind][1].items() if row is not None else ():
                value = d.get(k, now[k])
                colour = k in EQ.COLOUR_CHOICES
                options = [] if names is None else [[n, lab] for n, lab in EQ.options(kind, k, now[k])]
                if options and not any(n == value for n, _l in options):
                    options.insert(0, [value, f'Model {value}'])
                rows.append({'key': k, 'label': label, 'colour': colour, 'team_wide': k in EQ.TEAM_WIDE and not free,
                             'value': value, 'current': now[k], 'changed': k in d,
                             'show': 'colour' if colour else 'number' if not options else
                             'buttons' if len(options) <= BUTTONS else 'grid',
                             'options': options})
            shared = [r for r in rows if r['changed'] and r['team_wide']]
            goalie = kind == 'goalie'
            colours = [x.upper() for x in (chip['colours'] if chip else [])]
            if free or not chip:
                team_label, team_title = 'Apply to the whole team', 'A free agent has no team.'
            else:
                team_label = f"Apply to every goalie ({chip['code']})" if goalie else \
                    f"Apply to the whole team ({chip['code']})"
                if shared:
                    team_title = f"Gives {', '.join(r['label'].lower() for r in shared)} to every " \
                                 f"{'goalie' if goalie else 'skater'} of {chip['name']}."
                elif goalie:
                    team_title = 'Pick a jersey tuck first: it can go to every goalie of the team.'
                else:
                    team_title = 'Pick a helmet, gloves, visor, tint, tuck, pants or tape first: those can go to ' \
                                 'the whole team.'
            done = c.parts['roster'].mine(pi, 'gear')
            picked = any(r['changed'] for r in rows)
            return {
                'open': True, 'id': pi, 'name': s.name(b), 'kind': kind, 'team': chip, 'free_agent': free,
                'none': '' if row is not None else 'He has no equipment record, so there is nothing to pick.',
                'rows': rows, 'swatches': list(dict.fromkeys((*SWATCHES, *colours, *MORE_SWATCHES))),
                'can_apply': picked, 'can_team': bool(shared), 'team_label': team_label, 'team_title': team_title,
                'can_take_back': picked or bool(done), 'busy': bool(c.busy),
            }

    # --- the window's calls ------------------------------------------------------------------------------------------
    def _who(self):
        c = self.ctl
        pi = self.open if self.open is not None else c.player
        if c.session is None or pi is None or c.session.bio(pi)[1] is None:
            c.say('Pick a player first.', 'caution')
            return None
        return pi

    def open_window(self):
        c = self.ctl
        with c.lock:
            if c.session is None or c.player is None:
                c.say('Pick a player first.', 'caution')
                return {'ok': False}
            self.open = c.player
        c.changed('roster_gear')
        return {'ok': True}

    def close(self):
        with self.ctl.lock:
            self.open = None
        self.ctl.changed('roster_gear')
        return {'ok': True}

    def pick(self, choice, value):
        """Hold a model (a number) or a tape colour ('#RRGGBB') until Apply."""
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            kind, row, now = self._his(s, pi)
            choices = EQ.KINDS[kind][1]
            why, v = '', None
            if row is None:
                why = 'He has no equipment record.'
            elif choice not in choices:
                why = f'He has no {choice}.'
            elif choice in EQ.COLOUR_CHOICES:
                m = HEX.match(str(value or '').strip())
                if not m:
                    why = f'{choices[choice][1]}: type a colour like #FFFFFF.'
                else:
                    v = f'#{m.group(1).upper()}'
            else:
                try:
                    v = int(str(value).strip())
                except (TypeError, ValueError):
                    v = None
                if v is None:
                    why = f'{choices[choice][1]}: type a number.'
                elif v != now[choice]:
                    _ok, problems = EQ.clean(s.db, {choice: v}, kind)
                    if problems:
                        why = problems[0] + '.'
            if not why:
                d = self.picks.setdefault(pi, {})
                if v == now[choice]:
                    d.pop(choice, None)
                else:
                    d[choice] = v
                if not d:
                    del self.picks[pi]
        if why:
            c.say(why, 'bad')
            return {'ok': False}
        c.changed('roster_gear', 'roster_card', 'rail')
        return {'ok': True}

    def apply(self, whole_team=False):
        """Apply the picks to him; whole_team also gives the team-wide ones to every teammate of his kind."""
        c = self.ctl
        roster = c.parts['roster']
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            d = self.picks.get(pi)
            if not d:
                c.say('Nothing to apply: pick something first.', 'caution')
                return {'ok': False}
            kind, row, now = self._his(s, pi)
            choices = EQ.KINDS[kind][1]
            values = {k: (_colour(v) if k in EQ.COLOUR_CHOICES else v) for k, v in d.items()}
            ok, problems = EQ.clean(s.db, values, kind)
            name = s.name(s.bio(pi)[1])
            if problems or row is None:
                text = f"{name}: {'; '.join(problems) or 'he has no equipment record'}."
                c.say(text, 'bad')
                return {'ok': False, 'error': text}
            team = RC.rail_team(s, pi)
            shared = {k: v for k, v in ok.items() if k in EQ.TEAM_WIDE} if whole_team and team != L.FREE_AGENTS else {}
            mates = []
            for m in s.players_of(team) if shared else ():
                _, mb = s.bio(m)
                if m == pi or mb is None or EQ.kind_of(mb['position']) != kind:
                    continue
                r = EQ.row_of(s.db, mb['game_id'], kind)
                if r is not None:
                    mates.append(r)
            moved = []

            def work(setter):
                EQ.write(s.db, row, ok, kind, setter)
                for r in mates:
                    if EQ.write(s.db, r, shared, kind, setter):
                        moved.append(r)

            def shown(k, v):
                return v if k in EQ.COLOUR_CHOICES else dict(EQ.options(kind, k, v)).get(v, f'model {v}')
            try:
                ch, _ = s.edit(f'{name}: equipment', work)
            except EditError as err:
                text = f'{name}: {err}'
                c.say(text, 'bad')
                return {'ok': False, 'error': text}
            words = [f'{choices[k][1].lower()} {shown(k, now[k])} to {shown(k, d[k])}' for k in d]
            for k in d:
                ch.details.append((f'{name}: {choices[k][1].lower()}', shown(k, now[k]), shown(k, d[k])))
            label = f"{name}: {', '.join(words)}"
            if shared:
                code = s.team_abbr(team) or str(team)
                label += f"; {', '.join(choices[k][1].lower() for k in shared)} for {len(moved)} " \
                         f"{'goalies' if kind == 'goalie' else 'skaters'} of {code}"
                ch.details.append((f'{code}: {", ".join(choices[k][1].lower() for k in shared)}', 'per player',
                                   f'{len(moved)} teammate(s)'))
            ch.label = label
            roster.note(ch, pi, 'gear', ['equipment'], ['gear'], kept=list(ok))
            del self.picks[pi]
            c.issues = None
            c.editors._logged(ch, c.host)
        c.say(f'{label}. Not saved yet.', 'good')
        c.changed('editor', 'lines', 'save', 'equipment')
        return {'ok': True, 'players': 1 + len(moved)}

    def take_back(self):
        """Drop the picks and take back his applied equipment edits."""
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            had = self.picks.pop(pi, None) is not None
            taken, blocked = c.parts['roster'].take_back(pi, 'gear')
            name = c.parts['roster'].who(c.session, pi)
        if blocked:
            c.say(f'{name}: take back "{blocked}" first (My edits). It changed him later.', 'caution')
        elif taken:
            c.say(f'{name} has his equipment back from before your edits.', 'good')
        elif had:
            c.say(f'Your equipment picks for {name} are gone. Nothing was applied.')
        else:
            c.say(f"Nothing to take back: {name}'s equipment is as it was.")
        c.changed('editor', 'lines', 'save', 'equipment')
        return {'ok': not blocked, 'taken': taken}

    # --- beta1's edits -----------------------------------------------------------------------------------------------
    def gear_set(self, values):
        ed = self.ctl.editors

        def work():
            s, pi, p = ed._player()
            kind = EQ.kind_of(p.position)
            row = EQ.row_of(s.db, p.game_id, kind)
            if row is None:
                raise EditError('This player has no equipment record.')
            vals = {k: (_colour(v) if k in EQ.COLOUR_CHOICES else v) for k, v in (values or {}).items()}
            ok, problems = EQ.clean(s.db, vals, kind)
            if problems:
                raise EditError('; '.join(problems) + '.')
            who = s.name(s.rows['exhibitionplayerbiotable'][p.bio])
            before = EQ.read(s.db, row, kind)
            ch, n = s.edit(f'{who}: gear', lambda setter: EQ.write(s.db, row, ok, kind, setter))
            self._details(ch, who, kind, before, ok)
            ed._logged(ch, self.ctl.host)
            return f'{who}: gear changed ({n} value(s); not saved yet).' if n else 'Nothing changed.'
        return ed._run(work, 'equipment')

    @staticmethod
    def _details(ch, who, kind, before, values):
        choices = EQ.KINDS[kind][1]
        for k, v in values.items():
            if before.get(k) != v:
                show = _hex if k in EQ.COLOUR_CHOICES else (lambda n, k=k: dict(EQ.options(kind, k, n)).get(n, n))
                ch.details.append((f'{who}: {choices[k][1].lower()}', show(before.get(k)), show(v)))

    def gear_team_wide(self, choice):
        """Give the open player's value of `choice` to every teammate of his kind (skaters or goalies)."""
        ed = self.ctl.editors

        def work():
            s, pi, p = ed._player()
            kind = EQ.kind_of(p.position)
            if choice not in EQ.TEAM_WIDE or choice not in EQ.KINDS[kind][1]:
                raise EditError(f'{choice} is not shared by a team.')
            team = self.ctl.team
            row = EQ.row_of(s.db, p.game_id, kind)
            if row is None or team is None or team == L.FREE_AGENTS:
                raise EditError('Pick a player of a team first.')
            value = EQ.read(s.db, row, kind)[choice]
            rows = []
            for m in s.players_of(team):
                try:
                    mp = F.Player(s.db, m)
                except KeyError:
                    continue
                r = EQ.row_of(s.db, mp.game_id, kind) if EQ.kind_of(mp.position) == kind else None
                if r is not None:
                    rows.append(r)
            label = EQ.KINDS[kind][1][choice][1]

            def apply(setter):
                return sum(EQ.write(s.db, r, {choice: value}, kind, setter) for r in rows)
            ch, n = s.edit(f'{s.team_abbr(team)}: {label.lower()} for the team', apply)
            ch.details.append((f'{s.team_abbr(team)} {label.lower()}', 'per player', f'{n} player(s) changed'))
            return f'{label}: {n} teammate(s) changed (not saved yet).' if n else 'The whole team has it already.'
        return ed._run(work, 'equipment')

    def snap_player(self):
        """The open player's gear (beta1's equipment slice, 'player'), or None. Call it under the lock."""
        c = self.ctl
        s = c.session
        if s is None or c.player is None:
            return None
        try:
            p = F.Player(s.db, c.player)
        except KeyError:
            p = None
        kind = EQ.kind_of(p.position) if p else None
        row = EQ.row_of(s.db, p.game_id, kind) if p else None
        if row is None:
            return None
        values = EQ.read(s.db, row, kind)
        return {
            'id': c.player, 'name': s.name(s.rows['exhibitionplayerbiotable'][p.bio]), 'kind': kind,
            'values': {k: (_hex(v) if k in EQ.COLOUR_CHOICES else v) for k, v in values.items()},
            'choices': [{'key': k, 'label': label, 'colour': k in EQ.COLOUR_CHOICES,
                         'team_wide': k in EQ.TEAM_WIDE,
                         'options': [] if names is None else
                         [[n, lab] for n, lab in EQ.options(kind, k, values[k])]}
                        for k, (_f, label, names) in EQ.KINDS[kind][1].items()],
        }
