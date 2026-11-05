from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install.py"
CURRENT_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SPEC = importlib.util.spec_from_file_location("repofoundry_installer", INSTALLER_PATH)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


class InstallerTestCase(unittest.TestCase):
    def test_public_brand_and_cli_identity_are_separate(self) -> None:
        self.assertEqual(installer.PRODUCT_NAME, "RepoHarnessKit")
        self.assertEqual(installer.PRODUCT_ID, "repo-foundry-ai")
        self.assertEqual(installer.CLI_VERSION_NAME, "RepoFoundry AI")
        with mock.patch("builtins.print") as printed:
            installer.print_human({
                "version": "0.15.3", "action": "installed",
                "home": "/tmp/repoharnesskit-demo",
                "cli": "/tmp/bin/repofoundry",
                "host_integrations": [], "backups": [],
            })
        self.assertIn("RepoHarnessKit 0.15.3 installed", printed.call_args_list[0].args[0])

    def run_installer(
        self,
        source: Path,
        prefix: Path,
        bin_dir: Path,
        *arguments: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(INSTALLER_PATH),
                "--source",
                str(source),
                "--prefix",
                str(prefix),
                "--bin-dir",
                str(bin_dir),
                *arguments,
                "--json",
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

    @staticmethod
    def copy_source(source: Path, version: str) -> None:
        shutil.copytree(
            ROOT,
            source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                "__pycache__",
                "*.pyc",
            ),
        )
        (source / "VERSION").write_text(f"{version}\n", encoding="utf-8")

    def test_local_install_and_repeat_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            bin_dir = root / "bin"
            first = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                ).stdout
            )
            self.assertEqual(first["action"], "installed")
            self.assertEqual(first["version"], CURRENT_VERSION)
            self.assertFalse(first["project_harnesses_modified"])
            self.assertEqual(first["host_integrations"], [])
            self.assertTrue((prefix / "current").is_symlink())
            self.assertEqual(
                (prefix / "current" / "VERSION").read_text(encoding="utf-8").strip(),
                CURRENT_VERSION,
            )
            launcher = bin_dir / "repofoundry"
            self.assertTrue(launcher.is_file())
            self.assertTrue(os.access(launcher, os.X_OK))
            version = subprocess.run(
                [str(launcher), "--version"],
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(
                version.stdout.strip(),
                f"RepoFoundry AI {CURRENT_VERSION}",
            )
            releases_before = sorted((prefix / "releases").iterdir())

            second = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                ).stdout
            )
            self.assertEqual(second["action"], "unchanged")
            self.assertEqual(second["backups"], [])
            self.assertEqual(releases_before, sorted((prefix / "releases").iterdir()))

    def test_package_requires_every_project_skill_entrypoint(self) -> None:
        required = (
            "assets/core/repo-foundry-ai/SKILL.md.template",
            "assets/adapters/codex/repo-foundry-ai/SKILL.md.template",
            "assets/adapters/codex/engineering-specs/SKILL.md.template",
            "assets/adapters/claude/repo-foundry-ai/SKILL.md.template",
            "assets/adapters/claude/engineering-specs/SKILL.md.template",
        )
        for relative in required:
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as temporary:
                    source = Path(temporary) / "source"
                    self.copy_source(source, "0.2.0")
                    (source / relative).unlink()
                    with self.assertRaisesRegex(
                        installer.InstallError,
                        "package entrypoint is missing or unsafe",
                    ):
                        installer.validate_package(source)

    def test_installed_discovery_contains_only_public_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex"
            self.run_installer(
                ROOT,
                root / "prefix",
                root / "bin",
                "--host", "codex",
                "--codex-home", str(codex_home),
            )
            skill = codex_home / "skills" / "repo-foundry-ai"
            discovered = {
                path.relative_to(skill).as_posix()
                for path in skill.rglob("SKILL.md")
            }
            self.assertEqual(
                discovered,
                {
                    "SKILL.md",
                    "architecture-design/SKILL.md",
                    "design-documentation/SKILL.md",
                    "engineering-benchmark/SKILL.md",
                    "engineering-case-study/SKILL.md",
                    "governed-design/SKILL.md",
                    "engineering-execution-plan/SKILL.md",
                    "engineering-research/SKILL.md",
                },
            )

    def test_legacy_skill_names_still_validate_without_duplicate_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            self.copy_source(source, "0.2.0")
            (source / "design-documentation").rename(source / "detailed-design")
            (source / "governed-design").rename(source / "engineering-design")
            # Simulate the older immutable distribution's own CLI layout.
            ctl = source / "scripts" / "foundryctl.py"
            ctl.write_text(
                ctl.read_text(encoding="utf-8").replace(
                    'SKILL_DIR / "governed-design" / "scripts" / "designctl.py"',
                    'SKILL_DIR / "engineering-design" / "scripts" / "designctl.py"',
                ),
                encoding="utf-8",
            )
            self.assertEqual(installer.validate_package(source), "0.2.0")

    def test_mixed_skill_naming_layout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            self.copy_source(source, "0.2.0")
            (source / "design-documentation").rename(source / "detailed-design")
            with self.assertRaisesRegex(installer.InstallError, "mixed or incomplete"):
                installer.validate_package(source)

    def test_missing_modern_skill_entrypoint_is_rejected(self) -> None:
        for relative in ("design-documentation/SKILL.md", "governed-design/SKILL.md"):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as temporary:
                    source = Path(temporary) / "source"
                    self.copy_source(source, "0.2.0")
                    (source / relative).unlink()
                    with self.assertRaisesRegex(installer.InstallError, "missing or unsafe"):
                        installer.validate_package(source)

    def test_pinned_legacy_template_names_remain_installable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            self.copy_source(source, "0.9.0")
            for path in (source / "assets").rglob("SKILL.md.template"):
                path.rename(path.with_name("SKILL.md"))
            self.assertEqual(installer.validate_package(source), "0.9.0")

    def test_upgrade_switches_current_and_retains_old_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_one = root / "source-one"
            source_two = root / "source-two"
            self.copy_source(source_one, "0.1.0")
            self.copy_source(source_two, "0.2.1")
            prefix = root / "prefix"
            bin_dir = root / "bin"

            first = json.loads(
                self.run_installer(
                    source_one,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                ).stdout
            )
            second = json.loads(
                self.run_installer(
                    source_two,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                ).stdout
            )
            self.assertEqual(first["action"], "installed")
            self.assertEqual(second["action"], "upgraded")
            self.assertEqual(len(list((prefix / "releases").iterdir())), 2)
            self.assertEqual(
                (prefix / "current" / "VERSION").read_text(encoding="utf-8").strip(),
                "0.2.1",
            )
            version = subprocess.run(
                [str(bin_dir / "repofoundry"), "--version"],
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(version.stdout.strip(), "RepoFoundry AI 0.2.1")
            refused = self.run_installer(
                source_one,
                prefix,
                bin_dir,
                "--host",
                "none",
                expected=1,
            )
            self.assertIn("refusing to downgrade", refused.stderr)
            self.assertEqual(
                (prefix / "current" / "VERSION").read_text(encoding="utf-8").strip(),
                "0.2.1",
            )

    def test_existing_codex_skill_is_backed_up_before_linking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            bin_dir = root / "bin"
            codex_home = root / "codex"
            existing = codex_home / "skills" / "repo-foundry-ai"
            existing.mkdir(parents=True)
            (existing / "custom.txt").write_bytes(b"keep-me\n")

            result = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "codex",
                    "--codex-home",
                    str(codex_home),
                ).stdout
            )
            self.assertTrue(existing.is_symlink())
            self.assertEqual(existing.resolve(), (prefix / "current").resolve())
            self.assertEqual(len(result["backups"]), 1)
            backup = Path(result["backups"][0])
            self.assertEqual((backup / "custom.txt").read_bytes(), b"keep-me\n")
            self.assertEqual(result["host_integrations"][0]["host"], "codex")

            repeated = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "codex",
                    "--codex-home",
                    str(codex_home),
                ).stdout
            )
            self.assertEqual(repeated["action"], "unchanged")
            self.assertEqual(repeated["backups"], [])

            cli_only = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                    "--codex-home",
                    str(codex_home),
                ).stdout
            )
            self.assertTrue(existing.is_symlink())
            self.assertEqual(cli_only["host_integrations"][0]["host"], "codex")

    def test_existing_claude_skill_is_backed_up_and_codex_link_is_retained(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            bin_dir = root / "bin"
            codex_home = root / "codex"
            claude_home = root / "claude"
            codex_skill = codex_home / "skills" / "repo-foundry-ai"
            claude_skill = claude_home / "skills" / "repo-foundry-ai"
            claude_skill.mkdir(parents=True)
            (claude_skill / "custom.txt").write_bytes(b"keep-claude\n")

            self.run_installer(
                ROOT,
                prefix,
                bin_dir,
                "--host",
                "codex",
                "--codex-home",
                str(codex_home),
                "--claude-home",
                str(claude_home),
            )
            result = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "claude",
                    "--codex-home",
                    str(codex_home),
                    "--claude-home",
                    str(claude_home),
                ).stdout
            )

            self.assertTrue(codex_skill.is_symlink())
            self.assertTrue(claude_skill.is_symlink())
            self.assertEqual(codex_skill.resolve(), (prefix / "current").resolve())
            self.assertEqual(claude_skill.resolve(), (prefix / "current").resolve())
            self.assertEqual(len(result["backups"]), 1)
            backup = Path(result["backups"][0])
            self.assertIn("claude-skill", backup.name)
            self.assertEqual((backup / "custom.txt").read_bytes(), b"keep-claude\n")
            self.assertEqual(
                {item["host"] for item in result["host_integrations"]},
                {"codex", "claude"},
            )

            repeated = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "claude",
                    "--codex-home",
                    str(codex_home),
                    "--claude-home",
                    str(claude_home),
                ).stdout
            )
            self.assertEqual(repeated["action"], "unchanged")
            self.assertEqual(repeated["backups"], [])

            cli_only = json.loads(
                self.run_installer(
                    ROOT,
                    prefix,
                    bin_dir,
                    "--host",
                    "none",
                    "--codex-home",
                    str(codex_home),
                    "--claude-home",
                    str(claude_home),
                ).stdout
            )
            self.assertEqual(
                {item["host"] for item in cli_only["host_integrations"]},
                {"codex", "claude"},
            )
            self.assertTrue(codex_skill.is_symlink())
            self.assertTrue(claude_skill.is_symlink())

    def test_auto_detects_codex_and_claude_configuration_homes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex"
            claude_home = root / "claude"
            codex_home.mkdir()
            claude_home.mkdir()
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    installer.select_hosts(
                        "auto",
                        codex_home,
                        False,
                        claude_home,
                        False,
                    ),
                    ["codex", "claude"],
                )

    def test_claude_config_dir_sets_default_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configured = str(Path(temporary) / "claude-config")
            with mock.patch.dict(
                os.environ,
                {"CLAUDE_CONFIG_DIR": configured},
                clear=False,
            ):
                self.assertEqual(installer.default_claude_home(), Path(configured))

    def test_unsafe_local_source_fails_before_activation(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            self.copy_source(source, "0.2.0")
            os.symlink("VERSION", source / "unsafe-link")
            prefix = root / "prefix"
            bin_dir = root / "bin"
            result = self.run_installer(
                source,
                prefix,
                bin_dir,
                "--host",
                "none",
                expected=1,
            )
            self.assertIn("cannot contain symlinks", result.stderr)
            self.assertFalse((prefix / "current").exists())
            self.assertFalse((bin_dir / "repofoundry").exists())

    def test_install_prefix_cannot_recursively_enter_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            self.copy_source(source, "0.2.0")
            prefix = source / "nested-install"
            result = self.run_installer(
                source,
                prefix,
                root / "bin",
                "--host",
                "none",
                expected=1,
            )
            self.assertIn("cannot be inside the local source tree", result.stderr)
            self.assertFalse(prefix.exists())

    def test_explicit_version_mismatch_fails_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            bin_dir = root / "bin"
            result = self.run_installer(
                ROOT,
                prefix,
                bin_dir,
                "--version",
                "9.9.9",
                "--host",
                "none",
                expected=1,
            )
            self.assertIn("does not match requested version", result.stderr)
            self.assertFalse((prefix / "current").exists())
            self.assertFalse((bin_dir / "repofoundry").exists())

    def test_future_install_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            prefix.mkdir()
            (prefix / "install.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "product": "repo-foundry-ai",
                        "active_release": {},
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_installer(
                ROOT,
                prefix,
                root / "bin",
                "--host",
                "none",
                expected=1,
            )
            self.assertIn("newer than this installer", result.stderr)
            self.assertFalse((prefix / "current").exists())
            self.assertFalse((prefix / "releases").exists())

    def test_remote_response_size_is_bounded(self) -> None:
        with self.assertRaisesRegex(installer.InstallError, "safety limit"):
            installer.read_response(io.BytesIO(b"12345"), 4)

    def test_launcher_failure_rolls_back_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "prefix"
            bin_dir = root / "bin"
            source = installer.PackageSource(
                root=ROOT,
                version=CURRENT_VERSION,
                provenance={"kind": "local", "path": str(ROOT)},
            )
            original_run = installer.subprocess.run

            def fail_launcher(command, *args, **kwargs):
                if command and str(command[0]).endswith("repofoundry"):
                    return subprocess.CompletedProcess(command, 1, "", "injected")
                return original_run(command, *args, **kwargs)

            with mock.patch.object(installer.subprocess, "run", side_effect=fail_launcher):
                with self.assertRaisesRegex(
                    installer.InstallError, "installed launcher validation failed"
                ):
                    installer.install_package(
                        source,
                        prefix,
                        bin_dir,
                        ["claude"],
                        root / "codex",
                        False,
                        root / "claude",
                    )
            self.assertFalse((prefix / "current").exists())
            self.assertFalse((prefix / "install.json").exists())
            self.assertFalse((bin_dir / "repofoundry").exists())
            claude_skill = root / "claude" / "skills" / "repo-foundry-ai"
            self.assertFalse(claude_skill.exists() or claude_skill.is_symlink())
            self.assertEqual(list((prefix / "releases").iterdir()), [])

    def test_archive_traversal_and_links_are_rejected(self) -> None:
        for unsafe_member in ("../escape", "root/link"):
            with self.subTest(member=unsafe_member):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    archive = root / "unsafe.tar.gz"
                    with tarfile.open(archive, "w:gz") as package:
                        member = tarfile.TarInfo(unsafe_member)
                        if unsafe_member.endswith("link"):
                            member.type = tarfile.SYMTYPE
                            member.linkname = "VERSION"
                            package.addfile(member)
                        else:
                            content = b"unsafe"
                            member.size = len(content)
                            package.addfile(member, io.BytesIO(content))
                    destination = root / "extract"
                    destination.mkdir()
                    with self.assertRaises(installer.InstallError):
                        installer.extract_archive(archive, destination)
                    self.assertFalse((root / "escape").exists())

    def test_release_resolution_is_stable_and_commit_pinned(self) -> None:
        tag_object = "a" * 40
        commit = "b" * 40

        def fake_github_json(_repository: str, endpoint: str):
            if endpoint == "releases/latest":
                return {
                    "tag_name": "v0.2.0",
                    "draft": False,
                    "prerelease": False,
                }
            if endpoint == "git/ref/tags/v0.2.0":
                return {"object": {"type": "tag", "sha": tag_object}}
            if endpoint == f"git/tags/{tag_object}":
                return {"object": {"type": "commit", "sha": commit}}
            raise AssertionError(endpoint)

        with mock.patch.object(installer, "github_json", side_effect=fake_github_json):
            tag = installer.release_tag("owner/repository", "latest")
            self.assertEqual(tag, "v0.2.0")
            self.assertEqual(
                installer.resolve_tag_commit("owner/repository", tag),
                commit,
            )

        with mock.patch.object(
            installer,
            "github_json",
            return_value={
                "tag_name": "v0.2.0",
                "draft": False,
                "prerelease": True,
            },
        ):
            with self.assertRaisesRegex(installer.InstallError, "not a stable"):
                installer.release_tag("owner/repository", "latest")


if __name__ == "__main__":
    unittest.main()
