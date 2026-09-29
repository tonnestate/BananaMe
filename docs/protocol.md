# AI Protocol

## `understand`

Read-only. Returns repository revision, dirty state, current SHA-256 file guards, bounded localization evidence, symbol evidence where available and historical co-change hints.

## `mutate`

Effectful. Requires guarded edits. A transaction either preflights all proposed edits or performs no source write. It never commits.

Primary failure codes:

- `STALE_HEAD`
- `STALE_FILE`
- `SEARCH_NOT_FOUND`
- `SEARCH_AMBIGUOUS`
- `SYNTAX_PREFLIGHT_FAILED`
- `PATH_ESCAPE`
- `ROLLBACK_CONFLICT`

## `verify`

Read/execute evidence phase. It can syntax-check changed files and execute explicit argv-based commands. A `PASS` is verification evidence only; BananaMe never converts it into commit, deployment or business acceptance.
