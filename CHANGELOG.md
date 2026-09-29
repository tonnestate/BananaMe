# Changelog

## 0.1.1 — 2026-09-29

Trust, concurrency and crash-recovery hardening over the published v0.1.0 base.

- changed normal mutation concurrency from optional whole-repository HEAD coupling to mandatory target-file guards with optional strict `expected_head`;
- added a short cross-process BananaMe mutation/recovery lock and target-hash revalidation immediately before source writes;
- added `bananame-transaction/2` write-ahead recovery journals, durable before-images, intended after-hashes and explicit interrupted-transaction recovery;
- blocked new mutation while incomplete journals require recovery and added compatibility recovery for interrupted v0.1 transaction/1 journals;
- resolved same-file edits against one original snapshot and reject overlapping edit spans with `EDIT_OVERLAP`;
- added explicit verification states: `VERIFIED`, `PARTIAL`, `NOT_VERIFIED`, `VERIFICATION_FAILED`;
- made inventory, search and context truncation visible instead of silently presenting bounded results as complete;
- made exact/hot files return guarded file evidence within the context budget;
- bound MCP workspaces on the host side through `BANANAME_WORKSPACE_ROOT`;
- clarified that BananaMe's own shallow release layout does not restrict target-repository path depth;
- added scientific design rationale for OCC, crash recovery, compact agent interfaces and the planned structural-intelligence layer;
- expanded the suite to 42 passing tests covering concurrency, recovery, truth states, deep paths, stale HEAD, co-change, binary/UTF-8 rejection and internal-path hardening.

## 0.1.0 — 2026-09-29

Initial BananaMe foundation.

Repository hardening completed before the first public release: MangoMe-style README header/banner, complete capability and implementation description, shallow-layout invariant, packaged Skill at `src/bananame/SKILL.md`, `.gitignore`, CI, and packaging/layout tests.

- established the three-operation AI-facing protocol: `understand`, `mutate`, `verify`;
- added bounded lexical repository localization with ripgrep and deterministic fallback;
- added Python AST symbol localization and body hashes;
- added bounded Git co-change evidence;
- added guarded exact SEARCH/REPLACE mutation with stale HEAD/file detection;
- added ambiguous-match refusal and newline-style preservation;
- added multi-file in-memory preflight and persisted transaction evidence;
- added conflict-safe transaction rollback;
- added syntax verification and explicit argv-only validation commands;
- added CLI, Agent Skill and optional MCP stdio adapter over one core;
- explicitly excludes LLMs, planning, memory, governance, automatic commits and deployment authority.
