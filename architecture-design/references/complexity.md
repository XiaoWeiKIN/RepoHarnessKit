# Complexity, boundaries and deep modules

This is a **reasoning lens**, not a mandatory architecture style or a linter. Always start with the consuming project's real requirements and verified constraints.

## Three symptoms to investigate

| Symptom | Observable question | Evidence |
| --- | --- | --- |
| Change amplification | Does one small product change require repeated updates across otherwise unrelated consumers? | Prior changes, imports, call sites, versioned API contracts |
| Cognitive load | Must a caller understand implementation choices outside its owned concern? | API signatures, options, required call ordering, failure paths |
| Unknown unknowns | Can the team reliably locate consumers and predict side effects? | Ownership, hidden global state, runtime registration, test gaps |

A cross-cutting security or protocol migration may legitimately touch many modules. Report that contract, not a false architecture defect.

## Complexity ownership

Track *decisions*, not only files. For each significant concern record:

- Responsibility and owner: which module makes the decision and persists or applies its state?
- External contract: what callers must know and which guarantees they can rely on.
- Internal variability: algorithms, wire formats, versions and coordination deliberately hidden.
- Failure and resource boundaries: who validates input, commits effects, retries, cancels, restores and cleans up?
- Evidence: source/API/test/ADR references or a clearly labelled proposal.

A module should own a cohesive set of decisions it can change together. Avoid using a single "manager" as a destination for unrelated complexity.

## Deep versus shallow modules

Depth is the amount of useful functionality and complexity concealed relative to the conceptual size of the external interface, **not** line count, number of methods or nesting depth.

- A **deep module** supplies a stable contract while absorbing valid implementation choices and failure mechanics.
- A **shallow module** forces callers to coordinate many trivial stages, pass implementation details, or understand hidden preconditions.
- An overly broad "deep" module that owns unrelated concepts is not an improvement: it creates an implicit shared change boundary and dangerous ownership.

Ask: Can callers perform the supported use case without reconstructing internal order, formats, version quirks or side effects? Does hiding those details weaken visibility of safety-critical failure outcomes? Error and lifecycle contracts must remain visible where callers need them.

## Information hiding

Hide changeable design decisions (data representation, cache policy, query plan strategy, provider-specific transport) behind a semantic contract. Hiding source code alone is not information hiding.

Reject a redesign that merely adds a facade while callers still pass all provider options, know the internal steps, or coordinate the same failure modes.

## Abstraction cost

Compare new abstractions to the simplest correct baseline:

1. Which actual change or cognitive dependency does the abstraction remove?
2. Which new interfaces, configurations, adaptation logic, runtime states and tests does it add?
3. Can a small amount of duplication remain without coupling concepts that evolve independently?
4. Is the contract stable for observed consumers, or based only on speculative variants?

No generic score or universal target for number of modules is defensible. Preserve correctness, security, data integrity and explicit compatibility even if they add complexity.
