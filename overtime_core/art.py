"""Overtime game patch, art part: team art (logos, menu jerseys, 3D kits, centre ice) and player portraits from art
packs, served as new archives that the game mounts after its own (overlay layer `art`).

The game's patch loader lists `<root>/databigs/patch_<family>_*.big` and mounts them sorted by name, so the last one
wins. It does this for the UI family (`inxp`) and the 3D family (`game`) separately, and shadPS4's mods overlay merges
the directory listing of `<game folder>-mods/` into the game's. So the art goes into new archives one number above the
game's highest of each family (`patch_inxp_57.big` and `patch_game_97.big` for v1.60), written into the overlay. The
overlay's copies of the game's own archives are never touched.
- A texture the game already has goes into every family that holds a copy, because which family wins over the other
  is not known.
- A new texture (Seattle's t10499) goes into the family that holds its folder's other files.

An art pack is a zip, built on the owner's PC from their own NHL 27 dump and from NHL.com (tools/build_looks.py,
tools/build_photopack.py). Packs are never committed.

    pack.json   {"format": 1, "name", "built", "source", "files": {game path: sha256}}
    <path>      each texture as a ready GNF file, stored at its game path (nhl/...)

A delta pack (format 2, the all-team 3D kits: most of a kit's normal / coeff maps is the game's own) also lists
    "deltas": {game path: {"base": sha256 of the game's own file, "sha256": of the result, "size": its length}}
    <path>.delta  the result's 16-byte blocks that differ from the game's file (DELTA_MAGIC, then runs of
                  u32 offset, u32 length, bytes)
and is read with the game folder (load_pack(path, game_dir)): each delta is laid on the game's winning copy of its
path, and a pack whose base does not match that copy (another game version, a modded file) is refused.

Stdlib only: the textures are made when the pack is built, never here.
"""
import hashlib
import json
import os
import re
import zipfile

from . import eb, gamefiles

FORMAT = 1
DELTA_FORMAT = 2
MANIFEST = 'pack.json'
DELTA_MAGIC = b'OTD1'
BLOCK = 16
FAMILIES = ('inxp', 'game')
GNF_MAGIC = b'GNF '
_PATH = re.compile(r'^nhl/[a-z0-9_./-]+\.gnf$')
_ARCHIVE = re.compile(r'^(patch_)?([a-z]+)_(\d+)\.big$')
# NHL 19 draws a player's portrait from p<artid> (the bio's artid, not its game_id: ws8 run pk), when his bio has
# hasportrait set
PORTRAIT = 'nhl/ui/kettle_assets/playerportraits/p{}.gnf'
BIOS = 'exhibitionplayerbiotable'


class ArtError(Exception):
    pass


def family(archive):
    """'inxp' (UI) / 'game' (3D) / 'boot' / 'overlays' / 'other' of an archive file name."""
    m = _ARCHIVE.match(os.path.basename(archive).lower())
    if m and m.group(2) in FAMILIES + ('boot', 'overlays'):
        return m.group(2)
    name = os.path.basename(archive).lower()
    return 'boot' if name.startswith('boot') else 'other'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def check_file(path, data):
    """Raise ArtError unless `path` is a lower-case game texture path and `data` a GNF file."""
    if not _PATH.match(path) or '..' in path.split('/'):
        raise ArtError(f'not a game texture path: {path}')
    if data[:4] != GNF_MAGIC:
        raise ArtError(f'{path}: not a GNF texture')


class Pack:
    """One art pack: `name`, `info` (pack.json without the file list) and `files` {game path: bytes}."""

    def __init__(self, name, info, files, path=None):
        self.name, self.info, self.files, self.path = name, info, files, path

    @property
    def sha256(self):
        h = hashlib.sha256()
        for p in sorted(self.files):
            h.update(p.encode() + b'\0' + _sha(self.files[p]).encode())
        return h.hexdigest()

    def record(self):
        return {'name': self.name, 'files': len(self.files), 'sha256': self.sha256,
                'built': self.info.get('built'), 'source': self.info.get('source')}


def make_delta(base, data):
    """The delta that turns `base` into `data` (same length): the differing BLOCK-byte blocks, adjacent ones joined."""
    if len(base) != len(data):
        raise ArtError('a delta needs a base of the same length')
    runs, start = [], None
    for o in range(0, len(data), BLOCK):
        if data[o:o + BLOCK] != base[o:o + BLOCK]:
            if start is None:
                start = o
        elif start is not None:
            runs.append((start, o))
            start = None
    if start is not None:
        runs.append((start, len(data)))
    out = bytearray(DELTA_MAGIC)
    for a, b in runs:
        out += a.to_bytes(4, 'little') + (b - a).to_bytes(4, 'little') + data[a:b]
    return bytes(out)


def apply_delta(base, delta):
    """`base` with `delta` (make_delta) laid on it."""
    if delta[:4] != DELTA_MAGIC:
        raise ArtError('not an art delta')
    out, i = bytearray(base), 4
    while i < len(delta):
        if i + 8 > len(delta):
            raise ArtError('a cut-off art delta')
        off, n = int.from_bytes(delta[i:i + 4], 'little'), int.from_bytes(delta[i + 4:i + 8], 'little')
        i += 8
        if off + n > len(out) or i + n > len(delta):
            raise ArtError('an art delta that runs past its file')
        out[off:off + n] = delta[i:i + n]
        i += n
    return bytes(out)


def game_reader(game_dir, paths):
    """A function reading the winning copy (last mounted) of each of `paths` from the game's own archives, which are
    listed once for all of them."""
    want, where = set(paths), {}
    for big in gamefiles.archives(game_dir):
        with eb.EbArchive(big) as arc:
            for p in want.intersection(arc.entries):
                where[p] = big

    def read(p):
        if p not in where:
            raise ArtError(f'{p} is not in the game, so its delta has no base')
        with eb.EbArchive(where[p]) as arc:
            return arc.read(p)
    return read


def load_pack(path, game_dir=None):
    """Read and check an art pack zip; a delta pack needs `game_dir` (its bases). Raises ArtError when anything is
    off."""
    try:
        with zipfile.ZipFile(path) as z:
            try:
                info = json.loads(z.read(MANIFEST).decode('utf-8'))
            except KeyError:
                raise ArtError(f'{path}: no {MANIFEST}') from None
            if info.get('format') not in (FORMAT, DELTA_FORMAT):
                raise ArtError(f'{path}: pack format {info.get("format")} (this app reads {FORMAT}, {DELTA_FORMAT})')
            listed = info.get('files') or {}
            files = {}
            for p, sha in listed.items():
                try:
                    data = z.read(p)
                except KeyError:
                    raise ArtError(f'{path}: {p} is listed but missing') from None
                if _sha(data) != sha:
                    raise ArtError(f'{path}: {p} does not match its checksum')
                check_file(p, data)
                files[p] = data
            deltas = info.get('deltas') or {}
            if deltas and game_dir is None:
                raise ArtError(f'{path}: a delta pack is read with the game folder')
            read = game_reader(game_dir, deltas) if deltas else None
            for p, rec in deltas.items():
                if not _PATH.match(p) or '..' in p.split('/'):
                    raise ArtError(f'{path}: not a game texture path: {p}')
                base = read(p)
                if _sha(base) != rec.get('base') or len(base) != rec.get('size'):
                    raise ArtError(f"{path}: the game's {p} is not the file this pack was made on "
                                   '(another game version, or a modded file)')
                try:
                    data = apply_delta(base, z.read(p + '.delta'))
                except KeyError:
                    raise ArtError(f'{path}: {p}.delta is listed but missing') from None
                if _sha(data) != rec.get('sha256'):
                    raise ArtError(f'{path}: {p} does not match its checksum')
                check_file(p, data)
                files[p] = data
    except (zipfile.BadZipFile, OSError, ValueError) as err:
        raise ArtError(f'{path}: {err}') from err
    if not files:
        raise ArtError(f'{path}: the pack holds no textures')
    meta = {k: v for k, v in info.items() if k not in ('files', 'deltas')}
    return Pack(info.get('name') or os.path.splitext(os.path.basename(path))[0], meta, files, path)


def write_pack(path, name, files, source='', built='', bases=None):
    """Write an art pack zip ({game path: GNF bytes}); the same files make the same zip. Returns its sha256.
    `bases` ({game path: the game's own bytes}) makes it a delta pack: each file with a base of the same length is
    stored as a delta to it."""
    for p, data in files.items():
        check_file(p, data)
    bases = bases or {}
    whole = {p: d for p, d in files.items() if len(bases.get(p, b'')) != len(d)}
    deltas = {p: make_delta(bases[p], d) for p, d in files.items() if p not in whole}
    info = {'format': DELTA_FORMAT if deltas else FORMAT, 'name': name, 'built': built, 'source': source,
            'files': {p: _sha(whole[p]) for p in sorted(whole)}}
    if deltas:
        info['deltas'] = {p: {'base': _sha(bases[p]), 'sha256': _sha(files[p]), 'size': len(files[p])}
                          for p in sorted(deltas)}
    stored = dict(whole, **{p + '.delta': d for p, d in deltas.items()})
    tmp = path + '.tmp'
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        stamp = (2026, 1, 1, 0, 0, 0)
        z.writestr(zipfile.ZipInfo(MANIFEST, stamp), json.dumps(info, indent=1, sort_keys=True))
        for p in sorted(stored):
            zi = zipfile.ZipInfo(p, stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, stored[p])
    os.replace(tmp, path)
    with open(path, 'rb') as f:
        return _sha(f.read())


def merge(packs):
    """{game path: bytes} of several packs; a later pack wins where two hold the same path."""
    out = {}
    for pack in packs:
        out.update(pack.files)
    return out


def game_index(game_dir):
    """({path: {family}}, {folder: {family}}) of the game's own archives, for the families the art can go to."""
    where, folders = {}, {}
    for big in gamefiles.archives(game_dir):
        fam = family(big)
        if fam not in FAMILIES:
            continue
        with eb.EbArchive(big) as arc:
            for p in arc.entries:
                where.setdefault(p, set()).add(fam)
                folders.setdefault(p.rsplit('/', 1)[0], set()).add(fam)
    return where, folders


def targets(game_dir):
    """{family: game-relative path of the new archive}: one number above the game's highest archive of the family."""
    top = {}
    for big in gamefiles.archives(game_dir):
        m = _ARCHIVE.match(os.path.basename(big).lower())
        if m and m.group(2) in FAMILIES:
            top[m.group(2)] = max(top.get(m.group(2), -1), int(m.group(3)))
    missing = [f for f in FAMILIES if f not in top]
    if missing:
        raise ArtError(f'no {", ".join(missing)} archives in {game_dir}')
    return {f: f'databigs/patch_{f}_{top[f] + 1}.big' for f in FAMILIES}


def route(files, where, folders):
    """{family: {path: bytes}}: each path into every family whose archives hold it, a new path into the family that
    holds its folder (both, when both do)."""
    out = {}
    for p, data in files.items():
        fams = where.get(p) or folders.get(p.rsplit('/', 1)[0])
        if not fams:
            raise ArtError(f'{p}: neither the texture nor its folder is in the game, so its archive is unknown')
        for fam in fams:
            out.setdefault(fam, {})[p] = data
    return out


def edits(game_dir, files):
    """{absolute path of a new archive (not in the game folder): {path: bytes}} for the overlay, and the record."""
    routed = route(files, *game_index(game_dir))
    names = targets(game_dir)
    out, record = {}, {}
    for fam, entries in sorted(routed.items()):
        archive = os.path.join(game_dir, *names[fam].split('/'))
        if os.path.exists(archive):
            raise ArtError(f'{archive} is a game file: the art archive name is taken')
        out[archive] = entries
        record[fam] = {'archive': names[fam], 'textures': len(entries)}
    return out, record


def portrait_flags(db, stock, files):
    """Set each bio's hasportrait in `db` (a tdb.Database) for the portraits served: on where `files` (the art
    layer's {game path: bytes}, empty with the layer off) holds p<artid>, else what the stock database `stock` has for
    that player (game_id), off for a player stock does not have (a new one: his artid has no stock portrait). So
    the flag is the same whichever database the layer starts from, and taking the art away puts the stock flags back.
    Returns how many bios changed."""
    if BIOS not in db or BIOS not in stock:
        return 0
    s = stock[BIOS]
    stocked = {s.get(i, 'game_id'): s.get(i, 'hasportrait') for i in range(s.count)}
    t, changed = db[BIOS], 0
    for i in range(t.count):
        want = 1 if PORTRAIT.format(t.get(i, 'artid')) in files else stocked.get(t.get(i, 'game_id'), 0)
        if t.get(i, 'hasportrait') != want:
            t.set(i, 'hasportrait', want)
            changed += 1
    return changed
