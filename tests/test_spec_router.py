from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.spec_git_fixture import create_git_catalog, git


ROOT = Path(__file__).resolve().parents[1]
FOUNDRYCTL = ROOT / "scripts" / "foundryctl.py"


class SpecRouterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "target"
        self.repo.mkdir()
        self.catalog, _ = create_git_catalog(self.base)
        git(self.repo, "init", "-b", "main")
        (self.repo / "go.mod").write_text(
            "module example.test/router\n",
            encoding="utf-8",
        )
        source = self.repo / "service" / "main.go"
        source.parent.mkdir()
        source.write_text("package service\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(
            self.repo,
            "-c",
            "user.name=Router Test",
            "-c",
            "user.email=router@example.invalid",
            "commit",
            "-m",
            "initial target",
        )
        self.run_foundry(
            "bootstrap",
            "--profile",
            "codex",
            "--governance-profile",
            "strict",
            "--spec-repository",
            self.catalog.resolve().as_uri(),
            "--spec-version",
            "0.1.0",
            "--spec",
            "languages/go",
            "--apply",
        )
        git(self.repo, "add", ".")
        git(
            self.repo,
            "-c",
            "user.name=Router Test",
            "-c",
            "user.email=router@example.invalid",
            "commit",
            "-m",
            "bootstrap harness",
        )
        self.router = (
            self.repo
            / ".agents"
            / "skills"
            / "engineering-specs"
            / "scripts"
            / "spec_router.py"
        )
        self.core_router = (
            self.repo
            / ".repo-foundry"
            / "engineering-specs"
            / "spec_router.py"
        )

    def set_governance_profile(self, profile: str) -> None:
        manifest_path = self.repo / "docs/.engineering/harness.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["governance"] = {
            "policy_schema": 1,
            "profile": profile,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_foundry(
        self,
        *arguments: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(FOUNDRYCTL),
                "--repo",
                str(self.repo),
                *arguments,
            ],
            text=True,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != expected:
            self.fail(
                f"expected {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def run_router(
        self,
        *arguments: str,
        stdin: dict[str, object] | None = None,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-B", str(self.router), *arguments],
            cwd=self.repo,
            input=(json.dumps(stdin) if stdin is not None else None),
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != expected:
            self.fail(
                f"expected {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def run_core(
        self,
        *arguments: str,
        stdin: dict[str, object] | None = None,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-B", str(self.core_router), *arguments],
            cwd=self.repo,
            input=(json.dumps(stdin) if stdin is not None else None),
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != expected:
            self.fail(
                f"expected {expected}, got {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def hook(self, event: str, **values: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(self.repo),
            "hook_event_name": event,
            "model": "test-model",
            "permission_mode": "default",
        }
        payload.update(values)
        result = self.run_router("hook", stdin=payload)
        return json.loads(result.stdout) if result.stdout else {}

    def initialize_turn(self) -> dict[str, object]:
        output = self.hook(
            "UserPromptSubmit",
            prompt="Rename the public Go service API",
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("$engineering-specs", context)
        self.assertIn("Session ID: `session-1`", context)
        self.assertIn("languages/go", context)
        return output

    def activate_go(self, *paths: str) -> dict[str, object]:
        arguments = [
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
        ]
        for path in paths:
            arguments.extend(("--path", path))
        arguments.extend(("--spec", "languages/go"))
        return json.loads(self.run_router(*arguments).stdout)

    def test_bootstrap_generates_one_valid_router_skill_and_hooks(self) -> None:
        self.assertTrue(self.router.is_file())
        self.assertTrue(self.core_router.is_file())
        self.assertTrue(
            (self.repo / ".agents/skills/engineering-specs/SKILL.md").is_file()
        )
        hooks = json.loads(
            (self.repo / ".codex/hooks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(hooks["hooks"]),
            {"UserPromptSubmit", "SubagentStart", "PreToolUse", "Stop"},
        )
        agents = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("$engineering-specs", agents)
        requirement_index = json.loads(
            (
                self.repo
                / "docs"
                / "agent-guides"
                / "managed"
                / "requirements.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(requirement_index["schema_version"], 2)
        self.run_foundry("spec", "validate")
        self.run_foundry("validate", "--harness")

    def test_adaptive_explore_allows_reversible_write_and_promotes_monotonically(
        self,
    ) -> None:
        self.set_governance_profile("adaptive")
        started = self.initialize_turn()
        context = started["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Adaptive Explore mode is active", context)
        self.assertIn("Governance mode: `explore`", context)

        allowed = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_input={
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: service/main.go\n"
                    "@@\n-package service\n+package service\n"
                    "*** End Patch"
                )
            },
        )
        self.assertEqual(allowed, {})

        promoted = json.loads(
            self.run_router(
                "classify",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--mode",
                "build",
                "--reason",
                "bounded production source change",
            ).stdout
        )
        self.assertEqual(promoted["governance_profile"], "adaptive")
        self.assertEqual(promoted["governance_mode"], "build")
        self.assertTrue(promoted["promoted"])

        denied = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_input={
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: service/main.go\n"
                    "@@\n-package service\n+package service\n"
                    "*** End Patch"
                )
            },
        )
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertIn(
            "activation before editing",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

        downgrade = self.run_router(
            "classify",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--mode",
            "explore",
            "--reason",
            "try to bypass Build",
            expected=2,
        )
        self.assertIn("ROUTER_GOVERNANCE_DOWNGRADE_DENIED", downgrade.stderr)

        governed = json.loads(
            self.run_router(
                "classify",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--mode",
                "governed",
                "--reason",
                "public API compatibility trigger discovered",
            ).stdout
        )
        self.assertEqual(governed["governance_mode"], "governed")

    def test_adaptive_explore_stop_and_audit_do_not_require_activation(self) -> None:
        self.set_governance_profile("adaptive")
        self.initialize_turn()
        (self.repo / "notes.txt").write_text("local exploration\n", encoding="utf-8")

        audit = json.loads(
            self.run_router(
                "audit",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--message",
                "Exploration result with ordinary prose.",
            ).stdout
        )
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["governance_mode"], "explore")
        self.assertEqual(audit["missing_handoff_labels"], [])
        self.assertIn("notes.txt", audit["changed_paths"])

        stopped = self.hook(
            "Stop",
            last_assistant_message="Exploration result with ordinary prose.",
        )
        self.assertEqual(stopped, {})

    def test_strict_profile_cannot_downgrade_from_governed(self) -> None:
        self.initialize_turn()
        status = json.loads(
            self.run_router(
                "status",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        self.assertEqual(status["governance_profile"], "strict")
        self.assertEqual(status["governance_mode"], "governed")

        result = self.run_router(
            "classify",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--mode",
            "build",
            "--reason",
            "attempted downgrade",
            expected=2,
        )
        self.assertIn("ROUTER_GOVERNANCE_DOWNGRADE_DENIED", result.stderr)

    def test_codex_and_portable_share_results_but_isolate_receipts(self) -> None:
        self.initialize_turn()
        codex_candidates = json.loads(
            self.run_router(
                "candidates",
                "--path",
                "service/main.go",
            ).stdout
        )
        codex_activation = self.activate_go("service/main.go")

        portable_start = {
            "protocol_version": 2,
            "event": "session_start",
            "adapter_id": "portable",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "prompt": "Rename the public Go service API",
        }
        started = json.loads(
            self.run_core("event", stdin=portable_start).stdout
        )
        self.assertEqual(started["decision"], "allow")
        self.assertIn("Adapter ID: `portable`", started["context"])
        portable_candidates = json.loads(
            self.run_core(
                "candidates",
                "--path",
                "service/main.go",
            ).stdout
        )
        portable_activation = json.loads(
            self.run_core(
                "activate",
                "--adapter-id",
                "portable",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
            ).stdout
        )

        self.assertEqual(
            [item["id"] for item in portable_candidates["candidates"]],
            [item["id"] for item in codex_candidates["candidates"]],
        )
        self.assertEqual(
            portable_activation["activated_specs"],
            codex_activation["activated_specs"],
        )
        mutation = {
            "protocol_version": 2,
            "event": "before_mutation",
            "adapter_id": "portable",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "tool": {
                "category": "file_write",
                "name": "portable-write",
                "paths": ["service/main.go"],
                "input": {},
            },
        }
        first_write = json.loads(
            self.run_core("event", stdin=mutation).stdout
        )
        self.assertEqual(first_write["decision"], "deny")
        self.assertIn("BEGIN languages/go", first_write["context"])
        second_write = json.loads(
            self.run_core("event", stdin=mutation).stdout
        )
        self.assertEqual(second_write, {"decision": "allow"})
        codex_status = json.loads(
            self.run_router(
                "status",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        portable_status = json.loads(
            self.run_core(
                "status",
                "--adapter-id",
                "portable",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        self.assertEqual(codex_status["adapter_id"], "codex")
        self.assertEqual(portable_status["adapter_id"], "portable")

    def test_claude_manual_flow_shares_results_and_isolates_receipts(self) -> None:
        self.initialize_turn()
        codex_candidates = json.loads(
            self.run_router(
                "candidates",
                "--path",
                "service/main.go",
            ).stdout
        )
        codex_activation = self.activate_go("service/main.go")

        self.run_core(
            "begin",
            "--adapter-id",
            "claude",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--prompt",
            "Rename the public Go service API",
        )
        claude_candidates = json.loads(
            self.run_core(
                "candidates",
                "--path",
                "service/main.go",
            ).stdout
        )
        claude_activation = json.loads(
            self.run_core(
                "activate",
                "--adapter-id",
                "claude",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
            ).stdout
        )
        self.assertEqual(
            [item["id"] for item in claude_candidates["candidates"]],
            [item["id"] for item in codex_candidates["candidates"]],
        )
        self.assertEqual(
            claude_activation["activated_specs"],
            codex_activation["activated_specs"],
        )
        claude_status = json.loads(
            self.run_core(
                "status",
                "--adapter-id",
                "claude",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        codex_status = json.loads(
            self.run_router(
                "status",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        self.assertEqual(claude_status["adapter_id"], "claude")
        self.assertEqual(codex_status["adapter_id"], "codex")
        handoff = "\n".join(
            (
                "Activated specifications: languages/go",
                "Activated requirements: naming",
                "Verification: router tests",
                "Exceptions: none",
                "Compatibility or migration: none",
            )
        )
        audit = json.loads(
            self.run_core(
                "audit",
                "--adapter-id",
                "claude",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--message",
                handoff,
            ).stdout
        )
        self.assertTrue(audit["ok"])

        self.run_core(
            "begin",
            "--adapter-id",
            "claude",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-none",
        )
        explicit_none = json.loads(
            self.run_core(
                "activate",
                "--adapter-id",
                "claude",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-none",
                "--path",
                "README.md",
                "--none",
                "--reason",
                "Documentation-only task has no applicable locked Spec",
            ).stdout
        )
        self.assertEqual(explicit_none["decision"], "none")
        self.assertEqual(explicit_none["activated_specs"], [])


    def test_session_context_budget_uses_routing_index_pointer_when_large(self) -> None:
        index = self.repo / "docs/agent-guides/managed/index.md"
        index.write_text(
            index.read_text(encoding="utf-8") + "\n" + "UNRELATED_CONTEXT_PADDING\n" * 900,
            encoding="utf-8",
        )
        result = json.loads(
            self.run_core(
                "event",
                stdin={
                    "protocol_version": 2,
                    "event": "session_start",
                    "adapter_id": "portable",
                    "session_id": "budget-session",
                    "turn_id": "budget-turn",
                    "prompt": "Inspect the cache module",
                },
            ).stdout
        )
        self.assertEqual(result["decision"], "allow")
        self.assertIn("Governance mode:", result["context"])
        self.assertIn(
            "[ContextRef:routing-index] docs/agent-guides/managed/index.md",
            result["context"],
        )
        self.assertNotIn("UNRELATED_CONTEXT_PADDING", result["context"])
        budget = result["context_plan"]
        self.assertLessEqual(budget["used_bytes"], budget["budget_bytes"])
        self.assertEqual(
            [section["selection"] for section in budget["selections"]],
            ["content", "reference"],
        )
        self.assertEqual(len(result["context"].encode("utf-8")), budget["used_bytes"])


    def test_session_context_ep_snapshot_and_current_adr_navigation(self) -> None:
        self.set_governance_profile("adaptive")
        plan_dir = self.repo / "docs/exec-plans/active/ep-123_cache-invalidation"
        plan_dir.mkdir(parents=True)
        plan = plan_dir / "EXECPLAN.md"
        plan.write_text(
            '---\nid: EP-123\nstatus: active\nadr_refs: ["ADR-012", "ADR-099"]\n---\n'
            '# Cache invalidation\n\n## Current Snapshot\n\n'
            '- Current milestone: Validate cache eviction.\n'
            '- Next action: Run the focused cache tests.\n\n'
            '## Context and Orientation\n\nThis should not be injected.\n',
            encoding="utf-8",
        )
        unrelated = self.repo / "docs/exec-plans/active/ep-124_other"
        unrelated.mkdir(parents=True)
        (unrelated / "EXECPLAN.md").write_text(
            "---\nid: EP-124\nstatus: active\n---\n"
            "## Current Snapshot\n\nUNRELATED_EP_SECRET\n",
            encoding="utf-8",
        )
        adr_path = self.repo / "docs/adr/adr-012_current-contract.md"
        adr_path.parent.mkdir(parents=True, exist_ok=True)
        adr_path.write_text("current ADR source\n", encoding="utf-8")
        adr_index = self.repo / "docs/DECISIONS.md"
        adr_index.write_text(
            "# Decisions\n<!-- ADRCTL:CURRENT:START -->\n"
            "| ADR-012 | Current | accepted | current | — | — | — | "
            "[ADR](adr/adr-012_current-contract.md) |\n"
            "<!-- ADRCTL:CURRENT:END -->\n",
            encoding="utf-8",
        )
        started = json.loads(
            self.run_core(
                "event",
                stdin={
                    "protocol_version": 2,
                    "event": "session_start",
                    "adapter_id": "portable",
                    "session_id": "ep-context-session",
                    "turn_id": "ep-context-turn",
                    "prompt": "Continue EP-123 without changing other EPs.",
                },
            ).stdout
        )
        self.assertEqual(started["decision"], "allow")
        self.assertIn("Validate cache eviction", started["context"])
        self.assertIn("Next action: Run the focused cache tests", started["context"])
        self.assertNotIn("This should not be injected", started["context"])
        self.assertNotIn("UNRELATED_EP_SECRET", started["context"])
        self.assertIn("ADR-012: docs/adr/adr-012_current-contract.md", started["context"])
        self.assertIn("ADR-099: not in the current-effect projection", started["context"])
        self.assertLessEqual(
            started["context_plan"]["used_bytes"],
            started["context_plan"]["budget_bytes"],
        )
        resumed = json.loads(
            self.run_core(
                "rehydrate", "--adapter-id", "portable",
                "--session-id", "ep-context-session", "--turn-id", "ep-context-turn",
            ).stdout
        )
        self.assertIn("Validate cache eviction", resumed["context"])
        self.assertIn("ADR-012: docs/adr/adr-012_current-contract.md", resumed["context"])
        self.assertNotIn("UNRELATED_EP_SECRET", resumed["context"])
        self.run_foundry("validate", "--harness")

    def test_session_context_without_explicit_ep_does_not_load_other_plans(self) -> None:
        plan_dir = self.repo / "docs/exec-plans/active/ep-127_unrelated"
        plan_dir.mkdir(parents=True)
        (plan_dir / "EXECPLAN.md").write_text(
            "---\nid: EP-127\nstatus: active\n---\n"
            "## Current Snapshot\n\nUNRELATED_EP_CONTENT\n",
            encoding="utf-8",
        )
        started = json.loads(
            self.run_core(
                "event",
                stdin={
                    "protocol_version": 2,
                    "event": "session_start",
                    "adapter_id": "portable",
                    "session_id": "unscoped-session",
                    "turn_id": "unscoped-turn",
                    "prompt": "Fix a small local typo",
                },
            ).stdout
        )
        self.assertNotIn("UNRELATED_EP_CONTENT", started["context"])
        self.assertEqual(
            [item["id"] for item in started["context_plan"]["selections"]],
            ["routing-contract", "routing-index"],
        )

    def test_normalized_protocol_fails_closed_on_future_version(self) -> None:
        result = self.run_core(
            "event",
            stdin={
                "protocol_version": 3,
                "event": "session_start",
                "adapter_id": "portable",
                "session_id": "session-1",
                "turn_id": "turn-1",
            },
            expected=2,
        )

        self.assertIn("ROUTER_PROTOCOL_UNSUPPORTED", result.stderr)

    def test_subagent_receives_the_same_turn_routing_contract(self) -> None:
        self.initialize_turn()
        output = self.hook(
            "SubagentStart",
            agent_id="agent-1",
            agent_type="worker",
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("$engineering-specs", context)
        self.assertIn("Session ID: `session-1`", context)
        self.assertIn("Turn ID: `turn-1`", context)
        self.assertIn("languages/go", context)

    def test_candidates_activation_injection_and_stop_handoff(self) -> None:
        self.initialize_turn()
        candidates = json.loads(
            self.run_router(
                "candidates",
                "--path",
                "service/main.go",
            ).stdout
        )
        self.assertEqual(
            [item["id"] for item in candidates["candidates"]],
            ["core/semantic-naming", "languages/go"],
        )

        activation = self.activate_go("service/main.go")
        self.assertEqual(
            [item["id"] for item in activation["activated_specs"]],
            ["core/semantic-naming", "languages/go"],
        )

        patch = "*** Begin Patch\n*** Update File: service/main.go\n@@\n-package service\n+package service\n*** End Patch"
        first = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_use_id="tool-1",
            tool_input={"command": patch},
        )
        specific = first["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn(
            "BEGIN languages/go",
            specific["additionalContext"],
        )

        second = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_use_id="tool-2",
            tool_input={"command": patch},
        )
        self.assertEqual(second, {})

        (self.repo / "service/main.go").write_text(
            "package service\n\nfunc PublicAPI() {}\n",
            encoding="utf-8",
        )
        incomplete = self.hook(
            "Stop",
            stop_hook_active=False,
            last_assistant_message="done",
        )
        self.assertEqual(incomplete["decision"], "block")
        self.assertIn("ROUTER_HANDOFF_INCOMPLETE", incomplete["reason"])

        complete = self.hook(
            "Stop",
            stop_hook_active=True,
            last_assistant_message=(
                "Activated specifications: core/semantic-naming@0.1.0, "
                "languages/go@0.1.0\n"
                "Activated requirements: none\n"
                "Verification: go test ./... passed\n"
                "Exceptions: none\n"
                "Compatibility or migration: none"
            ),
        )
        self.assertEqual(complete, {})

    def test_requirement_cards_compile_an_exact_bounded_capsule(self) -> None:
        self.initialize_turn()
        cards = json.loads(
            self.run_router(
                "requirements",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
            ).stdout
        )
        self.assertEqual(
            [item["id"] for item in cards["cards"]],
            ["GO-NAME-001", "GO-TEST-001"],
        )
        card_levels = {
            card["id"]: card["automated_enforcement"]
            for card in cards["cards"]
        }
        self.assertEqual(
            card_levels["GO-NAME-001"],
            {
                "effective": "Advisory",
                "published": "Advisory",
                "source": "declared",
            },
        )
        self.assertEqual(
            card_levels["GO-TEST-001"],
            {
                "effective": "Advisory",
                "published": "Warning",
                "source": "declared",
            },
        )
        self.assertLessEqual(cards["card_bytes"], cards["card_budget_bytes"])

        activation = json.loads(
            self.run_router(
                "activate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
                "--requirement",
                "GO-NAME-001",
                "--because",
                "GO-NAME-001=the task renames a public Go API",
            ).stdout
        )
        self.assertEqual(
            [item["id"] for item in activation["direct_requirements"]],
            ["GO-NAME-001"],
        )
        self.assertEqual(
            activation["direct_requirements"][0][
                "automated_enforcement"
            ],
            {
                "effective": "Advisory",
                "published": "Advisory",
                "source": "declared",
            },
        )
        self.assertEqual(
            [item["id"] for item in activation["resolved_requirements"]],
            ["SEM-NAME-001", "GO-NAME-001"],
        )
        self.assertEqual(
            activation["dependency_edges"],
            [{"from": "GO-NAME-001", "to": "SEM-NAME-001"}],
        )
        for item in activation["resolved_requirements"]:
            self.assertEqual(
                item["automated_enforcement"]["published"],
                "Advisory",
            )
            self.assertEqual(
                item["automated_enforcement"]["effective"],
                "Advisory",
            )
            self.assertGreater(item["block"]["bytes"], 0)
            self.assertEqual(len(item["block"]["sha256"]), 64)
            self.assertGreater(item["verification"]["bytes"], 0)
        self.assertEqual(activation["capsule"]["mode"], "requirements")
        self.assertLessEqual(
            activation["capsule"]["bytes"],
            activation["capsule"]["budget_bytes"],
        )

        patch = "*** Begin Patch\n*** Update File: service/main.go\n@@\n-package service\n+package service\n*** End Patch"
        first = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_use_id="tool-requirement",
            tool_input={"command": patch},
        )
        capsule = first["hookSpecificOutput"]["additionalContext"]
        self.assertIn("### SEM-NAME-001", capsule)
        self.assertIn("### GO-NAME-001", capsule)
        self.assertIn("| `GO-NAME-001` | Go API review |", capsule)
        self.assertNotIn("### GO-TEST-001", capsule)
        self.assertNotIn("UNRELATED-TEST-SENTINEL", capsule)
        self.assertEqual(
            hashlib.sha256(capsule.encode("utf-8")).hexdigest(),
            activation["capsule"]["sha256"],
        )

    def test_requirement_budgets_fail_without_truncation(self) -> None:
        cards = self.run_router(
            "requirements",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            "--card-budget-bytes",
            "1",
            expected=2,
        )
        self.assertIn("ROUTER_REQUIREMENT_CARDS_TOO_LARGE", cards.stderr)

        self.initialize_turn()
        capsule = self.run_router(
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            "--requirement",
            "GO-NAME-001",
            "--because",
            "GO-NAME-001=rename public API",
            "--capsule-budget-bytes",
            "100",
            expected=2,
        )
        self.assertIn("ROUTER_CONTEXT_BUDGET_EXCEEDED", capsule.stderr)
        self.assertIn("direct=GO-NAME-001", capsule.stderr)
        self.assertIn("resolved=SEM-NAME-001,GO-NAME-001", capsule.stderr)
        self.assertIn("requirement_bytes(block+verification)=", capsule.stderr)
        self.assertIn("frame_bytes=", capsule.stderr)

        missing_reason = self.run_router(
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            "--requirement",
            "GO-NAME-001",
            "--because",
            "GO-NAME-001=rename public API",
            "--capsule-budget-bytes",
            "40000",
            expected=2,
        )
        self.assertIn("ROUTER_CAPSULE_BUDGET_REASON_REQUIRED", missing_reason.stderr)

        raised = json.loads(
            self.run_router(
                "activate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
                "--requirement",
                "GO-NAME-001",
                "--because",
                "GO-NAME-001=rename public API",
                "--capsule-budget-bytes",
                "40000",
                "--capsule-budget-reason",
                "reviewed broad API migration",
            ).stdout
        )
        self.assertEqual(
            raised["capsule"]["budget_override_reason"],
            "reviewed broad API migration",
        )

    def test_requirement_index_metadata_drift_fails_closed(self) -> None:
        index_path = (
            self.repo / "docs/agent-guides/managed/requirements.json"
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        go_spec = next(
            item for item in index["specs"] if item["id"] == "languages/go"
        )
        go_spec["requirements"][0]["activation"] = (
            "Load when a tampered cache says so."
        )
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = self.run_router(
            "requirements",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            expected=2,
        )
        self.assertIn("ROUTER_REQUIREMENT_INDEX_METADATA_DRIFT", result.stderr)

    def test_enforcement_metadata_drift_fails_closed(self) -> None:
        index_path = (
            self.repo / "docs/agent-guides/managed/requirements.json"
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        go_spec = next(
            item for item in index["specs"] if item["id"] == "languages/go"
        )
        go_spec["requirements"][0]["automated_enforcement"] = "Warning"
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = self.run_router(
            "requirements",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            expected=2,
        )
        self.assertIn("ROUTER_REQUIREMENT_INDEX_METADATA_DRIFT", result.stderr)
        self.assertIn("Automated enforcement", result.stderr)

    def test_schema_v1_requirement_index_remains_readable(self) -> None:
        index_path = (
            self.repo / "docs/agent-guides/managed/requirements.json"
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["schema_version"] = 1
        for spec in index["specs"]:
            for requirement in spec["requirements"]:
                requirement.pop("automated_enforcement")
                requirement.pop("automated_enforcement_source")
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        cards = json.loads(
            self.run_router(
                "requirements",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
            ).stdout
        )
        self.assertEqual(
            cards["cards"][0]["automated_enforcement"],
            {
                "effective": "Advisory",
                "published": "Advisory",
                "source": "declared",
            },
        )

    def test_evidence_export_is_verified_advisory_activation_context(
        self,
    ) -> None:
        self.initialize_turn()
        self.run_router(
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            "--requirement",
            "GO-TEST-001",
            "--because",
            "GO-TEST-001=review focused test evidence",
        )
        arguments = (
            "evidence",
            "--adapter-id",
            "codex",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
        )
        first = json.loads(self.run_router(*arguments).stdout)
        second = json.loads(self.run_router(*arguments).stdout)

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 1)
        self.assertEqual(
            first["evidence_type"],
            "repo-foundry/requirement-activation",
        )
        self.assertFalse(first["finding_lifecycle"]["supported"])
        self.assertEqual(
            first["finding_lifecycle"]["maximum_effective_level"],
            "Advisory",
        )
        self.assertEqual(
            [item["id"] for item in first["requirements"]],
            ["GO-TEST-001"],
        )
        for requirement in first["requirements"]:
            self.assertEqual(
                requirement["automated_enforcement"]["published"],
                "Warning",
            )
            self.assertEqual(
                requirement["automated_enforcement"]["effective"],
                "Advisory",
            )
            self.assertEqual(
                len(requirement["requirement_block_sha256"]),
                64,
            )
        serialized = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("Go changes **MUST**", serialized)
        digest = first.pop("sha256")
        canonical = json.dumps(
            first,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)

    def test_legacy_protocol_v2_receipt_rehydrates_without_level_fields(
        self,
    ) -> None:
        self.initialize_turn()
        self.run_router(
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--path",
            "service/main.go",
            "--spec",
            "languages/go",
            "--requirement",
            "GO-NAME-001",
            "--because",
            "GO-NAME-001=rename public API",
        )
        state_paths = list(
            (
                self.repo
                / ".git"
                / "repo-foundry"
                / "spec-activation-v2"
            ).glob("*.json")
        )
        self.assertEqual(len(state_paths), 1)
        runtime = json.loads(state_paths[0].read_text(encoding="utf-8"))
        runtime["version"] = 3
        for item in runtime["activation"]["direct_requirements"]:
            item.pop("automated_enforcement")
        for item in runtime["activation"]["resolved_requirements"]:
            item.pop("automated_enforcement")
        state_paths[0].write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        rehydrated = json.loads(
            self.run_router(
                "rehydrate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        self.assertEqual(rehydrated["decision"], "allow")
        self.assertIn("### GO-NAME-001", rehydrated["context"])

    def test_rehydrate_starts_a_new_epoch_with_the_same_capsule(self) -> None:
        self.initialize_turn()
        activation = json.loads(
            self.run_router(
                "activate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
                "--requirement",
                "GO-NAME-001",
                "--because",
                "GO-NAME-001=rename public API",
            ).stdout
        )
        rehydrated = json.loads(
            self.run_router(
                "rehydrate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        marker = "# Engineering Specification Context Capsule"
        self.assertIn(marker, rehydrated["context"])
        capsule = rehydrated["context"][rehydrated["context"].index(marker) :]
        self.assertEqual(
            hashlib.sha256(capsule.encode("utf-8")).hexdigest(),
            activation["capsule"]["sha256"],
        )
        status = json.loads(
            self.run_router(
                "status",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
            ).stdout
        )
        self.assertEqual(status["context_epoch"], 2)
        self.assertEqual(status["context_injected_epoch"], 2)

    def test_uncovered_path_is_denied_until_activation_expands(self) -> None:
        self.initialize_turn()
        self.activate_go("service/main.go")
        patch = "*** Begin Patch\n*** Add File: service/other.go\n+package service\n*** End Patch"
        output = self.hook(
            "PreToolUse",
            tool_name="apply_patch",
            tool_use_id="tool-3",
            tool_input={"command": patch},
        )
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("service/other.go", specific["permissionDecisionReason"])

    def test_explicit_none_requires_reason_and_still_unlocks_declared_path(self) -> None:
        self.initialize_turn()
        missing_reason = self.run_router(
            "activate",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--path",
            "README.md",
            "--none",
            expected=2,
        )
        self.assertIn("ROUTER_NONE_REASON_REQUIRED", missing_reason.stderr)

        activation = json.loads(
            self.run_router(
                "activate",
                "--session-id",
                "session-1",
                "--turn-id",
                "turn-1",
                "--path",
                "README.md",
                "--none",
                "--reason",
                "Editorial wording does not change an engineering contract",
            ).stdout
        )
        self.assertEqual(activation["decision"], "none")
        self.assertEqual(activation["activated_specs"], [])

    def test_unbounded_scope_and_mutating_inspection_commands_are_denied(self) -> None:
        self.initialize_turn()
        broad = self.run_router(
            "candidates",
            "--path",
            "**/*",
            expected=2,
        )
        self.assertIn("ROUTER_PLANNED_PATH_TOO_BROAD", broad.stderr)

        safe = self.hook(
            "PreToolUse",
            tool_name="Bash",
            tool_use_id="tool-safe",
            tool_input={"command": "git status --short"},
        )
        self.assertEqual(safe, {})

        evidence = self.hook(
            "PreToolUse",
            tool_name="Bash",
            tool_use_id="tool-evidence",
            tool_input={
                "command": (
                    "python3 .repo-foundry/engineering-specs/"
                    "spec_router.py evidence --adapter-id codex "
                    "--session-id session-1 --turn-id turn-1"
                )
            },
        )
        self.assertEqual(evidence, {})

        mutating = self.hook(
            "PreToolUse",
            tool_name="Bash",
            tool_use_id="tool-mutating",
            tool_input={"command": "git branch bypass"},
        )
        self.assertEqual(
            mutating["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_manual_begin_activation_and_handoff_audit_work_without_hooks(self) -> None:
        begin = json.loads(
            self.run_router(
                "begin",
                "--session-id",
                "manual-session",
                "--turn-id",
                "manual-turn",
                "--prompt",
                "Review the Go handler name",
            ).stdout
        )
        self.assertTrue(begin["initialized"])
        activation = json.loads(
            self.run_router(
                "activate",
                "--session-id",
                "manual-session",
                "--turn-id",
                "manual-turn",
                "--path",
                "service/main.go",
                "--spec",
                "languages/go",
            ).stdout
        )
        self.assertEqual(activation["decision"], "activated")

        (self.repo / "service/main.go").write_text(
            "package service\n\nfunc ManualReview() {}\n",
            encoding="utf-8",
        )
        handoff = (
            "Activated specifications: languages/go@0.1.0\n"
            "Activated requirements: none\n"
            "Verification: focused review passed\n"
            "Exceptions: none\n"
            "Compatibility or migration: none"
        )
        audit = json.loads(
            self.run_router(
                "audit",
                "--session-id",
                "manual-session",
                "--turn-id",
                "manual-turn",
                "--message",
                handoff,
            ).stdout
        )
        self.assertTrue(audit["ok"])

    def test_recursive_glob_preflight_covers_zero_and_nested_directories(self) -> None:
        self.initialize_turn()
        self.activate_go("service/**/*.go")
        self.run_core(
            "rehydrate", "--adapter-id", "codex",
            "--session-id", "session-1", "--turn-id", "turn-1",
        )
        result = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service/main.go",
                "--path", "service/nested/new.go",
            ).stdout
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["uncovered_paths"], [])
        self.assertTrue(result["capsule_delivered_in_current_epoch"])
        self.assertEqual(result["changed_since_begin"], [])
        write_gate = self.hook(
            "PreToolUse", tool_name="apply_patch",
            tool_input={
                "command": (
                    "*** Begin Patch\\n"
                    "*** Update File: service/main.go\\n"
                    "@@\\n"
                    " package service\\n"
                    "*** End Patch"
                )
            },
        )
        self.assertEqual(write_gate, {})
        uncovered = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service2/main.go", expected=1,
            ).stdout
        )
        self.assertIn("service2/main.go", uncovered["uncovered_paths"])
        invalid = self.run_core(
            "preflight", "--adapter-id", "codex",
            "--session-id", "session-1", "--turn-id", "turn-1",
            "--path", "service/**/*.go", expected=2,
        )
        self.assertIn("ROUTER_PREFLIGHT_EXACT_PATH_REQUIRED", invalid.stderr)

    def test_preflight_detects_missing_requirement_even_after_capsule_delivery(self) -> None:
        self.initialize_turn()
        self.run_core(
            "activate", "--adapter-id", "codex",
            "--session-id", "session-1", "--turn-id", "turn-1",
            "--path", "service/main.go", "--spec", "languages/go",
            "--requirement", "GO-TEST-001",
            "--because", "GO-TEST-001=Focused regression for this change",
        )
        self.run_core(
            "rehydrate", "--adapter-id", "codex",
            "--session-id", "session-1", "--turn-id", "turn-1",
        )
        missing = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service/main.go",
                "--expect-requirement", "GO-NAME-001",
                expected=1,
            ).stdout
        )
        self.assertEqual(missing["missing_requirements"], ["GO-NAME-001"])
        passed = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service/main.go",
                "--expect-requirement", "GO-TEST-001",
            ).stdout
        )
        self.assertTrue(passed["ok"])

    def test_preflight_cannot_retroactively_certify_post_edit_activation(self) -> None:
        self.initialize_turn()
        self.activate_go("service/**/*.go")
        not_yet_delivered = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service/main.go", expected=1,
            ).stdout
        )
        self.assertIn(
            "ROUTER_PREFLIGHT_CONTEXT_NOT_DELIVERED",
            not_yet_delivered["errors"],
        )
        self.run_core(
            "rehydrate", "--adapter-id", "codex",
            "--session-id", "session-1", "--turn-id", "turn-1",
        )
        (self.repo / "service/main.go").write_text(
            "package service\nfunc Fixed() {}\n", encoding="utf-8"
        )
        late = json.loads(
            self.run_core(
                "preflight", "--adapter-id", "codex",
                "--session-id", "session-1", "--turn-id", "turn-1",
                "--path", "service/main.go", expected=1,
            ).stdout
        )
        self.assertIn("service/main.go", late["changed_since_begin"])
        self.assertTrue(any(
            error.startswith("ROUTER_PREFLIGHT_AFTER_EDIT")
            for error in late["errors"]
        ))

    def test_custom_hooks_are_preserved_and_report_manual_merge(self) -> None:
        custom = self.repo / ".codex/hooks.json"
        original = '{"hooks":{"Stop":[]},"description":"custom"}\n'
        custom.write_text(original, encoding="utf-8")

        preview = json.loads(
            self.run_foundry(
                "bootstrap",
                "--profile",
                "codex",
                expected=0,
            ).stdout
        )
        conflicts = [
            item
            for item in preview["actions"]
            if item["action"] == "conflict"
            and item["path"] == ".codex/hooks.json"
        ]
        self.assertEqual(len(conflicts), 1)
        self.assertIn("preserve existing Hooks", conflicts[0]["reason"])
        self.assertEqual(custom.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
