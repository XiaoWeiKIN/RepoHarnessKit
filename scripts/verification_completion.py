#!/usr/bin/env python3
"""Fail-closed, coordinator-declared completion check for revision-bound receipts.

This is an opt-in check, not a native Agent hook, a full Spec compliance grader,
or an authentication system. A trusted coordinator must freeze the required
commands before the agent runs, and invoke this tool after source freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import verification_receipt as receipt

MAX_MANIFEST = 128 * 1024
MAX_CHECKS = 64
CHECK_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InputError(ValueError):
    pass


def read_json(path: Path) -> tuple[dict, str]:
    """Read a bounded, non-symlink JSON object with unique keys."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST:
        raise InputError(f"missing, unsafe or oversized input: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        data = stream.read(MAX_MANIFEST + 1)
    if len(data) > MAX_MANIFEST:
        raise InputError(f"oversized input: {path}")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise InputError(f"duplicate JSON field: {key}")
            obj[key] = value
        return obj

    try:
        obj = json.loads(
            data.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(InputError("nonfinite JSON")),
        )
    except (ValueError, UnicodeError) as exc:
        raise InputError(f"invalid JSON: {path}") from exc
    if not isinstance(obj, dict):
        raise InputError("expected JSON object")
    return obj, hashlib.sha256(data).hexdigest()


def validate_policy(obj: dict) -> dict[str, list[str]]:
    if (set(obj) != {"schema_version", "required_checks"}
            or type(obj["schema_version"]) is not int or obj["schema_version"] != 1):
        raise InputError("invalid policy schema/version")
    rows = obj["required_checks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CHECKS:
        raise InputError("policy must require 1..64 checks")
    result: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "command"}:
            raise InputError("invalid required check")
        name, command = row["id"], row["command"]
        if not isinstance(name, str) or not CHECK_ID.fullmatch(name) or name in result:
            raise InputError("invalid or duplicate check id")
        if not isinstance(command, list) or not 1 <= len(command) <= 64 or any(
            not isinstance(a, str) or not a or "\x00" in a or len(a.encode("utf-8")) > 4096
            for a in command
        ):
            raise InputError("invalid expected command")
        result[name] = command
    return result


def validate_evidence(obj: dict, required: set[str]) -> dict[str, str]:
    if (set(obj) != {"schema_version", "receipts"}
            or type(obj["schema_version"]) is not int or obj["schema_version"] != 1):
        raise InputError("invalid evidence schema/version")
    rows = obj["receipts"]
    if not isinstance(rows, list) or len(rows) > MAX_CHECKS:
        raise InputError("invalid evidence receipts")
    result: dict[str, str] = {}
    used_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "path"}:
            raise InputError("invalid evidence row")
        name, path = row["id"], row["path"]
        if not isinstance(name, str) or name not in required or name in result:
            raise InputError("duplicate or undeclared evidence id")
        if not isinstance(path, str) or not path or "\x00" in path or len(path.encode("utf-8")) > 4096:
            raise InputError("invalid evidence path")
        if not Path(path).is_absolute():
            raise InputError("receipt paths must be absolute")
        identity = os.path.normpath(path)
        if identity in used_paths:
            raise InputError("one Receipt cannot satisfy multiple required checks")
        used_paths.add(identity)
        result[name] = path
    return result


def check(root: Path, policy_file: Path, evidence_file: Path,
          expected_policy_sha256: str) -> tuple[dict, int]:
    if not SHA256.fullmatch(expected_policy_sha256):
        raise InputError("invalid expected policy SHA-256")
    # Coordinator policy cannot live inside the Agent-editable worktree.
    # This is not a proof of access controls; the caller owns isolation.
    policy_path = policy_file.resolve(strict=True)
    if policy_path == root or root in policy_path.parents:
        raise InputError("coordinator policy must be outside the observed repository")
    policy, policy_digest = read_json(policy_file)
    if policy_digest != expected_policy_sha256:
        raise InputError("coordinator policy digest mismatch")
    evidence, evidence_digest = read_json(evidence_file)
    required = validate_policy(policy)
    supplied = validate_evidence(evidence, set(required))
    before = receipt.observe(root, [], None)
    rows = []
    for name, command in required.items():
        path = supplied.get(name)
        if path is None:
            rows.append({"id": name, "status": "UNVERIFIED", "reason": "MISSING_RECEIPT"})
            continue
        try:
            record = receipt.read(path)
            if record["command"] != command:
                rows.append({"id": name, "status": "UNVERIFIED", "reason": "COMMAND_MISMATCH"})
                continue
            observation = receipt.check_receipt(root, path)
            # Reject a receipt replaced between the two required reads.
            if observation["receipt_sha256"] != record["payload_sha256"]:
                rows.append({"id": name, "status": "UNVERIFIED",
                             "reason": "RECEIPT_CHANGED_DURING_GATE"})
                continue
            outcome = observation["outcome"]
            status = {"passed": "PASS", "failed": "FAIL", "stale": "STALE",
                      "unknown": "UNVERIFIED"}.get(outcome, "UNVERIFIED")
            rows.append({"id": name, "status": status, "reason": outcome.upper(),
                         "receipt_sha256": observation["receipt_sha256"],
                         "exit_code": observation["exit_code"],
                         "receipt_reasons": observation["reasons"]})
        except (OSError, ValueError, KeyError, TypeError, receipt.handoff.HandoffError) as exc:
            rows.append({"id": name, "status": "UNVERIFIED", "reason": "INVALID_RECEIPT",
                         "detail": type(exc).__name__})
    after = receipt.observe(root, [], None)
    gate_drift = receipt.drift(before, after)
    try:
        _, current_policy_digest = read_json(policy_file)
        _, current_evidence_digest = read_json(evidence_file)
        input_drift = []
        if current_policy_digest != policy_digest:
            input_drift.append("POLICY_CHANGED_DURING_GATE")
        if current_evidence_digest != evidence_digest:
            input_drift.append("EVIDENCE_CHANGED_DURING_GATE")
    except (InputError, OSError):
        input_drift = ["GATE_INPUT_UNREADABLE_AFTER_CHECK"]
    passed = not gate_drift and not input_drift and all(row["status"] == "PASS" for row in rows)
    return {
        "schema_version": 1, "completion": "PASS" if passed else "BLOCKED",
        "worktree_changed_during_gate": gate_drift,
        "input_changed_during_gate": input_drift,
        "policy_sha256": policy_digest, "evidence_sha256": evidence_digest,
        "checks": rows,
        "authority": "opt_in_coordinator_policy;not_native_hook;not_full_spec_compliance",
    }, 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--policy", required=True, help="coordinator-frozen command policy JSON")
    parser.add_argument("--policy-sha256", required=True,
                        help="SHA-256 frozen and supplied by a trusted coordinator, not the agent")
    parser.add_argument("--evidence", required=True, help="record of individual Receipt paths JSON")
    args = parser.parse_args()
    try:
        root = receipt.handoff.repository_root(args.repo)
        result, code = check(root, Path(args.policy), Path(args.evidence), args.policy_sha256)
        sys.stdout.write(json.dumps(result, sort_keys=True, ensure_ascii=False) + "\n")
        return code
    except (InputError, OSError, receipt.handoff.HandoffError) as exc:
        print(f"verification-completion: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
