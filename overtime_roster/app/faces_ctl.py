"""The Roster tab's Face & type window: the picked player's player type and face. docs/ui/roster.md
(roster_face, calls roster_face_*).

Picks wait here per player (`picks`) until Apply to this player, which writes the type and the face as one change
(his ratings follow the type: ratings.Model of his table). Closing the window keeps them; Save asks about them
(RosterCtl.drafts) and the rail shows the team's dot (RosterCtl.dirty). Take back drops the picks and takes back his
applied face and type edits (RosterCtl.take_back). The lists hold what the game's own default roster wears
(EditorsController.default), plus what he wears now. Beta1's edits (type_set, face_set, face_copy) and their snapshot
(snap_faces) stay as before.
"""
from overtime_core import faces as F

from . import roster_card as RC
from .registry import Part
from .session import EditError

FOUND_MAX = 60


class FacesCtl(Part):
    SLICES = {'roster_face': 'view'}
    CALLS = {'roster_face_open': 'open_window', 'roster_face_close': 'close', 'roster_face_search': 'search',
             'roster_face_pick': 'pick', 'roster_face_type': 'pick_type', 'roster_face_copy': 'copy',
             'roster_face_apply': 'apply', 'roster_face_undo': 'take_back',
             'type_set': 'type_set', 'face_set': 'face_set', 'face_copy': 'face_copy'}

    def __init__(self, ctl):
        super().__init__(ctl)
        self.open = None        # the player the window shows (None: closed)
        self.query = ''
        self.picks = {}        # {pi: {'face': {part: n}, 'style': n, 'from': name}}

    def roster_changed(self):
        self.open, self.query, self.picks = None, '', {}

    # --- reading -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _his(s, pi):
        """(bio, ratings dict or None, ratings table, goalie, style now) of player pi."""
        _, b = s.bio(pi)
        table, _r, ai = s.ai(b)
        style = ai.get(F.STYLE) if ai else None
        return b, ai, table, b['position'] == F.GOALIE, style

    def _move(self, s, table, ai, style):
        """About how much his overall moves with another type (the model of his table)."""
        if not ai or table is None:
            return 0
        model = self.ctl.editors._model(s, table)
        now = model.predict(dict(ai)).get('skill_overall', 0)
        then = model.predict(dict(ai, **{F.STYLE: style})).get('skill_overall', 0)
        return then - now

    def _options(self, current, picks):
        _db, parts, _w, _c = self.ctl.editors.default()
        return {k: sorted(set(parts.get(k, ())) | {current[k], picks.get(k, current[k])}) for k in F.PARTS}

    def view(self):
        c = self.ctl
        with c.lock:
            s, pi = c.session, self.open
            if s is None or pi is None or s.bio(pi)[1] is None:
                return {'open': False}
            roster = c.parts['roster']
            b, ai, table, goalie, style_now = self._his(s, pi)
            d = self.picks.get(pi, {})
            current = F.read(b)
            face = dict(current, **d.get('face', {}))
            style = d.get('style', style_now)
            kind = F.type_class(b['position'])
            choices = []
            for n in F.TYPE_CHOICES[kind]:
                short, label = F.type_name(n, goalie)
                choices.append({'value': n, 'label': label, 'short': short, 'move': self._move(s, table, ai, n)})
            words = RC.plain(self.query).split()
            if words:
                pool = [p for p in RC.find(s, self.query, roster.names(s)) if p != pi]
            else:
                pool = [p for p in s.players_of(RC.rail_team(s, pi)) if p != pi]
            found = []
            for p in pool:
                _, ob = s.bio(p)
                if ob is None:
                    continue
                sm = s.summary(p)
                found.append({'id': p, 'name': sm['name'], 'pos': sm['pos'], 'team': sm['team'],
                              'head': ob['headid'], 'generic': ob['headid'] >= F.GENERIC,
                              'ovr': sm['ovr'] if isinstance(sm['ovr'], int) else 0})
            found.sort(key=lambda r: (r['generic'], -r['ovr'], r['name']))
            done = roster.mine(pi, 'face')
            changed = list(d.get('face', {}))
            picked = bool(changed) or style != style_now
            name = s.name(b)
            return {
                'open': True, 'id': pi, 'name': name, 'goalie': goalie, 'team': c.rail.chip(RC.rail_team(s, pi)),
                'type': {'value': style, 'current': style_now, 'changed': style != style_now,
                         'ovr': roster.ovr_of(s, pi), 'fits': style_now in F.TYPE_CHOICES[kind], 'choices': choices},
                'face': face, 'current': current, 'changed': changed,
                'parts': self._options(current, d.get('face', {})),
                'generic_from': F.GENERIC, 'colours': {k: [r.start, r.stop - 1] for k, r in F.COLOURS.items()},
                'words': dict(F.WORDS), 'from': d.get('from', ''),
                'query': self.query,
                'found': [{k: r[k] for k in ('id', 'name', 'pos', 'team', 'head', 'generic')} for r in found[:FOUND_MAX]],
                'found_title': f'{len(found)} found' if words else 'His teammates',
                'can_apply': picked, 'can_take_back': picked or bool(done),
                'note': f'{name} has a generic head: the game draws a stand-in face.'
                        if current['head'] >= F.GENERIC else '',
                'busy': bool(c.busy),
            }

    # --- the window's calls ------------------------------------------------------------------------------------------
    def _who(self):
        """The window's player, or the card's; None (and the Help bar says so) without one. Under the lock."""
        c = self.ctl
        pi = self.open if self.open is not None else c.player
        if c.session is None or pi is None or c.session.bio(pi)[1] is None:
            c.say('Pick a player first.', 'caution')
            return None
        return pi

    def _pushed(self):
        self.ctl.changed('roster_face', 'roster_card', 'rail')

    def _tidy(self, s, pi):
        d = self.picks.get(pi)
        if d is not None and not d.get('face') and ('style' not in d or d['style'] == self._his(s, pi)[4]):
            del self.picks[pi]

    def open_window(self):
        c = self.ctl
        with c.lock:
            if c.session is None or c.player is None:
                c.say('Pick a player first.', 'caution')
                return {'ok': False}
            self.open, self.query = c.player, ''
        c.changed('roster_face')
        return {'ok': True}

    def close(self):
        with self.ctl.lock:
            self.open = None
        self.ctl.changed('roster_face')
        return {'ok': True}

    def search(self, text):
        with self.ctl.lock:
            if self.open is None:
                return {'ok': False}
            self.query = str(text or '')
        self.ctl.changed('roster_face')
        return {'ok': True}

    def pick(self, part, value):
        """Hold one part (head, hair, brows, beard, a colour) until Apply."""
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            current = F.read(s.bio(pi)[1])
            d = self.picks.setdefault(pi, {})
            face = d.setdefault('face', {})
            try:
                n = int(value)
            except (TypeError, ValueError):
                n = None
            why = ''
            if part not in F.FACE or n is None:
                why = 'That is not a face part.'
            elif part in F.PARTS and n not in self._options(current, face)[part]:
                why = f'{F.WORDS[part].capitalize()} {n} is not one the game has.'
            elif part in F.COLOURS and n not in F.COLOURS[part]:
                r = F.COLOURS[part]
                why = f'{F.WORDS[part].capitalize()}: {r.start}-{r.stop - 1}.'
            if not why:
                if n == current[part]:
                    face.pop(part, None)
                else:
                    face[part] = n
                d.pop('from', None)
            self._tidy(s, pi)
        if why:
            c.say(why, 'bad')
            return {'ok': False}
        self._pushed()
        return {'ok': True}

    def pick_type(self, style):
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            b, _ai, _t, _g, now = self._his(s, pi)
            try:
                n = int(style)
            except (TypeError, ValueError):
                n = None
            ok = n in F.TYPE_CHOICES[F.type_class(b['position'])]
            if ok:
                d = self.picks.setdefault(pi, {})
                if n == now:
                    d.pop('style', None)
                else:
                    d['style'] = n
                self._tidy(s, pi)
        if not ok:
            c.say('That type is not one for his position.', 'bad')
            return {'ok': False}
        self._pushed()
        return {'ok': True}

    def copy(self, ident):
        """Hold another player's whole face."""
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            try:
                src = s.bio(int(ident))[1]
            except (TypeError, ValueError):
                src = None
            if src is None:
                c.say('Pick a player to take the face from.', 'caution')
                return {'ok': False}
            current = F.read(s.bio(pi)[1])
            d = self.picks.setdefault(pi, {})
            d['face'] = {k: v for k, v in F.read(src).items() if v != current[k]}
            d['from'] = s.name(src)
            self._tidy(s, pi)
            text = f"{s.name(src)}'s face is picked for {s.name(s.bio(pi)[1])}. Press Apply to this player to keep it."
        c.say(text)
        self._pushed()
        return {'ok': True}

    def apply(self):
        """Type and face as one change (his ratings follow the type)."""
        c = self.ctl
        roster = c.parts['roster']
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            s = c.session
            d = self.picks.get(pi)
            if not d:
                c.say('Nothing to apply: pick a type or a face part first.', 'caution')
                return {'ok': False}
            b, _ai, table, goalie, style_now = self._his(s, pi)
            brow, _b = s.bio(pi)
            name, ovr = s.name(b), roster.ovr_of(s, pi)
            face, style = dict(d.get('face') or {}), d.get('style')
            before = F.read(b)
            model = c.editors._model(s, table) if style is not None and table else None

            def work(setter):
                if style is not None:
                    F.set_type(s.db, pi, style, setter, model)
                    for t, row in RC.style_rows(s, pi):   # his other cards (All-Stars, Seattle) carry the type too
                        if F.STYLE in s.db[t].by_name:
                            setter(t, row, F.STYLE, style)
                if face:
                    F.write(s.db, brow, face, setter)
            try:
                ch, _ = s.edit(f'{name}: face & type', work)
            except EditError as err:
                text = f'{name}: {err}'
                c.say(text, 'bad')
                return {'ok': False, 'error': text}
            words, short = [], []
            if style is not None:
                now = roster.ovr_of(s, pi)
                old_t, new_t = F.type_name(style_now, goalie), F.type_name(style, goalie)
                words.append(f"type {old_t[0] if old_t else 'none'} to {new_t[0]}"
                             + (f' (overall {ovr} to {now})' if now != ovr else ''))
                ch.details.append((f'{name}: player type', F.type_label(style_now, goalie) if old_t else 'none',
                                   F.type_label(style, goalie)))
                short.append('type')
            if face:
                if d.get('from'):
                    words.append(f"{d['from']}'s face")
                else:
                    words.append('face: ' + ', '.join(f'{F.WORDS[k]} {before[k]} to {v}' for k, v in face.items()))
                for k, v in face.items():
                    ch.details.append((f'{name}: {F.WORDS[k]}', before[k], v))
                short.append('face')
            ch.label = f"{name}: {'; '.join(words)}"
            roster.note(ch, pi, 'face', short, short, kept=(['style'] if style is not None else []) + list(face))
            del self.picks[pi]
            c.issues = None
            c.editors._logged(ch, c.host)
            text = f'{ch.label}. Not saved yet.'
        c.say(text, 'good')
        c.changed('editor', 'lines', 'save', 'roster_face')
        return {'ok': True}

    def take_back(self):
        """Drop the picks and take back his applied face and type edits."""
        c = self.ctl
        with c.lock:
            pi = self._who()
            if pi is None:
                return {'ok': False}
            had = self.picks.pop(pi, None) is not None
            taken, blocked = c.parts['roster'].take_back(pi, 'face')
            name = c.parts['roster'].who(c.session, pi)
        if blocked:
            c.say(f'{name}: take back "{blocked}" first (My edits). It changed him later.', 'caution')
        elif taken:
            c.say(f'{name} has his face and type back from before your edits.', 'good')
        elif had:
            c.say(f'Your face and type picks for {name} are gone. Nothing was applied.')
        else:
            c.say(f"Nothing to take back: {name}'s face and type are as they were.")
        c.changed('editor', 'lines', 'save', 'roster_face')
        return {'ok': not blocked, 'taken': taken}

    # --- beta1's edits -----------------------------------------------------------------------------------------------
    def type_set(self, style):
        ed = self.ctl.editors

        def work():
            s, pi, p = ed._player()
            who = s.name(s.bio(pi)[1])
            goalie = p.position == F.GOALIE
            old = s.db[p.ai_table].get(p.ai, F.STYLE) if p.ai is not None else None
            model = ed._model(s, p.ai_table)
            ch, _ = s.edit(f'{who}: player type', lambda setter: F.set_type(s.db, pi, int(style), setter, model))
            ch.details.append((f'{who}: player type', F.type_label(old, goalie), F.type_label(int(style), goalie)))
            ed._logged(ch, self.ctl.host)
            return f'{who} is now a {F.type_label(int(style), goalie)} (OVR follows; not saved yet).'
        return ed._run(work)

    def face_set(self, values):
        ed = self.ctl.editors

        def work():
            s, pi, p = ed._player()
            _db, parts, _worn, _c = ed.default()
            face = {}
            for k, v in (values or {}).items():
                if k not in F.FACE:
                    raise EditError(f'Unknown face part {k}.')
                try:
                    face[k] = int(v)
                except (TypeError, ValueError):
                    raise EditError(f'{F.WORDS[k].capitalize()}: {v!r} is not a number.') from None
            why = F.wrong(face, parts)
            if why:
                raise EditError(f'The game cannot show this: {why}.')
            b = s.rows['exhibitionplayerbiotable'][p.bio]
            who, before = s.name(b), F.read(b)
            ch, n = s.edit(f'{who}: face', lambda setter: F.write(s.db, p.bio, face, setter))
            for k, v in face.items():
                if before[k] != v:
                    ch.details.append((f'{who}: {F.WORDS[k]}', before[k], v))
            ed._logged(ch, self.ctl.host)
            return f'{who}: face changed ({n} value(s); not saved yet).' if n else 'Nothing changed.'
        return ed._run(work, 'faces')

    def face_copy(self, ident):
        ed = self.ctl.editors

        def work():
            s, pi, p = ed._player()
            try:
                src = F.Player(s.db, int(ident))
            except (KeyError, TypeError, ValueError):
                raise EditError('No such player to copy the face from.') from None
            face = F.read(s.rows['exhibitionplayerbiotable'][src.bio])
            other = s.name(s.rows['exhibitionplayerbiotable'][src.bio])
            who = s.name(s.rows['exhibitionplayerbiotable'][p.bio])
            ch, n = s.edit(f"{who}: {other}'s face", lambda setter: F.write(s.db, p.bio, face, setter))
            ch.details.append((f'{who}: face', 'own', f"{other}'s"))
            ed._logged(ch, self.ctl.host)
            return f"{who} has {other}'s face now (not saved yet)." if n else 'Same face already.'
        return ed._run(work, 'faces')

    def snap_faces(self):
        c = self.ctl
        with c.lock:
            if not c.session or c.player is None:
                return {'ready': False}
            s = c.session
            try:
                p = F.Player(s.db, c.player)
            except KeyError:
                return {'ready': False}
            b = s.rows['exhibitionplayerbiotable'][p.bio]
            goalie = p.position == F.GOALIE
            style = s.db[p.ai_table].get(p.ai, F.STYLE) if p.ai is not None else None
            _db, parts, _w, _c = c.editors.default()
            mates = [m for m in (s.players_of(c.team) if c.team is not None else []) if m != c.player]
            face = F.read(b)
            return {
                'ready': True, 'player': c.player, 'name': s.name(b), 'goalie': goalie,
                'type': style, 'type_label': F.type_label(style, goalie) if style is not None else '',
                'types': [[n, label] for n, label in F.type_choices(p.position)],
                'type_ok': style in F.TYPE_CHOICES[F.type_class(p.position)],
                'face': face,
                'parts': {k: sorted(v | {face[k]}) for k, v in parts.items()},
                'generic': face['head'] >= F.GENERIC,
                'colours': {k: [r.start, r.stop - 1] for k, r in F.COLOURS.items()},
                'words': F.WORDS,
                'wrong': F.wrong(face, parts) or '',
                'mates': [{'id': m, 'label': f"{s.summary(m)['pos']} #{s.summary(m)['num']} {s.summary(m)['name']}"}
                          for m in mates],
            }
