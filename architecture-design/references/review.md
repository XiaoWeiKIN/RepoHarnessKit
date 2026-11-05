# Architecture decision and review protocol

Architecture review evaluates concrete behavior and changes, **not** prose style, package aesthetics or compliance with a preferred pattern.

## Evidence hierarchy

Read affected code and tests, then current accepted ADRs and pinned Specifications; reconcile rather than silently choose one. Label each claim `observed`, `decided`, `proposed`, `derived` or `unknown`. Source links and revisions are necessary for claims about a repository. A user's example without a checkout is a hypothesis, not verified source evidence.

## Review in risk order

1. Correctness, security, durable state, concurrency, failure and compatibility boundaries.
2. Ownership of domain decisions, data and resources; accidental coupling and hidden order dependencies.
3. Interface depth, implementation leakage, change propagation and cognitive cost.
4. Testability, migration impact, rollback and evidence needed to select a design.

Avoid these false positives:
- More files or interfaces alone prove bad architecture.
- A small function or interface is automatically shallow and harmful.
- A single public interface is automatically better than explicit steps with different effects.
- All duplicated code should be centralized.
- All errors must be hidden by a facade.
- Multiple modules changing during an intentional protocol revision necessarily indicates poor design.

## Design options

For a consequential choice, compare current/simplest correct design and at least one credible alternative. List what changes for callers, what moves inside the boundary, invariants and failure contracts, new coupling/indirection, migration cost and a falsifying scenario. Reject a proposed general framework if its only motivation is hypothetical reuse.

## Findings format

Use only fields that provide a concrete decision:

```text
Finding: [severity] [short title]
Status: observed / derived / proposed / unknown
Evidence: path:line, test, or accepted contract (with revision)
Mechanism: where complexity leaks or where an invariant can fail
Scenario: a grounded change/failure that exposes the issue
Impact: what real consumer or guarantee is affected
Alternatives: keep as-is vs bounded improvement; costs and trade-offs
Verification: an executable test/prototype/review action and expected observation
```

`blocker` requires evidence of a violated binding safety, correctness or compatibility contract, not aesthetic disagreement. `high` marks a material probable risk with traceable impact; `medium/low` are improvements with explicit costs. Unknown impact is an uncertainty, not a severity promotion.

## Deliverable boundaries

Return concise findings for a review-only request; do not rewrite architecture documents or code. For a design request, return boundary/contract and trade-off decisions before any optional diagram. A new approved or governed DD is owned by `engineering-design`; a document explanation by `detailed-design`; ADR/EP authority by `engineering-execution-plan`. An executed command or measured claim requires actual execution evidence with target revision, not a hypothetical check plan.
