"""
Usage: python -m tools.justin_planner
"""

import argparse
import json
from pathlib import Path
from typing import Any, NoReturn

from rich.console import Console

from src.core.config import Config
from src.utils.data.io import read_json, read_user_text, write_json
from src.utils.sync.data_sync_manager import DataSyncManager

console = Console()


def _fail(message: str) -> NoReturn:
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise SystemExit(1)


class JustinPlannerProcessor:
    """
    Transforms and merges scanned scanner outputs (Equipment, Items, Students)
    into a unified export file compatible with Justin's Blue Archive Planner.
    """

    def __init__(self):
        self.equipment_file = Config.final_equipment
        self.items_file = Config.final_items
        self.students_file = Config.final_students
        self.processed_students_file = Config.students_processed
        self.input_file = Config.justin_planner_data
        self.output_file = Config.justin_planner_merged_output

        # Map internal scanner IDs to one allowed IDs (e.g. Hoshino (Armed) Tank and Dealer)
        self.SITE_ID_MAP = {
            "10099": "10098",  # Hoshino (Armed): Dealer to Tank
            "10144": "10143",  # Shunling (Swimsuit) (T_T) to Shun (Swimsuit)
        }

        self.CATEGORY_NAME_MAP = {
            "WeaponExpGrowthA": "Spring",
            "WeaponExpGrowthB": "Hammer",
            "WeaponExpGrowthC": "Barrel",
            "WeaponExpGrowthZ": "Needle",
        }

        # Catalog item ids that Justin's planner reads under its own key (checked
        # against its JS): EXP reports, Eligma, shop coins, Blueprint Choice Boxes.
        # Other ids stay numeric, Eleph go to characters[].eleph.
        # ponytail: fixed ids, a new Choice Box tier stays numeric (ignored by the
        # planner) until it is added here
        self.ITEM_KEY_MAP = {
            "10": "XP_1",  # Novice Activity Report (50 EXP)
            "11": "XP_2",  # Normal Activity Report (500 EXP)
            "12": "XP_3",  # Advanced Activity Report (2000 EXP)
            "13": "XP_4",  # Superior Activity Report (10000 EXP)
            "23": "Eligma",
            "7": "RaidToken",  # Total Assault Coin
            "9": "RareRaidToken",  # Advanced Total Assault Coin
            "70": "EliminationRaidToken",  # Grand Assault Coin
            "71": "RareEliminationRaidToken",  # Advanced Grand Assault Coin
            "8": "ArenaCoin",  # Tactical Challenge Coin
            "60": "JECoin",  # Joint Firing Drill Coin
            "61": "BountyCoin",
            "150028": "Choice_T2",  # T2 Equipment Blueprint Choice Box
            "150029": "Choice_T3",
            "150030": "Choice_T4",
            "150031": "Choice_T5",
            "150032": "Choice_T6",
            "150033": "Choice_T7",
            "150041": "Choice_T8",
            "150045": "Choice_T9",
            "150048": "Choice_T10",
        }

        self.DEFAULT_TEMPLATE = {
            "exportVersion": 2,
            "characters": [],
            "character_order": [],
            "disabled_characters": [],
            "owned_materials": {},
            "groups": {
                "Binah": [],
                "Chesed": [],
                "Hod": [],
                "ShiroKuro": [],
                "Perorodzilla": [],
                "Goz": [],
                "Hieronymous": [],
                "Kaiten": [],
            },
            "language": "EN",
            "level_cap": 90,
            "server": "Global",
            "site_version": "1.4.22",
        }

        self.DEFAULT_ELEPH = {
            "owned": "0",
            "unlocked": True,
            "cost": "1",
            "purchasable": "20",
            "farm_nodes": "0",
            "node_refresh": False,
            "use_eligma": False,
            "use_shop": False,
        }

    def _transform_equipment(
        self, grouped_data: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Transforms equipment and growth material keys to Justin Planner format."""
        transformed = {}
        for category, items in grouped_data.items():
            if not isinstance(items, dict):
                continue
            transformed_category = self.CATEGORY_NAME_MAP.get(category, category)
            for key, value in items.items():
                if category == "Exp":
                    new_key = f"GXP_{key}"
                elif str(key) == "0":
                    # Tier 0 is the General blueprint, usable for any tier
                    new_key = f"G_{transformed_category}"
                else:
                    new_key = f"T{key}_{transformed_category}"
                transformed[new_key] = value
        return transformed

    def _transform_items(
        self, items: dict[str, Any], student_ids: set[str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Renames item ids to Justin Planner keys (XP_1, Eligma, Choice_T2...).
        Eleph (an Eleph's item id is its student's id) are returned apart,
        the planner keeps them per character.
        """
        materials, eleph = {}, {}
        for item_id, value in items.items():
            if item_id in student_ids:
                eleph[item_id] = value
            else:
                materials[self.ITEM_KEY_MAP.get(item_id, item_id)] = value
        return materials, eleph

    def _load_base(
        self, base_file_path: str | Path | None
    ) -> tuple[dict[str, Any], str]:
        """
        Planner data to merge into and its name for messages: --file, else
        input/justin_data.json, else the default template when that is missing.
        """
        path = Path(base_file_path) if base_file_path else self.input_file
        if not path.exists():
            if base_file_path:
                _fail(f"Justin Planner file not found: {path}")
            console.print(
                f"[yellow]No {path} found, using the default template.[/yellow]"
            )
            return dict(self.DEFAULT_TEMPLATE), "the default template"

        # Never fall back to the template for a file that is there: importing
        # the result would replace the user's whole planner
        try:
            data = json.loads(read_user_text(path))
        except (OSError, ValueError) as e:
            _fail(f"Could not read Justin Planner file {path}: {e}")
        if not isinstance(data, dict):
            _fail(f"{path} is not a Justin Planner export (no JSON object).")
        return data or dict(self.DEFAULT_TEMPLATE), str(path)

    def _format_stats(
        self, raw_stats: dict[str, Any], star_grade: int = 1
    ) -> dict[str, Any]:
        """
        Formats character stat values, locking skills based on base StarGrade:
        - 1-Star: Passive & Sub locked ('0')
        - 2-Star: Sub locked ('0')
        - 3-Star+: All skills unlocked ('1')
        """

        default_passive = "1" if star_grade >= 2 else "0"
        default_sub = "1" if star_grade >= 3 else "0"

        return {
            "level": str(raw_stats.get("level", "1")),
            "ue_level": str(raw_stats.get("ue_level", "0")),
            "bond": str(raw_stats.get("bond", "1")),
            "ex": str(raw_stats.get("ex", "1")),
            "basic": str(raw_stats.get("basic", "1")),
            "passive": str(raw_stats.get("passive", default_passive)),
            "sub": str(raw_stats.get("sub", default_sub)),
            "gear1": str(raw_stats.get("gear1", "0")),
            "gear2": str(raw_stats.get("gear2", "0")),
            "gear3": str(raw_stats.get("gear3", "0")),
            "bond_gear": str(
                raw_stats.get("gear_bond", raw_stats.get("bond_gear", "0"))
            ),
            "book_hp": str(raw_stats.get("book_hp", raw_stats.get("talent_hp", "0"))),
            "book_atk": str(
                raw_stats.get("book_atk", raw_stats.get("talent_atk", "0"))
            ),
            "book_heal": str(
                raw_stats.get("book_heal", raw_stats.get("talent_healing", "0"))
            ),
            "star": int(raw_stats.get("star", 1)),
            "ue": int(raw_stats.get("ue", 0)),
        }

    def _get_target_stats(
        self,
        current_stats: dict[str, Any],
        set_max_target: bool,
        has_bond_gear: bool = False,
    ) -> dict[str, Any]:
        """Generates target stats (MAX stats or matching current stats)."""
        target = self._format_stats(current_stats)
        if set_max_target:
            target.update(
                {
                    "level": "90",
                    "ue_level": "50",
                    "bond": "1",
                    "ex": "5",
                    "basic": "10",
                    "passive": "10",
                    "sub": "10",
                    "gear1": "10",
                    "gear2": "10",
                    "gear3": "10",
                    "bond_gear": "2" if has_bond_gear else "0",
                    "book_hp": "25",
                    "book_atk": "25",
                    "book_heal": "25",
                    "star": 5,
                    "ue": 3,
                }
            )
        return target

    def process(
        self,
        set_max_target: bool = False,
        base_file_path: str | Path | None = None,
    ) -> Path:
        """
        Converts and merges scanned outputs into a single Justin Planner output file.

        Args:
            set_max_target: If True, sets new characters' target stats to MAX (90, EX 5, 10/10/10, etc.).
            base_file_path: Path to an existing Justin Planner JSON to merge into.
        """
        console.print("[bold yellow]Processing Justin Planner Export...[/bold yellow]")

        equipment_raw = read_json(self.equipment_file)
        items_raw = read_json(self.items_file)
        students_raw = read_json(self.students_file)

        processed_students = read_json(self.processed_students_file)
        student_map = {
            str(s["id"]): s
            for s in (
                processed_students if isinstance(processed_students, list) else []
            )
            if isinstance(s, dict) and "id" in s
        }

        # Transform materials
        transformed_equipment = self._transform_equipment(equipment_raw)
        transformed_items, eleph_owned = self._transform_items(
            items_raw, set(student_map)
        )
        new_materials = {**transformed_equipment, **transformed_items}

        # Load base/existing Planner file or default template
        planner_data, base_name = self._load_base(base_file_path)

        # Merge Owned Materials. Scanned ids replace the base file's, also what an
        # older export wrote under keys Justin ignores: numeric ids of items that now
        # have a Justin key, and T0_{Category} for the General blueprints (now G_)
        owned_materials = {
            key: value
            for key, value in planner_data.get("owned_materials", {}).items()
            if key not in items_raw and not key.startswith("T0_")
        }
        planner_data["owned_materials"] = {**owned_materials, **new_materials}

        # Merge Character Stats
        existing_chars_map = {
            c["id"]: c
            for c in planner_data.get("characters", [])
            if isinstance(c, dict) and "id" in c
        }
        kept_count = len(existing_chars_map)

        scanned_characters = students_raw.get("characters", [])

        for char in scanned_characters:
            original_id = str(char.get("id", ""))
            name = char.get("name", "")
            if original_id in ("", "N/A"):
                console.print(f"[yellow]Skipping unmatched student:[/yellow] {name}")
                continue

            # Translate scanner ID to allowed ID
            char_id = self.SITE_ID_MAP.get(original_id, original_id)

            # Look up StarGrade and hasBondGear metadata from students_processed.json
            meta = student_map.get(char_id, {})
            star_grade = int(meta.get("StarGrade", 1))
            has_bond_gear = bool(meta.get("hasBondGear", False))

            current_stats = self._format_stats(
                char.get("current", {}), star_grade=star_grade
            )

            if char_id in existing_chars_map:
                # Update existing character stats while preserving user's custom targets/settings
                existing_char = existing_chars_map[char_id]
                existing_char["current"] = current_stats
                existing_char["hasBondGear"] = has_bond_gear
            else:
                # Add new character
                new_char = {
                    "id": char_id,
                    "name": name,
                    "current": current_stats,
                    "target": self._get_target_stats(
                        current_stats=current_stats,
                        set_max_target=set_max_target,
                        has_bond_gear=has_bond_gear,
                    ),
                    "eleph": dict(self.DEFAULT_ELEPH),
                    "enabled": True,
                    "hasBondGear": has_bond_gear,
                }
                existing_chars_map[char_id] = new_char

        # Justin's planner keeps owned Eleph per character, none is invented for it
        missing_eleph = []
        for char_id, owned in eleph_owned.items():
            if char_id in existing_chars_map:
                eleph = existing_chars_map[char_id].setdefault(
                    "eleph", dict(self.DEFAULT_ELEPH)
                )
                eleph["owned"] = str(owned)
            elif owned:
                missing_eleph.append(student_map[char_id].get("name", char_id))
        if missing_eleph:
            console.print(
                "[yellow]Eleph not exported, the student is not in the planner file:[/yellow] "
                + ", ".join(missing_eleph)
            )

        # Characters this scan missed keep their data, the planner file is a merge
        planner_data["characters"] = list(existing_chars_map.values())
        console.print(
            f"Merged into {base_name}: kept {kept_count} existing characters, "
            f"added {len(existing_chars_map) - kept_count}."
        )

        write_json(self.output_file, planner_data)
        console.print(
            f"[bold green]✔ Successfully exported Justin Planner data to:[/bold green] \n{self.output_file}"
        )
        return self.output_file


def main():
    parser = argparse.ArgumentParser(
        description="Convert and merge scanner output into Justin Planner format."
    )
    parser.add_argument(
        "-m",
        "--max-target",
        action="store_true",
        help="Set target stats to MAX for newly added characters.",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help="Path to an existing Justin Planner export file to merge with. Leave it empty for default path. Stops with an error if the file can't be read",
    )
    parser.add_argument(
        "-o",
        "--online",
        action="store_true",
        help="Download the latest community-maintained data before processing.",
    )
    args = parser.parse_args()

    # try update processed data
    if args.online:
        try:
            DataSyncManager().update_from_online()
        except Exception:  # noqa: BLE001, S110
            pass

    processor = JustinPlannerProcessor()
    processor.process(set_max_target=args.max_target, base_file_path=args.file)


if __name__ == "__main__":
    main()
