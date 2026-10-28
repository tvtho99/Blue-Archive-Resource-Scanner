import codecs
from pathlib import Path

from src.utils.data.io import (
    read_json,
    read_user_text,
    update_count,
    update_student,
    write_json,
)


class TestIO:
    def test_read_write_roundtrip(self, tmp_path: Path):
        path = tmp_path / "test.json"
        data = {"a": 1, "b": [2, 3]}

        write_json(path, data)
        loaded = read_json(path)

        assert loaded == data

    def test_read_missing_file(self, tmp_path: Path):
        path = tmp_path / "missing.json"
        assert read_json(path) == {}

    def test_read_file_with_bom(self, tmp_path: Path):
        # PowerShell 7's Out-File and some editors save UTF-8 with a BOM
        path = tmp_path / "bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + b'{"name": "Hina"}')
        assert read_json(path) == {"name": "Hina"}

    def test_read_invalid_file(self, tmp_path: Path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        assert read_json(path) == {}

    def test_update_count(self, tmp_path: Path):
        path = tmp_path / "counts.json"
        update_count(path, "Item A", 10)
        update_count(path, "Item B", 5)

        data = read_json(path)
        assert data["Item A"] == 10
        assert data["Item B"] == 5

    def test_update_student(self, tmp_path: Path):
        path = tmp_path / "students.json"
        stats = {"level": "80", "star": 3}
        update_student(path, "Shiroko", stats)

        data = read_json(path)
        assert data["characters"]["Shiroko"]["current"] == stats

    def test_read_user_text_handles_bom_and_utf16(self, tmp_path: Path):
        # Windows PowerShell 5.1 "> file" writes UTF-16 with a BOM
        path = tmp_path / "pasted.txt"
        for raw in (
            b"Hina",
            codecs.BOM_UTF8 + b"Hina",
            "Hina".encode("utf-16"),
        ):
            path.write_bytes(raw)
            assert read_user_text(path) == "Hina"
