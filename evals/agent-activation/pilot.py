#!/usr/bin/env python3
"""Prepare answer-free subjects and probe a runtime; never execute a model.

A successful preparation is not an Agent trial, independent label review,
pre-edit attestation, or a semantic compliance verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "evals/spec-activation/baseline.py"
BASELINE_SHA256 = "5de1581ec0da3991afa1964b69c75029239498af4171bf86dab01ad99eda017b"
CORPUS = ROOT / "evals/spec-activation/corpus.json"
CORPUS_SHA256 = "897a792aee32010a45060d1b26846fcf6c8dec27783868405314c9d6519c3796"
CASE_IDS = ("format-only", "local-name-only", "explain-same-go-path", "ambiguous-boundary")
PARENT_HEAD = "1e8c6a1d5b5ecfa9262cc9908721702734bc98b1"
TARGET_VERSION = "0.15.2"


class PilotError(ValueError):
    """Invalid preparation input or unavailable preparation dependency."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def load_baseline():
    if BASELINE.is_symlink() or sha(BASELINE.read_bytes()) != BASELINE_SHA256:
        raise PilotError("The prerequisite evaluator differs from the fixed PR111 revision")
    spec = importlib.util.spec_from_file_location("_pilot_baseline", BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_corpus(baseline) -> dict:
    data = baseline.read_bytes(CORPUS)
    if sha(data) != CORPUS_SHA256:
        raise PilotError("The source corpus changed; define a new pilot revision")
    corpus = baseline.json_bytes(data)
    baseline.validate_corpus(corpus)
    return corpus


def source_task(case: dict) -> dict:
    """An allowlist projection, not filtering by names of known answer fields."""
    files = {}
    for path, snapshot in case["snapshots"].items():
        before = snapshot["before"]
        if sha(before.encode()) != snapshot["before_sha256"]:
            raise PilotError("Before-snapshot digest mismatch")
        files[path] = before
    return {"task": case["task"], "files": files}


def reserve_output(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise PilotError("Output path must not contain symlinks")
    if absolute.exists() or absolute == ROOT or ROOT in absolute.parents:
        raise PilotError("Use a new output directory outside the source checkout")
    absolute.mkdir(parents=True, mode=0o700)
    return absolute


def invoke(argv: list[str], cwd: Path, log, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run trusted local setup tools, retaining unsuccessful attempts too."""
    try:
        proc = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write(canonical({"argv": argv, "cwd": str(cwd), "error": type(exc).__name__}).decode())
        log.flush()
        raise PilotError(f"Setup failed: {type(exc).__name__}") from exc
    log.write(canonical({"argv": argv, "cwd": str(cwd), "exit_code": proc.returncode,
                         "stdout": proc.stdout, "stderr": proc.stderr}).decode())
    log.flush()
    if proc.returncode:
        raise PilotError(f"Setup command exited {proc.returncode}: {argv[0]}")
    return proc


def check_preview(preview: dict) -> None:
    # Only a conflict-free official plan may be applied to the disposable seed.
    actions = preview.get("actions")
    if not isinstance(actions, list) or any(
        not isinstance(row, dict) or row.get("action") == "conflict" for row in actions
    ):
        raise PilotError("Official upgrade preview is missing or has conflicts")
    if preview.get("mode") != "dry-run":
        raise PilotError("Expected the official read-only upgrade preview")
    if (preview.get("to", {}).get("distribution") != TARGET_VERSION
            or preview.get("to", {}).get("governance_profile") != "strict"):
        raise PilotError("Unexpected target distribution")


def protect_business(before: dict, after: dict) -> None:
    protected = {p for p in set(before) | set(after) if p.endswith(".go") or p in {"go.mod", "go.sum"}
                 or p.startswith("docs/agent-guides/managed/")
                 or p in {"docs/.engineering/specs.json", "docs/.engineering/specs.lock.json"}}
    if any(before.get(p) != after.get(p) for p in protected):
        raise PilotError("Official upgrade changed a protected business or normative input")


def prepare(fixture: Path, output: Path) -> dict:
    baseline = load_baseline()
    corpus = load_corpus(baseline)
    router_path = ROOT / "assets/core/engineering-specs/spec_router.py"
    router = baseline.load_router(router_path, corpus["pins"]["router_sha256"])
    result_dir = reserve_output(output)
    coordinator = result_dir / "coordinator"
    coordinator.mkdir()
    records = []
    try:
        with (coordinator / "setup.log").open("w", encoding="utf-8") as log:
            with tempfile.TemporaryDirectory(prefix="rf-agent-subject-") as temporary:
                seed = baseline.extract_fixture(fixture, corpus["pins"]["fixture_sha256"], Path(temporary))
                baseline.verify_subject(seed, corpus, router)
                before = baseline.inventory(seed)
                command = [sys.executable, "-B", str(ROOT / "scripts/foundryctl.py"),
                           "--repo", str(seed), "upgrade", "--to", TARGET_VERSION,
                           "--governance-profile", "strict"]
                preview = baseline.json_bytes(invoke(command, ROOT, log).stdout.encode())
                check_preview(preview)
                if before != baseline.inventory(seed):
                    raise PilotError("Upgrade preview changed the disposable seed")
                invoke([*command, "--apply"], ROOT, log)
                protect_business(before, baseline.inventory(seed))
                baseline.verify_subject(seed, corpus, router)
                if sha((seed / ".repo-foundry/engineering-specs/spec_router.py").read_bytes()) != corpus["pins"]["router_sha256"]:
                    raise PilotError("Official upgrade did not deliver the pinned Router")
                harness = baseline.json_bytes((seed / "docs/.engineering/harness.json").read_bytes())
                if harness.get("governance", {}).get("profile") != "strict":
                    raise PilotError("Pilot requires the declared strict treatment")
                cli = [sys.executable, "-B", str(ROOT / "scripts/foundryctl.py"), "--repo", str(seed)]
                invoke([*cli, "validate", "--harness"], ROOT, log)
                invoke([*cli, "spec", "validate"], ROOT, log)
                by_id = {c["id"]: c for c in corpus["cases"]}
                for number, name in enumerate(CASE_IDS, 1):
                    case = source_task(by_id[name])
                    home = result_dir / "subjects" / f"case-{number:02}"
                    project = home / "project"
                    shutil.copytree(seed, project)
                    for path, content in case["files"].items():
                        target = project / baseline.relative(path)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content, encoding="utf-8")
                    (home / "TASK.md").write_text(case["task"] + "\n", encoding="utf-8")
                    baseline.verify_subject(project, corpus, router)
                    # Fresh Git history contains only the initial subject. No source
                    # repository history, reference patch, labels or model output.
                    git = ["git", "-c", "core.hooksPath=/dev/null"]
                    invoke([*git, "init", "-q"], project, log)
                    invoke([*git, "add", "--all"], project, log)
                    invoke([*git, "-c", "user.name=Activation Pilot", "-c", "user.email=pilot@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "-qm", "Frozen pilot input"], project, log)
                    tree = invoke([*git, "rev-parse", "HEAD^{tree}"], project, log).stdout.strip()
                    records.append({"subject": home.name, "source_case": name,
                                    "task_sha256": sha((home / "TASK.md").read_bytes()),
                                    "initial_tree": tree,
                                    "snapshot_sha256": sha(baseline.canonical({
                                        p: d for p, d in baseline.inventory(project).items()
                                        if not p.startswith(".git/")}))})
        # Re-read all inputs before publishing a completion manifest.
        load_corpus(baseline)
        load_baseline()
        if sha(baseline.read_bytes(fixture, baseline.MAX_ARCHIVE)) != corpus["pins"]["fixture_sha256"]:
            raise PilotError("Fixture changed during preparation")
        if sha(router_path.read_bytes()) != corpus["pins"]["router_sha256"]:
            raise PilotError("Router changed during preparation")
        result = {"schema_version": 1, "status": "PREPARED_NOT_EXECUTED",
                  "parent_head": PARENT_HEAD, "corpus_sha256": CORPUS_SHA256,
                  "pins": corpus["pins"], "governance": "strict",
                  "subjects": records, "planned_repetitions": 3,
                  "agent_trials_started": 0, "activation_recall": None, "activation_precision": None,
                  "gold_status": "NOT_INDEPENDENTLY_ACCEPTED",
                  "isolation": "NOT_ESTABLISHED_BY_DIRECTORY_SEPARATION",
                  "native_hook_enforcement": "NOT_TESTED"}
        (coordinator / "preparation.json").write_bytes(canonical(result))
        return result
    except Exception as exc:
        (coordinator / "failure.json").write_bytes(canonical({"status": "PREPARATION_FAILED",
            "error": type(exc).__name__, "agent_trials_started": 0}))
        raise


def probe_runtime(agent: str = "codex") -> dict:
    """Inspect CLI availability/auth status only; do not install or infer auth."""
    if agent not in {"codex"}:
        raise PilotError("Only the documented codex probe is supported")
    binary = shutil.which(agent)
    record = {"schema_version": 1, "agent": agent, "executable_present": bool(binary),
              "credential_environment_present": bool(os.environ.get("CODEX_API_KEY")),
              "agent_trials_started": 0, "activation_recall": None, "activation_precision": None,
              "model_access": "NOT_TESTED", "isolation": "NOT_TESTED",
              "version": None, "login_status_exit_code": None, "blockers": []}
    if binary is None:
        record["blockers"].append("AGENT_EXECUTABLE_MISSING")
        record["status"] = "BLOCKED_NOT_STARTED"
        return record
    for suffix, field in ((["--version"], "version"), (["login", "status"], "login_status_exit_code")):
        try:
            proc = subprocess.run([binary, *suffix], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record["blockers"].append("AGENT_PROBE_" + type(exc).__name__.upper())
            continue
        if field == "version":
            record[field] = proc.stdout.strip()[:200] if proc.returncode == 0 else None
            if proc.returncode:
                record["blockers"].append("AGENT_VERSION_UNAVAILABLE")
        else:
            record[field] = proc.returncode
            # Do not record authentication output, file contents or token values.
            if proc.returncode and not record["credential_environment_present"]:
                record["blockers"].append("AGENT_AUTH_NOT_CONFIRMED")
    record["status"] = "BLOCKED_NOT_STARTED" if record["blockers"] else "LOCAL_PREREQUISITES_ONLY"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    ready = commands.add_parser("prepare", help="prepare answer-free subjects using the official upgrader")
    ready.add_argument("--fixture", type=Path, required=True)
    ready.add_argument("--output", type=Path, required=True)
    commands.add_parser("probe", help="probe Codex CLI/auth only; never call a model")
    args = parser.parse_args()
    try:
        result = prepare(args.fixture, args.output) if args.operation == "prepare" else probe_runtime()
        print(canonical(result).decode(), end="")
        return 2 if result["status"] == "BLOCKED_NOT_STARTED" else 0
    except (PilotError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"agent-activation-pilot: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
