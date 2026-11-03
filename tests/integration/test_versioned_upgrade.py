"""Offline real old-generator -> current-generator upgrade. Requires full Git history.

No manifest fabrication: the fixed previous distribution generates every old
record. RF_UPGRADE_ARTIFACT_DIR optionally retains all CLI stdout/stderr.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.spec_git_fixture import create_git_catalog

LEGACY_SHA = "88a72024018f9258ef7c66f7ad36bd0554df9ce1"
CURRENT = json.loads((ROOT / "release.json").read_text())


def inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file() and p.name != "lock"}


class RealVersionedUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        cls.old = cls.base / "old-source"
        cls.old.mkdir()
        archive = subprocess.run(["git", "archive", "--format=tar.gz", LEGACY_SHA], cwd=ROOT, capture_output=True, timeout=30)
        if archive.returncode:
            raise RuntimeError("Pinned legacy source unavailable; use a full Git checkout. " + archive.stderr.decode())
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:gz") as t:
            for member in t.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                    raise RuntimeError("Unsafe legacy source archive")
                target = cls.old / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(t.extractfile(member).read())
        cls.artifacts = Path(os.environ["RF_UPGRADE_ARTIFACT_DIR"]) if os.environ.get("RF_UPGRADE_ARTIFACT_DIR") else None
        if cls.artifacts:
            cls.artifacts.mkdir(parents=True, exist_ok=True)
            (cls.artifacts / "legacy-source-provenance.json").write_text(json.dumps(dict(commit=LEGACY_SHA,archive_sha256=hashlib.sha256(archive.stdout).hexdigest(),command=archive.args,exit_code=archive.returncode,stderr=archive.stderr.decode()),indent=2))
        assert (cls.old / "VERSION").read_text().strip() == "0.15.1"

    def setUp(self):
        self.test_tmp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.test_tmp.cleanup)
        self.work = Path(self.test_tmp.name)
        self.target = self.work / "target"
        self.target.mkdir()
        self.catalog, _ = create_git_catalog(self.work)
        self.sequence = 0
        self.cli(self.old, "bootstrap", "--all-adapters", "--spec-repository", self.catalog.as_uri(), "--spec-version", "0.1.0", "--spec", "languages/go", "--apply")
        m = json.loads((self.target / "docs/.engineering/harness.json").read_text())
        self.assertEqual(m["core"]["version"], "1.6.0")
        self.assertEqual(m["producer"]["version"], "0.15.1")
        self.cli(self.old, "validate", "--harness")
        self.initial = inventory(self.target)

    def cli(self, source, *args, expected=0):
        self.sequence += 1
        argv = [sys.executable, "-B", str(source / "scripts/foundryctl.py"), "--repo", str(self.target), *args]
        start = datetime.now(timezone.utc).isoformat()
        p = subprocess.run(argv, cwd=self.target, env=dict(os.environ, GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0"), capture_output=True, text=True, timeout=120)
        if self.artifacts:
            record = dict(argv=argv,cwd=str(self.target),start=start,end=datetime.now(timezone.utc).isoformat(),exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
            (self.artifacts / f"{self._testMethodName}-{self.sequence:02d}.json").write_text(json.dumps(record,indent=2))
        self.assertEqual(p.returncode, expected, p.stdout + "\n" + p.stderr)
        return json.loads(p.stdout) if p.stdout and p.returncode == 0 else p.stderr

    def test_preview_apply_validate_repeat_and_custom_documents(self):
        custom = {}
        for name in ("AGENTS.md", "ARCHITECTURE.md", "docs/owner-notes.md"):
            p = self.target / name
            p.write_bytes((p.read_bytes() if p.exists() else b"") + b"\nOwner-maintained regression sentinel.\n")
            custom[name] = p.read_bytes()
        before = inventory(self.target)
        manifest_before = (self.target / "docs/.engineering/harness.json").read_bytes()
        preview = self.cli(ROOT, "upgrade", "--to", CURRENT["distribution"])
        self.assertEqual(inventory(self.target), before, "preview must not mutate old install")
        self.assertEqual((self.target / "docs/.engineering/harness.json").read_bytes(), manifest_before)
        self.assertFalse([a for a in preview["actions"] if a["action"] == "conflict"])
        self.assertEqual(preview["from"]["core"], "1.6.0")
        self.assertEqual(preview["to"]["core"], CURRENT["core"])
        self.cli(ROOT, "upgrade", "--to", CURRENT["distribution"], "--apply")
        self.cli(ROOT, "validate", "--harness")
        self.cli(ROOT, "spec", "validate")
        m = json.loads((self.target / "docs/.engineering/harness.json").read_text())
        self.assertEqual(m["producer"]["version"], CURRENT["distribution"])
        self.assertEqual(m["core"]["version"], CURRENT["core"])
        self.assertEqual({a["id"]:a["version"] for a in m["adapters"]}, CURRENT["adapters"])
        for name, contents in custom.items():
            self.assertEqual((self.target / name).read_bytes(), contents)
        for name, digest in self.initial.items():
            if name.startswith("docs/agent-guides/managed/") or name.startswith("docs/.engineering/specs"):
                self.assertEqual(inventory(self.target)[name], digest, name)
        router = self.target / ".repo-foundry/engineering-specs/spec_router.py"
        self.assertEqual(router.read_bytes(), (ROOT / "assets/core/engineering-specs/spec_router.py").read_bytes())
        self.assertIn(b"preflight", router.read_bytes())
        after = inventory(self.target)
        repeat = self.cli(ROOT, "upgrade", "--to", CURRENT["distribution"], "--apply")
        self.assertEqual(repeat["updated"], [])
        self.assertEqual(inventory(self.target), after)

    def test_changed_generated_file_is_rejected_without_any_writes(self):
        paths = (
            ".repo-foundry/engineering-specs/spec_router.py",
            ".agents/skills/engineering-specs/scripts/spec_router.py",
            ".claude/skills/engineering-specs/SKILL.md",
            "docs/agent-guides/README.md",
        )
        for name in paths:
            with self.subTest(path=name):
                p = self.target / name
                original = p.read_bytes()
                p.write_bytes(original + b"\n# Unknown modified seed\n")
                before = inventory(self.target)
                preview = self.cli(ROOT, "upgrade", "--to", CURRENT["distribution"])
                self.assertIn(name, [a["path"] for a in preview["actions"] if a["action"] == "conflict"])
                self.assertIn("Harness upgrade preflight failed", self.cli(ROOT, "upgrade", "--to", CURRENT["distribution"], "--apply", expected=2))
                self.assertEqual(inventory(self.target), before)
                p.write_bytes(original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
