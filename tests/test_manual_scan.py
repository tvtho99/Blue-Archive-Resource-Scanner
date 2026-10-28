"""Read-only scan: the watcher, saving, and that nothing ever sends input."""

import json
import threading

import numpy as np
import pytest

from locations.search import SearchPattern, StudentSearchPattern
from src.utils.device.interfaces import DeviceUnavailableError
from tools import manual_scan

SCREENS = [None, "Lobby", "Equipment", "Items", "Student"]
PANELS = {
    "Equipment": SearchPattern.EQUIPMENT.NAME.value,
    "Items": SearchPattern.ITEM.NAME.value,
    "Student": StudentSearchPattern.STUDENT_NAME.value,
}


def frame(screen, shown=0):
    """1280x720 screenshot: pixel (0, 0) says the screen, the panel what is shown."""
    image = np.zeros((720, 1280, 3), np.uint8)
    image[0, 0] = SCREENS.index(screen)
    if screen in PANELS:
        r = PANELS[screen]
        image[r.y : r.bottom, r.x : r.right] = 10 * shown
    return image


def screen_of(image):
    return SCREENS[int(image[0, 0, 0])]


def shown_in(image, screen):
    r = PANELS[screen]
    return int(image[r.y, r.x, 0]) // 10


def test_keeps_one_screenshot_per_item_and_student():
    reads = []
    watcher = manual_scan.Watcher(screen_of, lambda image: reads.append(1) or True)
    sequence = [
        frame("Lobby"), frame("Lobby"),
        frame("Equipment", 1), frame("Equipment", 1), frame("Equipment", 1),
        frame("Equipment", 2),  # Mid-animation: shown once only, not kept
        frame("Equipment", 3), frame("Equipment", 3),
        frame("Equipment", 1), frame("Equipment", 1),  # Clicked again later: kept again
        frame("Student", 4), frame("Student", 4), frame("Student", 5), frame("Student", 5),
    ]
    for image in sequence:
        watcher.feed(image)

    kept = {s: [shown_in(f, s) for f in fs] for s, fs in watcher.frames.items()}
    assert kept == {"Equipment": [1, 3, 1], "Items": [], "Student": [4, 5]}
    assert reads == [1]  # Currencies saved once per lobby visit


def test_currencies_are_retried_a_few_times_per_lobby_visit():
    reads = []
    watcher = manual_scan.Watcher(screen_of, lambda image: reads.append(1) and False)
    for image in [frame("Lobby")] * 10 + [frame(None)] + [frame("Lobby")] * 2:
        watcher.feed(image)
    assert len(reads) == manual_scan.CURRENCY_TRIES + 2  # A new visit retries


class NoInputDevice:
    """Screenshots from a list. Any input fails the test."""

    def __init__(self, frames, stop):
        self.frames = list(frames)
        self.stop = stop

    def capture_screenshot(self):
        if not self.frames:
            self.stop.set()
            return None
        item = self.frames.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def tap(self, *args, **kwargs):
        raise AssertionError("tapped")

    def swipe(self, *args, **kwargs):
        raise AssertionError("swiped")


def test_watch_never_sends_input_and_survives_a_lost_window(monkeypatch, caplog):
    stop = threading.Event()
    monkeypatch.setattr(stop, "wait", lambda seconds: stop.is_set())
    device = NoInputDevice(
        [
            frame("Equipment", 1), frame("Equipment", 1),
            DeviceUnavailableError("Window 'Blue Archive' not found."),
            DeviceUnavailableError("Window 'Blue Archive' not found."),
            frame("Equipment", 2), frame("Equipment", 2),
        ],
        stop,
    )
    watcher = manual_scan.Watcher(screen_of, lambda image: True)

    manual_scan.watch(device.capture_screenshot, watcher, stop)

    assert [shown_in(f, "Equipment") for f in watcher.frames["Equipment"]] == [1, 2]
    assert caplog.text.count("not found. Still watching.") == 1


def test_save_merges_into_the_scanned_files(monkeypatch, tmp_path):
    config = manual_scan.Config
    for name in ("scanned_equipment", "scanned_items", "scanned_students"):
        monkeypatch.setattr(config, name, tmp_path / f"{name}.json")
    config.scanned_equipment.write_text(json.dumps({"Rusty Spring": 5, "Old Hat": 1}))
    config.scanned_students.write_text(
        json.dumps({"characters": [{"name": "Aru", "current": {"level": 1}}]})
    )
    monkeypatch.setattr(
        manual_scan.grids,
        "process_ocr_results",
        lambda frames, grid_type, workers: {"Rusty Spring": 9, "New Gloves": 2},
    )
    monkeypatch.setattr(
        manual_scan.students,
        "process_ocr_results",
        lambda frames, workers: [{"Name": "Hina", "Level": "Lv.90"}],
    )
    processed = []
    monkeypatch.setattr(manual_scan, "run_post_processing", processed.append)

    watcher = manual_scan.Watcher(screen_of, lambda image: True)
    watcher.frames["Equipment"] = [frame("Equipment", 1)]
    watcher.frames["Student"] = [frame("Student", 1)]
    manual_scan.save(watcher)

    assert json.loads(config.scanned_equipment.read_text()) == {
        "Rusty Spring": 9, "Old Hat": 1, "New Gloves": 2,  # Old Hat not looked at: kept
    }
    assert not config.scanned_items.exists()  # Items not visited: untouched
    names = [c["name"] for c in json.loads(config.scanned_students.read_text())["characters"]]
    assert names == ["Aru", "Hina"]
    assert processed == [{"Equipment", "Student"}]


def test_desktop_device_in_read_only_mode_refuses_input():
    pytest.importorskip("win32gui")
    from src.utils.device.desktop.desktop_device import DesktopDevice

    device = DesktopDevice(read_only=True)  # No window needed: refused before any lookup
    with pytest.raises(RuntimeError, match="must not send input"):
        device.tap(100, 100)
    with pytest.raises(RuntimeError, match="must not send input"):
        device.swipe(0, 0, 100, 100)


def test_read_only_capture_never_focuses_the_game(monkeypatch):
    pytest.importorskip("win32gui")
    from src.utils.device.desktop import window_manager

    wm = object.__new__(window_manager.WindowManager)
    wm.window_name, wm.hwnd, wm.allow_focus = "Blue Archive", 0x10, False
    monkeypatch.setattr(wm, "activate", lambda: pytest.fail("focused the game"))
    monkeypatch.setattr(window_manager.win32gui, "GetForegroundWindow", lambda: 0x20)

    with pytest.raises(RuntimeError, match="not in front"):
        wm._capture_mss()
