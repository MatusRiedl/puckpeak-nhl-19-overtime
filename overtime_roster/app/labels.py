"""Readable names for NHL 19 database values: positions, leagues, countries, attributes, line slots.

Facts from the game's own default roster (docs/notes/roster-app.md): bio height = inches - 54, weight = lbs - 120,
birth year = year - 1900, month and day count from 0, handedness 0 = left, contract dollars in units of $5,000.
League names are the `stockleagues` rows; country ids were read off the players' birthplaces.
"""

POSITIONS = ['C', 'LW', 'RW', 'D', 'G']
SKATER_POSITIONS = POSITIONS[:4]
GOALIE = 4
HANDS = ['L', 'R']

HEIGHT_BASE = 54     # inches
WEIGHT_BASE = 120    # lbs
YEAR_BASE = 1900
CONTRACT_UNIT = 5000  # dollars

LEAGUES = {
    0: 'NHL', 1: 'AHL', 2: 'SHL', 3: 'Liiga', 4: 'DEL', 5: 'Czech Extraliga', 6: 'Swiss League', 7: 'EBEL',
    8: 'Allsvenskan', 9: 'Champions League', 10: 'International', 11: 'OHL', 12: 'QMJHL', 13: 'WHL',
    14: 'Prospects', 15: 'ECHL', 16: 'Custom', 17: 'EASHL', 18: 'Mascots', 19: '3-on-3', 20: 'Spengler Cup',
    21: 'NHL Alumni', 22: 'Alumni specials', 23: 'Pro-Am', 24: 'CHL', 25: 'United States', 26: 'Russia',
    27: 'Rest of world', 28: 'HUT',
}
FREE_AGENTS = -1  # pseudo team / league id for the free agent list

COUNTRIES = {
    0: 'Canada', 14: 'USA', 66: 'Denmark', 67: 'Finland', 68: 'Norway', 69: 'Sweden', 70: 'Belarus',
    71: 'Estonia', 72: 'Kazakhstan', 74: 'Latvia', 75: 'Lithuania', 76: 'Russia', 77: 'Ukraine', 78: 'Austria',
    79: 'Belgium', 81: 'Croatia', 82: 'Czech Republic', 83: 'Great Britain', 84: 'France', 85: 'Germany',
    86: 'Hungary', 87: 'Italy', 89: 'Netherlands', 91: 'Poland', 92: 'Romania', 95: 'Slovakia', 96: 'Slovenia',
    97: 'Switzerland', 109: 'Japan',
}


def country(cid):
    return COUNTRIES.get(cid, f'Country {cid}')


# NHL 19's attribute screen groups; field -> label. Fields missing from a schema are skipped.
SKATER_GROUPS = [
    ('Skating', [('c_acceleration', 'Acceleration'), ('c_agility', 'Agility'), ('c_balance', 'Balance'),
                 ('c_endurance', 'Endurance'), ('c_speed', 'Speed'), ('c_backskating', 'Backskating')]),
    ('Shooting', [('c_slapaccuracy', 'Slap shot accuracy'), ('c_slapshotpower', 'Slap shot power'),
                  ('c_wristaccuracy', 'Wrist shot accuracy'), ('c_wristshotpower', 'Wrist shot power')]),
    ('Hands', [('c_deking', 'Deking'), ('c_handeye', 'Hand-eye'), ('c_passing', 'Passing'),
               ('c_puckcontrol', 'Puck control')]),
    ('Checking', [('c_bodychecking', 'Body checking'), ('c_strength', 'Strength'),
                  ('c_aggression', 'Aggressiveness'), ('c_durability', 'Durability'),
                  ('c_fightingskill', 'Fighting skill')]),
    ('Defense', [('c_defawareness', 'Defensive awareness'), ('c_faceoffs', 'Faceoffs'),
                 ('c_shotblocking', 'Shot blocking'), ('c_stickchecking', 'Stick checking')]),
    ('Senses', [('c_discipline', 'Discipline'), ('c_offawareness', 'Offensive awareness'), ('c_poise', 'Poise')]),
    ('Overall', [('c_overall', 'Overall (stored)'), ('c_potential', 'Potential')]),
]
GOALIE_GROUPS = [
    ('Glove / stick', [('c_gsh', 'Glove high'), ('c_gsl', 'Glove low'), ('c_ssh', 'Stick high'),
                       ('c_ssl', 'Stick low'), ('c_5hole', 'Five hole')]),
    ('Positioning', [('c_positioning', 'Angles'), ('c_breakaway', 'Breakaway'),
                     ('c_reboundcontrol', 'Rebound control'), ('c_shotrecover', 'Recover'),
                     ('c_vision', 'Vision')]),
    ('Athletics', [('c_speed', 'Speed'), ('c_agility', 'Agility'), ('c_endurance', 'Endurance'),
                   ('c_durability', 'Durability')]),
    ('Puck / mind', [('c_pokecheck', 'Poke check'), ('c_passing', 'Passing'),
                     ('c_puckplayfrequency', 'Puck playing frequency'), ('c_aggression', 'Aggressiveness'),
                     ('c_poise', 'Poise'), ('c_consistency', 'Consistency')]),
    ('Overall', [('c_overall', 'Overall (stored)'), ('c_potential', 'Potential')]),
]
SKATER_SUMMARY = [('skill_overall', 'Overall'), ('skill_skate', 'Skating'), ('skill_shoot', 'Shooting'),
                  ('skill_puck', 'Hands'), ('skill_physical', 'Physical'), ('skill_defense', 'Defense'),
                  ('skill_sense', 'Senses')]
GOALIE_SUMMARY = [('skill_overall', 'Overall'), ('skill_reflex', 'Reflexes'), ('skill_control', 'Control'),
                  ('skill_athletics', 'Athletics')]


def rating_label(field):
    for groups in (SKATER_GROUPS, GOALIE_GROUPS):
        for _, items in groups:
            for f, label in items:
                if f == field:
                    return label
    return field


# --- line slots (exhibitionrostertable 1-bit fields) ------------------------------------------------
# (section, group, [(unit label, [(slot field, slot label)])]); a section is one page of the Lines tab and maps to
# lines.GROUPS (LINE_SECTIONS)
LINE_GROUPS = [
    ('Even strength', 'Forwards', [(f'L{i}', [(f'l{i}lw', 'LW'), (f'l{i}c', 'C'), (f'l{i}rw', 'RW')])
                                   for i in range(1, 5)]),
    ('Even strength', 'Defense', [(f'D{i}', [(f'l{i}ld', 'LD'), (f'l{i}rd', 'RD')]) for i in range(1, 4)]),
    ('Even strength', 'Goalies', [('G', [('g1', 'Starter'), ('g2', 'Backup')])]),
    ('Power play', '5 on 4', [(f'PP{i}', [(f'pp{i}lw', 'LW'), (f'pp{i}c', 'C'), (f'pp{i}rw', 'RW'),
                                           (f'pp{i}ld', 'LD'), (f'pp{i}rd', 'RD')]) for i in (1, 2)]),
    ('Power play', '4 on 3', [(f'PP4-{i}', [(f'pp4_{i}lw', 'LW'), (f'pp4_{i}c', 'C'), (f'pp4_{i}ld', 'LD'),
                                             (f'pp4_{i}rd', 'RD')]) for i in (1, 2)]),
    ('Penalty kill', '4 on 5', [(f'PK{i}', [(f'pk4_{i}lw', 'LW'), (f'pk4_{i}c', 'C'), (f'pk4_{i}ld', 'LD'),
                                             (f'pk4_{i}rd', 'RD')]) for i in (1, 2)]),
    ('Penalty kill', '3 on 5', [(f'PK3-{i}', [(f'pk3_{i}c', 'C'), (f'pk3_{i}ld', 'LD'), (f'pk3_{i}rd', 'RD')])
                                for i in (1, 2)]),
    ('Overtime', '4 on 4', [(f'OT{i}', [(f'ot_{i}lw', 'LW'), (f'ot_{i}c', 'C'), (f'ot_{i}ld', 'LD'),
                                         (f'ot_{i}rd', 'RD')]) for i in (1, 2, 3)]),
    ('Overtime', '3 on 3', [(f'3v3-{i}', [(f'ot3_{i}c', 'C'), (f'ot3_{i}ld', 'LD'), (f'ot3_{i}rd', 'RD')])
                            for i in (1, 2, 3)]),
    ('Shootout', 'Shooters', [('SO', [(f's{i}', str(i)) for i in range(1, 6)])]),
    ('Shootout', 'Extra attackers', [('X', [('x1', '1'), ('x2', '2')])]),
    ('Threes', 'NHL Threes', [('3s', [('three_c', 'C'), ('three_w', 'W'), ('three_d', 'D'), ('three_g1', 'G1'),
                                      ('three_g2', 'G2'), ('three_s1', 'S1'), ('three_s2', 'S2')])]),
]

LINE_SECTIONS = {'Even strength': ('Lines',), 'Power play': ('Power play', 'Power play 4 on 3'),
                 'Penalty kill': ('Penalty kill', 'Penalty kill 3 on 5'), 'Overtime': ('Overtime', 'Overtime 3 on 3'),
                 'Shootout': ('Shootout', 'Extra attackers'), 'Threes': ('Threes',)}


def all_slots():
    return [s for _, _, units in LINE_GROUPS for _, slots in units for s, _ in slots]


CAPTAIN_NAMES = {0: '', 1: 'C', 2: 'A'}
