"""Read-only scan: you go through the game yourself, the scanner only watches.

Nothing is clicked, dragged or focused, the scanner only takes screenshots and
reads them:
- Lobby: AP, Credits and Pyroxene are read when it shows.
- Equipment / Items: click the items one by one and scroll yourself. Every item
  whose details stay on screen for about a second is read.
- A student's page (Student Info): go through your students with the next arrow.

Press F2 (or Ctrl+C here) when done: everything seen is read, saved and
post-processed. Items and students you didn't look at keep their earlier values.

Usage: python -m tools.manual_scan
"""

import logging
import os
import threading
from types import SimpleNamespace

import numpy as np
from pynput import keyboard
from rich.logging import RichHandler

from locations.search import SearchPattern, StudentSearchPattern
from main import run_post_processing
from src.core.config import Config
from src.core.navigator import ScreenNavigator
from src.services.scanners import grids, students
from src.services.scanners.currencies import get_currencies
from src.utils.data.io import read_json, write_json
from src.utils.device.factory import create_device
from src.utils.device.interfaces import DeviceUnavailableError

logger = logging.getLogger("BA-Scanner")

POLL_S = 0.3
# What changes when another item or student is shown. A change has to hold for
# two screenshots in a row, so a panel caught mid-animation isn't kept
WATCHED = {
    "Equipment": (SearchPattern.EQUIPMENT.NAME.value, SearchPattern.EQUIPMENT.OWNED.value),
    "Items": (SearchPattern.ITEM.NAME.value, SearchPattern.ITEM.OWNED.value),
    "Student": (StudentSearchPattern.STUDENT_NAME.value,),
}
SAME = 2.0  # Mean pixel difference under which two crops show the same thing
CURRENCY_TRIES = 3  # Reads per visit of the lobby, a popup may cover the top bar


def _crops(frame: np.ndarray, regions) -> np.ndarray:
    return np.concatenate(
        [frame[r.y : r.bottom, r.x : r.right].reshape(-1) for r in regions]
    ).astype(np.int16)


def _same(a: np.ndarray, b: np.ndarray | None) -> bool:
    return b is not None and float(np.mean(np.abs(a - b))) < SAME


class Watcher:
    """Keeps the screenshots worth reading: one per item or student shown."""

    def __init__(self, screen_of, read_currencies):
        self.screen_of = screen_of  # frame -> "Lobby", "Equipment", "Items", "Student"...
        self.read_currencies = read_currencies  # frame -> True once saved
        self.frames = {name: [] for name in WATCHED}
        self.screen = None
        self.previous = None  # Watched crops of the last screenshot
        self.kept = {}  # Watched crops of the last kept screenshot, per screen
        self.currency_tries = 0

    def feed(self, frame: np.ndarray):
        screen = self.screen_of(frame)
        if screen != self.screen:
            self.screen, self.previous, self.currency_tries = screen, None, 0
            if screen:
                logger.info(f"[cyan]On {screen}[/cyan]")

        if screen == "Lobby" and self.currency_tries < CURRENCY_TRIES:
            self.currency_tries += 1
            if self.read_currencies(frame):
                self.currency_tries = CURRENCY_TRIES  # Saved, once per visit
        if screen not in WATCHED:
            return

        panel = _crops(frame, WATCHED[screen])
        # Unchanged since the last screenshot, but not the one kept last: a new one
        if _same(panel, self.previous) and not _same(panel, self.kept.get(screen)):
            self.frames[screen].append(frame)
            self.kept[screen] = panel
            logger.info(f"{screen}: {len(self.frames[screen])} captured")
        self.previous = panel


def watch(capture, watcher: Watcher, stop: threading.Event):
    """Feed screenshots to the watcher until stop is set. Never sends any input."""
    shown_error = None
    while not stop.is_set():
        try:
            frame = capture()
        except DeviceUnavailableError as e:  # Game closed, window too small...
            if str(e) != shown_error:
                shown_error = str(e)
                logger.warning(f"{e} Still watching.")
            stop.wait(2)
            continue
        if frame is not None:
            watcher.feed(frame)
        stop.wait(POLL_S)


def save(watcher: Watcher, ocr_workers: int = 2):
    """OCR what was captured, merge it into the scanned files and post-process."""
    scanned = set()
    for grid_type in ("Equipment", "Items"):
        frames = watcher.frames[grid_type]
        if not frames:
            continue
        results = grids.process_ocr_results(frames, grid_type, ocr_workers)
        if not results:
            logger.error(f"OCR could not read any {grid_type} item.")
            continue
        owned_file = (
            Config.scanned_equipment if grid_type == "Equipment" else Config.scanned_items
        )
        # ponytail: a merge, items you didn't look at keep their count (also ones
        # used up since). A full scan with main.py replaces the whole file
        write_json(owned_file, {**read_json(owned_file), **results})
        logger.info(f"{grid_type}: {len(results)} items saved to {owned_file}")
        scanned.add(grid_type)

    if watcher.frames["Student"]:
        new = students.to_characters(
            students.process_ocr_results(watcher.frames["Student"], ocr_workers)
        )
        if new:
            old = read_json(Config.scanned_students).get("characters", [])
            merged = {c["name"]: c for c in old} | {c["name"]: c for c in new}
            write_json(Config.scanned_students, {"characters": list(merged.values())})
            logger.info(f"Student: {len(new)} students saved to {Config.scanned_students}")
            scanned.add("Student")
        else:
            logger.error("OCR could not read any student name.")

    run_post_processing(scanned)


def _init_logging():
    logger.handlers = [RichHandler(show_path=False, markup=True)]
    logger.setLevel(logging.DEBUG if Config.DEBUG else logging.INFO)
    logger.propagate = False


def main():
    if Config.settings_error:
        raise SystemExit(
            "Can't use the settings, fix or delete the file, then run python launch.py "
            f"or python -m gui.run:\n{Config.settings_error}"
        )
    os.chdir(Config.PROJECT_ROOT)  # Templates and the OCR models are relative paths
    _init_logging()

    device = create_device(Config.settings, read_only=True)
    if not device.connect(Config.ADB_RETRIES):
        raise SystemExit("Could not connect to the device.")
    navigator = ScreenNavigator(device)  # Only its screen checks, never its taps

    def screen_of(frame):
        screen = navigator.screen_in(frame)
        if screen:
            return screen
        return "Lobby" if navigator.at_home(frame) else None

    def read_currencies(frame):
        return get_currencies(SimpleNamespace(capture_screenshot=lambda: frame))

    watcher = Watcher(screen_of, read_currencies)
    stop = threading.Event()

    def on_press(key):
        if key == keyboard.Key.f2:
            stop.set()

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    logger.info(
        "[bold green]Watching the game, nothing is clicked.[/bold green] Open the lobby, "
        "Equipment, Items or a student's page and go through it yourself. "
        "Press F2 (or Ctrl+C here) when done."
    )
    try:
        watch(device.capture_screenshot, watcher, stop)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()

    logger.info("[bold yellow]Reading what was captured...[/bold yellow]")
    save(watcher)
    logger.info("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
