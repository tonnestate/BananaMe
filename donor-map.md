# Donor Map

BananaMe is not an Aider fork. It is a reuse-first composition target.

| Area | Primary donor/prior art | BananaMe delta |
|---|---|---|
| Exact editing | Aider / agentpatch | hash guards, transaction evidence, conflict-safe rollback |
| Structural search/rewrite | ast-grep | unified AI-facing protocol |
| Repository graph | Entire Graph / RepoGraph / LocAgent | incremental dirty-delta graph target |
| Agent interface | SWE-agent | only three public operations |
| Indexing | Continue / Entire Graph | content-addressed per-file invalidation target |
| Verification | existing language tools | machine-readable evidence without promotion authority |

v0.1.1 intentionally implements only the smallest safe subset required to freeze the protocol before heavier graph machinery is selected.


Research references for the next intelligence layer include RepoGraph, LocAgent, ARISE, Repository Intelligence Graph, Repository Memory and Agent Retrieval Bench. See `research-basis.md`.
