"""Entry point of OvertimeNHL19-cli.exe (build.ps1 -Cli), and of `python packaging/launcher_cli.py` from source: the
same app with a console to print to (--browser, --selftest, --update)."""
import os
import sys

if not getattr(sys, 'frozen', False):       # from source: the repository root, not packaging/, is the import root
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overtime_roster.window import main as window

sys.exit(window.entry())
