# Security

BananaMe executes against a caller-selected local workspace and therefore treats repository content as untrusted input.

## v0.1.1 protections

- workspace-relative paths only;
- resolved paths must remain beneath the workspace root;
- direct `.git` mutation is denied;
- `.bananame` internal state is confined and internal symlinks are rejected;
- symlink-file mutation is denied;
- binary/non-UTF-8 mutation is denied;
- mutation requires a SHA-256 guard for each target file;
- optional Git HEAD guarding is available for callers that require strict whole-revision stability;
- normal mutation is target-scoped: targets are revalidated under a short cross-process commit/recovery lock and again immediately before each write;
- SEARCH blocks must match exactly once against the observed pre-image;
- same-file edit spans are resolved against one original snapshot and overlapping spans are rejected;
- all edits preflight in memory before filesystem mutation;
- before-images and intended after-hashes are durably journaled before source writes;
- interrupted transactions block subsequent mutation until explicitly recovered;
- recovery refuses to overwrite bytes that match neither the journaled before nor intended after state;
- rollback refuses to erase changes made after the transaction;
- verification commands use argv arrays and never `shell=True`;
- MCP workspaces are host-bound through `BANANAME_WORKSPACE_ROOT` instead of being agent-selected per tool call;
- Git commit, deployment and external promotion are out of scope.

## Limits of the guarantee

BananaMe does not claim a complete sandbox, filesystem-wide ACID semantics, or serializability against arbitrary external processes. The mutation lock coordinates BananaMe writers only. A non-cooperating editor can still race with BananaMe in a narrow interval; target-hash checks and recovery are designed to detect/refuse conflicting state rather than silently merge it.

Explicit verification commands run with the invoking process's operating-system privileges. A host requiring stronger isolation should run BananaMe inside its own sandbox/container policy.
