---
schema_version: "1.1"
metadata_schema: "1"
artifact_type: benchmark-result
id: "BR-002"
suite_id: "B-001"
scenario_id: "BS-001"
title: "Current main complete read-only candidate replay"
status: "sealed"
outcome: "inconclusive"
subject_revision: "git:4c56912785f498232c69722bd6327b92aaed4a04"
harness_revision: "sha256:a2100ef6c23ee603622363e7dec0961b44d7ce9d5ae4eb3456f80db728a82bf3"
supersedes: ["BR-001"]
manifest: "EVIDENCE_MANIFEST.json"
created: "2026-11-03T10:04:35Z"
updated: "2026-11-03T10:11:19Z"
author: "ChatGPT"
owner: "RepoFoundry Maintainer"
completed: "2026-11-03T10:11:19Z"
executed_by: "ChatGPT"
---

# Current main complete read-only candidate replay

## Summary

The complete read-only measurement ran 12 cases with two identical traversals each (204 successful Router CLI calls); all subject inventories remained byte-identical. Candidate-retrieval Recall is 24/25 = 96.00%; Precision is 24/490 = 4.90%, scoped to provisional labels. This is **not Agent activation accuracy**. Current activation Recall/Precision are NOT_MEASURED/null.

The broader activation-correctness verdict is **inconclusive**: original itemized evidence for the claimed 17 omissions/seven violations was not located, new control labels lack independent second-review adjudication, and no Coding Agent ran. The only candidate miss is GO-FORMAT-001 under stale documentation-only planned paths. Broad candidate inclusion is expected conservatism, not proof of erroneous activation.

## Revisions and Environment

Subject main: 4c56912785f498232c69722bd6327b92aaed4a04. The exact tree fbfff712a74e227ec2be417e48eba8ea1aac9fa5 was reconstructed from archived source plus the merged PR109 patch and verified against GitHub; signed main and historical generator commit objects were checked. The local history is shallow, not a fresh network clone. Required historical generator 88a7202 is available for canonical upgrade tests.

Harness revision is the SHA-256 of the preregistered path-to-digest map. Every frozen source/label/Scenario hash still matches. Linux x86_64, Python 3.13.5; exact environment is in artifacts/environment.json. Nine managed Spec files were independently compared with the pinned Catalog source archive and matched. No production file or normative source changed.

## Procedure and Commands

Used the exact command recorded in artifacts/execution.json, from 2026-11-03T10:04:36.584370Z to 2026-11-03T10:07:17.815186Z, exit 0. Twelve fresh temporary subjects, two traversals each, fixed case order; no warmup, load or timing inference. Only candidates and requirements were invoked. Gold IDs were not passed to the Router. The scope diagnostic calls the unchanged pure _covered predicate, not full preflight.

BR-001 exceeded the host invocation duration and is retained as errored. This retry used the same frozen Scenario and longer supervising invocation; no measured partial sample was carried forward.

## Decision Rule

Measurement validity conditions are satisfied: 12 cases, 24 identical traversals, 204 CLI calls all exit 0, verified pins and unchanged subject bytes. H1-H3 are supported on these controls. The preregistered broader verdict remains inconclusive because evidence and review prerequisites are unavailable; no post-hoc accuracy threshold is introduced.

## Raw Observations

Micro candidate pairs: TP 24, FP 466, FN 1. Of 566 retrieved pairs, 76 context-only/uncertain/unreviewed pairs are excluded and 490 assessed. Recall 24/(24+1)=0.96; Precision 24/(24+466)=0.04897959183673469. Each case counts once; two reads do not double sample size.

Constructed controls separately: TP16, FP434, FN1; Recall 16/17=94.12%, Precision 16/450=3.56%; 65 excluded. Historical candidate replay separately: TP8, FP32, FN0; Recall 8/8=100%, Precision 8/40=20%; 11 excluded. No population interval or causal estimate is justified.

| Case | Candidate IDs | TP | FP | FN | Uncovered actual paths |
|---|---:|---:|---:|---:|---|
| format-only | 51 | 2 | 47 | 0 | none |
| local-name-only | 51 | 3 | 45 | 0 | none |
| explain-same-go-path | 51 | 0 | 51 | 0 | none |
| decorative-asset | 23 | 0 | 23 | 0 | none |
| ambiguous-boundary | 51 | 1 | 0 | 0 | none |
| zero-depth-glob | 51 | 2 | 47 | 0 | none |
| nested-glob | 51 | 2 | 47 | 0 | none |
| unreported-path-change | 28 | 1 | 25 | 1 | internal/sample/count.go |
| reported-path-change | 56 | 2 | 52 | 0 | none |
| sibling-not-covered | 51 | 2 | 47 | 0 | internal/sample2/count.go |
| generated-not-handwritten | 51 | 1 | 50 | 0 | none |
| historical-task3 | 51 | 8 | 32 | 0 | none |

Complete normalized IDs, per-case confusion sets and both-origin aggregates are in artifacts/observations.json.gz. Decompress with `gzip -dc artifacts/observations.json.gz`. Raw command count, exit summary and retained-log digest are in artifacts/evidence-index.json.

## Interpretation

H1 supported: format-only and read-only explanation on the same Go path both return 51 candidate IDs despite different applicability labels. This supports only the path-derived discovery boundary; the Router does not autonomously solve semantic selection.

H2 supported: zero-depth/nested glob descendants are covered; sibling and unreported path-change targets are not. Updating planned paths recovers GO-FORMAT-001 and covers the actual target. This motivates explicit scope refresh, not a new heuristic blocker.

H3 supported: each repeated candidate/card traversal matches and every temporary subject inventory is unchanged. There is no activation, context delivery or native write-gate evidence.

Historical recheck independently verified all 409 payload hashes. Against eight retrospective direct-applicability labels, five were present in the original resolved activation (5/8=62.5%); the same three omissions remain. Historical scoped precision is 5/5=100% only after excluding seven context-only and four disputed preservation-only selections, so it is not unqualified historical precision. These are old observations, not a fresh model run or proof of repaired compliance.

## Contradictions and Supersession

Supersedes BR-001 only for completion of the same read-only measurement; its errored record remains. Do not conflate recovered three omissions with the unidentified aggregate 17, or four historical FAIL with the claimed seven baseline violations. The original Task 3 matrix remains 14 PASS / 4 FAIL / 1 UNVERIFIED / 37 N/A. Conditional preservation selections are flagged as disputes for new binary scoring, not rewritten in historical sources.

## Boundaries and Extrapolation

Gold status is provisional. New labels are independent of Router outputs, not independent of the author; second review is pending. The archived Work review was non-blind/shared-filesystem. Candidate over-inclusion is not an Agent activation mistake. No current Agent selection, native Hook, understanding, behavioral compliance, causal gain or universal correct routing is measured. The 17/7 claim remains source-unverified and outside all denominators. Private evidence hashes provide integrity, not authentication or public availability.

## Handoff

PR-A reviewers may use the corpus, script and measurements as a reproducible candidate/scope baseline, not as a merge gate for Spec compliance. Independently adjudicate the new labels and obtain the original 17/7 itemization before treating this as a fully reviewed activation Gold Set. Do not merge automatically or change Router/upstream semantics from these numbers alone.

## Artifacts

artifacts/preregistered-inputs.json: pre-run frozen input digests and timestamp.
artifacts/environment.json: runtime, exact source reconstruction and Spec crosscheck.
artifacts/execution.json: actual invocation, timestamps and exit code.
artifacts/observations.json.gz: complete normalized measurement JSON, deterministic gzip.
artifacts/evidence-index.json: raw command log identity, count, exits and retention.

Private original archive identities and source entry hashes are recorded in evals/spec-activation/history.json at the frozen harness input. Raw logs and originals remain in the owner's Library/task reproduction bundle; they are not republished in Git. The current command without the optional audit archive reproduces candidate observations while explicitly declining historical revalidation.
