# Security

BananaMe executes against a caller-selected local workspace and therefore treats repository content as untrusted input.

v0.1 protections:

- workspace-relative paths only;
- resolved paths must remain beneath the workspace root;
- direct `.git` mutation is denied;
- symlink-file mutation is denied;
- binary/non-UTF-8 mutation is denied;
- mutation requires a SHA-256 guard for each target file;
- optional Git HEAD guard detects stale plans;
- SEARCH blocks must match exactly once;
- all edits preflight in memory before filesystem mutation;
- pre-mutation backups and transaction manifests are persisted in `.bananame/`;
- rollback refuses to erase changes made after the transaction;
- verification commands use argv arrays and never `shell=True`;
- Git commit, deployment and external promotion are out of scope.

BananaMe does not claim a complete sandbox. Explicit verification commands run with the invoking process's operating-system privileges. A host requiring stronger isolation should run BananaMe inside its own sandbox/container policy.
