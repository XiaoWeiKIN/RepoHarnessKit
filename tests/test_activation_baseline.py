"""PR-A measurement contracts; fixture integration is plumbing, not gold truth."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tests.spec_git_fixture import create_git_catalog, git

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals/spec-activation"
SPEC = importlib.util.spec_from_file_location("activation_baseline", EVAL / "baseline.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.labels = {"applicable": {"A": "required", "B": "required"},
                       "context_only": ["C"], "uncertain": {"D": "unknown"},
                       "not_applicable": ["E"], "unreviewed": ["F"]}

    def test_recall_precision_have_distinct_denominators(self):
        result = BASELINE.score({"A", "C", "D", "E", "F"}, self.labels)
        self.assertEqual((result["recall"], result["precision"]), (0.5, 0.5))
        self.assertEqual(result["fn"], ["B"])
        self.assertEqual(result["excluded_retrieved"], {
            "context_only": ["C"], "uncertain": ["D"], "unreviewed": ["F"]})

    def test_empty_none_denominators_are_null_not_success(self):
        labels = {"applicable": {}, "context_only": [], "uncertain": {},
                  "not_applicable": ["A"], "unreviewed": []}
        result = BASELINE.score(set(), labels)
        self.assertIsNone(result["recall"])
        self.assertIsNone(result["precision"])
        self.assertEqual(BASELINE.score({"A"}, labels)["precision"], 0)

    def test_micro_scores_count_case_requirement_pairs_once(self):
        rows = [{"metrics": BASELINE.score({"A", "E"}, self.labels)},
                {"metrics": BASELINE.score({"A", "B"}, self.labels)}]
        result = BASELINE.aggregate(rows)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (3, 1, 1))
        self.assertEqual(result["recall"], 0.75)
        self.assertEqual(result["precision"], 0.75)

    def test_excluded_context_is_not_a_false_positive(self):
        result = BASELINE.score({"A", "B", "C", "D", "F"}, self.labels)
        self.assertEqual(result["precision"], 1)
        self.assertEqual(result["retrieved"], 5)
        self.assertEqual(result["expected_positive"], 2)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.corpus = json.loads((EVAL / "corpus.json").read_text())

    def test_all_provisional_labels_partition_the_pinned_universe(self):
        BASELINE.validate_corpus(self.corpus)
        self.assertEqual(len(self.corpus["cases"]), 12)
        self.assertEqual(len(self.corpus["requirements"]), 56)

    def test_duplicate_case_rejected(self):
        self.corpus["cases"].append(copy.deepcopy(self.corpus["cases"][0]))
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_corpus(self.corpus)

    def test_conflicting_label_rejected(self):
        c = self.corpus["cases"][0]
        c["labels"]["not_applicable"].append(next(iter(c["labels"]["applicable"])))
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_corpus(self.corpus)

    def test_omitted_label_is_not_silent_negative(self):
        self.corpus["cases"][0]["labels"]["not_applicable"].pop()
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_corpus(self.corpus)

    def test_source_snapshot_hash_is_enforced(self):
        c = self.corpus["cases"][0]
        next(iter(c["snapshots"].values()))["before"] += "// changed\n"
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_corpus(self.corpus)

    def test_cases_cannot_overwrite_normative_state(self):
        c = self.corpus["cases"][0]
        c["snapshots"]["docs/.engineering/specs.lock.json"] = next(iter(c["snapshots"].values()))
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.validate_corpus(self.corpus)

    def test_unresolved_aggregate_claims_are_not_gold_rows(self):
        history = json.loads((EVAL / "history.json").read_text())
        self.assertEqual([r["reported_count"] for r in history["unresolved_claims"]], [17, 7])
        self.assertTrue(all(r["requirement_ids"] is None and not r["denominator_eligible"]
                            for r in history["unresolved_claims"]))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.json_bytes(b'{"x":1,"x":2}')

    def test_unsafe_and_noncanonical_paths_rejected(self):
        for value in ("../file", "/tmp/file", ".git/config", "a/../b", "a//b", "x\\y"):
            with self.subTest(value=value), self.assertRaises(BASELINE.BaselineError):
                BASELINE.relative(value)

    def test_mutating_router_commands_rejected_before_subprocess(self):
        with patch.object(BASELINE.subprocess, "run") as run:
            for op in ("begin", "activate", "rehydrate", "event", "classify"):
                with self.subTest(operation=op), self.assertRaises(BASELINE.BaselineError):
                    BASELINE.invoke(Path("router"), Path("project"), op, [], io.StringIO())
            run.assert_not_called()

    def test_wrong_router_pin_rejected(self):
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.load_router(ROOT / "assets/core/engineering-specs/spec_router.py", "0" * 64)

    def test_fixture_path_traversal_and_links_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name, link in (("project/../../escape", False), ("project/link", True)):
                tar = home / "case.tar.gz"
                with tarfile.open(tar, "w:gz") as out:
                    info = tarfile.TarInfo(name)
                    if link:
                        info.type = tarfile.SYMTYPE
                        info.linkname = "/tmp"
                        out.addfile(info)
                    else:
                        info.size = 1
                        out.addfile(info, io.BytesIO(b"x"))
                with self.subTest(name=name), self.assertRaises(BASELINE.BaselineError):
                    BASELINE.extract_fixture(tar, sha(tar), home / "output")


class RouterIntegrationTests(unittest.TestCase):
    """Use the unmodified real Router with existing synthetic Catalog plumbing."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        catalog, _ = create_git_catalog(self.home)
        project = self.home / "project"
        project.mkdir()
        git(project, "init", "-b", "main")
        (project / "go.mod").write_text("module example.test/baseline\n")
        git(project, "add", ".")
        git(project, "-c", "user.name=Baseline", "-c", "user.email=baseline@example.invalid",
            "commit", "-m", "fixture")
        run = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/foundryctl.py"),
            "--repo", str(project), "bootstrap", "--adapter", "portable", "--required-only",
            "--spec-repository", catalog.as_uri(), "--spec-version", "0.1.0", "--apply"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.fixture = self.home / "fixture.tar.gz"
        with tarfile.open(self.fixture, "w:gz") as out:
            for path in sorted(project.rglob("*")):
                if path.is_file() and ".git" not in path.relative_to(project).parts:
                    out.add(path, arcname="project/" + path.relative_to(project).as_posix())
        self.router = ROOT / "assets/core/engineering-specs/spec_router.py"
        lock = json.loads((project / "docs/.engineering/specs.lock.json").read_text())
        index = json.loads((project / "docs/agent-guides/managed/requirements.json").read_text())
        requirements = {r["id"]: {"spec": s["id"], "source_path": next(
            v["source_path"] for v in lock["specs"] if v["id"] == s["id"]),
            "start_byte": r["start_byte"], "end_byte": r["end_byte"], "sha256": r["sha256"]}
            for s in index["specs"] for r in s["requirements"]}
        self.corpus = {"schema_version": 1, "pins": {
            "router_revision": "test-fixture", "router_sha256": sha(self.router),
            "fixture_sha256": sha(self.fixture),
            "lock_sha256": sha(project / "docs/.engineering/specs.lock.json"),
            "manifest_sha256": sha(project / "docs/.engineering/specs.json"),
            "index_sha256": sha(project / "docs/agent-guides/managed/requirements.json"),
            "catalog_revision": lock["catalog"]["resolved_revision"],
            "catalog_version": lock["catalog"]["catalog_version"],
            "catalog_sha256": lock["catalog"]["sha256"]}, "requirements": requirements,
            "cases": [{"id": "plumbing", "origin": "synthetic_test_only", "task": "Review names",
                "planned_paths": ["service/main.go"], "actual_paths": ["service/main.go"],
                "snapshots": {}, "labels": {"applicable": {k: "plumbing" for k in requirements},
                    "context_only": [], "uncertain": {}, "not_applicable": [], "unreviewed": []},
                "review": {"status": "synthetic_plumbing"}, "exclusion_basis": "not semantic gold"}]}

    def test_actual_router_readonly_repeat_and_separate_activation(self):
        result = BASELINE.measure(self.corpus, self.fixture, self.router, self.home / "run")
        self.assertTrue(result["read_only"])
        self.assertIsNone(result["activation_metrics"]["recall"])
        self.assertEqual(result["cases"][0]["identical_repeats"], 2)
        self.assertTrue(result["cases"][0]["input_unchanged"])
        self.assertEqual(sha(self.fixture), self.corpus["pins"]["fixture_sha256"])
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.measure(self.corpus, self.fixture, self.router, self.home / "run")

    def test_input_drift_prevents_complete_result(self):
        output = self.home / "drift"
        frozen = self.home / "frozen"
        frozen.write_bytes(b"new")
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.measure(self.corpus, self.fixture, self.router, output,
                             frozen_inputs={frozen: b"old"})
        self.assertFalse((output / "observations.json").exists())
        self.assertTrue((output / "commands.jsonl").exists())

    def test_wrong_fixture_pin_fails_without_success_artifact(self):
        self.corpus["pins"]["fixture_sha256"] = "0" * 64
        output = self.home / "bad-pin"
        with self.assertRaises(BASELINE.BaselineError):
            BASELINE.measure(self.corpus, self.fixture, self.router, output)
        self.assertFalse((output / "observations.json").exists())


if __name__ == "__main__":
    unittest.main()
