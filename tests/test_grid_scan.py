"""Equipment/Items grid scan on a fake scrollable grid, with OCR and sleeps faked out."""

import json
import logging

import numpy as np
import pytest

from src.core.area import Location, Region
from src.services.scanners import grids
from src.utils.device import swipe_utils
from src.utils.device.interfaces import DeviceUnavailableError

G = grids.EQUIPMENT_GRID
BG = (0xD4, 0xCF, 0xC4)  # c4cfd4 as BGR, the grid background process_grid keys on
CARD = (236, 240, 242)
OUTLINE = (177, 189, 195)  # An empty slot is an outline around the background
COLS, SLOT_W, SLOT_H, GAP, PAD = 5, 98, 110, 12, 8
PITCH = SLOT_H + GAP  # Drags scroll exactly 3 rows: slot frames line up, only icons change
PREVIOUS = {"Old item": 7}


def icon_colour(idx):
    return tuple(int(v) for v in np.random.default_rng(idx).integers(30, 220, 3))


class FakeGrid:
    """
    A 5-column inventory of n_items in the Equipment grid. Drags scroll drag_px
    (clamped at both ends), a tap selects the item under it, and every capture
    carries the selected item's index in pixel (0, 0) for the fake OCR.
    """

    def __init__(
        self, n_items, scroll=0, drags_work=True, bg=BG, none_when=lambda d: False
    ):
        self.n = n_items
        rows = -(-n_items // COLS)
        height = max(2 * PAD + rows * PITCH - GAP, G.height)
        self.content = np.full((height, G.width, 3), bg, np.uint8)
        for idx in range(rows * COLS):
            r, c = divmod(idx, COLS)
            x, y = PAD + c * (SLOT_W + GAP), PAD + r * PITCH
            slot = self.content[y : y + SLOT_H, x : x + SLOT_W]
            if idx < n_items:
                slot[:] = CARD
                slot[30:80, 24:74] = icon_colour(idx)
            else:
                slot[:] = OUTLINE
                slot[2:-2, 2:-2] = bg

        self.max_scroll = height - G.height
        self.scroll = min(scroll, self.max_scroll)
        self.drags_work = drags_work
        self.none_when = none_when
        self.selected = 0
        self.taps = self.drags_down = self.drags_up = 0

    def capture_screenshot(self):
        if self.none_when(self):
            return None
        frame = np.full((720, 1280, 3), 245, np.uint8)
        frame[G.y : G.bottom, G.x : G.right] = self.content[
            self.scroll : self.scroll + G.height
        ]
        frame[0, 0] = (self.selected % 256, self.selected // 256, 7)
        return frame

    def tap(self, x, y, duration_ms=100):
        assert G.contains_point(Location(x, y))
        self.taps += 1
        r, in_y = divmod(y - G.y + self.scroll - PAD, PITCH)
        c, in_x = divmod(x - G.x - PAD, SLOT_W + GAP)
        idx = r * COLS + c
        if in_y < SLOT_H and in_x < SLOT_W and c < COLS and 0 <= idx < self.n:
            self.selected = idx
        return True

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        assert G.contains_point(Location(x1, y1)) and G.contains_point(Location(x2, y2))
        up = y2 > y1  # Dragged downwards: the list scrolls back towards its top
        if up:
            self.drags_up += 1
        else:
            self.drags_down += 1
        if self.drags_work:
            step = -3 * PITCH if up else 3 * PITCH
            self.scroll = min(max(self.scroll + step, 0), self.max_scroll)
        return True


def read_selected(image, grid_type):
    idx = int(image[0, 0, 0]) + 256 * int(image[0, 0, 1])
    return {"name": f"Item {idx:03d}", "count": str(idx + 1)}


def every_item(n):
    return {f"Item {i:03d}": i + 1 for i in range(n)}


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, caplog):
    """Log into caplog only, never into handlers (a log file) another test attached."""
    logger = logging.getLogger("BA-Scanner")
    monkeypatch.setattr(logger, "handlers", [caplog.handler])
    monkeypatch.setattr(logger, "propagate", False)
    caplog.set_level(logging.INFO, logger="BA-Scanner")


@pytest.fixture
def owned(monkeypatch, tmp_path):
    """The Equipment owned file, holding a previous scan. OCR and sleeps are faked."""
    path = tmp_path / "scanned_equipment.json"
    path.write_text(json.dumps(PREVIOUS))
    monkeypatch.setattr(grids.Config, "scanned_equipment", path)
    monkeypatch.setattr(grids.Config, "scanned_items", tmp_path / "scanned_items.json")
    monkeypatch.setattr(grids, "item_ocr_worker", read_selected)
    monkeypatch.setattr(grids.time, "sleep", lambda s: None)  # swipe_utils too
    return path


def scan(device):
    return grids.item_grid(device, grid_type="Equipment", ocr_workers=1)


def saved(path):
    return json.loads(path.read_text())


def test_scans_every_item_over_several_pages(owned):
    device = FakeGrid(52)  # 11 rows, the last one ends in empty slots
    assert scan(device)
    assert saved(owned) == every_item(52)
    assert (device.drags_down, device.drags_up) == (3, 2)  # 2 still drags = at the top


def test_starts_mid_list_by_scrolling_to_the_top(owned):
    device = FakeGrid(60, scroll=6 * PITCH)
    assert scan(device)
    assert saved(owned) == every_item(60)
    # Up to the top (2 drags + 2 that no longer move), then 1 back up at the end
    assert device.drags_up == 4 + 1


def test_end_of_a_full_last_row_is_confirmed_by_a_drag_back_up(owned):
    device = FakeGrid(35)  # 7 full rows: no empty slot marks the end
    assert scan(device)
    assert saved(owned) == every_item(35)
    assert (device.drags_down, device.drags_up) == (1 + 3, 2 + 1)


def test_no_slot_boxes_keeps_the_previous_results(owned, caplog):
    off = tuple(c + 6 for c in BG)  # Background just outside the colour tolerance
    assert not scan(FakeGrid(52, bg=off))
    assert saved(owned) == PREVIOUS
    assert "No item slots found on the Equipment grid" in caplog.text
    assert "python -m tools.capture_layout" in caplog.text


def test_nothing_captured_keeps_the_previous_results(owned, monkeypatch, caplog):
    monkeypatch.setattr(grids, "is_empty_slot", lambda image, region: True)
    assert not scan(FakeGrid(52))
    assert saved(owned) == PREVIOUS
    assert "No item slots found on the Equipment grid" in caplog.text


def test_drags_the_game_ignores_raise_and_keep_the_previous_results(owned):
    device = FakeGrid(40, drags_work=False)
    with pytest.raises(RuntimeError, match="not reaching the game"):
        scan(device)
    assert saved(owned) == PREVIOUS
    assert (device.drags_down, device.drags_up) == (3, 2 + 1)


def test_failed_capture_while_scrolling_raises(owned):
    device = FakeGrid(52, none_when=lambda d: d.drags_down == 1)
    with pytest.raises(RuntimeError, match="Screenshot failed while scrolling"):
        scan(device)
    assert saved(owned) == PREVIOUS


def test_failed_detail_capture_raises_instead_of_dropping_the_item(owned):
    device = FakeGrid(52, none_when=lambda d: d.taps == 3)
    with pytest.raises(RuntimeError, match="item's details"):
        scan(device)
    assert saved(owned) == PREVIOUS


def test_device_unavailable_propagates_unchanged(owned):
    class GoneMidGrid(FakeGrid):
        def tap(self, x, y, duration_ms=100):
            raise DeviceUnavailableError("Mouse moved to a screen corner.")

    with pytest.raises(DeviceUnavailableError):
        scan(GoneMidGrid(52))
    assert saved(owned) == PREVIOUS


def test_grid_that_never_ends_fails_after_max_pages(owned, monkeypatch):
    monkeypatch.setattr(grids, "MAX_PAGES", 3)
    monkeypatch.setattr(
        grids, "swipe_with_verification", lambda device, grid_region: True
    )
    with pytest.raises(RuntimeError, match="after 3 pages"):
        scan(FakeGrid(40))
    assert saved(owned) == PREVIOUS


GRID = Region(0, 0, 10, 10)


class FakeSwipeDevice:
    """Tiny grid: down drags move it from the n-th one on, up drags if up_moves."""

    def __init__(self, scrolls_on, up_moves=True, captures_fail=False):
        self.scrolls_on = scrolls_on
        self.up_moves = up_moves
        self.captures_fail = captures_fail
        self.position = 0
        self.downs = self.ups = 0

    def capture_screenshot(self):
        if self.captures_fail:
            return None
        return np.full((10, 10, 3), 60 * self.position % 256, np.uint8)

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        if y2 > y1:
            self.ups += 1
            if self.up_moves:
                self.position -= 1
        else:
            self.downs += 1
            if self.downs >= self.scrolls_on:
                self.position += 1


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(swipe_utils.time, "sleep", lambda s: None)


def test_swipe_retries_an_ignored_drag(no_sleep):
    device = FakeSwipeDevice(scrolls_on=2)
    assert swipe_utils.swipe_with_verification(device, GRID, max_attempts=3)
    assert (device.downs, device.ups) == (2, 0)


def test_swipe_end_is_confirmed_by_a_drag_back_up(no_sleep):
    device = FakeSwipeDevice(scrolls_on=99)
    assert not swipe_utils.swipe_with_verification(device, GRID, max_attempts=3)
    assert (device.downs, device.ups) == (3, 1)


def test_swipe_raises_when_the_grid_moves_in_neither_direction(no_sleep):
    device = FakeSwipeDevice(scrolls_on=99, up_moves=False)
    with pytest.raises(RuntimeError, match="not reaching the game"):
        swipe_utils.swipe_with_verification(device, GRID, max_attempts=3)
    assert (device.downs, device.ups) == (3, 1)


def test_swipe_raises_on_a_failed_screenshot(no_sleep):
    with pytest.raises(RuntimeError, match="Screenshot failed"):
        swipe_utils.swipe_with_verification(FakeSwipeDevice(1, captures_fail=True), GRID)


def test_scroll_to_top_costs_two_drags_at_the_top(no_sleep):
    device = FakeSwipeDevice(scrolls_on=99, up_moves=False)
    swipe_utils.scroll_to_top(device, GRID)
    assert (device.downs, device.ups) == (0, 2)


def test_scroll_to_top_does_not_trust_one_ignored_drag(no_sleep):
    class FirstUpIgnored(FakeSwipeDevice):
        def swipe(self, *args, **kwargs):
            self.up_moves = self.ups >= 1 and self.position > -3  # 3 rows down
            super().swipe(*args, **kwargs)

    device = FirstUpIgnored(scrolls_on=99)
    swipe_utils.scroll_to_top(device, GRID)
    # Ignored, 3 that move, 2 still at the top
    assert (device.position, device.ups) == (-3, 1 + 3 + 2)


def test_failed_swipe_command_raises_at_once(no_sleep):
    class AdbFailure(FakeSwipeDevice):
        def swipe(self, *args, **kwargs):
            super().swipe(*args, **kwargs)
            return False  # ADBDevice.swipe when "input swipe" fails

    device = AdbFailure(scrolls_on=1)
    with pytest.raises(RuntimeError, match="Swipe command failed"):
        swipe_utils.swipe_with_verification(device, GRID)
    assert device.downs == 1


def test_scroll_to_top_gives_up_on_a_grid_that_keeps_moving(no_sleep):
    device = FakeSwipeDevice(scrolls_on=99)
    with pytest.raises(RuntimeError, match="could not reach its top"):
        swipe_utils.scroll_to_top(device, GRID, max_drags=5)
    assert device.ups == 5


def grid_crop(scroll):
    frame = FakeGrid(80, scroll=scroll).capture_screenshot()
    return frame[G.y : G.bottom, G.x : G.right]


@pytest.mark.parametrize("rows", [1, 2, 3])
def test_whole_row_pitch_scroll_counts_as_moved(rows):
    before, after = grid_crop(0), grid_crop(rows * PITCH)
    # Slot frames line up again and only the icons differ: the mean diff alone misses it
    assert np.mean(np.abs(before.astype(float) - after.astype(float))) / 255 < 0.05
    assert swipe_utils._screens_are_different(before, after)


def test_capture_noise_is_not_movement():
    rng = np.random.default_rng(0)
    crop = grid_crop(0)

    def noisy():
        return np.clip(crop + rng.normal(0, 3, crop.shape), 0, 255).astype(np.uint8)

    assert not swipe_utils._screens_are_different(noisy(), noisy())
