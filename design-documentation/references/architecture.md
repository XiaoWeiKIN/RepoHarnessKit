# Architecture documentation method

Use this reference for system architecture, internals, contributor architecture, and subsystem-overview documents.

## Start from the reader

Apply [controlled technical writing](controlled-writing.md) for shared editorial
rules; this reference adds architecture-specific methods rather than another style
policy. Choose the primary reader before choosing sections:

| Reader | Needs first |
|---|---|
| library or platform user | capabilities, stable abstractions, extension points |
| contributor | end-to-end flow, boundaries, code map, safe change points |
| maintainer | ownership, invariants, failure behavior, evolution pressure |
| reviewer | selected shape, alternatives, risks, verification |

If audiences need incompatible detail, keep one overview and link focused deep dives. Do not interleave beginner orientation with implementation minutiae.

Before drafting, state the reader's existing knowledge and intended outcome in
working notes. For example: "A new contributor knows Go but not this planner;
after reading, they can trace one query and locate the test for a rewrite rule."
This is an illustrative reader task, not a claim about the target repository.
Use known context without requiring a separate audience document or form.

## Scale to a documentation set only when needed

One focused Markdown document is the default. When a topic has genuinely
independent reader routes or separately maintained deep dives, use this
Technical Architecture Docs vocabulary selectively:

```text
README.md
how-it-works/
core-concepts/
subsystems/
extension-points/
deep-dives/
contributor-guide/
```

`README.md` owns the overview and reading routes. A directory exists only when
it contains a useful document. Do not create top-level `contracts/`, `data/`,
`operations/`, `migration/`, or `verification/` buckets to mirror a review
checklist; cover those topics inside the architecture document they materially
affect.

## Choose a narrative spine

Prefer one dominant spine:

- request/query lifecycle;
- data flow and transformation stages;
- control-plane lifecycle;
- state/resource lifecycle;
- subsystem composition.

For a query engine, a useful spine may be:

```text
input -> parse -> analyze -> logical plan -> optimize -> physical plan -> execute -> result
```

For each stage state its input, output, owner, facts established, facts deliberately deferred, and failure boundary.

## Build progressive disclosure

A strong architecture document usually moves through:

1. purpose, audience, goals and non-goals;
2. one-page system model;
3. representative end-to-end flows;
4. core abstractions and responsibility boundaries;
5. state, data, runtime or deployment model where material;
6. extension and integration points;
7. failure, resource, security or compatibility constraints that shape the architecture;
8. code map and links to focused deep dives;
9. freshness owner or observable guards when drift is likely.

This is an ordering heuristic, not a required outline. Remove sections that do not help the selected reader.

Use concrete subjects and consistent names; preserve preconditions, exceptions,
and the distinction between current and proposed behavior. On revision, explain
the material change against a known source version before repeating stable
background. If no comparison is available, state the current model.

Choose representations by the question: diagrams for relationships, tables
for comparable alternatives, and optional interactive views for parameter or
failure exploration. State a demonstration's assumptions and source version;
simulation does not prove implementation behavior. Recheck derived views when
their sources change, keeping the document's existing fact owners authoritative.

## Walk through one example

Choose one supported request, input, or failure and follow it through the model.
Introduce unfamiliar terms before using them to explain an invariant. Connect
each transition to its cause and consequence instead of listing components.
Place source and test links near the claims they support; keep the code map last.

For a runnable example, apply the shared procedure guidance: identify its context,
inputs, placeholders, expected observations, and failure branch. Distinguish
observed results from illustrative output. If execution is unavailable or outside
authority, report that limitation rather than claiming the example passed.

Explain a diagram's important relationships in adjacent text. A contributor must
still be able to trace the example without the image, animation, or color. Link
optional views to the same facts and identify assumptions rather than letting a
simulation establish implementation behavior.

## Explain abstractions through behavior

For each core abstraction, answer:

- Why does it exist?
- What does it own and explicitly not own?
- What enters and leaves it?
- Which invariant does it establish or preserve?
- How does it compose or extend?
- Which concrete type, module, test, or API proves the description?

Do not lead with a package tree. A code map is useful only after the reader understands the concepts it maps.

## Maintain the current explanation

When an authorized implementation change invalidates the walkthrough, update its
current documentation and examples together or identify the documentation gap.
Keep the historical rationale separate: link accepted decisions without editing
their history. Follow the project's existing owner and revision process; do not
create another manual source of truth or a mandatory freshness field.

## Architecture review questions

- Can a reader redraw the system after the overview?
- Can they trace a real request, datum, state transition, or resource through it?
- Are logical, physical, transport, runtime, and product concerns separated?
- Are extension points distinguished from internal implementation seams?
- Are examples clearly examples rather than normative owners?
- Do source links support the claim, and is likely drift visible?
- Can the intended reader explain the walkthrough without images or color?
- Are example commands verified or explicitly untested, and can the reader distinguish current behavior from historical rationale?


## Optional architecture reading view

A completed architecture explanation can have a disposable offline HTML reading
view when the user asks for a visual or interactive surface. The Markdown/design
artifact and its inspected sources remain the fact owners. Do not generate HTML
merely to satisfy this guide.

The renderer accepts an explicit source-bound JSON document with schema
`repofoundry.architecture-explanation/v1`. The authoring step must supply the
subject, language, source repository/revision, an explicit source-file list with
per-file digests, components, flows, invariants, limitations, and evidence locators.
The renderer recomputes the source-set SHA-256 from that list. The renderer does not inspect a
repository, infer architecture, convert arbitrary Markdown, or add claims.

From a full RepoFoundry checkout, preview the output inventory before writing:

```bash
python3 -B scripts/explain_architecture.py \
  --input architecture-explanation.json \
  --output /tmp/architecture-view
```

Add `--apply` only when the destination is new and the derived view is wanted.
The output is a self-contained offline `index.html`, the exact input
`architecture.json`, and a render manifest with hashes. The view has
`authority=none`; it is not approval evidence and does not replace the source
document. Keep limitations visible in the input so the HTML cannot present an
unverified behavior as a measured result.
