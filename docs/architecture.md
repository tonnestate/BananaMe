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
2. guarded transactional source mutation;
3. machine-readable verification evidence.

BananaMe explicitly does not own:

- task planning;
- model inference or routing;
- long-term agent memory;
- work-item/state-machine governance;
- Git commit policy;
- deployment policy;
- acceptance or independent assurance.

This keeps BananaMe usable by MangoMe, SPARI, Claude Code, Codex, Copilot, OpenHands or another host without embedding any of them.

## v0.1 component map

```text
src/bananame/
├── core.py        # stable three-operation facade + machine-readable failures
├── understand.py  # repository observation/localization
├── mutate.py      # guarded edit transaction + rollback
├── verify.py      # syntax and explicit command evidence
├── workspace.py   # path confinement, snapshots, atomic writes
├── git.py         # HEAD, dirty state, inventory, co-change history
├── cli.py         # JSON CLI adapter
└── mcp_server.py  # optional MCP adapter
```

## UNDERSTAND

The current read-side pipeline is:

```text
workspace
   │
   ├─ Git HEAD / dirty state
   ├─ tracked + untracked inventory
   ├─ ripgrep lexical localization
   │    └─ deterministic Python fallback when rg is absent
   ├─ hot-file inclusion
   ├─ SHA-256 source guards
   ├─ Python AST symbol extraction
   │    ├─ class/function/method
   │    ├─ qualified name
   │    └─ body hash
   ├─ bounded source context
   └─ bounded Git co-change evidence
```

The output is bounded by `max_context_bytes` and `max_results` so repository understanding does not become an uncontrolled context dump.

## MUTATE

The current write-side pipeline is:

```text
request
  │
  ├─ workspace confinement
  ├─ optional expected Git HEAD guard
  ├─ per-file SHA-256 guard
  ├─ exact unique SEARCH resolution
  ├─ newline adaptation
  ├─ construct every changed file in memory
  ├─ syntax preflight
  ├─ persist transaction manifest + before-images + diff
  ├─ atomic per-file replacement
  └─ restore already-written files if the write phase fails
```

The preflight is all-or-nothing with respect to source mutation: no source write occurs until every proposed edit has resolved and passed preflight.

The subsequent write phase uses atomic replacement per file. If a later file write fails, files already written by the transaction are restored from their captured before-images.

## ROLLBACK

Rollback is hash-owned rather than Git-reset-based.

For each changed file BananaMe compares the current SHA-256 against the transaction's recorded `after_hash`.

If every file is still owned by the transaction, the captured before-image may be restored. If any file differs, rollback fails with `ROLLBACK_CONFLICT` and leaves the repository untouched.

This prevents a stale rollback from destroying later human or agent work.

## VERIFY

Verification is a separate evidence phase.

Built-in parsers/checkers in v0.1:

```text
.py          python compile()
.json        json.loads()
.toml        tomllib.loads()
.xml/.svg    xml.etree.ElementTree
```

Optional local runtime checks when executables exist:

```text
.js/.mjs/.cjs   node --check
.php            php -l
.sh/.bash       bash -n
```

The caller may also provide explicit argv commands. BananaMe resolves the executable, applies a bounded timeout and captures bounded stdout/stderr. Shell strings are rejected and `shell=True` is not used.

## Transaction evidence

Every successful mutation has a transaction directory:

```text
.bananame/transactions/<id>/
├── manifest.json
├── diff.patch
└── before/
```

This is local derived state. It is not agent memory and is not a governance ledger.

## Independence

BananaMe has no dependency on MangoMe, SPARI, AVCOS or any model/provider. Those systems may call or govern BananaMe externally.

The intended authority relationship is:

```text
host decides whether an effect is allowed
           ↓
BananaMe performs guarded repository mechanics
           ↓
BananaMe returns evidence
           ↓
host decides whether evidence permits promotion
```

## Target evolution

v0.1 establishes protocol and safe mutation. Planned internal evolution without expanding the public tool surface:

1. content-addressed per-file parse cache;
2. cross-language stable symbol identity;
3. typed relation graph (`CALLS`, `IMPORTS`, `IMPLEMENTS`, `USES_TYPE`, `TESTS`, `DATA_FLOWS`);
4. dirty-delta graph over the current working tree;
5. impact neighborhoods and semantic diff;
6. optional ast-grep structural localization/rewrite;
7. adaptive retrieval combining exact, lexical, structural, graph, history and semantic recall;
8. controlled A/B/C evaluation against Aider and simpler baselines.

## Shallow repository invariant

BananaMe deliberately avoids deep directory trees because several agent/file-transfer paths become unreliable beyond two directory levels. Ordinary project files therefore stay at directory depth <= 2. The required `.github/workflows/` path is the only infrastructure exception. The packaged Agent Skill is stored directly at `src/bananame/SKILL.md`; the repository mirror remains `skill/SKILL.md`.
