# Example: evolving an APM sampling policy boundary

**Illustrative scenario only.** No repository was inspected for this example; paths and actual module names are intentionally not asserted.

## Requirements and invariants

- A shared policy expresses supported sampling semantics across Agent types.
- Java Agent versions may encode the same semantic policy in different remote-config formats.
- Publication failures must be surfaced to the caller; the policy must not report success before the owning persistence/publish contract allows it.
- Unsupported capabilities must have an explicit, testable outcome.

## Two candidate boundaries

**A — Keep adapter logic in the policy service:** simplest initially if only one format is supported; but the domain service learns version-specific keys and may become the recurring edit site for every new Agent.

**B — Semantic policy plus versioned compiler/adapter:** policy service validates domain intent; an adapter maps a stable policy representation into supported Agent-specific remote config. More interfaces and adapter tests, but version-specific decisions can change without altering unrelated policy callers.

Choose B only when variant growth and caller contamination are real constraints, not because more layers look cleaner.

## Change scenarios

| Change | A: predicted effect | B: predicted effect | Required verification |
| --- | --- | --- | --- |
| Add supported Agent version | Policy service and serializer may both change | Adapter and capability tests may change | Mixed-version fixtures, payload contract |
| Unsupported sampling feature | Validation/publish ownership may be ambiguous | Domain validation and adapter rejection must agree | Explicit rejection; no false success |
| Partial publish failure | Domain service may need transport knowledge | Adapter cannot hide failed effects; surface through contract | Fault injection and recovery semantics |

**Counterexample:** If the system deliberately supports exactly one Agent and one format, an adapter layer can increase indirection without isolating any real change. Keep A until requirements or observed changes justify B.

## Example analysis conclusion

`proposed`: Prefer B *if* two or more supported formats already require version-dependent translation. `unknown`: actual repository call sites, current compatibility constraints and effect transaction semantics. **No implementation or tests have been run.** The next verification step is to map real producers/consumers, prototype a change in an isolated workspace, and run contract and failure-path tests with user authorization.
