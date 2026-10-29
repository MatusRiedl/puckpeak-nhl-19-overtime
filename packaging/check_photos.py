r"""Build check: photos.zip goes with the default roster it was made for. Its files are p<artid>.gnf of that roster's
bios, so every portrait must name an artid a bio of the default database has (the game files give the schema; they
are only read). The app runs the same check on the photos.zip it downloads (overtime_roster.app.packdownload), this
one also reads every file of the pack. Prints the pack's sha256 and counts as JSON on the last line; exit 1 when they
do not fit.
    python packaging\check_photos.py <nhl_game.db> <photos.zip> [<game dir>]"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from overtime_core import art  # noqa: E402
from overtime_roster.app import packdownload, paths  # noqa: E402


def main(db_path, photos, game_dir):
    pack = art.load_pack(photos)
    ids, other = packdownload.portraits(pack.files)
    with open(db_path, 'rb') as f:
        have = packdownload.artids(f.read(), game_dir)
    ok, missing = packdownload.fit(ids, other, have)
    with open(photos, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f'{os.path.basename(photos)}  {len(ids)} portraits, {len(ids) - len(missing)} on bios of the default roster, '
          f'{len(missing)} not ({missing[:10]}), {len(other)} other files')
    print(json.dumps({'sha256': sha, 'bytes': os.path.getsize(photos), 'portraits': len(ids), 'name': pack.name}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else paths.default_game_dir()))
