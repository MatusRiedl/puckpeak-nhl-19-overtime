"""My edits: the Roster tab's player edits, kept in edits.json (the app folder) when Save writes them and put back
after every Update (Go and Apply), as Legacy's edits.json. docs/ui/update.md "My edits".

A kept edit is one player's: `id` is who he was before his first kept edit (first, last, real birth date: the person
key the update's matcher knows him by), `label` his name now. It holds the latest value of everything that was
changed: `card` {key: value} in the card's units (roster_card.values; ratings as 'ratings': {field: value}), `face`
{'style': type, 'parts': {part: value}}, `gear` {choice: value}. A renamed player is still found (every mix of his old
and new name and birth date), and the update's plan matches him to NHL.com under his old name (`aliases`).

It is put back through the Roster tab's own checks and writers (roster_card.check / write, faces, equipment), one
change per part: a part the roster refuses changes nothing and is skipped with its reason (a card value that is
refused, such as a number another player has now, is skipped alone; the rest of the card goes in).
"""
import json
import os

from overtime_core import equipment as EQ, faces as F, rosterupdate as U

from . import labels as L, paths, roster_card as RC
from .session import EditError

VERSION = 1
FILE = 'edits.json'
PARTS = ('card', 'face', 'gear')
PART_WORDS = {'card': 'card', 'face': 'face & type', 'gear': 'equipment'}
NAME_KEYS = ('first', 'last', 'born')


# --- the file ------------------------------------------------------------------------------------------------------
def where():
    return paths.app_dir(FILE)


def empty():
    return {'version': VERSION, 'players': {}}


def load(path=None):
    """edits.json, or an empty one (no file, or one this version cannot read)."""
    try:
        with open(path or where(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict) or data.get('version') != VERSION or not isinstance(data.get('players'), dict):
        return empty()
    data['players'] = {k: e for k, e in data['players'].items()
                       if isinstance(e, dict) and isinstance(e.get('id'), dict)}
    return data


def save(data, path=None):
    """Write edits.json whole or not at all (a temporary file, then a rename)."""
    path = path or where()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


# --- who a player is -----------------------------------------------------------------------------------------------
def plain_name(first, last):
    return ' '.join(RC.plain(f'{first or ""} {last or ""}').split())


def person_key(first, last, born):
    return f"{plain_name(first, last)}|{born or ''}"


def identity(s, clock, pi):
    """{'first', 'last', 'born'} of player pi now (born: his real birth date, as on the card)."""
    _, b = s.bio(pi)
    return {'first': b['firstname'], 'last': b['lastname'], 'born': clock.born(b)}


def keys_of(e):
    """The person keys he may have now, newest first: his new name and birth date, either one alone, his old ones (an
    update puts NHL.com's birth date back but leaves a name alone)."""
    i, card = e['id'], e.get('card') or {}
    names = [(card.get('first', i['first']), card.get('last', i['last'])), (i['first'], i['last'])]
    borns = [card.get('born', i['born']), i['born']]
    out = []
    for first, last in names:
        for born in borns:
            k = person_key(first, last, born)
            if k not in out:
                out.append(k)
    return out


def index(s, clock):
    """({person key: playerindex}, {plain name: [playerindex]}) of every player of the roster (his main card:
    rosterupdate.State.main_pi)."""
    state = U.State(s.db)
    keys, names = {}, {}
    for gid in s.bio_row:
        pi = state.main_pi(gid)
        if pi is None:
            continue
        _, b = s.bio(pi)
        if b is not None:
            keys.setdefault(person_key(b['firstname'], b['lastname'], clock.born(b)), pi)
            names.setdefault(plain_name(b['firstname'], b['lastname']), []).append(pi)
    return keys, names


def locate(e, found):
    """The playerindex of the player of kept edit `e` in the roster (`found`: index()), or None: one of his person
    keys, else his name alone when one player of the roster has it (a birth date read on another clock)."""
    keys, names = found
    mine = keys_of(e)
    pi = next((keys[k] for k in mine if k in keys), None)
    if pi is None:
        for k in mine:
            hits = names.get(k.split('|')[0], ())
            if len(hits) == 1:
                return hits[0]
    return pi


def aliases(data, s, clock):
    """{game_id: (first, last, real birth date or None)} of the kept players whose name or birth date the user
    changed: the update's plan matches them to NHL.com as they were (rosterupdate.plan `aliases`), so a renamed player
    is not released. The birth date only when it was changed (else the roster's own stored one matches)."""
    found = index(s, clock)
    out = {}
    for e in data['players'].values():
        i, card = e['id'], e.get('card') or {}
        renamed = (plain_name(card.get('first', i['first']), card.get('last', i['last']))
                   != plain_name(i['first'], i['last']))
        reborn = card.get('born', i['born']) != i['born']
        if not (renamed or reborn):
            continue
        pi = locate(e, found)
        if pi is None:
            continue
        _, b = s.bio(pi)
        out[b['game_id']] = (i['first'], i['last'], i['born'] if reborn and i['born'] else None)
    return out


def find(data, ident):
    """The key of the kept edit of the player who is `ident` now, or None."""
    k = person_key(ident['first'], ident['last'], ident['born'])
    return next((key for key, e in data['players'].items() if k in keys_of(e)), None)


# --- keeping them --------------------------------------------------------------------------------------------------
def record(data, s, clock, items):
    """Keep the edits `items` ([{pi, what, kept, ident}]: roster_card.Edits items Save just wrote; ident: who he was
    before that edit) with the values he has now. Returns how many players' edits changed."""
    touched = set()
    for it in items:
        pi = it['pi']
        _, b = s.bio(pi)
        if b is None or it['what'] not in PARTS:
            continue
        ident = it.get('ident') or identity(s, clock, pi)
        key = find(data, ident) or find(data, identity(s, clock, pi))
        if key is None:
            key = person_key(ident['first'], ident['last'], ident['born'])
            data['players'][key] = {'id': dict(ident)}
        e = data['players'][key]
        _keep(e, s, clock, pi, b, it['what'], it.get('kept', it['keys']))
        e['label'] = s.name(b)
        team = RC.rail_team(s, pi)
        e['team'] = s.team_abbr(team) or str(team)
        touched.add(key)
    return len(touched)


def _keep(e, s, clock, pi, b, what, keys):
    if what == 'card':
        now = RC.values(s, clock, pi)
        card = e.setdefault('card', {})
        for k in keys:
            if k.startswith('ratings.'):
                f = k[len('ratings.'):]
                if f in now['ratings']:
                    card.setdefault('ratings', {})[f] = now['ratings'][f]
            elif k in now:
                card[k] = now[k]
    elif what == 'face':
        face = e.setdefault('face', {})
        _t, _r, ai = s.ai(b)
        if 'style' in keys and ai:
            face['style'] = ai.get(F.STYLE)
        parts = {k: v for k, v in F.read(b).items() if k in keys}
        if parts:
            face.setdefault('parts', {}).update(parts)
    elif what == 'gear':
        kind = EQ.kind_of(b['position'])
        row = EQ.row_of(s.db, b['game_id'], kind)
        if row is not None:
            now = EQ.read(s.db, row, kind)
            e.setdefault('gear', {}).update({k: now[k] for k in keys if k in now})


def forget(data, s, clock, items):
    """Drop what the taken-back edits `items` kept (saved earlier, then taken back and saved again), unless a later
    edit still keeps it. Returns how many players' edits changed."""
    touched = set()
    for it in items:
        key = find(data, it.get('ident') or {}) if it.get('ident') else None
        if key is None and s.bio(it['pi'])[1] is not None:
            key = find(data, identity(s, clock, it['pi']))
        e = data['players'].get(key) if key else None
        if e is None:
            continue
        part = e.get(it['what'])
        if not isinstance(part, dict):
            continue
        for k in it.get('kept', it['keys']):
            if it['what'] == 'card' and k.startswith('ratings.'):
                (part.get('ratings') or {}).pop(k[len('ratings.'):], None)
                if part.get('ratings') == {}:
                    part.pop('ratings')
            elif it['what'] == 'face' and k != 'style':
                (part.get('parts') or {}).pop(k, None)
                if part.get('parts') == {}:
                    part.pop('parts')
            else:
                part.pop(k, None)
        if not part:
            e.pop(it['what'])
        if not any(p in e for p in PARTS):
            del data['players'][key]
        touched.add(key)
    return len(touched)


def remove(data, key):
    return data['players'].pop(key, None) is not None


def words(e):
    """['number #94', 'cap hit $1.5M', '3 ratings', 'face & type', 'equipment'] of one kept edit."""
    out = []
    card = e.get('card') or {}
    for k in RC.ORDER:
        if k in card:
            out.append(f'{RC.WORDS[k]} {RC.shown(k, card[k])}')
    n = len(card.get('ratings') or {})
    if n:
        out.append('1 rating' if n == 1 else f'{n} ratings')
    face = e.get('face') or {}
    if 'style' in face:
        out.append('player type')
    if face.get('parts'):
        out.append('face')
    if e.get('gear'):
        out.append('equipment')
    return out


def rows(data):
    """The list of kept edits, by last name: [{key, label, team, words}]."""
    def last(k):
        e = data['players'][k]
        return RC.plain((e.get('card') or {}).get('last', e['id']['last']))
    out = [{'key': k, 'label': e.get('label') or f"{e['id']['first']} {e['id']['last']}", 'team': e.get('team', ''),
            'words': words(e)} for k, e in data['players'].items()]
    return sorted(out, key=lambda r: (last(r['key']), RC.plain(r['label']), r['key']))


# --- putting them back ---------------------------------------------------------------------------------------------
def replay(s, clock, data, model_of=lambda table: None, fold=lambda ch: None):
    """Put every kept edit back in the open roster (after an update). Each part of a player is one change (s.edit),
    handed to `fold` (the update folds them into its own change, so one Undo takes both back). Returns {'applied': n
    parts, 'skipped': [{'who', 'part', 'why'}]}."""
    found = index(s, clock)
    out = {'applied': 0, 'skipped': []}
    for e in sorted(data['players'].values(), key=lambda e: RC.plain(e.get('label') or e['id']['last'])):
        who = e.get('label') or f"{e['id']['first']} {e['id']['last']}"
        pi = locate(e, found)
        if pi is None:
            out['skipped'].append({'who': who, 'part': 'player', 'why': 'He is not in this roster.'})
            continue
        for part in PARTS:
            if not e.get(part):
                continue
            try:
                went, refused = _put(s, clock, pi, part, e[part], model_of, fold)
            except EditError as err:
                went, refused = False, [str(err)]
            out['applied'] += went
            out['skipped'] += [{'who': who, 'part': PART_WORDS[part], 'why': why} for why in refused]
    return out


def _put(s, clock, pi, part, value, model_of, fold):
    """Put one part back: (it went in, or was already so; [why] of each value refused)."""
    _, b = s.bio(pi)
    who = s.name(b)
    if part == 'card':
        typed = dict(value)
        changes, problems = RC.check(s, clock, pi, typed)
        refused = [p['text'] for p in problems]
        if problems:   # the card's other values still go in
            for p in problems:
                if p['key'].startswith('ratings.'):
                    typed['ratings'] = {f: v for f, v in typed.get('ratings', {}).items()
                                        if f'ratings.{f}' != p['key']}
                else:
                    typed.pop(p['key'], None)
            changes, _again = RC.check(s, clock, pi, typed)
        if changes:
            table, _r, _ai = s.ai(b)
            rated = any(k.startswith('ratings.') for k, _o, _n in changes)
            model = model_of(table) if rated and table else None
            ch, _lost = s.edit(f'My edits: {who}', lambda setter: RC.write(s, clock, pi, changes, setter, model))
            for k, old, new in changes:
                if k.startswith('ratings.'):
                    ch.details.append((f'My edits: {who}: {L.rating_label(k[len("ratings."):]).lower()}', old, new))
                else:
                    ch.details.append((f'My edits: {who}: {RC.WORDS[k]}', RC.shown(k, old), RC.shown(k, new)))
            fold(ch)
        return bool(changes) or not problems, refused
    if part == 'face':
        style, parts = value.get('style'), dict(value.get('parts') or {})

        def work(setter):
            if style is not None:
                F.set_type(s.db, pi, int(style), setter, model_of(s.ai(b)[0]))
                for t, row in RC.style_rows(s, pi):
                    if F.STYLE in s.db[t].by_name:
                        setter(t, row, F.STYLE, int(style))
            if parts:
                F.write(s.db, s.bio(pi)[0], parts, setter)
        ch, _ = s.edit(f'My edits: {who}: face & type', work)
        ch.details.append((f'My edits: {who}', '', 'face & type'))
        fold(ch)
        return True, []
    if part == 'gear':
        kind = EQ.kind_of(b['position'])
        row = EQ.row_of(s.db, b['game_id'], kind)
        if row is None:
            return False, ['He has no equipment record.']
        ok, problems = EQ.clean(s.db, value, kind)
        if problems:
            return False, problems
        ch, _ = s.edit(f'My edits: {who}: equipment', lambda setter: EQ.write(s.db, row, ok, kind, setter))
        ch.details.append((f'My edits: {who}', '', 'equipment'))
        fold(ch)
        return True, []
    return False, [f'unknown part {part}']
