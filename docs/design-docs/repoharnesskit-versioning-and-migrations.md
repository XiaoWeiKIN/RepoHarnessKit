# RepoHarnessKit — versioning and migration entrypoint

This is the current **public navigation page** for distribution and Harness
migration. The accepted [DD-006 — versioning and Harness migrations](repo-foundry-versioning-and-migrations.md)
remains the registered, detailed Design, with its historical path and
provenance unchanged. Earlier version examples inside DD-006 are historical,
not the currently installed release identity.

## Checked-in version planes

At the present source revision the distribution metadata declares:

| Plane | Version |
|---|---|
| Distribution (`VERSION`) | `0.15.3` |
| Harness schema | `3` |
| Harness Core | `1.6.2` |
| Codex adapter | `2.4.4` |
| Claude adapter | `1.3.3` |
| Portable adapter | `1.3.4` |
| Activation protocol | `2` |
| Default EngineeringSpecifications Catalog | `1.9.0` |

These are checked-in source values, **not** a claim that a GitHub Release or
a target repository has already upgraded. Repository Spec locks are independent.

Use [release-candidate notes](../releases/0.15.3.md) and the
[upgrade instructions](../../references/upgrades.md) for version-specific
behavior. Preview an upgrade and review customized-file conflicts before
applying it to any target repository.

Brand files and the installer display are labeled `RepoHarnessKit`; the
`repofoundry` command, `foundryctl.py`, `repo-foundry-ai` Skill ID,
manifest owner and project-local generated paths remain compatibility-stable.

This page is **not a second governed Design artifact**; it has no DD ID.
Registered DDs and archived ADR/Execution Plan references remain at their
original source paths rather than being silently relocated or rewritten.
