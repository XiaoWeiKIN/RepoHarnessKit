#!/usr/bin/env python3
"""Read-only candidate baseline; never an activation or compliance verdict.

The only Router CLI operations are candidates and requirements. Fixture setup
writes a disposable copy, not the input archive, checkout or installed project.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import types
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAX_JSON = 2 * 1024 * 1024
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
STATES = ("applicable", "context_only", "uncertain", "not_applicable", "unreviewed")
ROUTER_OPERATIONS = frozenset({"candidates", "requirements"})
# Schema 1 has one historical experiment. This is its role-bound archive entry,
# not a caller-selected member of the source registry.
HISTORICAL_CASE_ID = "historical-task3"
HISTORICAL_DIFF_PATH = "frozen/final.diff"
HISTORICAL_DIFF_SOURCE = "compliance-archive:" + HISTORICAL_DIFF_PATH


class BaselineError(ValueError):
    """Invalid input or measurement; not evidence of a Router semantic defect."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def read_bytes(path: Path, maximum: int = MAX_JSON) -> bytes:
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise BaselineError(f"Expected a regular non-symlink file: {path}")
    if path.stat().st_size > maximum:
        raise BaselineError(f"Input too large: {path}")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise BaselineError(f"Input grew beyond limit: {path}")
    return data


def json_bytes(data: bytes) -> object:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BaselineError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              BaselineError(f"Non-finite JSON: {value}")))
    except (ValueError, UnicodeError) as exc:
        raise BaselineError(f"Invalid UTF-8 JSON: {exc}") from exc


def relative(value: str, *, glob: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("-"):
        raise BaselineError("Invalid relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or ".git" in p.parts or str(p) != value:
        raise BaselineError(f"Unsafe path: {value}")
    if any(ord(c) < 32 for c in value) or (not glob and any(c in value for c in "*?[")):
        raise BaselineError(f"Invalid path: {value}")
    return value


def final_diff_reference(case: dict) -> dict:
    """Validate the fixed historical diff role, not just an arbitrary locator."""
    ref = case.get("final_diff")
    if (not isinstance(ref, dict) or set(ref) != {"source", "sha256"}
            or ref["source"] != HISTORICAL_DIFF_SOURCE
            or not isinstance(ref["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) is None):
        raise BaselineError("Invalid historical final_diff reference")
    return ref


def bind_final_diff(history: dict, case: dict) -> dict:
    """Cross-check the case declaration against the frozen history registry.

    This proves metadata consistency only. verify_history must still read and
    hash the original archive entry before claiming historical revalidation.
    """
    ref = final_diff_reference(case)
    sources = history["recovered_experiment"]["sources"]
    matches = [row for row in sources if row["path"] == HISTORICAL_DIFF_PATH]
    if len(matches) != 1 or matches[0]["sha256"] != ref["sha256"]:
        raise BaselineError("Historical final_diff registry binding mismatch")
    return ref


def validate_corpus(data: dict) -> None:
    if not isinstance(data, dict):
        raise BaselineError("Corpus must be an object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise BaselineError("Unsupported corpus schema")
    if not isinstance(data["requirements"], dict) or not isinstance(data["cases"], list):
        raise BaselineError("Invalid requirement map or case list")
    for name, ref in data["requirements"].items():
        if not isinstance(ref, dict) or "source_path" not in ref:
            raise BaselineError(f"Missing Requirement source_path: {name}")
        relative(ref["source_path"])
    universe = set(data["requirements"])
    if not universe or not data["cases"]:
        raise BaselineError("Empty corpus")
    seen = set()
    for case in data["cases"]:
        name = case["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) or name in seen:
            raise BaselineError("Invalid or duplicate case ID")
        seen.add(name)
        if (name == HISTORICAL_CASE_ID or case.get("origin") == "source_audit_20261101"
                or "final_diff" in case):
            if name != HISTORICAL_CASE_ID:
                raise BaselineError("Unsupported historical case identity")
            final_diff_reference(case)
        if not case["task"].strip() or not case["planned_paths"] or not case["actual_paths"]:
            raise BaselineError(f"Incomplete task: {name}")
        for p in case["planned_paths"]:
            relative(p, glob=True)
        for p in case["actual_paths"]:
            relative(p)
        labels = case["labels"]
        if set(labels) != set(STATES):
            raise BaselineError(f"Missing label state: {name}")
        covered = set()
        for state in STATES:
            if not isinstance(labels[state], (dict, list)):
                raise BaselineError(f"Invalid label collection: {name}")
            values = list(labels[state])
            if len(values) != len(set(values)) or covered.intersection(values):
                raise BaselineError(f"Duplicate label: {name}")
            covered.update(values)
        if covered != universe:
            raise BaselineError(f"Labels must partition the pinned universe: {name}")
        for state in ("applicable", "uncertain"):
            if not isinstance(labels[state], dict) or any(
                not isinstance(reason, str) or not reason.strip()
                for reason in labels[state].values()
            ):
                raise BaselineError(f"Missing rationale: {name}")
        if not case["review"]["status"] or not case["exclusion_basis"]:
            raise BaselineError(f"Missing review provenance: {name}")
        for p, snapshot in case["snapshots"].items():
            relative(p)
            if p.startswith(("docs/.engineering/", "docs/agent-guides/managed/", ".repo-foundry/", ".agents/")):
                raise BaselineError("A case cannot overwrite Spec or Harness state")
            for stage in ("before", "after"):
                if digest(snapshot[stage].encode()) != snapshot[stage + "_sha256"]:
                    raise BaselineError(f"Snapshot digest drift: {name}:{p}:{stage}")


def score(predicted: set[str], labels: dict) -> dict:
    """Score only adjudicable binary labels; expose every excluded candidate."""
    positive = set(labels["applicable"])
    negative = set(labels["not_applicable"])
    tp, fp, fn = predicted & positive, predicted & negative, positive - predicted
    return {"tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
            "recall": len(tp) / len(positive) if positive else None,
            "precision": len(tp) / (len(tp) + len(fp)) if tp or fp else None,
            "expected_positive": len(positive), "retrieved": len(predicted),
            "excluded_retrieved": {state: sorted(predicted & set(labels[state]))
                                   for state in ("context_only", "uncertain", "unreviewed")}}


def aggregate(rows: list[dict]) -> dict:
    tp = sum(len(r["metrics"]["tp"]) for r in rows)
    fp = sum(len(r["metrics"]["fp"]) for r in rows)
    fn = sum(len(r["metrics"]["fn"]) for r in rows)
    excluded = sum(sum(len(v) for v in r["metrics"]["excluded_retrieved"].values()) for r in rows)
    return {"unit": "case_requirement_pair; each case counted once, not once per repeat",
            "tp": tp, "fp": fp, "fn": fn,
            "recall": tp / (tp + fn) if tp + fn else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "excluded_retrieved": excluded,
            "assessed_retrieved": tp + fp,
            "retrieved_total": tp + fp + excluded}


def extract_fixture(archive: Path, expected: str, destination: Path) -> Path:
    if digest(read_bytes(archive, MAX_ARCHIVE)) != expected:
        raise BaselineError("Fixture SHA-256 mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 5000 or sum(m.size for m in members) > MAX_EXPANDED:
            raise BaselineError("Expanded fixture exceeds limits")
        seen = set()
        for member in members:
            name = relative(member.name.rstrip("/"))
            if name.split("/")[0] != "project" or name in seen:
                raise BaselineError("Invalid or duplicate fixture member")
            if not (member.isdir() or member.isfile()):
                raise BaselineError("Fixture links and special files are forbidden")
            seen.add(name)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source:
                    target.write_bytes(source.read())
    return destination / "project"


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BaselineError("Unexpected symlink during read-only measurement")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(read_bytes(path, MAX_ARCHIVE))
    return result


def load_router(path: Path, expected: str):
    source = read_bytes(path)
    if digest(source) != expected:
        raise BaselineError("Router source differs from the frozen baseline pin")
    module = types.ModuleType("_activation_baseline_router")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def verify_subject(root: Path, corpus: dict, router) -> None:
    pins = corpus["pins"]
    pinned_bytes = {}
    for path, key in (("docs/.engineering/specs.lock.json", "lock_sha256"),
                      ("docs/.engineering/specs.json", "manifest_sha256"),
                      ("docs/agent-guides/managed/requirements.json", "index_sha256")):
        data = read_bytes(root / path)
        if digest(data) != pins[key]:
            raise BaselineError(f"Subject pin drift: {path}")
        pinned_bytes[key] = data
    state = router.load_state(root)
    lock = json_bytes(pinned_bytes["lock_sha256"])
    locked_sources = {spec["id"]: spec["source_path"] for spec in lock["specs"]}
    if (state.revision, state.catalog_version, state.catalog_digest) != (
        pins["catalog_revision"], pins["catalog_version"], pins["catalog_sha256"]
    ):
        raise BaselineError("Catalog pin mismatch")
    actual = state.requirement_index.by_requirement
    if set(actual) != set(corpus["requirements"]):
        raise BaselineError("Requirement universe mismatch")
    for name, ref in corpus["requirements"].items():
        item = actual[name]
        if (item.spec_id, locked_sources.get(item.spec_id),
                item.block.start_byte, item.block.end_byte, item.block.sha256) != (
            ref["spec"], ref.get("source_path"), ref["start_byte"], ref["end_byte"], ref["sha256"]
        ):
            raise BaselineError(f"Requirement source drift: {name}")


def invoke(router_path: Path, subject: Path, operation: str, paths: list[str],
           log, spec: str | None = None) -> dict:
    if operation not in ROUTER_OPERATIONS:
        raise BaselineError("Mutation/activation operations are not permitted")
    argv = [sys.executable, "-B", str(router_path), "--repo", str(subject), operation]
    for path in paths:
        argv.extend(["--path", path])
    if spec is not None:
        argv.extend(["--spec", spec])
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", GIT_ALLOW_PROTOCOL="file")
    run = subprocess.run(argv, cwd=subject, env=env, capture_output=True, timeout=30)
    record = {"argv": argv, "cwd": str(subject), "exit_code": run.returncode,
              "stdout": run.stdout.decode("utf-8", "replace"),
              "stderr": run.stderr.decode("utf-8", "replace"),
              "stdout_sha256": digest(run.stdout), "stderr_sha256": digest(run.stderr)}
    log.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.flush()
    if run.returncode:
        raise BaselineError(f"Router {operation} failed: {record['stderr']}")
    return json_bytes(run.stdout)


def verify_history(archive: Path, history: dict, case: dict) -> dict:
    diff_ref = bind_final_diff(history, case)
    expected = history["recovered_experiment"]
    if digest(read_bytes(archive, MAX_ARCHIVE)) != expected["archive_sha256"]:
        raise BaselineError("Historical archive digest mismatch")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > MAX_EXPANDED:
            raise BaselineError("Invalid historical archive inventory")
        manifest = json_bytes(z.read("SHA256_MANIFEST.json"))
        rows = manifest["files"]
        if {r["path"] for r in rows} != set(names) - {"SHA256_MANIFEST.json", "SHA256SUMS"}:
            raise BaselineError("Historical manifest does not cover the payload")
        for row in rows:
            payload = z.read(relative(row["path"]))
            if digest(payload) != row["sha256"] or len(payload) != row["size_bytes"]:
                raise BaselineError("Historical payload drift")
        for ref in expected["sources"]:
            if digest(z.read(ref["path"])) != ref["sha256"]:
                raise BaselineError("Historical source reference drift")
        # The case, registry and actual entry must identify the same bytes.
        if digest(z.read(HISTORICAL_DIFF_PATH)) != diff_ref["sha256"]:
            raise BaselineError("Historical case final_diff bytes mismatch")
        matrix = json_bytes(z.read("audit/compliance-matrix.json"))
        counts = dict(Counter(r["result"] for r in matrix["requirements"]))
        activation_log = json_bytes(z.read("evidence/coder-014-router-activate-reviewed-budget.json"))
        activation = json_bytes(activation_log["stdout"].encode())
        selected = {r["id"] for r in activation["resolved_requirements"]}
        if counts != expected["counts_preserved"] or selected != set(expected["resolved_selected"]):
            raise BaselineError("Historical projection drift")
        return {"status": "source_integrity_rechecked_not_new_agent_execution",
                "verified_payloads": len(rows), "counts_preserved": counts,
                "missing_preserved": matrix["missing_applicable_requirements"],
                "historical_scoped_label_metrics": score(selected, case["labels"]),
                "label_time": "retrospective final-diff audit, non-blind/shared filesystem",
                "relation_to_claimed_17_7": "unestablished"}


def measure(corpus: dict, fixture: Path, router_path: Path, output: Path,
            *, repeats: int = 2, audit_archive: Path | None = None, history: dict | None = None,
            frozen_inputs: dict[Path, bytes] | None = None) -> dict:
    validate_corpus(corpus)
    historical_case = next((c for c in corpus["cases"] if c["id"] == HISTORICAL_CASE_ID), None)
    if historical_case is not None:
        if history is None:
            raise BaselineError("Historical source registry is required")
        bind_final_diff(history, historical_case)
    if audit_archive is not None and historical_case is None:
        raise BaselineError("Historical case is required for archive revalidation")
    if repeats != 2:
        raise BaselineError("This frozen protocol requires exactly two deterministic repeats")
    router = load_router(router_path, corpus["pins"]["router_sha256"])
    if output.exists() or any(p.is_symlink() for p in output.parents):
        raise BaselineError("Use a new non-symlink output directory; old runs are immutable")
    output.mkdir(parents=True)
    observations = []
    with (output / "commands.jsonl").open("w", encoding="utf-8") as log:
        for case in corpus["cases"]:
            with tempfile.TemporaryDirectory(prefix="rf-activation-") as tmp:
                subject = extract_fixture(fixture, corpus["pins"]["fixture_sha256"], Path(tmp))
                verify_subject(subject, corpus, router)
                for path, expected in case.get("fixture_source_hashes", {}).items():
                    if digest(read_bytes(subject / relative(path))) != expected:
                        raise BaselineError("Historical code snapshot drift")
                for path, snapshot in case["snapshots"].items():
                    target = subject / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(snapshot["before"], encoding="utf-8")
                before = inventory(subject)
                samples = []
                for _ in range(repeats):
                    candidate = invoke(router_path, subject, "candidates", case["planned_paths"], log)
                    specs = [r["id"] for r in candidate["candidates"]]
                    requirements = set()
                    # Selection labels are never supplied to the Router. Every
                    # returned Spec is inspected equally, one bounded card set at a time.
                    for spec in specs:
                        cards = invoke(router_path, subject, "requirements", case["planned_paths"], log, spec)
                        requirements.update(c["id"] for c in cards["cards"])
                    samples.append({"specs": specs, "requirements": sorted(requirements)})
                after = inventory(subject)
                if before != after:
                    raise BaselineError("READ_ONLY_INVARIANT_FAILED")
                if samples[0] != samples[1]:
                    raise BaselineError("DETERMINISM_FAILED")
                predicted = set(samples[0]["requirements"])
                if not predicted <= set(corpus["requirements"]):
                    raise BaselineError("Router returned unknown Requirements")
                uncovered = [p for p in case["actual_paths"] if not router._covered(p, case["planned_paths"])]
                metrics = score(predicted, case["labels"])
                categories = []
                if metrics["fn"]:
                    categories.append("CANDIDATE_RETRIEVAL_MISS")
                if metrics["fp"]:
                    categories.append("CONSERVATIVE_CANDIDATE_OVERINCLUSION_NOT_ACTIVATION_FAILURE")
                if uncovered:
                    categories.append("DECLARED_SCOPE_UNCOVERED")
                if case["labels"]["uncertain"]:
                    categories.append("APPLICABILITY_UNRESOLVED")
                observations.append({"case_id": case["id"], "origin": case["origin"],
                    "sample": samples[0], "metrics": metrics, "uncovered_actual_paths": uncovered,
                    "failure_classification": categories, "identical_repeats": repeats,
                    "subject_inventory_sha256": digest(canonical(before)), "input_unchanged": True,
                    "review_status": case["review"]["status"],
                    "activation": {"status": "NOT_MEASURED", "recall": None, "precision": None}})
    if digest(read_bytes(fixture, MAX_ARCHIVE)) != corpus["pins"]["fixture_sha256"]:
        raise BaselineError("Fixture changed during measurement")
    if digest(read_bytes(router_path)) != corpus["pins"]["router_sha256"]:
        raise BaselineError("Router changed during measurement")
    historical = {"status": "NOT_REVALIDATED", "reason": "Original archive not supplied"}
    if audit_archive is not None:
        historical = verify_history(audit_archive, history, historical_case)
    result = {"schema_version": 1, "measurement_status": "complete", "read_only": True,
              "router_revision": corpus["pins"]["router_revision"], "router_sha256": corpus["pins"]["router_sha256"],
              "corpus_sha256": digest(canonical(corpus)), "pins": corpus["pins"],
              "scope": "candidate Requirement retrieval on provisional labels; NOT semantic activation/compliance",
              "candidate_metrics": aggregate(observations),
              "candidate_metrics_by_origin": {origin: aggregate([r for r in observations if r["origin"] == origin])
                                              for origin in sorted({r["origin"] for r in observations})},
              "activation_metrics": {"status": "NOT_MEASURED", "recall": None, "precision": None},
              "gold_status": "provisional; original 17/7 evidence and independent new-label review pending",
              "cases": observations, "historical_recheck": historical,
              "unresolved_claims": history["unresolved_claims"] if history else [],
              "limits": ["Read-only CLI replay, no Coding Agent or native Hook tested",
                         "Context-only, uncertain and unreviewed labels excluded from binary metrics",
                         "All constructed labels require independent second review",
                         "Two repeats test determinism, not statistical independence or model efficacy",
                         "Snapshots are not an authenticated or transactional filesystem boundary"]}
    for path, frozen in (frozen_inputs or {}).items():
        if read_bytes(path) != frozen:
            raise BaselineError("Evaluation inputs changed during measurement")
    (output / "observations.json").write_bytes(canonical(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--corpus", type=Path, default=HERE / "corpus.json")
    parser.add_argument("--history", type=Path, default=HERE / "history.json")
    parser.add_argument("--audit-archive", type=Path)
    args = parser.parse_args()
    try:
        corpus_bytes = read_bytes(args.corpus)
        history_bytes = read_bytes(args.history)
        corpus, history = json_bytes(corpus_bytes), json_bytes(history_bytes)
        result = measure(corpus, args.fixture, ROOT / "assets/core/engineering-specs/spec_router.py",
                         args.output, audit_archive=args.audit_archive, history=history,
                         frozen_inputs={args.corpus: corpus_bytes, args.history: history_bytes})
        print(json.dumps({"measurement_status": result["measurement_status"],
                          "candidate_metrics": result["candidate_metrics"],
                          "activation_metrics": result["activation_metrics"],
                          "gold_status": result["gold_status"]}, ensure_ascii=False, indent=2))
        return 0
    except (BaselineError, OSError, KeyError, TypeError, StopIteration,
            tarfile.TarError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(f"activation-baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
