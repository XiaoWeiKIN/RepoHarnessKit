---
schema_version: "1.1"
metadata_schema: "1"
artifact_type: benchmark-scenario
id: "BS-001"
suite_id: "B-001"
title: "Read-only candidate retrieval and scope baseline"
status: "active"
author: "ChatGPT"
owner: "RepoFoundry Maintainer"
created: "2026-11-03"
updated: "2026-11-03"
---

# Read-only candidate retrieval and scope baseline

## Question and Hypothesis

H1: the current Router is a path-derived candidate provider, not a semantic applicability classifier. The format-only and explain-same-go-path controls should return identical candidate IDs despite different source-derived labels. Different IDs falsify this bounded prediction.

H2: the pure scope predicate should cover zero-depth and nested descendants, reject the sibling directory and stale documentation-only plan, then cover the refreshed Go plan. Opposite outcomes falsify this scope prediction; this is not a native write-gate experiment.

H3: two repeated read-only CLI traversals per case should return the same IDs and leave the entire disposable subject byte inventory unchanged. Any drift or unequal IDs invalidates the measurement.

Prior evidence: the November 1 audit reported three omissions and a glob mismatch. These are historical observations, not fresh current-Router results. The later aggregate 17/7 claim lacks itemized original evidence. New control labels were source-reviewed before this run, not inferred from Router output; an independent second reviewer has not adjudicated them.

## Subject, Control, and Variants

Subject: shared Router from main commit 4c56912785f498232c69722bd6327b92aaed4a04, SHA-256 5dae7936f1e259565720ea9b9f23bb7d45265c1d9cc07488481ecaecba5fbf1e. It is executed directly from the source checkout; the old installed Router inside the fixture is not used.

Input: real Task 3 archive at benchmark commit 73f08883f4cdd17f7aef90f4962f2872a0b9d9a3, SHA-256 4681634fe89b8ba56e46e73d943ded022f86666b476f9209eb847ca203414398. Catalog 1.9.0 remains pinned to b0719f806615c0bb4f3d496931f14b6dc29df7e6 with the original lock/index. Corpus stores exact digests and Requirement byte anchors.

Controls: 11 constructed cases plus one archived final-diff-labelled historical replay. The two same-path tasks and two path-expansion tasks are discriminating controls. They are not randomized model trials.

## Variables

Hold Router bytes, Catalog/lock, fixture, Python, command implementation and universe fixed. Vary declared path scope and task intent as recorded in corpus.json. Task text and gold labels are intentionally not fed to the Router CLI: this experiment measures candidate discovery, not an Agent.

Measure candidate IDs, scope predicates, hash inventories and label-confusion counts. Confounders include provisional human-language interpretations, broad Spec scopes, historical retrospective labels, and task-specific coverage; do not attribute differences to model effectiveness.

## Dataset and Traffic Model

Freeze exactly 12 cases over all 56 installed Requirement IDs. Every case partitions IDs into applicable, context_only, uncertain, not_applicable and unreviewed. Store before/after text and hashes for constructed cases; historic source paths and final diff have archive-bound hashes. The original 17 omissions and 7 violations have null IDs/pins and are excluded entirely, not labelled false.

One sequential CLI at a time; no application traffic, business code execution or load generation. Retain private archives and raw normative stdout outside the public repository. Publish only source anchors, derived labels, IDs, counters and digests.

## Environment and Isolation

Local Linux container; capture uname, Python, Git and platform information in the Run artifact. Each case gets a fresh temporary fixture tree; repeated reads share that same tree. No Coding Agent, model API, native Codex Hook, OS security boundary or network service is part of the measurement. Source archives are immutable inputs; this is observational snapshot integrity, not hostile-concurrency protection.

## Procedure and Commands

Before execution, validate the corpus and freeze hashes of corpus.json, history.json, baseline.py, tests and this Scenario. Use benchctl new-run to snapshot the Scenario before measurement.

From the source root:

```sh
python3 -B evals/spec-activation/baseline.py \
  --fixture /external/initial-B.tar.gz \
  --audit-archive /external/repoharness-spec-compliance-88a7202-20261101.zip \
  --output /external/new-baseline-run
```

The runner validates fixture, lock, manifest, index, every Requirement anchor and Router pin, then writes only disposable before-snapshots. For each case it runs candidates and requirements for every returned Spec, twice, in a fixed order, without labels in command input. There is no warmup or timing endpoint. Two repeats test determinism, not independent statistical samples; eight-repeat microbenchmark advice does not apply to this exact-output contract.

Compare all subject bytes before/after. Evaluate actual paths with the shared pure _covered predicate. Recheck frozen inputs and archive payloads. Abort on invalid input or drift; retain failed logs and create a new output directory for retry. Never call begin, activate, rehydrate, classify or event.

## Metrics and Correctness Checks

Primary diagnostic: candidate-retrieval recall TP/(TP+FN), precision TP/(TP+FP), unit case-Requirement pair. Count each case once despite two repeats. Only explicit applicable and not_applicable labels enter binary denominators; report context-only, uncertain and unreviewed exclusions. Report constructed and historical-origin aggregates separately. Undefined denominators are null, not zero or success.

These are provisional label-scoped candidate metrics, not activation accuracy. Current Agent activation Recall/Precision remain NOT_MEASURED/null. Historical activation is a separate archived non-blind measurement using resolved (not merely direct) IDs against the retrospective direct-applicability labels; excluded context and disputed preservation rules remain visible. Do not mix it into current selection metrics.

Check H1-H3 directly, count missing candidate IDs and uncovered paths, preserve unverified semantic obligations. No confidence intervals or significance tests: this is a hand-selected diagnostic corpus, not a population sample or causal experiment.

## Decision Rule

Measurement validity requires all 12 cases, two identical repeats each, valid pins and unchanged subject bytes. H1-H3 can be supported or falsified on these controls. Recall/precision have no predeclared pass threshold because this establishes a baseline, not a semantic selection gate.

The broader activation-correctness conclusion is inconclusive while the original itemized 17/7 evidence, independent second review of new labels, and current Agent-selection observations are unavailable. A valid candidate measurement must not be sealed as proof of full activation or Spec compliance. Errors are retained as errored Runs; revised protocols use a new Scenario.

## Evidence Requirements

Retain complete actual argv/cwd, exit code, stdout/stderr for every CLI in the private commands.jsonl, and expose its digest/byte count plus normalized ID observations publicly. Run artifacts contain the pre-run freeze, environment, observations, provenance search ledger and reproducible report. The manifest seals exact public artifact bytes; private archive hashes are locators, not authentication.

Verify all 409 archived audit payloads against their original manifest before scoring the historical sample. Preserve its 14 PASS / 4 FAIL / 1 UNVERIFIED / 37 N/A verbatim. Keep the unrelated 269-file upgrade validation separate. No independent second-label review or fresh model run can be claimed from these archives.

## Safety, Cleanup, and Recovery

No writes to production Router, upstream Specs, original fixture, audit archives or historical results. Source checkout changes are restricted to evaluation, test and new Benchmark artifacts. Stop on missing/changed pins, malformed labels, unsafe archive paths, command failure, non-determinism or source drift. TemporaryDirectory owns cleanup; completed output directories are never overwritten. Retain failed command output outside the repository and do not delete old sealed Runs.

## Boundaries and Extrapolation

This cannot establish semantic activation correctness, Agent understanding, native interception, complete behavioral compliance, causal improvement or production recall. Candidate over-inclusion is expected from conservative routing, not proof that the Agent activated irrelevant rules. The constructed cases remain provisional, and the original 17/7 claim remains unverified. No publication, deployment, merge or production policy change is authorized by this Run.
