# RepoHarnessKit — versioning and migration entrypoint

This is the current **public navigation page** for distribution and Harness
migration. The accepted [DD-006 — versioning and Harness migrations](design-docs/repo-foundry-versioning-and-migrations.md)
remains the registered, detailed Design, with its historical path and
provenance unchanged. Earlier version examples inside DD-006 are historical,
not the currently installed release identity.

## Version sources, not copied version constants

The **checked-in source** and the **latest published distribution** are
different states. Read source versions from the maintained files instead of
copying a fixed number into this navigation page:

| Plane | Authoritative source |
|---|---|
| Checked-in distribution candidate | [`VERSION`](../VERSION) |
| Harness Core and adapter versions | [`release.json`](../release.json) |
| Harness schema and activation protocol | [`release.json`](../release.json) |
| Default EngineeringSpecifications Catalog | [`release.json`](../release.json) |
| Latest published distribution | [GitHub Releases](https://github.com/XiaoWeiKIN/RepoHarnessKit/releases/latest) |

The source checkout may carry an **unpublished release candidate** ahead of
the latest published package. The installed `repofoundry` command can upgrade
only to its own bundled distribution version; it cannot fetch a future migration
just because a newer `VERSION` exists on `main`.

For published release history, consult [GitHub Releases](https://github.com/XiaoWeiKIN/RepoHarnessKit/releases/latest).
The published [v0.15.4 notes](releases/0.15.4.md) are a versioned record,
not a live statement about all future source checkouts.
Follow the [upgrade instructions](../references/upgrades.md) and preview all
customized-file conflicts before applying. Repository Spec locks remain
independent of the distribution version.

Brand files and the installer display are labeled `RepoHarnessKit`; the
`repofoundry` command, `foundryctl.py`, `repo-foundry-ai` Skill ID,
manifest owner and project-local generated paths remain compatibility-stable.

This page is **not a second governed Design artifact**; it has no DD ID.
Registered DDs and archived ADR/Execution Plan references remain at their
original source paths rather than being silently relocated or rewritten.
