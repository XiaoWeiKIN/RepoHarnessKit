#!/usr/bin/env python3
"""Check release identity and versioned template changes without executing Git history."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
OWNERS = {
    "core": ("CORE_HARNESS_VERSION", "CORE_FILE_ASSETS"),
    "codex": ("CODEX_ADAPTER_VERSION", "CODEX_ADAPTER_FILE_ASSETS"),
    "claude": ("CLAUDE_ADAPTER_VERSION", "CLAUDE_ADAPTER_FILE_ASSETS"),
    "portable": ("PORTABLE_ADAPTER_VERSION", "PORTABLE_ADAPTER_FILE_ASSETS"),
}


def version(value: str) -> tuple[int, ...]:
    if not SEMVER.fullmatch(value):
        raise ValueError(f"Invalid release version: {value!r}")
    return tuple(map(int, value.split(".")))


def declarations(source: bytes) -> dict:
    """Evaluate only literals, tuple expansion and named constants used by ownership."""
    nodes = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node.value
    active = set()

    def read(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in active:
                raise ValueError(f"Cyclic release declaration: {node.id}")
            active.add(node.id)
            try:
                return read(nodes[node.id])
            finally:
                active.remove(node.id)
        if isinstance(node, (ast.Tuple, ast.List)):
            values = []
            for item in node.elts:
                if isinstance(item, ast.Starred):
                    values.extend(read(item.value))
                else:
                    values.append(read(item))
            return tuple(values)
        raise ValueError(f"Nonliteral release declaration: {ast.dump(node)}")

    names = {name for pair in OWNERS.values() for name in pair}
    names.update(("HARNESS_SCHEMA_VERSION", "ACTIVATION_PROTOCOL_VERSION", "DEFAULT_SPEC_VERSION"))
    return {name: read(nodes[name]) for name in names}


def git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def check(root: Path, base_ref: str) -> dict:
    # Resolve refs to a commit before constructing Git object names; no shell or
    # imports from the historical distribution are involved.
    base = git(root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").decode().strip()
    old = declarations(git(root, "show", f"{base}:scripts/foundryctl.py"))
    current = declarations((root / "scripts/foundryctl.py").read_bytes())
    previous_dist = git(root, "show", f"{base}:VERSION").decode().strip()
    dist = (root / "VERSION").read_text().strip()
    errors = []
    if version(dist) < version(previous_dist):
        errors.append(f"RELEASE_VERSION_DECREASED: distribution {previous_dist} -> {dist}")
    expected_metadata = {
        "schema_version": 1, "distribution": dist,
        "core": current["CORE_HARNESS_VERSION"],
        "adapters": {owner: current[OWNERS[owner][0]] for owner in ("codex", "claude", "portable")},
        "harness_schema": current["HARNESS_SCHEMA_VERSION"],
        "activation_protocol": current["ACTIVATION_PROTOCOL_VERSION"],
        "default_spec_version": current["DEFAULT_SPEC_VERSION"],
    }
    if json.loads((root / "release.json").read_text()) != expected_metadata:
        errors.append("RELEASE_METADATA_MISMATCH: release.json differs from VERSION / foundryctl constants")
    components = []
    for owner, (version_name, assets_name) in OWNERS.items():
        before, after = old[version_name], current[version_name]
        if version(after) < version(before):
            errors.append(f"RELEASE_VERSION_DECREASED: {owner} {before} -> {after}")
        def old_files():
            return {path: (asset, hashlib.sha256(git(root, "show", f"{base}:assets/{asset}")).hexdigest()) for path, asset in old[assets_name]}
        def new_files():
            return {path: (asset, hashlib.sha256((root / "assets" / asset).read_bytes()).hexdigest()) for path, asset in current[assets_name]}
        old_map, new_map = old_files(), new_files()
        changed = sorted(path for path in old_map.keys() | new_map.keys() if old_map.get(path) != new_map.get(path))
        if changed and version(after) <= version(before):
            errors.append(f"RELEASE_COMPONENT_VERSION_REQUIRED: {owner} remains {before}; changed templates: {', '.join(changed)}")
        if (changed or before != after) and version(dist) <= version(previous_dist):
            errors.append(f"RELEASE_DISTRIBUTION_VERSION_REQUIRED: {owner} changed under distribution {dist}")
        components.append(dict(owner=owner, previous=before, current=after, changed_templates=changed))
    return dict(ok=not errors, base_sha=base, distribution=dict(previous=previous_dist, current=dist), components=components, errors=errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default="HEAD", help="Immutable PR base / previous push SHA; default HEAD also checks uncommitted changes")
    args = parser.parse_args()
    try:
        result = check(args.repo.resolve(), args.base_ref)
    except (ValueError, KeyError, OSError, SyntaxError) as e:
        print(f"RELEASE_CHECK_INVALID: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
