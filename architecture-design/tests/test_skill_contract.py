"""Static routing/package regressions for the architecture design skill.

This does not pretend to execute or grade an agent's architecture reasoning;
behavioral cases remain in ../evals/evals.json.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent


class ArchitectureDesignContractTests(unittest.TestCase):
    def test_skill_is_independent_and_modeful(self) -> None:
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(content, r"(?m)^name: architecture-design$")
        self.assertIn("Design", content)
        self.assertIn("Review", content)
        self.assertIn("默认只读", content)
        self.assertIn("detailed-design", content)
        self.assertIn("engineering-design", content)
        self.assertIn("engineering-execution-plan", content)
        self.assertIn("observed", content)
        self.assertIn("unknown", content)

    def test_references_are_real_and_distinct_from_docs(self) -> None:
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for name in ("complexity.md", "change-scenarios.md", "review.md"):
            path = SKILL / "references" / name
            self.assertTrue(path.is_file(), path)
            self.assertIn(f"references/{name}", content)
        self.assertTrue((SKILL / "examples" / "apm-sampling.md").is_file())
        self.assertIn("examples/apm-sampling.md", content)

    def test_eval_coverage_is_explicit(self) -> None:
        catalog = json.loads((SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["skill_name"], "architecture-design")
        self.assertEqual([case["id"] for case in catalog["evals"]], list(range(1, 9)))
        self.assertTrue(all(case["assertions"] for case in catalog["evals"]))
        prompts = " ".join(case["prompt"] for case in catalog["evals"])
        for concern in ("Agent", "DD-", "Architecture.md", "插件", "生产"):
            self.assertIn(concern, prompts)

    def test_discovery_and_source_checks_route_the_skill(self) -> None:
        root_router = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        checker = (ROOT / "scripts" / "check.py").read_text(encoding="utf-8")
        self.assertIn("architecture-design", root_router)
        self.assertIn('"architecture-design"', checker)
        for readme in ("README.md", "README.zh-CN.md"):
            self.assertIn("architecture-design/SKILL.md", (ROOT / readme).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
