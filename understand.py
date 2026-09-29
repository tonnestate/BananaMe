from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .git import cochange, head_revision, tracked_and_untracked_files, working_tree_dirty
from .workspace import Workspace, sha256_bytes


_SKIP_DIRS = {".git", ".bananame", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.:/-]{2,}")


@dataclass(frozen=True)
class Symbol:
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    body_hash: str


@dataclass(frozen=True)
class Inventory:
    files: list[str]
    truncated: bool
    total: int | None
    source: str
    limit: int


def _inventory(root: Path, limit: int = 50000) -> Inventory:
    git_files = tracked_and_untracked_files(root)
    if git_files:
        total = len(git_files)
        return Inventory(git_files[:limit], total > limit, total, "git", limit)
    out: list[str] = []
    truncated = False
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            path = Path(base) / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if len(out) >= limit:
                truncated = True
                return Inventory(sorted(out), truncated, None, "walk", limit)
            out.append(rel)
    return Inventory(sorted(out), truncated, len(out), "walk", limit)


def _python_symbols(text: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines(keepends=True)
    symbols: list[Symbol] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _record(self, node: ast.AST, kind: str, name: str) -> None:
            start = int(getattr(node, "lineno", 1))
            end = int(getattr(node, "end_lineno", start))
            qualified = ".".join([*self.stack, name]) if self.stack else name
            segment = "".join(lines[start - 1 : end]).encode("utf-8")
            symbols.append(Symbol(kind, name, qualified, start, end, sha256_bytes(segment)[:16]))

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._record(node, "class", node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._record(node, "function" if not self.stack else "method", node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

    Visitor().visit(tree)
    return symbols


def _enclosing_symbol(symbols: Iterable[Symbol], line: int) -> Symbol | None:
    candidates = [s for s in symbols if s.start_line <= line <= s.end_line]
    if not candidates:
        return None
    return min(candidates, key=lambda s: (s.end_line - s.start_line, -s.start_line))


def _terms(query: str) -> list[str]:
    raw = [token for token in _WORD_RE.findall(query) if len(token) >= 3]
    seen: set[str] = set()
    out: list[str] = []
    for token in raw:
        lower = token.lower()
        if lower not in seen:
            seen.add(lower)
            out.append(token)
    return out[:16]


def _rg_hits(root: Path, query: str, max_results: int) -> tuple[list[dict], bool, int]:
    rg = shutil.which("rg")
    terms = _terms(query)
    if not rg or not terms:
        return [], False, 0
    pattern = "(?:" + "|".join(re.escape(term) for term in terms) + ")"
    cmd = [
        rg,
        "--json",
        "--line-number",
        "--ignore-case",
        "--max-count",
        "20",
        "--glob",
        "!.git/**",
        "--glob",
        "!.bananame/**",
        "--glob",
        "!node_modules/**",
        pattern,
        ".",
    ]
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=20, check=False)
    hits: list[dict] = []
    candidate_limit = max_results * 4 + 1
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") != "match":
            continue
        data = item.get("data", {})
        path = str(data.get("path", {}).get("text", "")).removeprefix("./").replace("\\", "/")
        line_no = int(data.get("line_number") or 0)
        text = str(data.get("lines", {}).get("text", "")).rstrip("\r\n")
        matched = {term.lower() for term in terms if term.lower() in text.lower() or term.lower() in path.lower()}
        score = len(matched) * 10 + (3 if any(term.lower() in path.lower() for term in terms) else 0)
        hits.append({"path": path, "line": line_no, "text": text, "score": score, "matched_terms": sorted(matched)})
        if len(hits) >= candidate_limit:
            break
    hits.sort(key=lambda h: (-h["score"], h["path"], h["line"]))
    return hits[:max_results], len(hits) > max_results, len(hits)


def _fallback_hits(root: Path, files: list[str], query: str, max_results: int) -> tuple[list[dict], bool, int]:
    terms = [t.lower() for t in _terms(query)]
    if not terms:
        return [], False, 0
    hits: list[dict] = []
    candidate_limit = max_results * 4 + 1
    for rel in files:
        path = root / rel
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for no, line in enumerate(text.splitlines(), 1):
            matched = {term for term in terms if term in line.lower() or term in rel.lower()}
            if matched:
                hits.append({"path": rel, "line": no, "text": line, "score": len(matched) * 10, "matched_terms": sorted(matched)})
                if len(hits) >= candidate_limit:
                    break
        if len(hits) >= candidate_limit:
            break
    hits.sort(key=lambda h: (-h["score"], h["path"], h["line"]))
    return hits[:max_results], len(hits) > max_results, len(hits)


def _utf8_prefix(text: str, max_bytes: int) -> tuple[str, bool]:
    if max_bytes <= 0:
        return "", bool(text)
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    prefix = raw[:max_bytes]
    while prefix:
        try:
            return prefix.decode("utf-8"), True
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return "", True


def _symbol_dict(symbol: Symbol) -> dict:
    return {
        "kind": symbol.kind,
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "body_hash": symbol.body_hash,
        "resolution": "exact_ast",
        "confidence": 1.0,
    }


def understand(
    workspace_root: str,
    query: str = "",
    hot_files: list[str] | None = None,
    max_context_bytes: int = 8192,
    max_results: int = 20,
) -> dict:
    ws = Workspace(workspace_root)
    max_context_bytes = max(1024, min(int(max_context_bytes), 131072))
    max_results = max(1, min(int(max_results), 100))
    inventory = _inventory(ws.root)
    files = inventory.files
    hot = [p.replace("\\", "/") for p in (hot_files or [])]

    exact_files: list[str] = []
    for candidate in [query, *hot]:
        if not candidate:
            continue
        try:
            path = ws.resolve(candidate)
        except Exception:
            continue
        if path.is_file():
            rel = path.relative_to(ws.root).as_posix()
            if rel not in exact_files:
                exact_files.append(rel)

    search_query = "" if query in exact_files else query
    if search_query:
        hits, search_truncated, candidates_seen = _rg_hits(ws.root, search_query, max_results)
        if not hits:
            hits, search_truncated, candidates_seen = _fallback_hits(ws.root, files, search_query, max_results)
    else:
        hits, search_truncated, candidates_seen = [], False, 0

    symbol_cache: dict[str, list[Symbol]] = {}
    file_evidence: list[dict] = []
    file_evidence_truncated = False
    enriched: list[dict] = []
    budget = 0
    context_truncated = False
    truncation_reasons: list[str] = []

    for path in exact_files:
        try:
            snap = ws.read_text(path)
        except Exception:
            continue
        record: dict = {
            "path": path,
            "sha256": snap.sha256,
            "size_bytes": len(snap.raw),
        }
        if path.endswith(".py"):
            symbols = symbol_cache.setdefault(path, _python_symbols(snap.text))
            summaries: list[dict] = []
            for symbol in symbols[:50]:
                candidate = [*summaries, _symbol_dict(symbol)]
                probe = {**record, "symbols": candidate, "symbols_truncated": len(symbols) > len(candidate)}
                if budget + len(json.dumps(probe, ensure_ascii=False).encode("utf-8")) > max_context_bytes:
                    break
                summaries = candidate
            if summaries:
                record["symbols"] = summaries
                record["symbols_truncated"] = len(symbols) > len(summaries)
        metadata_bytes = len(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        remaining = max(0, max_context_bytes - budget - metadata_bytes - 96)
        content, truncated = _utf8_prefix(snap.text, min(remaining, 4096))
        if content:
            record["content"] = content
            record["content_truncated"] = truncated
        else:
            record["content_omitted"] = "CONTEXT_BUDGET"
            truncated = bool(snap.text)
        encoded = json.dumps(record, ensure_ascii=False).encode("utf-8")
        if budget + len(encoded) > max_context_bytes:
            # Retry with guard-only evidence. If even guard metadata does not fit,
            # stop rather than silently exceeding the advertised context budget.
            record.pop("symbols", None)
            record.pop("symbols_truncated", None)
            record.pop("content", None)
            record.pop("content_truncated", None)
            record["content_omitted"] = "CONTEXT_BUDGET"
            encoded = json.dumps(record, ensure_ascii=False).encode("utf-8")
            context_truncated = True
            truncation_reasons.append("context_budget")
            if budget + len(encoded) > max_context_bytes:
                file_evidence_truncated = True
                break
        budget += len(encoded)
        file_evidence.append(record)
        if truncated:
            context_truncated = True
            truncation_reasons.append("file_preview")

    if len(file_evidence) < len(exact_files):
        file_evidence_truncated = True
        context_truncated = True
        truncation_reasons.append("context_budget")

    for hit in hits:
        path = hit["path"]
        try:
            snap = ws.read_text(path)
        except Exception:
            continue
        record = dict(hit)
        record["sha256"] = snap.sha256
        if path.endswith(".py"):
            symbols = symbol_cache.setdefault(path, _python_symbols(snap.text))
            symbol = _enclosing_symbol(symbols, hit["line"])
            if symbol:
                record["symbol"] = {
                    "id": f"python:{path}:{symbol.kind}:{symbol.qualified_name}",
                    **_symbol_dict(symbol),
                }
        encoded = json.dumps(record, ensure_ascii=False).encode("utf-8")
        if budget + len(encoded) > max_context_bytes:
            context_truncated = True
            truncation_reasons.append("context_budget")
            break
        budget += len(encoded)
        enriched.append(record)

    if inventory.truncated:
        truncation_reasons.append("inventory_limit")
    if search_truncated:
        truncation_reasons.append("max_results")
    truncation_reasons = sorted(set(truncation_reasons))

    anchors = hot or exact_files or [h["path"] for h in enriched[:2]]
    head = head_revision(ws.root)
    return {
        "ok": True,
        "operation": "understand",
        "workspace": str(ws.root),
        "head_revision": head,
        "working_tree_dirty": working_tree_dirty(ws.root),
        "query": query,
        "inventory_count": len(files),
        "inventory_returned": len(files),
        "inventory_total": inventory.total,
        "inventory_limit": inventory.limit,
        "inventory_truncated": inventory.truncated,
        "inventory_source": inventory.source,
        "exact_files": exact_files,
        "file_evidence": file_evidence,
        "file_evidence_requested": len(exact_files),
        "file_evidence_returned": len(file_evidence),
        "file_evidence_truncated": file_evidence_truncated,
        "hits": enriched,
        "search_candidates_seen": candidates_seen,
        "search_results_returned": len(enriched),
        "search_truncated": search_truncated,
        "cochange": cochange(ws.root, anchors),
        "context_bytes": budget,
        "context_budget_bytes": max_context_bytes,
        "context_truncated": context_truncated,
        "truncation_reasons": truncation_reasons,
        "capabilities": {
            "lexical_search": "ripgrep" if shutil.which("rg") else "python_fallback",
            "python_ast": True,
            "git_history_cochange": head is not None,
            "ast_grep_available": bool(shutil.which("ast-grep")),
            "semantic_graph": "python_symbol_localization_v1",
        },
        "limitations": [
            "v0.1.1 semantic symbol extraction is Python-native; other languages use lexical localization.",
            "Cross-language call/type/data-flow graphing is intentionally deferred to the structural-intelligence milestone.",
            "ast-grep is detected but is not yet invoked by the v0.1.1 core.",
        ],
    }
