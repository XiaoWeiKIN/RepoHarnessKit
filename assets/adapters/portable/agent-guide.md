# Agent Engineering Guide

This repository uses RepoFoundry's product-neutral engineering Harness. Read
`ARCHITECTURE.md` and `docs/index.md` before changing established boundaries.

## Activation depth

Ordinary read-only code explanation, navigation, call-chain tracing, and
existing-behavior summaries do not start the full Harness workflow. Read only
the necessary code and repository documents; do not run Harness validation,
activate Specifications, create governed artifacts, or require an evidence
handoff solely for that analysis. Use the workflow below for implementation,
formal code review, explicit Spec conformance, or repository mutation. A formal
defect, security, or reliability diagnosis may consult repository contracts,
but it escalates only when its requested scope requires review or change.

## Governance and Engineering Specifications

Create a stable local session and turn identifier and run the shared engine:

```bash
python3 .repo-foundry/engineering-specs/spec_router.py begin \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id> \
  --prompt "<task summary>"
```

`begin` reports the repository profile and mode. Adaptive Explore permits
bounded reversible work without a receipt. Promote to Build for bounded
production work or Governed for public contracts, security, data, irreversible
operations, reliability claims, releases, or durable decisions:

```bash
python3 .repo-foundry/engineering-specs/spec_router.py classify \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id> \
  --mode <build|governed> --reason <risk-reason>
```

In Build/Governed, read each candidate's `Applicability` section, request bounded
cards for applicable Specs, then record exact direct Requirements with reasons
or a justified explicit-none decision before the first mutation:

```bash
python3 .repo-foundry/engineering-specs/spec_router.py candidates \
  --path <planned-path> [--path <planned-path> ...]
python3 .repo-foundry/engineering-specs/spec_router.py requirements \
  --path <planned-path> --spec <applicable-spec-id>
python3 .repo-foundry/engineering-specs/spec_router.py activate \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id> \
  --path <planned-path> --spec <applicable-spec-id> \
  --requirement <ID> --because "<ID>=<task-specific reason>"
```

Before the first Build/Governed code edit, review **all applicable**
Requirement cards for naming, common paths, control flow and tests, and
enumerate every exact intended source/test file. With no native Hooks,
run `rehydrate` first to deliver the exact capsule, then:

```bash
python3 .repo-foundry/engineering-specs/spec_router.py preflight \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id> \
  --path <exact-source-file> --path <exact-test-file> \
  [--expect-requirement <independently-identified-required-ID> ...]
```

This read-only gate checks path coverage and expected Requirement IDs; it does
not infer semantic applicability. It refuses a pre-edit PASS when current files differ from the turn
baseline, but cannot detect reverted edits or prove historical timing.
No post-edit activation may backdate compliance.
If new code introduces identifiers or new branches, review their Requirement
cards and re-activate **before** the additional edits.

This adapter provides CLI checks and advisory instructions. It does not claim
native lifecycle interception. Use explicit whole-Spec fallback only with a
reason; a raised capsule budget also requires `--capsule-budget-reason`. Use
`--none --reason` when nothing applies. Run `rehydrate` after a context reset,
re-run activation if planned paths change, run each resolved
Requirement's Verification row, then audit the final handoff. If canonical
validation (for example, offline Go tidy) is blocked by unavailable
dependencies, report the exact command as UNVERIFIED/incomplete and do not
claim full CI or Compliance PASS. A no-effect Verification requires the actual
no-write/rollback evidence when specified; pure-function tests do not replace it.
When the
Execution Plan control plane is initialized, resolve its Skill and run
`epctl.py --repo . adr-maintenance` after an ADR lifecycle/storage mutation and
before a Governed handoff; scheduled CI may add `--check`. The result is
preview-only and grants no lifecycle or History Pack authority.

```bash
python3 .repo-foundry/engineering-specs/spec_router.py evidence \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id>
python3 .repo-foundry/engineering-specs/spec_router.py audit \
  --adapter-id portable --session-id <session-id> --turn-id <turn-id> \
  --message-file <handoff-file>
```

Explore reads only the files and checks needed for the local task. Continue
authorized implementation through relevant checks and corrections; ordinary
local work does not require another approval. Explore may use normal prose for
outcome, verification, and unresolved risk.
The evidence export preserves each source-owned published level but records
Advisory as RepoFoundry's effective ceiling. This adapter does not claim a
finding executor or Warning/Blocking lifecycle.
Build/Governed handoff contains all five labels:

```text
Activated specifications: <IDs and versions | none>
Activated requirements: <Requirement IDs | none>
Verification: <commands and observable results>
Exceptions: none | <governed exception>
Compatibility or migration: none | <observable effect and plan>
```
