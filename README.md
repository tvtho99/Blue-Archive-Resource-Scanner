# Blue Archive Resources Scanner

<h1 align="center">⚠️Attention: Look at dev branch if you want latest code.

</h1>

![Logo](assets/images/BA-Scanner-banner-light.png)

A Python-based tool to scan and count owned resources in **Blue Archive**.

**Resolution**: Emulators and devices: 1280x720 only. PC client (Steam): any window size with a 16:9 game picture of at least 1280x720.

> **TL;DR:** The scanner automates navigation through the game's menus to collect information that is already visible on screen. It uses screenshots and OCR to read that information and does not modify the game, memory, files, or network traffic, nor does it automate gameplay.

## Disclaimer & Scope

**Blue Archive Resource Scanner is an unofficial community-made project and is not affiliated with, endorsed by, or sponsored by Nexon or Blue Archive.**

The scanner automates navigation through relevant Blue Archive menus, captures screenshots of the information displayed by the game, and uses OCR to recognize the values shown on screen.

The resulting information is processed locally and converted into structured data for resource and inventory tracking.

### What It Does

* Automatically navigates relevant in-game menus.
* Captures screenshots of information displayed by the game.
* Uses OCR to recognize visible values (it can be inaccurate).
* Collects resource and inventory information.
* Processes the collected information locally.
* Produces structured data for resource tracking and planning.

### What It Does Not Do

* Does **not** modify the game client.
* Does **not** modify game files.
* Does **not** read or modify process memory.
* Does **not** inject code into the game.
* Does **not** intercept, inspect, or modify network traffic.
* Does **not** communicate with undocumented game APIs.
* Does **not** automate combat.
* Does **not** automate farming or stage completion.
* Does **not** automatically perform gacha or purchases.
* Does **not** automatically claim rewards.
* Does **not** attempt to bypass security or anti-cheat mechanisms.

The purpose of the automation is **information collection**, rather than playing the game on the user's behalf.

### Terms of Service

This project does not claim to be authorized, endorsed, or approved by Nexon.

Users are responsible for complying with the applicable Blue Archive/Nexon Terms of Service and other applicable policies. If you are uncertain whether using this software is permitted, please review the current official terms before using it.

### Third-Party Data

The scanner uses a separate community-maintained data repository:

* [BA-Scanner-Data](https://github.com/FleetingComet/BA-Scanner-Data)

The data in that repository includes **processed information based on Schale DB**, an unofficial database for Blue Archive maintained independently of this project.

Schale DB is an unofficial database for **Blue Archive**, developed and maintained independently of this project.

The scanner does **not** directly download game assets, game files, or proprietary data from Nexon's servers as part of this data synchronization process.

The `BA-Scanner-Data` repository is maintained separately from the scanner itself so that data updates can be distributed without requiring a new version of the scanner.

Please refer to the respective repositories and websites for their own licensing, attribution, and terms of use.

## Features

- **Scan Equipment and Item Page**: Scan and count resources in the equipment and item page.
- **Scan Student Page**: Extract levels, skill tiers, gear, UE stars, and bond levels.
- **Scan Currencies**: Scan AP, Credits, and Pyroxene.

---

## Requirements

To use the Blue Archive Resources Scanner, ensure you have the following installed:

- **Python** 3.13 or higher
- **Virtual Environment** (highly recommended)

---

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/FleetingComet/BA-Scanner.git
   cd BA-Scanner
   ```

   (You can skip this if you want)

2. Create the virtual environment and install the required packages with [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # macOS/Linux
   ```

   Without uv, use the standard library instead (a uv venv has no `pip`, so don't mix the two):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   python -m pip install -r requirements.txt
   ```

---

## Documentation

See the docs/website index for quick links to user and developer guides:
- [https://fleetingcomet.github.io/BA-Resource-Scanner-Docs/](https://fleetingcomet.github.io/BA-Resource-Scanner-Docs/)

## Usage

### Running the Scripts

#### Quick Start (Windows)

Double-click **`run.bat`** (or run it from a terminal). On the first run it installs the Python packages (with uv if installed, else with Python 3.13+), then shows a menu: automatic scan, read-only scan, settings, layout check, the three exporters and the data update. Each option explains what to do in the game before it starts.

#### First Run & Configuration

The scanner now uses an interactive setup wizard. Run:

```bash
python launch.py
```

The wizard will guide you through:

1. **Platform Selection**: Emulator (MuMu, LDPlayer, etc.), Desktop Client (Steam), or Real Device.
2. **ADB Connection**: Lets you enter a custom IP/port. (Auto-fill ports coming soon)
3. **Scan Targets**: Choose which inventories to scan (`Equipment`, `Items`, `Students`, `Currencies`).
4. **Performance Tuning**: Adjust wait-time multipliers for slower devices or emulators.
5. **Data Sync**: Enable/disable automatic downloads of the latest community-maintained scanner data.

Your choices are saved to `config/settings.json` and `config/screen_config.json`. You won't need to run the wizard again unless you want to change settings.

#### Running the Scanner

- **Standard Run** (uses saved settings):
  ```bash
  python launch.py
  ```
- **Edit Configuration** (re-run wizard with current values as defaults):
  ```bash
  python launch.py -e   # or --edit
  ```
- **Force Offline Mode** (skips network sync, runs directly):
  ```bash
  python main.py --offline
  ```

Once started, the scanner automatically navigates the game, captures screenshots, extracts data using the selected OCR engine, and saves the results to the `output/` directory.

#### PC Client (Steam)

Choose **PC client / desktop window** in the wizard. The scanner finds the window titled `Blue Archive` and detects its size on every screenshot. It finds the 16:9 game picture inside the window, skipping the black bars the game draws when the window or monitor is not 16:9 (for example fullscreen on a 16:10 laptop or an ultrawide monitor), and scales it to 1280x720.

**Window size:** any size works as long as the 16:9 game picture is at least **1280x720**. Bigger is fine. Sizes that scale exactly (1280x720, 2560x1440, 3840x2160) give the cleanest OCR. If the picture is smaller, or the window is not 16:9 and has no black bars, the scan pauses, tells you what to change, and continues by itself once the window is fixed. It stops after 60 seconds.

In the game options:

- **Screen Mode**: Window or Fullscreen.
- **Screen Ratio**: 16:9.
- **Language**: English. The scanner reads page titles and item names in English only.
- **Display Shortcut Icons**: Off. The key badges cover text the scanner reads.
- Disconnect controllers. The game ignores the mouse while one is connected.
- Turn off Steam overlay notifications while scanning. They are drawn into the game picture and can cover items.

While scanning, the scanner moves your real mouse, so don't touch it. Keep the whole game window on screen. If clicks do nothing, make sure the game and the scanner run at the same permission level (both as a normal user, or both as administrator).

To stop a scan, press **F2** (scans started with `launch.py`) or **Ctrl+C** in the terminal. Screens that finished before the stop are still processed, which can take a few seconds. Pressing Ctrl+C again while `launch.py` waits kills the scan at once, without processing. Moving the mouse into a screen corner also stops the scan (pyautogui failsafe).

> **Warning:** The Steam client ships Nexon Game Security, a kernel-level anti-cheat, and the Blue Archive Terms of Service prohibit macros and automated data collection. Using the scanner on PC may put your account at risk. Use it at your own discretion.

#### Read-only Mode (no clicks)

The normal scan moves your mouse to go through the menus, which is what makes it a macro. In read-only mode you go through the game yourself and the scanner only takes screenshots and reads them. It never clicks, drags, presses keys in the game, or focuses the game window:

```bash
python -m tools.manual_scan
```

- **Lobby**: AP, Credits and Pyroxene are read when the lobby shows.
- **Equipment / Items**: click the items one by one and scroll yourself. Keep each item's details on screen for about a second; the console counts every item it captured.
- **Students**: open a student's page and go through your students with the next arrow, about a second per student.

Press **F2** (or Ctrl+C in the terminal) when done. Everything captured is read, saved and post-processed, so the exporters work as after a normal scan. The results are merged into `output/owned/`: items and students you didn't look at keep their earlier values, including items you have used up since (a normal scan replaces the whole file). It works for the PC client and for emulators.

#### Checking the Layout

To check that the scan regions line up with your game screen, run:

```bash
python -m tools.capture_layout
```

Navigate the game by hand, then type the screen you are on (`home`, `menu`, `equipment`, `items`, `students`, `student`). The tool only takes screenshots and never clicks. It saves the screenshot and a copy with every scan region drawn on it to `output/layout/`.

#### Output Files

After a successful scan, check the `output/` folder:

- `owned/scanned_equipment.json`, `owned/scanned_items.json` -> Raw equipment & item counts, replaced on every complete scan of that screen. A scan that could not finish (no slots found, the grid would not scroll, a stop) keeps the previous file.
- `owned/scanned_students.json` -> Raw student stats
- `owned/scanned_currencies.json` -> AP, Credits, Pyroxene
- `equipment_final_values.json`, `items_final_values.json`, `students_final_values.json` -> Processed & mapped data ready for planning

### Exporters

### Justin163 Planner

Use the Justin163 Planner exporter to convert your scanned data and generate a file compatible with the planner:

```bash
python -m tools.justin_planner
```

The script will generate:

* **`output/justin_data_final.json`**: The converted and/or merged data compatible with Justin Planner.

#### Using an Existing Justin Planner Export

If you already have a Justin163 Planner export and want to merge it with the converted data:

1. Save your existing Justin Planner export as `justin_data.json`.
2. Place it in:
   **`input/justin_data.json`**
3. Run the exporter:

   ```bash
   python -m tools.justin_planner
   ```

The exporter will automatically use `input/justin_data.json` when available, and starts from an empty template only when that file does not exist. A file that exists but can't be read stops the exporter with an error, because importing a template-based result would replace your whole planner.

Alternatively, you can specify a different Justin Planner export using the `--file` option (the exporter stops with an error if that file is missing or unreadable):

```bash
python -m tools.justin_planner --file path/to/justin_data.json
```

Scanned Activity Reports, Eligma, Equipment Blueprint Choice Boxes and General blueprints are written under the planner's own keys, and each student's Eleph goes to that character's owned Eleph.

#### Optional Arguments

The exporter supports the following options:

| Option                | Description                                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `-m`, `--max-target`  | Set target stats to **MAX** for newly added characters.                                                               |
| `-f`, `--file <path>` | Path to an existing Justin Planner export to merge with. Uses the default `input/justin_data.json` path when omitted. |
| `-o`, `--online`      | Download the latest community-maintained data before processing.                                                      |

For example:

```bash
python -m tools.justin_planner -m -o
```

After processing, import the generated file **`output/justin_data_final.json`** into Justin163 Planner.

---

### Midokuni Roster URL Format

Use the Midokuni exporter to convert your scanned data into a roster URL compatible with Midokuni:

```bash
python -m tools.midokuni
```

The exporter will generate the Midokuni roster URL after processing your scanned data.

#### Optional Arguments

The exporter supports the following options:

| Option                        | Description                                                      |
| ----------------------------- | ---------------------------------------------------------------- |
| `-s`, `--state <blue\|black>` | Set all characters to the specified state.                       |
| `-o`, `--online`              | Download the latest community-maintained data before processing. |

For example:

```bash
python -m tools.midokuni -s blue -o
```

---

### Schale DB Import Format

Use the Schale DB exporter to convert your scanned data into a format compatible with Schale DB:

```bash
python -m tools.schaledb
```

The exporter will generate the Schale DB import data after processing your scanned data.

> **Note:** Schale DB's Import Collection **replaces** your whole collection. To keep students the scan missed, copy your Schale DB "Export Collection" text into a file and pass it with `--file`: the scan is merged into it. The exporter refuses to write a file without any scanned student.

#### Optional Arguments

The exporter supports the following options:

| Option                | Description                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------ |
| `-l`, `--lock`        | Set the `lock` field to **true** for all characters (otherwise the lock flags from `--file` are kept). |
| `-f`, `--file <path>` | Text file with your Schale DB "Export Collection" data to merge the scan into.                         |
| `-o`, `--online`      | Download the latest community-maintained data before processing.                                       |

For example, to mark all characters as locked:

```bash
python -m tools.schaledb --lock
```

You can also combine both options:

```bash
python -m tools.schaledb -l -o
```


---

## Roadmap

### Current Checklist:

- Read more resources (some of them needs modification, their [Search Region](/locations/search.py) are already defined)
  - [x] Credits
  - [x] Pyroxene
  - [x] Items Page, Equipment Page
  - [x] Student stats
    - [x] Skill levels (eg.: M/M/7/8)
    - [x] Unique Equipment level (is UE60?, is Level 60?)
    - [ ] the new constelation stuffs
- [ ] Different Resolution
- [x] Make screen capturing faster
- [x] More accurate and faster data reading

<!-- - [ ] Comet Haley -->
<!-- - [x] Earth (Orbit/Moon) -->

### Future Plans:

- Expand support for different resolutions (with bars and notch).
- Support other platforms (Linux) (someone tested it using waydroid)
  - Develop an Android app for convenient usage (using Kotlin, pls help I have skill issue).

---

## Credits

This project was inspired by and credits:

- [Fate/Grand Automata (FGA)](https://github.com/Fate-Grand-Automata/FGA)
- [AzurLaneAutoScript (ALAS)](https://github.com/LmeSzinc/AzurLaneAutoScript)
- [Schale DB](https://github.com/SchaleDB/SchaleDB)
- [Justin163 Planner](https://justin163.com/planner/)
- [Hina Loves Midokuni](https://hina.loves.midokuni.com/)

---

## Contributing

I welcome contributions to enhance the Blue Archive Resources Scanner. Please open an issue or submit a pull request if you'd like to help. Be sure to read the [Contribution Guide](CONTRIBUTING.md) for more information.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---
