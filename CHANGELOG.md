# Changelog

What changed in each version, for players.

## 0.20.0 (2026-10-30)

A hotfix for players whose NHL 19 update sits in a folder of its own.

### Fixed

- **NHL 19 with the update in its own folder.** shadPS4 can install update 1.60 beside the game, as `CUSA11126-patch`
  (or `CUSA11126-UPDATE`) next to the base game `CUSA11126`. Overtime read only one of the two folders and stopped with
  errors like `nhl/data/kettle/loc/eng_us-meta.xml not in ...\CUSA11126-patch`. Now it reads the two together, as the
  emulator does, whichever of them is picked:
  - Setup lists the game once, as the base folder.
  - The game patch goes to `CUSA11126-mods`, the folder shadPS4 reads for that game. If 0.10.0 left a
    `CUSA11126-patch-mods` folder, delete it.
  - The Quick check and Verify every file cover both folders.
  - If you merged the update into the base folder by hand to get around this, that keeps working.
- **Calendar tab:** "My season" no longer says it comes after beta2. It is still to come.
- **Setup tab:** the Online card (server address, firewall) shows only on the Multiplayer tab now, not on both.

## 0.10.0 (2026-10-29)

The first public release. It includes everything from the closed betas (0.1.0-beta1 to beta4).

### What is new

- **Multiplayer tab** (closed beta): join or host a lobby on the Overtime server, the host picks the match rules and
  both games bake them in, the game starts with one press, and finished games land in your match history. Elo
  rating with nine ranks, a leaderboard in the app and on the public web board, lobby chat and an in-game overlay.
  - The app presses READY on Game Setup once the server sees your game there, instead of on a timer. If no search
    starts, the card tells you to press it.
  - The match rules use the game's own words (Competitive, Full Sim, Continuous OT, ...).
  - The History card says what the Overtime server keeps about you. "Show me on the web board" hides your name
    there.
  - The game gets the online roster itself: when you press PLAY in Online Versus, it downloads the current one if
    yours is older.
- **Update warns when NHL 19 needs the patch**: when the game is not patched, the patch has a problem, or an older
  Overtime patched it. "Go to Game patch" takes you there.
- **Seattle in Be a Pro.** Choose Team lists the Seattle Kraken and a career on Seattle plays, saves and loads. It
  needs the game patch with the league layer; with the league layer off, Be a Pro keeps the game's 31 teams.
- **Real 2026-27 calendars for the AHL and Liiga**, next to the NHL's:
  - AHL: all 32 clubs, 72 games each, each real club on its NHL parent's farm-team place (Coachella Valley on
    Seattle's). Official statistics provided by American Hockey League.
  - Liiga: the game's 15 clubs, 56 games each. Jokerit and K-Espoo have no place in NHL 19, so their games are left
    out.
  - The Calendar tab shows them: pick an AHL or Liiga club for its games, or "All AHL games" / "All Liiga games".
  - Every other league keeps the game's own calendar: no official schedule feed was found for the ECHL, OHL, WHL,
    QMJHL, SHL, HockeyAllsvenskan, DEL, Czech Extraliga, Swiss National League, ICE Hockey League, Champions League
    or the Spengler Cup.
  - **The calendars travel with the roster.** A new Franchise or Season takes its league calendars from the roster
    you have loaded in the game. The new default and online rosters carry them; an older saved or downloaded roster
    keeps the game's AHL and Liiga calendars until you run Update over it (Update writes them) or load the new online
    roster.
  - 32 Team Expansion Draft Franchise: Seattle and Utah each play their own real schedule in their own division, 84
    games each.
- **Photos and logos are a download now.** The Game patch tab has one "Photos, logos pack" card (about 155 MB):
  Download gets the four packs and switches them on, Remove deletes them. A fresh install starts with them off and
  Patch never downloads by itself. If you had the packs already, they stay on. Without the pack, Utah plays in the
  Coyotes' look and Seattle shows a stand-in crest (EA SPORTS) and kit; games play normally.
- **Sign free agents** from the Front office (Free agents group, Sign window, one Undo).
- **Photos switch**: put back the game's own player photos without undoing the rest of the patch.
- **Real equipment** from the NHL 27 pack (sock tuck, pants, tape colours, goalie neck guard).
- **Export to a folder** picks the game slot the folder is made for.
- The Lines tab shows each player's shooting or catching hand. Game patch sits before Update. Easier-to-read
  headings.
- Fixed: Patch brings the hub's Puck Peak news tile back where a beta patch had left it empty (press Patch once
  with 0.10.0; the Update tab asks for it).
- Fixed: Update no longer crashes on a roster save without the game's career tables.
- **Fewer refusals when you edit a roster.** The app now allows these edits: two teammates with the same number, more than three
  letters, an empty or doubled place in the lines. Save lists these as warnings and saves anyway. It still stops what
  breaks the game: a roster place for a missing player or team, one player on two teams, a skater in goal or a goalie
  in a skater's place, more rows than the game holds, or more than 40 players on a team.
  Roster keys out of order are put right on Save.

### Known limits

- **Be a Pro, Seattle and Utah dates.** Be a Pro keeps Seattle in the Central and Utah in the Pacific. Each team's
  divisional games match that, but Seattle plays Utah's real 2026-27 dates and Utah plays Seattle's. A 32 Team
  Expansion Draft Franchise is right.
- **Classic Franchise and NHL Season have 31 clubs.** The team lists show 32, but the game builds the league with
  Seattle in Utah's place: Utah is not in the league and Seattle plays Utah's real 82-game calendar. For both teams,
  start a Franchise with "32 Team Expansion Draft". This has been so since Overtime added Seattle; it is not new in
  0.10.0.
- Season mode lists Seattle (0 OVR) among the teams of other leagues too, for example the Liiga. It is not part of
  those leagues: the season plays with the league's own clubs.
- Multiplayer is a closed beta: the lobby trusts the name you give it, and a game between two separate PCs has not been
  played through yet.
- Lines you set by hand are not kept in My edits while Real lines and captains is on (as in beta4).
- The looser roster edits were checked in game on every NHL team at once (shared numbers, five letters, an empty and a
  doubled line place, cloned skaters): the roster loads, the hub runs and Play Now reaches team select. A full match
  with all of them together was not played before release.
