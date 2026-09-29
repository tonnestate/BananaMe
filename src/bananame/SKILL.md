---
name: bananame
description: Deterministic AI-to-AI code interface for bounded repository understanding, guarded recoverable mutation, and verification evidence.
---

# BananaMe Skill

BananaMe is a code interface, not a coding agent. It contains no planner, LLM, memory system, governance authority, commit policy or deployment authority.

Use exactly this loop when BananaMe is available:

1. `understand` — obtain current repository evidence and SHA-256 guards with the smallest useful context budget. Inspect truncation flags before treating the result as complete.
2. `mutate` — submit exact SEARCH/REPLACE edits using the current target hashes. `expected_head` is optional and should be used only when the whole Git revision must remain fixed.
3. `verify` — validate the resulting transaction with syntax checks and explicit argv-based test/lint commands.

Rules:

- Never invent a file hash. Re-read with `understand` after `STALE_FILE` or `STALE_HEAD`.
- A SEARCH block must match exactly once against the observed pre-image. `SEARCH_NOT_FOUND`, `SEARCH_AMBIGUOUS`, and `EDIT_OVERLAP` require a new or better-grounded edit, not fuzzy guessing.
- Treat `MUTATION_BUSY` as short-lived commit/recovery contention; do not bypass the lock.
- If `RECOVERY_REQUIRED` is returned, recover the listed transaction before starting another mutation. Use `mutate(action="recover", transaction_id=...)`.
- Treat `APPLIED` as mutation evidence only, never as correctness, commit, acceptance, or deployment authority.
- Treat verification states literally: only `VERIFIED` is complete positive evidence; `PARTIAL` and `NOT_VERIFIED` preserve missing-check uncertainty.
- BananaMe never commits automatically. Commit/promotion belongs to the host or governance/control plane.
- Use `mutate(action="rollback", transaction_id=...)` only when BananaMe still owns the current post-edit hashes; later work must never be erased.
- Keep verification commands explicit argv arrays. Do not wrap commands in a shell.
- Prefer bounded `max_context_bytes`; do not request full-repository dumps.
- If `inventory_truncated`, `search_truncated`, or `context_truncated` is true, do not claim repository completeness.
