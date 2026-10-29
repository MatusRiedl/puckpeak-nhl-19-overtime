"""A key press in shadPS4's window, as window messages (Windows): the player's mouse, keyboard and focus are never touched.

Used by the Multiplayer tab for the two title-screen presses (docs/notes/zero-press.md). The key is the one the player's
own keyboard map gives Cross (`input_config/default.ini`, first single-character `cross =` line: shadPS4's default
profile lists the keypad key first and `n` as the alternative for users without a keypad); 'n' without a readable map.
"""
import ctypes
import os
import subprocess
import sys
import time

from . import gamesetup

DEFAULT_CROSS = 'n'
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101


def cross_key(emu_exe):
    """The keyboard key (one character) the player's map gives Cross, else 'n'."""
    path = os.path.join(gamesetup.emu_user_dir(emu_exe), 'input_config', 'default.ini') if emu_exe else ''
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return DEFAULT_CROSS
    for line in lines:
        if line.strip().lower().startswith('# controller'):     # the pad section follows the keyboard's
            break
        name, _, value = line.partition('=')
        value = value.strip()
        if name.strip().lower() == 'cross' and len(value) == 1 and value.isalnum():
            return value.lower()
    return DEFAULT_CROSS


def emulator_pids():
    """PIDs of the running shadPS4 (any build; not the Qt launcher)."""
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.splitlines():
        cells = line.strip('"').split('","')
        if len(cells) > 1 and cells[0].lower().startswith('shadps4') and 'launcher' not in cells[0].lower():
            pids.append(int(cells[1]))
    return pids


def press(key=DEFAULT_CROSS, hold=0.3):
    """Press `key` (a letter or digit) in the shadPS4 window. True when it was posted, False without a window (or off
    Windows)."""
    if sys.platform != 'win32' or len(key) != 1:
        return False
    import ctypes.wintypes as wt
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    hwnd = None
    for pid in emulator_pids():
        hwnd = _main_window(user32, pid)
        if hwnd:
            break
    if not hwnd:
        return False
    vk = ord(key.upper())
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam = 1 | (scan & 0xFF) << 16
    if not user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam):
        return False
    time.sleep(hold)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam | (3 << 30))
    return True


def _main_window(user32, pid):
    """The largest visible top-level window of `pid`, or None."""
    import ctypes.wintypes as wt
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if user32.IsWindowVisible(hwnd) and owner.value == pid:
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True
    user32.EnumWindows(each, 0)
    return max(found)[1] if found else None
