# PR #111 source-binding repair

This patch closes the two evaluator provenance gaps from the
[November 3 review](https://github.com/XiaoWeiKIN/RepoHarnessKit/pull/111#pullrequestreview-5753481111).
It does not change the production Router, normative Specifications, Gold Set
labels, scoring rules, or any sealed Benchmark Run. The PR remains Draft.

## Changed behavior

A Requirement reference must name the upstream source path belonging to the
same Spec in the digest-pinned lock, as well as the correct ID, byte range and
block digest. A valid block hash can no longer hide a wrong source path.

The schema-1 historical case has a fixed role:
`compliance-archive:frozen/final.diff`. Its digest must agree with the unique
history-registry entry for that role. Another registered source cannot replace
the diff. Missing, noncanonical, foreign or inconsistent declarations fail
before measurement. When the optional original archive is supplied, the actual
diff bytes must agree with those declarations, the archive pin and manifest.
Without it, historical status remains `NOT_REVALIDATED`.

The CLI exits 2 on an invalid binding and does not write a complete
`observations.json`. A partial directory or log is not a successful measurement.

## Regression evidence

The parent is `8c5c42a82a8f7cd8472b09ca9e78e18fe0faf264`. The first four-test run
retained one valid control and reproduced three failures: wrong Requirement
source, wrong case diff digest, and nonexistent case diff locator were accepted.
The repaired evaluator passes all 38 tests, including the original 19 and 19
new provenance regressions. These generated fixtures test validation mechanics,
not normative applicability labels.

[Real-source controls](controls.json) use the unchanged original Task 3 fixture
and audit ZIP. Two valid and eleven invalid controls give 6/13 expected outcomes
on the parent and 13/13 on the repair. Three additional real CLI inputs each exit
2, produce no complete artifact, and execute no Router command. Input archives
and temporary subject bytes remain unchanged. Private original payloads are not
published in this directory.

[Validation records](validation.json) bind commands, results and retained-log
digests to the evaluator and test bytes. The canonical result is recorded
separately from focused tests; CI for the new commit is a separate observation.

## Reproduce

From a checkout of this repair:

```sh
python3 -B -m unittest tests.test_activation_baseline -v
python3 -B scripts/check_release.py --base-ref 4c56912785f498232c69722bd6327b92aaed4a04
RF_RELEASE_BASE=4c56912785f498232c69722bd6327b92aaed4a04 python3 -B scripts/check.py
python3 -B engineering-benchmark/scripts/benchctl.py --repo . validate
```

The optional full read-only replay still uses the fixture/archive retrieval
instructions in the [baseline guide](../../README.md). This repair performs
source-binding regressions, not a new full candidate or Agent measurement;
there is no new Recall/Precision claim or semantic Benchmark outcome.

## Preservation and remaining gaps

`corpus.json`, `history.json`, published BR-001/BR-002 and the separately retained
BR-003/BR-004 audit package are not modified or reclassified. The same published
labels remain provisional. The review's 33 disputes and independence limitation
are not resolved by this code patch. Original 17/7 itemization remains
quarantined; no missing evidence becomes zero or a negative label.

No Core/Adapter asset or version plane changes. The evaluator verifies source
consistency under frozen inputs, not authorship, independent review or hostile
concurrent filesystem isolation. This is not approval to merge #111.
