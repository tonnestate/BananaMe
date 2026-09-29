# BananaMe

<p align="center">
  <img src="docs/bananame-banner.png" alt="BananaMe — deterministic AI-to-AI coding tool" width="100%">
</p>

<p align="center">
  <strong>Repository intelligence and transactional code mutation for AI agents.</strong><br>
  Understand the minimum. Mutate exactly. Verify mechanically.
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue">
  <img alt="Status" src="https://img.shields.io/badge/status-experimental-orange">
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.2-yellow">
  <img alt="Python" src="https://img.shields.io/badge/python-%3E%3D3.10-3776AB">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-optional-5b5bd6">
  <img alt="Agent Skill" src="https://img.shields.io/badge/agent-skill-purple">
  <img alt="LLM" src="https://img.shields.io/badge/built--in%20LLM-none-black">
</p>

---

## What BananaMe is

BananaMe is a **headless AI-to-AI coding tool**. It sits between a coding agent and a repository and turns common repository operations into a small, deterministic machine interface.

A normal coding agent has to repeatedly solve three different problems:

```text
Where is the relevant code?
        ↓
How can I change it without guessing or overwriting unrelated work?
        ↓
How do I demonstrate what actually happened?
```

BananaMe reduces that to three public operations:

```text
UNDERSTAND  →  MUTATE  →  VERIFY
```

It is deliberately **not** another autonomous coding agent. BananaMe contains no LLM, no planner, no chat UI, no model routing, no long-term memory, no task-management system, no governance authority, and no automatic commit or deployment policy.

The host remains responsible for reasoning and authority. BananaMe is the deterministic repository interface underneath it.

> **Agents decide. BananaMe observes, mutates and verifies repository state.**

BananaMe is independent of MangoMe, SPARI, AVCOS and any model/provider. MangoMe may govern BananaMe. SPARI may decide what should be reused or built. Neither is required to run BananaMe.

---

## What BananaMe v0.1.2 can do today

v0.1.2 keeps the v0.1.1 concurrency/recovery guarantees and adds a deliberately small composable-falsification layer behind `verify`. The public interface remains exactly `understand → mutate → verify`.

| Capability | v0.1.2 behavior |
|---|---|
| Repository observation | Reads Git HEAD, dirty state and repository inventory without modifying source files. |
| Bounded localization | Uses `ripgrep` when available and a deterministic Python fallback otherwise. Results are ranked and bounded by a context budget. |
| Hot-file context | A caller can identify files already believed relevant and receive guarded context for them. |
| File-state guards | Returns SHA-256 hashes for observed files so later mutation can prove it is editing the state the agent actually saw. |
| Python symbol localization | Parses Python with the standard AST and returns class/function/method locations, qualified names and body hashes. |
| Git-history hints | Computes bounded co-change evidence for files that historically changed with the current candidate files. |
| Surgical edits | Applies exact SEARCH/REPLACE blocks instead of asking an LLM to rewrite complete files. |
| Ambiguity refusal | Zero matches fail. Multiple matches fail. BananaMe never silently chooses an arbitrary match. |
| Target-scoped optimistic concurrency | Per-file SHA-256 guards are mandatory. The repository-wide `expected_head` guard remains optional for strict tasks. Targets are revalidated under a short mutation lock and again immediately before each write. |
| Multi-file transaction preflight | Resolves every proposed edit against the same original file snapshots, rejects overlapping spans, and validates all changed files before the first source write. |
| Newline preservation | Adapts replacement text to the target file's LF/CRLF convention instead of normalizing the entire file. |
| Syntax preflight | Validates changed Python, JSON, TOML and XML/SVG content before writes are accepted. |
| Atomic file replacement | Writes through a temporary file, flushes it and atomically replaces the target with `os.replace`. |
| Recoverable transaction journal | Persists before-images, intended after-hashes, per-file progress and a unified diff before source mutation, enabling explicit recovery after process interruption. |
| Safe rollback | Restores a transaction only if the files still contain the exact post-transaction hashes. Later human/agent work is never overwritten silently. |
| Verification truth states | Separates `VERIFIED`, `PARTIAL`, `NOT_VERIFIED` and `VERIFICATION_FAILED` so missing checker coverage cannot be reported as success. |
| Optional Hypothesis verifier | Runs an explicitly selected existing property test through pytest when Hypothesis is installed; never generates properties automatically. |
| Optional CrossHair verifier | Runs an explicitly selected CrossHair target with a bounded time budget and normalizes counterexample/no-counterexample/error outcomes. |
| Verifier provenance | Preserves whether a property/check is `PROJECT_EXISTING`, `OWNER_SUPPLIED`, `SPEC_DERIVED`, `AGENT_GENERATED`, or `UNKNOWN`. |
| Capability discovery | Reports whether pytest, Hypothesis and CrossHair are available without making them mandatory runtime dependencies. |
| Additional syntax tools | Uses `node --check`, `php -l` and `bash -n` when those runtimes exist. |
| Machine protocol | CLI, Python API, Agent Skill and optional MCP server all call the same core implementation. MCP binds its workspace on the host side instead of accepting an arbitrary agent-supplied root. |
| No automatic promotion | BananaMe never commits, deploys, approves or converts a passing test into an acceptance decision. |

The core package still has **no mandatory third-party runtime dependencies** in v0.1.2. MCP, Hypothesis and CrossHair are optional extras. Structural/graph providers are intentionally deferred rather than hidden inside the core.

### Repository/layout invariant

BananaMe intentionally keeps **its own release repository** shallow. Ordinary BananaMe project files stay at a maximum directory depth of two because deeper artifact layouts have repeatedly caused problems in agent upload, packaging and handoff workflows. The only deliberate exception is GitHub Actions under `.github/workflows/`. This is **not a restriction on target repositories**: BananaMe accepts arbitrarily deep workspace-relative paths such as `src/main/java/com/company/product/auth/AuthService.java`.

---

## How BananaMe solves the problem

### 1. Observe first; bind mutations to the observed state

`understand()` does not merely return snippets. It returns state that can later be used as a mutation guard:

```text
Git HEAD
working-tree dirty state
file path
file SHA-256
bounded source context
Python symbol identity where available
historical co-change hints
```

That produces an important invariant:

```text
Agent saw state S
      ↓
Agent proposes edit for S
      ↓
BananaMe verifies repository is still S
      ↓
only then may mutation begin
```

If the optional strict Git HEAD guard was requested and HEAD moved, BananaMe returns `STALE_HEAD`.

If an actual target file changed since observation, BananaMe returns `STALE_FILE`. v0.1.1 revalidates target hashes inside a short commit-phase lock and again immediately before each write. Unrelated repository changes therefore do not block normal target-scoped mutation.

The correct recovery from changed target state is a new observation, not a fuzzy guess.

### 2. Exact edits instead of full-file regeneration

BananaMe v0.1.1 keeps exact SEARCH/REPLACE blocks as the deterministic baseline mutation primitive.

```json
{
  "path": "src/auth.py",
  "search": "def valid(token):\n    return False\n",
  "replace": "def valid(token):\n    return bool(token)\n",
  "expected_sha256": "<hash returned by understand>"
}
```

Matching is fail-closed:

```text
0 matches  → SEARCH_NOT_FOUND
1 match    → eligible for mutation
>1 matches → SEARCH_AMBIGUOUS
```

BananaMe does not fall back to approximate/fuzzy replacement when the repository contradicts the agent's assumption.

### 3. Preflight against one snapshot, then validate again at commit

A multi-file change is not processed as a sequence of unrelated writes.

BananaMe first resolves every same-file edit against the **same original snapshot**. Non-overlapping spans are then applied from the end of the file backwards, so the result does not depend on edit ordering. Overlaps fail with `EDIT_OVERLAP`.

```text
resolve all workspace paths
        ↓
optional strict HEAD validation
        ↓
validate every expected target hash
        ↓
resolve all edit spans against original snapshots
        ↓
reject overlaps / build all post-images in memory
        ↓
syntax preflight
        ↓
short mutation lock
        ↓
revalidate every target hash
        ↓
persist recovery journal + before-images
        ↓
final hash compare immediately before each write
        ↓
atomic per-file replacement + progress journal
```

If any edit fails before the write phase, **no source file is written**. Handled write failures trigger ownership-aware rollback. A hard process/OS interruption is handled later through the persisted journal.

This is crash-recoverable application-level mutation, **not** a claim of filesystem-wide ACID semantics or serializability against arbitrary non-cooperating editors.

### 4. Recover interrupted write phases instead of pretending `os.replace` is multi-file ACID

v0.1.1 turns the transaction manifest into a write-ahead recovery journal. Before the first source write, BananaMe persists before-images, intended after-hashes and a `PREPARED`/`APPLYING` state. Per-file progress is journaled as writes complete.

If BananaMe restarts and finds an incomplete transaction, a new mutation is blocked with `RECOVERY_REQUIRED` until the transaction is reconciled. `mutate(action="recover")` classifies each target by checksum:

```text
current == before_hash  → not yet applied / already restored
current == after_hash   → BananaMe post-image present
anything else           → RECOVERY_CONFLICT; touch nothing
```

Mixed known states roll back to the captured before-images. If every target already matches its intended post-image, recovery records `APPLIED_RECOVERED`. Unknown bytes are never overwritten automatically.

### 5. Preserve the repository instead of normalizing it

A surgical edit should not create an unrelated full-file diff.

BananaMe therefore records the file's newline convention and adapts replacement blocks to it. Editing one CRLF file does not silently convert the entire file to LF.

The original file mode is also preserved during atomic replacement.

### 6. Make every mutation inspectable

Every successful mutation receives a transaction ID and a local evidence directory:

```text
.bananame/
└── transactions/
    └── <transaction-id>/
        ├── manifest.json
        ├── diff.patch
        └── before/
            └── <changed files>
```

The manifest records, among other fields:

```text
base_head
changed_files
before_hashes
after_hashes
requested edits
syntax preflight results
transaction status
```

A caller therefore receives more than "edit succeeded". It receives a reproducible description of what BananaMe believed it changed.

### 7. Roll back without erasing later work

Traditional `git checkout -- file` rollback is unsafe for an AI tool because it can destroy unrelated uncommitted changes.

BananaMe uses transaction ownership instead:

```text
transaction after_hash == current file hash ?

YES → rollback may restore the captured before-image
NO  → ROLLBACK_CONFLICT; do not touch the file
```

This means a later edit by a user or another agent is protected from a stale rollback request.

### 8. Verification is separate from mutation

`mutate()` can prove that a guarded change was applied. It cannot prove the change is correct.

`verify()` is a separate phase. It can:

- check the files changed by a BananaMe transaction;
- check explicitly supplied paths;
- compile/parse Python, JSON, TOML and XML/SVG;
- invoke `node --check`, `php -l` or `bash -n` when available;
- execute caller-selected tests or linters as explicit argv arrays;
- optionally execute an explicitly selected Hypothesis property test when Hypothesis is installed;
- optionally execute an explicitly selected CrossHair target when CrossHair is installed;
- preserve verifier provenance and uncertainty;
- enforce bounded command/verifier timeouts;
- return bounded stdout/stderr and normalized evidence.

Verification commands are passed as arrays such as:

```json
["python", "-m", "pytest", "-q"]
```

BananaMe intentionally rejects shell command strings. It does not invoke them with `shell=True`.

Optional verifier checks are explicitly requested. BananaMe does **not** synthesize properties and does **not** automatically start symbolic execution. Individual optional-provider outcomes are normalized as:

```text
PASSED
FALSIFIED
INCONCLUSIVE
ERROR
TIMEOUT
NOT_AVAILABLE
```

For CrossHair, `PASSED` means **no counterexample was found within the configured analysis budget**. It is not promoted to a universal correctness proof. `FALSIFIED` is negative evidence; inconclusive/error/timeout/not-available outcomes preserve uncertainty and therefore cannot make an otherwise incomplete run `VERIFIED`.

And even a successful verification remains only evidence:

```text
APPLIED != VERIFIED
VERIFIED != COMMITTED
COMMITTED != DEPLOYED
DEPLOYED != ACCEPTED
```

Commit, promotion, deployment and independent assurance belong to the host or governance layer.

---

## The AI-to-AI interface

BananaMe exposes only three semantic operations to an agent:

### `understand`

Read-only repository intelligence.

Typical Python/CLI-shaped input:

```json
{
  "workspace_root": "/repo",
  "query": "session expiry authentication",
  "hot_files": ["src/auth.py"],
  "max_context_bytes": 8192,
  "max_results": 20
}
```

MCP omits `workspace_root`; the host binds it with `BANANAME_WORKSPACE_ROOT`. The response contains current revision/state, ranked locations, guarded exact/hot-file evidence, symbol information where available, bounded Git-history hints and explicit completeness/truncation metadata.

### `mutate`

Guarded transactional mutation.

Typical Python/CLI-shaped input:

```json
{
  "workspace_root": "/repo",
  "edits": [
    {
      "path": "src/auth.py",
      "search": "...exact current code...",
      "replace": "...replacement code...",
      "expected_sha256": "<file-hash-from-understand>"
    }
  ]
}
```

`expected_head` may be added when strict whole-repository revision stability is required; it is not needed for normal target-scoped mutation. MCP again uses the host-bound workspace. The response contains the transaction ID, changed files, before/after hashes, syntax-preflight results, concurrency evidence and unified diff.

### `verify`

Machine-readable validation evidence.

Typical Python/CLI-shaped input:

```json
{
  "workspace_root": "/repo",
  "transaction_id": "<transaction-id>",
  "commands": [
    ["python", "-m", "pytest", "-q"]
  ],
  "verifier_checks": [
    {
      "provider": "hypothesis",
      "target": "tests/test_auth.py::test_roundtrip",
      "origin": "PROJECT_EXISTING"
    },
    {
      "provider": "crosshair",
      "target": "src/app/auth.py:validate_token",
      "analysis_kind": "asserts",
      "origin": "SPEC_DERIVED",
      "timeout_seconds": 10
    }
  ],
  "timeout_seconds": 60
}
```

The response reports syntax checks, command exit codes, optional-verifier evidence/capabilities, bounded output and one of four top-level evidence states: `VERIFIED`, `PARTIAL`, `NOT_VERIFIED`, or `VERIFICATION_FAILED`. Only `VERIFIED` maps to `ok=true`.

---

## Architecture

```text
                       CODING AGENT
                Claude / Codex / Copilot
                  OpenHands / other host
                            │
                 ┌──────────┴──────────┐
                 │                     │
             Agent Skill           MCP adapter
                 │                     │
                 └──────────┬──────────┘
                            │
                       BananaMe Core
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      UNDERSTAND          MUTATE            VERIFY
          │                 │                 │
     Git state         exact blocks       syntax
     inventory         SHA guards         diagnostics
     lexical search    HEAD guard         argv tests
     Python AST        full preflight     timeout
     body hashes       atomic writes      optional PBT/SMT
     co-change         tx manifest        provenance
     context budget    safe rollback      evidence
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                         Repository
```

The public surface is intentionally smaller than the internal implementation.

BananaMe should become more capable internally without forcing every host agent to learn an ever-growing tool catalog.

---

## Relationship to MangoMe and SPARI

BananaMe is intentionally a separate repository and has no runtime dependency on MangoMe or SPARI.

A possible composed system is:

```text
SPARI
  │
  │ reuse / build decision
  ▼
Coding Agent
  │
  ├──────────── BananaMe
  │              understand
  │              mutate
  │              verify
  │
  └──────────── MangoMe
                 work identity
                 governance
                 evidence / verification policy
                 effect reconciliation
```

The boundary is deliberate:

```text
SPARI    = engineering/reuse decision intelligence
MangoMe  = persistent work/governance substrate
BananaMe = repository understanding + safe code mutation + verification evidence
```

MangoMe may control whether a BananaMe mutation is authorized or whether its evidence is sufficient for a workflow. BananaMe itself does not know MangoMe exists.

---

## Donor strategy: reuse mechanisms, not products

BananaMe started from the question: what remains if a coding tool is built **for agents instead of humans**?

The project therefore treats existing systems as specialized donors/prior art rather than importing an entire coding application.

| Area | Donor / prior art | BananaMe direction |
|---|---|---|
| Exact editing | Aider, agentpatch | exact edit semantics + stale-state guards + transactions |
| Structural search/rewrite | ast-grep | future structural localization and mutation behind the same three-operation protocol |
| Repository graph | Entire Graph, RepoGraph, LocAgent | future symbol/relation/impact graph rather than whole-repo text dumps |
| Agent-computer interface | SWE-agent | small machine-oriented surface and immediate deterministic feedback |
| Incremental indexing | Continue, Entire Graph | content-addressed per-file invalidation rather than full rebuilds |
| Verification | native language/runtime tools, Hypothesis, CrossHair | structured falsification evidence, never automatic promotion authority |

v0.1.2 does **not vendor donor source code**. The core implementation is small and dependency-free. `THIRD_PARTY_NOTICES.md` records the relevant prior art and licensing context.

See [Donor Map](docs/donor-map.md) for the planned composition boundary.

---

## Why not just use Aider?

Aider is a full coding product designed around a human/LLM workflow. BananaMe targets a lower layer.

BananaMe does not need:

```text
chat UI
prompt/session product logic
voice
human approval prompts
provider/model routing
streaming presentation
automatic commit policy
web/UI integration
```

It needs the repository mechanics that an external agent can call deterministically.

That is why BananaMe's interface is not "chat with the repo". It is:

```text
understand(repository_state)
mutate(guarded_edits)
verify(transaction)
```

---

## Safety invariants

The initial release is built around a small set of hard rules:

```text
OBSERVATION != MUTATION
MUTATION != VERIFICATION
VERIFICATION != PROMOTION
APPLIED != CORRECT
EXIT_0 != OWNER_ACCEPTANCE
CHANGED MUTATION TARGETS MUST BE RE-OBSERVED
AMBIGUITY MUST FAIL CLOSED
ROLLBACK MUST NOT ERASE LATER WORK
```

Additional v0.1.2 boundaries:

- only workspace-relative paths are accepted;
- path traversal outside the selected workspace is rejected;
- direct `.git` access is rejected;
- `.bananame` is reserved for BananaMe's internal transaction state;
- mutable symlink files are rejected in v0.1;
- binary and non-UTF-8 source files are not mutated;
- verification commands are argv arrays, not shell strings;
- BananaMe never creates a Git commit automatically.

See [SECURITY.md](SECURITY.md) for the current trust boundary.

---

## Current limitations

v0.1.2 keeps the frozen machine protocol and adds optional composable falsification before the structural-intelligence milestone.

Current limitations are explicit:

- AST symbol extraction is currently Python-specific;
- other languages still rely mainly on bounded lexical localization;
- there is not yet a persistent cross-language call/type/data-flow graph;
- content-addressed per-file parse caching is not yet implemented;
- semantic diff and impact neighborhoods are not yet exposed;
- `ast-grep` is not yet a runtime dependency;
- optional Hypothesis/CrossHair providers are Python-focused and execute only explicit caller-selected targets;
- BananaMe does not automatically infer the optimal test command;
- the short BananaMe mutation lock coordinates BananaMe writers, but cannot force arbitrary external editors to honor it;
- exact SEARCH/REPLACE remains the baseline selector; symbol-/AST-addressed mutation is planned for v0.2;
- no benchmark superiority claim over Aider, AFT, SWE-agent or other systems is made by v0.1.1.

These are expansion points behind the existing `understand` and `verify` contracts, not reasons to add more public tools.

---

## Planned evolution

The intended internal progression is:

```text
v0.1.1
target-scoped optimistic validation + crash recovery + explicit evidence states

        ↓

content-addressed per-file parse/index cache

        ↓

cross-language stable symbol identity

        ↓

typed relation graph
CALLS / IMPORTS / IMPLEMENTS / USES_TYPE / TESTS / DATA_FLOWS

        ↓

impact neighborhoods + semantic diff + dirty-delta graph

        ↓

ast-grep structural search/rewrite

        ↓

adaptive retrieval
exact → lexical → structural → graph → history → semantic fallback
```

The external agent should still see only:

```text
understand
mutate
verify
```

---

## Install

Core + CLI:

```bash
python -m pip install -e .
```

Optional MCP adapter:

```bash
python -m pip install -e '.[mcp]'
```

Optional property-based verification:

```bash
python -m pip install -e '.[hypothesis]'
```

Optional CrossHair verification:

```bash
python -m pip install -e '.[crosshair]'
```

Both optional verifier providers:

```bash
python -m pip install -e '.[verification]'
```

Development:

```bash
python -m pip install -e '.[dev]'
pytest
```

Python 3.10+ is supported by the package metadata and CI currently tests Python 3.10, 3.11, 3.12 and 3.13.

### Codex / Agent Plugin skill discovery

For portable Agent Plugin and Codex discovery, the canonical repository skill lives at:

```text
skills/bananame/SKILL.md
```

The root `plugin.json` identifies BananaMe as a portable Agent Plugin package. `skill/SKILL.md` is retained as a compatibility mirror for existing installers, while `src/bananame/SKILL.md` is the packaged Python resource. All three Skill files are intentionally byte-identical and tested for drift.

Installing the Python runtime is still explicit:

```bash
python -m pip install -e '.[mcp]'
```

For a local MCP host, bind the target repository through `BANANAME_WORKSPACE_ROOT` before starting `bananame-mcp`. BananaMe does not hard-code a machine-specific local MCP configuration into the portable plugin manifest.

---

## CLI quick start

Observe the repository:

```bash
bananame --workspace /repo understand \
  --query "session expiry authentication"
```

Use the returned target-file SHA-256 values to build guarded edits. Inspect completeness/truncation flags before claiming repository-wide coverage. `head_revision` is available when a strict whole-repository guard is required.

Apply a normal target-scoped mutation:

```bash
bananame --workspace /repo mutate \
  --edits-json '<json-array>'
```

Add `--expected-head <git-sha>` only when the whole Git revision must remain fixed.

Verify the transaction:

```bash
bananame --workspace /repo verify \
  --transaction-id <transaction-id> \
  --command-json '["python","-m","pytest","-q"]'
```

Optional verifier requests use the same `verify` command:

```bash
bananame --workspace /repo verify \
  --path src/auth.py \
  --verifier-json '{"provider":"hypothesis","target":"tests/test_auth.py::test_roundtrip","origin":"PROJECT_EXISTING"}' \
  --verifier-json '{"provider":"crosshair","target":"src/app/auth.py:validate_token","analysis_kind":"asserts","origin":"SPEC_DERIVED","timeout_seconds":10}'
```

Roll back while BananaMe still owns the post-edit state:

```bash
bananame --workspace /repo mutate \
  --rollback <transaction-id>
```

Recover an interrupted journal:

```bash
bananame --workspace /repo mutate \
  --recover <transaction-id>
```

---

## MCP

Install the optional MCP dependency and start the server:

```bash
python -m pip install -e '.[mcp]'
bananame-mcp
```

Default transport is stdio.

The server exports exactly:

```text
understand
mutate
verify
```

For MCP, the host must bind the repository through `BANANAME_WORKSPACE_ROOT`; the agent-facing tools do not accept arbitrary workspace paths. For HTTP-capable hosts the transport can be switched with `BANANAME_MCP_TRANSPORT`; the coding core itself remains transport-independent.

---

## Agent Skill

`skills/bananame/SKILL.md` is the canonical portable/Codex skill path. `skill/SKILL.md` remains a compatibility mirror and `src/bananame/SKILL.md` is included in the installed Python package. They contain the same instructions.

The Skill teaches an AI host the minimal operating discipline:

```text
1. understand current state
2. mutate only against current guards
3. re-observe after stale/ambiguous failures
4. verify after mutation
5. never treat mutation or verification as promotion authority
```

The Skill contains procedure. The Python package contains mechanics. The MCP layer only exposes those mechanics to compatible hosts.

---

## Documentation

- [Start Here](docs/START_HERE.md) — the mental model and first complete agent workflow.
- [Architecture](docs/architecture.md) — current component boundaries and target evolution.
- [AI Protocol](docs/protocol.md) — operation semantics and machine-visible failure states.
- [Donor Map](docs/donor-map.md) — what is reused conceptually and where BananaMe adds its own delta.
- [Research Basis](docs/research-basis.md) — scientific basis for optimistic validation, crash recovery, compact agent interfaces and the planned structural-intelligence layer.
- [Security](SECURITY.md) — workspace, mutation and command-execution boundaries.
- [Third-party notices](THIRD_PARTY_NOTICES.md) — prior art and dependency/license notes.

---

## Status

BananaMe v0.1.2 is an **experimental alpha composable-verification release**.

The safe mutation path retains the v0.1.1 concurrency/recovery guarantees. v0.1.2 adds explicit optional Hypothesis and CrossHair verification behind the existing `verify` operation, without adding mandatory runtime dependencies, automatic property generation, automatic symbolic execution, or new MCP tools. Repository intelligence remains deliberately conservative and will be expanded behind the existing interface.

The project does not currently claim to outperform Aider or other coding agents. That claim, if it is ever made, must be earned through controlled evaluation of localization quality, context cost, mutation reliability, verification outcomes and wall-clock overhead.
