# Governed Design examples

## Convert concluded Research into a module package

```text
python3 scripts/designctl.py --repo . init
python3 scripts/designctl.py --repo . new-design \
  --slug umodel-registry --title "UModel registry module" --layout package \
  --research R-004 --adr ADR-021 --owner "Model Platform Owner" --author Codex
python3 scripts/designctl.py --repo . new-member DD-012 \
  --role flow --slug publication-flow --title "Registry publication flow"
python3 scripts/designctl.py --repo . new-member DD-012 \
  --role subsystem --slug registry-core --title "Registry core subsystem"
python3 scripts/designctl.py --repo . sync DD-012
python3 scripts/designctl.py --repo . validate
```

The Agent then writes the Design content. It translates the Synthesis rather
than copying it: supported findings become boundaries and invariants, rejected
hypotheses become forbidden shortcuts, and unknowns become assumptions,
blockers or revisit triggers. Migration, verification, operations and similar
topics become focused documents only when they materially shape this design.

## Create a bounded single-file design without Research

```text
python3 scripts/designctl.py --repo . new-design \
  --slug health-endpoint --title "Health endpoint response contract" \
  --layout single \
  --research-not-required-reason "ADR-009 already fixes the public response contract" \
  --adr ADR-009 --owner "Runtime Owner" --author Codex
```

The reason must explain why investigation cannot change the design input. “Not
needed” is insufficient.

## Split independent subdesigns

Keep API, data, and operational documents inside one package when they share
one owner and approval. Split a reusable identity service into `DD-021` when it
has independent consumers and rollout, then link it with
`--design-dependency uses:DD-021`. Do not copy the identity service package
inside the caller package.
