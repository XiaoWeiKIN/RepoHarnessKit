---
schema_version: "1.1"
metadata_schema: "1"
artifact_type: design-doc
id: {{DESIGN_ID}}
doc_type: design
layout: {{LAYOUT}}
title: {{TITLE_JSON}}
status: draft
working_revision: "1"
published_revision: "0"
research_refs: {{RESEARCH_REFS}}
research_not_required_reason: {{RESEARCH_NOT_REQUIRED_REASON_JSON}}
adr_refs: {{ADR_REFS}}
design_dependencies: {{DESIGN_DEPENDENCIES}}
decision_not_required_reason: ""
approved_by: ""
approved_at: ""
approval_ref: ""
superseded_by: ""
terminal_reason: ""
revision_reason: ""
author: {{AUTHOR_JSON}}
owner: {{OWNER_JSON}}
created: {{DATE}}
updated: {{DATE}}
---

# {{TITLE}}

This document is the entrypoint for `{{DESIGN_ID}}`. The logical Design and all
managed package members share one review and approval boundary.

## Design Summary

<!-- REQUIRED: State the selected system shape, user-visible outcome, main tradeoff, and validity conditions in clear, consistent terms before internal detail. For a revision, explain material changes against a known baseline; do not invent one. Link deeper explanations and evidence from existing sections. -->

## Goals and Non-goals

<!-- REQUIRED: State owned outcomes and explicit exclusions. -->

## Research and Decision Inputs

<!-- REQUIRED: Summarize the evidence, accepted ADR constraints, remaining unknowns, and validity conditions that materially shape this architecture. Do not provide only links. -->

## System Context and Invariants

<!-- REQUIRED: Define existing boundaries and invariants. Use Mermaid when relationships matter. -->

## Proposed Architecture

<!-- REQUIRED: Explain the system shape, core abstractions, responsibility boundaries, ownership, dependency direction, and extension points. Link focused package members where deeper treatment helps the reader. -->

## Control and Data Flows

<!-- REQUIRED: Trace one to three representative requests, data items, state transitions, or resource lifecycles end to end. Include failure or concurrency behavior only where it shapes the architecture. -->

## Alternatives, Open Questions, and Revisit Triggers

<!-- REQUIRED: Record meaningful rejected shapes, unresolved architecture questions, owners where known, and evidence that would change this design. -->

## Package Document Map

{{PACKAGE_MAP}}

## Revision Notes

- {{DATE}} — Created working revision 1.
