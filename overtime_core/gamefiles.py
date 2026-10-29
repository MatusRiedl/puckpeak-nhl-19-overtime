"""Find NHL 19 data in the user's own game folder (read only).

The game mounts `databigs/*.big`; for a path present in several archives the highest-numbered `patch_*`
archive wins (`patch_inxp_56.big` holds the current `nhl_game.db` in v1.60).
"""
import os
import re

from .eb import EbArchive

DB_PATH = 'nhl/data/common/gamemodes/database/t3db/nhl_game.db'
META_PATH = 'nhl/data/common/gamemodes/database/t3db/nhl_game-meta.xml'
# the game's own roster file: the 41 rosterupdate tables (players, teams, calendars), laid over nhl_game.db's
ROSTER_PATH = 'nhl/data/common/gamemodes/roster/initial_experience.db'


def _order(name):
    """Sort key: base archives first, then patches by number."""
    m = re.match(r'(patch_)?\w+?_(\d+)\.big$', name)
    return (1 if m and m.group(1) else 0, int(m.group(2)) if m else -1, name)


def archives(game_dir):
    big_dir = os.path.join(game_dir, 'databigs')
    names = sorted((n for n in os.listdir(big_dir) if n.endswith('.big')), key=_order)
    return [os.path.join(big_dir, n) for n in names]


def served(game_dir, archive):
    """The file the game opens for `archive` under shadPS4: `<game folder>-mods/<same path>` when the Overtime
    patch (or another mod) put one there, else the game's own."""
    mods = os.path.normpath(game_dir).rstrip('\\/') + '-mods'
    alt = os.path.join(mods, os.path.relpath(archive, game_dir))
    return alt if os.path.isfile(alt) else archive


def read_latest(game_dir, path, mods=False):
    """Bytes of `path` from the archive that wins, and that archive's file name. With `mods`, as the game sees it
    with the mods overlay (overtime_core.overlay): an archive copy in `<game folder>-mods/` replaces the game's."""
    found = None
    for big in archives(game_dir):
        with EbArchive(served(game_dir, big) if mods else big) as arc:
            if path in arc.entries:
                found = (arc.read(path), os.path.basename(big))
    if found is None:
        raise FileNotFoundError(f"{path} not in {game_dir}")
    return found


def default_database(game_dir, mods=False):
    return read_latest(game_dir, DB_PATH, mods)


def schema_xml(game_dir):
    return read_latest(game_dir, META_PATH)
