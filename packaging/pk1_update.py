"""PK1 self-update test of the real exe: a local http release site, an installed copy, `--update` in the copy.
    python packaging/pk1_update.py <dist exe> <work dir>
Case 1: bad sha256 in SHA256SUMS -> refused, exe unchanged, exit 1.
Case 2: good release (the dist exe + a marker) -> swapped, .old kept, exit 0; the new exe passes --selftest.
Case 3: up to date -> exit 3."""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

src, work = sys.argv[1], sys.argv[2]
shutil.rmtree(work, ignore_errors=True)
site, inst, home = (os.path.join(work, p) for p in ('site/app', 'install', 'home'))
for d in (site, inst, home):
    os.makedirs(d)
exe = os.path.join(inst, 'OvertimeNHL19.exe')
shutil.copyfile(src, exe)
new = open(src, 'rb').read() + b'\0OVERTIME-PK1-NEW-BUILD\0'
open(os.path.join(site, 'OvertimeNHL19.exe'), 'wb').write(new)
good = hashlib.sha256(new).hexdigest()


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=os.path.dirname(site)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_address[1]}/app/latest.json'
env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
env.update(OVERTIME_RELEASE_URL=url, OVERTIME_ROSTER_HOME=home,
           PATH=os.pathsep.join(p for p in env['PATH'].split(os.pathsep) if 'python' not in p.lower()))


def run(*args):
    return subprocess.run([exe, *args], env=env, timeout=180).returncode


def log(name):
    try:
        return open(os.path.join(home, 'logs', name), encoding='utf-8').read().strip()
    except OSError:
        return '(no log)'


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


old_sha = sha(exe)
result = {}
open(os.path.join(site, 'latest.json'), 'w').write(json.dumps({'version': '9.9.9', 'exe': 'OvertimeNHL19.exe'}))
open(os.path.join(site, 'SHA256SUMS.txt'), 'w').write(f'{"0" * 64}  OvertimeNHL19.exe\n')
rc = run('--update')
result['bad_sha'] = dict(rc=rc, unchanged=sha(exe) == old_sha, new_left=os.path.exists(exe + '.new'),
                         old_left=os.path.exists(exe + '.old'), log=log('update.txt'))
open(os.path.join(site, 'SHA256SUMS.txt'), 'w').write(f'{good}  OvertimeNHL19.exe\n')
rc = run('--update')
result['good'] = dict(rc=rc, swapped=sha(exe) == good, old_is_previous=os.path.exists(exe + '.old') and sha(exe + '.old') == old_sha,
                      log=log('update.txt'))
result['new_selftest'] = dict(rc=run('--selftest'), log=log('selftest.txt').splitlines()[-1])
open(os.path.join(site, 'latest.json'), 'w').write(json.dumps({'version': '0.1.0'}))
result['up_to_date'] = dict(rc=run('--update'), log=log('update.txt'))
server.shutdown()
print(json.dumps(result, indent=1))
ok = (result['bad_sha']['rc'] == 1 and result['bad_sha']['unchanged'] and not result['bad_sha']['new_left']
      and result['good']['rc'] == 0 and result['good']['swapped'] and result['good']['old_is_previous']
      and result['new_selftest']['rc'] == 0 and result['up_to_date']['rc'] == 3)
print('PK1 update', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
