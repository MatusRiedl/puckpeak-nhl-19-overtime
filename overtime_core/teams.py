"""NHL 19's teams set up as the 2026-27 league: Arizona's slot becomes Utah, the game's own 32nd team becomes Seattle.

    Utah      exhibitionteams 22 (Arizona Coyotes): names, abbreviation and colours of the Utah Mammoth, moved from the
              Pacific to the Central. The art stays Arizona's (artabbr 'PHX': the loc text and logos are keyed by it).
    Seattle   customteams 499 ("BURNABY NHL 32"): the team a Franchise with the 32-team expansion makes league team 31
              (run X1). Names, abbreviation, colours, Pacific. Its AHL club, customteams 498 ("Aces", league team 63 in
              that Franchise), becomes the Coachella Valley Firebirds.
    Play Now  exhibitionteams 399 ("NHL 32", the game's inactive copy of the expansion team, art id 10499 like 499):
              Seattle again, moved into the NHL league (0) and made active, so Play Now lists it; its players are
              customrostertable's team 499 through their own exhibitionplayers records (rosterupdate.mirror_seattle,
              as the All-Star teams have theirs). exhibitionteams is in the `rosterupdate` savegroup: this copy of
              Seattle travels in the online roster too.
    Arenas    exhibitionarena 22 becomes the Delta Center, customarena 499 Climate Pledge Arena (with Seattle's city:
              the game resets a custom arena's '$BURNABY' to '$ABBOTSFORD' when the team is saved in the Creation
              Zone, run x2-20261016/run6), customarena 498 Acrisure Arena, exhibitionarena 399 Climate Pledge Arena.

customteams is in the `rosters` / `custom` savegroups (not in `rosterupdate`): Seattle's team 499 travels in a custom
roster save, not in the online roster (exhibitionteams 399 does). Seattle's draftees keep `draftteam` -1 (the field is 5 bits: -1..30).
Colours are 0xRRGGBB; the Kraken's and the Mammoth's are the clubs' published ones, the Firebirds' approximate.
"""
from .calendar import SLOTS

PACIFIC, CENTRAL, ATLANTIC, METROPOLITAN = 8, 9, 10, 11  # divisiongroup (stock data)
WEST, EAST = 6, 7  # conferencegroup
CONFERENCE = {PACIFIC: WEST, CENTRAL: WEST, ATLANTIC: EAST, METROPOLITAN: EAST}
DIVISIONS_2026 = {
    PACIFIC: ('ANA', 'CGY', 'EDM', 'LAK', 'SEA', 'SJS', 'VAN', 'VGK'),
    CENTRAL: ('CHI', 'COL', 'DAL', 'MIN', 'NSH', 'STL', 'UTA', 'WPG'),
    ATLANTIC: ('BOS', 'BUF', 'DET', 'FLA', 'MTL', 'OTT', 'TBL', 'TOR'),
    METROPOLITAN: ('CAR', 'CBJ', 'NJD', 'NYI', 'NYR', 'PHI', 'PIT', 'WSH'),
}
DIVISION_OF = {code: div for div, codes in DIVISIONS_2026.items() for code in codes}

TEAMS, CUSTOM = 'exhibitionteams', 'customteams'
STOCK_JERSEYS, CUSTOM_JERSEYS = 'stockteamjerseys', 'customteamjerseys'
ARENAS, CUSTOM_ARENAS = 'exhibitionarena', 'customarena'
UTAH_SLOT = SLOTS['UTA']  # 22
SEATTLE, SEATTLE_AHL = 499, 498  # customteams index
SEATTLE_PLAY_NOW = 399  # exhibitionteams index of the game's "NHL 32" copy
NHL_LEAGUE = 0  # stockleagues: 0 NHL (Play Now's NHL list), 16 custom teams, 17 EASHL (399's stock league)

# NHL 19's league year (leaguestates key 138; the league kernel compares with 2018 in ~100 places, so the patch keeps
# it). Ages are counted from it: a roster for season S stores birth and draft years S - 2018 earlier.
GAME_YEAR = 2018


def year_shift(season):
    """Years an updated roster's birth / draft years sit behind the real ones (8 for 2026-27)."""
    return max(0, season - GAME_YEAR) if season else 0


def colours(primary, secondary, tertiary):
    out = {}
    for prefix in ('fe', 'overlay', 'pres'):
        out.update({f'{prefix}primarycolor': primary, f'{prefix}secondarycolor': secondary,
                    f'{prefix}tertiarycolor': tertiary})
    return out


UTAH = {'cityname': 'Utah', 'teamname': 'Utah Mammoth', 'nickname': 'Utah Mammoth', 'abbrname': 'UTA',
        'divisiongroup': CENTRAL, 'conferencegroup': WEST, **colours(0x010101, 0x6CACE4, 0xFFFFFF)}
# a custom team's city is a loc string id with '$' ('$BURNABY' -> "Burnaby"); a name that is not one shows as the
# first city of the list ("Abbotsford") and the Creation Zone stopped taking input (run x2-20261016)
SEATTLE_FIELDS = {'cityname': '$SEATTLE', 'teamname': 'Kraken', 'nickname': 'Kraken', 'abbrname': 'SEA',
                  'divisiongroup': PACIFIC, 'conferencegroup': WEST, **colours(0x001628, 0x99D9D9, 0x355464)}
# NHL teams and All-Stars have leaguegroup 1 (399's stock 53 is the custom teams'). Play Now lists 399 as "Seattle
# Kraken" after the All-Stars once the served roster is the active one (run ws8 run1b: an older RosterDownload save
# had kept the stock 399 off the list)
NHL_LEAGUE_GROUP = 1
SEATTLE_EXHIBITION = {**SEATTLE_FIELDS, 'league': NHL_LEAGUE, 'leaguegroup': NHL_LEAGUE_GROUP, 'active': 1}
# no loc id for Coachella Valley: the city stays '$BURNABY' (the text layer can rename "Burnaby", Phase B)
COACHELLA = {'teamname': 'Firebirds', 'nickname': 'Firebirds', 'abbrname': 'CV', **colours(0xC8102E, 0xF47A38, 0x001628)}

UTAH_ARENA = {'cityname': 'Salt Lake City, UT', 'arenaname': 'Delta Center', 'maxattendance': 16020, 'yearopened': 1991}
SEATTLE_ARENA = {'cityname': '$SEATTLE', 'arenaname': 'Climate Pledge Arena', 'maxattendance': 17151, 'yearopened': 2021}
COACHELLA_ARENA = {'arenaname': 'Acrisure Arena', 'maxattendance': 10087, 'yearopened': 2022}

# (table, index field value, fields)
CHANGES = ((TEAMS, UTAH_SLOT, UTAH), (CUSTOM, SEATTLE, SEATTLE_FIELDS), (CUSTOM, SEATTLE_AHL, COACHELLA),
           (ARENAS, UTAH_SLOT, UTAH_ARENA), (CUSTOM_ARENAS, SEATTLE, SEATTLE_ARENA),
           (CUSTOM_ARENAS, SEATTLE_AHL, COACHELLA_ARENA), (TEAMS, SEATTLE_PLAY_NOW, SEATTLE_EXHIBITION),
           (ARENAS, SEATTLE_PLAY_NOW, SEATTLE_ARENA))


# Seattle's art id: both records carry `artid` 10499, but their jerseys use the custom-team template's teamartid 1000,
# which is also the EA placeholder's (t1000, jersey_1_1000_*: the logo on the trade screen, run x4). With the
# art layer's 10499 logo and jersey files in the game, `jersey_art` points the jerseys at 10499
# (docs/notes/nhl19-32teams-re.md, S2).
SEATTLE_ART, TEMPLATE_ART = 10499, 1000

# Utah's equipment: stockteamequipmenttable keeps Arizona's colours per team (zone1..zone15, 0xRRGGBB; equipment 7
# is the helmet, 4 the gloves), so Utah's helmets rendered Coyotes red (WS7 run g). Arizona's own reds become the
# black of the other teams' helmets (0x0f0f0f) and gear (0x202020), the navy of its alternate kits Mountain Blue;
# whites and the shared colours stay. stockteamcolorstable's accents (colorid 0, 1) brick red and sand become
# Mountain Blue and white.
EQUIPMENT, TEAM_COLOURS = 'stockteamequipmenttable', 'stockteamcolorstable'
ZONES = tuple(f'zone{z}' for z in range(1, 16))
UTAH_EQUIPMENT = {0x821113: 0x0F0F0F, 0x732227: 0x0F0F0F, 0x6B141A: 0x202020, 0x6B1B20: 0x202020,
                  0x631219: 0x202020, 0x90181C: 0x202020, 0x122063: 0x6CACE4, 0x253B73: 0x6CACE4}
UTAH_COLOURS = {0x7F1112: 0x6CACE4, 0xE7C49C: 0xFFFFFF}


def _colour_plan(db, schema):
    out = []
    for name, fields, colours in ((EQUIPMENT, ZONES, UTAH_EQUIPMENT), (TEAM_COLOURS, ('color',), UTAH_COLOURS)):
        if schema.by_name(name).short not in db:
            continue
        t = db[schema.by_name(name).short]
        for i in range(t.count):
            if t.get(i, 'team') == UTAH_SLOT:
                out += [(name, i, f, t.get(i, f), colours[t.get(i, f)]) for f in fields if t.get(i, f) in colours]
    return out
JERSEYS = ((CUSTOM_JERSEYS, SEATTLE), (STOCK_JERSEYS, SEATTLE_PLAY_NOW))


def jersey_art(db, schema, art=SEATTLE_ART, setter=None, jerseys=JERSEYS):
    """Point Seattle's jerseys (customteamjerseys 499, stockteamjerseys 399; `jerseys`) at `art`. Returns [(table,
    row, old, new)] of the rows changed; a second run changes nothing."""
    out = []
    for name, team in jerseys:
        short = schema.by_name(name).short
        t = db[short]
        for i in range(t.count):
            if t.get(i, 'teamid') == team and t.get(i, 'teamartid') != art:
                out.append((name, i, t.get(i, 'teamartid'), art))
                if setter is None:
                    t.set(i, 'teamartid', art)
                else:
                    setter(short, i, 'teamartid', art)
    return out


# Seattle's 3D kit (WS7 run p): with the custom-team art 1000 the game draws Seattle as a Creation Zone recolour
# (czjersey_0 in its equipment zone colours; in game plain black, no crest), never the rbk_template files. Art 900 is
# Hockey Ultimate Team's (inactive; 3D set `pre_order`, menus jersey_1_900_*) and has real 3D kits for the style-1
# variants 0-2 Seattle's rows use, so Play Now's Seattle wears it and the looks pack lays NHL 27's Kraken kits over
# it (tools/nhl27/warp19.seattle). Three stockteamjerseys rows (rosterupdate: Play Now, online) and Seattle's three
# customteamjerseys rows (499; only in nhl_game.db, the database layer: Season, Be a Pro, Franchise's Seattle). The
# Creation Zone teams (400-449) keep art 1000.
SEATTLE_KIT_ART = 900
SEATTLE_KIT = ((STOCK_JERSEYS, SEATTLE_PLAY_NOW), (CUSTOM_JERSEYS, SEATTLE))


def seattle_kit(db, schema):
    """Seattle's jerseys (stockteamjerseys 399, customteamjerseys 499: SEATTLE_KIT) on art SEATTLE_KIT_ART. Returns
    the rows changed (jersey_art)."""
    return jersey_art(db, schema, SEATTLE_KIT_ART, jerseys=SEATTLE_KIT)


# Utah's throwbacks: Arizona's stockteamjerseys style 0 and 1 rows are Coyotes retro kits (WS7, docs/notes/art.md), so
# Utah would wear them. They go, as Vegas has none: Utah keeps its adidas rows (style 2), and their jerseyindex is
# renumbered from 0 in order, like every team's (it is the row's place among the team's rows). The resort goalie
# extras that wear a Utah kit (casualjerseyteam / casualjerseyindex) follow the new numbers.
ADIDAS = 2
RESORT_EXTRAS = ('exhibitionresortskaterextras', 'exhibitionresortgoalieextras', 'customresortskaterextras',
                 'customresortgoalieextras')


def drop_throwbacks(db, schema, team=UTAH_SLOT):
    """Remove `team`'s non-adidas stockteamjerseys rows. Returns [(style, variant)] removed; a second run removes
    nothing."""
    t = db[schema.by_name(STOCK_JERSEYS).short]
    rows = [i for i in range(t.count) if t.get(i, 'teamid') == team]
    old = [i for i in rows if t.get(i, 'style') != ADIDAS]
    if not old:
        return []
    keep = sorted((i for i in rows if t.get(i, 'style') == ADIDAS), key=lambda i: t.get(i, 'jerseyindex'))
    renumber = {t.get(i, 'jerseyindex'): n for n, i in enumerate(keep)}
    for i in keep:
        t.set(i, 'jerseyindex', renumber[t.get(i, 'jerseyindex')])
    for name in RESORT_EXTRAS:
        if schema.by_name(name).short not in db:
            continue
        x = db[schema.by_name(name).short]
        for i in range(x.count):
            if x.get(i, 'casualjerseyteam') == team:
                x.set(i, 'casualjerseyindex', renumber.get(x.get(i, 'casualjerseyindex'), 0))
    removed = [(t.get(i, 'style'), t.get(i, 'variant')) for i in old]
    for i in reversed(old):
        t.delete(i)
    return removed


# Centre ice as the NHL teams have it: the team's own logo (art id = team art id, WS7's ice_centerlogo_10499_cm for
# Seattle), not the generic logo 1000 the game's "NHL 32" copy and the custom team slots use.
CENTER_ICE_OWN = {'centericelogotype': -1, 'centericelogo': 0}


def seattle_center_ice(db):
    """Seattle's centre ice from its own logo: exhibitionteams 399 and customteams 499 get CENTER_ICE_OWN; the Creation
    Zone slots (customteams 400-449) keep logo 1000. Returns the number of team rows changed."""
    n = 0
    for name, index in ((TEAMS, SEATTLE_PLAY_NOW), (CUSTOM, SEATTLE)):
        t = db[name]
        row = next(i for i in range(t.count) if t.get(i, 'index') == index)
        if any(t.get(row, f) != v for f, v in CENTER_ICE_OWN.items()):
            for f, v in CENTER_ICE_OWN.items():
                t.set(row, f, v)
            n += 1
    return n


def draft_team(code):
    """`draftteam` for a player drafted by `code` (NHL.com code; 'ARI' counts as Utah): the team index, -1 for
    Seattle and teams the game has no slot for."""
    code = 'UTA' if code in ('ARI', 'PHX') else code
    slot = SLOTS.get(code, -1)
    return -1 if slot > 30 else slot


def _clean(value):
    return value.replace('™', '').strip() if isinstance(value, str) else value


def _rows_by_index(table):
    return {table.get(i, 'index'): i for i in range(table.count)}


def plan(db, schema):
    """[(table name, row, field, old, new)] still needed to set the teams up: empty when they already are (so a
    second run changes nothing)."""
    out = []
    for name, index, fields in CHANGES:
        t = db[schema.by_name(name).short]
        row = _rows_by_index(t).get(index)
        if row is None:
            raise KeyError(f"{name} has no team {index}")
        for field, value in fields.items():
            old = t.get(row, field)
            if _clean(old) != value:
                out.append((name, row, field, old, value))
    return out + _colour_plan(db, schema)


def apply(db, schema, setter=None):
    """Set the teams up. `setter(short tag, row, field, value)` writes one value (default: straight into `db`;
    the roster app passes its undoable one). Returns the plan that was applied."""
    todo = plan(db, schema)
    for name, row, field, _old, new in todo:
        short = schema.by_name(name).short
        if setter is None:
            db[short].set(row, field, new)
        else:
            setter(short, row, field, new)
    return todo


def check(db, schema):
    """Problems: the 31 NHL teams' divisions and conferences as in 2026-27 (Seattle's in customteams), Utah and
    Seattle set up."""
    problems = [f"{name} row {row}: {field} is {old!r}, expected {new!r}" for name, row, field, old, new in plan(db, schema)]
    t = db[schema.by_name(TEAMS).short]
    rows = _rows_by_index(t)
    for code, slot in SLOTS.items():
        if slot > 30:
            continue
        div, conf = t.get(rows[slot], 'divisiongroup'), t.get(rows[slot], 'conferencegroup')
        if div != DIVISION_OF[code] or conf != CONFERENCE[DIVISION_OF[code]]:
            problems.append(f"{code} (team {slot}) in division {div} / conference {conf}, expected "
                            f"{DIVISION_OF[code]} / {CONFERENCE[DIVISION_OF[code]]}")
    return problems
