# Detailed design review

Review engineering risk before prose quality. Group repeated symptoms under one root finding.
Use [controlled technical writing](controlled-writing.md) as the shared editorial
baseline, including project precedence and language, state, and authority safeguards.
Use this review for drafts and revisions as well as explicit review requests.
An explicit review-only request produces findings, not file modifications.

## Finding format

```text
Finding
Severity: blocker / high / medium / low
Claim or location
Why the design is incomplete or inconsistent
Concrete failure mode
Recommended design change
Verification needed
```

## Review lenses

- Mental model: no coherent end-to-end explanation, or the document is only a directory/type inventory.
- Fact ownership: a normative fact has multiple owners, no owner, or is delegated without a stable reference.
- Boundaries: parser/analyzer/planner/runtime, logical/physical, product/core, or transport/domain responsibilities overlap.
- State and lifetime: mutable aliases, multiple writers, invalidation, cleanup, retry, cancellation or recovery are undefined.
- Illegal states: nil/empty/zero, mutually exclusive fields, defaults or open containers have ambiguous semantics.
- Evolution: compatibility surface, activation gate, versioning, mixed-version behavior or exhaustive consumers are missing.
- Verification: a strong claim has only examples, no negative case, no failure injection or no measurable workload.
- Freshness: code links do not support the prose, target/current behavior is mixed, or no owner can detect drift.

For architecture documentation, also check that a contributor can follow a real request/data/state flow and then reach the relevant implementation without first reverse-engineering the repository.

Check the reading path by asking whether the intended reader can explain the
observable behavior, identify a failure or invalidating condition, and locate
the supporting evidence. A concise summary or polished diagram is not sufficient
if it hides those boundaries. Compare revisions only against an identified
baseline, and distinguish a demonstration's assumptions from observed behavior.

## Reader-task walkthrough

Start with one task the intended reader must understand or perform, not a word
count. Check that the opening establishes the model or answer, prerequisites
precede dependent details, and transitions preserve causal reasoning. A reader
should reach the relevant source or test after the conceptual explanation.

When examples contain procedures, check environment, purpose, placeholders,
ordering, expected output, and stop conditions against evidence. Mark unexecuted
examples as untested. Do not run destructive or external commands just to review
their wording. Preserve normative keywords, qualifications, and proposal status
when suggesting tense or sentence changes.

Inspect headings and links as a navigation route, respecting required headings
and stable anchors. For diagrams and requested media, follow the shared
accessibility guidance: check the equivalent text explanation, non-color status,
keyboard paths, and captions, transcript, or content description as applicable.
Test the rendered view when available; otherwise identify the unchecked behavior.

Separate editorial suggestions from factual or design defects. For a wording
issue, describe the reader's concrete misunderstanding and a local correction;
do not call an optional style preference a blocker. Missing evidence, unsafe
instructions, or an inaccessible required task can have substantive impact, but
neither a checklist nor a readable paragraph proves correctness or certification.
Do not invent a uniform compliance score or new approval gate.
