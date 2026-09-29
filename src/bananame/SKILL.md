---
name: bananame
description: Deterministic AI-to-AI code interface for compact repository understanding, guarded surgical mutation, and verification.
---

# BananaMe Skill

BananaMe is a code interface, not a coding agent. It contains no planner, LLM, memory system, or governance authority.

Use exactly this loop when BananaMe is available:

1. `understand` — obtain current repository evidence and SHA-256 guards with the smallest useful context budget.
2. `mutate` — submit exact SEARCH/REPLACE edits using the hashes returned from the current repository state. Use `expected_head` when Git HEAD must remain fixed.
3. `verify` — validate the resulting transaction with syntax checks and explicit argv-based test/lint commands.

Rules:

- Never invent a file hash. Re-read with `understand` after a stale-file or stale-head failure.
- A SEARCH block must match exactly once. `SEARCH_NOT_FOUND` and `SEARCH_AMBIGUOUS` require new observation, not fuzzy guessing.
- Treat `APPLIED` as mutation evidence only, never as correctness, commit, acceptance, or deployment authority.
- BananaMe never commits automatically. Commit/promotion belongs to the host or governance/control plane.
- Use `mutate(action="rollback", transaction_id=...)` only when the transaction still owns the current post-edit hashes; BananaMe refuses destructive rollback after later edits.
- Keep verification commands explicit argv arrays. Do not wrap commands in a shell.
- Prefer bounded `max_context_bytes`; do not request full-repository dumps.
