"""The test run never reaches the owner's app folder or saves, and the exe never uses a path in the temp folder."""
import os
import sys
import tempfile

from overtime_roster.app import controller, paths


def test_run_uses_its_own_app_and_save_folder():
    real = os.path.normcase(os.path.join(os.environ.get('APPDATA', ''), 'OvertimeRoster'))
    home = os.path.normcase(paths.app_home())
    assert home != real
    tmp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    for path in (home, paths.default_save_dir()):
        assert os.path.normcase(os.path.realpath(path)).startswith(tmp)


def test_monkeypatch_puts_back_the_run_folder(monkeypatch, tmp_path):
    before = os.environ['OVERTIME_ROSTER_HOME']
    with monkeypatch.context() as m:
        m.setenv('OVERTIME_ROSTER_HOME', str(tmp_path / 'home'))
    assert os.environ['OVERTIME_ROSTER_HOME'] == before


def test_exe_drops_temporary_paths(monkeypatch, tmp_path):
    real = r'D:\PS4\NHL 19'
    prefs = {'game_dir': str(tmp_path / 'game'), 'save_dir': real, 'save_name': 'x',
             'setup': {'emulator': str(tmp_path / 'shadPS4.exe'), 'skipped': ''}}
    assert controller._no_temporary(prefs) == prefs        # from source: tests use temp paths
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    out = controller._no_temporary(prefs)
    assert 'game_dir' not in out and out['save_dir'] == real and out['save_name'] == 'x'
    assert out['setup'] == {'emulator': '', 'skipped': ''}
    assert not paths.temporary(real) and not paths.temporary('')
