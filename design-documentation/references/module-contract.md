# Module and implementation-contract method

Use this reference when the document must constrain implementation rather than only explain the system.

## Select concerns by module type

| Profile | High-value concerns |
|---|---|
| compiler / parser / query / IR | syntax-semantic boundaries, taxonomy rules, typing, rewrite legality, diagnostics, canonicalization, exhaustive handling |
| scheduler / runtime | lifecycle, queues, fairness, backpressure, resource accounting, cancellation, retry, shutdown |
| storage | logical/physical model, transaction path, consistency, durability, recovery, compaction, format evolution |
| protocol / API | wire model, versioning, presence/defaults, ordering, idempotency, errors, mixed-version rollout |
| execution engine | plan/operator model, pipelines, scheduling, memory ownership, cancellation, spill and partial failure |
| telemetry pipeline | signal model, batching, queueing, temporality, loss/retry, cardinality and self-observability |

Use only applicable concerns.

## Contract construction

1. State facts owned by this document and facts delegated elsewhere.
2. Define classification or admission rules before enumerating current members.
3. Identify creation, mutation, sharing, persistence, invalidation and destruction ownership.
4. Separate structural validation from semantic, environment-dependent, physical and runtime validation.
5. Remove representable illegal states where justified; otherwise name the rejecting owner and verification.
6. Specify representative success and failure flows, including state changes and partial effects.
7. Define compatibility surfaces and the gate for extending closed categories, schemas, protocols or persisted formats.
8. Map strong claims to observable verification.

For important entities, selectively cover semantic responsibility, structure, legal positions, construction and semantic invariants, lifetime, identity/canonicalization, failure behavior, evolution rule and verification. Do not repeat this list mechanically for every type.

## Useful matrices

Ownership:

| Fact or invariant | Established by | Rechecked by | Must not be decided by |
|---|---|---|---|

Failure:

| Failure | Detected by | State changed | Retry/cleanup/recovery | Diagnostic |
|---|---|---|---|---|

Verification:

| Design claim | Verification mechanism | Regression caught |
|---|---|---|

Prefer exhaustive, property, differential, fault-injection or migration tests when example unit tests cannot establish the claim.
