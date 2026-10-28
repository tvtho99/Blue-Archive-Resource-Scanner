"""Scan flow checks with the device, OCR and sleeps faked out."""

import json
import logging

import numpy as np
import pytest

from locations.search import SearchPattern
from src.constant import SCREEN_DEFAULTS
from src.core import state as state_mod
from src.core.config import Config
from src.core.navigator import NavigationResult
from src.services.scanners import currencies
from src.utils.device.interfaces import DeviceUnavailableError


@pytest.fixture(autouse=True)
def scratch_logs(monkeypatch, tmp_path):
    """ScreenState logs into Config.LOGS_DIR and re-wires the BA-Scanner logger."""
    monkeypatch.setattr(Config, "LOGS_DIR", tmp_path)
    logger = logging.getLogger("BA-Scanner")
    handlers, level, propagate = logger.handlers, logger.level, logger.propagate
    logger.handlers = []  # Not the handlers other tests left behind
    logger.propagate = True  # For caplog
    yield
    for handler in logger.handlers:
        handler.close()
    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate


class FakeNavigator:
    device = None

    def __init__(self):
        self.state = None
        self.home_calls = 0
        self.taps = []

    def identify_screen(self):
        # Always "already there" once a target is picked
        return self.state.target_screen if self.state else None

    def at_home(self):
        return False

    def ensure_at_home(self):
        self.home_calls += 1
        return NavigationResult(success=True)

    def ensure_menu_state(self, should_open):
        return NavigationResult(success=True)

    def navigate_to_target(self, location, in_menu_tab):
        self.taps.append(location)
        return NavigationResult(success=True)


def make_state(monkeypatch, tmp_path, nav, enabled):
    config_path = tmp_path / "screen_config.json"
    config_path.write_text(
        json.dumps(
            {
                name: {**cfg, "enabled": name in enabled}
                for name, cfg in SCREEN_DEFAULTS.items()
            }
        )
    )
    monkeypatch.setattr(state_mod.time, "sleep", lambda s: None)  # tenacity too

    screen_state = state_mod.ScreenState(nav, str(config_path))
    nav.state = screen_state
    return screen_state


def test_failed_screen_is_not_post_processed(monkeypatch, tmp_path, capsys):
    def item_grid(device, grid_type):
        if grid_type == "Equipment":
            raise RuntimeError("OCR blew up")
        return True

    monkeypatch.setattr(state_mod, "item_grid", item_grid)
    screen_state = make_state(
        monkeypatch, tmp_path, FakeNavigator(), ["Equipment", "Items"]
    )

    assert not screen_state.run()  # Not every screen was scanned
    assert screen_state.visited == {"Equipment", "Items"}
    assert screen_state.scanned == {"Items"}  # The crash did not stop Items
    assert "Not scanned: Equipment" in capsys.readouterr().out


def test_ctrl_c_during_navigation_is_not_retried(monkeypatch, tmp_path):
    class Nav(FakeNavigator):
        def identify_screen(self):
            return ""  # On the lobby, so Equipment needs the menu

        def navigate_to_target(self, location, in_menu_tab):
            super().navigate_to_target(location, in_menu_tab)
            raise KeyboardInterrupt

    nav = Nav()
    screen_state = make_state(monkeypatch, tmp_path, nav, ["Equipment"])

    with pytest.raises(KeyboardInterrupt):
        screen_state.run()
    assert nav.taps == ["menu_equipment"]  # One attempt, no "Retrying..."
    assert not screen_state.visited  # Not abandoned either


def test_no_lobby_and_no_page_stops_before_blind_taps(monkeypatch, tmp_path):
    class Nav(FakeNavigator):
        def identify_screen(self):
            return ""

        def ensure_at_home(self):
            super().ensure_at_home()
            return NavigationResult(success=False)

    nav = Nav()
    screen_state = make_state(
        monkeypatch, tmp_path, nav, ["Currencies", "Equipment", "Items", "Students"]
    )

    with pytest.raises(DeviceUnavailableError, match="lobby or a scanner page"):
        screen_state.run()
    assert nav.home_calls == 1
    assert nav.taps == []


def test_currencies_and_students_need_the_lobby(monkeypatch, tmp_path):
    class Nav(FakeNavigator):
        def identify_screen(self):
            return "Items"  # e.g. a popup over Items that HOME can't close

        def ensure_at_home(self):
            super().ensure_at_home()
            return NavigationResult(success=False)

    reads = []
    monkeypatch.setattr(state_mod, "get_currencies", lambda device: reads.append(1))
    nav = Nav()
    screen_state = make_state(monkeypatch, tmp_path, nav, ["Currencies", "Students"])

    with pytest.raises(DeviceUnavailableError, match="get back to the Blue Archive lobby"):
        screen_state.run()
    assert reads == []  # Not read from whatever was on screen
    assert nav.taps == []  # No blind STUDENTS tap
    assert nav.home_calls == 1  # Stopped instead of tapping HOME again per screen
    assert screen_state.scanned == set()


def _fake_reads(monkeypatch, ap, credit, pyroxene):
    texts = {  # Region is unhashable
        id(SearchPattern.AP.value): ap,
        id(SearchPattern.CREDIT.value): credit,
        id(SearchPattern.PYROXENE.value): pyroxene,
    }
    monkeypatch.setattr(
        currencies, "extract_from_region", lambda image, region, mode: texts[id(region)]
    )


class FakeLobby:
    def capture_screenshot(self):
        return np.zeros((720, 1280, 3), np.uint8)


@pytest.mark.parametrize(
    ("ap", "credit", "pyroxene", "bad"),
    [
        ("1231240", "1,234,567", "12,345", "AP"),  # Slash misread
        (None, "1,234,567", "12,345", "AP"),
        ("123/240", "", "12,345", "CREDIT"),
        ("123/240", "1,234,567", "12.3k", "PYROXENE"),
    ],
)
def test_bad_currency_read_writes_nothing(
    monkeypatch, tmp_path, caplog, ap, credit, pyroxene, bad
):
    out = tmp_path / "scanned_currencies.json"
    out.write_text('{"Credit": "999"}')
    monkeypatch.setattr(currencies.Config, "scanned_currencies", out)
    _fake_reads(monkeypatch, ap, credit, pyroxene)

    assert currencies.get_currencies(FakeLobby()) is False
    assert json.loads(out.read_text()) == {"Credit": "999"}  # Last good values kept
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert bad in errors[0]


def test_good_currency_read_writes_all_three(monkeypatch, tmp_path):
    out = tmp_path / "scanned_currencies.json"
    monkeypatch.setattr(currencies.Config, "scanned_currencies", out)
    _fake_reads(monkeypatch, "123 / 240", "1,234.567", "12345")  # "." misread for ","

    assert currencies.get_currencies(FakeLobby()) is True
    assert json.loads(out.read_text()) == {
        "Ap": {"Remaining": "123", "Max": "240"},
        "Credit": "1,234.567",
        "Pyroxene": "12345",
    }
