from pathlib import Path
from typing import Any

import pytest
import requests

from src.utils.data.io import read_json, write_json
from src.utils.sync.data_sync_manager import DataSyncManager


class DummyResp:
    def __init__(self, data: Any, status_code: int = 200):
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


def equipment_records(count: int) -> list[dict]:
    return [
        {
            "id": 1000 + tier,
            "category": "Hat",
            "rarity": "N",
            "tier": tier,
            "icon": f"equipment_icon_hat_tier{tier}",
            "name": f"Hat T{tier}",
        }
        for tier in range(1, count + 1)
    ]


def test_update_from_online_writes_file(monkeypatch, tmp_path: Path):
    equipment_file = tmp_path / "equipment_processed.json"
    payload = equipment_records(3)
    monkeypatch.setattr("requests.get", lambda url, timeout=6: DummyResp(payload))

    make_manager(equipment_file, retries=1).update_from_online()

    assert read_json(equipment_file) == payload


def test_update_from_online_retries_failed_requests(monkeypatch, tmp_path: Path):
    equipment_file = tmp_path / "equipment_processed.json"
    payload = equipment_records(2)
    responses = iter([DummyResp({}, 503), DummyResp({}, 503), DummyResp(payload)])
    monkeypatch.setattr("requests.get", lambda url, timeout=6: next(responses))

    make_manager(equipment_file, retries=3).update_from_online()

    assert read_json(equipment_file) == payload


def test_update_from_online_allows_a_few_odd_records(monkeypatch, tmp_path: Path):
    equipment_file = tmp_path / "equipment_processed.json"
    write_json(equipment_file, equipment_records(10))
    payload = equipment_records(9) + [{"id": 9999}]  # 90% valid
    monkeypatch.setattr("requests.get", lambda url, timeout=6: DummyResp(payload))

    make_manager(equipment_file, retries=1).update_from_online()

    assert read_json(equipment_file) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"test": 1},
        [],
        # Upstream renamed a field the processor needs
        [
            {("Name" if k == "name" else k): v for k, v in record.items()}
            for record in equipment_records(10)
        ],
        # Under half of the 10 local records
        equipment_records(4),
    ],
    ids=["dict", "empty-list", "schema-drift", "big-shrink"],
)
def test_update_from_online_keeps_file_on_bad_download(
    monkeypatch, tmp_path: Path, payload
):
    equipment_file = tmp_path / "equipment_processed.json"
    local = equipment_records(10)
    write_json(equipment_file, local)
    monkeypatch.setattr("requests.get", lambda url, timeout=6: DummyResp(payload))

    make_manager(equipment_file, retries=1).update_from_online()

    assert read_json(equipment_file) == local
    assert not list(tmp_path.glob("*.tmp"))
