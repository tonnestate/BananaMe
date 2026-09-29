# Architecture

BananaMe sits below coding agents and above repository mechanics.

```text
Agent reasoning / planning / governance
                 │
                 ▼
             BananaMe
                 │
      understand/mutate/verify
                 │
                 ▼
            Repository
```

## Independence

BananaMe has no dependency on MangoMe, SPARI, AVCOS or any model/provider. Those systems may call or govern BananaMe externally.

## Target evolution

v0.1 establishes protocol and safe mutation. Planned internal evolution without expanding the public tool surface:

1. content-addressed per-file parse cache;
2. cross-language symbol identity;
3. typed relation graph (`CALLS`, `IMPORTS`, `IMPLEMENTS`, `USES_TYPE`, `TESTS`, `DATA_FLOWS`);
4. impact neighborhoods and semantic diff;
5. optional ast-grep structural localization/rewrite;
6. adaptive retrieval combining exact, lexical, structural, graph, history and semantic recall;
7. controlled A/B/C evaluation against Aider and simpler baselines.
