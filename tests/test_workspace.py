from pathlib import Path

from bananame.core import BananaMe


def test_path_escape_is_denied(tmp_path: Path) -> None:
    inside = tmp_path / "repo"
    inside.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    tool = BananaMe(str(inside))
    result = tool.mutate(edits=[{
        "path": "../outside.txt",
        "search": "x",
        "replace": "y",
        "expected_sha256": "0" * 64,
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_ESCAPE"


def test_symlink_file_is_denied(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    tool = BananaMe(str(tmp_path))
    import hashlib
    result = tool.mutate(edits=[{
        "path": "link.txt",
        "search": "x",
        "replace": "y",
        "expected_sha256": hashlib.sha256(real.read_bytes()).hexdigest(),
    }])
    assert result["ok"] is False
    assert result["error"]["code"] == "SYMLINK_FILE_DENIED"
    assert real.read_text("utf-8") == "x"
