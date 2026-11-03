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
import stat
import sys
from pathlib import Path

import verification_receipt as receipt

MAX_MANIFEST = 128 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_CHECKS = 64
CHECK_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InputError(ValueError):
    pass


def secure_path(path: Path) -> Path:
    """Reject a symlink in any path component, not just the final filename.

    This is best-effort path inspection, not an immutable filesystem guarantee.
    Callers on systems with a symlinked /var or /tmp should pass canonical paths.
    """
    absolute = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise InputError(f"symlink in input path: {path}")
    return absolute


def read_snapshot(path: Path, limit: int) -> tuple[bytes, tuple[str, int, int]]:
    """Read bounded file bytes with inode identity and a stability check."""
    safe = secure_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(safe, flags), "rb") as handle:
            start = os.fstat(handle.fileno())
            if not stat.S_ISREG(start.st_mode) or start.st_size > limit:
                raise InputError(f"not a bounded regular file: {path}")
            data = handle.read(limit + 1)
            end = os.fstat(handle.fileno())
        current = os.stat(safe, follow_symlinks=False)
    except OSError as exc:
        raise InputError(f"cannot read input: {path}") from exc
    if len(data) > limit or (start.st_dev, start.st_ino, start.st_size,
                            start.st_mtime_ns, start.st_ctime_ns) != (
                            end.st_dev, end.st_ino, end.st_size,
                            end.st_mtime_ns, end.st_ctime_ns) or (
                            end.st_dev, end.st_ino) != (current.st_dev, current.st_ino):
        raise InputError(f"input changed while being read: {path}")
    return data, (hashlib.sha256(data).hexdigest(), end.st_dev, end.st_ino)


def read_json(path: Path) -> tuple[dict, str]:
    """Read a bounded, no-symlink JSON object with unique keys."""
    data, fingerprint = read_snapshot(path, MAX_MANIFEST)

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise InputError(f"duplicate JSON field: {key}")
            obj[key] = value
        return obj

    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(InputError("nonfinite JSON")))
    except (ValueError, UnicodeError) as exc:
        raise InputError(f"invalid JSON: {path}") from exc
    if not isinstance(obj, dict):
        raise InputError("expected JSON object")
    return obj, fingerprint[0]



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
    policy_path = secure_path(policy_file)
    if policy_path == root or root in policy_path.parents:
        raise InputError("coordinator policy must be outside the observed repository")
    policy, policy_digest = read_json(policy_file)
    if policy_digest != expected_policy_sha256:
        raise InputError("coordinator policy digest mismatch")
    evidence, evidence_digest = read_json(evidence_file)
    required = validate_policy(policy)
    supplied = validate_evidence(evidence, set(required))

    # Load every Receipt before taking a gate-wide snapshot. Its observed_files
    # may include explicitly bound Git-ignored source files.
    records = {}
    fingerprints = {}
    invalid = {}
    bound_paths: set[str] = set()
    used_inodes: set[tuple[int, int]] = set()
    used_contents: set[str] = set()
    for name, path in supplied.items():
        try:
            _, before_fp = read_snapshot(Path(path), MAX_RECEIPT_BYTES)
            if (before_fp[1], before_fp[2]) in used_inodes or before_fp[0] in used_contents:
                raise InputError("one Receipt used for multiple checks (hardlink or copy)")
            used_inodes.add((before_fp[1], before_fp[2]))
            used_contents.add(before_fp[0])
            record = receipt.read(path)
            _, after_fp = read_snapshot(Path(path), MAX_RECEIPT_BYTES)
            if before_fp != after_fp:
                raise InputError("Receipt changed during initial validation")
            records[name] = record
            fingerprints[name] = after_fp
            bound_paths.update(item["path"] for item in record["revision"]["observed_files"])
        except InputError as exc:
            if "multiple checks" in str(exc):
                raise
            invalid[name] = type(exc).__name__
        except (OSError, ValueError, KeyError, TypeError, receipt.handoff.HandoffError) as exc:
            invalid[name] = type(exc).__name__

    observed = sorted(bound_paths)
    before = receipt.observe(root, observed, None)
    rows = []
    for name, command in required.items():
        path = supplied.get(name)
        if path is None:
            rows.append({"id": name, "status": "UNVERIFIED", "reason": "MISSING_RECEIPT"})
            continue
        if name in invalid:
            rows.append({"id": name, "status": "UNVERIFIED", "reason": "INVALID_RECEIPT",
                         "detail": invalid[name]})
            continue
        try:
            record = records[name]
            if record["command"] != command:
                rows.append({"id": name, "status": "UNVERIFIED", "reason": "COMMAND_MISMATCH"})
                continue
            observation = receipt.check_receipt(root, path)
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

    after = receipt.observe(root, observed, None)
    gate_drift = receipt.drift(before, after)
    # Check each original Receipt file again after *all* calls to check_receipt.
    # Earlier files may have been corrupted after their per-check validation.
    input_drift = []
    for name, old_fp in fingerprints.items():
        try:
            _, new_fp = read_snapshot(Path(supplied[name]), MAX_RECEIPT_BYTES)
            if new_fp != old_fp:
                input_drift.append("RECEIPT_CHANGED_DURING_GATE:" + name)
        except InputError:
            input_drift.append("RECEIPT_UNREADABLE_AFTER_CHECK:" + name)
    try:
        _, current_policy_digest = read_json(policy_file)
        _, current_evidence_digest = read_json(evidence_file)
        if current_policy_digest != policy_digest:
            input_drift.append("POLICY_CHANGED_DURING_GATE")
        if current_evidence_digest != evidence_digest:
            input_drift.append("EVIDENCE_CHANGED_DURING_GATE")
    except (InputError, OSError):
        input_drift.append("GATE_INPUT_UNREADABLE_AFTER_CHECK")
    passed = not gate_drift and not input_drift and all(row["status"] == "PASS" for row in rows)
    return {"schema_version": 1, "completion": "PASS" if passed else "BLOCKED",
            "worktree_changed_during_gate": gate_drift,
            "input_changed_during_gate": input_drift,
            "policy_sha256": policy_digest, "evidence_sha256": evidence_digest,
            "checks": rows, "authority": "opt_in_coordinator_policy;not_native_hook;not_full_spec_compliance"}, 0 if passed else 1



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
