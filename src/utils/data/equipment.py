from collections import defaultdict

from src.core.config import Config
from src.utils.data.base import BaseProcessor
from src.utils.data.shapes import Equipment


class EquipmentProcessor(BaseProcessor):
    def __init__(self):
        self.dataclass = Equipment
        self.processed_file = Config.equipment_processed
        self.owned_file = Config.scanned_equipment
        self.output_file = Config.final_equipment

    def map_data(self, equipment_list: list[Equipment], name_map: dict) -> dict:
        owned = self.match_owned([item.name for item in equipment_list], name_map)
        grouped = defaultdict(dict)
        for item in equipment_list:
            category = item.category
            key = item.id if category == "Exp" else item.tier
            value = owned.get(item.name, 0)

            if "WeaponExpGrowth" in category:
                icon_key = int(item.icon.split("_")[-1]) + 1
                grouped[category][icon_key] = value
            else:
                # A gear piece and its blueprint share (category, tier), the
                # blueprint is the planner material, whatever the file order
                if key in grouped[category] and not item.icon.endswith("_piece"):
                    continue
                grouped[category][key] = value
        return grouped
