"""Game setup, the part of the one-click patch outside the data overlay: find shadPS4 and NHL 19, put the Overtime
eboot patch (overtime_core.xmlpatch) into the emulator's patches folder, switch the game's network settings on,
and undo all of it.

The game folder is only read (param.sfo, hashes). Every file written in the emulator's folder is listed in the setup
manifest (`gamesetup.json` in the app's folder) with a copy of what was there before, so `remove` puts each one back
byte for byte, or, when the user changed the file since, only our keys.

shadPS4 keeps its data in `user\\` under its working directory when that folder exists (portable), otherwise in
`%APPDATA%\\shadPS4`. With no `-p` file on the command line it applies every `patches\\<folder>\\` whose
`files.json` lists the game's serial (also when started from the Qt launcher); `-p` skips the folder scan, `-i`
turns it off. A block applies when isEnabled="true", AppElf is the eboot's name and AppVer is the game's APP_VER.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from overtime_core import gamefiles, overlay, sfo, xmlpatch

from . import paths

TITLE_ID, APP_VER = 'CUSA11126', '01.60'
EMULATOR_URL = 'https://github.com/Kravickas/shadPS4/tree/NHL19-Build'
PATCH_FOLDER, PATCH_FILE = 'Overtime', 'overtime.xml'
NETWORK = {'connected_to_network': True, 'shad_net_enabled': True}  # custom_configs\CUSA11126.json, "General"
MANIFEST = 'gamesetup.json'
FIREWALL_RULE = 'Overtime NHL 19 (shadPS4)'


class SetupError(RuntimeError):
    pass


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.overtime-tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _refuse_while_running(running=None):
    if (running or overlay.emulator_running)():
        raise SetupError('shadPS4 is running. Close the game first, then try again.')


# ---- finding things ---------------------------------------------------------------------------------------------

def emu_user_dir(emu_exe):
    """The emulator's data folder: `user\\` next to it (portable; we start it from its own folder), else %APPDATA%."""
    portable = os.path.join(os.path.dirname(os.path.abspath(emu_exe)), 'user')
    if os.path.isdir(portable):
        return portable
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'shadPS4')


def _is_emulator(name):
    low = name.lower()
    return low.startswith('shadps4') and low.endswith('.exe') and 'launcher' not in low


def find_emulators(roots=None, depth=2):
    """shadPS4 executables (not the Qt launcher) under `roots`, newest first. The default roots are the folders
    the emulator's own config lists for games (and their parents), the user's Desktop and Downloads."""
    if roots is None:
        roots = []
        for d in install_dirs(emu_user_dir('')):
            roots += [d, os.path.dirname(d.rstrip('\\/'))]
        home = os.path.expanduser('~')
        roots += [os.path.join(home, 'Desktop'), os.path.join(home, 'Downloads')]
    found, seen = [], set()
    for root in roots:
        for path in _walk(root, depth):
            if _is_emulator(os.path.basename(path)) and os.path.normcase(path) not in seen:
                seen.add(os.path.normcase(path))
                found.append(path)
    return sorted(found, key=lambda p: os.path.getmtime(p), reverse=True)


def _walk(root, depth):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for e in entries:
        try:
            if e.is_file():
                yield e.path
            elif e.is_dir() and depth > 0:
                yield from _walk(e.path, depth - 1)
        except OSError:
            continue


def install_dirs(user_dir):
    """The game folders shadPS4 is set up to look in (config.json, General.install_dirs, enabled ones)."""
    try:
        with open(os.path.join(user_dir, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for d in ((cfg.get('General') or {}).get('install_dirs') or []):
        if isinstance(d, dict) and d.get('enabled', True) and d.get('path'):
            out.append(d['path'])
    return out


def read_game(game_dir):
    """What a game folder holds: {'path', 'ok', 'title_id', 'app_ver', 'problem', 'update'}; ok = NHL 19 CUSA11126
    v1.60. With the update in a folder of its own beside the base (`-UPDATE` / `-patch`, either folder picked), the
    version is the update's and 'update' names that folder."""
    base, update = gamefiles.roots(game_dir)
    info = {'path': game_dir, 'ok': False, 'title_id': None, 'app_ver': None, 'problem': None, 'update': update}
    game_dir = update or base
    try:
        values = {e.key: e.value for e in sfo.parse(_read(os.path.join(game_dir, 'sce_sys', 'param.sfo')))}
    except (OSError, sfo.SfoError) as e:
        info['problem'] = f'no readable sce_sys\\param.sfo ({e})'
        return info
    info['title_id'], info['app_ver'] = values.get('TITLE_ID'), values.get('APP_VER')
    if info['title_id'] != TITLE_ID:
        info['problem'] = f"this is {info['title_id'] or 'another game'}, not NHL 19 ({TITLE_ID})"
    elif info['app_ver'] != APP_VER:
        info['problem'] = f"NHL 19 version {info['app_ver']}; Overtime needs update {APP_VER}"
    elif not os.path.isfile(os.path.join(game_dir, 'eboot.bin')):
        info['problem'] = 'eboot.bin is missing'
    else:
        info['ok'] = True
    return info


def find_games(user_dir, extra=()):
    """NHL 19 folders in the emulator's game folders (and `extra`), each as read_game() sees it. A base game with its
    update in a folder of its own is one game, listed as the base folder."""
    out, seen = [], set()
    for root in list(extra) + install_dirs(user_dir):
        candidates = [root] + [e.path for e in _scandirs(root)]
        for c in candidates:
            if not os.path.isfile(os.path.join(c, 'sce_sys', 'param.sfo')):
                continue
            base = gamefiles.roots(c)[0]
            if os.path.normcase(base) not in seen:
                seen.add(os.path.normcase(base))
                same = os.path.normcase(base) == os.path.normcase(os.path.abspath(c))
                info = read_game(c if same else base)   # the folder as found, or the base of an update folder
                if info['title_id'] == TITLE_ID:
                    out.append(info)
    return out


def _scandirs(root):
    try:
        return [e for e in os.scandir(root) if e.is_dir()]
    except OSError:
        return []


def shadnet_users(user_dir):
    """The emulator's users as far as Overtime needs them: [{'user_id', 'name', 'shadnet', 'npid', 'password'}].
    Only these fields are read out of users.json ('password': whether one is filled in); e-mail, password and token
    never leave it."""
    try:
        with open(os.path.join(user_dir, 'users.json'), encoding='utf-8') as f:
            users = (json.load(f).get('Users') or {}).get('user') or []
    except (OSError, ValueError, AttributeError):
        return []
    return [{'user_id': u.get('user_id'), 'name': u.get('user_name') or '',
             'shadnet': bool(u.get('shadnet_enabled')), 'npid': u.get('shadnet_npid') or '',
             'password': bool(u.get('shadnet_password'))}
            for u in users if isinstance(u, dict)]


# shadPS4's log of its last run (it starts a new one at every start): the ShadNet sign-in is near the top
# (docs/notes/shadps4-network.md "ShadNet sign-in").
LOG_FILE = os.path.join('log', 'shad_log.txt')
LOG_HEAD = 1 << 20
_SIGNED_IN = re.compile(rb"ConnectUser: user_id=\d+ signed in npid='([^'\r\n]{0,32})'(?: accountId=(\d{1,12}))?")
_REJECTED = re.compile(rb'Login rejected error code (\d+)')


def shadnet_log(user_dir):
    """What shadPS4's last run said about ShadNet: {'state': 'signed_in' | 'rejected' | 'signed_out' | None,
    'npid', 'account' (the ShadNet account id of that sign-in, or None: the Blaze externalId), 'code', 'when' (the
    log's time, seconds)}, or None without a log. 'rejected': the server refused the
    Online ID or password (code 8: a wrong password, or the Online ID with other capitals); None: the run ended
    before it got that far."""
    path = os.path.join(user_dir, LOG_FILE)
    try:
        with open(path, 'rb') as f:
            head = f.read(LOG_HEAD)
        when = os.path.getmtime(path)
    except OSError:
        return None
    out = {'state': None, 'npid': '', 'account': None, 'code': None, 'when': when}
    signed, refused = _SIGNED_IN.search(head), _REJECTED.search(head)
    if signed:
        out.update(state='signed_in', npid=signed.group(1).decode('ascii', 'replace'),
                   account=int(signed.group(2)) if signed.group(2) else None)
    elif refused:
        out.update(state='rejected', code=int(refused.group(1)))
    elif b'no users connected to shadNet' in head:
        out['state'] = 'signed_out'
    return out


def save_dir(user_dir, user_id=1000):
    """The game's save folder in shadPS4's data folder (paths.SAVE_SUBDIR's place for this emulator)."""
    return os.path.join(user_dir, 'home', str(user_id), 'savedata', TITLE_ID)


# ---- which shadPS4 build (its exe carries the version block the log prints at start) -------------------------
# 'v0.20.1 WIP', the 40-hex revision, the branch, the short description, the remote: NUL-separated, in .rdata
# (log: "Starting shadps4 emulator v0.20.1 WIP", "Revision ...", "Branch NHL19-Build").
BUILD_BRANCH = 'NHL19-Build'
_SCM = re.compile(rb'(?<![\x20-\x7e])(\d+\.\d+\.\d+[ A-Za-z0-9.+-]{0,24})\x00+([0-9a-f]{40})\x00+([\x20-\x7e]{1,80})'
                  rb'\x00+([\x20-\x7e]{1,80})\x00+(https?://[\x20-\x7e]{1,200})\x00')
_builds = {}            # (path, size, mtime) -> emulator_build()


def emulator_build(emu_exe):
    """{'version', 'rev', 'branch', 'remote', 'nhl19'} of a shadPS4 exe (nhl19: the NHL19-Build, the one that plays
    NHL 19 online), or None when the exe carries no version block (another program, an exe we cannot read).
    Reads the exe (about 60 MB) once per size and time."""
    try:
        st = os.stat(emu_exe)
    except OSError:
        return None
    key = (os.path.normcase(os.path.abspath(emu_exe)), st.st_size, st.st_mtime_ns)
    if key not in _builds:
        try:
            data = _read(emu_exe)
        except OSError:
            return None
        _builds[key] = _scm_block(data)
    return dict(_builds[key]) if _builds[key] else None


def _scm_block(data):
    """The version block, looked for only around each NUL + http in the file (a whole-file search takes 0.5 s)."""
    i = data.find(b'\x00http')
    while i >= 0:
        for m in _SCM.finditer(data, max(0, i - 400), i + 220):
            if m.start(5) == i + 1:
                version, rev, branch, _desc, remote = (g.decode('ascii', 'replace') for g in m.groups())
                return {'version': version.strip(), 'rev': rev, 'branch': branch, 'remote': remote,
                        'nhl19': branch == BUILD_BRANCH}
        i = data.find(b'\x00http', i + 1)
    return None


# ---- the Overtime server (the game's first call: the redirector) -------------------------------------------------
REDIRECTOR_PORT = 42230
REDIRECTOR_PATH = '/redirector/getServerInstance'


def server_answers(host, port=REDIRECTOR_PORT, timeout=4, tls=True):
    """(True, '') when `host` answers the game's first call as the Overtime server does (POST the redirector's
    getServerInstance, as deploy/README.md does it with curl -k: the game skips the certificate check too), else
    (False, why). A few seconds at most: call it in a job."""
    import http.client
    import ssl
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request('POST', REDIRECTOR_PATH, body=b'<serverinstancerequest/>',
                     headers={'Content-Type': 'application/xml', 'User-Agent': 'OvertimeRoster setup check'})
        r = conn.getresponse()
        body = r.read(64 * 1024)
    except (OSError, http.client.HTTPException, ValueError) as err:
        return False, str(err) or type(err).__name__
    finally:
        conn.close()
    if r.status == 200 and b'serverinstanceinfo' in body.lower():
        return True, ''
    return False, f'HTTP {r.status}, not the Overtime server'


def custom_config_path(user_dir):
    return os.path.join(user_dir, 'custom_configs', TITLE_ID + '.json')


def network_settings(user_dir):
    """The network keys as the game will see them (its custom config over config.json): {key: value or None}."""
    values = {k: None for k in NETWORK}
    for path in (os.path.join(user_dir, 'config.json'), custom_config_path(user_dir)):
        try:
            with open(path, encoding='utf-8') as f:
                general = json.load(f).get('General') or {}
        except (OSError, ValueError, AttributeError):
            continue
        values.update({k: general[k] for k in NETWORK if k in general})
    return values


# ---- install / remove -------------------------------------------------------------------------------------------

def manifest_path():
    return paths.app_dir(MANIFEST)


def load_manifest():
    try:
        with open(manifest_path(), encoding='utf-8') as f:
            m = json.load(f)
            return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def _save_manifest(m):
    _write(manifest_path(), json.dumps(m, indent=1).encode('utf-8'))


def _drop_manifest():
    try:
        os.remove(manifest_path())
    except FileNotFoundError:
        pass


def patch_dir(user_dir):
    return os.path.join(user_dir, 'patches', PATCH_FOLDER)


def _game_config(cfg_path, user):
    """The per-game config as install() will write it; a missing one starts as a copy of the global one, as the Qt
    launcher makes it. Refuses a file it could not put back (bad JSON, not an object)."""
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding='utf-8') as f:
                cfg = json.load(f)
        except ValueError as e:
            raise SetupError(f'{cfg_path} is not valid JSON ({e}); fix or delete it first')
    else:
        try:
            with open(os.path.join(user, 'config.json'), encoding='utf-8') as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    if not isinstance(cfg, dict) or not isinstance(cfg.get('General', {}), dict):
        raise SetupError(f'{cfg_path}: "General" is not a section; fix or delete the file first')
    return cfg


def install(emu_exe, xml_text, running=None):
    """Put the patch into the emulator's patches folder and switch the game's network settings on. Returns the
    manifest. Installing again replaces our own files and keeps the first backups. Everything that can refuse is
    checked before the first write, and the manifest is saved around every write, so a failed install is still
    undone by remove()."""
    _refuse_while_running(running)
    xmlpatch.parse(xml_text)  # refuse a broken file before writing anything
    user = emu_user_dir(emu_exe)
    old = load_manifest() or {}
    if old.get('user_dir') and os.path.normcase(old['user_dir']) != os.path.normcase(user):
        raise SetupError(f"Overtime is set up for another emulator folder ({old['user_dir']}); remove it first.")
    entries = {e['path']: e for e in old.get('files', [])}
    folder = patch_dir(user)
    if os.path.isdir(folder) and not entries:
        strangers = set(os.listdir(folder)) - {PATCH_FILE, 'files.json'}
        if strangers:
            raise SetupError(f'{folder} holds files Overtime did not write: {", ".join(sorted(strangers))}')
    cfg_path = custom_config_path(user)
    cfg = _game_config(cfg_path, user)
    m = {'version': 1, 'emulator': os.path.abspath(emu_exe), 'user_dir': user,
         'installed': old.get('installed') or _now(), 'updated': _now(),
         'targets': xmlpatch.targets(xml_text), 'files': []}

    def record():
        m['files'] = list(entries.values())
        _save_manifest(m)

    def put(path, data, previous_keys=None):
        before = _read(path) if os.path.exists(path) else None
        e = entries.get(path)
        if e is None:
            # files in our own folder are ours whatever is there (leftovers of an install that never finished)
            ours = os.path.normcase(os.path.dirname(path)) == os.path.normcase(folder)
            e = {'path': path, 'action': 'replaced' if before is not None and not ours else 'created'}
            if before is not None and not ours:
                backup = paths.app_dir('backups', 'gamesetup', datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')
                                       + os.path.basename(path))
                _write(backup, before)
                e['backup'] = backup
            if previous_keys is not None:
                e['previous'] = previous_keys
            entries[path] = e
        elif before is not None and _sha(before) != e.get('sha256') and e.get('previous') is not None:
            # changed since we wrote it (the user's own edit): from now on remove() only puts our keys back
            e.pop('backup', None)
            e['action'] = 'replaced'
        record()  # before the write: a failure in between still leaves the file on record
        if before != data:
            _write(path, data)
        e['sha256'] = _sha(data)
        record()

    put(os.path.join(folder, PATCH_FILE), xml_text.encode('utf-8'))
    put(os.path.join(folder, 'files.json'), json.dumps({PATCH_FILE: [TITLE_ID]}, indent=4).encode('utf-8'))
    general = cfg.setdefault('General', {})
    if any(general.get(k) != v for k, v in NETWORK.items()) or cfg_path in entries:
        previous = (entries.get(cfg_path) or {}).get('previous') or {k: general.get(k) for k in NETWORK}
        general.update(NETWORK)
        put(cfg_path, json.dumps(cfg, indent=4).encode('utf-8'), previous_keys=previous)
    record()
    return m


def remove(running=None):
    """Undo install(): our files go, replaced files come back from their backups. A file changed since we wrote it
    gets only our keys put back (the custom config, also one we created) or is left alone. Returns what was done."""
    _refuse_while_running(running)
    m = load_manifest()
    if not m:
        return []
    said = []
    for e in reversed(m.get('files', [])):
        path = e['path']
        if not os.path.exists(path):
            said.append(f'already gone: {path}')
            continue
        same = _sha(_read(path)) == e.get('sha256')
        if e['action'] == 'created' and (same or os.path.dirname(path) == patch_dir(m['user_dir'])):
            os.remove(path)
            said.append(f'removed {path}')
        elif same and e.get('backup') and os.path.exists(e['backup']):
            _write(path, _read(e['backup']))
            said.append(f'restored {path}')
        elif e.get('previous') is not None:
            with open(path, encoding='utf-8') as f:
                cfg = json.load(f)
            general = cfg.setdefault('General', {})
            for k, v in e['previous'].items():
                if v is None:
                    general.pop(k, None)
                else:
                    general[k] = v
            _write(path, json.dumps(cfg, indent=4).encode('utf-8'))
            said.append(f'put back the network settings in {path}')
        elif e['action'] == 'created':
            said.append(f'left (changed since Overtime wrote it): {path}')
        else:
            said.append(f'left (no backup to restore): {path}')
    try:
        os.rmdir(patch_dir(m['user_dir']))
    except OSError:
        pass
    _drop_manifest()
    return said


def status(emu_exe=None):
    """{'installed': bool, 'intact': bool, 'targets', 'problems': [...], 'manifest'} for the Setup tab."""
    m = load_manifest()
    if not m:
        return {'installed': False, 'intact': False, 'targets': None, 'problems': [], 'manifest': None}
    problems = []
    if emu_exe and os.path.normcase(emu_user_dir(emu_exe)) != os.path.normcase(m['user_dir']):
        problems.append(f"set up for the emulator data in {m['user_dir']}, not this emulator's")
    for e in m.get('files', []):
        if not os.path.exists(e['path']):
            problems.append(f"missing: {e['path']}")
        elif _sha(_read(e['path'])) != e.get('sha256'):
            problems.append(f"changed since setup: {e['path']}")
    return {'installed': True, 'intact': not problems, 'targets': m.get('targets'), 'problems': problems,
            'manifest': m}


# ---- the clean game ---------------------------------------------------------------------------------------------

HASHED_ALWAYS = ('eboot.bin', os.path.join('sce_sys', 'param.sfo'))


def _file_sha(path, chunk=1 << 20, progress=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            block = f.read(chunk)
            if not block:
                return h.hexdigest()
            h.update(block)
            if progress:
                progress(len(block))


def snapshot(game_dir, full=False, progress=None, pair=True):
    """The game folder as it is: {rel path: [size, sha256 or None]}. Quick = sizes plus eboot.bin and param.sfo
    hashed; full = every file hashed (34 GB, minutes). `progress(done_bytes, total_bytes)`. With an update folder
    beside the base (and `pair`), both: the update's files as `..\\<update folder>\\...`, 'update' names it."""
    base, update = gamefiles.roots(game_dir) if pair else (os.path.abspath(game_dir), None)
    hashed = set(HASHED_ALWAYS)
    files = {}
    for root in (base, update):
        if root is None:
            continue
        hashed |= {os.path.relpath(os.path.join(root, h), base) for h in HASHED_ALWAYS}
        for dirpath, _dirs, names in os.walk(root):
            for n in names:
                p = os.path.join(dirpath, n)
                files[os.path.relpath(p, base)] = [os.path.getsize(p), None]
    total = sum(s for s, _ in files.values()) if full else sum(files.get(r, [0])[0] for r in hashed)
    done = [0]

    def tick(n):
        done[0] += n
        if progress:
            progress(done[0], total)

    for rel in sorted(files):
        if full or rel in hashed:
            files[rel][1] = _file_sha(os.path.join(base, rel), progress=tick)
    return {'game_dir': game_dir, 'update': update, 'made': _now(), 'full': full, 'files': files}


def clean_path():
    return paths.app_dir('clean', TITLE_ID + '.json')


def save_clean(snap):
    _write(clean_path(), json.dumps(snap).encode('utf-8'))


def load_clean():
    try:
        with open(clean_path(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def compare(before, now):
    """Differences between two snapshots: [(rel, 'missing' | 'added' | 'size' | 'content')]. A hash compares only
    where both snapshots have one."""
    out = []
    a, b = before['files'], now['files']
    for rel in sorted(set(a) | set(b)):
        if rel not in b:
            out.append((rel, 'missing'))
        elif rel not in a:
            out.append((rel, 'added'))
        elif a[rel][0] != b[rel][0]:
            out.append((rel, 'size'))
        elif a[rel][1] and b[rel][1] and a[rel][1] != b[rel][1]:
            out.append((rel, 'content'))
    return out


def copy_game(src, dst, progress=None, margin=1 << 30):
    """A full copy of the clean game (optional; the patch never needs it). Refuses without room or into a folder
    that already holds files. `progress(done_bytes, total_bytes)`."""
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    if os.path.normcase(dst).startswith(os.path.normcase(src) + os.sep) or os.path.normcase(dst) == os.path.normcase(src):
        raise SetupError('the copy must go outside the game folder')
    if os.path.isdir(dst) and os.listdir(dst):
        raise SetupError(f'{dst} is not empty')
    snap = snapshot(src, pair=False)
    total = sum(s for s, _ in snap['files'].values())
    probe = dst
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    free = shutil.disk_usage(probe).free
    if free < total + margin:
        raise SetupError(f'not enough room: the copy needs {total / 2**30:.1f} GB, {free / 2**30:.1f} GB free')
    done = 0
    for rel in sorted(snap['files']):
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(src, rel), target)
        done += snap['files'][rel][0]
        if progress:
            progress(done, total)
    if compare(snap, snapshot(dst, pair=False)):
        raise SetupError('the copy does not match the game folder')
    return dst


# ---- firewall (read-only check; the rule is added only on the user's click, through UAC) ------------------------

def firewall_allows(emu_exe):
    """True / False whether an enabled inbound allow rule exists for the emulator, None when Windows won't say."""
    if sys.platform != 'win32':
        return None
    script = ("$p = '" + os.path.abspath(emu_exe).replace("'", "''") + "'; "
              "$r = Get-NetFirewallApplicationFilter -Program $p -ErrorAction SilentlyContinue | Get-NetFirewallRule | "
              "Where-Object { $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' -and $_.Enabled -eq 'True' }; "
              "if ($r) { 'yes' } else { 'no' }")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, text=True, timeout=60,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return {'yes': True, 'no': False}.get(out.splitlines()[-1] if out else '', None)


def firewall_rule_args(emu_exe):
    """netsh arguments for the inbound rule (run elevated, only when the user asks)."""
    return ['advfirewall', 'firewall', 'add', 'rule', f'name={FIREWALL_RULE}', 'dir=in', 'action=allow',
            f'program={os.path.abspath(emu_exe)}', 'enable=yes', 'profile=private,public']
