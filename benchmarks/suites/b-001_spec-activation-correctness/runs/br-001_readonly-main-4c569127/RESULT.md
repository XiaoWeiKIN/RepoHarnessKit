---
schema_version: "1.1"
metadata_schema: "1"
artifact_type: benchmark-result
id: "BR-001"
suite_id: "B-001"
scenario_id: "BS-001"
title: "Current main read-only activation-candidate baseline"
status: "sealed"
outcome: "errored"
subject_revision: "git:4c56912785f498232c69722bd6327b92aaed4a04"
harness_revision: "sha256:a2100ef6c23ee603622363e7dec0961b44d7ce9d5ae4eb3456f80db728a82bf3"
supersedes: []
manifest: "EVIDENCE_MANIFEST.json"
created: "2026-11-03T10:02:50Z"
updated: "2026-11-03T10:04:34Z"
author: "ChatGPT"
owner: "RepoFoundry Maintainer"
completed: "2026-11-03T10:04:34Z"
executed_by: "ChatGPT"
---

# Current main read-only activation-candidate baseline

## Summary

Execution was interrupted by the host tool 120-second invocation timeout. No complete observations.json exists and no accuracy metric is accepted. Outcome: errored, not a Router failure.

## Revisions and Environment

Subject and harness are exactly the immutable revisions in metadata. Local Linux/Python 3.13.5. No source, Spec or protocol edit occurred.

## Procedure and Commands

Started the command in SCENARIO.md with the original archive and fixture. The host interrupted execution after 47 completed CLI records. The unfinished output directory and raw logs are retained, not overwritten.

## Decision Rule

Apply the predeclared execution-failure rule: errored. Do not infer activation success or failure from partial candidate observations.

## Raw Observations

47 commands completed before host interruption. No complete 12-case/two-repeat dataset. Counters and log digest are in artifacts/execution.json; metrics are null.

## Interpretation

H1, H2 and H3 remain unevaluated in this incomplete Run. Host duration is not a Router performance endpoint.

## Contradictions and Supersession

A subsequent Run may retry the unchanged Scenario with an invocation mechanism that waits for completion; this Run remains immutable.

## Boundaries and Extrapolation

This interrupted execution establishes neither correct selection nor incorrect routing, nor any model effect.

## Handoff

PR-A reviewers: retain the timeout as execution history and use a complete subsequent Run for candidate diagnostics.

## Artifacts

artifacts/preregistered-inputs.json freezes the planned inputs. artifacts/execution.json records interruption and raw-log identity. Original commands.jsonl is retained privately in the reproduction bundle.
