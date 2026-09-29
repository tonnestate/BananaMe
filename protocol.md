# AI Protocol

BananaMe exposes exactly three host-facing operations. v0.1.2 strengthens their evidence semantics without expanding the surface.

## `understand`

Read-only. Returns repository revision, dirty state, current SHA-256 file guards, bounded localization evidence, exact/hot-file evidence, Python symbol evidence where available, and bounded Git co-change hints.

Completeness is explicit. Relevant fields include:

```text
inventory_returned
inventory_total
inventory_limit
inventory_truncated
search_candidates_seen
search_results_returned
search_truncated
context_bytes
context_budget_bytes
context_truncated
truncation_reasons
```

A bounded result must not be interpreted as a complete repository view when a truncation flag is true.

## `mutate`

Effectful. Requires an `expected_sha256` guard for every target file. `expected_head` is optional and acts as a stricter repository-wide guard when the caller needs it.

Apply semantics:

```text
preflight against observed snapshots
        ↓
resolve every edit against the original file image
        ↓
reject 0 matches / >1 matches / overlapping spans
        ↓
short commit-phase lock
        ↓
revalidate all target hashes
        ↓
journal before-images + intended hashes
        ↓
final compare immediately before each write
        ↓
per-file atomic replacement + progress journal
```

Primary failure/control codes:

- `STALE_HEAD`
- `STALE_FILE`
- `MUTATION_BUSY`
- `SEARCH_NOT_FOUND`
- `SEARCH_AMBIGUOUS`
- `EDIT_OVERLAP`
- `SYNTAX_PREFLIGHT_FAILED`
- `PATH_ESCAPE`
- `ROLLBACK_CONFLICT`
- `RECOVERY_REQUIRED`
- `RECOVERY_CONFLICT`

### `mutate(action="recover")`

Recovery reconciles an interrupted `bananame-transaction/2` journal. Known states are identified by before/after hashes. Mixed known states roll back to the before-image; an all-after state is recognized as applied. Any unknown current hash fails closed.

## `verify`

Read/execute evidence phase. Syntax and explicit argv-based commands are reported separately.

Machine states:

```text
VERIFIED             all requested concrete checks executed and passed
PARTIAL              some checks passed but at least one selected path had no checker
NOT_VERIFIED         no concrete check executed
VERIFICATION_FAILED  at least one executed check failed
```

`ok=true` is reserved for `VERIFIED`. `execution_ok=true` means the verification operation itself completed normally even when evidence is incomplete.

A successful verification is still evidence only; BananaMe never converts it into Git commit, deployment, approval or business acceptance.

## Optional verifier checks (v0.1.2)

`verify` may receive `verifier_checks` without adding more host-facing tools. Supported providers are intentionally small:

```text
hypothesis  execute an explicitly selected property test through pytest
crosshair   execute an explicitly selected CrossHair target
```

Each request carries a property/evidence origin:

```text
PROJECT_EXISTING
OWNER_SUPPLIED
SPEC_DERIVED
AGENT_GENERATED
UNKNOWN
```

Provider outcomes are normalized separately from the top-level verification state:

```text
PASSED
FALSIFIED
INCONCLUSIVE
ERROR
TIMEOUT
NOT_AVAILABLE
```

`FALSIFIED` is negative evidence and forces `VERIFICATION_FAILED`. `INCONCLUSIVE`, `ERROR`, `TIMEOUT`, and `NOT_AVAILABLE` preserve uncertainty and therefore cannot produce a complete `VERIFIED` result. CrossHair `PASSED` means `NO_COUNTEREXAMPLE_FOUND` within the configured budget, not mathematical proof of the whole program.

BananaMe never creates properties automatically and never starts symbolic execution without an explicit verifier request.
