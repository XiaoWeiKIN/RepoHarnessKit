"""Regression contracts for coordinator-owned verification completion.

Standalone tests use a controlled Receipt adapter. In the full distribution,
the integration tests exercise the real verification_receipt implementation.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verification_completion.py"

FAKE_RECEIPT = '''
from pathlib import Path
import json
class handoff:
    class HandoffError(Exception):
        pass
    @staticmethod
    def repository_root(repo):
        return Path(repo).resolve()
def read(path):
    obj = json.loads(Path(path).read_text())
    if obj.get("tampered"):
        raise handoff.HandoffError("tampered")
    return {"command": obj["command"], "payload_sha256": "a" * 64,
            "revision": {"observed_files": [{"path": p} for p in obj.get("observed_paths", [])]}}
def check_receipt(root, path):
    obj = json.loads(Path(path).read_text())
    if obj.get("mutate_policy"):
        Path(obj["mutate_policy"]).write_text('{}')
    if obj.get("mutate_evidence"):
        Path(obj["mutate_evidence"]).write_text('{}')
    if obj.get("mutate_receipt"):
        return {"outcome": "passed", "receipt_sha256": "b" * 64,
                "exit_code": 0, "reasons": []}
    if obj.get("mutate_bound_file"):
        Path(obj["mutate_bound_file"]).write_text("modified during gate")
    if obj.get("corrupt_after_check"):
        Path(path).write_text("damaged after check")
    if obj.get("source_changed"):
        return {"outcome": "stale", "receipt_sha256": "a" * 64,
                "exit_code": 0, "reasons": ["OBSERVED_BYTES_CHANGED"]}
    return {"outcome": obj["outcome"], "receipt_sha256": "a" * 64,
            "exit_code": 0 if obj["outcome"] == "passed" else 1, "reasons": []}
def observe(root, inputs, base):
    return {"observed": [(p, (root / p).read_bytes().hex() if (root / p).is_file() else "missing")
                         for p in inputs]}
def drift(before, after):
    return [] if before == after else ["OBSERVED_BYTES_CHANGED"]
'''


class CompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        self.scripts = self.home / "scripts"
        self.scripts.mkdir()
        shutil.copyfile(SCRIPT, self.scripts / "verification_completion.py")
        (self.scripts / "verification_receipt.py").write_text(FAKE_RECEIPT)
        self.repo = self.home / "repo"
        self.repo.mkdir()
        self.policy = self.home / "policy.json"
        self.evidence = self.home / "evidence.json"
        self.tidy = self.home / "tidy.json"
        self.race = self.home / "race.json"
        self.write(self.policy, {"schema_version": 1, "required_checks": [
            {"id": "go-tidy", "command": ["go", "mod", "tidy", "-diff"]},
            {"id": "go-race", "command": ["go", "test", "-race", "./..."]},
        ]})
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"], "outcome": "passed"})
        self.write(self.race, {"command": ["go", "test", "-race", "./..."], "outcome": "passed"})
        self.write(self.evidence, {"schema_version": 1, "receipts": [
            {"id": "go-tidy", "path": str(self.tidy)},
            {"id": "go-race", "path": str(self.race)},
        ]})

    @staticmethod
    def write(path, obj):
        path.write_text(json.dumps(obj), encoding="utf-8")

    def run_gate(self, expected, policy_digest=None):
        if policy_digest is None:
            policy_digest = hashlib.sha256(self.policy.read_bytes()).hexdigest()
        result = subprocess.run(
            [sys.executable, "-B", str(self.scripts / "verification_completion.py"),
             "--repo", str(self.repo), "--policy", str(self.policy),
             "--policy-sha256", policy_digest, "--evidence", str(self.evidence)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + "\n" + result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def test_all_frozen_checks_pass(self):
        result = self.run_gate(0)
        self.assertEqual(result["completion"], "PASS")
        self.assertEqual([x["status"] for x in result["checks"]], ["PASS", "PASS"])

    def test_canonical_tidy_failed_must_block(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"], "outcome": "failed"})
        result = self.run_gate(1)
        self.assertEqual(result["completion"], "BLOCKED")
        self.assertEqual(result["checks"][0]["status"], "FAIL")

    def test_trusted_policy_digest_mismatch_rejected(self):
        self.run_gate(2, policy_digest="0" * 64)

    def test_policy_modified_mid_gate_blocks(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "mutate_policy": str(self.policy)})
        result = self.run_gate(1)
        self.assertIn("POLICY_CHANGED_DURING_GATE", result["input_changed_during_gate"])

    def test_evidence_modified_mid_gate_blocks(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "mutate_evidence": str(self.evidence)})
        result = self.run_gate(1)
        self.assertIn("EVIDENCE_CHANGED_DURING_GATE", result["input_changed_during_gate"])

    def test_receipt_changed_between_reads_blocks(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "mutate_receipt": True})
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["reason"], "RECEIPT_CHANGED_DURING_GATE")

    def test_policy_inside_worktree_rejected(self):
        path = self.repo / "policy.json"
        path.write_bytes(self.policy.read_bytes())
        self.policy = path
        self.run_gate(2)

    def test_absent_tidy_cannot_be_omitted(self):
        self.write(self.evidence, {"schema_version": 1, "receipts": [
            {"id": "go-race", "path": str(self.race)},
        ]})
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["reason"], "MISSING_RECEIPT")

    def test_tidy_receipt_cannot_be_replaced_by_other_command(self):
        self.write(self.tidy, {"command": ["go", "test", "./..."], "outcome": "passed"})
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["reason"], "COMMAND_MISMATCH")

    def test_source_drift_blocks_a_previous_pass(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "source_changed": True})
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["status"], "STALE")

    def test_unknown_execution_not_success(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"], "outcome": "unknown"})
        self.assertEqual(self.run_gate(1)["checks"][0]["status"], "UNVERIFIED")

    def test_invalid_receipt_fails_closed(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "tampered": True})
        self.assertEqual(self.run_gate(1)["checks"][0]["reason"], "INVALID_RECEIPT")

    def test_same_receipt_cannot_cover_two_checks(self):
        self.write(self.evidence, {"schema_version": 1, "receipts": [
            {"id": "go-tidy", "path": str(self.tidy)},
            {"id": "go-race", "path": str(self.tidy)},
        ]})
        self.run_gate(2)

    def test_duplicate_policy_id_rejected(self):
        self.write(self.policy, {"schema_version": 1, "required_checks": [
            {"id": "go-tidy", "command": ["go", "mod", "tidy", "-diff"]},
            {"id": "go-tidy", "command": ["go", "test", "./..."]},
        ]})
        self.run_gate(2)

    def test_empty_policy_rejected(self):
        self.write(self.policy, {"schema_version": 1, "required_checks": []})
        self.run_gate(2)

    def test_duplicate_json_fields_rejected(self):
        self.policy.write_text('{"schema_version": 1, "schema_version": 1, "required_checks": []}')
        self.run_gate(2)

    def test_receipt_absent_is_unverified(self):
        self.tidy.unlink()
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["status"], "UNVERIFIED")

    def test_ignored_source_changed_during_gate_blocks(self):
        ignored = self.repo / "ignored-source.txt"
        ignored.write_text("initial")
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "observed_paths": ["ignored-source.txt"],
                               "mutate_bound_file": str(ignored)})
        result = self.run_gate(1)
        self.assertEqual(result["completion"], "BLOCKED")
        self.assertIn("OBSERVED_BYTES_CHANGED", result["worktree_changed_during_gate"])

    def test_receipt_corrupted_after_check_blocks(self):
        self.write(self.tidy, {"command": ["go", "mod", "tidy", "-diff"],
                               "outcome": "passed", "corrupt_after_check": True})
        result = self.run_gate(1)
        self.assertEqual(result["completion"], "BLOCKED")
        self.assertIn("RECEIPT_CHANGED_DURING_GATE:go-tidy", result["input_changed_during_gate"])

    def test_receipt_hardlink_reuse_rejected(self):
        self.race.unlink()
        self.race.hardlink_to(self.tidy)
        self.run_gate(2)

    def test_receipt_content_copy_reuse_rejected(self):
        self.race.write_bytes(self.tidy.read_bytes())
        self.run_gate(2)

    def test_policy_parent_symlink_rejected(self):
        original = self.home / "trusted"
        original.mkdir()
        real = original / "policy.json"
        real.write_bytes(self.policy.read_bytes())
        alias = self.home / "alias"
        alias.symlink_to(original, target_is_directory=True)
        self.policy = alias / "policy.json"
        self.run_gate(2)

    def test_evidence_parent_symlink_rejected(self):
        original = self.home / "trusted-evidence"
        original.mkdir()
        real = original / "index.json"
        real.write_bytes(self.evidence.read_bytes())
        alias = self.home / "alias-evidence"
        alias.symlink_to(original, target_is_directory=True)
        self.evidence = alias / "index.json"
        self.run_gate(2)

    def test_receipt_parent_symlink_is_not_accepted(self):
        original = self.home / "trusted-receipts"
        original.mkdir()
        real = original / "tidy.json"
        real.write_bytes(self.tidy.read_bytes())
        alias = self.home / "alias-receipts"
        alias.symlink_to(original, target_is_directory=True)
        self.write(self.evidence, {"schema_version": 1, "receipts": [
            {"id": "go-tidy", "path": str(alias / "tidy.json")},
            {"id": "go-race", "path": str(self.race)},
        ]})
        result = self.run_gate(1)
        self.assertEqual(result["checks"][0]["status"], "UNVERIFIED")

    def test_symlink_policy_is_rejected(self):
        target = self.home / "target.json"
        target.write_bytes(self.policy.read_bytes())
        self.policy.unlink()
        self.policy.symlink_to(target)
        self.run_gate(2)


@unittest.skipUnless((ROOT / "scripts" / "verification_receipt.py").exists(),
                     "requires real RepoHarnessKit scripts/verification_receipt.py")
class RealReceiptIntegrationTests(unittest.TestCase):
    """Exercises the actual Receipt digest and revision-bound checks in the repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir()
        self.execute(["git", "init", "-b", "main"], cwd=self.repo)
        self.execute(["git", "config", "user.name", "Completion Tests"], cwd=self.repo)
        self.execute(["git", "config", "user.email", "completion@example.invalid"], cwd=self.repo)
        (self.repo / "code.py").write_text("print(1)\n")
        self.execute(["git", "add", "."], cwd=self.repo)
        self.execute(["git", "commit", "-m", "initial"], cwd=self.repo)
        self.receipt = self.base / "check.json"
        self.policy = self.base / "policy.json"
        self.evidence = self.base / "evidence.json"

    @staticmethod
    def execute(argv, cwd=None):
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=True)

    def make_case(self, command, expected_run):
        run = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "verification_receipt.py"),
             "--repo", str(self.repo), "run", "--output", str(self.receipt),
             "--", *command],
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, expected_run, run.stdout + run.stderr)
        self.policy.write_text(json.dumps({"schema_version": 1, "required_checks": [
            {"id": "required-check", "command": command}]}))
        self.evidence.write_text(json.dumps({"schema_version": 1, "receipts": [
            {"id": "required-check", "path": str(self.receipt)}]}))

    def gate(self, expected):
        digest = hashlib.sha256(self.policy.read_bytes()).hexdigest()
        run = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo),
             "--policy", str(self.policy), "--policy-sha256", digest,
             "--evidence", str(self.evidence)],
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, expected, run.stdout + run.stderr)
        return json.loads(run.stdout)

    def test_real_receipt_pass(self):
        self.make_case([sys.executable, "-c", "pass"], 0)
        self.assertEqual(self.gate(0)["completion"], "PASS")

    def test_real_receipt_failed_command(self):
        self.make_case([sys.executable, "-c", "raise SystemExit(3)"], 1)
        self.assertEqual(self.gate(1)["checks"][0]["status"], "FAIL")

    def test_real_receipt_stale_after_source_edit(self):
        self.make_case([sys.executable, "-c", "pass"], 0)
        (self.repo / "code.py").write_text("print(2)\n")
        self.assertEqual(self.gate(1)["checks"][0]["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
