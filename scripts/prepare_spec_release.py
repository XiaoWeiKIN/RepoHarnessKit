#!/usr/bin/env python3
"""Prepare one RF patch release for an authenticated, validated Spec Catalog tag."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def prepare(root: Path, catalog_version: str) -> dict[str, str]:
    if not VERSION.fullmatch(catalog_version):
        raise ValueError("Expected a Catalog MAJOR.MINOR.PATCH version")

    source = root / "scripts/foundryctl.py"
    original = source.read_text(encoding="utf-8")
    match = re.search(r'^DEFAULT_SPEC_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', original, re.M)
    if match is None:
        raise ValueError("RF default Spec version declaration is missing")
    previous_spec = match.group(1)
    current = tuple(map(int, previous_spec.split(".")))
    requested = tuple(map(int, catalog_version.split(".")))
    if requested <= current:
        return {"action": "skip", "catalog_version": previous_spec}

    old_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION.fullmatch(old_version):
        raise ValueError("Invalid RF VERSION")
    major, minor, patch = map(int, old_version.split("."))
    new_version = f"{major}.{minor}.{patch + 1}"

    # Each changed field is a current distribution contract, not release history.
    updates = {
        "scripts/foundryctl.py": [(f'DEFAULT_SPEC_VERSION = "{previous_spec}"',
                                  f'DEFAULT_SPEC_VERSION = "{catalog_version}"')],
        "tests/test_foundryctl.py": [(f"refs/tags/v{previous_spec}",
                                     f"refs/tags/v{catalog_version}")],
        "tests/test_repository_contracts.py": [(f'"{old_version}"', f'"{new_version}"'),
                                               (f'DEFAULT_SPEC_VERSION = "{previous_spec}"',
                                                f'DEFAULT_SPEC_VERSION = "{catalog_version}"')],
        "README.md": [(old_version, new_version), (previous_spec, catalog_version)],
        "README.zh-CN.md": [(old_version, new_version), (previous_spec, catalog_version)],
        "references/specifications.md": [(previous_spec, catalog_version)],
        "references/bootstrap.md": [(old_version, new_version)],
        "references/upgrades.md": [(old_version, new_version)],
    }
    new_contents = {}
    for name, pairs in updates.items():
        path = root / name
        text = path.read_text(encoding="utf-8")
        for before, after in pairs:
            if before not in text:
                raise ValueError(f"Missing release contract in {name}: {before}")
            text = text.replace(before, after)
        new_contents[path] = text

    # No partially applied source tree if one expected contract has drifted.
    metadata_path = root / "release.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["distribution"] != old_version or metadata["default_spec_version"] != previous_spec:
        raise ValueError("Release metadata differs from the current distribution")
    metadata.update(distribution=new_version, default_spec_version=catalog_version)
    new_contents[metadata_path] = json.dumps(metadata, indent=2) + "\n"
    for path, text in new_contents.items():
        path.write_text(text, encoding="utf-8")
    (root / "VERSION").write_text(new_version + "\n", encoding="utf-8")
    return {"action": "publish", "catalog_version": catalog_version, "rf_version": new_version}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    outcome = prepare(args.root, args.version)
    print(json.dumps(outcome))
