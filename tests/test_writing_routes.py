"""Exercise writing-route seeds without adding a runtime style gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.harness_legacy_fixture import CORE_MEMORY_PATHS, strip_memory_assets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import foundryctl  # noqa: E402
from tests.spec_git_fixture import create_git_catalog  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/writing-routes"
OLD_SEEDS = {
    "AGENTS.md": ("codex-agents-2.4.1.txt", "c3673c641ec6851291a6c36868c783204fa939ad"),
    foundryctl.CORE_PROJECT_SKILL_PATH: (
        "core-skill-1.5.4.txt",
        "50c666beb33d445ad67fcef07b949894c951f92a",
    ),
}
GUIDE = "references/controlled-writing.md"


class WritingRouteContractTests(unittest.TestCase):
    def test_templates_route_to_skill_relative_guides_within_existing_budgets(self) -> None:
        for asset, maximum in (
            ("adapters/codex/AGENTS.md", foundryctl.CODEX_AGENT_TEMPLATE_TARGET_LINES),
            ("core/repo-foundry-ai/SKILL.md.template", foundryctl.CORE_SKILL_MAX_LINES),
        ):
            with self.subTest(asset=asset):
                text = foundryctl.asset_text(asset)
                prose = " ".join(text.split())
                self.assertEqual(text.count(GUIDE), 1)
                self.assertIn("relative to", prose)
                self.assertIn("not this repository", prose)
                self.assertIn("not full ASD-STE100 conformance", prose)
                self.assertIn("Skill or guide is unavailable", prose)
                self.assertIn("report the gap and follow project conventions", prose)
                self.assertIn("do not install Skills or create artifacts solely for writing style", prose)
                self.assertLessEqual(len(text.splitlines()), maximum)
                self.assertNotIn("## Common guidance", text)
        self.assertEqual(foundryctl.CORE_HARNESS_VERSION, "1.6.3")
        self.assertEqual(foundryctl.CODEX_ADAPTER_VERSION, "2.4.5")
        self.assertNotIn(GUIDE, foundryctl.CODEX_ROUTER_AGENTS_ROUTES)

    def test_migration_fixtures_are_exact_previous_seed_blobs(self) -> None:
        # These are the actual pre-change seeds, not new seeds with a line removed.
        for filename, expected_blob in OLD_SEEDS.values():
            with self.subTest(filename=filename):
                raw = (FIXTURES / filename).read_bytes()
                header = f"blob {len(raw)}\0".encode("ascii")
                self.assertEqual(hashlib.sha1(header + raw).hexdigest(), expected_blob)
                self.assertNotIn(GUIDE.encode(), raw)


class WritingRouteBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "target"
        self.repo.mkdir()
        self.catalog, _ = create_git_catalog(self.base)

    def cli(self, *args: str, expected: int = 0) -> dict:
        arguments = list(args)
        if arguments[0] == "bootstrap" and not (self.repo / "docs/.engineering/specs.json").exists():
            arguments.extend(("--spec-repository", self.catalog.resolve().as_uri(), "--spec-version", "0.1.0"))
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/foundryctl.py"), "--repo", str(self.repo), *arguments],
            text=True, capture_output=True, timeout=60,
        )
        self.assertEqual(result.returncode, expected, result.stdout + "\n" + result.stderr)
        return json.loads(result.stdout) if expected == 0 else {"error": result.stderr}

    def inventory(self) -> dict[str, bytes]:
        return {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}

    def manifest(self) -> dict:
        return json.loads((self.repo / foundryctl.HARNESS_MANIFEST).read_text(encoding="utf-8"))

    def old_harness(self) -> None:
        self.cli("bootstrap", "--adapter", "codex", "--apply")
        manifest = self.manifest()
        manifest["core"]["version"] = "1.5.4"
        strip_memory_assets(self.repo, manifest)
        manifest["adapters"][0]["version"] = "2.4.1"
        for record in manifest["files"]:
            record["template_version"] = "1.5.4" if record["owner_kind"] == "core" else "2.4.1"
            seed = OLD_SEEDS.get(record["path"])
            if seed is not None:
                raw = (FIXTURES / seed[0]).read_bytes()
                (self.repo / record["path"]).write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                record["template_sha256"] = digest
                record["installed_sha256"] = digest
        (self.repo / foundryctl.HARNESS_MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        foundryctl.load_harness_manifest(self.repo)

    def assert_no_guide_copy(self) -> None:
        self.assertEqual(list(self.repo.rglob("controlled-writing.md")), [])

    def test_fresh_codex_preview_apply_and_repeat(self) -> None:
        preview = self.cli("bootstrap", "--adapter", "codex")
        self.assertEqual(preview["mode"], "dry-run")
        self.assertEqual(self.inventory(), {})
        self.cli("bootstrap", "--adapter", "codex", "--apply")
        for relative in OLD_SEEDS:
            self.assertIn(GUIDE, (self.repo / relative).read_text(encoding="utf-8"))
        manifest = self.manifest()
        self.assertEqual(manifest["core"]["version"], "1.6.3")
        self.assertEqual(manifest["adapters"][0]["version"], "2.4.5")
        for record in manifest["files"]:
            digest = hashlib.sha256((self.repo / record["path"]).read_bytes()).hexdigest()
            self.assertEqual(record["installed_sha256"], digest)
            self.assertEqual(record["template_sha256"], digest)
        before = self.inventory()
        repeated = self.cli("bootstrap", "--adapter", "codex", "--apply")
        self.assertEqual(repeated["created"], [])
        self.assertEqual(repeated["updated"], [])
        self.assertEqual(self.inventory(), before)
        self.cli("validate", "--harness")
        self.assert_no_guide_copy()

    def test_other_adapters_receive_shared_route_without_agents_file(self) -> None:
        for adapter in ("claude", "portable"):
            with self.subTest(adapter=adapter):
                self.repo = self.base / adapter
                self.repo.mkdir()
                self.cli("bootstrap", "--adapter", adapter, "--apply")
                self.assertFalse((self.repo / "AGENTS.md").exists())
                text = (self.repo / foundryctl.CORE_PROJECT_SKILL_PATH).read_text(encoding="utf-8")
                self.assertIn(GUIDE, text)
                self.cli("validate", "--adapter", adapter)
                self.assert_no_guide_copy()

    def test_preexisting_agents_without_writing_route_is_preserved(self) -> None:
        raw = (FIXTURES / "codex-agents-2.4.1.txt").read_bytes() + b"\nProject-owned instruction.\n"
        (self.repo / "AGENTS.md").write_bytes(raw)
        self.cli("bootstrap", "--adapter", "codex", "--apply")
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), raw)
        record = next(r for r in self.manifest()["files"] if r["path"] == "AGENTS.md")
        self.assertEqual(record["template_version"], foundryctl.LEGACY_UNVERSIONED)
        self.assertIsNone(record["installed_sha256"])
        self.cli("validate", "--harness")
        self.assert_no_guide_copy()

    def test_explicit_upgrade_replaces_only_unchanged_seeds_and_is_idempotent(self) -> None:
        self.old_harness()
        before = self.inventory()
        preview = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION)
        self.assertEqual({a["path"] for a in preview["actions"] if a["action"] == "replace_file"}, set(OLD_SEEDS))
        self.assertEqual({a["path"] for a in preview["actions"] if a["action"] == "create_file"}, CORE_MEMORY_PATHS)
        self.assertEqual(self.inventory(), before)
        applied = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION, "--apply")
        self.assertEqual(set(applied["created"]), CORE_MEMORY_PATHS)
        after = self.inventory()
        self.assertEqual(set(after), set(before) | CORE_MEMORY_PATHS)
        self.assertEqual({p for p in before if before[p] != after[p]}, {*OLD_SEEDS, foundryctl.HARNESS_MANIFEST})
        manifest = self.manifest()
        self.assertEqual([m["id"] for m in manifest["applied_migrations"]], ["core-1.5.4-to-1.6.3", "adapter-codex-2.4.1-to-2.4.5"])
        for relative in OLD_SEEDS:
            self.assertIn(GUIDE, after[relative].decode())
        repeated = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION, "--apply")
        self.assertEqual(repeated["created"], [])
        self.assertEqual(repeated["updated"], [])
        self.assertEqual(self.inventory(), after)
        self.cli("validate", "--harness")
        self.cli("spec", "validate")
        self.assert_no_guide_copy()

    def test_upgrade_preserves_customized_agents_and_updates_shared_route(self) -> None:
        self.old_harness()
        agents = self.repo / "AGENTS.md"
        raw = agents.read_bytes() + b"\nKeep the project writing convention.\n"
        agents.write_bytes(raw)
        preview = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION)
        action = next(a for a in preview["actions"] if a.get("path") == "AGENTS.md")
        self.assertEqual(action["action"], "preserve")
        applied = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION, "--apply")
        self.assertNotIn("AGENTS.md", applied["updated"])
        self.assertEqual(agents.read_bytes(), raw)
        self.assertIn(GUIDE, (self.repo / foundryctl.CORE_PROJECT_SKILL_PATH).read_text(encoding="utf-8"))
        record = next(r for r in self.manifest()["files"] if r["path"] == "AGENTS.md")
        self.assertEqual(record["template_version"], foundryctl.LEGACY_UNVERSIONED)
        self.cli("validate", "--harness")

    def test_customized_core_conflict_refuses_all_upgrade_writes(self) -> None:
        self.old_harness()
        core = self.repo / foundryctl.CORE_PROJECT_SKILL_PATH
        core.write_bytes(core.read_bytes() + b"\nCustom project workflow.\n")
        before = self.inventory()
        preview = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION)
        conflicts = {a["path"] for a in preview["actions"] if a["action"] == "conflict"}
        self.assertIn(foundryctl.CORE_PROJECT_SKILL_PATH, conflicts)
        self.assertEqual(self.inventory(), before)
        result = self.cli("upgrade", "--to", foundryctl.REPO_FOUNDRY_VERSION, "--apply", expected=2)
        self.assertIn("merge explicitly", result["error"])
        self.assertEqual(self.inventory(), before)


if __name__ == "__main__":
    unittest.main()
