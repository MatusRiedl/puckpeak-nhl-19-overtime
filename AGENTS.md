# Start here (for AI agents and new developers)

**Puck Peak Overtime** brings NHL 19 (PS4, CUSA11126 v1.60, played on the shadPS4 emulator) back online and up to
today. Players start a Windows exe (**Overtime Roster**), point it at shadPS4 and their own NHL 19 dump, press
**Patch**, and play on the Overtime community server with 32 teams and the 2026-27 calendars. The same app updates and
edits rosters. Explain changes to the project owner in plain words, and leave decisions about publishing, credits and
game-design trade-offs to them.

The window carries the look and logo of **Puck Peak**, the owner's NHL project, in NHL 19's orange. Keep it.

## Layout

| Folder | What is in it |
|---|---|
| `overtime_core/` | The NHL 19 roster codec (`tdb`, `schema`), the roster model and its verify rules (`roster`), roster updates from NHL.com, calendars (`calendar`, `leaguecal`), art packs, the eboot patch builder (`xmlpatch`, `eb`) and the data overlay (`overlay`) |
| `overtime_roster/app/` | The app's controllers: one per tab (`*_ctl.py`), the session (`session.py`), install, save, patch and self-update |
| `overtime_roster/web/` | The window: Preact-style components on React + htm, no build step (`js/tabs/<tab>.js`, `css/tabs/<tab>.css`) |
| `overtime_roster/window/`, `hud/` | The pywebview window and the in-game overlay |
| `patches/`, `client/` | The shadPS4 patch files and the replacement connection texts |
| `packaging/` | `build.ps1` (PyInstaller) and the launcher |
| `tests/` | pytest. Tests marked `game` need your own NHL 19 files: set `OVERTIME_GAME_DIR` |

## Rules that must not be broken

1. **Never commit or distribute game data**: the eboot, `.big` archives, extracted assets, EA certificates or keys,
   raw network captures. The app reads the game's schema and data from the player's own copy at runtime.
2. **Never overwrite a player's save by yourself.** Save writes a new roster folder, or updates the picked roster only
   after a backup copy.
3. **Never write the game folder.** The patch goes into shadPS4's patch folder and an overlay folder next to the game,
   and Unpatch removes both.
4. **Save stops corruption, not edits.** `Roster.verify(strict=False)` blocks only what breaks the game (roster keys,
   capacity, a missing player or team, one player on two teams, a goalie in a skater's place or a skater in goal,
   byte form, field ranges). Pattern rules (`jersey`, `lines`, `captains`) are warnings for a player's own roster.
5. **New code only.** Don't copy GPL code (for example from shadPS4) into this repository.

## Develop

```bash
py -3.13 -m pip install pywebview==6.2.1 certifi pillow numpy pytest
py -3.13 -m overtime_roster --browser            # the app in your browser instead of a window
py -3.13 -m pytest -q                            # tests; game tests skip without OVERTIME_GAME_DIR
```

Build the exe (Windows, its own `.venv-build`):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -DefaultDb <folder with the verified nhl_game.db>
dist\OvertimeNHL19.exe --selftest
```

The default roster, the NHL 27 data pack and the picture packs are made from the maintainer's own game files and are
never in git.
