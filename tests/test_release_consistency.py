"""Mutation tests for the release gate, using a real ownership declaration."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/check_release.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class ReleaseConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        for name in ("VERSION", "release.json", "scripts/foundryctl.py"):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "assets", self.root / "assets")
        for args in (("init",), ("add", "."), ("-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "-m", "baseline")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_unchanged_release_passes(self):
        self.assertTrue(gate.check(self.root, "HEAD")["ok"])

    def test_each_owner_requires_bump_for_changed_template_bytes(self):
        constants = gate.declarations((self.root / "scripts/foundryctl.py").read_bytes())
        for owner, (_, assets) in gate.OWNERS.items():
            with self.subTest(owner=owner):
                p = self.root / "assets" / constants[assets][0][1]
                original = p.read_bytes()
                p.write_bytes(original + b"\n# Changed versioned template\n")
                result = gate.check(self.root, "HEAD")
                self.assertFalse(result["ok"])
                self.assertTrue(any(f"RELEASE_COMPONENT_VERSION_REQUIRED: {owner}" in e for e in result["errors"]), result)
                p.write_bytes(original)

    def test_versioned_file_mapping_change_requires_owner_bump(self):
        p = self.root / "scripts/foundryctl.py"
        p.write_text(p.read_text().replace('("docs/agent-guides/README.md", "adapters/portable/agent-guide.md")', '("docs/agent-guides/NEW.md", "adapters/portable/agent-guide.md")'))
        result = gate.check(self.root, "HEAD")
        self.assertTrue(any("RELEASE_COMPONENT_VERSION_REQUIRED: portable" in e for e in result["errors"]), result)

    def test_bumped_component_still_requires_distribution_bump(self):
        p = self.root / "scripts/foundryctl.py"
        source = p.read_text()
        current = gate.declarations(source.encode())["CORE_HARNESS_VERSION"]
        major, minor, patch = gate.version(current)
        bumped = f"{major}.{minor}.{patch + 1}"
        p.write_text(source.replace(f'CORE_HARNESS_VERSION = "{current}"',
                                   f'CORE_HARNESS_VERSION = "{bumped}"'))
        metadata = json.loads((self.root / "release.json").read_text())
        metadata["core"] = bumped
        (self.root / "release.json").write_text(json.dumps(metadata))
        result = gate.check(self.root, "HEAD")
        self.assertTrue(any("RELEASE_DISTRIBUTION_VERSION_REQUIRED: core" in e for e in result["errors"]), result)

    def test_stale_release_metadata_fails(self):
        p = self.root / "release.json"
        data = json.loads(p.read_text()); data["adapters"]["codex"] = "0.0.0"
        p.write_text(json.dumps(data))
        self.assertIn("RELEASE_METADATA_MISMATCH", " ".join(gate.check(self.root, "HEAD")["errors"]))

    def test_history_is_parsed_without_execution(self):
        source = (ROOT / "scripts/foundryctl.py").read_bytes()
        current = gate.declarations(source)["CORE_HARNESS_VERSION"]
        mutated = source.replace(f'CORE_HARNESS_VERSION = "{current}"'.encode(),
                                 b'CORE_HARNESS_VERSION = print("must not execute")')
        self.assertNotEqual(source, mutated)
        with self.assertRaisesRegex(ValueError, "Nonliteral"):
            gate.declarations(mutated)


if __name__ == "__main__":
    unittest.main()
