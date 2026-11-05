"""Regression checks for packaged authoring guidance, not prose conformance.

The eval JSON contains model-review scenarios. These tests validate coverage and
routing; they do not run a model or certify readability or accessibility.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = Path("references/controlled-writing.md")
SKILLS = (
    "design-documentation", "engineering-benchmark", "engineering-research",
    "governed-design", "engineering-execution-plan", "engineering-case-study",
)
SHARED_SECTIONS = (
    "Editorial basis and precedence", "Language and fidelity", "Common guidance",
    "Reader and structure", "Procedures and examples", "Accessible explanations",
    "Documentation maintenance", "Source references", "Distribution maintenance",
)


def compact(text: str) -> str:
    return " ".join(text.split())


class DocumentationGuidanceTests(unittest.TestCase):
    def test_every_packaged_copy_carries_the_same_editorial_sections(self) -> None:
        source = (ROOT / GUIDE).read_bytes()
        for skill in SKILLS:
            with self.subTest(skill=skill):
                packaged = (ROOT / skill / GUIDE).read_bytes()
                self.assertEqual(packaged, source)
                headings = re.findall(r"^## (.+)$", packaged.decode("utf-8"), re.M)
                self.assertTrue(set(SHARED_SECTIONS).issubset(headings))
                self.assertEqual(len(headings), len(set(headings)))
                self.assertLess(headings.index("Documentation maintenance"), headings.index("ADR"))

    def test_project_contracts_remain_above_editorial_defaults(self) -> None:
        text = compact((ROOT / GUIDE).read_text(encoding="utf-8"))
        for boundary in (
            "Follow project-specific writing and language conventions before this guide's editorial defaults.",
            "Style never overrides meaning.",
            "This guide adds no approval step or lifecycle gate.",
            "not a Catalog Specification", "claim full ASD-STE100 conformance",
            "Do not create a separate Google-writing policy",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_language_requirement_strength_and_history_are_protected(self) -> None:
        text = compact((ROOT / GUIDE).read_text(encoding="utf-8"))
        for boundary in (
            "Keep the user's requested language",
            "English sentence case and word-count advice do not become Chinese writing rules.",
            "Do not replace normative `MUST`, `SHOULD`, or `MAY`",
            "Changing tense does not implement a proposal.",
            "do not enforce an arbitrary word limit or produce fragments",
            "Do not rewrite accepted ADRs, approved snapshots, sealed Checkpoints",
            "does not authorize deleting or rewriting accepted ADRs",
            "Report untested examples instead of claiming success.",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_google_references_are_attributed_optional_and_self_contained(self) -> None:
        text = (ROOT / GUIDE).read_text(encoding="utf-8")
        normalized = compact(text)
        for phrase in (
            "RF's selective paraphrase and adaptation",
            "optional maintainer references, not runtime dependencies",
            "Use the packaged guidance offline",
            "Google Developers prose is licensed under CC BY 4.0",
        ):
            self.assertIn(phrase, normalized)
        # No imported local policy or remote Markdown include is required to read
        # a separately installed guide. Bare URLs are optional source attribution.
        self.assertEqual(re.findall(r"\]\(([^)]+)\)", text), [])
        for url in (
            "https://developers.google.com/style",
            "https://developers.google.com/tech-writing/one/audience",
            "https://developers.google.com/tech-writing/one/documents",
            "https://developers.google.com/style/procedures",
            "https://developers.google.com/style/accessibility",
            "https://google.github.io/styleguide/docguide/best_practices.html",
            "https://creativecommons.org/licenses/by/4.0/",
            "https://www.asd-ste100.org/",
        ):
            self.assertIn(url, text)

    def test_detailed_design_routes_shared_rules_and_final_reader_review(self) -> None:
        skill = (ROOT / "design-documentation/SKILL.md").read_text(encoding="utf-8")
        route = "[受控技术写作](references/controlled-writing.md)"
        self.assertEqual(skill.count(route), 1)
        self.assertLess(skill.index(route), skill.index("\n## "))
        self.assertIn("已有知识", skill)
        self.assertIn("读完后需要理解或完成的任务", skill)
        self.assertIn("写作、修订和评审交付前都读取 [review.md](references/review.md)", skill)
        for filename in ("architecture.md", "review.md"):
            path = ROOT / "design-documentation/references" / filename
            with self.subTest(filename=filename):
                text = path.read_text(encoding="utf-8")
                self.assertIn("[controlled technical writing](controlled-writing.md)", text)
                self.assertTrue((path.parent / "controlled-writing.md").is_file())
                self.assertNotIn("https://developers.google.com", text)
        review = (ROOT / "design-documentation/references/review.md").read_text(encoding="utf-8")
        self.assertIn("findings, not file modifications", review)
        self.assertIn("Separate editorial suggestions from factual or design defects.", review)

    def test_eval_catalog_preserves_scenarios_for_risky_editorial_changes(self) -> None:
        catalog = json.loads((ROOT / "design-documentation/evals/evals.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["skill_name"], "design-documentation")
        ids = [item["id"] for item in catalog["evals"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(range(1, 10)).issubset(ids))
        scenarios = {item["id"]: item for item in catalog["evals"]}
        expected = {
            6: {"reader-task-and-prior-knowledge", "progressive-causal-explanation", "no-invented-evidence"},
            7: {"purpose-before-command", "no-fabricated-procedure", "review-only-authority"},
            8: {"equivalent-text-and-keyboard", "audio-video-alternative", "honest-accessibility-review"},
            9: {"project-contract-before-style", "language-and-state-fidelity", "historical-owner-boundary"},
        }
        for identifier, names in expected.items():
            with self.subTest(identifier=identifier):
                item = scenarios[identifier]
                self.assertTrue(item["prompt"].strip())
                self.assertTrue(item["expected_output"].strip())
                self.assertEqual(item["files"], [])  # The new prompts are self-contained.
                actual = [a["name"] for a in item["assertions"]]
                self.assertEqual(len(actual), len(set(actual)))
                self.assertTrue(names.issubset(actual))
                self.assertTrue(all(a["description"].strip() for a in item["assertions"]))


if __name__ == "__main__":
    unittest.main()
