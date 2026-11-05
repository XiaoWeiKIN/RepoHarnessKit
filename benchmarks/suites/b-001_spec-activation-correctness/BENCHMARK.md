---
schema_version: "1.1"
metadata_schema: "1"
artifact_type: benchmark-suite
id: "B-001"
title: "Spec activation correctness baseline"
status: "active"
author: "ChatGPT"
owner: "RepoFoundry Maintainer"
created: "2026-11-03"
updated: "2026-11-03"
---

# Spec activation correctness baseline

## Purpose and Scope

Measure only path-derived Requirement candidate retrieval and explicit scope coverage. Keep selection, delivery and compliance as separate facts.

## Subject Under Test

The unchanged shared Router at 4c56912785f498232c69722bd6327b92aaed4a04; real Task 3 fixture; Catalog 1.9.0.

## Consumers

PR-A reviewers and subsequent activation-coverage design. No automated merge or release consumer.

## Ownership and Lifecycle

RepoFoundry Maintainer owns repository review. ChatGPT authors this baseline; new labels need independent review. Retain all runs and original negative history.

## Non-goals

No Coding Agent evaluation, native Hook claim, semantic classifier, upstream Spec change or production Router modification.

## Safety and Data Policy

Only disposable fixture copies are written. Original Library archives stay private; publish hashes, source locators, bounded labels and measurements, not raw private logs or normative copies.
