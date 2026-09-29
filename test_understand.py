from pathlib import Path

from bananame.core import BananaMe


def test_understand_returns_hash_and_python_symbol(tmp_path: Path) -> None:
    target = tmp_path / "auth.py"
    target.write_text("class Auth:\n    def login(self, user):\n        return user\n", encoding="utf-8")
    tool = BananaMe(str(tmp_path))
    result = tool.understand(query="login")
    assert result["ok"] is True
    assert result["hits"]
    hit = result["hits"][0]
    assert len(hit["sha256"]) == 64
    assert hit["symbol"]["name"] == "login"
