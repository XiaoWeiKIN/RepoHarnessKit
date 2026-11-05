# Governed Design review protocol

## Review-ready gate

Review the package as one technical architecture model, not as unrelated
Markdown files or a concern checklist. Before `mark-review-ready`, confirm that
the selected reader can:

1. understand the design outcome, scope, goals, and explicit non-goals;
2. redraw the system context, major boundaries, and dependency direction;
3. follow one to three representative requests, data items, state transitions,
   or resource lifecycles end to end;
4. identify the core abstractions, what each owns, and the invariants they
   establish or preserve;
5. distinguish stable extension points from internal implementation seams;
6. navigate from concepts to the relevant focused document and source evidence;
7. understand meaningful alternatives, open questions, validity conditions,
   and revisit triggers.

Also confirm:

- the summary explains the observable outcome, main tradeoff, and validity
  conditions before implementation detail;
- revision comparisons name a known baseline and explain changed boundaries
  and evidence; absent a baseline, the account describes only the current design;
- diagrams and optional interactive demonstrations match the declared Design
  revision, distinguish assumptions from implementation evidence, and link back
  to the source model; a derived view cannot authorize a Design revision;
- decision-relevant Research findings retain their confidence limits, negative
  evidence, remaining unknowns, and validity conditions;
- proposed ADRs do not authorize a published durable choice;
- every package member answers a distinct reader question, is declared once,
  and matches the manifest byte-for-byte;
- typed Design dependencies are current and acyclic;
- material choices explored with the user are either confirmed Design inputs or
  explicit open questions; provisional preferences are not presented as settled
  invariants;
- migration, verification, operations, security, data, compatibility, failure,
  and recovery details appear only when they materially shape this architecture.

An absent optional concern needs no empty section, placeholder member, or
`Not applicable` prose. If one member merely mirrors a checklist item or repeats
the overview, merge or remove it before review.

## Approval boundary

Approval means one exact revision is coherent and publishable. It does not accept
an ADR, conclude Research, authorize implementation, or approve only selected
members. Specialist reviews may be recorded in prose, but publication remains
atomic. If one member needs its own publication cadence, split it into another
`DD-NNN` before approval.

Never infer approval from “looks good”, `review_ready`, a filled CLI flag, author,
or owner metadata. Run `approve` only after explicit authority for the exact
revision is available and record an auditable `approval_ref`.
