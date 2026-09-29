# Contributing

BananaMe is intentionally small. Contributions should preserve the public AI-facing surface:

```text
understand
mutate
verify
```

Prefer reuse of proven libraries and tools over new internal frameworks. New dependencies must have a clear runtime benefit and a compatible license.

Core invariants:

- no embedded LLM, planner, autonomous agent loop or model router;
- observation, mutation and verification remain separate operations;
- mutation is guarded by current repository/file state and fails closed on ambiguity;
- verification never implies commit, deployment, acceptance or independent assurance;
- repository writes must remain workspace-confined and transactionally recoverable;
- machine-readable evidence is preferred over prose-only output.

Before opening a pull request, run:

```bash
python -m pip install -e '.[dev]'
python -m compileall -q src
pytest
```

If a contribution directly reuses third-party source code rather than only a concept or public interface, update `THIRD_PARTY_NOTICES.md` and preserve all license obligations.
