import logging
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from src.utils.data.io import read_json, write_json
from src.utils.data.text_matcher import match_scanned

logger = logging.getLogger("BA-Scanner")


class BaseProcessor:
    dataclass: type[Any] | None = None
    processed_file: Path | None = None
    owned_file: Path | None = None
    output_file: Path | None = None

    def load_processed_data(self) -> list[dict]:
        data = read_json(self.processed_file)

        return data if isinstance(data, list) else []

    def load_owned_data(self) -> dict:
        return read_json(self.owned_file)

    def process_json(self, raw_data: list[dict]) -> list[Any]:
        if not self.dataclass:
            return []
        # Unknown keys (e.g. a field added upstream) would make the dataclass raise
        known = {field.name for field in fields(self.dataclass)}
        return [
            self.dataclass(**{k: v for k, v in item.items() if k in known})
            for item in raw_data
            if self.validate_item(item)
        ]

    def validate_item(self, item: dict) -> bool:
        if not self.dataclass or not isinstance(item, dict):
            return False

        # Fields with a default may be missing
        return all(
            field.name in item
            for field in fields(self.dataclass)
            if field.default is MISSING and field.default_factory is MISSING
        )

    def save_result(self, result: Any):
        write_json(self.output_file, result)

    def match_owned(self, names: list[str], owned_data: dict) -> dict[str, Any]:
        """Known name -> scanned value, for the names that were scanned."""
        if not isinstance(owned_data, dict):
            return {}
        return match_scanned(owned_data, names)

    def map_data(self, processed_items: list[Any], owned_data: dict) -> Any:
        raise NotImplementedError

    def process(self):
        processed_data = self.load_processed_data()
        items = self.process_json(processed_data)
        owned_data = self.load_owned_data()
        result = self.map_data(items, owned_data)
        self.save_result(result)
        logger.info(f"Data saved to [bold cyan]{self.output_file}[/bold cyan]")
