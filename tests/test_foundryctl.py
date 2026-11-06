from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.harness_legacy_fixture import CORE_MEMORY_PATHS, strip_memory_assets


ROOT = Path(__file__).resolve().parents[1]
FOUNDRYCTL = ROOT / "scripts" / "foundryctl.py"
sys.path.insert(0, str(ROOT / "scripts"))
import foundryctl  # noqa: E402

EPCTL = (
    ROOT
    / "engineering-execution-plan"
    / "scripts"
    / "epctl.py"
)
PREVIOUS_DISTRIBUTION = "0.7.1"
from tests.spec_git_fixture import (  # noqa: E402
    add_specialized_go_specs,
    commit_all,
    create_git_catalog,
    update_go_spec,
)


class FoundryctlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "target"
        self.repo.mkdir()
        (
            self.catalog_repository,
            self.catalog_commit,
        ) = create_git_catalog(self.base)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_default_source_is_a_fixed_catalog_release(self) -> None:
        source = foundryctl.spec_source(
            foundryctl.DEFAULT_SPEC_REPOSITORY,
            version=None,
            ref=None,
        )
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source["ref"], "refs/tags/v1.9.0")

    def run_cli(
        self,
        *arguments: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        selected_arguments = list(arguments)
        needs_source = (
            selected_arguments
            and selected_arguments[0] == "bootstrap"
        ) or (
            len(selected_arguments) >= 2
            and selected_arguments[0] == "spec"
            and selected_arguments[1] in {"plan", "sync", "update"}
        )
        manifest_exists = (
            self.repo / "docs" / ".engineering" / "specs.json"
        ).exists()
        if needs_source and not manifest_exists:
            if "--spec-repository" not in selected_arguments:
                selected_arguments.extend(
                    [
                        "--spec-repository",
                        self.catalog_repository.resolve().as_uri(),
                    ]
                )
            if (
                "--spec-ref" not in selected_arguments
                and "--spec-version" not in selected_arguments
            ):
                selected_arguments.extend(["--spec-ref", "main"])
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(FOUNDRYCTL),
                "--repo",
                str(self.repo),
                *selected_arguments,
            ],
            text=True,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != expected:
            self.fail(
                f"expected exit {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def run_ep_cli(
        self,
        *arguments: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(EPCTL),
                "--repo",
                str(self.repo),
                *arguments,
            ],
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != expected:
            self.fail(
                f"expected exit {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def write_schema2_manifest(self) -> Path:
        path = self.repo / "docs" / ".engineering" / "harness.json"
        payload = foundryctl.codex_harness_manifest(self.repo)
        payload["producer"]["version"] = "0.1.0"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def write_pre_project_skill_schema3_manifest(self) -> Path:
        path = self.repo / foundryctl.HARNESS_MANIFEST
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["components"] = ["engineering-execution-plan"]
        payload.pop("governance", None)
        payload["core"]["version"] = "1.0.0"
        strip_memory_assets(self.repo, payload)
        for adapter in payload["adapters"]:
            if adapter["id"] == "codex":
                adapter["version"] = "2.0.0"
        removed = {
            foundryctl.CORE_PROJECT_SKILL_PATH,
            foundryctl.CODEX_PROJECT_SKILL_PATH,
        }
        payload["files"] = [
            record for record in payload["files"]
            if record["path"] not in removed
        ]
        for record in payload["files"]:
            if record["owner_kind"] == "core":
                record["template_version"] = "1.0.0"
            elif record.get("owner_id") == "codex":
                record["template_version"] = "2.0.0"
        payload["instruction_files"] = [
            {"path": "AGENTS.md", "max_lines": 100}
        ]
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for relative in removed:
            (self.repo / relative).unlink()
        return path

    def test_codex_bootstrap_dry_run_does_not_write(self) -> None:
        payload = json.loads(
            self.run_cli("bootstrap", "--profile", "codex").stdout
        )

        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["adapters"], ["codex"])
        self.assertTrue(
            any(
                "HARNESS_PROFILE_ALIAS_DEPRECATED" in warning
                for warning in payload["warnings"]
            )
        )
        self.assertEqual(
            payload["components"],
            ["engineering-design", "engineering-execution-plan"],
        )
        self.assertIn(
            {"action": "create_file", "path": "AGENTS.md"},
            payload["actions"],
        )
        self.assertIn(
            {"action": "register", "path": "docs/design-docs"},
            payload["actions"],
        )
        self.assertEqual(payload["specs"], ["core/semantic-naming"])
        self.assertIn(
            {
                "action": "create_file",
                "path": "docs/.engineering/specs.json",
            },
            payload["actions"],
        )
        self.assertEqual(payload["created"], [])
        self.assertEqual(payload["updated"], [])
        self.assertEqual(list(self.repo.iterdir()), [])

        explicit = json.loads(
            self.run_cli(
                "bootstrap",
                "--profile",
                "codex",
                "--dry-run",
            ).stdout
        )
        self.assertEqual(explicit, payload)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_governance_profile_is_adaptive_for_fresh_and_previewed_for_changes(
        self,
    ) -> None:
        preview = json.loads(
            self.run_cli("bootstrap", "--adapter", "codex").stdout
        )
        self.assertEqual(preview["governance_profile"], "adaptive")

        self.run_cli(
            "bootstrap",
            "--adapter",
            "codex",
            "--governance-profile",
            "strict",
            "--apply",
        )
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        strict_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            strict_manifest["governance"],
            {"policy_schema": 1, "profile": "strict"},
        )

        migrate_preview = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "codex",
                "--governance-profile",
                "adaptive",
            ).stdout
        )
        self.assertEqual(migrate_preview["mode"], "dry-run")
        self.assertEqual(migrate_preview["governance_profile"], "adaptive")
        self.assertEqual(
            json.loads(manifest_path.read_text(encoding="utf-8"))["governance"],
            {"policy_schema": 1, "profile": "strict"},
        )

        applied = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "codex",
                "--governance-profile",
                "adaptive",
                "--apply",
            ).stdout
        )
        self.assertEqual(applied["governance_profile"], "adaptive")
        adaptive_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            adaptive_manifest["governance"],
            {"policy_schema": 1, "profile": "adaptive"},
        )
        self.assertIn(
            "governance-strict-to-adaptive",
            [item["id"] for item in adaptive_manifest["applied_migrations"]],
        )

    def test_invalid_governance_manifest_fails_closed(self) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["governance"]["profile"] = "unbounded"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = self.run_cli("validate", "--harness", expected=1)
        self.assertIn(
            "HARNESS_GOVERNANCE_PROFILE_UNSUPPORTED",
            result.stderr,
        )

    def test_adapter_list_declares_capabilities_and_enforcement(self) -> None:
        payload = json.loads(self.run_cli("adapter", "list").stdout)

        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["activation_protocol_version"], 2)
        self.assertEqual(
            payload["governance"],
            {
                "policy_schema": 1,
                "fresh_default": "adaptive",
                "profiles": ["adaptive", "strict"],
                "modes": ["explore", "build", "governed"],
            },
        )
        self.assertEqual(
            [item["id"] for item in payload["adapters"]],
            ["codex", "claude", "portable"],
        )
        by_id = {item["id"]: item for item in payload["adapters"]}
        self.assertEqual(by_id["codex"]["enforcement"], "native")
        self.assertEqual(
            by_id["codex"]["capabilities"][
                "automated_enforcement_effective_maximum"
            ],
            "Advisory",
        )
        self.assertEqual(
            by_id["codex"]["capabilities"]["finding_lifecycle"],
            "unsupported",
        )
        self.assertEqual(
            by_id["codex"]["capabilities"]["lifecycle_events"],
            [
                "session_start",
                "subagent_start",
                "before_mutation",
                "stop",
            ],
        )
        self.assertEqual(by_id["portable"]["enforcement"], "cli")
        self.assertEqual(
            by_id["portable"]["capabilities"]["mutation_gate"],
            "cli",
        )
        self.assertEqual(by_id["claude"]["version"], "1.3.4")
        self.assertEqual(by_id["claude"]["enforcement"], "cli")
        self.assertEqual(by_id["claude"]["capabilities"]["skills"], "native")
        self.assertEqual(
            by_id["claude"]["capabilities"]["lifecycle_events"],
            [],
        )

    def test_portable_bootstrap_creates_no_codex_paths(self) -> None:
        preview = json.loads(
            self.run_cli("bootstrap", "--adapter", "portable").stdout
        )
        preview_paths = {
            str(item.get("path"))
            for item in preview["actions"]
            if isinstance(item, dict)
        }

        self.assertEqual(preview["adapters"], ["portable"])
        self.assertNotIn("AGENTS.md", preview_paths)
        self.assertFalse(any(path.startswith(".codex") for path in preview_paths))
        self.assertFalse(any(path.startswith(".agents") for path in preview_paths))
        self.assertEqual(list(self.repo.iterdir()), [])

        applied = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "portable",
                "--apply",
            ).stdout
        )
        self.assertEqual(applied["adapters"], ["portable"])
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".codex").exists())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertFalse((self.repo / ".claude").exists())
        self.assertTrue(
            (self.repo / foundryctl.CORE_ROUTER_PATH).is_file()
        )
        self.assertTrue(
            (self.repo / "docs/agent-guides/README.md").is_file()
        )
        self.run_cli("validate", "--adapter", "portable")
        self.run_cli("spec", "validate")

    def test_claude_bootstrap_creates_native_project_skills_only(self) -> None:
        applied = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "claude",
                "--apply",
            ).stdout
        )

        self.assertEqual(applied["adapters"], ["claude"])
        for relative in (
            foundryctl.CORE_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_SPEC_SKILL_PATH,
        ):
            target = self.repo / relative
            self.assertTrue(target.is_file(), relative)
            self.assertFalse(target.is_symlink(), relative)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".agents").exists())
        self.assertFalse((self.repo / ".codex").exists())
        self.assertFalse(
            (self.repo / "docs/agent-guides/README.md").exists()
        )
        manifest = json.loads(
            (self.repo / foundryctl.HARNESS_MANIFEST).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["adapters"],
            [{"id": "claude", "version": "1.3.4", "enforcement": "cli"}],
        )
        self.assertEqual(
            manifest["governance"],
            {"policy_schema": 1, "profile": "adaptive"},
        )
        self.assertEqual(
            manifest["instruction_files"],
            foundryctl.instruction_files_for_versions(
                foundryctl.CORE_HARNESS_VERSION,
                (("claude", "1.3.4"),),
            ),
        )
        self.run_cli("validate", "--adapter", "claude")

    def test_all_adapters_are_deterministic_idempotent_and_scoped(self) -> None:
        preview = json.loads(
            self.run_cli("bootstrap", "--all-adapters").stdout
        )
        self.assertEqual(preview["adapters"], ["codex", "claude", "portable"])
        preview_paths = {
            item.get("path") for item in preview["actions"]
            if isinstance(item, dict)
        }
        for relative in (
            foundryctl.CORE_PROJECT_SKILL_PATH,
            foundryctl.CODEX_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_SPEC_SKILL_PATH,
            "docs/agent-guides/README.md",
        ):
            self.assertIn(relative, preview_paths)
        self.assertEqual(list(self.repo.iterdir()), [])

        first = json.loads(
            self.run_cli(
                "bootstrap",
                "--all-adapters",
                "--apply",
            ).stdout
        )
        second = json.loads(
            self.run_cli(
                "bootstrap",
                "--all-adapters",
                "--apply",
            ).stdout
        )
        self.assertEqual(first["adapters"], ["codex", "claude", "portable"])
        self.assertEqual(second["created"], [])
        self.assertEqual(second["updated"], [])
        for adapter_id in foundryctl.ADAPTER_ORDER:
            self.run_cli("validate", "--adapter", adapter_id)

        claude_skill = self.repo / foundryctl.CLAUDE_SPEC_SKILL_PATH
        claude_skill.write_text("# drift\n", encoding="utf-8")
        self.run_cli("validate", "--adapter", "codex")
        self.run_cli("validate", "--adapter", "portable")
        result = self.run_cli(
            "validate",
            "--adapter",
            "claude",
            expected=1,
        )
        self.assertIn("HARNESS_CLAUDE_ADAPTER_DRIFT", result.stderr)

    def test_claude_skill_conflict_blocks_every_project_write(self) -> None:
        target = self.repo / foundryctl.CLAUDE_PROJECT_SKILL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("# repository-owned Skill\n", encoding="utf-8")

        preview = json.loads(
            self.run_cli("bootstrap", "--adapter", "claude").stdout
        )
        conflict = next(
            action for action in preview["actions"]
            if action.get("path") == foundryctl.CLAUDE_PROJECT_SKILL_PATH
        )
        self.assertEqual(conflict["action"], "conflict")
        failed = self.run_cli(
            "bootstrap",
            "--adapter",
            "claude",
            "--apply",
            expected=2,
        )
        self.assertIn("generated adapter/Core bytes differ", failed.stderr)
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            "# repository-owned Skill\n",
        )
        self.assertFalse((self.repo / foundryctl.HARNESS_MANIFEST).exists())
        self.assertFalse((self.repo / foundryctl.CORE_PROJECT_SKILL_PATH).exists())

    def test_codex_and_portable_coexist_with_scoped_validation(self) -> None:
        first = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "portable",
                "--apply",
            ).stdout
        )
        self.assertEqual(first["adapters"], ["portable"])
        combined = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "codex",
                "--apply",
            ).stdout
        )
        self.assertEqual(combined["adapters"], ["codex", "portable"])
        manifest = json.loads(
            (self.repo / foundryctl.HARNESS_MANIFEST).read_text(encoding="utf-8")
        )
        paths = [item["path"] for item in manifest["files"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(
            [item["id"] for item in manifest["adapters"]],
            ["codex", "portable"],
        )
        self.assertEqual(paths.count(foundryctl.CORE_ROUTER_PATH), 1)
        self.run_cli("validate", "--adapter", "codex")
        self.run_cli("validate", "--adapter", "portable")

        guide = self.repo / "docs/agent-guides/README.md"
        guide.write_text("# Customized portable route\n", encoding="utf-8")
        self.run_cli("validate", "--adapter", "codex")
        portable = self.run_cli(
            "validate",
            "--adapter",
            "portable",
            expected=1,
        )
        self.assertIn("HARNESS_PORTABLE_ADAPTER_DRIFT", portable.stderr)

    def test_spec_validation_is_adapter_neutral(self) -> None:
        self.run_cli(
            "bootstrap",
            "--adapter",
            "portable",
            "--apply",
        )
        (self.repo / "docs/agent-guides/README.md").unlink()

        self.run_cli("spec", "validate")
        adapter = self.run_cli(
            "validate",
            "--adapter",
            "portable",
            expected=1,
        )
        self.assertIn("HARNESS_PORTABLE_ADAPTER_MISSING", adapter.stderr)

    def test_bootstrap_compatibility_selection_is_explicit(self) -> None:
        implicit = json.loads(self.run_cli("bootstrap").stdout)
        self.assertEqual(implicit["adapters"], ["codex"])
        self.assertTrue(
            any(
                "HARNESS_ADAPTER_DEFAULT_DEPRECATED" in warning
                for warning in implicit["warnings"]
            )
        )
        conflict = self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--adapter",
            "portable",
            expected=2,
        )
        self.assertIn("HARNESS_ADAPTER_SELECTION_CONFLICT", conflict.stderr)
        all_conflict = self.run_cli(
            "bootstrap",
            "--all-adapters",
            "--adapter",
            "codex",
            expected=2,
        )
        self.assertIn(
            "HARNESS_ADAPTER_SELECTION_CONFLICT",
            all_conflict.stderr,
        )
        duplicate = self.run_cli(
            "bootstrap",
            "--adapter",
            "codex",
            "--adapter",
            "codex",
            expected=2,
        )
        self.assertIn("HARNESS_ADAPTER_DUPLICATE", duplicate.stderr)

    def test_codex_bootstrap_apply_is_idempotent_and_validated(self) -> None:
        first = json.loads(
            self.run_cli(
                "bootstrap",
                "--profile",
                "codex",
                "--apply",
            ).stdout
        )

        self.assertEqual(first["mode"], "apply")
        required = (
            "AGENTS.md",
            "ARCHITECTURE.md",
            "docs/index.md",
            "docs/QUALITY_SCORE.md",
            "docs/RELIABILITY.md",
            "docs/SECURITY.md",
            "docs/design-docs/index.md",
            ".repo-foundry/engineering-specs/spec_router.py",
            ".repo-foundry/skills/repo-foundry-ai/SKILL.md",
            ".agents/skills/repo-foundry-ai/SKILL.md",
            ".agents/skills/engineering-specs/SKILL.md",
            ".agents/skills/engineering-specs/agents/openai.yaml",
            ".agents/skills/engineering-specs/scripts/spec_router.py",
            ".codex/hooks.json",
        )
        for relative in required:
            self.assertTrue((self.repo / relative).is_file(), relative)
        agents = self.repo / "AGENTS.md"
        self.assertLessEqual(
            len(agents.read_text(encoding="utf-8").splitlines()),
            80,
        )

        manifest = json.loads(
            (
                self.repo / "docs" / ".engineering" / "harness.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["owner"], "repo-foundry")
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(
            manifest["producer"],
            {
                "name": "repo-foundry",
                "version": foundryctl.REPO_FOUNDRY_VERSION,
            },
        )
        self.assertEqual(
            manifest["core"],
            {"version": foundryctl.CORE_HARNESS_VERSION},
        )
        self.assertEqual(
            manifest["adapters"],
            [{"id": "codex", "version": "2.4.5", "enforcement": "native"}],
        )
        self.assertEqual(
            manifest["governance"],
            {"policy_schema": 1, "profile": "adaptive"},
        )
        self.assertEqual(
            manifest["instruction_files"],
            foundryctl.instruction_files_for_versions(
                foundryctl.CORE_HARNESS_VERSION,
                (("codex", "2.4.5"),),
            ),
        )
        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            [
                item[0]
                for item in foundryctl.selected_file_assets(("codex",))
            ],
        )
        self.assertTrue(
            all(
                item["template_sha256"] == item["installed_sha256"]
                for item in manifest["files"]
            )
        )
        self.assertEqual(
            {item["owner_kind"] for item in manifest["files"]},
            {"core", "adapter"},
        )
        self.assertEqual(manifest["applied_migrations"], [])
        spec_manifest = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(spec_manifest["owner"], "repo-foundry")
        self.assertEqual(spec_manifest["specs"], ["core/semantic-naming"])
        spec_lock = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.lock.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(spec_lock["owner"], "repo-foundry")
        self.assertEqual(
            [item["id"] for item in spec_lock["specs"]],
            ["core/semantic-naming"],
        )
        self.assertEqual(
            spec_lock["catalog"]["resolved_revision"],
            self.catalog_commit,
        )
        self.assertEqual(
            spec_lock["catalog"]["source"],
            {
                "kind": "git",
                "url": self.catalog_repository.resolve().as_uri(),
                "ref": "main",
            },
        )
        self.assertTrue(
            (
                self.repo
                / "docs"
                / "agent-guides"
                / "managed"
                / "core"
                / "semantic-naming.md"
            ).is_file()
        )
        self.assertIn(
            "docs/agent-guides/managed/index.md",
            agents.read_text(encoding="utf-8"),
        )
        config = json.loads(
            (
                self.repo / "docs" / ".epctl" / "config.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("docs/design-docs", config["architecture_roots"])
        self.run_cli("validate", "--harness")
        self.run_cli("spec", "validate")
        self.run_ep_cli("validate")

        before = {
            relative: (self.repo / relative).read_bytes()
            for relative in (
                *required,
                "docs/.engineering/harness.json",
                "docs/.engineering/specs.json",
                "docs/.engineering/specs.lock.json",
                "docs/agent-guides/managed/index.md",
                "docs/agent-guides/managed/core/semantic-naming.md",
                "docs/.epctl/config.json",
            )
        }
        second = json.loads(
            self.run_cli(
                "bootstrap",
                "--profile",
                "codex",
                "--apply",
            ).stdout
        )
        after = {
            relative: (self.repo / relative).read_bytes()
            for relative in before
        }

        self.assertEqual(second["created"], [])
        self.assertEqual(second["updated"], [])
        self.assertEqual(after, before)

    def test_cli_reports_the_distribution_version(self) -> None:
        result = self.run_cli("--version")

        self.assertEqual(
            result.stdout.strip(),
            f"RepoFoundry AI {foundryctl.REPO_FOUNDRY_VERSION}",
        )

    def test_harness_validation_resolves_design_adr_refs_from_history_packs(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        adr = Path(
            self.run_ep_cli(
                "new-adr",
                "--slug",
                "historical-design-input",
                "--title",
                "Historical design input",
            ).stdout.strip()
        )
        text = adr.read_text(encoding="utf-8")
        for placeholder, value in {
            "REPLACE_WITH_SCOPE": "test architecture boundary",
            "REPLACE_WITH_CONSTRAINT": (
                "The implementation must preserve the test boundary."
            ),
            "REPLACE_WITH_CONFIRMATION": "Run the architecture contract test.",
        }.items():
            text = text.replace(placeholder, value)
        text = re.sub(
            r"<!--\s*REQUIRED(?:_[A-Z_]+)?\s*:[\s\S]*?-->",
            "Recorded evidence.",
            text,
        )
        text = re.sub(r"(?m)^-\s+\[ \]", "- [x]", text)
        adr.write_text(text, encoding="utf-8")
        self.run_ep_cli(
            "decide-adr",
            "ADR-001",
            "--outcome",
            "rejected",
            "--decision-maker",
            "Test Decision Owner",
        )

        designctl = foundryctl.load_design_ctl()
        designctl.new_design(
            self.repo,
            slug="historical-input-consumer",
            title="Historical input consumer",
            layout="single",
            research_refs=[],
            research_not_required_reason=(
                "The bounded fixture has authoritative inputs."
            ),
            adr_refs=["ADR-001"],
            dependencies=[],
            author="Test Author",
            owner="Test Owner",
        )
        packed = json.loads(
            self.run_ep_cli(
                "pack-historical-adrs",
                "ADR-001",
                "--packed-by",
                "Test Archivist",
                "--reason",
                "Compact a terminal design input fixture.",
                "--apply",
                "--json",
            ).stdout
        )

        self.assertTrue(packed["applied"])
        self.assertFalse(adr.exists())
        validation = self.run_cli("validate", "--harness")
        self.assertNotIn("ADR not found: ADR-001", validation.stderr)

    def test_084_manifest_can_upgrade_after_core_skill_template_change(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        skill_path = self.repo / foundryctl.CORE_PROJECT_SKILL_PATH
        history_pack_guidance = (
            "- Route ADR corpus reduction to the Engineering Execution Plan workflow. "
            "Semantic\n"
            "  consolidation remains an authorized ADR lifecycle change; physical "
            "compaction\n"
            "  may only use its explicit lossless terminal History Pack preview/apply "
            "and exact\n"
            "  unpack contract. A Harness upgrade never packs ADRs automatically.\n"
        )
        old_skill = skill_path.read_text(encoding="utf-8").replace(
            history_pack_guidance,
            "",
        )
        self.assertNotIn("History Pack", old_skill)
        skill_path.write_text(old_skill, encoding="utf-8")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer"]["version"] = "0.8.4"
        manifest["core"]["version"] = "1.5.0"
        strip_memory_assets(self.repo, manifest)
        old_digest = foundryctl.sha256_text(old_skill)
        for record in manifest["files"]:
            if record["owner_kind"] != "core":
                continue
            record["template_version"] = "1.5.0"
            if record["path"] == foundryctl.CORE_PROJECT_SKILL_PATH:
                record["template_sha256"] = old_digest
                record["installed_sha256"] = old_digest
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        validation = self.run_cli("validate", "--harness", expected=1)
        self.assertIn("HARNESS_CORE_UPGRADE_AVAILABLE", validation.stderr)
        self.assertIn("HARNESS_CORE_SKILL_DRIFT", validation.stderr)
        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertEqual(
            preview["to"]["core"],
            foundryctl.CORE_HARNESS_VERSION,
        )
        self.assertIn(
            foundryctl.CORE_PROJECT_SKILL_PATH,
            {
                item["path"]
                for item in preview["actions"]
                if item["action"] == "replace_file"
            },
        )
        self.assertEqual(skill_path.read_text(encoding="utf-8"), old_skill)

        self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            "--apply",
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            migrated["core"]["version"],
            foundryctl.CORE_HARNESS_VERSION,
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [
                f"core-1.5.0-to-{foundryctl.CORE_HARNESS_VERSION}",
                f"distribution-0.8.4-to-{foundryctl.REPO_FOUNDRY_VERSION}",
            ],
        )
        self.assertEqual(
            skill_path.read_text(encoding="utf-8"),
            foundryctl.asset_text("core/repo-foundry-ai/SKILL.md.template"),
        )
        self.run_cli("validate", "--harness")

    def test_090_upgrade_installs_maintenance_guidance_without_packing(self) -> None:
        self.run_cli("bootstrap", "--all-adapters", "--apply")
        adr_paths: list[Path] = []
        for index in range(3):
            adr = Path(
                self.run_ep_cli(
                    "new-adr",
                    "--slug",
                    f"terminal-maintenance-{index}",
                    "--title",
                    f"Terminal maintenance {index}",
                ).stdout.strip()
            )
            text = adr.read_text(encoding="utf-8")
            text = re.sub(
                r"<!--\s*REQUIRED(?:_[A-Z_]+)?\s*:[\s\S]*?-->",
                "Recorded evidence.",
                text,
            )
            text = re.sub(r"(?m)^-\s+\[ \]", "- [x]", text)
            for placeholder, value in {
                "REPLACE_WITH_SCOPE": "test maintenance boundary",
                "REPLACE_WITH_CONSTRAINT": "The fixture must remain unchanged.",
                "REPLACE_WITH_CONFIRMATION": "Compare exact source bytes.",
            }.items():
                text = text.replace(placeholder, value)
            adr.write_text(text, encoding="utf-8")
            self.run_ep_cli(
                "decide-adr",
                f"ADR-{index + 1:03d}",
                "--outcome",
                "rejected",
                "--decision-maker",
                "Test Decision Owner",
            )
            adr_paths.append(adr)
        adr_bytes = {path: path.read_bytes() for path in adr_paths}

        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer"]["version"] = "0.8.8"
        manifest["core"]["version"] = "1.5.1"
        strip_memory_assets(self.repo, manifest)
        for adapter in manifest["adapters"]:
            if adapter["id"] == "portable":
                adapter["version"] = "1.3.0"

        old_files = {
            foundryctl.CORE_PROJECT_SKILL_PATH: (
                "1.5.1",
                foundryctl.asset_text("core/repo-foundry-ai/SKILL.md.template").replace(
                    "adr-maintenance",
                    "adr-health",
                ),
            ),
            "docs/agent-guides/README.md": (
                "1.3.0",
                foundryctl.asset_text("adapters/portable/agent-guide.md").replace(
                    "adr-maintenance",
                    "adr-health",
                ),
            ),
        }
        for relative, (version, text) in old_files.items():
            (self.repo / relative).write_text(text, encoding="utf-8")
            digest = foundryctl.sha256_text(text)
            record = next(
                item for item in manifest["files"] if item["path"] == relative
            )
            record["template_version"] = version
            record["template_sha256"] = digest
            record["installed_sha256"] = digest
        for record in manifest["files"]:
            if record["owner_kind"] == "core":
                record["template_version"] = "1.5.1"
            elif record.get("owner_id") == "portable":
                record["template_version"] = "1.3.0"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertEqual(
            {
                item["path"]
                for item in preview["actions"]
                if item["action"] == "replace_file"
            },
            set(old_files),
        )
        self.assertFalse((self.repo / "docs/.epctl/adr-packs").exists())

        self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            "--apply",
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["core"]["version"], "1.6.3")
        self.assertEqual(
            next(
                adapter["version"]
                for adapter in migrated["adapters"]
                if adapter["id"] == "portable"
            ),
            "1.3.4",
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [
                "core-1.5.1-to-1.6.3",
                "adapter-portable-1.3.0-to-1.3.4",
                f"distribution-0.8.8-to-{foundryctl.REPO_FOUNDRY_VERSION}",
            ],
        )
        self.assertEqual(adr_bytes, {path: path.read_bytes() for path in adr_paths})
        self.assertFalse((self.repo / "docs/.epctl/adr-packs").exists())
        self.assertIn(
            "adr-maintenance",
            (self.repo / foundryctl.CORE_PROJECT_SKILL_PATH).read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "adr-maintenance",
            (self.repo / "docs/agent-guides/README.md").read_text(
                encoding="utf-8"
            ),
        )
        self.run_cli("validate", "--harness")

    def test_distribution_upgrade_adds_empty_decision_view_infrastructure(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer"]["version"] = PREVIOUS_DISTRIBUTION
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        registry = self.repo / "docs/.epctl/decision-views.json"
        index = self.repo / "docs/DECISION-VIEWS.md"
        view_root = self.repo / "docs/decision-views"
        view_marker = view_root / ".gitkeep"
        registry.unlink()
        index.unlink()
        view_marker.unlink()
        view_root.rmdir()
        adr = self.repo / "docs/adr/adr-900_existing-source.md"
        adr.write_text(
            "---\n"
            "doc_type: adr\n"
            "title: Existing source\n"
            "status: accepted\n"
            "created: 2026-01-01\n"
            "last_verified: 2026-01-02\n"
            "depends_on: []\n"
            "amends: []\n"
            "---\n\n"
            "# ADR-900: Existing source\n",
            encoding="utf-8",
        )
        adr_before = adr.read_bytes()

        preview = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
            ).stdout
        )
        create_paths = {
            str(item["path"])
            for item in preview["actions"]
            if item["action"] in {"create_file", "create_directory"}
        }
        self.assertEqual(
            create_paths,
            {
                "docs/decision-views/",
                "docs/decision-views/.gitkeep",
                "docs/DECISION-VIEWS.md",
                "docs/.epctl/decision-views.json",
            },
        )
        self.assertFalse(registry.exists())
        self.assertFalse(index.exists())
        self.assertFalse(view_root.exists())

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        self.assertEqual(
            set(applied["created"]),
            {
                "docs/decision-views/",
                "docs/decision-views/.gitkeep",
                "docs/DECISION-VIEWS.md",
                "docs/.epctl/decision-views.json",
            },
        )
        self.assertEqual(
            json.loads(registry.read_text(encoding="utf-8")),
            {"version": 1, "views": []},
        )
        self.assertTrue(index.is_file())
        self.assertTrue(view_root.is_dir())
        self.assertTrue(view_marker.is_file())
        self.assertEqual(adr.read_bytes(), adr_before)
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            migrated["producer"]["version"],
            foundryctl.REPO_FOUNDRY_VERSION,
        )
        self.assertIn(
            (
                f"distribution-{PREVIOUS_DISTRIBUTION}-to-"
                f"{foundryctl.REPO_FOUNDRY_VERSION}"
            ),
            [item["id"] for item in migrated["applied_migrations"]],
        )
        self.run_ep_cli("reindex")
        self.run_ep_cli("validate")
        self.assertEqual(adr.read_bytes(), adr_before)

    def test_legacy_schema_upgrade_is_preview_first_and_idempotent(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "harness.json"
        )
        manifest_path.write_text(
            json.dumps(
                foundryctl.legacy_codex_harness_manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        before_manifest = manifest_path.read_bytes()
        before_files = {
            relative: (self.repo / relative).read_bytes()
            for relative in foundryctl.CODEX_SEEDED_FILES
        }

        validation = self.run_cli("validate", "--harness")
        self.assertIn("HARNESS_SCHEMA_UPGRADE_AVAILABLE", validation.stderr)
        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )

        self.assertEqual(preview["mode"], "dry-run")
        self.assertEqual(preview["from"]["schema"], 1)
        self.assertEqual(preview["to"]["schema"], 3)
        self.assertEqual(preview["updated"], [])
        self.assertEqual(manifest_path.read_bytes(), before_manifest)
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in foundryctl.CODEX_SEEDED_FILES
            },
            before_files,
        )

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(applied["mode"], "apply")
        self.assertEqual(
            applied["updated"],
            ["docs/.engineering/harness.json"],
        )
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(
            migrated["adapters"],
            [{"id": "codex", "version": "2.4.5", "enforcement": "native"}],
        )
        self.assertEqual(
            migrated["governance"],
            {"policy_schema": 1, "profile": "strict"},
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            ["harness-schema-v1-to-v3"],
        )
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in foundryctl.CODEX_SEEDED_FILES
            },
            before_files,
        )
        second = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        self.assertEqual(second["updated"], [])
        self.assertEqual(
            json.loads(manifest_path.read_text(encoding="utf-8")),
            migrated,
        )

    def test_legacy_upgrade_adds_missing_generated_profile_seeds(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "harness.json"
        )
        manifest_path.write_text(
            json.dumps(
                foundryctl.legacy_codex_harness_manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        for relative in foundryctl.CODEX_GENERATED_FILES:
            (self.repo / relative).unlink()

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertEqual(
            {
                item["path"] for item in preview["actions"]
                if item["action"] == "create_file"
            },
            set(foundryctl.CODEX_GENERATED_FILES),
        )
        self.assertTrue(
            all(
                not (self.repo / relative).exists()
                for relative in foundryctl.CODEX_GENERATED_FILES
            )
        )

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )

        self.assertEqual(
            set(applied["created"]),
            set(foundryctl.CODEX_GENERATED_FILES),
        )
        for relative, asset in foundryctl.CODEX_ROUTER_FILE_ASSETS:
            self.assertEqual(
                (self.repo / relative).read_text(encoding="utf-8"),
                foundryctl.asset_text(asset),
            )
        self.run_cli("validate", "--harness")

    def test_schema3_component_upgrade_adds_project_skills_safely(self) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.write_pre_project_skill_schema3_manifest()

        validation = self.run_cli("validate", "--harness")
        self.assertIn("HARNESS_CORE_UPGRADE_AVAILABLE", validation.stderr)
        self.assertIn("HARNESS_ADAPTER_UPGRADE_AVAILABLE", validation.stderr)
        self.assertIn("HARNESS_COMPONENT_UPGRADE_AVAILABLE", validation.stderr)
        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertEqual(
            {
                item["path"] for item in preview["actions"]
                if item["action"] == "create_file"
            },
            {
                foundryctl.CORE_PROJECT_SKILL_PATH,
                foundryctl.CODEX_PROJECT_SKILL_PATH,
                *CORE_MEMORY_PATHS,
            },
        )
        self.assertFalse((self.repo / foundryctl.CORE_PROJECT_SKILL_PATH).exists())
        self.assertFalse((self.repo / foundryctl.CODEX_PROJECT_SKILL_PATH).exists())

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        self.assertEqual(
            set(applied["created"]),
            {
                foundryctl.CORE_PROJECT_SKILL_PATH,
                foundryctl.CODEX_PROJECT_SKILL_PATH,
                *CORE_MEMORY_PATHS,
            },
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            migrated["core"]["version"],
            foundryctl.CORE_HARNESS_VERSION,
        )
        self.assertEqual(migrated["adapters"][0]["version"], "2.4.5")
        self.assertEqual(
            migrated["governance"],
            {"policy_schema": 1, "profile": "strict"},
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [
                "components-add-engineering-design",
                f"core-1.0.0-to-{foundryctl.CORE_HARNESS_VERSION}",
                "adapter-codex-2.0.0-to-2.4.5",
            ],
        )
        self.run_cli("validate", "--harness")

    def test_old_schema3_can_register_claude_in_one_bootstrap(self) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.write_pre_project_skill_schema3_manifest()

        applied = json.loads(
            self.run_cli(
                "bootstrap",
                "--adapter",
                "claude",
                "--apply",
            ).stdout
        )
        self.assertEqual(applied["adapters"], ["codex", "claude"])
        for relative in (
            foundryctl.CORE_PROJECT_SKILL_PATH,
            foundryctl.CODEX_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_PROJECT_SKILL_PATH,
            foundryctl.CLAUDE_SPEC_SKILL_PATH,
        ):
            self.assertIn(relative, applied["created"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in manifest["adapters"]],
            ["codex", "claude"],
        )
        self.assertEqual(
            [item["id"] for item in manifest["applied_migrations"]],
            [
                "components-add-engineering-design",
                f"core-1.0.0-to-{foundryctl.CORE_HARNESS_VERSION}",
                "adapter-codex-2.0.0-to-2.4.5",
            ],
        )
        self.run_cli("validate", "--harness")

    def test_schema2_upgrade_splits_router_and_preserves_spec_state(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = self.write_schema2_manifest()
        core_router = self.repo / foundryctl.CORE_ROUTER_PATH
        core_router.unlink()
        spec_paths = (
            "docs/.engineering/specs.json",
            "docs/.engineering/specs.lock.json",
            "docs/agent-guides/managed/index.md",
            "docs/agent-guides/managed/core/semantic-naming.md",
        )
        before_specs = {
            relative: (self.repo / relative).read_bytes()
            for relative in spec_paths
        }

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )

        self.assertEqual(applied["created"], [foundryctl.CORE_ROUTER_PATH])
        self.assertTrue(core_router.is_file())
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            ["harness-schema-v2-to-v3"],
        )
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in spec_paths
            },
            before_specs,
        )
        self.run_cli("validate", "--harness")

    def test_distribution_upgrade_preserves_locked_spec_state(self) -> None:
        self.run_cli(
            "bootstrap",
            "--adapter",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer"]["version"] = "0.6.0"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before_manifest = manifest_path.read_bytes()
        spec_paths = (
            "docs/.engineering/specs.json",
            "docs/.engineering/specs.lock.json",
            "docs/agent-guides/managed/index.md",
            "docs/agent-guides/managed/requirements.json",
            "docs/agent-guides/managed/core/semantic-naming.md",
            "docs/agent-guides/managed/languages/go.md",
        )
        before_specs = {
            relative: (self.repo / relative).read_bytes()
            for relative in spec_paths
        }

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )

        self.assertEqual(preview["from"]["distribution"], "0.6.0")
        self.assertEqual(
            preview["to"]["distribution"],
            foundryctl.REPO_FOUNDRY_VERSION,
        )
        self.assertEqual(
            [
                item["action"]
                for item in preview["actions"]
                if item["action"] != "preserve"
            ],
            ["update_manifest"],
        )
        self.assertEqual(manifest_path.read_bytes(), before_manifest)
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in spec_paths
            },
            before_specs,
        )

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            applied["updated"],
            [foundryctl.HARNESS_MANIFEST],
        )
        self.assertEqual(
            migrated["producer"]["version"],
            foundryctl.REPO_FOUNDRY_VERSION,
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [f"distribution-0.6.0-to-{foundryctl.REPO_FOUNDRY_VERSION}"],
        )
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in spec_paths
            },
            before_specs,
        )
        self.run_cli("validate", "--harness")
        self.run_cli("spec", "validate")

    def test_041_upgrade_installs_lightweight_analysis_routing(self) -> None:
        self.run_cli("bootstrap", "--all-adapters", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer"]["version"] = "0.4.0"
        manifest["core"]["version"] = "1.3.0"
        strip_memory_assets(self.repo, manifest)
        old_adapter_versions = {
            "codex": "2.3.0",
            "claude": "1.2.0",
            "portable": "1.2.0",
        }
        for adapter in manifest["adapters"]:
            adapter["version"] = old_adapter_versions[adapter["id"]]

        target_assets = {
            foundryctl.CORE_PROJECT_SKILL_PATH: (
                "core/repo-foundry-ai/SKILL.md.template",
                "1.3.0",
                "---\nname: repo-foundry-ai\ndescription: Old Core Skill.\n---\n",
            ),
            foundryctl.CODEX_PROJECT_SKILL_PATH: (
                "adapters/codex/repo-foundry-ai/SKILL.md.template",
                "2.3.0",
                "---\nname: repo-foundry-ai\ndescription: Old Codex Skill.\n---\n",
            ),
            foundryctl.CLAUDE_PROJECT_SKILL_PATH: (
                "adapters/claude/repo-foundry-ai/SKILL.md.template",
                "1.2.0",
                "---\nname: repo-foundry-ai\ndescription: Old Claude Skill.\n---\n",
            ),
            "docs/agent-guides/README.md": (
                "adapters/portable/agent-guide.md",
                "1.2.0",
                "# Old Portable Guide\n",
            ),
        }
        for relative, (_, _, old_text) in target_assets.items():
            (self.repo / relative).write_text(old_text, encoding="utf-8")
        for record in manifest["files"]:
            if record["owner_kind"] == "core":
                record["template_version"] = "1.3.0"
            else:
                record["template_version"] = old_adapter_versions[
                    record["owner_id"]
                ]
            target = target_assets.get(record["path"])
            if target is None:
                continue
            _, old_version, old_text = target
            digest = foundryctl.sha256_text(old_text)
            self.assertEqual(record["template_version"], old_version)
            record["template_sha256"] = digest
            record["installed_sha256"] = digest
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertEqual(
            {
                item["path"]
                for item in preview["actions"]
                if item["action"] == "replace_file"
            },
            set(target_assets),
        )
        for relative, (_, _, old_text) in target_assets.items():
            self.assertEqual(
                (self.repo / relative).read_text(encoding="utf-8"),
                old_text,
            )

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative, (asset, _, _) in target_assets.items():
            self.assertIn(relative, applied["updated"])
            self.assertEqual(
                (self.repo / relative).read_text(encoding="utf-8"),
                foundryctl.asset_text(asset),
            )
        self.assertEqual(
            migrated["producer"]["version"],
            foundryctl.REPO_FOUNDRY_VERSION,
        )
        self.assertEqual(
            migrated["core"]["version"],
            foundryctl.CORE_HARNESS_VERSION,
        )
        self.assertEqual(
            [adapter["version"] for adapter in migrated["adapters"]],
            [
                foundryctl.CODEX_ADAPTER_VERSION,
                foundryctl.CLAUDE_ADAPTER_VERSION,
                foundryctl.PORTABLE_ADAPTER_VERSION,
            ],
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [
                f"core-1.3.0-to-{foundryctl.CORE_HARNESS_VERSION}",
                "adapter-codex-2.3.0-to-2.4.5",
                "adapter-claude-1.2.0-to-1.3.4",
                f"adapter-portable-1.2.0-to-{foundryctl.PORTABLE_ADAPTER_VERSION}",
                f"distribution-0.4.0-to-{foundryctl.REPO_FOUNDRY_VERSION}",
            ],
        )
        self.run_cli("validate", "--harness")

    def test_030_core_upgrade_installs_the_selection_decision_gate(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_skill = (
            "---\n"
            "name: repo-foundry-ai\n"
            "description: Legacy project workflow fixture.\n"
            "---\n\n"
            "# RepoFoundry AI project workflow\n"
        )
        skill_path = self.repo / foundryctl.CORE_PROJECT_SKILL_PATH
        skill_path.write_text(old_skill, encoding="utf-8")
        manifest["producer"]["version"] = "0.3.0"
        manifest["core"]["version"] = "1.2.0"
        strip_memory_assets(self.repo, manifest)
        for record in manifest["files"]:
            if record["owner_kind"] != "core":
                continue
            record["template_version"] = "1.2.0"
            installed = (
                old_skill
                if record["path"] == foundryctl.CORE_PROJECT_SKILL_PATH
                else (self.repo / record["path"]).read_text(encoding="utf-8")
            )
            digest = foundryctl.sha256_text(installed)
            record["template_sha256"] = digest
            record["installed_sha256"] = digest
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        spec_paths = (
            "docs/.engineering/specs.json",
            "docs/.engineering/specs.lock.json",
            "docs/agent-guides/managed/index.md",
            "docs/agent-guides/managed/requirements.json",
        )
        before_specs = {
            relative: (self.repo / relative).read_bytes()
            for relative in spec_paths
        }

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertIn(
            foundryctl.CORE_PROJECT_SKILL_PATH,
            [
                item["path"]
                for item in preview["actions"]
                if item["action"] == "replace_file"
            ],
        )
        self.assertEqual(skill_path.read_text(encoding="utf-8"), old_skill)

        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn(foundryctl.CORE_PROJECT_SKILL_PATH, applied["updated"])
        self.assertEqual(
            skill_path.read_text(encoding="utf-8"),
            foundryctl.asset_text("core/repo-foundry-ai/SKILL.md.template"),
        )
        self.assertEqual(
            migrated["producer"]["version"],
            foundryctl.REPO_FOUNDRY_VERSION,
        )
        self.assertEqual(
            migrated["core"]["version"],
            foundryctl.CORE_HARNESS_VERSION,
        )
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            [
                f"core-1.2.0-to-{foundryctl.CORE_HARNESS_VERSION}",
                f"distribution-0.3.0-to-{foundryctl.REPO_FOUNDRY_VERSION}",
            ],
        )
        self.assertEqual(
            {
                relative: (self.repo / relative).read_bytes()
                for relative in spec_paths
            },
            before_specs,
        )
        self.run_cli("validate", "--harness")
        self.run_cli("spec", "validate")

    def test_legacy_upgrade_preserves_customized_seed_without_a_base(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        architecture = self.repo / "ARCHITECTURE.md"
        custom = "# Repository-owned architecture\n"
        architecture.write_text(custom, encoding="utf-8")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "harness.json"
        )
        manifest_path.write_text(
            json.dumps(
                foundryctl.legacy_codex_harness_manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = next(
            item for item in migrated["files"]
            if item["path"] == "ARCHITECTURE.md"
        )

        self.assertEqual(architecture.read_text(encoding="utf-8"), custom)
        self.assertEqual(record["template_version"], "legacy-unversioned")
        self.assertIsNone(record["template_sha256"])
        self.assertIsNone(record["installed_sha256"])
        self.assertTrue(
            any(
                "HARNESS_CUSTOMIZED_SEED_PRESERVED" in warning
                for warning in result["warnings"]
            )
        )

    def test_upgrade_replaces_an_unmodified_versioned_seed(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        architecture = self.repo / "ARCHITECTURE.md"
        old_seed = "# Old seeded architecture\n"
        architecture.write_text(old_seed, encoding="utf-8")
        old_digest = foundryctl.sha256_text(old_seed)
        manifest_path = self.write_schema2_manifest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = next(
            item for item in manifest["files"]
            if item["path"] == "ARCHITECTURE.md"
        )
        record["template_version"] = "1.0.0"
        record["template_sha256"] = old_digest
        record["installed_sha256"] = old_digest
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertIn(
            "ARCHITECTURE.md",
            [
                item["path"] for item in preview["actions"]
                if item["action"] == "replace_file"
            ],
        )
        applied = json.loads(
            self.run_cli(
                "upgrade",
                "--to",
                foundryctl.REPO_FOUNDRY_VERSION,
                "--apply",
            ).stdout
        )

        self.assertEqual(
            architecture.read_text(encoding="utf-8"),
            foundryctl.asset_text("core/harness-architecture.md"),
        )
        self.assertEqual(
            applied["updated"],
            ["ARCHITECTURE.md", "docs/.engineering/harness.json"],
        )
        migrated = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(
            [item["id"] for item in migrated["applied_migrations"]],
            ["harness-schema-v2-to-v3"],
        )

    def test_upgrade_refuses_to_overwrite_a_modified_versioned_seed(
        self,
    ) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        adapter = (
            self.repo
            / ".agents"
            / "skills"
            / "engineering-specs"
            / "scripts"
            / "spec_router.py"
        )
        old_seed = "# Old generated adapter\n"
        old_digest = foundryctl.sha256_text(old_seed)
        adapter.write_text(
            old_seed + "\nRepository customization.\n",
            encoding="utf-8",
        )
        manifest_path = self.write_schema2_manifest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = next(
            item for item in manifest["files"]
            if item["path"]
            == ".agents/skills/engineering-specs/scripts/spec_router.py"
        )
        record["template_version"] = "1.0.0"
        record["template_sha256"] = old_digest
        record["installed_sha256"] = old_digest
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before_manifest = manifest_path.read_bytes()
        before_file = adapter.read_bytes()

        preview = json.loads(
            self.run_cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION).stdout
        )
        self.assertIn(
            ".agents/skills/engineering-specs/scripts/spec_router.py",
            [
                item["path"] for item in preview["actions"]
                if item["action"] == "conflict"
            ],
        )
        failed = self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            "--apply",
            expected=2,
        )

        self.assertIn("merge explicitly", failed.stderr)
        self.assertEqual(manifest_path.read_bytes(), before_manifest)
        self.assertEqual(adapter.read_bytes(), before_file)

    def test_upgrade_rejects_future_state_and_unavailable_targets(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "harness.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        future_schema = json.loads(json.dumps(manifest))
        future_schema["schema_version"] = 4
        manifest_path.write_text(
            json.dumps(future_schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        schema_result = self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            expected=2,
        )
        self.assertIn("HARNESS_SCHEMA_TOO_NEW", schema_result.stderr)

        future_product = json.loads(json.dumps(manifest))
        future_product["producer"]["version"] = "9.0.0"
        manifest_path.write_text(
            json.dumps(future_product, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        product_result = self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            expected=2,
        )
        self.assertIn("HARNESS_PRODUCER_TOO_NEW", product_result.stderr)

        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        target_result = self.run_cli(
            "upgrade",
            "--to",
            "0.3.1",
            expected=2,
        )
        self.assertIn("UPGRADE_TARGET_UNAVAILABLE", target_result.stderr)

    def test_schema3_fails_closed_on_future_component_versions(self) -> None:
        self.run_cli("bootstrap", "--adapter", "codex", "--apply")
        manifest_path = self.repo / foundryctl.HARNESS_MANIFEST
        original = json.loads(manifest_path.read_text(encoding="utf-8"))

        cases = (
            ("HARNESS_CORE_TOO_NEW", ("core", "version")),
            ("HARNESS_ADAPTER_TOO_NEW", ("adapters", 0, "version")),
            ("HARNESS_TEMPLATE_TOO_NEW", ("files", 0, "template_version")),
            (
                "HARNESS_MIGRATION_TOO_NEW",
                ("applied_migrations", 0, "applied_by_version"),
            ),
        )
        for expected_code, path in cases:
            payload = json.loads(json.dumps(original))
            if path[0] == "applied_migrations":
                payload["applied_migrations"] = [
                    {
                        "id": "future-migration",
                        "kind": "schema",
                        "from": "3",
                        "to": "4",
                        "applied_by_version": "9.0.0",
                    }
                ]
            elif len(path) == 2:
                payload[path[0]][path[1]] = "9.0.0"
            else:
                payload[path[0]][path[1]][path[2]] = "9.0.0"
            manifest_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_cli("validate", "--harness", expected=1)
            self.assertIn(expected_code, result.stderr)

        incompatible = json.loads(json.dumps(original))
        incompatible["core"]["version"] = "1.0.0"
        manifest_path.write_text(
            json.dumps(incompatible, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = self.run_cli("validate", "--harness", expected=1)
        self.assertIn("HARNESS_COMPONENT_INCOMPATIBLE", result.stderr)

        manifest_path.write_text(
            json.dumps(original, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.run_cli("validate", "--harness")

    def test_upgrade_rolls_back_when_post_validation_fails(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "harness.json"
        )
        manifest_path.write_text(
            json.dumps(
                foundryctl.legacy_codex_harness_manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        config_path = self.repo / "docs" / ".epctl" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["architecture_roots"].remove("docs/design-docs")
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for relative in foundryctl.CODEX_GENERATED_FILES:
            (self.repo / relative).unlink()
        before = manifest_path.read_bytes()

        result = self.run_cli(
            "upgrade",
            "--to",
            foundryctl.REPO_FOUNDRY_VERSION,
            "--apply",
            expected=2,
        )

        self.assertIn("validation failed after upgrade", result.stderr)
        self.assertEqual(manifest_path.read_bytes(), before)
        self.assertTrue(
            all(
                not (self.repo / relative).exists()
                for relative in foundryctl.CODEX_GENERATED_FILES
            )
        )

    def test_legacy_manifest_owners_remain_readable(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        state = self.repo / "docs" / ".engineering"
        for name in ("harness.json", "specs.json", "specs.lock.json"):
            path = state / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["owner"] = "engineering-workflow"
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        index = (
            self.repo / "docs" / "agent-guides" / "managed" / "index.md"
        )
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                "Generated by repo-foundry",
                "Generated by engineering-workflow",
            ),
            encoding="utf-8",
        )
        requirement_index = (
            self.repo
            / "docs"
            / "agent-guides"
            / "managed"
            / "requirements.json"
        )
        requirement_payload = json.loads(
            requirement_index.read_text(encoding="utf-8")
        )
        requirement_payload["owner"] = "engineering-workflow"
        requirement_index.write_text(
            json.dumps(requirement_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        validation = self.run_cli("validate", "--harness")
        self.assertIn("HARNESS_LEGACY_OWNER", validation.stderr)
        self.assertIn("SPEC_LEGACY_OWNER", validation.stderr)
        spec_validation = self.run_cli("spec", "validate")
        self.assertIn("SPEC_LEGACY_OWNER", spec_validation.stderr)

        preview = json.loads(
            self.run_cli("bootstrap", "--profile", "codex").stdout
        )
        conflicts = [
            action
            for action in preview["actions"]
            if action["action"] == "conflict"
        ]
        self.assertEqual(conflicts, [])

    def test_codex_bootstrap_preserves_existing_files_at_line_limit(
        self,
    ) -> None:
        self.run_ep_cli("init")
        plans = self.repo / "docs" / "PLANS.md"
        original_plans = (
            plans.read_text(encoding="utf-8") + "\nRepository-owned note.\n"
        )
        plans.write_text(original_plans, encoding="utf-8")
        agents = self.repo / "AGENTS.md"
        original_agents = (
            "$engineering-specs\n"
            "docs/agent-guides/managed/index.md\n"
            + "".join(f"line {number:03d}\n" for number in range(3, 101))
        )
        agents.write_text(original_agents, encoding="utf-8")
        architecture = self.repo / "ARCHITECTURE.md"
        architecture.write_text("# Human architecture\n", encoding="utf-8")

        result = json.loads(
            self.run_cli(
                "bootstrap",
                "--profile",
                "codex",
                "--apply",
            ).stdout
        )

        self.assertEqual(agents.read_text(encoding="utf-8"), original_agents)
        self.assertEqual(
            architecture.read_text(encoding="utf-8"),
            "# Human architecture\n",
        )
        self.assertEqual(plans.read_text(encoding="utf-8"), original_plans)
        self.assertTrue(
            any(
                "hard limit is 100" in warning
                for warning in result["warnings"]
            )
        )
        manifest = json.loads(
            (
                self.repo / "docs" / ".engineering" / "harness.json"
            ).read_text(encoding="utf-8")
        )
        custom_records = {
            item["path"]: item
            for item in manifest["files"]
            if item["path"] in {"AGENTS.md", "ARCHITECTURE.md"}
        }
        for record in custom_records.values():
            self.assertEqual(
                record["template_version"],
                "legacy-unversioned",
            )
            self.assertIsNone(record["template_sha256"])
            self.assertIsNone(record["installed_sha256"])
        self.run_cli("validate", "--harness")

    def test_codex_bootstrap_rejects_101_line_agents_without_writing(
        self,
    ) -> None:
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "".join(f"line {number:03d}\n" for number in range(1, 102)),
            encoding="utf-8",
        )

        result = self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--apply",
            expected=2,
        )

        self.assertIn("HARNESS_AGENTS_LINE_LIMIT", result.stderr)
        self.assertFalse((self.repo / "docs").exists())
        self.assertEqual(
            len(agents.read_text(encoding="utf-8").splitlines()),
            101,
        )

    def test_harness_validation_rejects_agents_growth(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            "".join(f"line {number:03d}\n" for number in range(1, 102)),
            encoding="utf-8",
        )

        result = self.run_cli("validate", "--harness", expected=1)

        self.assertIn("HARNESS_AGENTS_LINE_LIMIT", result.stderr)
        self.assertIn("actual 101 physical lines", result.stderr)

    def test_harness_validation_can_require_bootstrap(self) -> None:
        self.run_ep_cli("init")

        result = self.run_cli("validate", "--harness", expected=1)

        self.assertIn("HARNESS_MANIFEST_MISSING", result.stderr)

    def test_codex_bootstrap_path_conflict_is_non_destructive(self) -> None:
        docs = self.repo / "docs"
        docs.write_text("reserved by user\n", encoding="utf-8")

        result = self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--apply",
            expected=2,
        )

        self.assertIn("parent is not a directory", result.stderr)
        self.assertEqual(
            docs.read_text(encoding="utf-8"),
            "reserved by user\n",
        )
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_bootstrap_rolls_back_when_post_validation_fails(self) -> None:
        source = {
            "kind": "git",
            "url": self.catalog_repository.resolve().as_uri(),
            "ref": "main",
        }
        with mock.patch.object(
            foundryctl,
            "validate_harness",
            return_value=(["INJECTED_POST_VALIDATION_FAILURE"], []),
        ):
            with self.assertRaisesRegex(
                foundryctl.FoundryctlError,
                "INJECTED_POST_VALIDATION_FAILURE",
            ):
                foundryctl.bootstrap_repo(
                    self.repo,
                    ("codex",),
                    apply_changes=True,
                    initial_spec_source=source,
                    requested_spec_ids=None,
                )

        for relative in (
            "AGENTS.md",
            "ARCHITECTURE.md",
            foundryctl.CORE_ROUTER_PATH,
            foundryctl.HARNESS_MANIFEST,
            "docs/.engineering/specs.json",
            "docs/.engineering/specs.lock.json",
            "docs/agent-guides/managed/index.md",
        ):
            self.assertFalse((self.repo / relative).exists(), relative)

    def test_spec_detection_recommends_and_explicit_ids_select(self) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/polyglot\n",
            encoding="utf-8",
        )
        (self.repo / "tsconfig.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text(
            "[project]\nname = \"polyglot\"\n",
            encoding="utf-8",
        )

        preview = json.loads(self.run_cli("spec", "plan").stdout)

        optional = [
            "languages/go",
            "languages/typescript",
            "languages/python",
        ]
        expected = [
            "core/semantic-naming",
            *optional,
        ]
        self.assertEqual(
            preview["selected_specs"],
            ["core/semantic-naming"],
        )
        self.assertEqual(
            preview["configured_specs"],
            ["core/semantic-naming"],
        )
        self.assertEqual(
            preview["detected_specs"],
            optional,
        )
        self.assertEqual(preview["recommended_specs"], optional)
        self.assertEqual(
            [item["id"] for item in preview["available_specs"]],
            expected,
        )
        self.assertEqual(list(self.repo.glob("docs/**")), [])

        applied = json.loads(
            self.run_cli(
                "bootstrap",
                "--profile",
                "codex",
                "--spec",
                "languages/go",
                "--spec",
                "languages/typescript",
                "--spec",
                "languages/python",
                "--apply",
            ).stdout
        )
        self.assertEqual(applied["specs"], expected)
        self.assertEqual(applied["configured_specs"], expected)
        self.assertEqual(applied["recommended_specs"], optional)
        lock = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.lock.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["id"] for item in lock["specs"]],
            expected,
        )
        for item in lock["specs"]:
            installed = self.repo / item["installed_path"]
            source = self.catalog_repository / item["source_path"]
            self.assertEqual(installed.read_bytes(), source.read_bytes())
        index = (
            self.repo / "docs" / "agent-guides" / "managed" / "index.md"
        ).read_text(encoding="utf-8")
        for spec_id in expected:
            self.assertIn(spec_id, index)
        self.run_cli("spec", "validate")

    def test_spec_sync_and_update_preserve_or_replace_selection(self) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/update\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        (self.repo / "tsconfig.json").write_text("{}\n", encoding="utf-8")

        synced = json.loads(
            self.run_cli("spec", "sync", "--apply").stdout
        )
        self.assertEqual(
            synced["selected_specs"],
            ["core/semantic-naming", "languages/go"],
        )
        self.assertIn(
            "languages/typescript",
            synced["detected_specs"],
        )

        preserved = json.loads(self.run_cli("spec", "update").stdout)
        self.assertEqual(
            preserved["selected_specs"],
            ["core/semantic-naming", "languages/go"],
        )
        self.assertIn(
            "languages/typescript",
            preserved["recommended_specs"],
        )
        self.assertNotIn(
            {
                "action": "update_file",
                "path": "docs/.engineering/specs.json",
            },
            preserved["actions"],
        )

        preview = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec",
                "languages/go",
                "--spec",
                "languages/typescript",
            ).stdout
        )
        self.assertEqual(
            preview["configured_specs"],
            [
                "core/semantic-naming",
                "languages/go",
                "languages/typescript",
            ],
        )
        self.assertIn(
            {
                "action": "update_file",
                "path": "docs/.engineering/specs.json",
            },
            preview["actions"],
        )
        updated = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec",
                "languages/go",
                "--spec",
                "languages/typescript",
                "--apply",
            ).stdout
        )
        self.assertIn(
            "docs/.engineering/specs.json",
            updated["updated"],
        )
        manifest = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["specs"],
            [
                "core/semantic-naming",
                "languages/go",
                "languages/typescript",
            ],
        )
        self.run_cli("spec", "validate")

    def test_required_only_update_removes_locked_managed_copy(self) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/remove\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        managed = (
            self.repo
            / "docs"
            / "agent-guides"
            / "managed"
            / "languages"
            / "go.md"
        )
        self.assertTrue(managed.is_file())

        preview = json.loads(
            self.run_cli("spec", "update", "--required-only").stdout
        )
        self.assertEqual(
            preview["configured_specs"],
            ["core/semantic-naming"],
        )
        self.assertIn(
            {
                "action": "remove_file",
                "path": "docs/agent-guides/managed/languages/go.md",
            },
            preview["actions"],
        )

        applied = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--required-only",
                "--apply",
            ).stdout
        )
        self.assertEqual(
            applied["removed"],
            ["docs/agent-guides/managed/languages/go.md"],
        )
        self.assertFalse(managed.exists())
        manifest = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["specs"], ["core/semantic-naming"])
        self.run_cli("spec", "validate")

    def test_deselection_refuses_to_remove_drifted_managed_copy(self) -> None:
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        manifest_path = (
            self.repo / "docs" / ".engineering" / "specs.json"
        )
        original_manifest = manifest_path.read_bytes()
        managed = (
            self.repo
            / "docs"
            / "agent-guides"
            / "managed"
            / "languages"
            / "go.md"
        )
        managed.write_text("# repository-owned edit\n", encoding="utf-8")

        result = self.run_cli(
            "spec",
            "update",
            "--required-only",
            "--apply",
            expected=2,
        )

        self.assertIn("SPEC_MANAGED_REMOVAL_DRIFT", result.stderr)
        self.assertEqual(manifest_path.read_bytes(), original_manifest)
        self.assertEqual(
            managed.read_text(encoding="utf-8"),
            "# repository-owned edit\n",
        )

    def test_explicit_selection_rejects_unknown_and_duplicate_ids(self) -> None:
        unknown = self.run_cli(
            "bootstrap",
            "--spec",
            "languages/unknown",
            "--apply",
            expected=2,
        )
        self.assertIn("SPEC_SELECTION_UNKNOWN", unknown.stderr)
        self.assertEqual(list(self.repo.iterdir()), [])

        duplicate = self.run_cli(
            "bootstrap",
            "--spec",
            "languages/go",
            "--spec",
            "languages/go",
            "--apply",
            expected=2,
        )
        self.assertIn("SPEC_SELECTION_DUPLICATE", duplicate.stderr)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_spec_sync_pins_commit_and_update_moves_to_ref_head(self) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/pinned\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        managed = (
            self.repo
            / "docs"
            / "agent-guides"
            / "managed"
            / "languages"
            / "go.md"
        )
        original = managed.read_bytes()
        new_commit = update_go_spec(self.catalog_repository)
        self.assertNotEqual(new_commit, self.catalog_commit)

        sync_preview = json.loads(self.run_cli("spec", "sync").stdout)
        self.assertEqual(
            sync_preview["catalog"]["resolved_revision"],
            self.catalog_commit,
        )
        self.run_cli("spec", "sync", "--apply")
        self.assertEqual(managed.read_bytes(), original)
        locked = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.lock.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            locked["catalog"]["resolved_revision"],
            self.catalog_commit,
        )

        update_preview = json.loads(self.run_cli("spec", "update").stdout)
        self.assertEqual(
            update_preview["selection_decision"]["status"],
            "required",
        )
        self.assertEqual(
            update_preview["catalog"]["resolved_revision"],
            new_commit,
        )
        self.assertIn(
            {
                "action": "replace_file",
                "path": "docs/agent-guides/managed/languages/go.md",
            },
            update_preview["actions"],
        )
        self.run_cli("spec", "update", "--keep-selection", "--apply")
        self.assertEqual(
            managed.read_bytes(),
            (
                self.catalog_repository
                / "specification"
                / "languages"
                / "go.md"
            ).read_bytes(),
        )
        locked = json.loads(
            (
                self.repo / "docs" / ".engineering" / "specs.lock.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            locked["catalog"]["resolved_revision"],
            new_commit,
        )

    def test_spec_version_pins_tag_and_explicit_update_changes_release(
        self,
    ) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/versioned\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec-version",
            "0.1.0",
            "--apply",
        )
        manifest_path = (
            self.repo / "docs" / ".engineering" / "specs.json"
        )
        lock_path = (
            self.repo / "docs" / ".engineering" / "specs.lock.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        locked = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["catalog"]["ref"],
            "refs/tags/v0.1.0",
        )
        self.assertEqual(
            locked["catalog"]["resolved_revision"],
            self.catalog_commit,
        )

        new_commit = update_go_spec(self.catalog_repository)
        sync = json.loads(self.run_cli("spec", "sync").stdout)
        self.assertEqual(
            sync["catalog"]["resolved_revision"],
            self.catalog_commit,
        )

        preview = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec-version",
                "0.2.0",
            ).stdout
        )
        self.assertEqual(
            preview["catalog"]["source"]["ref"],
            "refs/tags/v0.2.0",
        )
        self.assertEqual(
            preview["catalog"]["resolved_revision"],
            new_commit,
        )
        self.assertEqual(
            preview["selection_decision"]["status"],
            "required",
        )
        self.assertIn(
            {
                "action": "update_file",
                "path": "docs/.engineering/specs.json",
            },
            preview["actions"],
        )

        self.run_cli(
            "spec",
            "update",
            "--spec-version",
            "0.2.0",
            "--keep-selection",
            "--apply",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        locked = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["catalog"]["ref"],
            "refs/tags/v0.2.0",
        )
        self.assertEqual(
            locked["catalog"]["resolved_revision"],
            new_commit,
        )

    def test_catalog_update_requires_explicit_optional_spec_decision(
        self,
    ) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/selection-decision\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec-version",
            "0.1.0",
            "--spec",
            "languages/go",
            "--apply",
        )
        new_commit = add_specialized_go_specs(self.catalog_repository)

        preview = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec-version",
                "0.2.0",
            ).stdout
        )
        decision = preview["selection_decision"]
        self.assertEqual(decision["status"], "required")
        self.assertEqual(decision["resolution"], "unresolved")
        self.assertEqual(
            decision["reason"],
            "catalog_changed_with_unconfigured_optional_specs",
        )
        self.assertEqual(
            decision["candidates"],
            [
                {
                    "id": "languages/typescript",
                    "version": "0.2.0",
                    "description": "TypeScript implementation fixture",
                    "requires": ["core/semantic-naming"],
                    "recommended": False,
                    "configured": False,
                    "selected": False,
                },
                {
                    "id": "languages/python",
                    "version": "0.2.0",
                    "description": "Python implementation fixture",
                    "requires": ["core/semantic-naming"],
                    "recommended": True,
                    "configured": False,
                    "selected": False,
                },
                {
                    "id": "languages/go/functional-options",
                    "version": "0.2.0",
                    "description": "Go functional-option fixture",
                    "requires": ["languages/go"],
                    "recommended": False,
                    "configured": False,
                    "selected": False,
                },
                {
                    "id": "languages/go/factory-delegation",
                    "version": "0.2.0",
                    "description": "Go factory-delegation fixture",
                    "requires": ["languages/go/functional-options"],
                    "recommended": False,
                    "configured": False,
                    "selected": False,
                },
            ],
        )

        def snapshot() -> dict[str, bytes]:
            return {
                path.relative_to(self.repo).as_posix(): path.read_bytes()
                for path in self.repo.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        rejected = self.run_cli(
            "spec",
            "update",
            "--spec-version",
            "0.2.0",
            "--apply",
            expected=2,
        )
        self.assertIn("SPEC_SELECTION_DECISION_REQUIRED", rejected.stderr)
        self.assertEqual(snapshot(), before)

        keep_preview = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec-version",
                "0.2.0",
                "--keep-selection",
            ).stdout
        )
        self.assertEqual(
            keep_preview["selection_decision"]["status"],
            "resolved",
        )
        self.assertEqual(
            keep_preview["selection_decision"]["resolution"],
            "keep_selection",
        )
        kept = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec-version",
                "0.2.0",
                "--keep-selection",
                "--apply",
            ).stdout
        )
        self.assertEqual(
            kept["catalog"]["resolved_revision"],
            new_commit,
        )
        self.assertEqual(
            kept["configured_specs"],
            ["core/semantic-naming", "languages/go"],
        )

        explicit = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec",
                "languages/go/factory-delegation",
            ).stdout
        )
        self.assertEqual(
            explicit["selection_decision"]["resolution"],
            "explicit_specs",
        )
        self.assertEqual(
            explicit["configured_specs"],
            [
                "core/semantic-naming",
                "languages/go/factory-delegation",
            ],
        )
        self.assertEqual(
            explicit["selected_specs"],
            [
                "core/semantic-naming",
                "languages/go",
                "languages/go/functional-options",
                "languages/go/factory-delegation",
            ],
        )
        explicit_applied = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--spec",
                "languages/go/factory-delegation",
                "--apply",
            ).stdout
        )
        self.assertEqual(
            explicit_applied["selection_decision"]["resolution"],
            "explicit_specs",
        )
        self.assertEqual(
            explicit_applied["selected_specs"],
            explicit["selected_specs"],
        )

        required_only = json.loads(
            self.run_cli("spec", "update", "--required-only").stdout
        )
        self.assertEqual(
            required_only["selection_decision"]["resolution"],
            "required_only",
        )
        required_only_applied = json.loads(
            self.run_cli(
                "spec",
                "update",
                "--required-only",
                "--apply",
            ).stdout
        )
        self.assertEqual(
            required_only_applied["selection_decision"]["resolution"],
            "required_only",
        )
        self.assertEqual(
            required_only_applied["selected_specs"],
            ["core/semantic-naming"],
        )

        conflict = self.run_cli(
            "spec",
            "update",
            "--keep-selection",
            "--required-only",
            expected=2,
        )
        self.assertIn("not allowed with argument", conflict.stderr)

    def test_spec_validation_is_offline(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        unavailable = self.base / "specification-source-unavailable"
        self.catalog_repository.rename(unavailable)

        self.run_cli("spec", "validate")
        self.run_cli("validate", "--harness")

    def test_unreachable_initial_ref_is_non_destructive(self) -> None:
        result = self.run_cli(
            "spec",
            "plan",
            "--spec-ref",
            "refs/heads/missing",
            expected=2,
        )

        self.assertIn("SPEC_GIT_FETCH_FAILED", result.stderr)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_invalid_or_ambiguous_version_selector_is_non_destructive(
        self,
    ) -> None:
        invalid = self.run_cli(
            "spec",
            "plan",
            "--spec-version",
            "main",
            expected=2,
        )
        self.assertIn("SPEC_VERSION_INVALID", invalid.stderr)

        ambiguous = self.run_cli(
            "spec",
            "plan",
            "--spec-version",
            "0.1.0",
            "--spec-ref",
            "main",
            expected=2,
        )
        self.assertIn("not allowed with argument", ambiguous.stderr)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_existing_source_changes_require_explicit_update(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "specs.json"
        )
        original = manifest_path.read_bytes()

        sync = self.run_cli(
            "spec",
            "sync",
            "--spec-version",
            "0.1.0",
            expected=2,
        )
        self.assertIn("SPEC_SOURCE_OVERRIDE_REQUIRES_UPDATE", sync.stderr)

        bootstrap = self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec-version",
            "0.1.0",
            expected=2,
        )
        self.assertIn(
            "SPEC_BOOTSTRAP_OVERRIDE_REQUIRES_UPDATE",
            bootstrap.stderr,
        )

        repository_only = self.run_cli(
            "spec",
            "update",
            "--spec-repository",
            self.catalog_repository.resolve().as_uri(),
            expected=2,
        )
        self.assertIn(
            "SPEC_SOURCE_SELECTOR_REQUIRED",
            repository_only.stderr,
        )
        self.assertEqual(manifest_path.read_bytes(), original)

    def test_spec_drift_requires_explicit_sync(self) -> None:
        (self.repo / "go.mod").write_text(
            "module example.test/drift\n",
            encoding="utf-8",
        )
        self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--spec",
            "languages/go",
            "--apply",
        )
        managed = (
            self.repo
            / "docs"
            / "agent-guides"
            / "managed"
            / "languages"
            / "go.md"
        )
        managed.write_text("# locally modified\n", encoding="utf-8")

        bootstrap = self.run_cli(
            "bootstrap",
            "--profile",
            "codex",
            "--apply",
            expected=2,
        )
        self.assertIn("SPEC_MANAGED_CONTENT_DRIFT", bootstrap.stderr)
        self.assertEqual(
            managed.read_text(encoding="utf-8"),
            "# locally modified\n",
        )
        validation = self.run_cli("spec", "validate", expected=1)
        self.assertIn("SPEC_MANAGED_CONTENT_DRIFT", validation.stderr)

        preview = json.loads(self.run_cli("spec", "sync").stdout)
        self.assertIn(
            {
                "action": "replace_file",
                "path": (
                    "docs/agent-guides/managed/languages/go.md"
                ),
            },
            preview["actions"],
        )
        self.run_cli("spec", "sync", "--apply")
        self.assertEqual(
            managed.read_bytes(),
            (
                self.catalog_repository
                / "specification"
                / "languages"
                / "go.md"
            ).read_bytes(),
        )
        self.run_cli("spec", "validate")

    def test_project_spec_is_routed_without_becoming_managed(self) -> None:
        self.run_cli("bootstrap", "--profile", "codex", "--apply")
        project_spec = (
            self.repo / "docs" / "agent-guides" / "handler-pattern.md"
        )
        project_spec.parent.mkdir(parents=True, exist_ok=True)
        original = "# Project Handler Pattern\n"
        project_spec.write_text(original, encoding="utf-8")
        manifest_path = (
            self.repo / "docs" / ".engineering" / "specs.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["project_specs"] = [
            {
                "path": "docs/agent-guides/handler-pattern.md",
                "applies_to": ["internal/http/**"],
                "description": "Project HTTP Handler pattern",
            }
        ]
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        self.run_cli("spec", "sync", "--apply")

        index = (
            self.repo / "docs" / "agent-guides" / "managed" / "index.md"
        ).read_text(encoding="utf-8")
        self.assertIn("internal/http/**", index)
        self.assertIn("handler-pattern.md", index)
        self.assertEqual(project_spec.read_text(encoding="utf-8"), original)
        self.run_cli("spec", "validate")

    def test_git_catalog_digest_failure_is_non_destructive(self) -> None:
        (
            self.catalog_repository
            / "specification"
            / "core"
            / "semantic-naming.md"
        ).write_text("# drifted catalog\n", encoding="utf-8")
        commit_all(self.catalog_repository, "commit invalid catalog drift")
        state = self.repo / "docs" / ".engineering"
        state.mkdir(parents=True)
        (state / "specs.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "owner": "repo-foundry",
                    "catalog": {
                        "kind": "git",
                        "url": self.catalog_repository.resolve().as_uri(),
                        "ref": "main",
                    },
                    "specs": ["core/semantic-naming"],
                    "project_specs": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_cli("spec", "plan", expected=2)

        self.assertIn("SPEC_CATALOG_DIGEST_MISMATCH", result.stderr)
        self.assertFalse((state / "specs.lock.json").exists())
        self.assertFalse(
            (self.repo / "docs" / "agent-guides" / "managed").exists()
        )

    def test_execution_plan_cli_does_not_own_harness_commands(self) -> None:
        help_result = subprocess.run(
            [sys.executable, "-B", str(EPCTL), "--help"],
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn("bootstrap", help_result.stdout)
        self.assertNotIn("--harness", help_result.stdout)
        self.assertNotIn(" spec ", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
