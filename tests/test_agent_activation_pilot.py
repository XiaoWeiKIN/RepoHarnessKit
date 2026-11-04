"""Preparation/probe regressions, not Agent execution or semantic accuracy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_activation_pilot", ROOT / "evals/agent-activation/pilot.py")
PILOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOT)


class SourcePacketTests(unittest.TestCase):
    def test_protocol_matches_preparation_without_completed_trials(self):
        protocol = json.loads((ROOT / "evals/agent-activation/protocol.json").read_text())
        self.assertEqual(protocol["source_cases"], list(PILOT.CASE_IDS))
        self.assertEqual(protocol["planned_trials"], 3 * len(PILOT.CASE_IDS))
        self.assertEqual(protocol["counts"]["agent_trials_started"], 0)

    def test_pinned_parent_inputs_load(self):
        corpus = PILOT.load_corpus(PILOT.load_baseline())
        self.assertEqual(len(corpus["cases"]), 12)
        self.assertEqual(len(PILOT.CASE_IDS), 4)

    def test_only_task_and_before_bytes_enter_agent_projection(self):
        before = "package sample\n"
        case = {"task": "Read the file", "labels": {"applicable": ["GOLD-ID"]},
                "review": "secret", "category": "negative-control", "origin": "gold-origin",
                "planned_paths": ["hidden-path"], "actual_paths": ["hidden-path"],
                "snapshots": {"internal/sample/a.go": {"before": before,
                    "before_sha256": PILOT.sha(before.encode()), "after": "ANSWER", "after_sha256": "answer"}}}
        result = PILOT.source_task(case)
        self.assertEqual(result, {"task": "Read the file", "files": {"internal/sample/a.go": before}})
        encoded = json.dumps(result)
        for forbidden in ("GOLD-ID", "secret", "negative-control", "gold-origin", "hidden-path", "ANSWER"):
            self.assertNotIn(forbidden, encoded)

    def test_changed_before_digest_rejected(self):
        with self.assertRaises(PILOT.PilotError):
            PILOT.source_task({"task": "Read", "snapshots": {"a.go": {"before": "changed", "before_sha256": "0" * 64}}})

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            marker = p / "old"; marker.write_text("keep")
            with self.assertRaises(PILOT.PilotError):
                PILOT.reserve_output(p)
            self.assertEqual(marker.read_text(), "keep")

    def test_output_inside_source_is_rejected(self):
        with self.assertRaises(PILOT.PilotError):
            PILOT.reserve_output(ROOT / "never-create-agent-output")

    def test_symlink_output_parent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            with self.assertRaises(PILOT.PilotError):
                PILOT.reserve_output(root / "alias/new")

    def test_valid_official_preview(self):
        PILOT.check_preview({"mode": "dry-run", "actions": [{"action": "preserve"}],
                             "to": {"distribution": "0.15.2", "governance_profile": "strict"}})

    def test_conflicting_or_non_strict_preview_rejected(self):
        for change in ({"actions": [{"action": "conflict"}]}, {"actions": None},
                       {"mode": "apply"}, {"to": {"distribution": "0.15.2", "governance_profile": "adaptive"}}):
            value = {"mode": "dry-run", "actions": [],
                     "to": {"distribution": "0.15.2", "governance_profile": "strict"}, **change}
            with self.subTest(change=change), self.assertRaises(PILOT.PilotError):
                PILOT.check_preview(value)

    def test_protected_business_and_normative_bytes_cannot_change(self):
        for path in ("service/a.go", "go.mod", "go.sum", "docs/agent-guides/managed/go.md",
                     "docs/.engineering/specs.lock.json"):
            with self.subTest(path=path), self.assertRaises(PILOT.PilotError):
                PILOT.protect_business({path: "a"}, {path: "b"})

    def test_new_business_file_during_upgrade_rejected(self):
        with self.assertRaises(PILOT.PilotError):
            PILOT.protect_business({}, {"unexpected.go": "new"})

    def test_upgrade_can_change_only_harness_inputs_in_this_check(self):
        PILOT.protect_business({"service/a.go": "same", ".repo-foundry/router.py": "old"},
                               {"service/a.go": "same", ".repo-foundry/router.py": "new"})


class RuntimeProbeTests(unittest.TestCase):
    def test_missing_cli_does_not_launch_any_process(self):
        with patch.object(PILOT.shutil, "which", return_value=None), patch.object(PILOT.subprocess, "run") as run:
            result = PILOT.probe_runtime()
        run.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED_NOT_STARTED")
        self.assertEqual(result["agent_trials_started"], 0)
        self.assertIsNone(result["activation_recall"])
        self.assertIsNone(result["activation_precision"])

    def test_probe_only_runs_version_and_login_not_model(self):
        calls = [subprocess.CompletedProcess([], 0, "codex fixed-version\n", ""),
                 subprocess.CompletedProcess([], 0, "SENSITIVE-AUTH-OUTPUT", "")]
        with patch.object(PILOT.shutil, "which", return_value="/trusted/codex"), \
             patch.object(PILOT.subprocess, "run", side_effect=calls) as run:
            result = PILOT.probe_runtime()
        self.assertEqual([c.args[0] for c in run.call_args_list],
                         [["/trusted/codex", "--version"], ["/trusted/codex", "login", "status"]])
        self.assertEqual(result["status"], "LOCAL_PREREQUISITES_ONLY")
        self.assertEqual(result["model_access"], "NOT_TESTED")
        self.assertNotIn("SENSITIVE-AUTH-OUTPUT", json.dumps(result))

    def test_login_failure_without_credential_stays_blocked(self):
        calls = [subprocess.CompletedProcess([], 0, "codex fixed-version", ""),
                 subprocess.CompletedProcess([], 1, "", "")]
        with patch.dict(PILOT.os.environ, {}, clear=True), \
             patch.object(PILOT.shutil, "which", return_value="/trusted/codex"), \
             patch.object(PILOT.subprocess, "run", side_effect=calls):
            result = PILOT.probe_runtime()
        self.assertIn("AGENT_AUTH_NOT_CONFIRMED", result["blockers"])

    def test_api_key_value_is_never_reported(self):
        with patch.dict(PILOT.os.environ, {"CODEX_API_KEY": "DO-NOT-PRINT"}), \
             patch.object(PILOT.shutil, "which", return_value=None):
            result = PILOT.probe_runtime()
        self.assertTrue(result["credential_environment_present"])
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_probe_timeout_is_blocked_not_success(self):
        with patch.object(PILOT.shutil, "which", return_value="/trusted/codex"), \
             patch.object(PILOT.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 10)):
            result = PILOT.probe_runtime()
        self.assertEqual(result["status"], "BLOCKED_NOT_STARTED")
        self.assertEqual(result["agent_trials_started"], 0)

    def test_unknown_agent_is_not_guessed(self):
        with self.assertRaises(PILOT.PilotError):
            PILOT.probe_runtime("invented-runtime")


if __name__ == "__main__":
    unittest.main()
