"""
Usage: python -m tools.schaledb
"""

import argparse
import base64
import json
from pathlib import Path
from typing import Any, NoReturn

from rich.console import Console

from src.core.config import Config
from src.utils.data.io import read_json, read_user_text, write_text
from src.utils.sync.data_sync_manager import DataSyncManager

console = Console()


def _fail(message: str) -> NoReturn:
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise SystemExit(1)


class SchaleDBExporter:
    """
    Transforms scanned student data into SchaleDB import format.
    """

    def __init__(self, output_filename: str = "SchaleDB_import.txt"):
        self.input_file = Config.final_students
        self.output_file = Config.OUTPUT_DIR / output_filename

        # SchaleDB requires both IDs to update both modes/styles (e.g. Hoshino (Armed) Tank and Dealer)
        self.DUAL_ID_MAP = {
            "10098": "10099",  # Hoshino (Armed) Tank
            "10099": "10098",  # Hoshino (Armed) Dealer
            "10143": "10144",  # Shun (Swimsuit)
            "10144": "10143",  # Shunling (Swimsuit) (T_T)
        }

    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Safely parses string/int values to integer."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def transform_character(
        self, current_stats: dict[str, Any], lock: bool = False
    ) -> dict[str, Any]:
        """Transforms character stats into the target site format."""
        return {
            "s": self._safe_int(current_stats.get("star"), 3),
            "l": self._safe_int(current_stats.get("level"), 1),
            "e1": self._safe_int(current_stats.get("gear1"), 1),
            "e2": self._safe_int(current_stats.get("gear2"), 1),
            "e3": self._safe_int(current_stats.get("gear3"), 1),
            "e4": self._safe_int(
                current_stats.get("gear_bond", current_stats.get("bond_gear")), 0
            ),
            "ws": self._safe_int(current_stats.get("ue"), 0),
            "wl": self._safe_int(current_stats.get("ue_level"), 0),
            "b": self._safe_int(current_stats.get("bond"), 1),
            "s1": self._safe_int(current_stats.get("ex"), 1),
            "s2": self._safe_int(current_stats.get("basic"), 1),
            "s3": self._safe_int(current_stats.get("passive"), 0),
            "s4": self._safe_int(current_stats.get("sub"), 0),
            "pm": self._safe_int(current_stats.get("talent_hp"), 0),
            "pa": self._safe_int(current_stats.get("talent_atk"), 0),
            "ph": self._safe_int(current_stats.get("talent_healing"), 0),
            "lock": lock,
        }

    def _load_collection(self, path: str | Path) -> dict[str, dict[str, Any]]:
        """Reads SchaleDB's "Export Collection" text: Base64 JSON keyed by student id."""
        path = Path(path)
        try:
            text = read_user_text(path)
            collection = json.loads(
                base64.b64decode("".join(text.split()), validate=True)
            )
        except (OSError, ValueError) as e:
            _fail(f"Could not read SchaleDB collection {path}: {e}")
        if not isinstance(collection, dict) or not all(
            isinstance(entry, dict) for entry in collection.values()
        ):
            _fail(f'{path} is not a SchaleDB "Export Collection" text.')
        return collection

    def process(
        self, lock: bool = False, base_file_path: str | Path | None = None
    ) -> Path:
        """
        Processes final_students.json and exports to the Base64 Schale import format.

        SchaleDB's Import Collection replaces the whole collection, so the export
        is merged into base_file_path (the user's own export) when given.
        """
        console.print("[bold yellow]Processing SchaleDB Export...[/bold yellow]")

        base = self._load_collection(base_file_path) if base_file_path else {}

        scanned_data = read_json(self.input_file)
        characters = scanned_data.get("characters", [])

        scanned: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []
        for char in characters:
            char_id = str(char.get("id", ""))
            if not char_id or char_id == "N/A":
                unmatched.append(str(char.get("name", "?")))
                continue
            scanned[char_id] = char.get("current", {})

        if unmatched:
            console.print(
                f"[yellow]Skipped {len(unmatched)} unmatched (N/A) students:[/yellow] "
                + ", ".join(unmatched)
            )
        if not scanned:
            _fail(
                f"No scanned students in {self.input_file}, nothing written. "
                "Importing an empty file would wipe your SchaleDB collection."
            )

        # SchaleDB needs both IDs of dual-mode/style characters, a scanned one wins
        for char_id, paired_id in self.DUAL_ID_MAP.items():
            if char_id in scanned and paired_id not in scanned:
                scanned[paired_id] = scanned[char_id]

        output_data = dict(base)
        for char_id, current_stats in scanned.items():
            # A student locked in SchaleDB stays locked
            locked = bool(base.get(char_id, {}).get("lock", False))
            output_data[char_id] = self.transform_character(current_stats, lock=locked)
        if lock:
            for stats in output_data.values():
                stats["lock"] = True

        # Serialize dict to JSON string -> encode bytes -> Base64 string
        json_str = json.dumps(output_data, ensure_ascii=False)
        encoded_output = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        write_text(self.output_file, encoded_output)
        kept = len(output_data) - len(scanned)
        console.print(
            f"[bold green]:heavy_check_mark: Successfully exported ({len(output_data)} characters) to SchaleDB import format:[/bold green] \n"
            f"[cyan]{self.output_file}[/cyan]"
        )
        if base_file_path:
            console.print(
                f"{len(scanned)} from the scan, {kept} kept from {base_file_path}."
            )
        else:
            console.print(
                "[yellow]Warning: SchaleDB's Import Collection replaces your whole collection, "
                "students missing from this file are removed. To keep them, copy your SchaleDB "
                '"Export Collection" text into a file and pass it with --file.[/yellow]'
            )

        console.print(
            "Go to [link=https://schaledb.com][cyan]https://schaledb.com[/cyan][/link], open Settings, and scroll down to "
            '"Import Collection". Paste the contents of the exported file, then click Import.'
        )
        return self.output_file


def main():
    parser = argparse.ArgumentParser(
        description="Convert scanner output into Schale DB import format."
    )
    parser.add_argument(
        "-l",
        "--lock",
        action="store_true",
        help="Set the 'lock' field to true for all characters (otherwise the lock flags from --file are kept).",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help='Path to a text file with your SchaleDB "Export Collection" data to merge into, keeping the students this scan missed.',
    )

    parser.add_argument(
        "-o",
        "--online",
        action="store_true",
        help="Download the latest community-maintained data before processing.",
    )
    args = parser.parse_args()

    if args.online:
        try:
            DataSyncManager().update_from_online()

        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]Online sync warning: {e}[/yellow]")

    processor = SchaleDBExporter()
    processor.process(lock=args.lock, base_file_path=args.file)


if __name__ == "__main__":
    main()
