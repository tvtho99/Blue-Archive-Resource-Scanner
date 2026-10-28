import time
from pathlib import Path
from typing import Any

import requests
from rich.console import Console

from src.core.config import Config
from src.utils.data.equipment import EquipmentProcessor
from src.utils.data.io import read_json, write_json
from src.utils.data.item import ItemProcessor
from src.utils.data.student import StudentProcessor

console = Console()


class DataSyncManager:
    """
    Manages syncing local data files with online sources.
    Falls back to local files if online is unavailable.
    """

    def __init__(self):
        self.BASE_URL = (
            "https://raw.githubusercontent.com/FleetingComet/BA-Scanner-Data/main/data"
        )

        self.DEFAULT_ONLINE_URLS = {
            "equipment": f"{self.BASE_URL}/equipment.json",
            "items": f"{self.BASE_URL}/items.json",
            "students": f"{self.BASE_URL}/students.json",
        }

        self.local_paths: dict[str, Path] = {
            "equipment": Config.equipment_processed,
            "items": Config.items_processed,
            "students": Config.students_processed,
        }
        # The processor that reads each file, a download must have its shape
        self.processors = {
            "equipment": EquipmentProcessor,
            "items": ItemProcessor,
            "students": StudentProcessor,
        }
        self.retries: int = Config.settings.adb_retries
        self.retry_backoff: float = 1.0

    def _rejection(self, key: str, remote_data: Any, local_data: Any) -> str | None:
        """Why a downloaded file must not replace the local one, None if it may."""
        if not isinstance(remote_data, list) or not remote_data:
            return "not a non-empty list"
        # ponytail: checks that the required fields are there, not their types
        processor = self.processors[key]()
        valid = sum(1 for record in remote_data if processor.validate_item(record))
        if valid < 0.9 * len(remote_data):
            return f"only {valid} of {len(remote_data)} records have the expected fields"
        if isinstance(local_data, list) and len(remote_data) < 0.5 * len(local_data):
            return f"{len(remote_data)} records, the local file has {len(local_data)}"
        return None

    def update_from_online(self):
        """
        Try to update local processed data files from online sources if available and different.
        If online is not available, fallback to local file.
        """

        # Allow caller to provide their own mapping via attribute or use defaults
        remote_sources = getattr(self, "remote_sources", self.DEFAULT_ONLINE_URLS)

        for key, url in remote_sources.items():
            local_path = self.local_paths.get(key)
            if not local_path:
                print(f"[DataSync] Unknown data key '{key}', skipping.")
                continue

            local_path = Path(local_path)
            tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")

            # Try downloading with retries
            retries = max(1, getattr(self, "retries", 3))
            retry_backoff = getattr(self, "retry_backoff", 1.0)
            last_exc: Exception | None = None

            for attempt in range(1, retries + 1):
                try:
                    response = requests.get(url, timeout=6)
                    response.raise_for_status()
                    remote_data = response.json()

                    local_data = read_json(local_path)

                    # An upstream format change or a cut-off file would quietly
                    # turn every post-processed result empty or N/A
                    rejection = self._rejection(key, remote_data, local_data)
                    if rejection:
                        console.print(
                            f"[yellow][DataSync] Ignoring the downloaded {key} ({rejection}). "
                            f"Keeping local {local_path}[/yellow]"
                        )
                    # Compare and write atomically if different
                    elif local_data == remote_data:
                        console.print(
                            f"[bold blue][DataSync][/bold blue] Local {key} is up to date."
                        )
                    else:
                        write_json(tmp_path, remote_data)
                        tmp_path.replace(local_path)
                        console.print(f"[DataSync] Updated local {key} from {url}")

                    last_exc = None
                    break
                except requests.RequestException as exc:
                    last_exc = exc
                    if attempt < retries:
                        wait = retry_backoff * attempt
                        console.print(
                            f"[DataSync] Attempt {attempt} failed for {key} ({exc}), retrying in {wait}s"
                        )
                        time.sleep(wait)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    console.print(f"[DataSync] Unexpected error updating {key}: {exc}")
                    break

            if last_exc is not None:
                console.print(
                    f"[DataSync] Failed to update {key} ({last_exc}). Using local {local_path}"
                )
