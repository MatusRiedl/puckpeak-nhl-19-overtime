"""PK1 browser fallback: the exe with OVERTIME_NO_WEBVIEW2=1 serves the page, shows the stop box, quits on OK.
    python packaging/pk1_browser.py <dist exe> <home dir>"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

exe, home = sys.argv[1], sys.argv[2]
env = dict(os.environ, OVERTIME_NO_WEBVIEW2='1', OVERTIME_ROSTER_HOME=home,
           OVERTIME_RELEASE_URL='http://127.0.0.1:9/app/latest.json', BROWSER='cmd /c rem %s')
u32 = ctypes.windll.user32
PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def boxes():
    found = []

    def cb(h, _):
        c = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(h, c, 64)
        t = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, t, 256)
        if c.value == '#32770' and t.value == 'Overtime Roster' and u32.IsWindowVisible(h):
            found.append(h)
        return True
    u32.EnumWindows(PROC(cb), 0)
    return found


def box_text(h):
    out = []

    def cb(c, _):
        n = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(c, n, 64)
        if n.value == 'Static':
            t = ctypes.create_unicode_buffer(1024)
            u32.GetWindowTextW(c, t, 1024)
            out.append(t.value)
        return True
    u32.EnumChildWindows(h, PROC(cb), 0)
    return '\n'.join(out)


p = subprocess.Popen([exe], env=env)
result = {}
box = None
for _ in range(120):
    time.sleep(0.5)
    b = boxes()
    if b:
        box = b[0]
        break
result['box'] = bool(box)
if box:
    text = box_text(box)
    url = re.search(r'http://127\.0\.0\.1:\d+/\?token=\S+', text).group(0)
    result['url_has_token'] = 'token=' in url
    result['page'] = urllib.request.urlopen(url, timeout=10).status
    tok = url.split('token=')[1]
    req = urllib.request.Request(url.split('/?')[0] + '/api/ready', data=b'{"args": []}',
                                 headers={'X-Overtime-Token': tok, 'Content-Type': 'application/json'})
    reply = json.loads(urllib.request.urlopen(req, timeout=30).read())
    result['api_ready_meta'] = reply.get('meta')
    ok = u32.FindWindowExW(box, None, 'Button', 'OK')
    u32.SendMessageW(ok, 0x00F5, 0, 0)
    result['exit'] = p.wait(30)
print(json.dumps(result, indent=1))
print('PK1 browser', 'PASS' if result.get('page') == 200 and result.get('exit') == 0 and result.get('api_ready_meta') else 'FAIL')
