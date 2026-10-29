r"""The kits pack download in the real exe: the release build.ps1 -Kits wrote to dist\ (latest.json "packs",
SHA256SUMS.txt, packs\kits.zip), served over local http; `OvertimeNHL19.exe --download-kits`.
    python packaging/pk1_kits.py <dist folder> <work dir>
Case 1: the release as built -> rc 0, the cache's kits.zip has the published sha256.
Case 2: a wrong sha256 in latest.json and SHA256SUMS.txt -> rc 1, nothing left in the cache.
Case 3: latest.json and SHA256SUMS.txt disagree -> rc 1, nothing downloaded."""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

dist, work = sys.argv[1], sys.argv[2]
shutil.rmtree(work, ignore_errors=True)
site = os.path.join(work, 'site', 'app')
os.makedirs(os.path.join(site, 'packs'))
for name in ('latest.json', 'SHA256SUMS.txt', os.path.join('packs', 'kits.zip')):
    shutil.copyfile(os.path.join(dist, name), os.path.join(site, name))
exe = os.path.join(work, 'OvertimeNHL19.exe')
shutil.copyfile(os.path.join(dist, 'OvertimeNHL19.exe'), exe)
latest = json.load(open(os.path.join(site, 'latest.json'), encoding='utf-8'))
published = latest['packs']['kits.zip']['sha256']
sums = open(os.path.join(site, 'SHA256SUMS.txt'), encoding='ascii').read()


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=os.path.dirname(site)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_address[1]}/app/latest.json'


def run(case):
    home = os.path.join(work, case)
    env = dict(os.environ, OVERTIME_RELEASE_URL=url, OVERTIME_ROSTER_HOME=home)
    rc = subprocess.run([exe, '--download-kits'], env=env, timeout=600).returncode
    kits = os.path.join(home, 'cache', 'kits.zip')
    try:
        log = open(os.path.join(home, 'logs', 'kits.txt'), encoding='utf-8').read().strip()
    except OSError:
        log = '(no log)'
    got = hashlib.sha256(open(kits, 'rb').read()).hexdigest() if os.path.exists(kits) else None
    return dict(rc=rc, sha=got, part_left=os.path.exists(kits + '.part'), log=log)


def write(lat, s):
    json.dump(lat, open(os.path.join(site, 'latest.json'), 'w', encoding='utf-8'))
    open(os.path.join(site, 'SHA256SUMS.txt'), 'w', encoding='ascii').write(s)


result = {'good': run('good')}
bad = json.loads(json.dumps(latest))
bad['packs']['kits.zip']['sha256'] = '0' * 64
write(bad, sums.replace(published, '0' * 64))
result['bad_sha'] = run('bad_sha')
write(latest, sums.replace(published, 'f' * 64))
result['disagree'] = run('disagree')
server.shutdown()
print(json.dumps(result, indent=1))
ok = (result['good']['rc'] == 0 and result['good']['sha'] == published
      and all(result[c]['rc'] == 1 and result[c]['sha'] is None and not result[c]['part_left'] for c in ('bad_sha', 'disagree')))
print('PK1 kits', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
