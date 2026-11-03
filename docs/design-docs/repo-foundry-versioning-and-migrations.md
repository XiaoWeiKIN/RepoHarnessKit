---
schema_version: "1"
metadata_schema: "1"
artifact_type: design-doc
id: DD-006
doc_type: design
title: RepoFoundry versioning and Harness migrations
status: current
adr_refs: ["ADR-011", "ADR-012", "ADR-015", "ADR-058"]
author: "Codex"
owner: "RepoFoundry Maintainer"
created: 2026-08-03
updated: 2026-11-02
---

# RepoFoundry Versioning and Harness Migrations

## Purpose

RepoFoundry must be able to improve its Skill, scripts, Core, adapters, and generated
files without treating an existing repository as disposable. Versioning is
therefore part of the repository contract, not only release metadata.

The current distribution is `0.15.2`. It writes Harness schema `3`, Core
`1.6.1`, Codex adapter `2.4.3`, Claude adapter `1.3.2`, Portable adapter
`1.3.3`, governance policy schema `1`, and activation protocol `2`.
Engineering Specifications keep their independent Catalog version and lock
lifecycle. Earlier distributions, schemas `1` and `2`, earlier schema-3 Core
and adapters, and Codex profile `1.0.0` remain migration inputs.

## Independent version planes

| Plane | Current | Stored in | Meaning |
|---|---:|---|---|
| RepoFoundry distribution | `0.15.2` | `VERSION`, `producer.version` | Skill and CLI release that produced or last migrated the Harness |
| Harness schema | `3` | `schema_version` | JSON state shape and validation contract |
| Harness Core | `1.6.1` | `core.version`, Core file records | Product-neutral repository, project Skill, and mode-aware activation behavior |
| Codex adapter | `2.4.3` | `adapters[]`, adapter file records | Codex instructions, Skills, Hooks, and event translation |
| Claude adapter | `1.3.2` | `adapters[]`, adapter file records | Claude project Skills with CLI/advisory classification and activation |
| Portable adapter | `1.3.3` | `adapters[]`, adapter file records | CLI and advisory classification and activation |
| Governance policy | `1` | optional `governance` object in schema `3` | Repository profile; missing means strict compatibility |
| Activation protocol | `2` | Core executable and adapter capability output | Normalized event, exact capsule, receipt, and epoch semantics |
| Engineering Specs Catalog | `1.9.0` by default | `specs.json`, `specs.lock.json` | Independently selected engineering guidance release |

No plane inherits another plane's version. A Spec update does not migrate the
Harness, and a RepoFoundry upgrade does not change the selected Spec Catalog.

Release `0.8.3` permits an accepted replacement ADR to be superseded later
without flattening or rewriting the earlier relationship. Validation preserves
every immediate `superseded_by` / `supersedes` backlink, accepts only
accepted-origin lifecycle states along the chain, and rejects supersession
cycles. Current Decision contexts still require an accepted/current terminal
ADR, so historical View anchors become `review_required` until their owner
explicitly retargets them. Harness schema, Core, adapters, governance policy and
activation protocol do not change.

Release `0.8.2` adds Git-proven recovery for schema-1.2 checkpoint seals that
were invalid in the commit introducing their exact path. Registration is
preview-first and writes a content-addressed, self-digested receipt under
`docs/.epctl/checkpoint-recoveries/`; normal validation remains offline and
accepts only the exact recorded document and payload mismatch. Checkpoint bytes,
Harness schema, Core, adapters, governance policy and activation protocol do not
change. Downgrading to 0.8.1 leaves checkpoints intact but cannot consume the
recovery receipt, so the original mismatch becomes visible again.

Release `0.8.0` added lossless ADR context compaction. Explicit Harness upgrade
creates only an empty Decision View registry, generated index, and projection
directory; it does not create views or alter ADR sources. Decision Views remain
non-normative, capsules copy exact verified source text under an explicit budget,
and consolidation analysis is preview-only.

Release `0.8.1` adds explicit focused ADR capsule materialization without changing
Harness schema or persistent state. Complete mode preserves the 0.8.0 output
contract. Focused mode validates the same full current-effect closure, materializes
only requested rows and downstream scoped amendments, and exposes an auditable
partial-context manifest. Downgrading to 0.8.0 leaves repository state readable;
only the ephemeral focused CLI flags become unavailable.

Release `0.7.1` fixes lifecycle writes for registered legacy ADRs whose YAML
frontmatter uses block-style relationship lists. Preview and authority gates are
unchanged; apply now updates only top-level lifecycle metadata while preserving
repository-owned legacy fields. Harness schema, Core, adapters, governance
policy, and activation protocol remain unchanged.

Release `0.7.0` makes the authoring phases of Engineering Benchmark, Research,
Design, and Execution Plan explicitly collaborative while keeping their
deterministic evidence and lifecycle controls. It also projects ADRs by effective
decision state and current effect, so retired and historical decisions remain
traceable without crowding the current decision surface. These are distribution
Skill and tooling changes: Harness schema, Core, adapters, governance policy, and
activation protocol remain unchanged, and existing repositories require only an
explicit distribution metadata upgrade when they choose to adopt `0.7.0`.

Release `0.6.0` adds `engineering-design` as a fifth independently installable
professional Skill. Fresh Harness manifests register both `engineering-design`
and `engineering-execution-plan`; existing schema-3 manifests with only the EP
component remain readable and gain the Design component through a previewed
bootstrap or upgrade migration. Design uses its own `docs/.designctl` state and
approved revision evidence, while `epctl` is a read-only consumer. The canonical
project workflow now routes governed technical-design production to that peer, so
Core advances to `1.5.0`; Harness schema, adapters, governance policy, and activation
protocol remain unchanged.

Release `0.5.0` adds risk-adaptive governance. Fresh Harnesses start in
adaptive Explore while existing manifests without a profile remain strict until
an explicit preview/apply migration. A turn promotes monotonically through
Explore, Build, and Governed; exact Requirement activation remains mandatory in
Build and Governed. It also adds reversible ADR effect transitions and a
repository-owned historical ADR revision registry. Harness schema and activation
protocol remain unchanged.

Release `0.4.1` makes Harness activation depth explicit. Ordinary read-only
code explanation, navigation, call-chain tracing, and existing-behavior
summaries do not auto-trigger full Harness validation, Spec activation,
governed artifacts, or the five-label evidence handoff. Formal review,
explicit Spec conformance, diagnosis, and repository mutation retain their
governed paths. The canonical Core Skill and all three adapter entrypoints
change, so their component versions advance by one patch. Harness schema and
activation protocol remain unchanged.

Release `0.4.0` consumes Requirement-level Automated enforcement metadata. It
advances the derived Requirement index to schema `2`, keeps schema `1`
readable, adds published/effective levels to cards and receipts, and exports
source-verified activation evidence without normative text. RepoFoundry's
effective ceiling remains Advisory because this release does not provide a
finding adjudicator or Warning/Blocking observation lifecycle. Core advances
to `1.3.0`; all adapters advance because their generated instructions or
command allowlists expose the evidence workflow. Activation protocol stays at
`2`, and the default Catalog stays on published release `1.5.0`.

Release `0.3.1` adds a fail-closed selection decision to Catalog updates. When
a changed Catalog exposes optional Specs outside the existing dependency-closed
selection, dry-run emits their IDs, descriptions, dependencies, recommendation
state, and configuration state. Apply is rejected until the caller explicitly
provides the complete `--spec` set, `--required-only`, or `--keep-selection`.
This changes Core Agent behavior, so Core advances to `1.2.1`; it does not
change the Harness schema, adapter protocol, or locked Spec state by itself.

Release `0.3.0` changes the default Catalog used only when a project does not
yet have `docs/.engineering/specs.json`: new projects start from
EngineeringSpecifications `1.5.0`. Installing the distribution or upgrading a
Harness MUST NOT rewrite an existing Spec manifest, lock, routing indexes, or
managed Markdown. Existing projects adopt Catalog `1.5.0` only through an
explicit, previewed `spec update`. A previewed `spec sync --apply` generates
the new derived Requirement index without selecting another Catalog.

```mermaid
flowchart LR
    D["RepoFoundry distribution<br/>VERSION 0.15.2"] --> P["producer.version"]
    D --> U["foundryctl upgrade"]
    U --> H["Harness schema 3"]
    U --> C["Harness Core 1.6.1"]
    U --> A["Codex + Claude + Portable adapters"]
    C --> F["Core file provenance"]
    A --> F
    S["Specs Catalog<br/>independent SemVer"] --> L["specs.json + specs.lock.json"]
    H -.->|"does not select"| L
```

## Distribution installation is not Harness migration

The public `install.py` entrypoint owns acquisition and activation of the
RepoFoundry distribution on one macOS or Linux user machine. The same command
performs a first install, advances to a newer stable release, or reports an
idempotent no-op. It does not discover or mutate target repositories.

```mermaid
flowchart LR
    O["One-line installer"] --> R["Stable GitHub Release"]
    R --> G["Tag resolved to commit"]
    G --> S["Safe staged package<br/>archive + package SHA-256"]
    S --> A["Atomic current release"]
    A --> C["repofoundry CLI"]
    C --> P["Explicit per-project<br/>Harness migration preview"]
    P -->|"--apply"| H["Repository Harness updated"]
    A -.->|"never scans projects"| H
```

The default install prefix contains immutable, source-addressed directories in
`releases/`, a relative `current` symlink, and a local `install.json`. That
installation manifest records the active version, release ID, package digest,
GitHub tag/commit/archive digest or explicit local source, launcher, and host
integration links. It is local distribution provenance and never appears in a
repository Harness manifest.

The installer uses `curl` transport when available and a certificate-validating
standard-library HTTPS fallback. It validates all archive paths before extraction, rejects links and
non-regular members, bounds remote payload sizes, verifies package identity and
`foundryctl --version`, then switches the active release. Pre-existing
non-managed launchers or host registrations are moved to reported backups.
Network, extraction, validation, or activation failure preserves the previous
active release. Host detection and registration are installer adapters; the
installed package remains usable through the portable CLI without any
product-specific private directory.

## Release invariants

Every distributed change updates the planes it actually changes:

- bump `VERSION` for every RepoFoundry release;
- publish `install.py` in every release so the stable one-line entrypoint can
  install that release and later versions;
- bump Core or the owning adapter whenever its template bytes, required seed
  set, or behavior changes;
- bump the Harness schema whenever the persistent JSON shape or interpretation
  changes, while retaining explicit readers for supported older schemas;
- add deterministic migration logic and fixtures before publishing a release
  that changes existing repository state;
- update the Specs Catalog only in its own repository and select it through
  `spec update`.

In particular, template bytes must never change while keeping the same owning
Core or adapter version. A distribution-only script or Skill fix may leave the
schema, Core, and adapter versions unchanged.

`release.json` mirrors `VERSION` and the authoritative CLI constants for release
tooling. `scripts/check_release.py --base-ref <commit>` verifies that metadata
and compares each owner's exact template bytes and file mapping against the
specified Git commit. Changed templates require a strictly greater owner version
and distribution version. The checker parses historical declarations as data;
it does not import or execute historical Python. CI supplies the PR base or
previous main-push SHA, so a clean checkout cannot hide changes behind `HEAD`.
The canonical source check also exercises an actual previous-distribution
bootstrap followed by the current official preview/apply/validate workflow.

## Schema compatibility

The reader is deliberately asymmetric:

- schema `1` is accepted as a legacy, read-only contract and emits
  `HARNESS_SCHEMA_UPGRADE_AVAILABLE`;
- schema `2` is accepted as the versioned Codex-profile migration input;
- schema `3` is accepted when its producer, Core, adapters, templates, and
  migration records are not newer than the installed distribution;
- a schema `3` manifest without `governance` remains valid and resolves to
  `strict`; fresh manifests write policy schema `1` with profile `adaptive`;
- an unknown future schema, producer, Core, adapter, template, or migration version
  fails closed;
- schema `1` or `2` migration requires the explicit `upgrade` command;
- schema `3` is interpreted by its declared component versions, so Core
  `1.0.0` and Codex `2.0.0` remain valid without the newer project Skill
  records;
- a schema `3` bootstrap that adds an adapter may also create missing new
  generated paths and record Core/adapter component migrations after the same
  conflict-free preview; replacing an older seed still requires `upgrade`.

Schema `3` records the producer, Core, adapters, and unique Core/adapter owner
for each seeded file. A versioned record contains the template SHA-256 and the SHA-256
installed at the last safe adoption point. A pre-existing file that cannot be
matched to a bundled template is recorded as `legacy-unversioned` with null
hashes so a future release cannot mistake it for an overwrite-safe seed.

## Preview-first migration

`foundryctl upgrade --to VERSION` computes a plan and writes nothing. An
explicit `--governance-profile adaptive|strict` participates in the same plan;
omitting it preserves the existing effective profile. `--apply` acquires the
Harness lock, recomputes the same plan, refuses any
changed preflight, applies atomic file replacements, writes the manifest, and
runs Harness validation. A post-write validation failure restores every file
touched by the migration.

```mermaid
flowchart TD
    P["Read and validate existing manifest"] --> V{"State version supported?"}
    V -- "No / future" --> X["Fail closed"]
    V -- "Yes" --> D["Build dry-run plan"]
    D --> C{"Any conflict?"}
    C -- "Yes" --> M["Preserve repository bytes<br/>require manual merge"]
    C -- "No" --> A{"--apply?"}
    A -- "No" --> R["Return JSON plan"]
    A -- "Yes" --> K["Lock and recompute"]
    K --> W["Atomic writes + manifest history"]
    W --> Q{"Post-validation passes?"}
    Q -- "Yes" --> O["Return updated paths"]
    Q -- "No" --> B["Rollback touched paths"]
```

## Seed replacement policy

| Existing seed state | Upgrade action |
|---|---|
| File already equals the current template | Update provenance only |
| File equals its recorded `installed_sha256` and a newer template exists | Replace it and record the new hashes |
| Versioned file differs from `installed_sha256` | Conflict; preserve bytes and require a manual merge |
| `legacy-unversioned` project-editable document differs from the current template | Preserve permanently until explicitly reconciled |
| A new generated Core or adapter seed is absent | Create it during the explicit upgrade |
| A generated Core or adapter path contains different bytes | Conflict; require explicit reconciliation |
| Required file missing, wrong type, or reached through a symlink | Conflict |

This policy makes customization detection evidence-based. Timestamps, Git
status, and heuristic text matching are not accepted as overwrite authority.

## Migration history and idempotence

Successful structural, Core, and adapter migrations append stable records to
`applied_migrations`. The records have no wall-clock timestamp so the manifest
remains reproducible. Reapplying the same target produces no file or manifest
updates and never duplicates a migration ID.

The current distribution bundles only migrations to its own version. Selecting
another target returns `UPGRADE_TARGET_UNAVAILABLE`; fetching and executing
remote migration code is outside the CLI trust boundary.

The Core `1.0.0` to `1.1.0` migration adds
`.repo-foundry/skills/repo-foundry-ai/SKILL.md`. The Codex `2.0.0` to `2.1.0`
migration adds `.agents/skills/repo-foundry-ai/SKILL.md`. Both are generated,
repository-relative regular files. Core `1.2.x` and Codex `2.2.x` add
protocol-v2 exact Requirement activation; Core `1.3.x` and Codex `2.3.x` add
enforcement metadata and the activation-depth boundary. Core `1.4.0`, Codex
`2.4.0`, Claude `1.3.0`, and Portable `1.3.0` add the shared risk-adaptive
governance contract. Existing schema-3 manifests without governance move
forward as `strict`; selecting `adaptive` is a separate explicit migration.

## Professional artifact compatibility is not a Harness migration

The independently installable professional Skills may add optional evidence
needed to keep their own historical contracts verifiable. For example, an
archived ExecPlan can retain an ADR payload digest whose exact document revision
is no longer the current ADR file. `engineering-execution-plan` stores an
explicitly imported revision under
`docs/.epctl/adr-revisions/ADR-NNN/sha256-<payload>.md` and resolves it only for
completed or cancelled plans.

This operation follows the same safety principles—preview first, immutable
target, conflict rejection, atomic apply and offline validation—but it does not
change `docs/.engineering/harness.json`, Core or adapter versions. Git can be an
explicit one-time source for a recovered blob; it is never a validation-time
dependency. A distribution containing this CLI behavior still bumps `VERSION`
because the shipped professional Skill changed, while Harness component planes
remain unchanged.
