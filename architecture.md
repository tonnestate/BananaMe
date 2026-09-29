# Architecture

BananaMe is a deterministic repository substrate below coding agents and above filesystem/Git mechanics.

```text
Agent reasoning / planning / governance
                 │
        Skill or MCP adapter
                 │
                 ▼
             BananaMe Core
                 │
      understand/mutate/verify
                 │
                 ▼
            Repository
```

## Design boundary

BananaMe owns three things:

1. bounded repository observation;
2. guarded and recoverable source mutation;
3. machine-readable verification evidence.

BananaMe explicitly does not own task planning, model inference/routing, long-term agent memory, work-item governance, Git commit policy, deployment policy, acceptance, or independent assurance.

## v0.1.2 component map

```text
src/bananame/
├── core.py        # stable three-operation facade + machine-readable failures
├── understand.py  # bounded observation/localization + completeness metadata
├── mutate.py      # optimistic validation + journaled mutation/rollback/recovery
├── verify.py      # syntax/command/provider aggregation + evidence states
├── verifiers.py   # optional Hypothesis/CrossHair provider execution
├── workspace.py   # confinement, snapshots, atomic writes, commit-phase lock
├── git.py         # HEAD, dirty state, inventory, co-change history
├── cli.py         # JSON CLI adapter
└── mcp_server.py  # optional MCP adapter
```

## UNDERSTAND

v0.1.1 keeps lexical/Python-AST intelligence deliberately small but makes incompleteness explicit:

```text
workspace
   ├─ Git HEAD / dirty state
   ├─ tracked + untracked inventory
   │    └─ explicit truncation metadata
   ├─ exact/hot-file evidence
   │    ├─ SHA-256 guard
   │    ├─ bounded content
   │    └─ Python symbol summary where available
   ├─ ripgrep lexical localization
   │    └─ deterministic Python fallback
   ├─ Python AST enclosing-symbol extraction
   └─ bounded Git co-change evidence
```

The next intelligence milestone is adaptive exact/lexical/structural/graph/history retrieval behind the same `understand` operation.

## MUTATE: optimistic target validation

The normal concurrency boundary is the actual mutation target, not the whole repository.

```text
observe file hashes
      ↓
preflight without long lock
      ↓
short BananaMe commit-phase lock
      ↓
revalidate every target hash
      ↓
write-ahead transaction journal
      ↓
final compare before each target write
      ↓
atomic replace + after-hash verification
```

`expected_head` is optional. Supplying it requests stricter repository-wide consistency; omitting it allows unrelated HEAD movement as long as target files remain unchanged.

The lock coordinates BananaMe writers and automatically releases on process death. It is intentionally not a claim that arbitrary external editors honor the same lock.

## Exact edit resolution

All edits for one file are resolved against the same original snapshot. BananaMe requires exactly one occurrence per SEARCH block, maps each edit to a concrete span, rejects overlapping spans, and applies non-overlapping spans from the end of the file toward the beginning.

This removes edit-order dependence without introducing fuzzy matching.

## Journaled write phase and crash recovery

v0.1.1 uses `bananame-transaction/2`:

```text
PREPARED → APPLYING → APPLIED
                 ↘
                  RECOVERY_REQUIRED
```

The journal records before/after hashes and per-file progress before dependent source writes. Atomic file replacement fsyncs the temporary file and best-effort fsyncs the parent directory on supported platforms.

Recovery classifies targets by checksum:

- `BEFORE`: intended write is absent;
- `AFTER`: intended write is present;
- unknown: fail closed with `RECOVERY_CONFLICT`.

Mixed known states are rolled back to captured before-images. An all-after state is marked `APPLIED_RECOVERED`.

This is crash-recoverable application-level mutation, not filesystem-wide ACID.

## VERIFY: evidence completeness and optional falsification

v0.1.2 preserves the v0.1.1 execution/evidence distinction:

```text
VERIFIED
PARTIAL
NOT_VERIFIED
VERIFICATION_FAILED
```

A missing checker produces `SKIP` and can no longer be collapsed into a positive verification result.

Built-in checkers remain intentionally small: Python, JSON, TOML and XML/SVG, plus local `node --check`, `php -l` and `bash -n` when available. v0.1.2 adds optional Hypothesis and CrossHair providers behind the same `verify` operation. They are explicit, bounded, and never mandatory runtime dependencies. BananaMe does not generate properties or automatically start symbolic execution.

## Independence

BananaMe has no dependency on MangoMe, SPARI, AVCOS or any model/provider. Those systems may call or govern BananaMe externally.

## Research-backed evolution

See [Research Basis](research-basis.md). The next planned internal progression is:

1. optional ast-grep structural provider;
2. cross-language stable symbol identity;
3. content-addressed per-file parse/index cache;
4. import/call/type/test relation graph;
5. symbol/body-hash mutation;
6. impact neighborhoods and semantic diff;
7. adaptive retrieval across exact, lexical, structural, graph and history evidence;
8. controlled A/B/C evaluation against Aider and simpler baselines.

## Shallow BananaMe repository invariant

The shallow-layout convention applies only to **BananaMe's own repository/release artifacts** because some agent/file-transfer paths used by this project are unreliable beyond two generated directory levels. It does not constrain target repositories. Deep target paths are explicitly tested.

`.github/workflows/` is the required infrastructure exception inside BananaMe.
