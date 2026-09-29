# Research Basis

BananaMe is intentionally small, but the v0.1.1 hardening choices are not ad-hoc. This note records the research basis for the concurrency, recovery, agent-interface and future repository-intelligence design.

## 1. Optimistic concurrency: validate the write set, not the whole world

Kung and Robinson's optimistic concurrency-control model separates transaction work into read, validation and write phases. The central idea is that long-lived locks are unnecessary when conflicts are uncommon, provided a transaction validates that relevant state has not changed before publishing writes.

BananaMe applies the same principle at repository-mutation granularity:

```text
observe target bytes
      ↓
plan + preflight without a long lock
      ↓
short commit-phase lock
      ↓
revalidate target hashes
      ↓
final compare immediately before each write
      ↓
apply
```

Per-file SHA-256 guards are therefore mandatory mutation guards. `expected_head` remains optional and is reserved for callers that deliberately want a stricter whole-revision constraint.

Reference:

- H. T. Kung and J. T. Robinson, "On Optimistic Methods for Concurrency Control," *ACM Transactions on Database Systems*, 6(2), 213–226, 1981. DOI: 10.1145/319566.319567.

Scope note: BananaMe does not claim database serializability against arbitrary non-cooperating editors. The short process lock coordinates BananaMe writers; target-hash validation detects conflicting target changes. External processes that ignore the lock can still race in a narrow interval, so the guarantee is explicit conflict detection/fail-closed behavior, not a global transactional filesystem.

## 2. Crash consistency: journal before dependent source mutation

Recovery literature consistently separates durable recovery metadata from later data mutation. ARIES is the canonical write-ahead-logging design: recovery information is established before dependent state is allowed to become authoritative. File-system work such as TxFS likewise shows that true multi-file ACID requires explicit transactional filesystem support rather than a sequence of ordinary application writes.

BananaMe v0.1.1 therefore narrows its claim and adds a recovery journal:

```text
before images + intended after hashes
              ↓
        PREPARED journal
              ↓
          APPLYING
              ↓
 atomic per-file writes + progress
              ↓
           APPLIED
```

Recovery classifies each target as known-before, known-after or unknown. Known mixed states are rolled back. All-after is recognized as applied. Unknown current bytes produce `RECOVERY_CONFLICT` and are never overwritten automatically.

References:

- C. Mohan, D. Haderle, B. Lindsay, H. Pirahesh, and P. Schwarz, "ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging," *ACM Transactions on Database Systems*, 17(1), 94–162, 1992. DOI: 10.1145/128765.128770.
- Y. Hu et al., "TxFS: Leveraging File-System Crash Consistency to Provide ACID Transactions," *USENIX ATC 2018*, 879–891.

Design consequence: BananaMe describes v0.1.1 as **crash-recoverable application-level mutation**, not filesystem ACID.

## 3. Concurrency should be target-scoped before it becomes semantic merge

The natural response to parallel coding is not to disable safety checks globally. Research on optimistic concurrency supports validating the actual write set, while recent structured-merge work shows both the benefit and the risk of increasingly aggressive structural reconciliation: structure-aware merge reduces some spurious conflicts, but semantic/structural automation still has correctness boundaries and can miss real conflicts.

References:

- A. Mori and M. Hashimoto, "On the Correctness of Software Merge," arXiv:2607.07987, 2026.
- P. Lopes, P. Borba, P. Accioly, and G. Cavalcanti, "MergirafSemi: A Language-Agnostic Semistructured Merge Tool," arXiv:2608.11345, 2026.

Design consequence: v0.1.1 does **not** introduce autonomous semantic merge. It moves from optional repository-wide guarding to mandatory target-file validation plus a short commit-phase lock. Symbol-/AST-aware rebasing belongs to a later structural milestone and must remain fail-closed when the intended target becomes ambiguous.

## 4. Agent-computer interfaces materially affect coding-agent performance

SWE-agent demonstrates that the interface exposed to a language-model agent materially changes software-engineering performance. BananaMe adopts the same general lesson while keeping a narrower responsibility: expose a compact machine interface instead of a human-oriented coding application.

Reference:

- J. Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering," *NeurIPS 2024*; arXiv:2405.15793.

Design consequence: the public protocol remains:

```text
understand
mutate
verify
```

Internal mechanisms may grow without multiplying host-facing tools.

## 5. Repository localization benefits from structure, but no single retrieval family dominates

Repository-level code graphs improve localization in several recent systems. RepoGraph shows repository-graph gains across multiple SWE systems. LocAgent models files, classes, functions, imports, invocations and inheritance. ARISE extends repository structure to definition-use/data-flow edges and reports better function/line localization and downstream repair in its evaluation.

At the same time, Agent Retrieval Bench reports that lexical retrieval, RepoMap and embedding-based retrieval win different tasks/metrics; no single family dominates across workflows.

References:

- S. Ouyang et al., "RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph," *ICLR 2025*; arXiv:2410.14684.
- Z. Chen et al., "LocAgent: Graph-Guided LLM Agents for Code Localization," arXiv:2503.09089, 2025.
- S. Seddik and F. Fard, "ARISE: A Repository-level Graph Representation and Toolset for Agentic Fault Localization and Program Repair," arXiv:2605.03117, 2026.
- B. Qin and Y. Xie, "Agent Retrieval Bench: Evaluating Repository Context Retrieval for Coding Agents," arXiv:2607.24882, 2026.

Design consequence: v0.2 should add structural/symbol/graph retrieval **adaptively behind `understand`**, not force a monolithic graph pass for every request.

## 6. Structure-aware mutation is a better next step than silent fuzzy text matching

Exact text editing is a deterministic baseline, but raw string selectors are brittle. Research on program transformation and structured merge supports using program structure as the address space for changes instead of merely weakening text matching until something happens to match.

BananaMe therefore keeps exact SEARCH/REPLACE in v0.1.1, resolves all same-file edits against the original snapshot and rejects overlapping spans. The planned next selector layer is symbol-/AST-addressed editing with body/signature guards. Fuzzy replacement is not an automatic fallback.

## 7. Verification must preserve unknowns

A checker that did not run is not positive evidence. v0.1.0 could collapse unsupported-path `SKIP` results into an overall success. v0.1.1 fixes the truth semantics with four states:

```text
VERIFIED
PARTIAL
NOT_VERIFIED
VERIFICATION_FAILED
```

Only `VERIFIED` maps to `ok=true`. This is deliberately conservative: incomplete checker coverage remains visible rather than being converted into a success claim.

## Research-to-code map for v0.1.1

| Research/design principle | BananaMe v0.1.1 mechanism |
|---|---|
| Optimistic validation | per-target SHA-256 revalidation + final compare |
| Avoid long pessimistic locking | short commit/recovery phase lock only |
| Journal-before-data | transaction/2 manifest + durable before-images before source writes |
| Crash recovery | before/after hash classification + explicit `recover` |
| Do not overclaim ACID | recovery semantics documented separately from filesystem ACID |
| Preserve concurrency | `expected_head` optional; target guards mandatory |
| ACI matters | fixed `understand → mutate → verify` surface |
| Preserve epistemic uncertainty | truncation/completeness flags + four verification states |
| Structured edits over fuzzy guessing | original-snapshot span resolution + overlap refusal now; symbol/AST selectors next |
| Retrieval methods are complementary | adaptive structural/graph retrieval deferred to v0.2 behind `understand` |

## 8. v0.1.2: composable falsification instead of an embedded verification framework

Property-based testing and symbolic execution are complementary bug-finding techniques, but they have different cost profiles and neither should silently become BananaMe's authority layer. QuickCheck established the practical value of stating executable properties and generating many inputs automatically; Hypothesis brings this model to Python and supports shrinking counterexamples. Symbolic execution systems such as KLEE demonstrate that solver-guided path exploration can expose failures missed by conventional tests. CrossHair applies symbolic execution to Python contracts and assertions and returns counterexamples when found.

References:

- K. Claessen and J. Hughes, "QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs," ICFP 2000.
- C. Cadar, D. Dunbar, and D. Engler, "KLEE: Unassisted and Automatic Generation of High-Coverage Tests for Complex Systems Programs," OSDI 2008.
- Hypothesis documentation, property-based testing and third-party backends, accessed 2026.
- CrossHair documentation, `crosshair check` counterexample search and bounded analysis, accessed 2026.

Design consequence: BananaMe v0.1.2 composes these mechanisms only when explicitly requested. The runtime core retains zero mandatory third-party dependencies. Existing project properties are preferred; provenance is preserved when a property comes from a specification, owner, project, or agent. A found counterexample is strong falsification evidence. Failure to find one within a bounded run is recorded as such and is never promoted to a universal correctness proof.

The public protocol remains `understand → mutate → verify`; verification technology stays behind `verify`.
