from src.core.config import Config
from src.utils.data.base import BaseProcessor
from src.utils.data.shapes import Item


class ItemProcessor(BaseProcessor):
    def __init__(self):
        self.dataclass = Item
        self.processed_file = Config.items_processed
        self.owned_file = Config.scanned_items
        self.output_file = Config.final_items

    def map_data(self, items: list[Item], name_map: dict) -> dict:
        owned = self.match_owned([item.name for item in items], name_map)
        return {item.id: owned.get(item.name, 0) for item in items}
