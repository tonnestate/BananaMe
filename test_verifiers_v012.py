from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bananame.core import BananaMe
import bananame.verifiers as verifiers


def test_unavailable_requested_verifier_never_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers, "verification_capabilities", lambda: {"pytest": False, "hypothesis": False, "crosshair": False})
    tool = BananaMe(str(tmp_path))
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text("def test_prop():\n    assert True\n", encoding="utf-8")
    result = tool.verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "hypothesis", "target": "tests/test_x.py::test_prop", "origin": "PROJECT_EXISTING"}],
    )
    assert result["status"] == "PARTIAL"
    assert result["ok"] is False
    assert result["verifier_checks"][0]["outcome"] == "NOT_AVAILABLE"


def test_crosshair_counterexample_falsifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers.shutil, "which", lambda name: "/usr/bin/crosshair" if name == "crosshair" else None)
    monkeypatch.setattr(
        verifiers.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="a.py:1: error: counterexample\n", stderr=""),
    )
    tool = BananaMe(str(tmp_path))
    result = tool.verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "crosshair", "target": "a.py:f", "analysis_kind": "asserts", "origin": "SPEC_DERIVED"}],
    )
    assert result["status"] == "VERIFICATION_FAILED"
    evidence = result["verifier_checks"][0]
    assert evidence["outcome"] == "FALSIFIED"
    assert evidence["counterexample_found"] is True
    assert evidence["property_origin"] == "SPEC_DERIVED"


def test_crosshair_no_counterexample_can_complete_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers.shutil, "which", lambda name: "/usr/bin/crosshair" if name == "crosshair" else None)
    monkeypatch.setattr(
        verifiers.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="", stderr=""),
    )
    tool = BananaMe(str(tmp_path))
    result = tool.verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "crosshair", "target": "a.py:f", "origin": "PROJECT_EXISTING"}],
    )
    assert result["status"] == "VERIFIED"
    evidence = result["verifier_checks"][0]
    assert evidence["outcome"] == "PASSED"
    assert evidence["reason"] == "NO_COUNTEREXAMPLE_FOUND"


def test_crosshair_timeout_preserves_uncertainty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers.shutil, "which", lambda name: "/usr/bin/crosshair" if name == "crosshair" else None)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))

    monkeypatch.setattr(verifiers.subprocess, "run", _timeout)
    tool = BananaMe(str(tmp_path))
    result = tool.verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "crosshair", "target": "a.py:f", "origin": "PROJECT_EXISTING", "timeout_seconds": 1}],
    )
    assert result["status"] == "PARTIAL"
    assert result["verifier_checks"][0]["outcome"] == "TIMEOUT"


def test_hypothesis_provider_uses_pytest_without_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers, "verification_capabilities", lambda: {"pytest": True, "hypothesis": True, "crosshair": False})
    seen = {}

    def _run(argv, **kwargs):
        seen["argv"] = argv
        seen["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(argv, 0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(verifiers.subprocess, "run", _run)
    tool = BananaMe(str(tmp_path))
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_prop.py").write_text("def test_prop():\n    assert True\n", encoding="utf-8")
    result = tool.verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "hypothesis", "target": "tests/test_prop.py::test_prop", "origin": "PROJECT_EXISTING"}],
    )
    assert result["status"] == "VERIFIED"
    assert result["verifier_checks"][0]["outcome"] == "PASSED"
    assert seen["argv"][1:4] == ["-m", "pytest", "-q"]
    assert seen["shell"] is None


def test_agent_generated_origin_is_preserved_not_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(verifiers, "verification_capabilities", lambda: {"pytest": False, "hypothesis": False, "crosshair": False})
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    result = BananaMe(str(tmp_path)).verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "hypothesis", "target": "tests/test_x.py::test_x", "origin": "AGENT_GENERATED"}],
    )
    assert result["verifier_checks"][0]["property_origin"] == "AGENT_GENERATED"
    assert result["status"] == "PARTIAL"


def test_verifier_target_cannot_escape_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(verifiers, "verification_capabilities", lambda: {"pytest": True, "hypothesis": True, "crosshair": False})
    result = BananaMe(str(repo)).verify(
        paths=["a.py"],
        verifier_checks=[{"provider": "hypothesis", "target": "../outside.py::test_x", "origin": "PROJECT_EXISTING"}],
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_ESCAPE"
