# BananaMe

**Headless AI-to-AI Code Interface**

> Understand the minimum. Mutate exactly. Verify mechanically.

BananaMe is an experimental coding substrate for AI agents. It deliberately does **not** contain an LLM, planner, chat UI, autonomous loop, memory system, model router, governance engine, or automatic commit policy.

Its public surface is intentionally small:

```text
understand → mutate → verify
```

BananaMe is designed as an independent tool. Systems such as MangoMe may govern its use, but BananaMe does not depend on MangoMe.

## v0.1.0

The first release establishes the machine contract and safe mutation boundary:

- compact repository localization using ripgrep with a deterministic Python fallback;
- Python AST symbol localization with stable qualified symbol references and body hashes;
- bounded Git-history co-change evidence;
- SHA-256 guarded exact SEARCH/REPLACE edits;
- zero-match and multi-match fail-closed semantics;
- Git HEAD stale-state guard;
- CRLF/LF preservation without rewriting an entire file's newline convention;
- multi-file in-memory preflight before writes;
- built-in syntax preflight for Python, JSON, TOML and XML;
- persisted transaction evidence and pre-mutation backups under `.bananame/`;
- conflict-safe rollback that refuses to erase later work;
- syntax/diagnostic verification plus explicit argv-based test/lint commands;
- CLI, Agent Skill and optional MCP adapter over the same core;
- no automatic Git commit.

## Architecture

```text
                    Agent / Host
                         │
                Skill or MCP adapter
                         │
                  BananaMe Core
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    UNDERSTAND         MUTATE           VERIFY
        │                │                │
 lexical search      exact blocks      syntax
 Python AST          hash guards       diagnostics
 Git co-change       transaction       explicit tests
 compact context     rollback          evidence
```

The v0.1 architecture is intentionally narrower than the target architecture. Cross-language symbol graphs, call/type/data-flow relations, content-addressed incremental graph updates and semantic diffs are planned behind the existing `understand`/`verify` contract rather than exposed as more agent tools.

## Install

Core + CLI:

```bash
python -m pip install -e .
```

MCP adapter:

```bash
python -m pip install -e '.[mcp]'
```

Development:

```bash
python -m pip install -e '.[dev]'
pytest
```

## CLI

Understand:

```bash
bananame --workspace /repo understand --query "session expiry authentication"
```

Mutation requires current file hashes. Example payload:

```json
[
  {
    "path": "src/auth.py",
    "search": "def valid(token):\n    return False\n",
    "replace": "def valid(token):\n    return bool(token)\n",
    "expected_sha256": "<sha256 from understand>"
  }
]
```

Apply:

```bash
bananame --workspace /repo mutate --expected-head <git-sha> --edits-json '<json-array>'
```

Verify:

```bash
bananame --workspace /repo verify --transaction-id <id> --command-json '["python","-m","pytest","-q"]'
```

Rollback:

```bash
bananame --workspace /repo mutate --rollback <transaction-id>
```

Rollback is conflict-safe: if a file changed after the BananaMe transaction, rollback fails rather than deleting the later work.

## MCP

The optional MCP server exports only three tools:

```text
understand
mutate
verify
```

Default transport is stdio:

```bash
bananame-mcp
```

BananaMe does not use FastAPI for local MCP operation.

## Safety boundary

BananaMe v0.1 follows these invariants:

```text
OBSERVATION != MUTATION
MUTATION != VERIFICATION
VERIFICATION != PROMOTION
APPLIED != CORRECT
EXIT_0 != OWNER_ACCEPTANCE
```

`.git` is never directly mutated. Workspace paths are resolved and confined beneath the selected root. Mutation through symlink files is rejected in v0.1. User-supplied verification commands are argv arrays executed without `shell=True`.

## Donor strategy

BananaMe is independently composed and does not vendor donor source code in v0.1. Relevant prior art includes Aider, agentpatch, Entire Graph, ast-grep, SWE-agent, RepoGraph/LocAgent/Agentless and related repository-level software-engineering research. See `THIRD_PARTY_NOTICES.md` and `docs/donor-map.md`.

The project deliberately follows a reuse-first strategy: proven external mechanisms should be composed where they improve the kernel; custom code is reserved for BananaMe's transaction/evidence boundary and unified AI-facing protocol.

## Status

v0.1.0 is an alpha foundation. Its mutation path is usable; its repository intelligence is intentionally conservative. Claims of superiority over Aider or other coding systems require controlled evaluation and are not made by this release.
