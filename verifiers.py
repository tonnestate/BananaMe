from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from .errors import BananaMeError
from .workspace import Workspace

_ALLOWED_ORIGINS = {
    "PROJECT_EXISTING",
    "OWNER_SUPPLIED",
    "SPEC_DERIVED",
    "AGENT_GENERATED",
    "UNKNOWN",
}
_ALLOWED_CROSSHAIR_KINDS = {"asserts", "PEP316", "icontract", "deal"}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def verification_capabilities() -> dict[str, bool]:
    return {
        "pytest": _module_available("pytest"),
        "hypothesis": _module_available("hypothesis"),
        "crosshair": shutil.which("crosshair") is not None,
    }


def _origin(raw: Any) -> str:
    value = str(raw or "UNKNOWN").upper()
    if value not in _ALLOWED_ORIGINS:
        raise BananaMeError(
            "INVALID_VERIFIER_ORIGIN",
            f"Unsupported verifier origin: {value}",
            details={"allowed": sorted(_ALLOWED_ORIGINS)},
        )
    return value


def _bounded_output(value: str | None, limit: int = 12000) -> str:
    return (value or "")[-limit:]


def _run(
    argv: list[str],
    *,
    ws: Workspace,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str] | None, dict[str, Any] | None, int]:
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    start = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=ws.root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
        elapsed_ms = max(0, int((time.monotonic() - start) * 1000))
        return result, None, elapsed_ms
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = max(0, int((time.monotonic() - start) * 1000))
        return None, {
            "outcome": "TIMEOUT",
            "reason": "TIME_BUDGET_EXHAUSTED",
            "timeout_seconds": timeout_seconds,
            "stdout": _bounded_output(exc.stdout if isinstance(exc.stdout, str) else "", 4000),
            "stderr": _bounded_output(exc.stderr if isinstance(exc.stderr, str) else "", 4000),
        }, elapsed_ms


def _validate_target(target: Any) -> str:
    value = str(target or "").strip()
    if not value:
        raise BananaMeError("VERIFIER_TARGET_REQUIRED", "Optional verifier checks require a non-empty target.")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise BananaMeError("INVALID_VERIFIER_TARGET", "Verifier targets must be single-line strings without NUL bytes.")
    return value


def _workspace_pytest_target(ws: Workspace, target: str) -> str:
    path_part = target.split("::", 1)[0]
    path = ws.resolve(path_part)
    if not path.is_file():
        raise BananaMeError("VERIFIER_TARGET_NOT_FOUND", f"Hypothesis/pytest target file not found: {path_part}")
    return target


def _workspace_crosshair_target(ws: Workspace, target: str) -> str:
    # v0.1.2 deliberately accepts only workspace-relative Python file targets.
    # This prevents an agent from using CrossHair to execute/analyse arbitrary
    # installed modules outside the host-bound repository.
    path_part, sep, suffix = target.partition(":")
    if not path_part.endswith(".py"):
        raise BananaMeError(
            "CROSSHAIR_WORKSPACE_TARGET_REQUIRED",
            "CrossHair targets must use a workspace-relative .py path, optionally followed by :qualname.",
        )
    path = ws.resolve(path_part)
    if not path.is_file():
        raise BananaMeError("VERIFIER_TARGET_NOT_FOUND", f"CrossHair target file not found: {path_part}")
    return path_part + (sep + suffix if sep else "")


def _run_hypothesis(ws: Workspace, check: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    origin = _origin(check.get("origin"))
    target = _workspace_pytest_target(ws, _validate_target(check.get("target")))
    base = {
        "provider": "hypothesis",
        "target": target,
        "property_origin": origin,
    }
    capabilities = verification_capabilities()
    if not capabilities["hypothesis"] or not capabilities["pytest"]:
        missing = [name for name in ("hypothesis", "pytest") if not capabilities[name]]
        return base | {
            "outcome": "NOT_AVAILABLE",
            "reason": "MISSING_OPTIONAL_CAPABILITY",
            "missing": missing,
            "executed": False,
        }

    argv = [sys.executable, "-m", "pytest", "-q", target]
    result, timeout, elapsed_ms = _run(argv, ws=ws, timeout_seconds=timeout_seconds)
    if timeout is not None:
        return base | timeout | {"executed": True, "duration_ms": elapsed_ms, "argv": argv}
    assert result is not None
    if result.returncode == 0:
        outcome = "PASSED"
        reason = "PROPERTY_TESTS_PASSED"
    elif result.returncode == 1:
        combined = f"{result.stdout}\n{result.stderr}"
        if "Falsifying example:" in combined or "AssertionError" in combined:
            outcome = "FALSIFIED"
            reason = "PROPERTY_COUNTEREXAMPLE_OR_ASSERTION_FAILURE"
        else:
            outcome = "ERROR"
            reason = "PROPERTY_TEST_FAILED_WITHOUT_COUNTEREXAMPLE_EVIDENCE"
    elif result.returncode == 5:
        outcome = "INCONCLUSIVE"
        reason = "NO_TESTS_COLLECTED"
    else:
        outcome = "ERROR"
        reason = "PYTEST_ERROR"
    combined = f"{result.stdout}\n{result.stderr}"
    return base | {
        "outcome": outcome,
        "reason": reason,
        "executed": True,
        "exit_code": result.returncode,
        "counterexample_found": bool(outcome == "FALSIFIED" and "Falsifying example" in combined),
        "duration_ms": elapsed_ms,
        "stdout": _bounded_output(result.stdout),
        "stderr": _bounded_output(result.stderr),
        "argv": argv,
    }


def _crosshair_kinds(raw: Any) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    canonical = {kind.lower(): kind for kind in _ALLOWED_CROSSHAIR_KINDS}
    raw_kinds = [part.strip() for part in str(raw).split(",") if part.strip()]
    invalid = [kind for kind in raw_kinds if kind.lower() not in canonical]
    if invalid:
        raise BananaMeError(
            "INVALID_CROSSHAIR_ANALYSIS_KIND",
            f"Unsupported CrossHair analysis kind(s): {', '.join(invalid)}",
            details={"allowed": sorted(_ALLOWED_CROSSHAIR_KINDS)},
        )
    return ",".join(canonical[kind.lower()] for kind in raw_kinds)


def _run_crosshair(ws: Workspace, check: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    origin = _origin(check.get("origin"))
    target = _workspace_crosshair_target(ws, _validate_target(check.get("target")))
    analysis_kind = _crosshair_kinds(check.get("analysis_kind"))
    executable = shutil.which("crosshair")
    base = {
        "provider": "crosshair",
        "target": target,
        "property_origin": origin,
        "analysis_kind": analysis_kind or "default",
    }
    if executable is None:
        return base | {
            "outcome": "NOT_AVAILABLE",
            "reason": "MISSING_OPTIONAL_CAPABILITY",
            "executed": False,
        }

    per_condition_timeout = max(1.0, min(float(timeout_seconds), 120.0))
    argv = [executable, "check", "--per_condition_timeout", str(per_condition_timeout)]
    if analysis_kind:
        argv.extend(["--analysis_kind", analysis_kind])
    argv.append(target)
    result, timeout, elapsed_ms = _run(argv, ws=ws, timeout_seconds=timeout_seconds)
    if timeout is not None:
        return base | timeout | {"executed": True, "duration_ms": elapsed_ms, "argv": argv}
    assert result is not None
    if result.returncode == 0:
        outcome = "PASSED"
        reason = "NO_COUNTEREXAMPLE_FOUND"
        counterexample_found = False
    elif result.returncode == 1:
        outcome = "FALSIFIED"
        reason = "COUNTEREXAMPLE_FOUND"
        counterexample_found = True
    else:
        outcome = "ERROR"
        reason = "CROSSHAIR_ERROR"
        counterexample_found = False
    return base | {
        "outcome": outcome,
        "reason": reason,
        "executed": True,
        "exit_code": result.returncode,
        "counterexample_found": counterexample_found,
        "duration_ms": elapsed_ms,
        "stdout": _bounded_output(result.stdout),
        "stderr": _bounded_output(result.stderr),
        "argv": argv,
    }


def run_verifier_checks(
    ws: Workspace,
    checks: list[dict[str, Any]] | None,
    *,
    default_timeout_seconds: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, check in enumerate(checks or []):
        if not isinstance(check, dict):
            raise BananaMeError("INVALID_VERIFIER_CHECK", "verifier_checks entries must be objects.", details={"index": index})
        provider = str(check.get("provider") or "").strip().lower()
        timeout_seconds = max(1, min(int(check.get("timeout_seconds") or default_timeout_seconds), 900))
        if provider == "hypothesis":
            result = _run_hypothesis(ws, check, timeout_seconds)
        elif provider == "crosshair":
            result = _run_crosshair(ws, check, timeout_seconds)
        else:
            raise BananaMeError(
                "UNKNOWN_VERIFIER_PROVIDER",
                f"Unknown optional verifier provider: {provider or '<empty>'}",
                details={"index": index, "allowed": ["hypothesis", "crosshair"]},
            )
        result["request_index"] = index
        result["timeout_seconds"] = timeout_seconds
        results.append(result)
    return results
