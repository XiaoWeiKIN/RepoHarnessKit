---
schema_version: "1"
metadata_schema: "1"
artifact_type: design-doc
id: DD-001
doc_type: design
title: RepoFoundry AI design documents
status: current
adr_refs: []
author: "Codex"
owner: "RepoFoundry Maintainer"
created: 2026-07-30
updated: 2026-08-16
---

# Design Documents

This directory contains implementation-level architecture descriptions. Durable
choices and their authorization remain in `docs/adr/`; these documents explain
how accepted choices are realized.

## Current

- [RepoHarnessKit public identity and compatibility](repoharnesskit-system.md) —
  brand-facing navigation; the registered historical DD-004 remains at its old path.
- [Aggregation Skill packaging baseline](engineering-workflow-packaging.md) —
  ADR-004/005 boundaries; public naming is amended by the RepoFoundry AI
  identity document.
- [Codex project documentation bootstrap](codex-project-bootstrap.md) —
  compatibility behavior now implemented by the Codex adapter.
- [RepoHarnessKit versioning and Harness migrations](repoharnesskit-versioning-and-migrations.md) —
  current-version navigation; registered DD-006 retains its stable reference path.
- [Engineering Spec resolution and project materialization](engineering-spec-management.md) —
  Catalog and materialization contract; activation is amended by ADR-012.
- [Agent-neutral Harness and Engineering Spec adapters](agent-neutral-harness-adapters.md)
- [Artifact Metadata Contract](artifact-metadata-contract.md) — semantic
  provenance, identity, responsibility, time, compatibility, and integrity for
  governed engineering artifacts.
- [Risk-adaptive Agent governance](risk-adaptive-agent-governance.md) —
  Explore, Build, and Governed modes that scale process controls to risk while
  keeping authority, safety, and evidence-integrity boundaries hard.
- [Reversible ADR effect](reversible-adr-effect.md) — immutable decision
  history with review, reaffirmation, retirement, supersession, and transitive
  impact reporting.

## Drafts

- [First-class technical Design Documents](first-class-technical-design-documents.md) —
  lifecycle and Research-to-design handoff proposed by ADR-018.
