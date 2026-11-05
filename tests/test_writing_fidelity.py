"""Static distribution/eval checks; does not run a model or certify its prose."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = Path("references/controlled-writing.md")
SKILLS = ("design-documentation", "engineering-benchmark", "engineering-research",
          "governed-design", "engineering-execution-plan", "engineering-case-study")
SECTIONS = ("Preserve meaning while editing", "Precise Chinese technical prose",
            "Optional source-bound prose hints", "Report writing verification")
EXPECTED_ASSERTIONS = {
    10: {"branch-preservation", "no-shortening-loss", "polish-scope"},
    11: {"term-over-linter", "no-registry-mutation"},
    12: {"modal-fidelity", "protected-bytes", "no-action-authority"},
    13: {"execution-evidence", "no-invented-counts"},
    14: {"critical-conditions-inline", "no-invented-recovery", "handoff-separation"},
    15: {"no-causal-quality-claim", "prospective-protocol", "not-yet-run"},
}


class WritingFidelityTests(unittest.TestCase):
    def test_review_sections_reach_every_independent_skill(self):
        source = (ROOT / GUIDE).read_bytes()
        for skill in SKILLS:
            with self.subTest(skill=skill):
                text = (ROOT / skill / GUIDE).read_text(encoding="utf-8")
                self.assertEqual(text.encode(), source)
                for heading in SECTIONS:
                    self.assertEqual(text.count("## " + heading + "\n"), 1)
                    self.assertLess(text.index("## " + heading), text.index("## Documentation maintenance"))
                self.assertEqual(re.findall(r"\]\(([^)]+)\)", text), [])

    def test_native_extension_uses_rf_source_model(self):
        text = " ".join((ROOT / GUIDE).read_text(encoding="utf-8").split())
        for phrase in (
            "project terminology before editorial preferences",
            "same actor owns each action",
            "A keyword scan cannot establish equivalence",
            "do not make prose findings a merge gate",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_fidelity_and_editorial_scope_are_distinct(self):
        text = " ".join((ROOT / GUIDE).read_text(encoding="utf-8").split())
        for phrase in (
            "Polishing may change wording and organization but not the factual model",
            "Review-only work returns findings instead of editing the artifact",
            "Keep negation, quantities, units, uncertainty, and normative strength unchanged",
            "Keep proposal, authorization, implementation, verification, and historical status distinct",
            "zero candidates do not prove semantic fidelity",
            "Reading the script is not execution",
        ):
            self.assertIn(phrase, text)

    def test_checker_is_optional_nonblocking_and_has_no_model_verdict(self):
        text = " ".join((ROOT / GUIDE).read_text(encoding="utf-8").split())
        for phrase in (
            "Skills do not require the script",
            "Findings return exit status 0",
            "Tool errors must not be described as a clean scan",
            "There is no autofix, recursive scan, compliance score, or blocking style mode",
            "same-session reconstructions are demonstrations",
        ):
            self.assertIn(phrase, text)

    def test_checker_imports_no_execution_or_network_client(self):
        tree = ast.parse((ROOT / "scripts/check_writing.py").read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or "").split(".")[0])
        self.assertLessEqual(imports, {"__future__", "argparse", "hashlib", "json", "pathlib",
                                       "re", "stat", "sys", "typing"})

    def test_self_contained_eval_catalog_extends_existing_cases(self):
        catalog = json.loads((ROOT / "design-documentation/evals/evals.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["skill_name"], "design-documentation")
        cases = catalog["evals"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(range(1, 16)).issubset(ids))
        by_id = {case["id"]: case for case in cases}
        for identifier, names in EXPECTED_ASSERTIONS.items():
            with self.subTest(identifier=identifier):
                case = by_id[identifier]
                self.assertEqual(case["files"], [])
                self.assertTrue(case["prompt"].strip())
                self.assertTrue(case["expected_output"].strip())
                self.assertEqual({a["name"] for a in case["assertions"]}, names)
                self.assertTrue(all(a["description"].strip() for a in case["assertions"]))
                self.assertNotIn("score", case)
                self.assertNotIn("result", case)


if __name__ == "__main__":
    unittest.main()
