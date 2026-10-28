"""DesktopDevice capture and tap checks with a stub window and a fake clock."""

import logging

import cv2
import numpy as np
import pytest

pytest.importorskip("win32gui")  # Desktop backend is Windows-only

from src.core.area import Region  # noqa: E402
from src.utils.device.desktop import desktop_device  # noqa: E402
from src.utils.device.desktop.desktop_device import DesktopDevice  # noqa: E402
from src.utils.device.desktop.window_manager import (  # noqa: E402
    FOCUS_WAIT_S,
    WindowManager,
    bars_are_black,
)
from src.utils.device.interfaces import DeviceUnavailableError  # noqa: E402


class FakeWindow:
    """Hands out client-area captures in order, then keeps repeating the last one."""

    def __init__(self, *frames):
        self.frames = list(frames)
        self.captures = 0

    def get_screenshot(self):
        self.captures += 1
        frame = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        if isinstance(frame, BaseException):
            raise frame
        return frame


class StubWindow(WindowManager):
    """Focused, uncovered client area at a fixed place, no real window behind it."""

    def __init__(self, client: Region):
        self.client = client

    def get_client_region(self) -> Region:
        return self.client

    def activate(self):
        pass

    def owns_point(self, x, y) -> bool:
        return True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(desktop_device, "time", fake)
    return fake


@pytest.fixture
def log(caplog, monkeypatch):
    # ScreenState turns propagation off and adds handlers, one of them writes logs/
    scanner_log = logging.getLogger("BA-Scanner")
    monkeypatch.setattr(scanner_log, "propagate", True)
    monkeypatch.setattr(scanner_log, "handlers", [])
    caplog.set_level(logging.INFO, logger="BA-Scanner")
    return caplog


def warnings_in(log):
    return [r.getMessage() for r in log.records if r.levelno == logging.WARNING]


def picture(width=2560, height=1440):
    """Game picture with detail everywhere, so a misplaced crop shows."""
    rng = np.random.default_rng(0)
    return rng.integers(40, 256, (height, width, 3), dtype=np.uint8)


def letterbox(content, client_w, client_h):
    """Client capture with the picture centred on black bars, as Unity draws it."""
    frame = np.zeros((client_h, client_w, 3), np.uint8)
    h, w = content.shape[:2]
    y, x = (client_h - h) // 2, (client_w - w) // 2
    frame[y : y + h, x : x + w] = content
    return frame


def scaled(content):
    return cv2.resize(content, (1280, 720), interpolation=cv2.INTER_AREA)


def device_for(*frames):
    device = DesktopDevice()
    device.wm = FakeWindow(*frames)
    return device


@pytest.mark.parametrize(
    ("client", "picture_size", "offset"),
    [
        ((2560, 1600), (2560, 1440), (0, 80)),
        ((3440, 1440), (2560, 1440), (440, 0)),
        ((1440, 1080), (1440, 810), (0, 135)),
    ],
)
def test_returns_the_game_picture_without_bars(clock, log, client, picture_size, offset):
    content = picture(*picture_size)
    device = device_for(letterbox(content, *client))

    out = device.capture_screenshot()

    assert np.array_equal(out, scaled(content))
    assert clock.now == 0
    assert not warnings_in(log)
    assert (
        f"Game area {picture_size[0]}x{picture_size[1]} at {offset} "
        f"in a {client[0]}x{client[1]} window" in log.text
    )


def test_16_9_window_is_scaled_whole(clock, log):
    content = picture(1920, 1080)
    assert np.array_equal(device_for(content).capture_screenshot(), scaled(content))


def test_unletterboxed_window_waits_then_stops(clock, log):
    stretched = np.full((1200, 1920, 3), 200, np.uint8)  # Screen Ratio is not 16:9
    device = device_for(stretched)

    with pytest.raises(DeviceUnavailableError, match="not letterboxed"):
        device.capture_screenshot()

    assert FOCUS_WAIT_S <= clock.now <= FOCUS_WAIT_S + 2
    assert device.wm.captures == pytest.approx(FOCUS_WAIT_S, abs=3)  # About every 1 s
    [warning] = warnings_in(log)
    assert "Set Screen Ratio to 16:9" in warning
    assert f"Waiting up to {FOCUS_WAIT_S} s" in warning


def test_too_small_window_waits_until_enlarged(clock, log):
    small = letterbox(picture(1024, 576), 1024, 640)
    content = picture(1920, 1080)
    device = device_for(small, small, content)

    out = device.capture_screenshot()

    assert np.array_equal(out, scaled(content))
    assert clock.now == 2 + desktop_device.SETTLE_S  # Passed twice, SETTLE_S apart
    [warning] = warnings_in(log)
    assert "1024x576, smaller than the 1280x720 minimum" in warning


def test_window_still_being_resized_keeps_waiting(clock, log):
    small = picture(1024, 576)
    mid_drag = picture(1600, 900)  # Passes once while the user still drags the border
    content = picture(1920, 1080)
    device = device_for(small, mid_drag, small, content)

    out = device.capture_screenshot()

    assert np.array_equal(out, scaled(content))
    assert device.wm.captures == 5  # The second pass of 1920x1080 is the one returned
    assert len(warnings_in(log)) == 1  # Same instruction, not repeated


def test_new_problem_while_waiting_is_shown_with_a_fresh_wait(clock, log):
    small = picture(1024, 576)
    stretched = np.full((1200, 1920, 3), 200, np.uint8)  # Bigger now, but 16:10
    device = device_for(small, *[small] * 30, stretched)

    with pytest.raises(DeviceUnavailableError, match="not letterboxed"):
        device.capture_screenshot()

    first, second = warnings_in(log)
    assert "smaller than the 1280x720 minimum" in first
    assert "Set Screen Ratio to 16:9" in second
    assert clock.now >= 31 + FOCUS_WAIT_S  # The deadline restarted with the new problem


def test_failed_capture_while_waiting_keeps_waiting(clock, log):
    content = picture(1920, 1080)
    device = device_for(picture(1024, 576), RuntimeError("mode switch"), content)

    assert np.array_equal(device.capture_screenshot(), scaled(content))


def test_too_small_window_stops_after_the_wait(clock, log):
    device = device_for(picture(1024, 576))

    with pytest.raises(DeviceUnavailableError, match="Make the game window bigger"):
        device.capture_screenshot()
    assert len(warnings_in(log)) == 1


def test_bars_are_checked_once_per_window_size(clock, log):
    first = letterbox(picture(), 2560, 1600)
    toast = first.copy()
    toast[1500:1600, 2160:2560] = 230  # A Steam toast over the bottom bar
    assert not bars_are_black(toast, Region(0, 80, 2560, 1440))
    device = device_for(first, toast)

    device.capture_screenshot()
    out = device.capture_screenshot()

    assert np.array_equal(out, scaled(toast[80:1520]))
    assert clock.now == 0
    assert not warnings_in(log)
    assert log.text.count("Game area 2560x1440 at (0, 80)") == 1


def test_new_window_size_is_checked_again(clock, log):
    stretched = np.full((1080, 2560, 3), 200, np.uint8)  # 21:9, Screen Ratio not 16:9
    fixed = letterbox(picture(1920, 1080), 2560, 1080)
    device = device_for(letterbox(picture(), 2560, 1600), stretched, fixed)

    device.capture_screenshot()
    out = device.capture_screenshot()  # Waits until Screen Ratio is set to 16:9

    assert np.array_equal(out, scaled(picture(1920, 1080)))
    assert clock.now == 1 + desktop_device.SETTLE_S
    [warning] = warnings_in(log)
    assert "Game window is 2560x1080 (not 16:9)" in warning


def test_failed_capture_returns_none(clock, log):
    assert device_for(RuntimeError("window moved")).capture_screenshot() is None


@pytest.mark.parametrize(
    "error", [DeviceUnavailableError("Window not found."), KeyboardInterrupt()]
)
def test_stop_errors_pass_through(clock, error):
    small = picture(1024, 576)
    device = device_for(small, error)  # Also while waiting for a bigger window

    with pytest.raises(type(error)):
        device.capture_screenshot()
    assert device.wm.captures == 2


def test_tap_lands_in_the_letterboxed_picture(clock, monkeypatch):
    clicks = []
    monkeypatch.setattr(
        desktop_device.pyautogui, "click", lambda x, y: clicks.append((x, y))
    )
    device = DesktopDevice()
    device.wm = StubWindow(Region(0, 0, 2560, 1600))

    device.tap(1238, 25)

    assert clicks == [(2476, 130)]
