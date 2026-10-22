"""Scan flow checks with the device, OCR and sleeps faked out."""

import json

import numpy as np

from src.core import state as state_mod
from src.core.area import Region
from src.core.navigator import NavigationResult
from src.services.scanners import students
from src.utils.device import swipe_utils

GRID = Region(0, 0, 10, 10)


class FakeSwipeDevice:
    """Grid that only scrolls on the n-th swipe."""

    def __init__(self, scrolls_on: int):
        self.scrolls_on = scrolls_on
        self.swipes = 0

    def capture_screenshot(self):
        moved = self.swipes >= self.scrolls_on
        return np.full((10, 10, 3), 255 if moved else 0, np.uint8)

    def swipe(self, *args, **kwargs):
        self.swipes += 1


def test_swipe_retries_an_ignored_swipe(monkeypatch):
    monkeypatch.setattr(swipe_utils.time, "sleep", lambda s: None)

    device = FakeSwipeDevice(scrolls_on=2)
    assert swipe_utils.swipe_with_verification(device, GRID, max_attempts=3)
    assert device.swipes == 2


def test_swipe_gives_up_at_the_end_of_the_grid(monkeypatch):
    monkeypatch.setattr(swipe_utils.time, "sleep", lambda s: None)

    device = FakeSwipeDevice(scrolls_on=99)
    assert not swipe_utils.swipe_with_verification(device, GRID, max_attempts=3)
    assert device.swipes == 3


def test_student_scan_survives_empty_first_read_and_duplicates(monkeypatch):
    # Each screenshot carries its index, the fakes read the name from it
    # Unreadable first name, a missed NEXT tap, then the loop back to the start
    pages = ["", "Aru", "Mutsuki", "Mutsuki", "Kayoko", "", "Aru"]
    seen = []

    class Device:
        page = 0

        def capture_screenshot(self):
            return np.full((1, 1), self.page, np.uint8)

        def tap(self, x, y):
            self.page += 1

    def name_of(image, *args, **kwargs):
        return pages[int(image[0, 0])]

    def worker(image):
        name = pages[int(image[0, 0])] or "Haruka"  # the worker reads the empty one
        return {"Name": name}

    monkeypatch.setattr(students, "extract_from_region", name_of)
    monkeypatch.setattr(students, "student_ocr_worker", worker)
    monkeypatch.setattr(students, "write_json", lambda path, data: seen.append(data))
    monkeypatch.setattr(students.time, "sleep", lambda s: None)
    monkeypatch.setattr(students.Config, "DEBUG", False)

    assert students.get_student_info(Device())
    names = [c["name"] for c in seen[0]["characters"]]
    assert names == ["Haruka", "Aru", "Mutsuki", "Kayoko"]


class FakeNavigator:
    device = None

    def __init__(self):
        self.state = None

    def identify_screen(self):
        # Always "already there" once a target is picked
        return self.state.target_screen if self.state else None

    def at_home(self):
        return False

    def ensure_at_home(self):
        return NavigationResult(success=True)

    def ensure_menu_state(self, should_open):
        return NavigationResult(success=True)


def test_failed_screen_is_not_post_processed(monkeypatch, tmp_path):
    config_path = tmp_path / "screen_config.json"
    config_path.write_text(
        json.dumps(
            {
                "Equipment": {"grid_type": "Equipment", "enabled": True},
                "Items": {"grid_type": "Items", "enabled": True},
            }
        )
    )

    def item_grid(device, grid_type):
        if grid_type == "Equipment":
            raise RuntimeError("OCR blew up")
        return True

    monkeypatch.setattr(state_mod, "item_grid", item_grid)
    monkeypatch.setattr(state_mod.time, "sleep", lambda s: None)

    nav = FakeNavigator()
    screen_state = state_mod.ScreenState(nav, str(config_path))
    nav.state = screen_state

    assert screen_state.run()
    assert screen_state.visited == {"Equipment", "Items"}
    assert screen_state.scanned == {"Items"}  # The crash did not stop Items
