from pathlib import Path

import requests

from src.utils.data.io import read_json
from src.utils.sync.data_sync_manager import DataSyncManager


class DummyResp:
    def __init__(self, data: dict, status_code: int = 200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.RequestException(f"status {self.status_code}")

    def json(self):
        return self.data


def make_manager(equipment_file: Path, retries: int) -> DataSyncManager:
    mgr = DataSyncManager()
    # Only equipment, pointed at tmp so the real assets are untouched
    mgr.local_paths = {"equipment": equipment_file}
    mgr.remote_sources = {"equipment": "https://example.com/equipment.json"}
    mgr.retries = retries
    mgr.retry_backoff = 0
    return mgr


def test_update_from_online_writes_file(monkeypatch, tmp_path: Path):
    equipment_file = tmp_path / "equipment_processed.json"
    monkeypatch.setattr("requests.get", lambda url, timeout=6: DummyResp({"test": 1}))

    make_manager(equipment_file, retries=1).update_from_online()

    assert read_json(equipment_file) == {"test": 1}


def test_update_from_online_retries_failed_requests(monkeypatch, tmp_path: Path):
    equipment_file = tmp_path / "equipment_processed.json"
    responses = iter([DummyResp({}, 503), DummyResp({}, 503), DummyResp({"test": 2})])
    monkeypatch.setattr("requests.get", lambda url, timeout=6: next(responses))

    make_manager(equipment_file, retries=3).update_from_online()

    assert read_json(equipment_file) == {"test": 2}
