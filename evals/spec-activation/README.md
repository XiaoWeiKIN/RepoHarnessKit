# Activation Correctness Baseline (PR-A)

This is an **offline, read-only candidate-retrieval baseline**, not a new Router,
semantic applicability classifier, activation receipt or compliance gate. The
shared production Router and all upstream Specifications remain unchanged.

## Findings and source boundaries

The original itemized evidence behind the **17 missed Requirements / seven
baseline violations** claim has not been located. PR #110 repeats the aggregate
claim but supplies no per-item audit, code snapshot or Catalog/lock pin. These
claims are quarantined in `history.json`; missing evidence is not a zero count,
a negative label or a denominator.

A different original experiment was recovered and integrity-checked: the
November 1 Task 3 policy-selector audit, fixed to Harness `88a7202`, Catalog
`1.9.0` / `b0719f8`, and its original local code baseline and final diff. Its
historical **14 PASS / 4 FAIL / 1 UNVERIFIED / 37 N/A** remain unchanged. It reports
three omitted Requirements, not 17: `SIM-PATH-001`, `SIM-READ-001`, `GO-NAME-001`.
The HTTP Handler experiment and the later upgrade/blocked trials are separate
records, not additional samples of that Task 3 audit.

The current results and failures are preserved in the repository-native
[Benchmark suite](../../benchmarks/suites/b-001_spec-activation-correctness/BENCHMARK.md).
The first attempt timed out and is retained as an errored Run. A subsequent
complete Run must not rewrite it or any previous audit.

## Corpus and annotation contract

`corpus.json` contains 11 constructed controls and one historical replay, over
56 pinned Requirement IDs. Categories cover positive edits, negative generated
code, explicit `none`, same-path/different-intent, zero/nested/sibling globs,
stale/refreshed paths and an ambiguous trust boundary. It records exact task
text, before/after snapshot bytes and hashes, original source locations,
Requirement byte spans and digests, Catalog/lock/index pins, rationale, reviewer
identity and dispute state. No upstream normative document is vendored here.

Each case partitions the universe into `applicable`, `context_only`,
`uncertain`, `not_applicable` and `unreviewed`. Labels were derived from the
pinned Activation/Applicability text and snapshots, **not Router output**.
However, the new controls were labelled by the implementation author and remain
**provisional, pending independent second review**. The historical reviewer was
a separate Work context, non-blind and on a shared filesystem. Neither is
represented as blinded, sandboxed or statistically independent evidence.

Preservation-only historical selections are excluded as disputed direct
applicability rather than silently promoted to ground truth. Changing labels
requires a new frozen measurement; do not edit sealed Benchmark artifacts.
For readable JSON inspection, use `python3 -m json.tool corpus.json`.

## Source-binding validation

Requirement `source_path` is mandatory and must match the upstream source path
for the same Spec in the digest-pinned lock. The evaluator checks this together
with the Requirement ID, owning Spec, byte range and block digest before Router
calls. An unrelated path is not valid merely because a block hash matches.

Schema 1 binds the historical Task 3 case to
`compliance-archive:frozen/final.diff`. The case digest must match the unique
entry for that role in the history registry. This metadata check also runs when
`--audit-archive` is omitted. When the original archive is supplied, its pin,
manifest and actual diff bytes must match as well. Without the archive,
historical revalidation remains `NOT_REVALIDATED`; consistent declarations are
not proof that the original bytes were re-read.

Invalid bindings exit 2 without a complete `observations.json`. A partial output
directory or log is not a completed measurement. The
[source-binding repair record](repairs/20261104-provenance-binding/README.md)
records the regressions without changing the provisional labels or old Runs.

## Reproduce

Use a checkout containing this evaluation and Python 3.10+. No network is used
by the runner. Obtain the original fixture separately, from the fixed public
[benchmark source](https://github.com/XiaoWeiKIN/repoharness-agent-benchmark/tree/73f08883f4cdd17f7aef90f4962f2872a0b9d9a3/fixtures/task3).
The path is `fixtures/task3/initial-B.tar.gz`; verify SHA-256:

```text
4681634fe89b8ba56e46e73d943ded022f86666b476f9209eb847ca203414398
```

From the RepoHarnessKit root, with a new output directory outside the checkout:

```sh
python3 -B evals/spec-activation/baseline.py \
  --fixture /external/initial-B.tar.gz \
  --output /external/new-baseline-run
```

Optional original-history verification requires the separately retained private
archive `repoharness-spec-compliance-88a7202-20261101.zip` (SHA-256
`92446e00a856a86f80403e21ee3c426e9ee0554b26978b12e3765a622b1e1d59`):

```sh
python3 -B evals/spec-activation/baseline.py \
  --fixture /external/initial-B.tar.gz \
  --audit-archive /external/repoharness-spec-compliance-88a7202-20261101.zip \
  --output /external/new-baseline-with-history
```

Without that archive, current candidate measurement still runs and historical
revalidation explicitly reports `NOT_REVALIDATED`. The report does not pretend
that a public hash makes private evidence available. The archive is retained
in the owner's Library and the task's private reproduction bundle; it is not
copied into this public repository. Raw `commands.jsonl` includes normative
Router stdout and temporary absolute paths: keep it private. `observations.json`
contains normalized IDs, counters and source identities, not normative text.

Every case is evaluated in a fresh temporary copy. Only `candidates` and
`requirements` are called, twice, for every returned Spec; gold labels never
select the candidate subset. `_covered` is used only as a pure scope probe, not
as an invocation of full `preflight` or native enforcement. Before/after
inventories must match. Original archives and the source Router are rehashed;
invalid pins and changed inputs abort without a complete observation artifact.
Existing output directories are refused. Exit 0 means a complete measurement,
not a compliance PASS; exit 2 means invalid inputs or execution failure.

## Metric definitions

For **candidate retrieval**, TP is an independently labelled applicable ID
returned among candidate cards; FP is an explicitly not-applicable ID returned;
FN is an applicable ID absent. Micro Recall = TP/(TP+FN), Precision = TP/(TP+FP).
The unit is a case-Requirement pair, counted once, not twice for repeated reads.
Context-only, disputed and unreviewed IDs are excluded and explicitly counted.
Undefined denominators remain null. Constructed and historical origins are
reported separately. These deliberately narrow labels are not population
accuracy estimates; conservative over-inclusion is not an activation failure.

**Current Agent activation Recall/Precision are NOT_MEASURED/null.** The Router
provides candidates and records caller choices; this read-only run neither
creates those choices nor observes a new Coding Agent. Supplying gold IDs to
`activate` and scoring the result would be circular, so it is forbidden here.
Historical selection is re-scored separately using the original resolved IDs
and retrospective labels; it cannot certify pre-edit path coverage or causality.

## Validation and version contract

```sh
python3 -B -m unittest tests.test_activation_baseline -v
python3 -B scripts/check_release.py --base-ref 4c56912785f498232c69722bd6327b92aaed4a04
RF_RELEASE_BASE=4c56912785f498232c69722bd6327b92aaed4a04 python3 -B scripts/check.py
python3 -B engineering-benchmark/scripts/benchctl.py --repo . validate
```

The root tests include real unmodified Router CLI calls over the existing
synthetic test Catalog. Those are plumbing regressions, not replacement gold
labels or the real-Catalog measurement. No Core/Adapter template or version
contract changes are introduced, so no distribution/version bump is required.
New Benchmark records are created and sealed through `benchctl`; prior sealed
records are not edited. Original 17/7 itemization and second-review adjudication
remain explicit follow-up evidence gaps, not automatically satisfied gates.
