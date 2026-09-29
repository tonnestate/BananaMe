from pathlib import Path

from bananame.core import BananaMe


def test_python_syntax_failure(tmp_path: Path) -> None:
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    result = tool.verify(paths=["broken.py"])
    assert result["ok"] is False
    assert result["status"] == "VERIFICATION_FAILED"
