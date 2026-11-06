# RepoHarnessKit — public identity and compatibility

**RepoHarnessKit** is the current repository and public-facing toolkit name.
The repository provides a repository-native Harness for coding Agents,
with source-owned constraints, deterministic checks, and evidence-oriented workflows.

## Public assets

The canonical brand files are:

- [repoharnesskit-mark.svg](../assets/brand/repoharnesskit-mark.svg)
- [repoharnesskit-icon.svg](../assets/brand/repoharnesskit-icon.svg)
- [repoharnesskit-icon.png](../assets/brand/repoharnesskit-icon.png)

The original `repofoundry-*` assets remain byte-identical compatibility aliases;
historical documents, packages, tags and embedded images must not be rewritten
or invalidated merely to align the contemporary name.

## Runtime identity is a separate compatibility contract

| Surface | Current identifier | Compatibility decision |
|---|---|---|
| Public toolkit and installer display | `RepoHarnessKit` | New user-facing name |
| GitHub repository | `XiaoWeiKIN/RepoHarnessKit` | Current remote |
| Root Skill | `repo-foundry-ai` | Retained for existing Agent discovery |
| Installed command | `repofoundry` | Retained; `--version` still reports `RepoFoundry AI` |
| Installer product ID | `repo-foundry-ai` | Retained for installed release metadata |
| Project-local generated paths | `.repo-foundry/` and `*/skills/repo-foundry-ai/` | Retained |
| Manifest owner | `repo-foundry` | Retained for historical and new manifests |

This is a **branding and navigational naming** change, not a runtime identity
migration. Do not rename the CLI, Skill frontmatter ID, generated paths or
manifest owners without a separate, versioned compatibility migration.

## Accepted design and decision history

The registered [DD-004 — system identity and packaging](design-docs/repo-foundry-system.md)
and [ADR-008 — historical RepoFoundry AI brand decision](adr/adr-008_repofoundry-ai-brand.md)
retain their original paths, metadata and evidence. The public RepoHarnessKit
name is reflected in the merged [README branding PR #86](https://github.com/XiaoWeiKIN/RepoHarnessKit/pull/86),
[public filename and installer-display PR #114](https://github.com/XiaoWeiKIN/RepoHarnessKit/pull/114),
and the [v0.15.4 release](https://github.com/XiaoWeiKIN/RepoHarnessKit/releases/tag/v0.15.4).
ADR-008 records the earlier accepted naming decision; it has **not** been
silently superseded, rewritten, or presented here as approval for the new name.
Any formal ADR replacement requires a separate governed decision.

For the current distribution and migration workflow see
[RepoHarnessKit versioning and migrations](repoharnesskit-versioning-and-migrations.md).
