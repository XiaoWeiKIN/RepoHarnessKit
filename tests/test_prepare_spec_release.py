"""Offline regression tests for Spec-driven RF patch release preparation."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prepare_spec_release", ROOT / "scripts/prepare_spec_release.py"
)
assert spec is not None and spec.loader is not None
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

FILES = (
    "VERSION", "scripts/foundryctl.py", "tests/test_foundryctl.py",
    "tests/test_repository_contracts.py", "README.md", "README.zh-CN.md",
    "references/specifications.md", "references/bootstrap.md",
    "references/upgrades.md", "release.json",
)


class SpecDrivenReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in FILES:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)

        self.old_rf = (self.root / "VERSION").read_text().strip()
        source = (self.root / "scripts/foundryctl.py").read_text()
        import re
        self.old_spec = re.search(r'DEFAULT_SPEC_VERSION = "([0-9.]+)"', source)[1]
        major, minor, _ = map(int, self.old_spec.split("."))
        self.new_spec = f"{major}.{minor + 1}.0"

    def snapshot(self) -> dict[str, bytes]:
        return {name: (self.root / name).read_bytes() for name in FILES}

    def test_next_catalog_prepares_one_patch_and_is_idempotent(self) -> None:
        before = self.snapshot()
        result = release.prepare(self.root, self.new_spec)
        major, minor, patch = map(int, self.old_rf.split("."))
        expected_rf = f"{major}.{minor}.{patch + 1}"
        self.assertEqual(result, {
            "action": "publish",
            "catalog_version": self.new_spec,
            "rf_version": expected_rf,
        })
        self.assertEqual((self.root / "VERSION").read_text().strip(), expected_rf)
        metadata = json.loads((self.root / "release.json").read_text())
        self.assertEqual(metadata["distribution"], expected_rf)
        self.assertEqual(metadata["default_spec_version"], self.new_spec)
        self.assertIn(
            f'DEFAULT_SPEC_VERSION = "{self.new_spec}"',
            (self.root / "scripts/foundryctl.py").read_text(),
        )
        self.assertNotEqual(self.snapshot(), before)
        after = self.snapshot()
        self.assertEqual(release.prepare(self.root, self.new_spec)["action"], "skip")
        self.assertEqual(release.prepare(self.root, self.old_spec)["action"], "skip")
        self.assertEqual(self.snapshot(), after)

    def test_missing_version_contract_fails_without_partial_writes(self) -> None:
        doc = self.root / "references/upgrades.md"
        doc.write_text(doc.read_text().replace(self.old_rf, "unsupported-version"))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Missing release contract"):
            release.prepare(self.root, self.new_spec)
        self.assertEqual(self.snapshot(), before)

    def test_rejects_invalid_catalog_version(self) -> None:
        before = self.snapshot()
        for value in ("main", "v1.9.0", "1.9.0; exit 0", "01.9.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.prepare(self.root, value)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
