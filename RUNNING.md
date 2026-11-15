# Cannon: Eight Days Left

Exam project developed with Python 3.11 and Kivy 2.3.0. The campaign has ten
levels in which the player must destroy the Rust Swarm beacons before the
Foreman's fleet reaches the colonies. The game includes three weapons,
obstacles with different behaviours, two boss encounters, three difficulty
settings, three save slots and a Hall of Fame.

## Running the game

Open a terminal in the `Project` directory, which contains `main.py` and
`requirements.txt`, then run the commands for your operating system.

On macOS and Linux:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

On Windows PowerShell, after installing Python 3.11 with the Python Launcher:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

The first run asks for the commander's name and shows the introduction. Once
these two steps have been completed, later runs open the menu after the loading
screen.

## Controls

- Mouse: aim the cannon.
- Mouse wheel or Up and Down arrows: adjust the initial speed.
- Left and Right arrows: fine-tune the angle.
- `1`, `2`, `3`: select Bullet, Bombshell or Laser when available.
- `Space` or click: advance dialogue, close the briefing, or fire while aiming.
- `Enter`: continue after a victory or retry after a defeat.
- `S`: choose a slot on the first save, then save to the active slot.
- `Shift+S`: choose another slot. `L`: open the load screen.
- `Esc`: return to the menu.

During a game, `S` and `L` are available while the cannon is in the aiming
state. The load screen can also be opened from the menu. Every shot counts
towards the campaign total. Easy has no per-level shot limit, Normal uses each
level's standard limit, and Hard reduces it.

## Settings and data

Settings can change the player name, difficulty, music and sound-effect
volumes, trajectory preview, instant text and reduced motion. The selected
difficulty is locked when a new campaign begins.

Settings, Hall of Fame entries and save slots are stored in the application
directory managed by Kivy. Set `CANNON_DATA_DIR` before launch to use a
different directory, for example:

```bash
CANNON_DATA_DIR=/tmp/cannon-data .venv/bin/python main.py
```

In PowerShell:

```powershell
$env:CANNON_DATA_DIR = "$PWD\cannon-data"
.\.venv\Scripts\python.exe main.py
```

The Help screen also allows the introduction to be replayed or the player name
and initial onboarding path to be reset. This does not delete save slots, Hall
of Fame entries or preferences.

## Project structure

- `main.py`: application entry point and screen construction.
- `game/`: physics, levels, interface, audio and persistence.
- `assets/`: images, runtime music, sound effects, fonts and their licences.

Credits and asset sources are listed in [CREDITS.md](CREDITS.md).

## Validation and source

Twelve automated checks cover geometry, ballistic motion, laser paths, settings, save consistency and asset checksums. They were added and run for the November 2026 publication. Rendering, sound and interactive timing still require manual checks; the submitted report records the original playtesting and known limitations.

The submitted game code, assets, report and credits are unchanged by this documentation update. [Source checksums](docs/source-manifest.json) identify the original files. The README, extracted report screenshot and automated checks were added when the project was published. The later [gameplay clip](docs/media/cannon-showcase.mp4) and [GIF](docs/media/cannon-showcase.gif) were supplied by Matteo for the repository showcase.
