"""Workflow text contracts and real CLI plumbing, not an Agent effectiveness eval."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.spec_git_fixture import create_git_catalog, git, commit_all

ROOT = Path(__file__).resolve().parents[1]
GUIDES = (
    "assets/adapters/codex/engineering-specs/SKILL.md.template",
    "assets/adapters/claude/engineering-specs/SKILL.md.template",
    "assets/adapters/portable/agent-guide.md",
)


class SpecWorkflowTextTests(unittest.TestCase):
    """Guard the instruction contract; these assertions do not prove Agent behavior."""

    def test_candidate_cards_precede_exclusion_in_every_adapter(self):
        for name in GUIDES:
            with self.subTest(guide=name):
                text = (ROOT / name).read_text()
                self.assertIn("before excluding", text)
                self.assertIn("--spec <candidate-spec-id>", text)
                self.assertNotIn("cards only for applicable Specs", text)
                self.assertNotIn("cards for applicable Specs", text)
                self.assertIn("uncertain", text)

    def test_delivery_is_sequential_and_observed_not_just_emitted(self):
        for name in GUIDES:
            with self.subTest(guide=name):
                text = (ROOT / name).read_text()
                self.assertIn("separate, sequential tool calls", text)
                self.assertIn("model-visible", text)
                self.assertIn("truncation", text)
                self.assertIn("same capsule", text)
                self.assertIn("UNVERIFIED", text)
                self.assertNotIn("max_output_tokens: 6500", text)
                self.assertNotIn("max_output_tokens: 5200", text)

    def test_shared_workflow_preserves_lightweight_modes_and_uncertainty(self):
        text = (ROOT / "assets/core/repo-foundry-ai/SKILL.md.template").read_text()
        self.assertIn("before excluding", text)
        self.assertIn("model-visible", text)
        self.assertIn("uncertain", text)
        self.assertIn("Explore", text)
        self.assertIn("ordinary read-only", text)
        self.assertLessEqual(len(text.splitlines()), 120)

    def test_templates_do_not_encode_case_answers(self):
        for name in GUIDES:
            with self.subTest(guide=name):
                text = (ROOT / name).read_text()
                self.assertNotIn("SIM-CHANGE-001", text)
                self.assertNotIn("internal/sample/count.go", text)
                self.assertIn("independently", text)


class SpecWorkflowCLITests(unittest.TestCase):
    """Use an offline synthetic Catalog and the unchanged production CLI."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.repo = base / "target"
        cls.repo.mkdir()
        catalog, _ = create_git_catalog(base)
        git(cls.repo, "init", "-b", "main")
        (cls.repo / "main.go").write_text("package main\n")
        commit_all(cls.repo, "initial")
        cls.invoke([sys.executable, "-B", str(ROOT / "scripts/foundryctl.py"),
                    "--repo", str(cls.repo), "bootstrap", "--all-adapters",
                    "--governance-profile", "strict", "--spec-repository", catalog.as_uri(),
                    "--spec-version", "0.1.0", "--spec", "languages/go", "--apply"])
        commit_all(cls.repo, "installed")
        cls.router = cls.repo / ".repo-foundry/engineering-specs/spec_router.py"

    @classmethod
    def invoke(cls, argv, expected=0):
        result = subprocess.run(argv, cwd=cls.repo, capture_output=True, text=True, timeout=60)
        if result.returncode != expected:
            raise AssertionError(f"{argv}: {result.returncode}\n{result.stdout}\n{result.stderr}")
        return result

    def route(self, *args, expected=0):
        return self.invoke([sys.executable, "-B", str(self.router), *args], expected)

    def test_all_candidate_batches_are_readable_without_activation(self):
        before = git(self.repo, "status", "--porcelain", "--untracked-files=all").stdout
        state_dir = self.repo / ".git/repo-foundry/spec-activation-v2"
        runtime_before = {p.name: p.read_bytes() for p in state_dir.glob("*.json")}
        candidates = json.loads(self.route("candidates", "--path", "main.go").stdout)
        ids = []
        for candidate in candidates["candidates"]:
            result = json.loads(self.route("requirements", "--path", "main.go",
                                           "--spec", candidate["id"]).stdout)
            ids.extend(card["id"] for card in result["cards"])
            self.assertEqual(candidate["requirements"], [card["id"] for card in result["cards"]])
            for card in result["cards"]:
                self.assertTrue(card["activation"])
        self.assertEqual(set(ids), {"SEM-NAME-001", "GO-NAME-001", "GO-TEST-001"})
        self.assertEqual(before, git(self.repo, "status", "--porcelain", "--untracked-files=all").stdout)
        self.assertEqual(runtime_before, {p.name: p.read_bytes() for p in state_dir.glob("*.json")})

    def test_small_card_budget_rejects_instead_of_silently_dropping_rules(self):
        result = self.route("requirements", "--path", "main.go", "--spec", "languages/go",
                            "--card-budget-bytes", "1", expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("ROUTER_REQUIREMENT_CARDS_TOO_LARGE", result.stderr)

    def test_independent_rehydrate_preserves_exact_dependency_closure(self):
        for adapter in ("codex", "claude", "portable"):
            with self.subTest(adapter=adapter):
                identity = ("--adapter-id", adapter, "--session-id", "workflow-test", "--turn-id", "rename")
                self.route("begin", *identity, "--prompt", "Rename a Go API")
                activation = json.loads(self.route("activate", *identity, "--path", "main.go",
                    "--spec", "languages/go", "--requirement", "GO-NAME-001",
                    "--because", "GO-NAME-001=rename a public Go API").stdout)
                self.assertEqual([r["id"] for r in activation["resolved_requirements"]],
                                 ["SEM-NAME-001", "GO-NAME-001"])
                undelivered = json.loads(self.route("preflight", *identity, "--path", "main.go", expected=1).stdout)
                self.assertFalse(undelivered["capsule_delivered_in_current_epoch"])
                response = json.loads(self.route("rehydrate", *identity).stdout)
                marker = "# Engineering Specification Context Capsule"
                context = response["context"]
                capsule = context[context.index(marker):].encode()
                self.assertEqual(hashlib.sha256(capsule).hexdigest(), activation["capsule"]["sha256"])
                self.assertEqual(len(capsule), activation["capsule"]["bytes"])
                self.assertIn(b"### SEM-NAME-001", capsule)
                self.assertNotIn(b"UNRELATED-TEST-SENTINEL", capsule)
                preflight = json.loads(self.route("preflight", *identity, "--path", "main.go",
                    "--expect-requirement", "GO-NAME-001").stdout)
                self.assertTrue(preflight["ok"])
                # An explicit independent expectation still catches a missing choice.
                missing = json.loads(self.route("preflight", *identity, "--path", "main.go",
                    "--expect-requirement", "GO-TEST-001", expected=1).stdout)
                self.assertEqual(missing["missing_requirements"], ["GO-TEST-001"])
                self.assertTrue(missing["applicability_review_required"])
                # This process-side success does NOT assert client-visible delivery.


if __name__ == "__main__":
    unittest.main()
