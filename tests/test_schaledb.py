import base64
import json

import pytest

from src.utils.data.io import write_json
from tools.schaledb import SchaleDBExporter


def encode(collection) -> str:
    """SchaleDB's Export Collection format."""
    return base64.b64encode(json.dumps(collection).encode()).decode()


def decode(path) -> dict:
    return json.loads(base64.b64decode(path.read_text(encoding="utf-8")))


def make_exporter(tmp_path, characters: list[dict]) -> SchaleDBExporter:
    exporter = SchaleDBExporter()
    exporter.input_file = tmp_path / "students_final.json"
    exporter.output_file = tmp_path / "SchaleDB_import.txt"
    write_json(exporter.input_file, {"characters": characters})
    return exporter


def write_base(tmp_path, text: str):
    base_file = tmp_path / "schale_export.txt"
    base_file.write_text(text, encoding="utf-8")
    return base_file


def printed(capsys) -> str:
    # Rich wraps long lines
    return " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize(
    "characters",
    [[], [{"id": "N/A", "name": "Misread", "current": {}}]],
    ids=["no-students", "only-unmatched"],
)
def test_refuses_to_write_without_characters(tmp_path, characters):
    exporter = make_exporter(tmp_path, characters)

    with pytest.raises(SystemExit) as exc:
        exporter.process()

    assert exc.value.code != 0
    assert not exporter.output_file.exists()


def test_without_base_file_warns_that_import_replaces_collection(tmp_path, capsys):
    exporter = make_exporter(tmp_path, [{"id": "10000", "name": "Aru", "current": {}}])

    exporter.process()

    assert list(decode(exporter.output_file)) == ["10000"]
    assert "replaces your whole collection" in printed(capsys)


def test_merge_keeps_unscanned_students_and_their_lock(tmp_path, capsys):
    exporter = make_exporter(
        tmp_path,
        [
            {"id": "10000", "name": "Aru", "current": {"level": "90", "star": 5}},
            {"id": "N/A", "name": "Misread", "current": {}},
        ],
    )
    eimi = exporter.transform_character({"level": "70"}, lock=True)
    haruna = exporter.transform_character({"level": "60"})
    base = {
        "10000": exporter.transform_character({"level": "80"}, lock=True),
        "10001": eimi,
        "10002": haruna,
    }

    exporter.process(base_file_path=write_base(tmp_path, encode(base)))

    out = decode(exporter.output_file)
    # Scanned stats replace the old ones, the user's lock stays
    assert out["10000"] == exporter.transform_character(
        {"level": "90", "star": 5}, lock=True
    )
    assert (out["10001"], out["10002"]) == (eimi, haruna)
    assert "Misread" in printed(capsys)


def test_lock_option_locks_every_student(tmp_path):
    exporter = make_exporter(tmp_path, [{"id": "10000", "name": "Aru", "current": {}}])
    base = {"10001": exporter.transform_character({})}

    exporter.process(lock=True, base_file_path=write_base(tmp_path, encode(base)))

    out = decode(exporter.output_file)
    assert {key: stats["lock"] for key, stats in out.items()} == {
        "10000": True,
        "10001": True,
    }


def test_merge_updates_both_ids_of_dual_students(tmp_path):
    exporter = make_exporter(
        tmp_path,
        [{"id": "10098", "name": "Hoshino (Armed)", "current": {"level": "90"}}],
    )
    stale = exporter.transform_character({"level": "1"})
    base = {"10098": stale, "10099": stale}

    exporter.process(base_file_path=write_base(tmp_path, encode(base)))

    out = decode(exporter.output_file)
    assert out["10098"]["l"] == out["10099"]["l"] == 90


@pytest.mark.parametrize(
    "text",
    [None, "not base64 !!", encode([1, 2]), base64.b64encode(b"{oops").decode()],
    ids=["missing", "not-base64", "not-a-collection", "not-json"],
)
def test_unreadable_collection_file_exits(tmp_path, text):
    exporter = make_exporter(tmp_path, [{"id": "10000", "name": "Aru", "current": {}}])
    base_file = tmp_path / "schale_export.txt"
    if text is not None:
        base_file.write_text(text, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        exporter.process(base_file_path=base_file)

    assert exc.value.code != 0
    assert not exporter.output_file.exists()


def test_collection_saved_by_windows_powershell_is_read(tmp_path):
    # Windows PowerShell 5.1 "Get-Clipboard > file" writes UTF-16 with a BOM
    exporter = make_exporter(tmp_path, [{"id": "10000", "name": "Aru", "current": {}}])
    haruna = exporter.transform_character({"level": "60"})
    base_file = tmp_path / "schale_export.txt"
    base_file.write_bytes(encode({"10002": haruna}).encode("utf-16"))

    exporter.process(base_file_path=base_file)

    assert decode(exporter.output_file)["10002"] == haruna
