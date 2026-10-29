"""A player's type (playing style) and face in NHL 19. Ported from PS3 Legacy (`faces.py`, `ratings.STYLES`,
`Builder.set_style`).

Type: `playerstyle` on the player's exhibitionskaterai or exhibitiongoalieai record and on his exhibitionrostertable
entry (a copy; 8780 of the default roster's 8846 entries agree). Defencemen 1-4, forwards 5-10, goalies 0-2: the
game's PlayerTypeId enum (boot service defs job/lines/line.json: DEFENSIVE_DEFENSEMAN=0 ... ENFORCER=9, STAND_UP=10,
HYBRID=11, BUTTERFLY=12) one up for skaters and ten down for goalies, the same numbers as Legacy. The skill_* values
(OVR and the rest) are, per type, a straight line of the c_* ratings (ratings.Model): `set_type` works them out again
when it is given the table's model, as the game's own roster has them.

Face (exhibitionplayerbiotable): headid (the 3D head; headtexture equals it on every default-roster player and is
written with it), hairid, haircolorcode, eyebrowid, eyebrowcolorcode, skincolor, eyecolorcode and the playoff beard.
Unlike Legacy, the hair is its own part (199 heads are worn with more than one hair). NHL 19 has no table of heads
(Legacy's stockplayerheads), so the parts the game can draw are taken as those worn on its default roster (`parts`:
541 heads, 209 of them generic from 60000; 57 hairs); the colours run as the default roster has them
(docs/notes/editors.md).
"""
PLAYERS, BIOS, ROSTER = 'exhibitionplayers', 'exhibitionplayerbiotable', 'exhibitionrostertable'
SKATERS, GOALIES = 'exhibitionskaterai', 'exhibitiongoalieai'
GOALIE, DEFENCE = 4, 3  # bio position
GENERIC = 60000         # head ids from here on are the game's generic heads
STYLE = 'playerstyle'

TYPES = {1: ('DFD', 'Defensive defenceman'), 2: ('OFD', 'Offensive defenceman'), 3: ('END', 'Enforcer defenceman'),
         4: ('TWD', 'Two-way defenceman'), 5: ('GRN', 'Grinder'), 6: ('PLY', 'Playmaker'), 7: ('SNP', 'Sniper'),
         8: ('PWF', 'Power forward'), 9: ('TWF', 'Two-way forward'), 10: ('ENF', 'Enforcer')}
GOALIE_TYPES = {0: ('STD', 'Stand-up'), 1: ('HYB', 'Hybrid'), 2: ('BUT', 'Butterfly')}
TYPE_CHOICES = {'F': (5, 6, 7, 8, 9, 10), 'D': (1, 2, 3, 4), 'G': (0, 1, 2)}

FACE = {'head': 'headid', 'hair': 'hairid', 'hair_colour': 'haircolorcode', 'brows': 'eyebrowid',
        'brow_colour': 'eyebrowcolorcode', 'skin': 'skincolor', 'eyes': 'eyecolorcode', 'beard': 'playoffbeardtype',
        'beard_colour': 'playoffbeardcolor'}
PARTS = ('head', 'hair', 'brows', 'beard')  # ids: only those worn on the game's own roster
COLOURS = {'skin': range(1, 11), 'eyes': range(0, 7), 'hair_colour': range(0, 14), 'brow_colour': range(0, 14),
           'beard_colour': range(0, 14)}
WORDS = {'head': 'head', 'hair': 'hair', 'hair_colour': 'hair colour', 'brows': 'eyebrows',
         'brow_colour': 'eyebrow colour', 'skin': 'skin colour', 'eyes': 'eye colour', 'beard': 'playoff beard',
         'beard_colour': 'beard colour'}


# --- type ---------------------------------------------------------------------------------------
def type_class(position):
    """'F', 'D' or 'G' for a bio position (0 C, 1 LW, 2 RW, 3 D, 4 G)."""
    return 'G' if position == GOALIE else 'D' if position == DEFENCE else 'F'


def type_name(style, goalie=False):
    """('SNP', 'Sniper') of a type number, or None."""
    return (GOALIE_TYPES if goalie else TYPES).get(style)


def type_label(style, goalie=False):
    name = type_name(style, goalie)
    return f'{name[0]} · {name[1]}' if name else f'Type {style}'


def type_choices(position):
    """[(type number, label)] a player of this position may have."""
    kind = type_class(position)
    return [(s, type_label(s, kind == 'G')) for s in TYPE_CHOICES[kind]]


class Player:
    """Where one player (exhibitionplayers index) is kept: his bio row, his ratings table and row, his roster rows."""

    def __init__(self, db, pi):
        P = db[PLAYERS]
        prow = next((i for i in range(P.count) if P.get(i, 'index') == pi), None)
        if prow is None or P.get(prow, 'table') != 0:
            raise KeyError(f'no player {pi}')
        gid = P.get(prow, 'playerid')
        B = db[BIOS]
        self.pi, self.game_id = pi, gid
        self.bio = next((i for i in range(B.count) if B.get(i, 'game_id') == gid), None)
        if self.bio is None:
            raise KeyError(f'player {pi} has no bio record')
        self.position = B.get(self.bio, 'position')
        self.ai_table = GOALIES if self.position == GOALIE else SKATERS
        A = db[self.ai_table]
        self.ai = next((i for i in range(A.count) if A.get(i, 'game_id') == gid), None)
        R = db[ROSTER]
        self.entries = [i for i in range(R.count) if R.get(i, 'playerindex') == pi]


def set_type(db, pi, style, setter=None, model=None):
    """Give player `pi` another type: on his ratings record and his roster entries; with `model` (ratings.Model of
    his ratings table) his skill_* follow. ValueError when the type does not fit his position. Returns
    [(table, row, field, old, new)] of what changed."""
    p = Player(db, pi)
    kind = type_class(p.position)
    if style not in TYPE_CHOICES[kind]:
        raise ValueError(f'type {type_label(style, kind == "G")} does not fit a {"goalie" if kind == "G" else "defenceman" if kind == "D" else "forward"}')
    if p.ai is None:
        raise ValueError('this player has no ratings record')
    set_ = setter or (lambda table, row, field, value: db[table].set(row, field, value))
    out = []

    def put(table, row, field, value):
        old = db[table].get(row, field)
        if old != value:
            set_(table, row, field, value)
            out.append((table, row, field, old, value))
    put(p.ai_table, p.ai, STYLE, style)
    for e in p.entries:
        put(ROSTER, e, STYLE, style)
    if model is not None:
        for field, value in model.predict(db[p.ai_table].row(p.ai)).items():
            put(p.ai_table, p.ai, field, value)
    return out


def type_problems(db):
    """Players whose type does not fit their position (a centre moved to defence keeps his forward type)."""
    B, out = db[BIOS], []
    pos = {B.get(i, 'game_id'): B.get(i, 'position') for i in range(B.count)}
    for table in (SKATERS, GOALIES):
        A = db[table]
        for i in range(A.count):
            gid = A.get(i, 'game_id')
            if gid not in pos:
                continue
            kind, style = type_class(pos[gid]), A.get(i, STYLE)
            if style not in TYPE_CHOICES[kind]:
                out.append((gid, f'type {type_label(style, kind == "G")} does not fit his position'))
    return out


# --- face ---------------------------------------------------------------------------------------
def read(bio):
    """{part: value} of a bio record (dict)."""
    return {key: bio[field] for key, field in FACE.items()}


def write(db, brow, face, setter=None):
    """Set the parts of `face` (any FACE keys) on bio row `brow`; the head texture follows the head. Returns the
    number of fields changed."""
    unknown = [k for k in face if k not in FACE]
    if unknown:
        raise KeyError(f'no face part {unknown[0]!r}')
    set_ = setter or (lambda table, row, field, value: db[table].set(row, field, value))
    B, n = db[BIOS], 0
    fields = [(FACE[k], int(v)) for k, v in face.items()]
    if 'head' in face:
        fields.append(('headtexture', int(face['head'])))
    for field, value in fields:
        if B.get(brow, field) != value:
            set_(BIOS, brow, field, value)
            n += 1
    return n


def parts(db):
    """{part: set of ids} worn on a roster: of the game's default roster, the parts the game can draw."""
    B = db[BIOS]
    return {key: {B.get(i, FACE[key]) for i in range(B.count)} for key in PARTS}


def generic(valid):
    """The generic heads of `valid` (parts()), lowest first."""
    return sorted(h for h in valid['head'] if h >= GENERIC)


def wrong(face, valid):
    """What in `face` the game cannot show (`valid`: parts() of the default roster), as words, or None."""
    for key in PARTS:
        if key in face and valid and face[key] not in valid[key]:
            return f'{WORDS[key]} {face[key]} is not one the game has'
    for key, allowed in COLOURS.items():
        if key in face and face[key] not in allowed:
            return f'{WORDS[key]} {face[key]} is not {allowed.start}-{allowed.stop - 1}'
    return None


def problems(db, valid, before=None):
    """[(game_id, words)] of faces the game cannot show. With `before` (the roster an edit or update started from), a
    part that player already had there is not blamed."""
    old = {}
    if before is not None:
        old = {r['game_id']: read(r) for r in before[BIOS].rows()}
    out = []
    for r in db[BIOS].rows():
        face, was = read(r), old.get(r['game_id'], {})
        changed = {k: v for k, v in face.items() if was.get(k) != v}
        why = wrong(changed, valid)
        if why:
            out.append((r['game_id'], why))
    return out
