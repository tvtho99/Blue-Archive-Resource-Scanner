import json

from src.utils.data.item import ItemProcessor


def test_item_matching(tmp_config):
    # Setup test data
    items_data = [
        {"id": 120, "name": "Wolfsegg Iron Ore", "rarity": "N", "icon": "a"},
        {"id": 121, "name": "Wolfsegg Steel", "rarity": "R", "icon": "b"},
        {"id": 122, "name": "Low-Purity Wolfsegg Steel", "rarity": "SR", "icon": "c"},
        {"id": 123, "name": "High-Purity Wolfsegg Steel", "rarity": "SSR", "icon": "d"},
    ]
    owned_data = {"High Purity Wolfegg Steel": 2}

    # Write test files
    with open(tmp_config.ITEMS_PROCESSED_FILE, "w") as f:
        json.dump(items_data, f)

    with open(tmp_config.OWNED_COUNTS_FILE, "w") as f:
        json.dump(owned_data, f)

    # Run processor
    processor = ItemProcessor()
    processor.processed_file = tmp_config.ITEMS_PROCESSED_FILE
    processor.owned_file = tmp_config.OWNED_COUNTS_FILE
    processor.output_file = tmp_config.ITEMS_PROCESSED_FILE.parent / "items_output.json"
    processor.process()

    # Verify output
    with open(processor.output_file) as f:
        result = json.load(f)
    assert result["123"] == 2  # Should match via fuzzy
    # Not owned: must not borrow the count of the similarly named item
    assert result["122"] == 0
    assert result["121"] == 0
