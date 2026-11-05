from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGNCTL = ROOT / "scripts" / "designctl.py"
EPCTL = ROOT.parent / "engineering-execution-plan" / "scripts" / "epctl.py"


class DesignctlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.run_cli("init")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(
        self, *arguments: str, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(DESIGNCTL),
                "--repo",
                str(self.repo),
                *arguments,
            ],
            text=True,
            capture_output=True,
            timeout=20,
        )
        if result.returncode != expected:
            self.fail(
                f"expected exit {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def run_ep_cli(
        self, *arguments: str, expected: int = 0
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
            timeout=20,
        )
        if result.returncode != expected:
            self.fail(
                f"expected exit {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    @staticmethod
    def complete_markers(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"<!--\s*REQUIRED(?:_[A-Z_]+)?\s*:[\s\S]*?-->",
            (
                "The design records a concrete bounded contract, its ownership, "
                "failure behavior, compatibility conditions, and observable verification evidence."
            ),
            text,
        )
        text = text.replace(
            'decision_not_required_reason: ""',
            'decision_not_required_reason: "The change is local and introduces no durable architecture choice"',
        )
        path.write_text(text, encoding="utf-8")

    def new_design(self, slug: str, layout: str = "single") -> Path:
        result = self.run_cli(
            "new-design",
            "--slug",
            slug,
            "--title",
            f"{slug} technical design",
            "--layout",
            layout,
            "--research-not-required-reason",
            "Existing accepted architecture fully fixes the bounded input contract",
            "--author",
            "Test Author",
            "--owner",
            "Test Owner",
        )
        return Path(result.stdout.strip())

    def test_direct_cli_resolves_design_adr_refs_from_history_packs(self) -> None:
        self.run_ep_cli("init")
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
        self.run_cli(
            "new-design",
            "--slug",
            "historical-input-consumer",
            "--title",
            "Historical input consumer",
            "--layout",
            "single",
            "--research-not-required-reason",
            "The bounded fixture has authoritative inputs.",
            "--adr",
            "ADR-001",
            "--author",
            "Test Author",
            "--owner",
            "Test Owner",
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
        validation = self.run_cli("validate")
        status = json.loads(self.run_cli("status", "--json").stdout)
        self.assertNotIn("ADR not found: ADR-001", validation.stdout)
        self.assertEqual(status[0]["errors"], [])

    def publish(self, path: Path) -> str:
        self.complete_markers(path)
        design_id = re.search(
            r"(?m)^id:\s+(DD-\d+)$", path.read_text(encoding="utf-8")
        ).group(1)
        if path.name == "DESIGN.md":
            for member in path.parent.rglob("*.md"):
                self.complete_markers(member)
            self.run_cli("sync", design_id)
        self.run_cli("mark-review-ready", design_id)
        return self.run_cli(
            "approve",
            design_id,
            "--approved-by",
            "Design Authority",
            "--approval-ref",
            "test:explicit-approval",
        ).stdout.strip()

    def test_single_design_lifecycle_preserves_published_revision(self) -> None:
        design = self.new_design("health-contract")
        self.assertEqual(design.name, "dd-001_health-contract.md")
        evidence = self.publish(design)
        self.assertRegex(evidence, r"^DD-001@rev:1@sha256:[0-9a-f]{64}$")
        snapshot = (
            self.repo
            / "docs/.designctl/snapshots/DD-001/rev-001/DESIGN.md"
        )
        published_bytes = snapshot.read_bytes()

        self.run_cli(
            "revise",
            "DD-001",
            "--reason",
            "Add a versioned response field",
        )
        status = json.loads(self.run_cli("status", "DD-001", "--json").stdout)[0]
        self.assertEqual(status["status"], "revising")
        self.assertEqual(status["working_revision"], "2")
        self.assertEqual(status["published_revision"], "1")
        self.assertEqual(snapshot.read_bytes(), published_bytes)
        self.run_cli("validate")

    def test_package_manifest_members_and_atomic_snapshot(self) -> None:
        design = self.new_design("registry-module", layout="package")
        reading_map = design.parent / "README.md"
        self.assertIn(
            'href="DESIGN.md"',
            reading_map.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            {
                path.name
                for path in design.parent.iterdir()
                if path.is_dir()
            },
            {
                "artifacts",
                "contributor-guide",
                "core-concepts",
                "deep-dives",
                "extension-points",
                "how-it-works",
                "snapshots",
                "subsystems",
            },
        )
        member = Path(
            self.run_cli(
                "new-member",
                "DD-001",
                "--role",
                "subsystem",
                "--slug",
                "registry-api",
                "--title",
                "Registry API",
            ).stdout.strip()
        )
        self.assertIn("doc-002_registry-api.md", member.name)
        evidence = self.publish(design)
        manifest_path = design.parent / "DESIGN_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "current")
        self.assertEqual(
            [item["role"] for item in manifest["documents"]],
            ["entrypoint", "reading-map", "subsystem"],
        )
        self.assertEqual(manifest["reading_map"], "README.md")
        snapshot = design.parent / "snapshots/rev-001"
        self.assertTrue((snapshot / "DESIGN.md").is_file())
        self.assertTrue((snapshot / "README.md").is_file())
        self.assertTrue((snapshot / "subsystems/doc-002_registry-api.md").is_file())
        self.assertRegex(evidence, r"^DD-001@rev:1@sha256:[0-9a-f]{64}$")
        self.run_cli("validate")

    def test_package_move_preserves_document_identity(self) -> None:
        design = self.new_design("move-member", layout="package")
        member = Path(
            self.run_cli(
                "new-member",
                "DD-001",
                "--role",
                "component",
                "--slug",
                "worker",
                "--title",
                "Worker component",
            ).stdout.strip()
        )
        self.publish(design)
        self.run_cli("revise", "DD-001", "--reason", "Reorganize package navigation")
        destination = design.parent / "deep-dives" / "worker-component.md"
        member.rename(destination)
        self.run_cli("sync", "DD-001")
        manifest = json.loads(
            (design.parent / "DESIGN_MANIFEST.json").read_text(encoding="utf-8")
        )
        item = next(item for item in manifest["documents"] if item["id"] == "DOC-002")
        self.assertEqual(item["path"], "deep-dives/worker-component.md")
        self.run_cli("validate")

    def test_legacy_package_layout_remains_syncable_and_publishable(self) -> None:
        design = self.new_design("legacy-package", layout="package")
        package = design.parent
        legacy_reading = package / "docs/README.md"
        legacy_reading.parent.mkdir()
        (package / "README.md").rename(legacy_reading)
        legacy_reading.write_text(
            legacy_reading.read_text(encoding="utf-8").replace(
                'href="DESIGN.md"', 'href="../DESIGN.md"'
            ),
            encoding="utf-8",
        )
        for directory in (
            "how-it-works",
            "core-concepts",
            "subsystems",
            "extension-points",
            "deep-dives",
            "contributor-guide",
        ):
            (package / directory).rmdir()

        member = Path(
            self.run_cli(
                "new-member",
                "DD-001",
                "--role",
                "interface",
                "--slug",
                "legacy-contract",
                "--title",
                "Legacy contract",
            ).stdout.strip()
        )
        self.assertEqual(member.parent.name, "contracts")
        self.complete_markers(design)
        self.complete_markers(legacy_reading)
        self.complete_markers(member)
        self.run_cli("sync", "DD-001")
        stable_bytes = {
            path.relative_to(package).as_posix(): path.read_bytes()
            for path in (design, legacy_reading, member)
        }

        self.run_cli("sync", "DD-001")
        self.run_cli("validate")
        self.assertEqual(
            stable_bytes,
            {
                path.relative_to(package).as_posix(): path.read_bytes()
                for path in (design, legacy_reading, member)
            },
        )
        evidence = self.publish(design)
        manifest = json.loads((package / "DESIGN_MANIFEST.json").read_text())
        self.assertEqual(manifest["reading_map"], "docs/README.md")
        self.assertTrue((package / "snapshots/rev-001/docs/README.md").is_file())
        self.assertTrue(
            (package / "snapshots/rev-001/contracts/doc-002_legacy-contract.md").is_file()
        )
        self.assertRegex(evidence, r"^DD-001@rev:1@sha256:[0-9a-f]{64}$")

    def test_high_water_marks_never_reuse_deleted_ids(self) -> None:
        first = self.new_design("first")
        first.unlink()
        second = self.new_design("second")
        self.assertEqual(second.name, "dd-002_second.md")

        package = self.new_design("members", layout="package")
        first_member = Path(
            self.run_cli(
                "new-member",
                "DD-003",
                "--role",
                "data",
                "--slug",
                "first",
                "--title",
                "First member",
            ).stdout.strip()
        )
        first_member.unlink()
        self.run_cli("sync", "DD-003")
        second_member = Path(
            self.run_cli(
                "new-member",
                "DD-003",
                "--role",
                "data",
                "--slug",
                "second",
                "--title",
                "Second member",
            ).stdout.strip()
        )
        self.assertIn("doc-003_second.md", second_member.name)
        self.assertTrue(package.is_file())

    def test_review_gate_rejects_placeholders_and_manifest_drift(self) -> None:
        design = self.new_design("drift", layout="package")
        self.run_cli("mark-review-ready", "DD-001", expected=2)
        self.complete_markers(design)
        reading = design.parent / "README.md"
        self.complete_markers(reading)
        self.run_cli("sync", "DD-001")
        reading.write_text(reading.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")
        result = self.run_cli("validate", expected=1)
        self.assertIn("manifest drift", result.stdout)

    def test_research_must_be_concluded(self) -> None:
        package = self.repo / "docs/research/active/r-001_input"
        package.mkdir(parents=True)
        (package / "RESEARCH.md").write_text(
            "---\nid: R-001\nstatus: active\nsynthesis: SYNTHESIS.md\n---\n# Input\n",
            encoding="utf-8",
        )
        (package / "SYNTHESIS.md").write_text("# Synthesis\n", encoding="utf-8")
        result = self.run_cli(
            "new-design",
            "--slug",
            "from-research",
            "--title",
            "From Research",
            "--layout",
            "single",
            "--research",
            "R-001",
            expected=2,
        )
        self.assertIn("must be concluded", result.stderr)
        research = package / "RESEARCH.md"
        research.write_text(
            research.read_text(encoding="utf-8").replace("status: active", "status: concluded"),
            encoding="utf-8",
        )
        synthesis_body = "# Synthesis\n\nSealed evidence for the Design handoff.\n"
        synthesis_digest = hashlib.sha256(synthesis_body.encode("utf-8")).hexdigest()
        (package / "SYNTHESIS.md").write_text(
            "---\n"
            'schema_version: "1"\n'
            "parent_id: R-001\n"
            "title: Input synthesis\n"
            "status: sealed\n"
            "created: 2024-01-01\n"
            "updated: 2024-01-01\n"
            f"payload_sha256: {synthesis_digest}\n"
            "---\n"
            + synthesis_body,
            encoding="utf-8",
        )
        created = Path(
            self.run_cli(
                "new-design",
                "--slug",
                "from-research",
                "--title",
                "From Research",
                "--layout",
                "single",
                "--research",
                "R-001",
            ).stdout.strip()
        )
        self.assertTrue(created.is_file())

        (package / "SYNTHESIS.md").write_text(
            (package / "SYNTHESIS.md").read_text(encoding="utf-8") + "tamper\n",
            encoding="utf-8",
        )
        self.complete_markers(created)
        result = self.run_cli("mark-review-ready", "DD-001", expected=2)
        self.assertIn("sealed Synthesis payload changed", result.stderr)

    def test_typed_dependency_cycle_is_rejected(self) -> None:
        first = self.new_design("first")
        second = self.new_design("second")
        first.write_text(
            first.read_text(encoding="utf-8").replace(
                "design_dependencies: []", 'design_dependencies: ["uses:DD-002"]'
            ),
            encoding="utf-8",
        )
        second.write_text(
            second.read_text(encoding="utf-8").replace(
                "design_dependencies: []", 'design_dependencies: ["extends:DD-001"]'
            ),
            encoding="utf-8",
        )
        result = self.run_cli("validate", expected=1)
        self.assertIn("Design dependency cycle", result.stdout)

    def test_review_requires_current_adr_or_a_no_decision_reason(self) -> None:
        adr = self.repo / "docs/adr/adr-001_route.md"
        adr.parent.mkdir(parents=True)
        adr.write_text(
            "---\n"
            'schema_version: "1.4"\n'
            "id: ADR-001\n"
            "status: proposed\n"
            "---\n# Route\n",
            encoding="utf-8",
        )
        design = Path(
            self.run_cli(
                "new-design",
                "--slug",
                "adr-route",
                "--title",
                "ADR route",
                "--layout",
                "single",
                "--research-not-required-reason",
                "The bounded fixture has authoritative inputs.",
                "--adr",
                "ADR-001",
            ).stdout.strip()
        )
        self.complete_markers(design)
        proposed = self.run_cli("mark-review-ready", "DD-001", expected=2)
        self.assertIn("not current accepted architecture", proposed.stderr)

        adr.write_text(
            adr.read_text(encoding="utf-8").replace(
                "status: proposed", "status: accepted"
            ),
            encoding="utf-8",
        )
        self.run_cli("mark-review-ready", "DD-001")

    def test_unpublished_dependency_blocks_review_until_publication(self) -> None:
        dependency = self.new_design("dependency")
        dependent = Path(
            self.run_cli(
                "new-design",
                "--slug",
                "dependent",
                "--title",
                "Dependent design",
                "--layout",
                "single",
                "--research-not-required-reason",
                "The bounded fixture has authoritative inputs.",
                "--design-dependency",
                "uses:DD-001",
            ).stdout.strip()
        )
        self.complete_markers(dependent)
        blocked = self.run_cli("mark-review-ready", "DD-002", expected=2)
        self.assertIn("dependency DD-001 has no consumable current publication", blocked.stderr)

        self.publish(dependency)
        self.run_cli("mark-review-ready", "DD-002")

    def test_explicit_terminal_transitions_preserve_audit_metadata(self) -> None:
        abandoned = self.new_design("abandoned")
        self.run_cli(
            "abandon",
            "DD-001",
            "--approved-by",
            "Design Authority",
            "--approval-ref",
            "test:abandon",
            "--reason",
            "The proposal no longer matches the supported product scope.",
        )
        abandoned_text = abandoned.read_text(encoding="utf-8")
        self.assertIn("status: abandoned", abandoned_text)
        self.assertIn('approval_ref: "test:abandon"', abandoned_text)

        old = self.new_design("old")
        new = self.new_design("replacement")
        self.publish(old)
        self.publish(new)
        self.run_cli(
            "supersede",
            "DD-002",
            "--by",
            "DD-003",
            "--approved-by",
            "Design Authority",
            "--approval-ref",
            "test:supersede",
            "--reason",
            "The replacement owns the complete design scope and rollout.",
        )
        old_text = old.read_text(encoding="utf-8")
        self.assertIn("status: superseded", old_text)
        self.assertIn("superseded_by: DD-003", old_text)
        self.run_cli("validate")

    def test_duplicate_identity_and_managed_symlink_are_rejected(self) -> None:
        design = self.new_design("duplicate")
        duplicate = design.with_name("dd-001_duplicate-copy.md")
        shutil.copy2(design, duplicate)
        duplicate_result = self.run_cli("validate", expected=1)
        self.assertIn("duplicate Design id DD-001", duplicate_result.stdout)
        duplicate.unlink()

        package = self.new_design("symlink", layout="package")
        outside = self.repo / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        linked = package.parent / "core-concepts/linked.md"
        linked.symlink_to(outside)
        symlink_result = self.run_cli("validate", expected=1)
        self.assertIn("Refusing symbolic link", symlink_result.stdout)

    def test_reindex_preserves_human_architecture_index(self) -> None:
        architecture_index = self.repo / "docs/design-docs/index.md"
        original = "# Human architecture map\n\nKeep this route verbatim.\n"
        architecture_index.write_text(original, encoding="utf-8")
        self.new_design("indexed")

        self.run_cli("reindex")

        self.assertEqual(architecture_index.read_text(encoding="utf-8"), original)
        generated = (self.repo / "docs/DESIGN-DOCS.md").read_text(encoding="utf-8")
        self.assertIn("DD-001", generated)

    def test_legacy_schema_is_adopted_without_rewrite(self) -> None:
        legacy = self.repo / "docs/design-docs/legacy.md"
        payload = (
            "---\n"
            'schema_version: "1"\n'
            'metadata_schema: "1"\n'
            "artifact_type: design-doc\n"
            "id: DD-009\n"
            "title: Legacy design\n"
            "status: current\n"
            "author: Historical Author\n"
            "owner: Historical Owner\n"
            "created: 2024-01-01\n"
            "updated: 2024-01-01\n"
            "---\n# Legacy design\n"
        )
        legacy.write_text(payload, encoding="utf-8")
        self.run_cli("init")
        self.run_cli("reindex")
        self.run_cli("validate")
        self.assertEqual(legacy.read_text(encoding="utf-8"), payload)
        next_design = self.new_design("after-legacy")
        self.assertEqual(next_design.name, "dd-010_after-legacy.md")

    def test_legacy_draft_is_preserved_and_warned_as_unpublished(self) -> None:
        legacy = self.repo / "docs/design-docs/legacy-draft.md"
        payload = (
            "---\n"
            'schema_version: "1"\n'
            'metadata_schema: "1"\n'
            "artifact_type: design-doc\n"
            "id: DD-009\n"
            "title: Legacy draft\n"
            "status: draft\n"
            "author: Historical Author\n"
            "owner: Historical Owner\n"
            "created: 2024-01-01\n"
            "updated: 2024-01-01\n"
            "---\n# Legacy draft\n"
        )
        legacy.write_text(payload, encoding="utf-8")
        self.run_cli("init")

        result = self.run_cli("validate")

        self.assertIn("legacy Design is unpublished: draft", result.stdout)
        self.assertEqual(legacy.read_text(encoding="utf-8"), payload)

    def test_snapshot_tampering_is_detected(self) -> None:
        design = self.new_design("tamper")
        self.publish(design)
        snapshot = self.repo / "docs/.designctl/snapshots/DD-001/rev-001/DESIGN.md"
        snapshot.write_text(snapshot.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
        result = self.run_cli("validate", expected=1)
        self.assertIn("snapshot", result.stdout)

    def test_skill_runs_after_independent_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "governed-design"
            shutil.copytree(ROOT, copied)
            repository = Path(temporary) / "repository"
            repository.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(copied / "scripts/designctl.py"),
                    "--repo",
                    str(repository),
                    "init",
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((repository / "docs/.designctl/state.json").is_file())


if __name__ == "__main__":
    unittest.main()
