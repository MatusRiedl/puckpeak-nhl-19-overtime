"""Moving a roster save to the Windows Recycle Bin (Setup's Delete: docs/ui/setup.md, rosters_delete), so the player
can take it out again. Only a Roster* folder right inside the saves folder is ever moved; nothing is deleted for good
without Windows asking first (FOF_WANTNUKEWARNING: a folder the Recycle Bin cannot take, too big or on a drive without
one, brings Windows' own "delete it for good?" question). Standard library only (SHFileOperationW).
"""
import ctypes
import os
import sys

FO_DELETE = 3
FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x0004, 0x0010, 0x0040, 0x0400
FOF_WANTNUKEWARNING = 0x4000
FLAGS = FOF_ALLOWUNDO | FOF_WANTNUKEWARNING | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
PREFIX = 'Roster'     # RosterCustom0-14, RosterOnline*: the game's roster saves


class TrashError(RuntimeError):
    pass


def check(path, save_dir):
    """The folder to move, when it is a roster save right inside the saves folder; TrashError otherwise."""
    path, save_dir = os.path.abspath(path or ''), os.path.abspath(save_dir) if save_dir else ''
    name = os.path.basename(path)
    if not save_dir or os.path.normcase(os.path.dirname(path)) != os.path.normcase(save_dir):
        raise TrashError('Only a roster in your saves folder can be moved to the Recycle Bin.')
    if not name.startswith(PREFIX):
        raise TrashError(f'{name} is not a roster save.')
    if os.path.islink(path) or not os.path.isdir(path):
        raise TrashError('That roster is not there any more.')
    return path


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [('hwnd', ctypes.c_void_p), ('wFunc', ctypes.c_uint), ('pFrom', ctypes.c_wchar_p),
                ('pTo', ctypes.c_wchar_p), ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', ctypes.c_int),
                ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', ctypes.c_wchar_p)]


def _shell_delete(op):
    """SHFileOperationW (the tests put a stub here)."""
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))


def recycle(path, save_dir):
    """Move a roster save folder to the Recycle Bin (Windows only). Returns the path moved."""
    path = check(path, save_dir)
    if sys.platform != 'win32':
        raise TrashError('The Recycle Bin is there only on Windows.')
    op = _SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom=path + '\0\0', pTo=None, fFlags=FLAGS)
    rc = _shell_delete(op)
    if op.fAnyOperationsAborted:
        raise TrashError(f'{os.path.basename(path)} was not deleted.')
    if rc != 0 or os.path.isdir(path):
        raise TrashError(f'Windows could not move {os.path.basename(path)} to the Recycle Bin (code {rc}). '
                         'Close the folder if it is open somewhere, then try again.')
    return path
