import codecs
import json

import pytest

from src.utils.data.io import read_json, write_json
from tools.justin_planner import JustinPlannerProcessor


def make_processor(tmp_path) -> JustinPlannerProcessor:
    processor = JustinPlannerProcessor()
    processor.equipment_file = tmp_path / "equipment.json"
    processor.items_file = tmp_path / "items.json"
    processor.students_file = tmp_path / "students.json"
    processor.processed_students_file = tmp_path / "students_processed.json"
    processor.input_file = tmp_path / "input" / "justin_data.json"
    processor.output_file = tmp_path / "out.json"
    return processor


def printed(capsys) -> str:
    # Rich wraps long lines
    return " ".join(capsys.readouterr().out.split())


def test_merge_keeps_unscanned_characters(tmp_path):
    processor = make_processor(tmp_path)

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


def test_items_use_justin_planner_keys(tmp_path):
    processor = make_processor(tmp_path)
    write_json(
        processor.processed_students_file,
        [
            {"id": 10000, "name": "Aru"},
            {"id": 10001, "name": "Eimi"},
            {"id": 10002, "name": "Haruna"},
        ],
    )
    write_json(
        processor.items_file,
        {
            "10": 120, "11": 5, "12": 0, "13": 45,  # Activity Reports
            "23": 300,  # Eligma
            "7": 1500, "9": 20, "70": 800, "71": 10, "8": 300, "60": 40, "61": 25,  # Coins
            "150028": 2, "150048": 1,  # Equipment Blueprint Choice Boxes
            "10000": 55, "10001": 7, "10002": 3,  # Eleph, item id == student id
            "4043": 9,  # Ids Justin knows stay numeric
        },
    )
    write_json(processor.equipment_file, {"Hat": {"0": 4, "9": 3}, "Exp": {"4": 900}})
    write_json(
        processor.students_file,
        {"characters": [{"id": "10001", "name": "Eimi", "current": {"level": "70"}}]},
    )
    aru_eleph = {**processor.DEFAULT_ELEPH, "owned": "1", "use_eligma": True}
    aru = {"id": "10000", "name": "Aru", "current": {}, "eleph": aru_eleph}
    base_file = tmp_path / "base.json"
    write_json(
        base_file,
        {
            **processor.DEFAULT_TEMPLATE,
            "characters": [aru],
            # Numeric key from an older export, the XP_1 below replaces it
            # T0_Hat: how it wrote the General Hat Blueprint, now G_Hat
            "owned_materials": {"10": "999", "T9_Hat": "1", "T0_Hat": "2"},
        },
    )

    processor.process(base_file_path=base_file)

    out = read_json(processor.output_file)
    owned = out["owned_materials"]
    expected = {
        "XP_1": 120, "XP_2": 5, "XP_3": 0, "XP_4": 45,
        "Eligma": 300, "Choice_T2": 2, "Choice_T10": 1, "4043": 9,
        "G_Hat": 4, "T9_Hat": 3, "GXP_4": 900,
        "RaidToken": 1500, "RareRaidToken": 20, "EliminationRaidToken": 800,
        "RareEliminationRaidToken": 10, "ArenaCoin": 300, "JECoin": 40, "BountyCoin": 25,
    }
    assert {key: owned.get(key) for key in expected} == expected
    assert not {"10", "11", "12", "13", "23", "150028", "150048", "T0_Hat"} & owned.keys()
    assert not {"7", "8", "9", "60", "61", "70", "71"} & owned.keys()
    assert not {"10000", "10001", "10002"} & owned.keys()  # Eleph

    chars = {c["id"]: c for c in out["characters"]}
    assert list(chars) == ["10000", "10001"]  # No character invented for Haruna's Eleph
    assert chars["10000"]["eleph"] == {**aru_eleph, "owned": "55"}  # Settings kept
    assert chars["10001"]["eleph"] == {**processor.DEFAULT_ELEPH, "owned": "7"}


@pytest.mark.parametrize(
    "content",
    [None, b"{oops", b"\xff\xfe garbage", b"[]"],
    ids=["missing", "not-json", "not-utf8", "not-an-object"],
)
def test_unreadable_file_option_exits(tmp_path, content):
    processor = make_processor(tmp_path)
    base_file = tmp_path / "justin_data.json"
    if content is not None:
        base_file.write_bytes(content)

    with pytest.raises(SystemExit) as exc:
        processor.process(base_file_path=base_file)

    assert exc.value.code != 0
    assert not processor.output_file.exists()


def test_unreadable_default_file_exits(tmp_path):
    # Only a missing default file falls back to the template
    processor = make_processor(tmp_path)
    processor.input_file.parent.mkdir()
    processor.input_file.write_text("{oops", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        processor.process()

    assert exc.value.code != 0
    assert not processor.output_file.exists()


def test_missing_default_file_uses_template(tmp_path, capsys):
    processor = make_processor(tmp_path)
    write_json(
        processor.students_file,
        {"characters": [{"id": "10000", "name": "Aru", "current": {}}]},
    )

    processor.process()

    out = read_json(processor.output_file)
    assert out["exportVersion"] == 2
    assert [c["id"] for c in out["characters"]] == ["10000"]
    assert "using the default template" in printed(capsys)


def test_base_file_with_bom_merges(tmp_path, capsys):
    processor = make_processor(tmp_path)
    kept = {"id": "10001", "name": "Eimi", "current": {}, "target": {"level": "90"}}
    base = {**processor.DEFAULT_TEMPLATE, "characters": [kept]}
    base_file = tmp_path / "justin_data.json"
    base_file.write_bytes(codecs.BOM_UTF8 + json.dumps(base).encode("utf-8"))

    processor.process(base_file_path=base_file)

    assert read_json(processor.output_file)["characters"] == [kept]
    assert "kept 1 existing characters, added 0" in printed(capsys)
