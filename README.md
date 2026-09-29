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
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-yellow">
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

## What BananaMe v0.1.0 can do today

v0.1.0 is intentionally small, but it is not a mock-up. The first release establishes a usable repository-understanding, mutation and verification path with machine-readable evidence.

| Capability | v0.1.0 behavior |
|---|---|
| Repository observation | Reads Git HEAD, dirty state and repository inventory without modifying source files. |
| Bounded localization | Uses `ripgrep` when available and a deterministic Python fallback otherwise. Results are ranked and bounded by a context budget. |
| Hot-file context | A caller can identify files already believed relevant and receive guarded context for them. |
| File-state guards | Returns SHA-256 hashes for observed files so later mutation can prove it is editing the state the agent actually saw. |
| Python symbol localization | Parses Python with the standard AST and returns class/function/method locations, qualified names and body hashes. |
| Git-history hints | Computes bounded co-change evidence for files that historically changed with the current candidate files. |
| Surgical edits | Applies exact SEARCH/REPLACE blocks instead of asking an LLM to rewrite complete files. |
| Ambiguity refusal | Zero matches fail. Multiple matches fail. BananaMe never silently chooses an arbitrary match. |
| Stale-state protection | Can require both an expected Git HEAD and expected per-file SHA-256 hashes. |
| Multi-file transaction preflight | Resolves and validates every proposed edit in memory before the first source write. |
| Newline preservation | Adapts replacement text to the target file's LF/CRLF convention instead of normalizing the entire file. |
| Syntax preflight | Validates changed Python, JSON, TOML and XML/SVG content before writes are accepted. |
| Atomic file replacement | Writes through a temporary file, flushes it and atomically replaces the target with `os.replace`. |
| Transaction evidence | Persists a manifest, before-hashes, after-hashes, backups and a unified diff under `.bananame/transactions/`. |
| Safe rollback | Restores a transaction only if the files still contain the exact post-transaction hashes. Later human/agent work is never overwritten silently. |
| Verification | Re-checks syntax and can execute explicit lint/test commands as argv arrays without `shell=True`. |
| Additional syntax tools | Uses `node --check`, `php -l` and `bash -n` when those runtimes exist. |
| Machine protocol | CLI, Python API, Agent Skill and optional MCP server all call the same core implementation. |
| No automatic promotion | BananaMe never commits, deploys, approves or converts a passing test into an acceptance decision. |

The core package has **no mandatory third-party runtime dependencies** in v0.1.0. MCP support is an optional extra.

### Repository/layout invariant

BananaMe intentionally keeps the repository shallow. Ordinary project files stay at a maximum directory depth of two because deeper layouts have repeatedly caused problems in agent upload, packaging and handoff workflows. The only deliberate exception is GitHub Actions under `.github/workflows/`. The installable Skill therefore lives directly at `src/bananame/SKILL.md`, while `skill/SKILL.md` remains the repository-facing mirror.

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

If Git HEAD moved, BananaMe returns `STALE_HEAD`.

If a target file changed since observation, BananaMe returns `STALE_FILE`.

The correct recovery is a new observation, not a fuzzy guess.

### 2. Exact edits instead of full-file regeneration

BananaMe v0.1 uses exact SEARCH/REPLACE blocks as the mutation primitive.

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

### 3. Preflight the complete transaction before writing

A multi-file change is not processed as a sequence of unrelated writes.

BananaMe first:

```text
resolve all workspace paths
        ↓
validate expected Git HEAD
        ↓
validate every expected file hash
        ↓
resolve every SEARCH block uniquely
        ↓
build every resulting file in memory
        ↓
run syntax preflight on every changed file
        ↓
create transaction evidence + backups
        ↓
write files
```

If any edit fails during the preflight, **no source file is written**.

If an unexpected error occurs during the write phase, already-written files are restored from the transaction snapshot before the operation returns failure.

This is application-level transactional mutation, not a claim of filesystem-wide ACID semantics.

### 4. Preserve the repository instead of normalizing it

A surgical edit should not create an unrelated full-file diff.

BananaMe therefore records the file's newline convention and adapts replacement blocks to it. Editing one CRLF file does not silently convert the entire file to LF.

The original file mode is also preserved during atomic replacement.

### 5. Make every mutation inspectable

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

### 6. Roll back without erasing later work

Traditional `git checkout -- file` rollback is unsafe for an AI tool because it can destroy unrelated uncommitted changes.

BananaMe uses transaction ownership instead:

```text
transaction after_hash == current file hash ?

YES → rollback may restore the captured before-image
NO  → ROLLBACK_CONFLICT; do not touch the file
```

This means a later edit by a user or another agent is protected from a stale rollback request.

### 7. Verification is separate from mutation

`mutate()` can prove that a guarded change was applied. It cannot prove the change is correct.

`verify()` is a separate phase. It can:

- check the files changed by a BananaMe transaction;
- check explicitly supplied paths;
- compile/parse Python, JSON, TOML and XML/SVG;
- invoke `node --check`, `php -l` or `bash -n` when available;
- execute caller-selected tests or linters as explicit argv arrays;
- enforce bounded command timeouts;
- return bounded stdout/stderr and exit codes as structured evidence.

Verification commands are passed as arrays such as:

```json
["python", "-m", "pytest", "-q"]
```

BananaMe intentionally rejects shell command strings. It does not invoke them with `shell=True`.

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

Typical input:

```json
{
  "workspace_root": "/repo",
  "query": "session expiry authentication",
  "hot_files": ["src/auth.py"],
  "max_context_bytes": 8192,
  "max_results": 20
}
```

The response contains the current revision/state, ranked locations, guarded file evidence, symbol information where available and bounded Git-history hints.

### `mutate`

Guarded transactional mutation.

Typical input:

```json
{
  "workspace_root": "/repo",
  "expected_head": "<git-head-from-understand>",
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

The response contains the transaction ID, changed files, before/after hashes, syntax-preflight results and unified diff.

### `verify`

Machine-readable validation evidence.

Typical input:

```json
{
  "workspace_root": "/repo",
  "transaction_id": "<transaction-id>",
  "commands": [
    ["python", "-m", "pytest", "-q"]
  ],
  "timeout_seconds": 60
}
```

The response reports syntax checks, command exit codes, bounded output and a final `VERIFIED` or `VERIFICATION_FAILED` status.

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
     body hashes       atomic writes      evidence
     co-change         tx manifest
     context budget    safe rollback
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
| Verification | native language/runtime tools | structured evidence, never automatic promotion authority |

v0.1.0 does **not vendor donor source code**. The core implementation is small and dependency-free. `THIRD_PARTY_NOTICES.md` records the relevant prior art and licensing context.

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
STALE STATE MUST BE RE-OBSERVED
AMBIGUITY MUST FAIL CLOSED
ROLLBACK MUST NOT ERASE LATER WORK
```

Additional v0.1 boundaries:

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

v0.1.0 freezes the machine protocol and safe mutation boundary before adding heavier repository intelligence.

Current limitations are explicit:

- AST symbol extraction is currently Python-specific;
- other languages still rely mainly on bounded lexical localization;
- there is not yet a persistent cross-language call/type/data-flow graph;
- content-addressed per-file parse caching is not yet implemented;
- semantic diff and impact neighborhoods are not yet exposed;
- `ast-grep` is not yet a runtime dependency;
- BananaMe does not automatically infer the optimal test command;
- no benchmark superiority claim over Aider, AFT, SWE-agent or other systems is made by v0.1.0.

These are expansion points behind the existing `understand` and `verify` contracts, not reasons to add more public tools.

---

## Planned evolution

The intended internal progression is:

```text
v0.1
guarded state + bounded localization + transactional editing + verification

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

Development:

```bash
python -m pip install -e '.[dev]'
pytest
```

Python 3.10+ is supported by the package metadata and CI currently tests Python 3.10, 3.11, 3.12 and 3.13.

---

## CLI quick start

Observe the repository:

```bash
bananame --workspace /repo understand \
  --query "session expiry authentication"
```

Use the returned `head` and file SHA-256 values to build guarded edits.

Apply a mutation:

```bash
bananame --workspace /repo mutate \
  --expected-head <git-sha> \
  --edits-json '<json-array>'
```

Verify the transaction:

```bash
bananame --workspace /repo verify \
  --transaction-id <transaction-id> \
  --command-json '["python","-m","pytest","-q"]'
```

Roll back while BananaMe still owns the post-edit state:

```bash
bananame --workspace /repo mutate \
  --rollback <transaction-id>
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

For HTTP-capable hosts the transport can be switched with `BANANAME_MCP_TRANSPORT`; the coding core itself remains transport-independent.

---

## Agent Skill

`skill/SKILL.md` teaches an AI host the minimal operating discipline:

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
- [Security](SECURITY.md) — workspace, mutation and command-execution boundaries.
- [Third-party notices](THIRD_PARTY_NOTICES.md) — prior art and dependency/license notes.

---

## Status

BananaMe v0.1.0 is an **experimental alpha foundation**.

The safe mutation path, transaction evidence, rollback semantics, verification separation and three-operation AI interface are implemented. Repository intelligence is deliberately conservative in this release and will be expanded behind the existing interface.

The project does not currently claim to outperform Aider or other coding agents. That claim, if it is ever made, must be earned through controlled evaluation of localization quality, context cost, mutation reliability, verification outcomes and wall-clock overhead.
