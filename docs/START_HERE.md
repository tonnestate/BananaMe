# Start Here

BananaMe is a headless repository interface for AI coding agents.

It gives an external agent three operations:

```text
understand → mutate → verify
```

BananaMe does not plan the task and does not decide whether a change should be accepted. Its job is narrower: provide bounded repository evidence, apply guarded code changes, and return machine-readable verification evidence.

## Mental model

```text
Agent reasoning
      │
      ▼
UNDERSTAND
observe the current repository state
      │
      ▼
Agent proposes exact edits
      │
      ▼
MUTATE
validate guards, preflight every edit, write transactionally
      │
      ▼
VERIFY
syntax + explicit tests/linters
      │
      ▼
Host/governance decides what happens next
```

## First workflow

### 1. Observe

```bash
bananame --workspace . understand --query "authentication token expiry"
```

Use the returned Git HEAD and target-file SHA-256 values. Do not invent or reuse stale hashes.

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

Then apply them against the observed HEAD:

```bash
bananame --workspace . mutate \
  --expected-head <current-head> \
  --edits-json '<json-array>'
```

BananaMe resolves every proposed edit before writing. A missing, ambiguous or stale target fails closed.

### 3. Verify

```bash
bananame --workspace . verify \
  --transaction-id <transaction-id> \
  --command-json '["python","-m","pytest","-q"]'
```

`VERIFIED` means the selected checks passed. It is not a Git commit, deployment approval or business acceptance.

## What happens on failure?

The common recoverable failures are intentional control signals:

```text
STALE_HEAD         → repository revision changed; observe again
STALE_FILE         → file changed; observe again
SEARCH_NOT_FOUND   → assumption does not match current source
SEARCH_AMBIGUOUS   → proposed target is not unique
SYNTAX_PREFLIGHT_FAILED → proposed result is syntactically invalid
ROLLBACK_CONFLICT  → later work exists; rollback is refused
```

The expected response to stale or contradictory state is renewed observation, not guesswork.

## Where state is stored

BananaMe stores only local transaction evidence under:

```text
.bananame/transactions/<transaction-id>/
```

This includes the manifest, before-images and unified diff needed for inspectable rollback behavior.

BananaMe has no long-term agent memory. Persistent workflow state belongs to the host or a separate system such as MangoMe.
