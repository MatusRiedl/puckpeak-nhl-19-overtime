"""PK1 in-window update: the exe's 12 h check offers a newer release, Yes is clicked, the exe swaps and restarts.
    python packaging/pk1_restart.py <dist exe> <work dir>"""
import ctypes
import ctypes.wintypes as wt
import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

src, work = sys.argv[1], sys.argv[2]
shutil.rmtree(work, ignore_errors=True)
site, inst, home = (os.path.join(work, p) for p in ('site/app', 'install', 'home'))
for d in (site, inst, home):
    os.makedirs(d)
exe = os.path.join(inst, 'OvertimeNHL19.exe')
shutil.copyfile(src, exe)
new = open(src, 'rb').read() + b'\0OVERTIME-PK1-RESTART\0'
open(os.path.join(site, 'OvertimeNHL19.exe'), 'wb').write(new)
open(os.path.join(site, 'SHA256SUMS.txt'), 'w').write(f'{hashlib.sha256(new).hexdigest()}  OvertimeNHL19.exe\n')
open(os.path.join(site, 'latest.json'), 'w').write(json.dumps({'version': '9.9.9', 'notes': 'PK1 restart test'}))


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=os.path.dirname(site)))
threading.Thread(target=server.serve_forever, daemon=True).start()
env = dict(os.environ, OVERTIME_RELEASE_URL=f'http://127.0.0.1:{server.server_address[1]}/app/latest.json',
           OVERTIME_ROSTER_HOME=home)
u32 = ctypes.windll.user32
PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def windows(pid=None, cls=None):
    found = []

    def cb(h, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        buf = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, buf, 256)
        t = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, t, 256)
        if u32.IsWindowVisible(h) and (pid is None or p.value == pid) and (cls is None or buf.value == cls):
            found.append((h, p.value, buf.value, t.value))
        return True
    u32.EnumWindows(PROC(cb), 0)
    return found


def pids():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq OvertimeNHL19.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"OvertimeNHL19')}


before = pids()
first = subprocess.Popen([exe], env=env)
result = {'first_pid': first.pid}
box = None
for _ in range(120):
    time.sleep(0.5)
    boxes = [w for pid in pids() - before for w in windows(pid, '#32770')]
    if boxes:
        box = boxes[0]
        break
result['asked'] = bool(box)
result['python_pid'] = box and box[1]
if box:
    yes = u32.FindWindowExW(box[0], None, 'Button', '&Yes')
    u32.SendMessageW(yes, 0x00F5, 0, 0)         # BM_CLICK
    try:
        first.wait(60)
    except subprocess.TimeoutExpired:
        pass
    result['first_exited'] = first.poll()
    second = None
    for _ in range(60):
        time.sleep(0.5)
        others = pids() - before - {first.pid, box[1]}
        second = next((pid for pid in others if any(w[3].startswith('Overtime Roster') for w in windows(pid))), None)
        if second:
            break
    result['restarted_pid'] = second
    result['swapped'] = hashlib.sha256(open(exe, 'rb').read()).hexdigest() == hashlib.sha256(new).hexdigest()
    time.sleep(3)
    if second:
        for h, *_ in windows(second):
            u32.PostMessageW(h, 0x0010, 0, 0)    # WM_CLOSE: close the restarted window gracefully
        time.sleep(4)
    result['old_cleaned_by_restart'] = not os.path.exists(exe + '.old')
server.shutdown()
print(json.dumps(result, indent=1))
ok = result['asked'] and result.get('first_exited') == 0 and result.get('restarted_pid') and result.get('swapped')
print('PK1 restart', 'PASS' if ok else 'FAIL')
