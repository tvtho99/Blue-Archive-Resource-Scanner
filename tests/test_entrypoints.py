"""main.py, launch.py and settings loading, with the device, scan and subprocess faked out."""

import logging
import signal
import subprocess
import sys

import pytest

import launch
import main
from src.core.config import AppSettings, Config, TargetPlatform

STOP_SIGNAL = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGINT


@pytest.fixture(autouse=True)
def quiet_logger(monkeypatch):
    """Only caplog sees the BA-Scanner logger, not handlers other tests left on it."""
    logger = logging.getLogger("BA-Scanner")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)


# main.py


def test_ctrl_c_still_post_processes_finished_screens(monkeypatch, caplog):
    processed = []

    class FakeState:
        def __init__(self, navigator):
            self.scanned = {"Equipment", "Items"}  # Finished before the Ctrl+C

        def run(self):
            raise KeyboardInterrupt

    for name in ("EquipmentProcessor", "ItemProcessor", "StudentProcessor"):
        processor = type(name, (), {"process": lambda self, n=name: processed.append(n)})
        monkeypatch.setattr(main, name, processor)
    monkeypatch.setattr(main, "ScreenNavigator", lambda device: None)
    monkeypatch.setattr(main, "ScreenState", FakeState)

    with pytest.raises(SystemExit) as stop:
        main.mainpage(device=None)

    assert stop.value.code == 130
    assert processed == ["EquipmentProcessor", "ItemProcessor"]
    assert "Scan stopped by user." in caplog.text


@pytest.fixture
def main_run(monkeypatch, tmp_path):
    """main.main() up to the scan: returns what mainpage saw, or the exit."""
    seen = {}
    handlers = []

    class FakeDevice:
        def connect(self, retries):
            return True

    def mainpage(device):
        seen["debug"] = Config.DEBUG

    monkeypatch.setattr(main.os, "chdir", lambda path: None)
    monkeypatch.setattr(main.signal, "signal", lambda *args: handlers.append(args))
    monkeypatch.setattr(main, "create_device", lambda settings: FakeDevice())
    monkeypatch.setattr(main, "mainpage", mainpage)
    monkeypatch.setattr(Config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(Config, "DEBUG", False)
    monkeypatch.setattr(Config, "settings_error", None)
    monkeypatch.setattr(Config, "settings", AppSettings())

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["main.py", "--offline", *args])
        main.main()
        return seen, handlers

    return run


def test_main_debug_flag_and_platform(main_run, monkeypatch, tmp_path, capsys):
    (tmp_path / "settings.json").write_text("{}")
    monkeypatch.setattr(
        Config, "settings", AppSettings(target_platform=TargetPlatform.DESKTOP)
    )

    seen, handlers = main_run("--debug")

    assert seen == {"debug": True}  # Set before mainpage builds ScreenState
    out = capsys.readouterr().out
    assert "Platform: PC client, window 'Blue Archive'" in out
    assert "not found" not in out
    if sys.platform == "win32":  # launch.py's stop request becomes a Ctrl+C
        assert (signal.SIGBREAK, signal.default_int_handler) in handlers


def test_main_warns_about_missing_settings(main_run, capsys):
    seen, _ = main_run()

    assert seen == {"debug": False}
    out = capsys.readouterr().out
    assert "not found" in out
    assert "Platform: emulator over ADB 127.0.0.1:16384" in out


def test_main_stops_on_broken_settings(main_run, monkeypatch, capsys):
    monkeypatch.setattr(Config, "settings_error", "config/settings.json: Invalid JSON")

    with pytest.raises(SystemExit) as stop:
        main_run()

    assert stop.value.code == 1
    out = capsys.readouterr().out
    assert "config/settings.json: Invalid JSON" in out
    assert "fix or delete the file" in out


# config.py


@pytest.mark.parametrize(
    "text",
    [
        '{"target_platform": "desktop",}',  # Trailing comma
        '{"target_platform": "Desktop"}',  # Not a TargetPlatform value
    ],
)
def test_broken_settings_file_is_reported(monkeypatch, tmp_path, text):
    path = tmp_path / "settings.json"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(Config, "settings_error", None)

    assert Config.load_settings() == AppSettings()  # Still importable
    assert Config.settings_error.startswith(f"{path}: ")


def test_good_or_missing_settings_file_has_no_error(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(Config, "settings_error", "stale")

    assert Config.load_settings() == AppSettings()
    assert Config.settings_error is None

    (tmp_path / "settings.json").write_text(
        '﻿{"target_platform": "desktop"}', encoding="utf-8"  # Notepad's BOM
    )
    assert Config.load_settings().target_platform is TargetPlatform.DESKTOP
    assert Config.settings_error is None


# launch.py


class FakeListener:
    """pynput stand-in: with press_f2 the stop key is pressed as it starts."""

    press_f2 = False

    def __init__(self, on_press):
        self.on_press = on_press

    def start(self):
        if self.press_f2:
            self.on_press(launch.keyboard.Key.f2)

    def stop(self):
        pass

    def join(self):
        pass


def fake_scan(events, *, on_stop="exit", ctrl_c=False):
    """Popen stand-in for main.py that runs until it is stopped."""

    class FakeProcess:
        def __init__(self, cmd, **kwargs):
            events.append(("start", cmd, kwargs))
            self.returncode = None
            self.ctrl_c = ctrl_c

        def poll(self):
            if self.ctrl_c:  # Ctrl+C in launch.py's console
                self.ctrl_c = False
                raise KeyboardInterrupt
            return self.returncode

        def send_signal(self, sig):
            events.append(("signal", sig))
            if on_stop == "no_console":
                raise OSError(6, "The handle is invalid")
            if on_stop == "exit":
                self.returncode = 130

        def wait(self, timeout=None):
            if self.returncode is None:
                events.append(("wait", timeout))
                raise KeyboardInterrupt  # The user gives up waiting: Ctrl+C again
            return self.returncode

        def terminate(self):
            events.append(("terminate",))
            self.returncode = 1

    return FakeProcess


@pytest.fixture
def launcher(monkeypatch):
    monkeypatch.setattr(launch, "write_screen_config", lambda screens: None)
    monkeypatch.setattr(launch.keyboard, "Listener", FakeListener)
    return {"screens": ["Items"], "enable_sync": False, "debug_mode": False}


@pytest.mark.parametrize("stop", ["f2", "ctrl_c"])
def test_launcher_stop_lets_main_post_process(launcher, monkeypatch, capsys, stop):
    events = []
    monkeypatch.setattr(launch.subprocess, "Popen", fake_scan(events, ctrl_c=stop == "ctrl_c"))
    monkeypatch.setattr(FakeListener, "press_f2", stop == "f2")

    launch.launch(launcher)

    assert events[1:] == [("signal", STOP_SIGNAL)]  # No terminate()
    if sys.platform == "win32":  # CTRL_BREAK_EVENT only reaches a process group
        assert events[0][2] == {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    assert "finished screens are still post-processed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("on_stop", "expected"),
    [
        ("ignore", [("signal", STOP_SIGNAL), ("wait", None), ("terminate",)]),
        ("no_console", [("signal", STOP_SIGNAL), ("terminate",)]),
    ],
)
def test_launcher_terminates_a_scan_it_cannot_stop(
    launcher, monkeypatch, on_stop, expected
):
    events = []
    monkeypatch.setattr(launch.subprocess, "Popen", fake_scan(events, on_stop=on_stop))
    monkeypatch.setattr(FakeListener, "press_f2", True)

    launch.launch(launcher)

    assert events[1:] == expected


def test_launcher_forwards_debug(launcher, monkeypatch):
    events = []
    monkeypatch.setattr(launch.subprocess, "Popen", fake_scan(events))
    monkeypatch.setattr(FakeListener, "press_f2", True)

    launch.launch({**launcher, "debug_mode": True})

    cmd = events[0][1]
    assert cmd[1:] == [str(launch.MAIN_ENTRY), "--offline", "--debug"]
