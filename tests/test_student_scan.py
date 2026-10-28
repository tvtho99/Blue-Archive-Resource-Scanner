"""Student roster loop with the device, OCR, file writes and sleeps faked out."""

import logging

import numpy as np
import pytest

from locations import screens
from src.services.scanners import students
from src.utils.device.interfaces import DeviceUnavailableError

NEXT = screens.StudentInfo.BUTTONS.NEXT


class FakeRoster:
    """
    Student pages in a ring, starting on the first one. A screenshot carries
    its page index, the fakes below read the name from it.
    """

    def __init__(self, names, missed_taps=(), late=None):
        self.names = names
        self.page = 0  # What the game shows
        self.shown = 0  # What the last screenshot showed
        self.taps = 0
        self.captures = 0
        self.missed_taps = set(missed_taps)  # Tap numbers the game ignores
        self.late = dict(late or {})  # Tap number -> captures still on the old page
        self.stale = 0
        self.log = []

    def capture_screenshot(self):
        self.captures += 1
        self.log.append("capture")
        if self.stale:
            self.stale -= 1
        else:
            self.shown = self.page
        return np.full((1, 1), self.shown, np.uint8)

    def tap(self, x, y):
        assert (x, y) == (NEXT.x, NEXT.y)
        self.taps += 1
        self.log.append("tap")
        if self.taps not in self.missed_taps:
            self.page = (self.page + 1) % len(self.names)
            self.stale = self.late.get(self.taps, 0)


@pytest.fixture
def scan(monkeypatch, caplog):
    """
    scan(device) runs get_student_info and returns (result, saved names).
    scan.run holds what was written, the sleeps and the pages the OCR worker read.
    """
    run = {"written": [], "sleeps": [], "worker_reads": []}

    def run_scan(device, worker_names=None):
        def name_of(image, region, mode=None):
            return device.names[int(image[0, 0])]

        def worker(image):
            index = int(image[0, 0])
            run["worker_reads"].append(index)
            # The worker reads the name with the same call as the quick check
            return {"Name": (worker_names or device.names)[index]}

        monkeypatch.setattr(students, "extract_from_region", name_of)
        monkeypatch.setattr(students, "student_ocr_worker", worker)
        result = students.get_student_info(device)
        return result, [c["name"] for c in run["written"][0]["characters"]]

    monkeypatch.setattr(
        students, "write_json", lambda path, data: run["written"].append(data)
    )
    monkeypatch.setattr(students.time, "sleep", run["sleeps"].append)
    monkeypatch.setattr(students.Config, "WAIT_TIME_MULTIPLIER", 1.0)
    monkeypatch.setattr(students.Config, "DEBUG", False)
    monkeypatch.setattr(logging.getLogger("BA-Scanner"), "propagate", True)
    caplog.set_level(logging.INFO, logger="BA-Scanner")
    run_scan.run = run
    return run_scan


ROSTER = ["Aru", "Mutsuki", "Kayoko", "Haruka", "Hina"]


def dropped(caplog):
    """Names whose duplicate page was dropped, from the warnings."""
    prefix = "Dropped a second page read as "
    return [
        r.getMessage()[len(prefix) : -1]
        for r in caplog.records
        if r.levelno == logging.WARNING and r.getMessage().startswith(prefix)
    ]


def test_full_roster_in_capture_order(scan):
    device = FakeRoster(ROSTER)

    assert scan(device) == (True, ROSTER)
    assert device.taps == len(ROSTER)  # The last one wraps back to Aru
    assert set(scan.run["sleeps"]) == {0.5}


def test_missed_first_next_is_tapped_again(scan):
    device = FakeRoster(ROSTER, missed_taps={1})

    assert scan(device) == (True, ROSTER)  # Not just Aru
    assert device.taps == len(ROSTER) + 1
    # Tap, then the page is re-captured 5 times before NEXT is tapped again
    assert device.log[:8] == ["capture", "tap"] + ["capture"] * 5 + ["tap"]


@pytest.mark.parametrize("late_captures", [1, 4])
def test_late_page_is_recaptured_not_tapped_past(scan, late_captures):
    # The page after tap 2 shows up only after a few more captures
    device = FakeRoster(ROSTER, late={2: late_captures})

    assert scan(device) == (True, ROSTER)  # Nobody skipped
    assert device.taps == len(ROSTER)  # No second tap on a page that had moved


def test_next_stuck_raises_and_writes_nothing(scan):
    device = FakeRoster(ROSTER, missed_taps={2, 3})

    with pytest.raises(RuntimeError, match="NEXT never changed the page from Mutsuki"):
        scan(device)
    assert device.taps == 3
    assert scan.run["written"] == []
    assert scan.run["worker_reads"] == []


def unreadable(caplog):
    """How many pages were dropped for an unreadable name, from the warnings."""
    return sum(
        r.levelno == logging.WARNING and "name could not be read" in r.getMessage()
        for r in caplog.records
    )


def test_empty_first_read_is_dropped_with_a_warning(scan, caplog):
    # The first page can't be read, Aru marks the loop, so the first page is
    # captured again before the wrap. Both nameless pages are dropped and logged.
    device = FakeRoster(["", "Aru", "Mutsuki", "Kayoko"])

    assert scan(device) == (True, ["Aru", "Mutsuki", "Kayoko"])
    assert sorted(scan.run["worker_reads"]) == [0, 0, 1, 2, 3]
    assert unreadable(caplog) == 2


def test_unreadable_page_is_recaptured_not_tapped_past(scan, caplog):
    # A missed NEXT on a page whose name can't be read: it can't be compared,
    # so it is kept twice rather than risk a second tap skipping a student
    device = FakeRoster(["Aru", "", "Kayoko"], missed_taps={2})

    assert scan(device) == (True, ["Aru", "Kayoko"])
    assert sorted(scan.run["worker_reads"]) == [0, 1, 1, 2]
    assert device.taps == 4  # Never a second tap on the unreadable page
    assert unreadable(caplog) == 2


def test_two_students_read_alike_keep_the_first_and_log_it(scan, caplog):
    device = FakeRoster(["Aru", "Mutsuki", "Kayoko", "Mutsuki", "Hina"])

    assert scan(device) == (True, ["Aru", "Mutsuki", "Kayoko", "Hina"])
    assert dropped(caplog) == ["Mutsuki"]


def test_unreadable_names_in_a_row_raise_and_write_nothing(scan):
    # A popup covers the game: no name for MAX_UNREADABLE pages in a row
    device = FakeRoster(["Aru", "Mutsuki", "", "", "", "Hina"])

    with pytest.raises(RuntimeError, match="unreadable on 3 pages in a row"):
        scan(device)
    assert scan.run["written"] == []


def test_debug_mode_scans_the_whole_roster(scan, monkeypatch):
    monkeypatch.setattr(students.Config, "DEBUG", True)

    assert scan(FakeRoster(ROSTER)) == (True, ROSTER)


def test_wait_scales_with_the_multiplier(scan, monkeypatch):
    monkeypatch.setattr(students.Config, "WAIT_TIME_MULTIPLIER", 3.0)

    scan(FakeRoster(ROSTER, missed_taps={1}))
    assert set(scan.run["sleeps"]) == {1.5}


def test_roster_cap_ends_the_loop(scan, monkeypatch):
    monkeypatch.setattr(students, "MAX_STUDENTS", 3)

    assert scan(FakeRoster(ROSTER)) == (True, ROSTER[:3])


class FailingCapture(FakeRoster):
    """The screenshot of the third student fails: None, or `error` is raised."""

    def __init__(self, names, error=None):
        super().__init__(names)
        self.error = error

    def capture_screenshot(self):
        image = super().capture_screenshot()
        if self.captures == 3:
            if self.error:
                raise self.error
            return None
        return image


def test_failed_capture_mid_roster_writes_nothing(scan):
    with pytest.raises(RuntimeError, match="Failed to capture a student page"):
        scan(FailingCapture(ROSTER))
    assert scan.run["written"] == []


@pytest.mark.parametrize("error", [DeviceUnavailableError("gone"), KeyboardInterrupt()])
def test_stop_mid_roster_propagates_unchanged(scan, error):
    with pytest.raises(type(error)) as raised:
        scan(FailingCapture(ROSTER, error))
    assert raised.value is error
    assert scan.run["written"] == []
