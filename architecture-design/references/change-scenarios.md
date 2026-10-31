# Change scenario analysis

Use a *counterfactual change* to make architecture claims falsifiable. Do not pretend the change was executed when it was only traced.

## Choose scenarios

Select two or three relevant changes grounded in requirements, committed roadmaps, observed incidents or explicit user hypotheses. Include one adversarial condition (e.g. partial publish failure, mixed Agent versions, concurrent requests, cancellation or rollback). Do not invent a future requirement merely to justify a framework.

Examples: add a supported Agent type; change a storage adapter without altering query semantics; add a sampling policy that must keep backward compatibility.

## Trace current and proposed impact

For each scenario:

1. State the trigger, supported behavior and invariants that must not change.
2. Enumerate entrypoints, call sites, shared contracts, owned data/state and effect boundaries by source location. Mark non-inspected surfaces as unknown.
3. Identify *semantic* changes, not just anticipated edited files: who must learn a new rule, translate a provider detail or coordinate a transition?
4. Repeat for the simplest correct candidate and up to two credible alternatives.
5. List verification needed: compile-time interface/call-site check, contract test, fault injection, compatibility test, benchmark for performance claims, or migration rehearsal.
6. Look for a counterexample that would invalidate the recommended boundary. Reconsider the decision if the counterexample contradicts it.

## Evidence table (optional)

| Scenario | Baseline affected owners | Candidate affected owners | Public contract impact | New indirection and risk | Evidence status |
| --- | --- | --- | --- | --- | --- |
| Add supported variant | Verified call sites or unknown | Derived estimate | Breaks / compatible / unknown | Added wrappers, migration, runtime states | observed / derived / unknown |

Counts of files and static fan-out are diagnostic, not architecture quality scores. A change in ten files can be appropriate for a public contract migration; a one-file change can conceal unsafe global coupling. Where a scenario has not been implemented, say "predicted impact" and report the untested assumptions.

## Decision rules

- Prefer the simplest design that satisfies documented behavior and binding constraints.
- Introduce a boundary only where it hides a real changeable decision, stabilizes a contract or meaningfully constrains a failure mode.
- State migration/compatibility costs and avoid speculative extensibility.
- If existing design already isolates the scenario, record "keep as-is" rather than proposing a cosmetic abstraction.
- Never change production configuration, test fixtures, protected decisions or deploy solely to gather review evidence without authorization.
