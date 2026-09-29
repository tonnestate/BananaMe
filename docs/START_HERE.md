# Start Here

BananaMe is a headless repository interface for AI coding agents.

It gives an external agent three operations:

```text
understand → mutate → verify
```

BananaMe does not plan the task and does not decide whether a change should be accepted. Its job is narrower: provide bounded repository evidence, apply guarded/recoverable code changes, and return machine-readable verification evidence.

## Mental model

```text
Agent reasoning
      │
      ▼
UNDERSTAND
observe current target state + completeness flags
      │
      ▼
Agent proposes exact edits
      │
      ▼
MUTATE
preflight → short lock → revalidate → journal → write
      │
      ▼
VERIFY
syntax + explicit tests/linters + evidence state
      │
      ▼
Host/governance decides what happens next
```

## First workflow

### 1. Observe

```bash
bananame --workspace . understand --query "authentication token expiry"
```

Use the returned target-file SHA-256 values. Inspect `inventory_truncated`, `search_truncated`, `context_truncated`, and `truncation_reasons` before treating the result as complete.

`head_revision` is also returned, but the repository-wide HEAD guard is optional. Use it only when the task requires the whole Git revision to stay fixed.

### 2. Mutate

Create exact SEARCH/REPLACE edits using the state you just observed.

```json
[
  {
    "path": "src/auth.py",
    "search": "def valid(token):\n    return False\n",
    "replace": "def valid(token):\n    return bool(token)\n",
    "expected_sha256": "<current hash>"
  }
]
```

Target-scoped mutation (normal mode):

```bash
bananame --workspace . mutate \
  --edits-json '<json-array>'
```

Strict whole-repository guard when required:

```bash
bananame --workspace . mutate \
  --expected-head <current-head> \
  --edits-json '<json-array>'
```

BananaMe resolves every proposed edit against the same original file snapshot, rejects overlaps, acquires a short commit-phase lock, revalidates target hashes, journals recovery state, and only then writes.

### 3. Verify

```bash
bananame --workspace . verify \
  --transaction-id <transaction-id> \
  --command-json '["python","-m","pytest","-q"]'
```

Interpret the status literally:

```text
VERIFIED             requested concrete checks passed
PARTIAL              some evidence exists but selected paths remain unchecked
NOT_VERIFIED         no concrete check executed
VERIFICATION_FAILED  at least one concrete check failed
```

Only `VERIFIED` produces `ok=true`. None of these states is a Git commit, deployment approval or business acceptance.

## Interrupted mutation recovery

v0.1.1 journals before/after hashes and per-file progress before source writes. If a previous process died during the write phase, a new mutation returns `RECOVERY_REQUIRED` until the transaction is reconciled.

```bash
bananame --workspace . mutate --recover <transaction-id>
```

Recovery never guesses. A file must match either the journaled before-image or intended after-image. Anything else yields `RECOVERY_CONFLICT` and remains untouched.

## Common control signals

```text
STALE_HEAD              → optional strict HEAD guard failed
STALE_FILE              → target bytes changed; observe again
MUTATION_BUSY            → another BananaMe commit/recovery phase owns the short lock
SEARCH_NOT_FOUND         → assumption does not match observed source
SEARCH_AMBIGUOUS         → proposed target is not unique
EDIT_OVERLAP             → same-file proposed spans overlap
SYNTAX_PREFLIGHT_FAILED  → proposed result is syntactically invalid
RECOVERY_REQUIRED        → reconcile an interrupted transaction first
RECOVERY_CONFLICT        → current bytes match neither journaled before nor after state
ROLLBACK_CONFLICT        → later work exists; rollback is refused
```

## Deep target paths are supported

The shallow-layout convention documented for BananaMe applies only to BananaMe's own release repository. Target repositories may be arbitrarily deep, for example:

```text
src/main/java/com/company/product/auth/AuthService.java
```

## Where state is stored

BananaMe stores only local transaction/lock evidence under `.bananame/`. This is not long-term agent memory. Persistent workflow state belongs to the host or a separate system such as MangoMe.
