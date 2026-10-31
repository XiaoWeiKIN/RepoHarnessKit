#!/usr/bin/env python3
"""Run the provider-neutral integrity checks for the source repository."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
INDEX_PATHS = (
    Path("docs/RESEARCH.md"),
    Path("docs/DESIGN-DOCS.md"),
    Path("docs/DECISIONS.md"),
    Path("docs/PLANS.md"),
    Path("docs/BUGFIXES.md"),
)
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SUITE_TIMEOUT_SECONDS = 600


class CheckError(RuntimeError):
    pass


def run(label: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"[check] {label}", flush=True)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=SUITE_TIMEOUT_SECONDS,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise CheckError(
            f"{label} failed with exit status {result.returncode}"
        )


def repository_markdown_files() -> list[Path]:
    return sorted(
        path
        for pattern in ("*.md", "*.md.template")
        for path in ROOT.rglob(pattern)
        if not EXCLUDED_DIRECTORIES.intersection(path.relative_to(ROOT).parts)
    )


def visible_markdown_lines(text: str):
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            continue
        if fence is None:
            yield number, line


def link_path(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    elif re.search(r"\s+[\"']", target):
        target = re.split(r"\s+[\"']", target, maxsplit=1)[0]
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return urllib.parse.unquote(parsed.path)


def validate_markdown_links() -> None:
    errors: list[str] = []
    root = ROOT.resolve()
    for source in repository_markdown_files():
        for line_number, line in visible_markdown_lines(
            source.read_text(encoding="utf-8")
        ):
            for match in LINK_RE.finditer(line):
                relative = link_path(match.group(1))
                if relative is None:
                    continue
                if relative.startswith("/"):
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"absolute local link is not portable: {relative}"
                    )
                    continue
                target = (source.parent / relative).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"local link escapes repository: {relative}"
                    )
                    continue
                if not target.exists():
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"missing local link target: {relative}"
                    )
    if errors:
        raise CheckError("Markdown link validation failed:\n- " + "\n- ".join(errors))
    print("[check] Markdown links", flush=True)


def skill_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(?P<body>.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise CheckError(f"{path.relative_to(ROOT)}: invalid YAML frontmatter")
    result: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def validate_skill_packages() -> None:
    skills = (
        (ROOT, "repo-foundry-ai"),
        (
            ROOT / "assets" / "adapters" / "codex" / "engineering-specs",
            "engineering-specs",
        ),
        (
            ROOT / "engineering-execution-plan",
            "engineering-execution-plan",
        ),
        (ROOT / "architecture-design", "architecture-design"),
        (ROOT / "detailed-design", "detailed-design"),
        (ROOT / "engineering-research", "engineering-research"),
        (ROOT / "engineering-design", "engineering-design"),
        (ROOT / "engineering-benchmark", "engineering-benchmark"),
        (ROOT / "engineering-case-study", "engineering-case-study"),
    )
    for directory, expected_name in skills:
        filename = (
            "SKILL.md.template"
            if directory.is_relative_to(ROOT / "assets") else "SKILL.md"
        )
        skill_path = directory / filename
        metadata = skill_frontmatter(skill_path)
        if metadata.get("name") != expected_name:
            raise CheckError(
                f"{skill_path}: expected name {expected_name!r}"
            )
        if "description" not in metadata:
            raise CheckError(f"{skill_path}: missing description")
        agent_metadata = (directory / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        for field in ("display_name:", "short_description:", "default_prompt:"):
            if field not in agent_metadata:
                raise CheckError(
                    f"{directory / 'agents' / 'openai.yaml'}: missing {field}"
                )

    project_skill_assets = (
        (
            ROOT / "assets" / "core" / "repo-foundry-ai" / "SKILL.md.template",
            "repo-foundry-ai",
        ),
        (
            ROOT
            / "assets"
            / "adapters"
            / "codex"
            / "repo-foundry-ai"
            / "SKILL.md.template",
            "repo-foundry-ai",
        ),
        (
            ROOT
            / "assets"
            / "adapters"
            / "claude"
            / "repo-foundry-ai"
            / "SKILL.md.template",
            "repo-foundry-ai",
        ),
        (
            ROOT
            / "assets"
            / "adapters"
            / "claude"
            / "engineering-specs"
            / "SKILL.md.template",
            "engineering-specs",
        ),
    )
    for path, expected_name in project_skill_assets:
        metadata = skill_frontmatter(path)
        if metadata.get("name") != expected_name:
            raise CheckError(
                f"{path.relative_to(ROOT)}: expected name {expected_name!r}"
            )
        if "description" not in metadata:
            raise CheckError(
                f"{path.relative_to(ROOT)}: missing description"
            )
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in ("~/", "/Users/", "/home/")):
            raise CheckError(
                f"{path.relative_to(ROOT)}: project Skill uses a home path"
            )

    portable_sources = [
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "SKILL.md",
        (
            ROOT
            / "assets"
            / "adapters"
            / "codex"
            / "engineering-specs"
            / "SKILL.md.template"
        ),
        *(path for path, _ in project_skill_assets),
        *sorted((ROOT / "references").glob("*.md")),
        ROOT / "engineering-execution-plan" / "SKILL.md",
        *sorted(
            (
                ROOT
                / "engineering-execution-plan"
                / "references"
            ).glob("*.md")
        ),
        ROOT / "engineering-research" / "SKILL.md",
        *sorted((ROOT / "engineering-research" / "references").glob("*.md")),
        ROOT / "architecture-design" / "SKILL.md",
        *sorted((ROOT / "architecture-design" / "references").glob("*.md")),
        ROOT / "detailed-design" / "SKILL.md",
        *sorted((ROOT / "detailed-design" / "references").glob("*.md")),
        ROOT / "engineering-design" / "SKILL.md",
        *sorted((ROOT / "engineering-design" / "references").glob("*.md")),
        ROOT / "engineering-benchmark" / "SKILL.md",
        *sorted((ROOT / "engineering-benchmark" / "references").glob("*.md")),
        ROOT / "engineering-case-study" / "SKILL.md",
        *sorted((ROOT / "engineering-case-study" / "references").glob("*.md")),
    ]
    forbidden = ("~/.codex/skills", "~/.agents/skills")
    for path in portable_sources:
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            if value in text:
                raise CheckError(
                    f"{path.relative_to(ROOT)}: host-specific skill path {value!r}"
                )
    print("[check] Skill package metadata and portability", flush=True)


def validate_eval_catalog(path: Path, expected_skill_name: str) -> None:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(
            f"{path.relative_to(ROOT)}:{exc.lineno}:{exc.colno}: invalid JSON: "
            f"{exc.msg}"
        ) from exc

    if not isinstance(catalog, dict):
        raise CheckError(f"{path.relative_to(ROOT)}: catalog must be an object")
    if catalog.get("skill_name") != expected_skill_name:
        raise CheckError(
            f"{path.relative_to(ROOT)}: skill_name must be "
            f"{expected_skill_name!r}"
        )
    evals = catalog.get("evals")
    if not isinstance(evals, list) or not evals:
        raise CheckError(f"{path.relative_to(ROOT)}: evals must be a non-empty array")

    seen_ids: set[int] = set()
    for position, item in enumerate(evals, start=1):
        prefix = f"{path.relative_to(ROOT)}: eval #{position}"
        if not isinstance(item, dict):
            raise CheckError(f"{prefix} must be an object")
        eval_id = item.get("id")
        if not isinstance(eval_id, int) or isinstance(eval_id, bool) or eval_id <= 0:
            raise CheckError(f"{prefix} must have a positive integer id")
        if eval_id in seen_ids:
            raise CheckError(f"{prefix} duplicates id {eval_id}")
        seen_ids.add(eval_id)
        for field in ("prompt", "expected_output"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise CheckError(f"{prefix} must have a non-empty {field}")
        if not isinstance(item.get("files"), list):
            raise CheckError(f"{prefix} files must be an array")
        assertions = item.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise CheckError(f"{prefix} assertions must be a non-empty array")
        assertion_names: set[str] = set()
        for assertion_position, assertion in enumerate(assertions, start=1):
            assertion_prefix = (
                f"{prefix}, assertion #{assertion_position}"
            )
            if not isinstance(assertion, dict):
                raise CheckError(f"{assertion_prefix} must be an object")
            for field in ("name", "description"):
                if (
                    not isinstance(assertion.get(field), str)
                    or not assertion[field].strip()
                ):
                    raise CheckError(
                        f"{assertion_prefix} must have a non-empty {field}"
                    )
            if assertion["name"] in assertion_names:
                raise CheckError(
                    f"{assertion_prefix} duplicates name {assertion['name']!r}"
                )
            assertion_names.add(assertion["name"])
    print(
        f"[check] {expected_skill_name} eval catalog",
        flush=True,
    )


def validate_eval_catalogs() -> None:
    catalogs = (
        (ROOT / "evals" / "evals.json", "repo-foundry-ai"),
        (
            ROOT
            / "engineering-execution-plan"
            / "evals"
            / "evals.json",
            "engineering-execution-plan",
        ),
        (
            ROOT / "engineering-research" / "evals" / "evals.json",
            "engineering-research",
        ),
        (
            ROOT / "engineering-benchmark" / "evals" / "evals.json",
            "engineering-benchmark",
        ),
        (
            ROOT / "architecture-design" / "evals" / "evals.json",
            "architecture-design",
        ),
        (
            ROOT / "detailed-design" / "evals" / "evals.json",
            "detailed-design",
        ),
        (
            ROOT / "engineering-design" / "evals" / "evals.json",
            "engineering-design",
        ),
        (
            ROOT / "engineering-case-study" / "evals" / "evals.json",
            "engineering-case-study",
        ),
    )
    for path, expected_skill_name in catalogs:
        validate_eval_catalog(path, expected_skill_name)


def validate_engineering_spec_catalog() -> None:
    bundled = ROOT / "engineering-specs"
    if bundled.exists():
        raise CheckError(
            "Normative Engineering Specs must live in the independent "
            "EngineeringSpecifications repository, not engineering-specs/"
        )
    print("[check] external Engineering Spec ownership", flush=True)


def copy_repository(destination: Path) -> None:
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "*.pyc",
        ),
    )


def validate_generated_indexes() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        copied = Path(temporary) / "repository"
        copy_repository(copied)
        before = {
            path: (copied / path).read_bytes()
            for path in INDEX_PATHS
        }
        run(
            "Research index projection",
            [
                sys.executable,
                "-B",
                str(copied / "engineering-research" / "scripts" / "researchctl.py"),
                "--repo",
                str(copied),
                "reindex",
            ],
            copied,
        )
        run(
            "Execution artifact index projections",
            [
                sys.executable,
                "-B",
                str(
                    copied
                    / "engineering-execution-plan"
                    / "scripts"
                    / "epctl.py"
                ),
                "--repo",
                str(copied),
                "reindex",
            ],
            copied,
        )
        run(
            "Design index projection",
            [
                sys.executable,
                "-B",
                str(copied / "engineering-design" / "scripts" / "designctl.py"),
                "--repo",
                str(copied),
                "reindex",
            ],
            copied,
        )
        changed = [
            path.as_posix()
            for path, content in before.items()
            if (copied / path).read_bytes() != content
        ]
        if changed:
            raise CheckError(
                "Generated indexes are stale; run reindex for: "
                + ", ".join(changed)
            )


def validate_git_whitespace() -> None:
    result = subprocess.run(
        ["git", "hash-object", "-t", "tree", "--stdin"],
        cwd=ROOT,
        input="",
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise CheckError(
            "Unable to compute the Git empty tree for whitespace validation"
        )
    empty_tree = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]+", empty_tree):
        raise CheckError("Git returned an invalid empty-tree object id")
    run(
        "Git tracked-tree whitespace validation",
        ["git", "diff", "--check", empty_tree, "HEAD"],
    )
    run("Git staged whitespace validation", ["git", "diff", "--cached", "--check"])
    run("Git working-tree whitespace validation", ["git", "diff", "--check"])


def main() -> int:
    try:
        validate_skill_packages()
        validate_eval_catalogs()
        validate_engineering_spec_catalog()
        validate_markdown_links()
        run(
            "Architecture Design contract tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "architecture-design/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "Engineering Research tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "engineering-research/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "Engineering Benchmark tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "engineering-benchmark/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "Engineering Design tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "engineering-design/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "Engineering Execution Plan tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "engineering-execution-plan/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "RepoFoundry AI and repository contract tests",
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        run(
            "Engineering Research repository validation",
            [
                sys.executable,
                "-B",
                str(ROOT / "engineering-research" / "scripts" / "researchctl.py"),
                "--repo",
                str(ROOT),
                "validate",
            ],
        )
        run(
            "Engineering Execution Plan repository validation",
            [
                sys.executable,
                "-B",
                str(
                    ROOT
                    / "engineering-execution-plan"
                    / "scripts"
                    / "epctl.py"
                ),
                "--repo",
                str(ROOT),
                "validate",
            ],
        )
        run(
            "Engineering Design repository validation",
            [
                sys.executable,
                "-B",
                str(ROOT / "engineering-design" / "scripts" / "designctl.py"),
                "--repo",
                str(ROOT),
                "validate",
            ],
        )
        validate_generated_indexes()
        if (ROOT / ".git").exists() and shutil.which("git"):
            validate_git_whitespace()
    except (CheckError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"check: {exc}", file=sys.stderr)
        return 1
    print("[check] all integrity checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
