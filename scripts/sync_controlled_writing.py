#!/usr/bin/env python3
"""Maintain offline authoring-guide copies in independent Skill packages."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GUIDE = Path("references/controlled-writing.md")
SKILLS = (
    "design-documentation",
    "engineering-benchmark",
    "engineering-research",
    "governed-design",
    "engineering-execution-plan",
    "engineering-case-study",
)


def regular_path(root: Path, relative: Path, *, required: bool) -> Path:
    """Reject symlinks and non-files before a maintainer changes any copy."""
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlink is not a managed guide path: {relative}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Not a regular file: {relative}")
    if required and not path.is_file():
        raise ValueError(f"Missing source-checkout file: {relative}")
    return path


def sync(root: Path, *, apply: bool = False) -> dict[str, object]:
    """Preview by default. Only --apply replaces generated guide copies."""
    root = root.resolve()
    source = regular_path(root, GUIDE, required=True).read_bytes()
    if not source.decode("utf-8").startswith("# Controlled technical writing\n"):
        raise ValueError("Source is not the controlled-writing guide")
    targets: list[Path] = []
    for skill in SKILLS:
        regular_path(root, Path(skill) / "SKILL.md", required=True)
        target = regular_path(root, Path(skill) / GUIDE, required=False)
        if not target.parent.is_dir():
            raise ValueError(f"Missing Skill references directory: {skill}")
        targets.append(target)
    changed = [path for path in targets if not path.exists() or path.read_bytes() != source]
    # Complete preflight before writing. This command operates on a source
    # checkout, never on a target project's artifacts or installed user Skills.
    if apply:
        for path in changed:
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(source)
                temporary.chmod(0o644)
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    return {
        "mode": "apply" if apply else "check",
        "changed": [path.relative_to(root).as_posix() for path in changed],
        "ok": apply or not changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Refresh packaged copies")
    args = parser.parse_args(argv)
    try:
        result = sync(ROOT, apply=args.apply)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
