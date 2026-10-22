from src.utils.data.io import read_json, write_json
from tools.justin_planner import JustinPlannerProcessor


def test_merge_keeps_unscanned_characters(tmp_path):
    processor = JustinPlannerProcessor()
    processor.equipment_file = tmp_path / "equipment.json"
    processor.items_file = tmp_path / "items.json"
    processor.students_file = tmp_path / "students.json"
    processor.processed_students_file = tmp_path / "students_processed.json"
    processor.output_file = tmp_path / "out.json"

    base_file = tmp_path / "base.json"
    kept = {"id": "10001", "name": "Aru", "current": {}, "target": {"level": "90"}}
    write_json(base_file, {**processor.DEFAULT_TEMPLATE, "characters": [kept]})
    write_json(
        processor.students_file,
        {
            "characters": [
                {"id": "10002", "name": "Mutsuki", "current": {"level": 50}},
                {"id": "N/A", "name": "Misread", "current": {}},
            ]
        },
    )

    processor.process(base_file_path=base_file)

    chars = read_json(processor.output_file)["characters"]
    assert [c["id"] for c in chars] == ["10001", "10002"]
    assert chars[0]["target"] == {"level": "90"}  # User's data untouched
