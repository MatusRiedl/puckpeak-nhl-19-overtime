"""Windows: is Microsoft's WebView2 Runtime there (it draws the window)? Windows 11 and an updated Windows 10 have it;
an old Windows 10 may not, and then the app runs in the browser instead. Standard library only."""
import os

CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"      # the Evergreen Bootstrapper


def available():
    """True when the runtime is installed (or when this is not Windows: the question does not arise).
    OVERTIME_NO_WEBVIEW2=1 answers False (to try the browser fallback on a PC that has it)."""
    if os.environ.get('OVERTIME_NO_WEBVIEW2') == '1':
        return False
    if os.name != 'nt':
        return True
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + CLIENT[len("SOFTWARE"):]),
              (winreg.HKEY_LOCAL_MACHINE, CLIENT), (winreg.HKEY_CURRENT_USER, CLIENT)]
    for root, key in places:
        try:
            with winreg.OpenKey(root, key) as k:
                version, _kind = winreg.QueryValueEx(k, 'pv')
                if version and version != '0.0.0.0':
                    return True
        except OSError:
            continue
    return False


def message(title, text, ask=False, info=False):
    """A plain Windows message box (no window toolkit needed). With `ask`: Yes / No, True for Yes."""
    if os.name != 'nt':
        print(f"{title}\n{text}")
        return False
    import ctypes
    if ask:
        flags = 0x00000004 | 0x00000030         # MB_YESNO | MB_ICONWARNING
    else:
        flags = 0x00000040 if info else 0x00000010      # MB_ICONINFORMATION, or MB_ICONERROR
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x00010000) == 6     # MB_SETFOREGROUND; IDYES
