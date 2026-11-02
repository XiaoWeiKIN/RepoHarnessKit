#!/usr/bin/env python3
"""Run RepoFoundry's product-neutral local Engineering Spec activation engine."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


ROUTER_VERSION = 5
PROTOCOL_VERSION = 2
REQUIREMENT_INDEX_SCHEMA_VERSION = 2
ENFORCEMENT_EVIDENCE_SCHEMA_VERSION = 1
HARNESS_PATH = "docs/.engineering/harness.json"
MANIFEST_PATH = "docs/.engineering/specs.json"
LOCK_PATH = "docs/.engineering/specs.lock.json"
INDEX_PATH = "docs/agent-guides/managed/index.md"
REQUIREMENT_INDEX_PATH = "docs/agent-guides/managed/requirements.json"
MAX_JSON_BYTES = 1024 * 1024
MAX_CONTEXT_BYTES = 128 * 1024
DEFAULT_CARD_BUDGET_BYTES = 16 * 1024
DEFAULT_CAPSULE_BUDGET_BYTES = 32 * 1024
MAX_ENTRIES = 256
SPEC_ID_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?"
    r"(?:/[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?)*$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIREMENT_RE = re.compile(
    r"^###\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-[0-9]{3})\s+[—-]\s+",
    re.MULTILINE,
)
REQUIREMENT_ID_RE = re.compile(
    r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-[0-9]{3}$"
)
REQUIREMENT_ID_TOKEN_RE = re.compile(
    r"`([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-[0-9]{3})`"
)
REQUIREMENT_ACTIVATION_PREFIX = "**Activation:** "
REQUIREMENT_DEPENDENCIES_PREFIX = "**Context dependencies:** "
REQUIREMENT_AUTOMATED_ENFORCEMENT_MARKER = "**Automated enforcement:**"
REQUIREMENT_AUTOMATED_ENFORCEMENT_PREFIX = (
    REQUIREMENT_AUTOMATED_ENFORCEMENT_MARKER + " "
)
AUTOMATED_ENFORCEMENT_LEVELS = frozenset(
    {"Advisory", "Warning", "Blocking"}
)
LEGACY_AUTOMATED_ENFORCEMENT_LEVEL = "Advisory"
REPO_FOUNDRY_EFFECTIVE_AUTOMATED_ENFORCEMENT = "Advisory"
BLOCKING_OBLIGATION_RE = re.compile(r"\*\*MUST(?: NOT)?\*\*")
WARNING_OBLIGATION_RE = re.compile(
    r"\*\*(?:MUST(?: NOT)?|SHOULD(?: NOT)?)\*\*"
)
ADAPTER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
HANDOFF_LABELS = (
    "Activated specifications:",
    "Activated requirements:",
    "Verification:",
    "Exceptions:",
    "Compatibility or migration:",
)
DISALLOWED_BROAD_GLOBS = frozenset({"*", "**", "**/*"})
NORMALIZED_EVENTS = frozenset(
    {
        "session_start",
        "subagent_start",
        "context_resume",
        "before_mutation",
        "stop",
    }
)
TOOL_CATEGORIES = frozenset({"read", "file_write", "command_write"})
GOVERNANCE_PROFILES = frozenset({"adaptive", "strict"})
GOVERNANCE_MODES = ("explore", "build", "governed")
GOVERNANCE_MODE_RANK = {
    mode: index for index, mode in enumerate(GOVERNANCE_MODES)
}
GOVERNANCE_POLICY_SCHEMA = 1


class RouterError(RuntimeError):
    """Raised when local routing state violates its boundary contract."""


SESSION_CONTEXT_BUDGET_BYTES = 8 * 1024
MAX_SESSION_CONTEXT_BUDGET_BYTES = 128 * 1024


@dataclass(frozen=True)
class SessionContextSection:
    """Non-normative context offered for one agent session."""

    id: str
    priority: int
    content: str
    source: str
    mandatory: bool = False


def plan_session_context(
    sections: Iterable[SessionContextSection],
    budget_bytes: int = SESSION_CONTEXT_BUDGET_BYTES,
) -> dict[str, object]:
    """Select bounded session context without truncating any section.

    Reserve mandatory content and the shorter of each optional section or its
    source pointer first. A large early section must not hide later sources.
    This planner never handles the normative Engineering Spec capsule.
    """
    if (
        type(budget_bytes) is not int
        or budget_bytes < 1
        or budget_bytes > MAX_SESSION_CONTEXT_BUDGET_BYTES
    ):
        raise RouterError("ROUTER_SESSION_CONTEXT_BUDGET_INVALID")
    values = tuple(sections)
    seen: set[str] = set()
    sources: set[str] = set()
    for section in values:
        if not isinstance(section, SessionContextSection):
            raise RouterError("ROUTER_SESSION_CONTEXT_SECTION_INVALID")
        if (
            not isinstance(section.id, str)
            or not re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", section.id)
            or section.id in seen
            or type(section.priority) is not int
            or section.priority < 0
            or type(section.mandatory) is not bool
            or not isinstance(section.content, str)
            or not section.content.strip()
            or not isinstance(section.source, str)
            or not section.source.strip()
            or len(section.source) > 512
            or "\n" in section.source
            or "\r" in section.source
        ):
            raise RouterError("ROUTER_SESSION_CONTEXT_SECTION_INVALID")
        if section.source in sources:
            raise RouterError("ROUTER_SESSION_CONTEXT_SOURCE_DUPLICATE")
        seen.add(section.id)
        sources.add(section.source)
    ordered = tuple(sorted(values, key=lambda section: (section.priority, section.id)))

    def pointer(section: SessionContextSection) -> str:
        return f"[ContextRef:{section.id}] {section.source}"

    # Two newlines separate adjacent sections, including references.
    baseline_bytes = 2 * max(0, len(ordered) - 1) + sum(
        min(
            len(section.content.encode("utf-8")),
            len(pointer(section).encode("utf-8")),
        )
        if not section.mandatory
        else len(section.content.encode("utf-8"))
        for section in ordered
    )
    if baseline_bytes > budget_bytes:
        raise RouterError(
            "ROUTER_SESSION_CONTEXT_BUDGET_EXCEEDED: "
            f"mandatory content and source pointers need {baseline_bytes} bytes; "
            f"budget is {budget_bytes} bytes"
        )

    remaining = budget_bytes - baseline_bytes
    parts: list[str] = []
    selections: list[dict[str, object]] = []
    for section in ordered:
        short = pointer(section)
        content_size = len(section.content.encode("utf-8"))
        pointer_size = len(short.encode("utf-8"))
        extra = max(0, content_size - pointer_size)
        include = section.mandatory or extra <= remaining
        chosen = section.content if include else short
        if not section.mandatory and include:
            remaining -= extra
        parts.append(chosen)
        selections.append(
            {
                "id": section.id,
                "source": section.source,
                "selection": "content" if include else "reference",
                "bytes": len(chosen.encode("utf-8")),
            }
        )
    text = "\n\n".join(parts)
    used_bytes = len(text.encode("utf-8"))
    assert used_bytes <= budget_bytes
    return {
        "text": text,
        "budget_bytes": budget_bytes,
        "used_bytes": used_bytes,
        "selections": selections,
    }


@dataclass(frozen=True)
class SpecEntry:
    key: str
    version: str
    path: str
    sha256: str | None
    requires: tuple[str, ...]
    applies_to: tuple[str, ...]
    description: str
    project_owned: bool


@dataclass(frozen=True)
class SourceRange:
    start_byte: int
    end_byte: int
    sha256: str


@dataclass(frozen=True)
class RequirementRecord:
    requirement_id: str
    title: str
    activation: str
    dependencies: tuple[str, ...]
    automated_enforcement: str
    automated_enforcement_source: str
    spec_id: str
    block_bytes: int
    block: SourceRange
    verification: SourceRange


@dataclass(frozen=True)
class RequirementSpec:
    spec_id: str
    version: str
    path: str
    sha256: str
    mode: str
    title: str
    frame_sections: tuple[str, ...]
    sections: dict[str, SourceRange]
    requirements: tuple[RequirementRecord, ...]


@dataclass(frozen=True)
class RequirementIndex:
    specs: tuple[RequirementSpec, ...]
    by_spec: dict[str, RequirementSpec]
    by_requirement: dict[str, RequirementRecord]


@dataclass(frozen=True)
class SpecState:
    catalog_id: str
    catalog_version: str
    catalog_digest: str
    revision: str
    entries: tuple[SpecEntry, ...]
    by_key: dict[str, SpecEntry]
    requirement_index: RequirementIndex


def _json_output(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bytes(path: Path, label: str, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RouterError(f"{label}: expected a non-symlink regular file: {path}")
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise RouterError(f"{label}: {path}: {exc}") from exc
    if len(value) > maximum:
        raise RouterError(f"{label}: {path}: exceeds {maximum} bytes")
    return value


def _load_json(path: Path, label: str) -> dict[str, object]:
    raw = _read_bytes(path, label, MAX_JSON_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RouterError(f"{label}: {path}: invalid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RouterError(f"{label}: {path}: expected an object")
    return value


def _governance_profile(root: Path) -> str:
    harness = _load_json(root / HARNESS_PATH, "ROUTER_HARNESS_INVALID")
    governance = harness.get("governance")
    if governance is None:
        return "strict"
    if not isinstance(governance, dict) or set(governance) != {
        "policy_schema",
        "profile",
    }:
        raise RouterError("ROUTER_HARNESS_INVALID.governance")
    if governance.get("policy_schema") != GOVERNANCE_POLICY_SCHEMA:
        raise RouterError(
            "ROUTER_GOVERNANCE_POLICY_UNSUPPORTED: expected policy_schema "
            f"{GOVERNANCE_POLICY_SCHEMA}"
        )
    profile = governance.get("profile")
    if profile not in GOVERNANCE_PROFILES:
        raise RouterError(
            f"ROUTER_GOVERNANCE_PROFILE_UNSUPPORTED: {profile!r}"
        )
    return str(profile)


def _initial_governance(profile: str) -> tuple[str, list[dict[str, str]]]:
    if profile == "strict":
        return "governed", [
            {
                "mode": "governed",
                "reason": "repository strict profile requires Governed mode",
            }
        ]
    return "explore", [
        {
            "mode": "explore",
            "reason": "repository adaptive profile starts in Explore mode",
        }
    ]


def _governance(runtime: dict[str, object]) -> tuple[str, str, list[dict[str, str]]]:
    profile = runtime.get("governance_profile")
    mode = runtime.get("governance_mode")
    reasons = runtime.get("governance_reasons")
    if profile not in GOVERNANCE_PROFILES:
        raise RouterError("ROUTER_RUNTIME_INVALID.governance_profile")
    if mode not in GOVERNANCE_MODE_RANK:
        raise RouterError("ROUTER_RUNTIME_INVALID.governance_mode")
    if not isinstance(reasons, list) or not reasons:
        raise RouterError("ROUTER_RUNTIME_INVALID.governance_reasons")
    normalized: list[dict[str, str]] = []
    for item in reasons:
        if (
            not isinstance(item, dict)
            or set(item) != {"mode", "reason"}
            or item.get("mode") not in GOVERNANCE_MODE_RANK
            or not isinstance(item.get("reason"), str)
            or not str(item["reason"]).strip()
        ):
            raise RouterError("ROUTER_RUNTIME_INVALID.governance_reasons entry")
        normalized.append(
            {"mode": str(item["mode"]), "reason": str(item["reason"])}
        )
    if profile == "strict" and mode != "governed":
        raise RouterError("ROUTER_RUNTIME_INVALID.strict mode must be governed")
    return str(profile), str(mode), normalized


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if check:
            raise RouterError(f"ROUTER_GIT_FAILED: git {' '.join(arguments)}: {exc}") from exc
        return ""
    if result.returncode:
        if check:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RouterError(
                f"ROUTER_GIT_FAILED: git {' '.join(arguments)}: {detail}"
            )
        return ""
    return result.stdout


def repository_root(value: str | Path) -> Path:
    start = Path(value).expanduser().resolve()
    if start.is_file():
        start = start.parent
    output = _git(start, "rev-parse", "--show-toplevel", check=False).strip()
    if output:
        return Path(output).resolve()
    current = start
    while True:
        if (current / MANIFEST_PATH).is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RouterError(f"ROUTER_REPOSITORY_NOT_FOUND: {start}")


def _safe_relative(value: object, label: str, *, allow_glob: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 32 for character in value)
    ):
        raise RouterError(f"{label}: expected a non-empty string")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RouterError(f"{label}: path must be repository-relative: {value!r}")
    if not allow_glob and any(char in normalized for char in "*?["):
        raise RouterError(f"{label}: globs are not allowed: {value!r}")
    return path.as_posix()


def _resolve_regular(root: Path, relative: str, label: str) -> Path:
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise RouterError(f"{label}: symbolic links are not supported: {relative}")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RouterError(f"{label}: path escapes repository: {relative}") from exc
    if not path.is_file():
        raise RouterError(f"{label}: file is missing: {relative}")
    return path


def _strings(value: object, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RouterError(f"{label}: expected an array of strings")
    result = tuple(value)
    if nonempty and not result:
        raise RouterError(f"{label}: expected at least one entry")
    if len(result) != len(set(result)):
        raise RouterError(f"{label}: duplicate entries")
    return result


def _source_range(
    value: object,
    label: str,
    content: bytes,
) -> SourceRange:
    if not isinstance(value, dict) or set(value) != {
        "start_byte",
        "end_byte",
        "sha256",
    }:
        raise RouterError(f"{label}: expected an exact source range")
    start = value.get("start_byte")
    end = value.get("end_byte")
    digest = value.get("sha256")
    if type(start) is not int or type(end) is not int:
        raise RouterError(f"{label}: byte boundaries must be integers")
    if start < 0 or end <= start or end > len(content):
        raise RouterError(f"{label}: byte boundaries are outside the source")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise RouterError(f"{label}.sha256: expected lowercase SHA-256")
    actual = _sha256(content[start:end])
    if actual != digest:
        raise RouterError(
            f"ROUTER_REQUIREMENT_INDEX_RANGE_DRIFT: {label}: "
            f"expected {digest}; got {actual}"
        )
    return SourceRange(start_byte=start, end_byte=end, sha256=digest)


def _routing_metadata_from_block(
    block_text: str,
    label: str,
) -> tuple[str, tuple[str, ...], str, str]:
    lines = block_text.splitlines()
    if len(lines) < 6 or lines[1] != "":
        raise RouterError(f"{label}: routing metadata is not immediate")
    cursor = 2
    if not lines[cursor].startswith(REQUIREMENT_ACTIVATION_PREFIX):
        raise RouterError(f"{label}: Activation metadata is missing")
    activation_parts = [
        lines[cursor][len(REQUIREMENT_ACTIVATION_PREFIX) :].strip()
    ]
    cursor += 1
    while cursor < len(lines) and lines[cursor] != "":
        activation_parts.append(lines[cursor].strip())
        cursor += 1
    activation = " ".join(part for part in activation_parts if part)
    cursor += 1
    if (
        cursor >= len(lines)
        or not lines[cursor].startswith(REQUIREMENT_DEPENDENCIES_PREFIX)
    ):
        raise RouterError(f"{label}: Context dependencies metadata is missing")
    dependency_parts = [
        lines[cursor][len(REQUIREMENT_DEPENDENCIES_PREFIX) :].strip()
    ]
    cursor += 1
    while cursor < len(lines) and lines[cursor] != "":
        dependency_parts.append(lines[cursor].strip())
        cursor += 1
    dependency_text = " ".join(
        part for part in dependency_parts if part
    )
    if dependency_text == "None":
        dependencies: tuple[str, ...] = ()
    else:
        values = [item.strip() for item in dependency_text.split(",")]
        dependencies = tuple(
            match.group(1)
            for item in values
            if (match := REQUIREMENT_ID_TOKEN_RE.fullmatch(item)) is not None
        )
        if len(dependencies) != len(values):
            raise RouterError(f"{label}: Context dependencies are malformed")
    if cursor >= len(lines) or lines[cursor] != "":
        raise RouterError(
            f"{label}: Context dependencies must be one Markdown paragraph"
        )
    legacy_metadata_end = cursor
    cursor += 1
    if (
        cursor < len(lines)
        and lines[cursor].startswith(
            REQUIREMENT_AUTOMATED_ENFORCEMENT_PREFIX
        )
    ):
        automated_enforcement = lines[cursor][
            len(REQUIREMENT_AUTOMATED_ENFORCEMENT_PREFIX) :
        ].strip()
        if automated_enforcement not in AUTOMATED_ENFORCEMENT_LEVELS:
            raise RouterError(
                f"{label}: Automated enforcement is unsupported"
            )
        if lines[cursor] != (
            REQUIREMENT_AUTOMATED_ENFORCEMENT_PREFIX
            + automated_enforcement
        ):
            raise RouterError(
                f"{label}: Automated enforcement must be one scalar line"
            )
        automated_enforcement_source = "declared"
        cursor += 1
        if cursor >= len(lines) or lines[cursor] != "":
            raise RouterError(
                f"{label}: Automated enforcement must be followed by one "
                "blank line"
            )
        metadata_end = cursor
    else:
        automated_enforcement = LEGACY_AUTOMATED_ENFORCEMENT_LEVEL
        automated_enforcement_source = "legacy_default"
        metadata_end = legacy_metadata_end
    marker_count = block_text.count(
        REQUIREMENT_AUTOMATED_ENFORCEMENT_MARKER
    )
    expected_marker_count = (
        1 if automated_enforcement_source == "declared" else 0
    )
    if marker_count != expected_marker_count:
        raise RouterError(
            f"{label}: Automated enforcement must immediately follow "
            "Context dependencies as one scalar marker"
        )
    body = "\n".join(lines[metadata_end:])
    if (
        automated_enforcement == "Blocking"
        and BLOCKING_OBLIGATION_RE.search(body) is None
    ):
        raise RouterError(
            f"{label}: Blocking requires a MUST or MUST NOT obligation"
        )
    if (
        automated_enforcement == "Warning"
        and WARNING_OBLIGATION_RE.search(body) is None
    ):
        raise RouterError(
            f"{label}: Warning requires a MUST, MUST NOT, SHOULD, or "
            "SHOULD NOT obligation"
        )
    return (
        activation,
        dependencies,
        automated_enforcement,
        automated_enforcement_source,
    )


def _legacy_requirement_index(
    root: Path,
    entries: tuple[SpecEntry, ...],
) -> RequirementIndex:
    specs: list[RequirementSpec] = []
    for entry in entries:
        content = _read_bytes(
            _resolve_regular(root, entry.path, "ROUTER_SPEC_FILE_INVALID"),
            "ROUTER_SPEC_FILE_INVALID",
            MAX_CONTEXT_BYTES,
        )
        specs.append(
            RequirementSpec(
                spec_id=entry.key,
                version=entry.version,
                path=entry.path,
                sha256=entry.sha256 or _sha256(content),
                mode="whole-spec",
                title=entry.key,
                frame_sections=(),
                sections={},
                requirements=(),
            )
        )
    return RequirementIndex(
        specs=tuple(specs),
        by_spec={item.spec_id: item for item in specs},
        by_requirement={},
    )


def _load_requirement_index(
    root: Path,
    entries: tuple[SpecEntry, ...],
    *,
    catalog_id: str,
    catalog_version: str,
    catalog_digest: str,
    revision: str,
) -> RequirementIndex:
    path = root / REQUIREMENT_INDEX_PATH
    if not path.exists():
        return _legacy_requirement_index(root, entries)
    data = _load_json(path, "ROUTER_REQUIREMENT_INDEX_INVALID")
    if set(data) != {"schema_version", "owner", "catalog", "specs"}:
        raise RouterError(
            "ROUTER_REQUIREMENT_INDEX_INVALID: unexpected top-level shape"
        )
    requirement_index_schema = data.get("schema_version")
    if requirement_index_schema not in {1, REQUIREMENT_INDEX_SCHEMA_VERSION}:
        raise RouterError(
            "ROUTER_REQUIREMENT_INDEX_UNSUPPORTED: expected schema_version "
            f"1 or {REQUIREMENT_INDEX_SCHEMA_VERSION}"
        )
    if not isinstance(data.get("owner"), str) or not data["owner"]:
        raise RouterError("ROUTER_REQUIREMENT_INDEX_INVALID.owner")
    raw_catalog = data.get("catalog")
    expected_catalog = {
        "catalog_id": catalog_id,
        "catalog_version": catalog_version,
        "sha256": catalog_digest,
        "resolved_revision": revision,
    }
    if raw_catalog != expected_catalog:
        raise RouterError(
            "ROUTER_REQUIREMENT_INDEX_CATALOG_DRIFT: regenerate with spec sync"
        )
    raw_specs = data.get("specs")
    if not isinstance(raw_specs, list) or len(raw_specs) != len(entries):
        raise RouterError(
            "ROUTER_REQUIREMENT_INDEX_INVALID.specs: installed set mismatch"
        )
    expected_entries = {entry.key: entry for entry in entries}
    specs: list[RequirementSpec] = []
    by_requirement: dict[str, RequirementRecord] = {}
    for index, raw in enumerate(raw_specs):
        label = f"ROUTER_REQUIREMENT_INDEX_INVALID.specs[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "id",
            "version",
            "path",
            "sha256",
            "requires",
            "project_owned",
            "mode",
            "title",
            "frame_sections",
            "sections",
            "requirements",
        }:
            raise RouterError(f"{label}: unexpected shape")
        spec_id = raw.get("id")
        if not isinstance(spec_id, str) or spec_id not in expected_entries:
            raise RouterError(f"{label}.id: unknown Spec")
        entry = expected_entries[spec_id]
        if raw.get("version") != entry.version or raw.get("path") != entry.path:
            raise RouterError(f"{label}: version or path drift")
        if raw.get("requires") != list(entry.requires):
            raise RouterError(f"{label}.requires: lock drift")
        if raw.get("project_owned") is not entry.project_owned:
            raise RouterError(f"{label}.project_owned: lock drift")
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise RouterError(f"{label}.sha256: invalid")
        content = _read_bytes(
            _resolve_regular(root, entry.path, "ROUTER_SPEC_FILE_INVALID"),
            "ROUTER_SPEC_FILE_INVALID",
            MAX_CONTEXT_BYTES,
        )
        if _sha256(content) != digest or (
            entry.sha256 is not None and entry.sha256 != digest
        ):
            raise RouterError(
                f"ROUTER_REQUIREMENT_INDEX_SOURCE_DRIFT: {entry.path}"
            )
        mode = raw.get("mode")
        if mode not in {"requirements", "whole-spec"}:
            raise RouterError(f"{label}.mode: unsupported")
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            raise RouterError(f"{label}.title: expected string")
        frame_sections = _strings(
            raw.get("frame_sections"),
            f"{label}.frame_sections",
        )
        raw_sections = raw.get("sections")
        if not isinstance(raw_sections, list):
            raise RouterError(f"{label}.sections: expected array")
        sections: dict[str, SourceRange] = {}
        for section_index, section_raw in enumerate(raw_sections):
            section_label = f"{label}.sections[{section_index}]"
            if not isinstance(section_raw, dict) or set(section_raw) != {
                "name",
                "start_byte",
                "end_byte",
                "sha256",
            }:
                raise RouterError(f"{section_label}: unexpected shape")
            name = section_raw.get("name")
            if not isinstance(name, str) or not name or name in sections:
                raise RouterError(f"{section_label}.name: invalid or duplicate")
            sections[name] = _source_range(
                {key: section_raw[key] for key in ("start_byte", "end_byte", "sha256")},
                section_label,
                content,
            )
        if any(name not in sections for name in frame_sections):
            raise RouterError(f"{label}.frame_sections: missing source range")
        raw_requirements = raw.get("requirements")
        if not isinstance(raw_requirements, list):
            raise RouterError(f"{label}.requirements: expected array")
        records: list[RequirementRecord] = []
        for requirement_index, requirement_raw in enumerate(raw_requirements):
            requirement_label = (
                f"{label}.requirements[{requirement_index}]"
            )
            expected_requirement_keys = {
                "id",
                "title",
                "activation",
                "context_dependencies",
                "block_bytes",
                "start_byte",
                "end_byte",
                "sha256",
                "verification",
            }
            if requirement_index_schema == REQUIREMENT_INDEX_SCHEMA_VERSION:
                expected_requirement_keys.update(
                    {
                        "automated_enforcement",
                        "automated_enforcement_source",
                    }
                )
            if (
                not isinstance(requirement_raw, dict)
                or set(requirement_raw) != expected_requirement_keys
            ):
                raise RouterError(f"{requirement_label}: unexpected shape")
            requirement_id = requirement_raw.get("id")
            if (
                not isinstance(requirement_id, str)
                or not REQUIREMENT_ID_RE.fullmatch(requirement_id)
                or requirement_id in by_requirement
            ):
                raise RouterError(f"{requirement_label}.id: invalid or duplicate")
            requirement_title = requirement_raw.get("title")
            activation = requirement_raw.get("activation")
            if not isinstance(requirement_title, str) or not requirement_title:
                raise RouterError(f"{requirement_label}.title: invalid")
            if (
                not isinstance(activation, str)
                or not activation.startswith("Load when ")
                or len(activation) > 180
            ):
                raise RouterError(f"{requirement_label}.activation: invalid")
            dependencies = _strings(
                requirement_raw.get("context_dependencies"),
                f"{requirement_label}.context_dependencies",
            )
            block = _source_range(
                {
                    key: requirement_raw[key]
                    for key in ("start_byte", "end_byte", "sha256")
                },
                requirement_label,
                content,
            )
            block_bytes = requirement_raw.get("block_bytes")
            if type(block_bytes) is not int or block_bytes != block.end_byte - block.start_byte:
                raise RouterError(f"{requirement_label}.block_bytes: invalid")
            verification = _source_range(
                requirement_raw.get("verification"),
                f"{requirement_label}.verification",
                content,
            )
            block_text = content[block.start_byte:block.end_byte].decode("utf-8")
            if not block_text.startswith(f"### {requirement_id} "):
                raise RouterError(f"{requirement_label}: block heading drift")
            heading_match = re.match(
                rf"^### {re.escape(requirement_id)} [—-] (\S[^\r\n]*)",
                block_text,
            )
            if (
                heading_match is None
                or heading_match.group(1) != requirement_title
            ):
                raise RouterError(f"{requirement_label}: title drift")
            (
                source_activation,
                source_dependencies,
                source_automated_enforcement,
                source_automated_enforcement_origin,
            ) = _routing_metadata_from_block(block_text, requirement_label)
            if (
                source_activation != activation
                or source_dependencies != dependencies
            ):
                raise RouterError(
                    f"ROUTER_REQUIREMENT_INDEX_METADATA_DRIFT: "
                    f"{requirement_id}"
                )
            if requirement_index_schema == REQUIREMENT_INDEX_SCHEMA_VERSION:
                automated_enforcement = requirement_raw.get(
                    "automated_enforcement"
                )
                automated_enforcement_source = requirement_raw.get(
                    "automated_enforcement_source"
                )
                if (
                    automated_enforcement != source_automated_enforcement
                    or automated_enforcement_source
                    != source_automated_enforcement_origin
                ):
                    raise RouterError(
                        "ROUTER_REQUIREMENT_INDEX_METADATA_DRIFT: "
                        f"{requirement_id}: Automated enforcement"
                    )
            else:
                automated_enforcement = source_automated_enforcement
                automated_enforcement_source = (
                    source_automated_enforcement_origin
                )
            row_text = content[
                verification.start_byte:verification.end_byte
            ].decode("utf-8")
            if not row_text.startswith(f"| `{requirement_id}` |"):
                raise RouterError(f"{requirement_label}: Verification row drift")
            record = RequirementRecord(
                requirement_id=requirement_id,
                title=requirement_title,
                activation=activation,
                dependencies=dependencies,
                automated_enforcement=automated_enforcement,
                automated_enforcement_source=(
                    automated_enforcement_source
                ),
                spec_id=spec_id,
                block_bytes=block_bytes,
                block=block,
                verification=verification,
            )
            records.append(record)
            by_requirement[requirement_id] = record
        if mode == "requirements" and not records:
            raise RouterError(f"{label}: requirements mode is empty")
        if mode == "whole-spec" and (records or sections or frame_sections):
            raise RouterError(f"{label}: whole-spec mode carries partial metadata")
        specs.append(
            RequirementSpec(
                spec_id=spec_id,
                version=entry.version,
                path=entry.path,
                sha256=digest,
                mode=mode,
                title=title,
                frame_sections=frame_sections,
                sections=sections,
                requirements=tuple(records),
            )
        )
    if [item.spec_id for item in specs] != [item.key for item in entries]:
        raise RouterError(
            "ROUTER_REQUIREMENT_INDEX_ORDER_DRIFT: regenerate with spec sync"
        )
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(requirement_id: str) -> None:
        if requirement_id in visiting:
            raise RouterError(
                "ROUTER_REQUIREMENT_DEPENDENCY_CYCLE: "
                + " -> ".join((*visiting, requirement_id))
            )
        if requirement_id in visited:
            return
        record = by_requirement.get(requirement_id)
        if record is None:
            raise RouterError(
                f"ROUTER_REQUIREMENT_DEPENDENCY_UNKNOWN: {requirement_id}"
            )
        visiting.append(requirement_id)
        for dependency in record.dependencies:
            visit(dependency)
        visiting.pop()
        visited.add(requirement_id)

    for requirement_id in sorted(by_requirement):
        visit(requirement_id)
    return RequirementIndex(
        specs=tuple(specs),
        by_spec={item.spec_id: item for item in specs},
        by_requirement=by_requirement,
    )


def load_state(root: Path) -> SpecState:
    manifest = _load_json(root / MANIFEST_PATH, "ROUTER_MANIFEST_INVALID")
    lock = _load_json(root / LOCK_PATH, "ROUTER_LOCK_INVALID")
    project_specs = manifest.get("project_specs")
    raw_specs = lock.get("specs")
    catalog = lock.get("catalog")
    if not isinstance(project_specs, list):
        raise RouterError("ROUTER_MANIFEST_INVALID.project_specs: expected an array")
    if not isinstance(raw_specs, list) or not raw_specs or len(raw_specs) > MAX_ENTRIES:
        raise RouterError("ROUTER_LOCK_INVALID.specs: expected a bounded non-empty array")
    if not isinstance(catalog, dict):
        raise RouterError("ROUTER_LOCK_INVALID.catalog: expected an object")
    for field in (
        "catalog_id",
        "catalog_version",
        "sha256",
        "resolved_revision",
    ):
        if not isinstance(catalog.get(field), str) or not catalog[field]:
            raise RouterError(f"ROUTER_LOCK_INVALID.catalog.{field}: expected string")
    if not SHA256_RE.fullmatch(str(catalog["sha256"])):
        raise RouterError(
            "ROUTER_LOCK_INVALID.catalog.sha256: expected lowercase SHA-256"
        )

    entries: list[SpecEntry] = []
    by_key: dict[str, SpecEntry] = {}
    for index, raw in enumerate(raw_specs):
        label = f"ROUTER_LOCK_INVALID.specs[{index}]"
        if not isinstance(raw, dict):
            raise RouterError(f"{label}: expected an object")
        key = raw.get("id")
        if not isinstance(key, str) or not SPEC_ID_RE.fullmatch(key):
            raise RouterError(f"{label}.id: invalid Spec ID")
        if key in by_key:
            raise RouterError(f"{label}.id: duplicate Spec ID: {key}")
        version = raw.get("version")
        digest = raw.get("sha256")
        if not isinstance(version, str) or not version:
            raise RouterError(f"{label}.version: expected string")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise RouterError(f"{label}.sha256: expected lowercase SHA-256")
        path = _safe_relative(raw.get("installed_path"), f"{label}.installed_path")
        expected = f"docs/agent-guides/managed/{key}.md"
        if path != expected:
            raise RouterError(f"{label}.installed_path: expected {expected}")
        requires = _strings(raw.get("requires"), f"{label}.requires")
        applies_to = _strings(
            raw.get("applies_to"), f"{label}.applies_to", nonempty=True
        )
        description = raw.get("description")
        if not isinstance(description, str) or not description.strip():
            raise RouterError(f"{label}.description: expected non-empty string")
        managed_path = _resolve_regular(root, path, "ROUTER_MANAGED_FILE_INVALID")
        actual = _sha256(_read_bytes(managed_path, "ROUTER_MANAGED_FILE_INVALID", MAX_CONTEXT_BYTES))
        if actual != digest:
            raise RouterError(
                f"ROUTER_MANAGED_CONTENT_DRIFT: {path}: lock {digest}; actual {actual}"
            )
        entry = SpecEntry(
            key=key,
            version=version,
            path=path,
            sha256=digest,
            requires=requires,
            applies_to=applies_to,
            description=description,
            project_owned=False,
        )
        entries.append(entry)
        by_key[key] = entry

    for entry in entries:
        missing = sorted(set(entry.requires) - set(by_key))
        if missing:
            raise RouterError(
                f"ROUTER_DEPENDENCY_MISSING: {entry.key}: {', '.join(missing)}"
            )

    for index, raw in enumerate(project_specs):
        label = f"ROUTER_MANIFEST_INVALID.project_specs[{index}]"
        if not isinstance(raw, dict):
            raise RouterError(f"{label}: expected an object")
        path = _safe_relative(raw.get("path"), f"{label}.path")
        if not path.endswith(".md"):
            raise RouterError(f"{label}.path: expected Markdown")
        _resolve_regular(root, path, "ROUTER_PROJECT_FILE_INVALID")
        key = f"project:{path}"
        if key in by_key:
            raise RouterError(f"{label}.path: duplicate: {path}")
        applies_to = _strings(
            raw.get("applies_to"), f"{label}.applies_to", nonempty=True
        )
        description = raw.get("description")
        if not isinstance(description, str) or not description.strip():
            raise RouterError(f"{label}.description: expected non-empty string")
        entry = SpecEntry(
            key=key,
            version="project",
            path=path,
            sha256=None,
            requires=(),
            applies_to=applies_to,
            description=description,
            project_owned=True,
        )
        entries.append(entry)
        by_key[key] = entry

    ordered_entries = tuple(entries)
    requirement_index = _load_requirement_index(
        root,
        ordered_entries,
        catalog_id=str(catalog["catalog_id"]),
        catalog_version=str(catalog["catalog_version"]),
        catalog_digest=str(catalog["sha256"]),
        revision=str(catalog["resolved_revision"]),
    )
    return SpecState(
        catalog_id=str(catalog["catalog_id"]),
        catalog_version=str(catalog["catalog_version"]),
        catalog_digest=str(catalog["sha256"]),
        revision=str(catalog["resolved_revision"]),
        entries=ordered_entries,
        by_key=by_key,
        requirement_index=requirement_index,
    )


def _matches(path: str, pattern: str) -> bool:
    """Match bounded globs, treating a whole '**' directory as zero or more.

    Keep existing fnmatch behavior for compatibility, but also try omitting
    any complete '**/' path segment. This covers 'dir/**/*.go' matching both
    'dir/file.go' and deeper descendants, not only leading '**/' patterns.
    """
    pending = [tuple(pattern.split("/"))]
    seen: set[tuple[str, ...]] = set()
    while pending:
        parts = pending.pop()
        if parts in seen:
            continue
        seen.add(parts)
        if fnmatch.fnmatchcase(path, "/".join(parts)):
            return True
        for index, part in enumerate(parts):
            if part == "**":
                pending.append(parts[:index] + parts[index + 1:])
    return False


def candidate_entries(state: SpecState, paths: Iterable[str]) -> tuple[SpecEntry, ...]:
    selected_paths = tuple(paths)
    return tuple(
        entry
        for entry in state.entries
        if any(
            _matches(path, scope)
            for path in selected_paths
            for scope in entry.applies_to
        )
    )


def dependency_closure(state: SpecState, keys: Iterable[str]) -> tuple[SpecEntry, ...]:
    result: list[SpecEntry] = []
    done: set[str] = set()
    visiting: list[str] = []

    def visit(key: str) -> None:
        if key in done:
            return
        if key in visiting:
            raise RouterError("ROUTER_DEPENDENCY_CYCLE: " + " -> ".join((*visiting, key)))
        entry = state.by_key.get(key)
        if entry is None:
            raise RouterError(f"ROUTER_SPEC_UNKNOWN: {key}")
        visiting.append(key)
        for dependency in entry.requires:
            visit(dependency)
        visiting.pop()
        done.add(key)
        result.append(entry)

    for key in keys:
        visit(key)
    return tuple(result)


def entry_payload(
    root: Path,
    entry: SpecEntry,
    requirement_index: RequirementIndex | None = None,
) -> dict[str, object]:
    content = _read_bytes(
        _resolve_regular(root, entry.path, "ROUTER_SPEC_FILE_INVALID"),
        "ROUTER_SPEC_FILE_INVALID",
        MAX_CONTEXT_BYTES,
    )
    text = content.decode("utf-8", errors="strict")
    indexed = (
        requirement_index.by_spec.get(entry.key)
        if requirement_index is not None
        else None
    )
    return {
        "id": entry.key,
        "version": entry.version,
        "path": entry.path,
        "sha256": entry.sha256 or _sha256(content),
        "requires": list(entry.requires),
        "applies_to": list(entry.applies_to),
        "description": entry.description,
        "requirements": (
            [item.requirement_id for item in indexed.requirements]
            if indexed is not None
            else sorted(set(REQUIREMENT_RE.findall(text)))
        ),
        "routing_mode": indexed.mode if indexed is not None else "whole-spec",
        "project_owned": entry.project_owned,
    }


def _state_base(root: Path) -> Path:
    git_dir = _git(root, "rev-parse", "--git-dir", check=False).strip()
    if git_dir:
        path = Path(git_dir)
        if not path.is_absolute():
            path = root / path
        return path.resolve() / "repo-foundry" / "spec-activation-v2"
    digest = _sha256(str(root.resolve()).encode("utf-8"))
    return Path(tempfile.gettempdir()) / "repo-foundry-spec-activation-v2" / digest


def _state_path(
    root: Path,
    adapter_id: str,
    session_id: str,
    turn_id: str,
) -> Path:
    digest = _sha256(
        f"{adapter_id}\x00{session_id}\x00{turn_id}".encode("utf-8")
    )
    return _state_base(root) / f"{digest}.json"


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_runtime(
    root: Path,
    adapter_id: str,
    session_id: str,
    turn_id: str,
) -> dict[str, object] | None:
    path = _state_path(root, adapter_id, session_id, turn_id)
    if not path.exists():
        return None
    return _load_json(path, "ROUTER_RUNTIME_INVALID")


def _changed_file_state(root: Path) -> dict[str, str]:
    paths: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "--no-renames", "-z"),
        ("diff", "--cached", "--name-only", "--no-renames", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        output = _git(root, *arguments, check=False)
        paths.update(item for item in output.split("\x00") if item)
    state: dict[str, str] = {}
    for raw in sorted(paths):
        try:
            relative = _safe_relative(raw, "ROUTER_GIT_PATH")
        except RouterError:
            continue
        path = root / relative
        if path.is_symlink():
            state[relative] = "symlink"
        elif path.is_file():
            try:
                state[relative] = _sha256(path.read_bytes())
            except OSError:
                state[relative] = "unreadable"
        else:
            state[relative] = "missing"
    return state


def _baseline(root: Path) -> dict[str, object]:
    return {
        "head": _git(root, "rev-parse", "HEAD", check=False).strip(),
        "worktree": _changed_file_state(root),
    }


def _paths_changed_since(root: Path, baseline: object) -> tuple[str, ...]:
    if not isinstance(baseline, dict):
        raise RouterError("ROUTER_RUNTIME_INVALID.baseline: expected object")
    old_state = baseline.get("worktree")
    if not isinstance(old_state, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in old_state.items()
    ):
        raise RouterError("ROUTER_RUNTIME_INVALID.baseline.worktree: expected string map")
    current = _changed_file_state(root)
    changed = {
        path
        for path in set(old_state) | set(current)
        if old_state.get(path) != current.get(path)
    }
    old_head = baseline.get("head")
    new_head = _git(root, "rev-parse", "HEAD", check=False).strip()
    if isinstance(old_head, str) and old_head and new_head and old_head != new_head:
        output = _git(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            f"{old_head}..{new_head}",
            check=False,
        )
        changed.update(item for item in output.split("\x00") if item)
    return tuple(sorted(changed))


def _initialize_turn(root: Path, payload: dict[str, object]) -> dict[str, object]:
    adapter_id = payload.get("adapter_id")
    session_id = payload.get("session_id")
    turn_id = payload.get("turn_id")
    if not isinstance(adapter_id, str) or not ADAPTER_ID_RE.fullmatch(adapter_id):
        raise RouterError("ROUTER_EVENT_INVALID.adapter_id")
    if not isinstance(session_id, str) or not session_id:
        raise RouterError("ROUTER_EVENT_INVALID.session_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise RouterError("ROUTER_EVENT_INVALID.turn_id")
    prompt = payload.get("prompt", "")
    direct_ep_refs = sorted({
        f"EP-{int(number):03d}" for number in _SESSION_EP_RE.findall(prompt)
    }) if isinstance(prompt, str) else []
    existing = _load_runtime(root, adapter_id, session_id, turn_id)
    if existing is not None:
        if payload.get("event") in {"subagent_start", "context_resume"}:
            prior = existing.get("context_direct_ep_refs", [])
            if not isinstance(prior, list) or any(not isinstance(item, str) for item in prior):
                prior = []
                existing["context_direct_ep_overflow"] = True
            protected = sorted(set(prior) | set(direct_ep_refs))
            existing["context_direct_ep_refs"] = protected[:32]
            existing["context_direct_ep_overflow"] = bool(
                existing.get("context_direct_ep_overflow") or len(protected) > 32
            )
            epoch = existing.get("context_epoch")
            if type(epoch) is not int or epoch < 1:
                raise RouterError("ROUTER_RUNTIME_INVALID.context_epoch")
            existing["context_epoch"] = epoch + 1
            existing["context_injected_epoch"] = None
            activation = existing.get("activation")
            if isinstance(activation, dict):
                activation["context_epoch"] = epoch + 1
            _atomic_json(
                _state_path(root, adapter_id, session_id, turn_id),
                existing,
            )
        return existing
    governance_profile = _governance_profile(root)
    governance_mode, governance_reasons = _initial_governance(
        governance_profile
    )
    ep_refs, adr_refs = _session_requested_refs(payload.get("prompt", ""))
    value: dict[str, object] = {
        "version": ROUTER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "adapter_id": adapter_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "prompt_sha256": _sha256(str(payload.get("prompt", "")).encode("utf-8")),
        "context_ep_ref": ep_refs[0] if ep_refs else None,
        "context_direct_ep_refs": direct_ep_refs[:32],
        "context_direct_ep_overflow": len(direct_ep_refs) > 32,
        "context_adr_refs": adr_refs[:_SESSION_MAX_ADR_LINKS],
        "context_adr_omitted_count": max(0, len(adr_refs) - _SESSION_MAX_ADR_LINKS),
        "baseline": _baseline(root),
        "governance_profile": governance_profile,
        "governance_mode": governance_mode,
        "governance_reasons": governance_reasons,
        "activation": None,
        "context_epoch": 1,
        "context_injected_epoch": None,
    }
    _atomic_json(_state_path(root, adapter_id, session_id, turn_id), value)
    return value


def _normalize_planned_path(root: Path, raw: str) -> str:
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            raw = candidate.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise RouterError(f"ROUTER_PATH_OUTSIDE_REPOSITORY: {candidate}") from exc
    normalized = _safe_relative(raw, "ROUTER_PLANNED_PATH", allow_glob=True)
    if normalized in DISALLOWED_BROAD_GLOBS:
        raise RouterError(
            "ROUTER_PLANNED_PATH_TOO_BROAD: use exact paths or a bounded "
            f"subtree glob instead of {normalized!r}"
        )
    return normalized


def _bounded_budget(value: int, label: str) -> int:
    if type(value) is not int or value < 1 or value > MAX_CONTEXT_BYTES:
        raise RouterError(
            f"{label}: expected 1..{MAX_CONTEXT_BYTES} bytes"
        )
    return value


def requirement_dependency_closure(
    index: RequirementIndex,
    requirement_ids: Iterable[str],
) -> tuple[RequirementRecord, ...]:
    result: list[RequirementRecord] = []
    visited: set[str] = set()
    visiting: list[str] = []

    def visit(requirement_id: str) -> None:
        if requirement_id in visited:
            return
        if requirement_id in visiting:
            raise RouterError(
                "ROUTER_REQUIREMENT_DEPENDENCY_CYCLE: "
                + " -> ".join((*visiting, requirement_id))
            )
        record = index.by_requirement.get(requirement_id)
        if record is None:
            raise RouterError(f"ROUTER_REQUIREMENT_UNKNOWN: {requirement_id}")
        visiting.append(requirement_id)
        for dependency in record.dependencies:
            visit(dependency)
        visiting.pop()
        visited.add(requirement_id)
        result.append(record)

    for requirement_id in requirement_ids:
        visit(requirement_id)
    return tuple(result)


def _enforcement_payload(record: RequirementRecord) -> dict[str, str]:
    return {
        "published": record.automated_enforcement,
        "effective": REPO_FOUNDRY_EFFECTIVE_AUTOMATED_ENFORCEMENT,
        "source": record.automated_enforcement_source,
    }


def _card_payload(record: RequirementRecord) -> dict[str, object]:
    return {
        "id": record.requirement_id,
        "spec_id": record.spec_id,
        "title": record.title,
        "activation": record.activation,
        "context_dependencies": list(record.dependencies),
        "automated_enforcement": _enforcement_payload(record),
        "block_bytes": record.block_bytes,
    }


def _range_payload(source_range: SourceRange) -> dict[str, object]:
    return {
        "start_byte": source_range.start_byte,
        "end_byte": source_range.end_byte,
        "bytes": source_range.end_byte - source_range.start_byte,
        "sha256": source_range.sha256,
    }


def _resolved_payload(
    records: Iterable[RequirementRecord],
    direct_ids: Iterable[str],
    *,
    include_enforcement: bool = True,
) -> list[dict[str, object]]:
    direct = set(direct_ids)
    result: list[dict[str, object]] = []
    for item in records:
        payload: dict[str, object] = {
            "id": item.requirement_id,
            "spec_id": item.spec_id,
            "source": (
                "direct"
                if item.requirement_id in direct
                else "context_dependency"
            ),
            "context_dependencies": list(item.dependencies),
            "block": _range_payload(item.block),
            "verification": _range_payload(item.verification),
        }
        if include_enforcement:
            payload["automated_enforcement"] = _enforcement_payload(item)
        result.append(payload)
    return result


def _direct_payload(
    records: Iterable[RequirementRecord],
    reasons: dict[str, str],
    *,
    include_enforcement: bool = True,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in records:
        payload: dict[str, object] = {
            "id": item.requirement_id,
            "reason": reasons[item.requirement_id],
            "source": "agent",
        }
        if include_enforcement:
            payload["automated_enforcement"] = _enforcement_payload(item)
        result.append(payload)
    return result


def _dependency_edges(
    records: Iterable[RequirementRecord],
) -> list[dict[str, str]]:
    return [
        {"from": item.requirement_id, "to": dependency}
        for item in records
        for dependency in item.dependencies
    ]


def command_requirements(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    state = load_state(root)
    paths = tuple(
        dict.fromkeys(
            _normalize_planned_path(root, value) for value in args.path
        )
    )
    candidates = {entry.key for entry in candidate_entries(state, paths)}
    requested = tuple(dict.fromkeys(args.spec))
    unknown = sorted(set(requested) - set(state.by_key))
    if unknown:
        raise RouterError("ROUTER_SPEC_UNKNOWN: " + ", ".join(unknown))
    irrelevant = sorted(set(requested) - candidates)
    if irrelevant:
        raise RouterError(
            "ROUTER_SPEC_NOT_CANDIDATE: " + ", ".join(irrelevant)
        )
    specs: list[dict[str, object]] = []
    cards: list[dict[str, object]] = []
    for spec_id in requested:
        indexed = state.requirement_index.by_spec[spec_id]
        specs.append(
            {
                "id": spec_id,
                "mode": indexed.mode,
                "requirement_count": len(indexed.requirements),
            }
        )
        cards.extend(_card_payload(item) for item in indexed.requirements)
    card_budget = _bounded_budget(
        args.card_budget_bytes,
        "ROUTER_CARD_BUDGET_INVALID",
    )
    card_bytes = len(
        json.dumps(
            {"specs": specs, "cards": cards},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if card_bytes > card_budget:
        raise RouterError(
            "ROUTER_REQUIREMENT_CARDS_TOO_LARGE: "
            f"{card_bytes} bytes exceeds {card_budget}; narrow applicable Specs"
        )
    _json_output(
        {
            "router_version": ROUTER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "paths": list(paths),
            "applicable_specs": specs,
            "cards": cards,
            "card_bytes": card_bytes,
            "card_budget_bytes": card_budget,
            "next": (
                "Select the smallest complete direct Requirement ID set and "
                "give each ID a task-specific --because reason. Use explicit "
                "--whole-spec for entries in whole-spec mode."
            ),
        }
    )
    return 0


def _because_map(values: Iterable[str]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for raw in values:
        requirement_id, separator, reason = raw.partition("=")
        requirement_id = requirement_id.strip()
        reason = reason.strip()
        if (
            not separator
            or not REQUIREMENT_ID_RE.fullmatch(requirement_id)
            or not reason
        ):
            raise RouterError(
                "ROUTER_REQUIREMENT_REASON_INVALID: use ID=task-specific reason"
            )
        if requirement_id in reasons:
            raise RouterError(
                f"ROUTER_REQUIREMENT_REASON_DUPLICATE: {requirement_id}"
            )
        reasons[requirement_id] = reason
    return reasons


def _supporting_sections(
    values: Iterable[str],
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for raw in values:
        spec_id, separator, heading = raw.partition("::")
        spec_id = spec_id.strip()
        heading = heading.strip()
        if not separator or not spec_id or not heading:
            raise RouterError(
                "ROUTER_SECTION_INVALID: use SPEC_ID::exact H2 heading"
            )
        pair = (spec_id, heading)
        if pair in result:
            raise RouterError(
                f"ROUTER_SECTION_DUPLICATE: {spec_id}::{heading}"
            )
        result.append(pair)
    return tuple(result)


def _verified_spec_content(
    root: Path,
    indexed: RequirementSpec,
) -> bytes:
    content = _read_bytes(
        _resolve_regular(root, indexed.path, "ROUTER_ACTIVATED_FILE_INVALID"),
        "ROUTER_ACTIVATED_FILE_INVALID",
        MAX_CONTEXT_BYTES,
    )
    actual = _sha256(content)
    if actual != indexed.sha256:
        raise RouterError(
            f"ROUTER_MANAGED_CONTENT_DRIFT: {indexed.path}: "
            f"expected {indexed.sha256}; got {actual}"
        )
    return content


def _slice(content: bytes, source_range: SourceRange) -> str:
    value = content[source_range.start_byte:source_range.end_byte]
    if _sha256(value) != source_range.sha256:
        raise RouterError("ROUTER_REQUIREMENT_INDEX_RANGE_DRIFT")
    return value.decode("utf-8", errors="strict")


def compile_context_capsule(
    root: Path,
    state: SpecState,
    direct_ids: tuple[str, ...],
    resolved: tuple[RequirementRecord, ...],
    whole_spec_ids: tuple[str, ...],
    sections: tuple[tuple[str, str], ...],
    budget_bytes: int,
) -> tuple[str, str]:
    direct = set(direct_ids)
    whole = set(whole_spec_ids)
    represented_order: list[str] = []
    for record in resolved:
        if record.spec_id not in represented_order:
            represented_order.append(record.spec_id)
    for spec_id in whole_spec_ids:
        if spec_id not in represented_order:
            represented_order.append(spec_id)
    section_map: dict[str, list[str]] = {}
    for spec_id, heading in sections:
        if spec_id not in represented_order:
            raise RouterError(
                f"ROUTER_SECTION_SPEC_NOT_ACTIVATED: {spec_id}::{heading}"
            )
        section_map.setdefault(spec_id, []).append(heading)
    chunks = [
        "# Engineering Specification Context Capsule\n\n"
        f"Protocol: `{PROTOCOL_VERSION}`\n\n"
        "Normative source text below is exact and digest-verified.\n"
    ]
    records_by_spec: dict[str, list[RequirementRecord]] = {}
    for record in resolved:
        records_by_spec.setdefault(record.spec_id, []).append(record)
    for spec_id in represented_order:
        indexed = state.requirement_index.by_spec[spec_id]
        content = _verified_spec_content(root, indexed)
        if spec_id in whole:
            chunks.append(
                f"\n\n--- BEGIN {spec_id} ({indexed.path}) [whole-spec] ---\n"
                + content.decode("utf-8", errors="strict")
                + f"\n--- END {spec_id} [whole-spec] ---"
            )
            continue
        chunks.append(
            f"\n\n## Specification: {indexed.title}\n\n"
            f"- Catalog ID: `{spec_id}`\n"
            f"- Version: `{indexed.version}`\n"
            f"- Source: `{indexed.path}`\n"
            f"- SHA-256: `{indexed.sha256}`\n"
        )
        for heading in indexed.frame_sections:
            chunks.append("\n" + _slice(content, indexed.sections[heading]))
        for record in sorted(
            records_by_spec.get(spec_id, []),
            key=lambda item: item.block.start_byte,
        ):
            source = "direct" if record.requirement_id in direct else "dependency"
            chunks.append(
                f"\n<!-- Requirement source: {source} -->\n"
                + _slice(content, record.block)
            )
        if records_by_spec.get(spec_id):
            chunks.append("\n### Selected Verification rows\n\n")
            for record in sorted(
                records_by_spec[spec_id],
                key=lambda item: item.verification.start_byte,
            ):
                chunks.append(_slice(content, record.verification) + "\n")
        for heading in section_map.get(spec_id, []):
            if heading in indexed.frame_sections or heading in {
                "Requirements",
                "Verification",
            }:
                raise RouterError(
                    f"ROUTER_SECTION_REDUNDANT_OR_UNSAFE: {spec_id}::{heading}"
                )
            source_range = indexed.sections.get(heading)
            if source_range is None:
                raise RouterError(
                    f"ROUTER_SECTION_UNKNOWN: {spec_id}::{heading}"
                )
            chunks.append("\n" + _slice(content, source_range))
    capsule = "".join(chunks)
    size = len(capsule.encode("utf-8"))
    if size > budget_bytes:
        requirement_costs = ",".join(
            f"{record.requirement_id}:"
            f"{record.block.end_byte - record.block.start_byte}+"
            f"{record.verification.end_byte - record.verification.start_byte}"
            for record in resolved
        ) or "none"
        frame_cost_items: list[str] = []
        for spec_id in represented_order:
            if spec_id in whole:
                continue
            indexed = state.requirement_index.by_spec[spec_id]
            frame_bytes = sum(
                indexed.sections[heading].end_byte
                - indexed.sections[heading].start_byte
                for heading in indexed.frame_sections
            )
            frame_cost_items.append(f"{spec_id}:{frame_bytes}")
        frame_costs = ",".join(frame_cost_items) or "none"
        whole_costs = ",".join(
            f"{spec_id}:"
            f"{len(_verified_spec_content(root, state.requirement_index.by_spec[spec_id]))}"
            for spec_id in represented_order
            if spec_id in whole
        ) or "none"
        raise RouterError(
            "ROUTER_CONTEXT_BUDGET_EXCEEDED: "
            f"capsule is {size} bytes; budget is {budget_bytes}; "
            f"direct={','.join(direct_ids) or 'none'}; "
            "resolved="
            f"{','.join(item.requirement_id for item in resolved) or 'none'}; "
            f"requirement_bytes(block+verification)={requirement_costs}; "
            f"frame_bytes={frame_costs}; whole_spec_bytes={whole_costs}; "
            "narrow Requirements, remove supporting sections, partition the "
            "task, or explicitly raise the reviewed budget with a reason"
        )
    mode = (
        "mixed"
        if whole and resolved
        else "whole-spec"
        if whole
        else "requirements"
    )
    return capsule, mode


def command_candidates(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    state = load_state(root)
    paths = tuple(_normalize_planned_path(root, value) for value in args.path)
    candidates = candidate_entries(state, paths)
    _json_output(
        {
            "router_version": ROUTER_VERSION,
            "catalog": {
                "id": state.catalog_id,
                "version": state.catalog_version,
                "revision": state.revision,
            },
            "paths": list(paths),
            "candidates": [
                entry_payload(root, item, state.requirement_index)
                for item in candidates
            ],
            "next": (
                "Read each candidate Applicability section, record applicable "
                "Spec IDs, then run requirements for bounded cards."
            ),
        }
    )
    return 0


def command_begin(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _initialize_turn(
        root,
        {
            "adapter_id": args.adapter_id,
            "session_id": args.session_id,
            "turn_id": args.turn_id,
            "prompt": args.prompt or "",
        },
    )
    _json_output(
        {
            "router_version": ROUTER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "adapter_id": runtime["adapter_id"],
            "session_id": runtime["session_id"],
            "turn_id": runtime["turn_id"],
            "governance_profile": runtime["governance_profile"],
            "governance_mode": runtime["governance_mode"],
            "governance_reasons": runtime["governance_reasons"],
            "initialized": True,
            "next": (
                "Explore bounded reversible work, or run classify to promote "
                "before crossing a Build or Governed trigger. Build and "
                "Governed require candidate review, exact Requirement cards, "
                "and a Spec activation decision before mutation."
            ),
        }
    )
    return 0


def command_classify(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root,
        args.adapter_id,
        args.session_id,
        args.turn_id,
    )
    if runtime is None:
        raise RouterError(
            "ROUTER_TURN_NOT_INITIALIZED: run begin before classification"
        )
    profile, current_mode, reasons = _governance(runtime)
    target_mode = args.mode
    if target_mode not in GOVERNANCE_MODE_RANK:
        raise RouterError(
            f"ROUTER_GOVERNANCE_MODE_UNSUPPORTED: {target_mode!r}"
        )
    reason = args.reason.strip() if isinstance(args.reason, str) else ""
    if not reason:
        raise RouterError("ROUTER_GOVERNANCE_REASON_REQUIRED")
    if profile == "strict" and target_mode != "governed":
        raise RouterError(
            "ROUTER_GOVERNANCE_DOWNGRADE_DENIED: strict profile remains governed"
        )
    if GOVERNANCE_MODE_RANK[target_mode] < GOVERNANCE_MODE_RANK[current_mode]:
        raise RouterError(
            "ROUTER_GOVERNANCE_DOWNGRADE_DENIED: mode promotion is monotonic "
            f"within a turn ({current_mode} -> {target_mode})"
        )
    receipt = {"mode": target_mode, "reason": reason}
    if target_mode != current_mode or reasons[-1] != receipt:
        reasons.append(receipt)
    runtime["governance_mode"] = target_mode
    runtime["governance_reasons"] = reasons
    _atomic_json(
        _state_path(root, args.adapter_id, args.session_id, args.turn_id),
        runtime,
    )
    _json_output(
        {
            "adapter_id": args.adapter_id,
            "session_id": args.session_id,
            "turn_id": args.turn_id,
            "governance_profile": profile,
            "governance_mode": target_mode,
            "governance_reasons": reasons,
            "promoted": target_mode != current_mode,
            "next": (
                "Build and Governed modes require an activation decision "
                "covering planned mutation paths and exact Requirements."
                if target_mode != "explore"
                else "Continue bounded reversible Explore work."
            ),
        }
    )
    return 0


def command_activate(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root,
        args.adapter_id,
        args.session_id,
        args.turn_id,
    )
    if runtime is None:
        raise RouterError(
            "ROUTER_TURN_NOT_INITIALIZED: no lifecycle adapter initialized "
            "this turn; run begin before any write"
        )
    state = load_state(root)
    paths = tuple(dict.fromkeys(_normalize_planned_path(root, value) for value in args.path))
    if not paths:
        raise RouterError("ROUTER_PATHS_REQUIRED: provide at least one --path")
    capsule_budget = _bounded_budget(
        args.capsule_budget_bytes,
        "ROUTER_CAPSULE_BUDGET_INVALID",
    )
    budget_override_reason = ""
    if not args.none and capsule_budget > DEFAULT_CAPSULE_BUDGET_BYTES:
        if (
            not isinstance(args.capsule_budget_reason, str)
            or not args.capsule_budget_reason.strip()
        ):
            raise RouterError(
                "ROUTER_CAPSULE_BUDGET_REASON_REQUIRED: raising the default "
                "capsule budget requires --capsule-budget-reason"
            )
        budget_override_reason = args.capsule_budget_reason.strip()
    candidates = {entry.key for entry in candidate_entries(state, paths)}
    requested = tuple(dict.fromkeys(args.spec or ()))
    direct_ids = tuple(dict.fromkeys(args.requirement or ()))
    explicit_whole = tuple(dict.fromkeys(args.whole_spec or ()))
    if args.none:
        if requested or direct_ids or explicit_whole:
            raise RouterError(
                "ROUTER_DECISION_INVALID: --none cannot be combined with "
                "Spec or Requirement selections"
            )
        if not isinstance(args.reason, str) or not args.reason.strip():
            raise RouterError("ROUTER_NONE_REASON_REQUIRED: --none requires --reason")
        selected: tuple[SpecEntry, ...] = ()
        decision = "none"
        reason = args.reason.strip()
        resolved: tuple[RequirementRecord, ...] = ()
        whole_ids: tuple[str, ...] = ()
        supporting: tuple[tuple[str, str], ...] = ()
        direct_payload: list[dict[str, object]] = []
        capsule = ""
        capsule_mode = "none"
    else:
        legacy_alias = bool(requested and not direct_ids and not explicit_whole)
        whole_requested = requested if legacy_alias else explicit_whole
        if not direct_ids and not whole_requested:
            raise RouterError(
                "ROUTER_SELECTION_REQUIRED: use --requirement, "
                "--whole-spec, legacy --spec, or --none"
            )
        considered_specs = tuple(
            dict.fromkeys((*requested, *whole_requested))
        )
        unknown = sorted(set(considered_specs) - set(state.by_key))
        if unknown:
            raise RouterError("ROUTER_SPEC_UNKNOWN: " + ", ".join(unknown))
        irrelevant = sorted(set(considered_specs) - candidates)
        if irrelevant:
            raise RouterError(
                "ROUTER_SPEC_NOT_CANDIDATE: " + ", ".join(irrelevant)
            )
        reasons = _because_map(args.because or ())
        if direct_ids:
            if not requested:
                raise RouterError(
                    "ROUTER_APPLICABLE_SPEC_REQUIRED: Requirement mode "
                    "requires --spec for each applicable Spec"
                )
            unknown_requirements = sorted(
                set(direct_ids) - set(state.requirement_index.by_requirement)
            )
            if unknown_requirements:
                raise RouterError(
                    "ROUTER_REQUIREMENT_UNKNOWN: "
                    + ", ".join(unknown_requirements)
                )
            missing_reasons = sorted(set(direct_ids) - set(reasons))
            extra_reasons = sorted(set(reasons) - set(direct_ids))
            if missing_reasons or extra_reasons:
                details: list[str] = []
                if missing_reasons:
                    details.append("missing " + ", ".join(missing_reasons))
                if extra_reasons:
                    details.append("extra " + ", ".join(extra_reasons))
                raise RouterError(
                    "ROUTER_REQUIREMENT_REASON_COVERAGE: "
                    + "; ".join(details)
                )
            direct_records = tuple(
                state.requirement_index.by_requirement[item]
                for item in direct_ids
            )
            direct_owner_ids = {item.spec_id for item in direct_records}
            outside_applicable = sorted(direct_owner_ids - set(requested))
            if outside_applicable:
                raise RouterError(
                    "ROUTER_REQUIREMENT_SPEC_NOT_APPLICABLE: "
                    + ", ".join(outside_applicable)
                )
            missing_direct = sorted(
                spec_id
                for spec_id in requested
                if (
                    state.requirement_index.by_spec[spec_id].mode
                    == "requirements"
                    and spec_id not in direct_owner_ids
                )
            )
            if missing_direct:
                raise RouterError(
                    "ROUTER_APPLICABLE_SPEC_REQUIREMENT_MISSING: "
                    + ", ".join(missing_direct)
                )
            legacy_applicable = sorted(
                spec_id
                for spec_id in requested
                if state.requirement_index.by_spec[spec_id].mode == "whole-spec"
                and spec_id not in whole_requested
            )
            if legacy_applicable:
                raise RouterError(
                    "ROUTER_WHOLE_SPEC_REQUIRED: "
                    + ", ".join(legacy_applicable)
                )
            resolved = requirement_dependency_closure(
                state.requirement_index,
                direct_ids,
            )
            direct_payload = _direct_payload(direct_records, reasons)
        else:
            if reasons:
                raise RouterError(
                    "ROUTER_REQUIREMENT_REASON_COVERAGE: reasons require "
                    "direct Requirement IDs"
                )
            resolved = ()
            direct_payload = []
        if explicit_whole and (
            not isinstance(args.whole_spec_reason, str)
            or not args.whole_spec_reason.strip()
        ):
            raise RouterError(
                "ROUTER_WHOLE_SPEC_REASON_REQUIRED: explicit --whole-spec "
                "requires --whole-spec-reason"
            )
        whole_entries = (
            dependency_closure(state, whole_requested)
            if whole_requested
            else ()
        )
        whole_ids = tuple(item.key for item in whole_entries)
        resolved_spec_ids = {item.spec_id for item in resolved}
        redundant = sorted(resolved_spec_ids & set(whole_ids))
        if redundant:
            raise RouterError(
                "ROUTER_SELECTION_REDUNDANT: Requirement and whole-Spec "
                "modes overlap for " + ", ".join(redundant)
            )
        supporting = _supporting_sections(args.section or ())
        if any(spec_id in set(whole_ids) for spec_id, _ in supporting):
            raise RouterError(
                "ROUTER_SECTION_REDUNDANT_OR_UNSAFE: supporting sections "
                "cannot accompany whole-Spec mode"
            )
        capsule, capsule_mode = compile_context_capsule(
            root,
            state,
            direct_ids,
            resolved,
            whole_ids,
            supporting,
            capsule_budget,
        )
        selected_ids: list[str] = []
        for record in resolved:
            if record.spec_id not in selected_ids:
                selected_ids.append(record.spec_id)
        for spec_id in whole_ids:
            if spec_id not in selected_ids:
                selected_ids.append(spec_id)
        selected = tuple(state.by_key[item] for item in selected_ids)
        decision = "activated"
        reason = ""

    capsule_bytes = len(capsule.encode("utf-8"))
    activation = {
        "decision": decision,
        "reason": reason,
        "planned_paths": list(paths),
        "applicable_specs": list(requested),
        "requested_specs": list(requested),
        "activated_specs": [
            entry_payload(root, item, state.requirement_index)
            for item in selected
        ],
        "direct_requirements": direct_payload,
        "resolved_requirements": _resolved_payload(resolved, direct_ids),
        "dependency_edges": _dependency_edges(resolved),
        "whole_specs": list(whole_ids),
        "whole_spec_reason": (
            args.whole_spec_reason.strip()
            if isinstance(args.whole_spec_reason, str)
            else "legacy --spec compatibility mode"
            if not args.none and requested and not direct_ids
            else ""
        ),
        "supporting_sections": [
            {"spec_id": spec_id, "heading": heading}
            for spec_id, heading in supporting
        ],
        "context_epoch": runtime["context_epoch"],
        "capsule": {
            "mode": capsule_mode,
            "sha256": _sha256(capsule.encode("utf-8")),
            "bytes": capsule_bytes,
            "budget_bytes": capsule_budget,
            "budget_override_reason": budget_override_reason,
        },
    }
    runtime["activation"] = activation
    runtime["context_injected_epoch"] = None
    _atomic_json(
        _state_path(root, args.adapter_id, args.session_id, args.turn_id),
        runtime,
    )
    _json_output(
        {
            "adapter_id": args.adapter_id,
            "session_id": args.session_id,
            "turn_id": args.turn_id,
            **activation,
            "next": (
                "Review the exact capsule. Trusted Hooks inject and verify "
                "the same digest before the first mutation in every context epoch."
            ),
        }
    )
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root,
        args.adapter_id,
        args.session_id,
        args.turn_id,
    )
    if runtime is None:
        raise RouterError("ROUTER_ACTIVATION_MISSING")
    _json_output(runtime)
    return 0


def command_evidence(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root,
        args.adapter_id,
        args.session_id,
        args.turn_id,
    )
    if runtime is None:
        raise RouterError("ROUTER_ACTIVATION_MISSING")
    activation = _activation(runtime)
    _context_for_activation(root, activation)
    state = load_state(root)
    raw_resolved = activation.get("resolved_requirements")
    if not isinstance(raw_resolved, list):
        raise RouterError("ROUTER_ACTIVATION_INVALID.resolved_requirements")
    requirements: list[dict[str, object]] = []
    for raw in raw_resolved:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise RouterError(
                "ROUTER_ACTIVATION_INVALID.resolved_requirements"
            )
        record = state.requirement_index.by_requirement.get(str(raw["id"]))
        if record is None:
            raise RouterError(f"ROUTER_REQUIREMENT_UNKNOWN: {raw['id']}")
        spec = state.requirement_index.by_spec[record.spec_id]
        requirements.append(
            {
                "id": record.requirement_id,
                "selection_source": raw.get("source"),
                "spec": {
                    "id": spec.spec_id,
                    "version": spec.version,
                    "path": spec.path,
                    "sha256": spec.sha256,
                },
                "requirement_block_sha256": record.block.sha256,
                "automated_enforcement": _enforcement_payload(record),
            }
        )
    repository_head = _git(
        root,
        "rev-parse",
        "HEAD",
        check=False,
    ).strip()
    evidence: dict[str, object] = {
        "schema_version": ENFORCEMENT_EVIDENCE_SCHEMA_VERSION,
        "evidence_type": "repo-foundry/requirement-activation",
        "catalog": {
            "id": state.catalog_id,
            "version": state.catalog_version,
            "revision": state.revision,
            "sha256": state.catalog_digest,
        },
        "consumer": {
            "id": "repo-foundry",
            "router_version": ROUTER_VERSION,
            "repository_head": repository_head or None,
            "worktree_clean": not bool(_changed_file_state(root)),
        },
        "receipt": {
            "adapter_id": runtime["adapter_id"],
            "session_id": runtime["session_id"],
            "turn_id": runtime["turn_id"],
            "context_epoch": activation.get("context_epoch"),
            "decision": activation.get("decision"),
            "planned_paths": activation.get("planned_paths"),
            "capsule": activation.get("capsule"),
        },
        "requirements": requirements,
        "whole_specs": activation.get("whole_specs"),
        "finding_lifecycle": {
            "supported": False,
            "maximum_effective_level": (
                REPO_FOUNDRY_EFFECTIVE_AUTOMATED_ENFORCEMENT
            ),
            "reason": (
                "RepoFoundry exports verified activation context but does "
                "not produce or adjudicate compliance findings."
            ),
        },
    }
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    evidence["sha256"] = _sha256(canonical)
    _json_output(evidence)
    return 0


def command_rehydrate(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    result = process_event(
        root,
        {
            "protocol_version": PROTOCOL_VERSION,
            "event": "context_resume",
            "adapter_id": args.adapter_id,
            "session_id": args.session_id,
            "turn_id": args.turn_id,
            "prompt": "",
        },
    )
    _json_output(result)
    return 0


def _covered(path: str, planned: Iterable[str]) -> bool:
    return any(_matches(path, pattern) for pattern in planned)


def command_preflight(args: argparse.Namespace) -> int:
    """Read-only snapshot check before the first Build/Governed edit.

    The caller supplies exact intended files and any independently identified
    expected Requirements; applicability is not inferred by this command.
    No late activation can retrospectively satisfy this before-edit check.
    """
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root, args.adapter_id, args.session_id, args.turn_id
    )
    if runtime is None:
        raise RouterError("ROUTER_ACTIVATION_MISSING")
    activation = _activation(runtime)
    _context_for_activation(root, activation)
    paths = tuple(dict.fromkeys(
        _normalize_planned_path(root, raw) for raw in args.path
    ))
    if any(any(char in path for char in "*?[]") for path in paths):
        raise RouterError(
            "ROUTER_PREFLIGHT_EXACT_PATH_REQUIRED: enumerate intended files"
        )
    expected = tuple(dict.fromkeys(args.expect_requirement or ()))
    state = load_state(root)
    unknown = sorted(
        set(expected) - set(state.requirement_index.by_requirement)
    )
    if unknown:
        raise RouterError(
            "ROUTER_REQUIREMENT_UNKNOWN: " + ", ".join(unknown)
        )
    selected = {
        item["id"] for item in activation.get("resolved_requirements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    whole = set(activation.get("whole_specs", []))
    missing_requirements = [
        item for item in expected
        if item not in selected
        and state.requirement_index.by_requirement[item].spec_id not in whole
    ]
    uncovered = [
        path for path in paths
        if not _covered(path, activation["planned_paths"])
    ]
    previous_changes = _paths_changed_since(root, runtime.get("baseline"))
    epoch = runtime.get("context_epoch")
    delivered = (
        type(epoch) is int
        and runtime.get("context_injected_epoch") == epoch
        and activation.get("context_epoch") == epoch
    )
    errors = []
    if previous_changes:
        errors.append("ROUTER_PREFLIGHT_AFTER_EDIT: " + ", ".join(previous_changes))
    if uncovered:
        errors.append("ROUTER_PREFLIGHT_PATH_UNCOVERED: " + ", ".join(uncovered))
    if missing_requirements:
        errors.append(
            "ROUTER_PREFLIGHT_REQUIREMENT_MISSING: "
            + ", ".join(missing_requirements)
        )
    if not delivered:
        errors.append("ROUTER_PREFLIGHT_CONTEXT_NOT_DELIVERED")
    result = {
        "ok": not errors,
        "checked_paths": list(paths),
        "uncovered_paths": uncovered,
        "expected_requirements": list(expected),
        "missing_requirements": missing_requirements,
        "changed_since_begin": list(previous_changes),
        "capsule_delivered_in_current_epoch": delivered,
        "checks_only_current_turn": True,
        "applicability_review_required": True,
        "errors": errors,
    }
    _json_output(result)
    return 0 if result["ok"] else 1


def _activation(runtime: dict[str, object]) -> dict[str, object]:
    activation = runtime.get("activation")
    if not isinstance(activation, dict):
        raise RouterError("ROUTER_ACTIVATION_MISSING")
    planned = activation.get("planned_paths")
    specs = activation.get("activated_specs")
    decision = activation.get("decision")
    if decision not in {"activated", "none"}:
        raise RouterError("ROUTER_ACTIVATION_INVALID.decision")
    if not isinstance(planned, list) or not planned or any(not isinstance(item, str) for item in planned):
        raise RouterError("ROUTER_ACTIVATION_INVALID.planned_paths")
    if not isinstance(specs, list):
        raise RouterError("ROUTER_ACTIVATION_INVALID.activated_specs")
    return activation


def _audit(
    root: Path,
    runtime: dict[str, object],
    message: str | None,
) -> dict[str, object]:
    profile, mode, reasons = _governance(runtime)
    if mode == "explore" and not isinstance(runtime.get("activation"), dict):
        changed = _paths_changed_since(root, runtime.get("baseline"))
        return {
            "ok": True,
            "governance_profile": profile,
            "governance_mode": mode,
            "governance_reasons": reasons,
            "changed_paths": list(changed),
            "uncovered_paths": [],
            "missing_handoff_labels": [],
            "errors": [],
        }
    activation = _activation(runtime)
    changed = _paths_changed_since(root, runtime.get("baseline"))
    planned = tuple(str(item) for item in activation["planned_paths"])
    uncovered = tuple(path for path in changed if not _covered(path, planned))
    missing_labels = tuple(
        label for label in HANDOFF_LABELS if message is not None and label not in message
    )
    errors: list[str] = []
    if uncovered:
        errors.append("ROUTER_CHANGED_PATH_UNCOVERED: " + ", ".join(uncovered))
    if missing_labels:
        errors.append("ROUTER_HANDOFF_INCOMPLETE: " + ", ".join(missing_labels))
    return {
        "ok": not errors,
        "governance_profile": profile,
        "governance_mode": mode,
        "governance_reasons": reasons,
        "changed_paths": list(changed),
        "uncovered_paths": list(uncovered),
        "missing_handoff_labels": list(missing_labels),
        "errors": errors,
    }


def command_audit(args: argparse.Namespace) -> int:
    root = repository_root(args.repo)
    runtime = _load_runtime(
        root,
        args.adapter_id,
        args.session_id,
        args.turn_id,
    )
    if runtime is None:
        raise RouterError("ROUTER_ACTIVATION_MISSING")
    message = args.message
    if args.message_file:
        message = _read_bytes(
            Path(args.message_file), "ROUTER_MESSAGE_INVALID", MAX_CONTEXT_BYTES
        ).decode("utf-8", errors="strict")
    result = _audit(root, runtime, message)
    _json_output(result)
    return 0 if result["ok"] else 1


def _router_command(adapter_id: str, session_id: str, turn_id: str) -> str:
    relative = ".repo-foundry/engineering-specs/spec_router.py"
    return (
        f"python3 {relative} classify --adapter-id {adapter_id} "
        f"--session-id {session_id} --turn-id {turn_id} "
        "--mode <explore|build|governed> --reason <risk-reason>\n"
        f"python3 {relative} candidates --path <planned-path>\n"
        f"python3 {relative} requirements --path <planned-path> "
        "--spec <applicable-spec>\n"
        f"python3 {relative} activate --adapter-id {adapter_id} "
        f"--session-id {session_id} --turn-id {turn_id} "
        "--path <planned-path> "
        "(--spec <applicable-spec> --requirement <ID> "
        "--because 'ID=reason' | --whole-spec <id> "
        "--whole-spec-reason <reason> | --none --reason <reason>)"
    )



# Session context is an optional navigation surface, never an EP/ADR validator.
# Only explicit references in the task select artifacts; no background corpus scan.
_SESSION_EP_RE = re.compile(r"(?<![A-Za-z0-9])EP-([0-9]{3,8})(?![A-Za-z0-9])", re.IGNORECASE)
_SESSION_ADR_RE = re.compile(r"(?<![A-Za-z0-9])ADR-([0-9]{3,8})(?![A-Za-z0-9])", re.IGNORECASE)
_SESSION_MAX_ADR_LINKS = 12


def _session_requested_refs(prompt: object) -> tuple[list[str], list[str]]:
    if not isinstance(prompt, str):
        return [], []
    plans = sorted({f"EP-{int(n):03d}" for n in _SESSION_EP_RE.findall(prompt)})
    adrs = sorted({f"ADR-{int(n):03d}" for n in _SESSION_ADR_RE.findall(prompt)})
    # A multi-plan task needs explicit scoping; never guess which plan is current.
    return plans[:1] if len(plans) == 1 else [], adrs


def _session_ep_snapshot(
    root: Path, plan_id: str
) -> tuple[SessionContextSection, list[str]]:
    number = int(plan_id.split("-", 1)[1])
    active_root = root / "docs/exec-plans/active"
    matches = sorted(active_root.glob(f"ep-{number:03d}_*/EXECPLAN.md"))
    source = "docs/PLANS.md"
    unavailable = f"{plan_id}: active EP snapshot unavailable; inspect {source} and validate EP."
    refs: list[str] = []
    if len(matches) != 1:
        return SessionContextSection(
            id="ep-snapshot", priority=5, content=unavailable, source=source
        ), refs
    relative = matches[0].relative_to(root).as_posix()
    try:
        file_path = _resolve_regular(root, relative, "ROUTER_EP_CONTEXT_INVALID")
        document = _read_bytes(
            file_path, "ROUTER_EP_CONTEXT_INVALID", MAX_CONTEXT_BYTES
        ).decode("utf-8")
        front = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", document, re.DOTALL)
        if front is None:
            raise ValueError("missing frontmatter")
        identity = re.search(r"(?m)^id:\s*(EP-[0-9]{3,8})\s*$", front.group(1))
        status = re.search(r"(?m)^status:\s*(active|blocked)\s*$", front.group(1))
        if identity is None or identity.group(1) != plan_id or status is None:
            raise ValueError("identity/status does not match the active plan")
        snapshots = re.findall(
            r"(?ms)^## Current Snapshot[ \t]*\r?\n(.*?)(?=^## [^\r\n]+|\Z)",
            document,
        )
        if len(snapshots) != 1 or not snapshots[0].strip():
            raise ValueError("missing unique Current Snapshot")
        raw_refs = re.search(r"(?m)^adr_refs:\s*(\[[^\r\n]*\])\s*$", front.group(1))
        if raw_refs is not None:
            parsed = json.loads(raw_refs.group(1))
            if not isinstance(parsed, list) or not all(
                isinstance(value, str) and _SESSION_ADR_RE.fullmatch(value)
                for value in parsed
            ):
                raise ValueError("invalid ADR references")
            refs = sorted(set(parsed))
        content = (
            f"Current Snapshot for {plan_id} (informational, not an acceptance "
            f"or validation result; source: {relative}):\n\n"
            + snapshots[0].strip()
        )
        return SessionContextSection(
            id="ep-snapshot", priority=5, content=content, source=relative
        ), refs
    except (OSError, UnicodeError, ValueError, RouterError):
        return SessionContextSection(
            id="ep-snapshot", priority=5, content=unavailable, source=source
        ), []


def _session_adr_navigation(
    root: Path, adr_ids: Iterable[str], additional_omitted: int = 0,
    *, priority_ids: Iterable[str] = (),
) -> SessionContextSection | None:
    all_ids = tuple(sorted(set(adr_ids)))
    # Explicit prompt references take precedence over EP dependency navigation.
    # Sort within each tier so the same inputs always produce the same context.
    priority = set(priority_ids)
    requested = tuple(
        [value for value in all_ids if value in priority]
        + [value for value in all_ids if value not in priority]
    )[:_SESSION_MAX_ADR_LINKS]
    if not requested:
        return None
    source = "docs/DECISIONS.md"
    unavailable = (
        "ADR navigation is unavailable or not validated; inspect "
        f"{source} and run epctl validate before relying on current effect."
    )
    try:
        index_path = _resolve_regular(root, source, "ROUTER_ADR_CONTEXT_INVALID")
        text = _read_bytes(
            index_path, "ROUTER_ADR_CONTEXT_INVALID", MAX_CONTEXT_BYTES
        ).decode("utf-8")
        start, end = (
            "<!-- ADRCTL:CURRENT:START -->",
            "<!-- ADRCTL:CURRENT:END -->",
        )
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("missing or duplicate current projection markers")
        body = text.split(start, 1)[1].split(end, 1)[0]
        if end not in text.split(start, 1)[1]:
            raise ValueError("malformed projection markers")
        current: dict[str, str] = {}
        for line in body.splitlines():
            row = re.match(r"^\|\s*(ADR-[0-9]{3,8})\s*\|", line)
            if row is None or row.group(1) not in requested:
                continue
            matches = re.findall(r"\[ADR\]\(([^()\s]+\.md)\)", line)
            if len(matches) != 1 or row.group(1) in current:
                raise ValueError("ambiguous ADR projection")
            relative = _safe_relative(
                "docs/" + matches[0], "ROUTER_ADR_CONTEXT_INVALID"
            )
            _resolve_regular(root, relative, "ROUTER_ADR_CONTEXT_INVALID")
            current[row.group(1)] = relative
        lines = [
            "Current-effect ADR navigation (derived index only; validate the "
            "ADR sources before relying on any constraint):"
        ]
        for adr_id in requested:
            if adr_id in current:
                lines.append(f"- {adr_id}: {current[adr_id]}")
            else:
                lines.append(
                    f"- {adr_id}: not in the current-effect projection; "
                    "verify history or amendments before use."
                )
        missing_count = len(all_ids) - len(requested) + additional_omitted
        if missing_count:
            lines.append(
                f"- {missing_count} additional ADR references: "
                f"inspect {source}; not individually materialized."
            )
        return SessionContextSection(
            id="adr-navigation",
            priority=10,
            content="\n".join(lines),
            source=source,
        )
    except (OSError, UnicodeError, ValueError, RouterError):
        return SessionContextSection(
            id="adr-navigation", priority=10, content=unavailable, source=source
        )


def _session_artifact_sections(
    root: Path, runtime: dict[str, object]
) -> tuple[SessionContextSection, ...]:
    sections: list[SessionContextSection] = []
    plan = runtime.get("context_ep_ref")
    adrs = runtime.get("context_adr_refs", [])
    ids = [value for value in adrs if isinstance(value, str)] if isinstance(adrs, list) else []
    explicit_ids = tuple(ids)
    if isinstance(plan, str) and _SESSION_EP_RE.fullmatch(plan):
        snapshot, plan_adrs = _session_ep_snapshot(root, plan)
        sections.append(snapshot)
        ids.extend(plan_adrs)
    extra = runtime.get("context_adr_omitted_count", 0)
    omitted = extra if type(extra) is int and extra > 0 else 0
    navigation = _session_adr_navigation(
        root, ids, additional_omitted=omitted, priority_ids=explicit_ids
    )
    if navigation is not None:
        sections.append(navigation)
    return tuple(sections)


def _apply_memory_runtime(
    root: Path, runtime: dict[str, object], payload: dict[str, object],
    baseline: dict[str, object],
) -> dict[str, object]:
    """Optional Core extension; an invalid baseline never reaches this call."""
    config = root / ".repo-foundry/memory-context.json"
    if not config.exists() and not config.is_symlink():
        return baseline
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        path = Path(__file__).with_name("memory_runtime.py")
        if path.is_symlink() or not path.is_file():
            raise ValueError("MEMORY_RUNTIME_UNAVAILABLE")
        spec = importlib.util.spec_from_file_location("_repoharness_memory_runtime", path)
        if spec is None or spec.loader is None:
            raise ValueError("MEMORY_RUNTIME_UNAVAILABLE")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.apply_context(
            sys.modules[__name__], root, runtime, baseline,
            as_of=payload.get("memory_as_of"),
        )
    except (OSError, ImportError, ValueError, RuntimeError, SyntaxError, AttributeError, TypeError):
        return {**baseline, "memory": {
            "schema_version": 1, "status": "baseline_fallback",
            "reason": "MEMORY_RUNTIME_UNAVAILABLE", "saved_bytes": 0,
            "protected_core_unchanged": True, "authority_changed": False,
        }}
    finally:
        sys.dont_write_bytecode = previous


def _route_context(
    root: Path, payload: dict[str, object]
) -> tuple[str, dict[str, object]]:
    runtime = _initialize_turn(root, payload)
    adapter_id = str(runtime["adapter_id"])
    session_id = str(runtime["session_id"])
    turn_id = str(runtime["turn_id"])
    profile, mode, reasons = _governance(runtime)
    index = _read_bytes(
        root / INDEX_PATH,
        "ROUTER_INDEX_INVALID",
        MAX_CONTEXT_BYTES,
    ).decode("utf-8", errors="strict")
    if mode == "explore":
        governance_context = (
            "Adaptive Explore mode is active. Bounded reversible inspection, "
            "experiments, local edits, and tests may proceed without a Spec "
            "activation receipt. Promote to Build for bounded production work "
            "and Governed for public contracts, security, data, irreversible "
            "operations, reliability claims, release, or durable decisions. "
            "Authority, destructive/external-action, security, data-integrity, "
            "and evidence-integrity boundaries remain mandatory."
        )
    else:
        governance_context = (
            f"{mode.title()} mode is active. Record applicable Specs or a "
            "justified no-Spec decision before mutation; Governed work also "
            "retains its full evidence and authority gates."
        )
    routing_contract = (
        governance_context
        + " File scope creates candidates; Applicability chooses Specs; bounded "
        "cards choose exact Requirements and code resolves their context "
        "dependencies. Record direct IDs with task-specific reasons, an explicit "
        "whole-Spec fallback, or a justified no-Spec decision before any write "
        "that requires Build or Governed mode.\n\n"
        f"Governance profile: `{profile}`\nGovernance mode: `{mode}`\n"
        f"Governance reasons: `{json.dumps(reasons, ensure_ascii=False)}`\n\n"
        f"Adapter ID: `{adapter_id}`\nSession ID: `{session_id}`\n"
        f"Turn ID: `{turn_id}`\nContext epoch: `{runtime['context_epoch']}`\n\n"
        f"Commands:\n{_router_command(adapter_id, session_id, turn_id)}"
    )
    context_plan = plan_session_context(
        (
            SessionContextSection(
                id="routing-contract",
                priority=0,
                content=routing_contract,
                source=".repo-foundry/engineering-specs/spec_router.py",
                mandatory=True,
            ),
            SessionContextSection(
                id="routing-index",
                priority=20,
                content="Current locked routing index:\n\n" + index,
                source=INDEX_PATH,
            ),
            *_session_artifact_sections(root, runtime),
        )
    )
    context_plan = _apply_memory_runtime(root, runtime, payload, context_plan)
    context = str(context_plan["text"])
    activation = runtime.get("activation")
    if isinstance(activation, dict):
        capsule = _context_for_activation(root, activation)
        runtime["context_injected_epoch"] = runtime["context_epoch"]
        _atomic_json(
            _state_path(root, adapter_id, session_id, turn_id),
            runtime,
        )
        context += (
            "\n\nExact activation capsule rehydrated for this context epoch:\n\n"
            + capsule
        )
    # Exact activated Spec capsules remain outside the session routing budget.
    return context, {
        key: value for key, value in context_plan.items() if key != "text"
    }


def _context_for_activation(root: Path, activation: dict[str, object]) -> str:
    specs = activation.get("activated_specs")
    if not isinstance(specs, list):
        raise RouterError("ROUTER_ACTIVATION_INVALID.activated_specs")
    if not specs:
        reason = activation.get("reason", "")
        return f"Engineering Spec activation decision: none. Reason: {reason}"
    raw_direct = activation.get("direct_requirements")
    raw_resolved = activation.get("resolved_requirements")
    raw_edges = activation.get("dependency_edges")
    raw_whole = activation.get("whole_specs")
    raw_sections = activation.get("supporting_sections")
    capsule_metadata = activation.get("capsule")
    direct_base_keys = {"id", "reason", "source"}
    if not isinstance(raw_direct, list) or any(
        not isinstance(item, dict)
        or frozenset(item) not in {
            frozenset(direct_base_keys),
            frozenset({*direct_base_keys, "automated_enforcement"}),
        }
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("reason"), str)
        or not item["reason"].strip()
        or item.get("source") != "agent"
        for item in raw_direct
    ):
        raise RouterError("ROUTER_ACTIVATION_INVALID.direct_requirements")
    resolved_base_keys = {
        "id",
        "spec_id",
        "source",
        "context_dependencies",
        "block",
        "verification",
    }
    if not isinstance(raw_resolved, list) or any(
        not isinstance(item, dict)
        or frozenset(item) not in {
            frozenset(resolved_base_keys),
            frozenset(
                {*resolved_base_keys, "automated_enforcement"}
            ),
        }
        or not isinstance(item.get("id"), str)
        for item in raw_resolved
    ):
        raise RouterError("ROUTER_ACTIVATION_INVALID.resolved_requirements")
    enforcement_flags = {
        "automated_enforcement" in item
        for item in (*raw_direct, *raw_resolved)
    }
    if len(enforcement_flags) > 1:
        raise RouterError(
            "ROUTER_ACTIVATION_INVALID: mixed enforcement receipt shapes"
        )
    include_enforcement = enforcement_flags != {False}
    if not isinstance(raw_edges, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("from"), str)
        or not isinstance(item.get("to"), str)
        for item in raw_edges
    ):
        raise RouterError("ROUTER_ACTIVATION_INVALID.dependency_edges")
    if not isinstance(raw_whole, list) or any(
        not isinstance(item, str) for item in raw_whole
    ):
        raise RouterError("ROUTER_ACTIVATION_INVALID.whole_specs")
    if not isinstance(raw_sections, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("spec_id"), str)
        or not isinstance(item.get("heading"), str)
        for item in raw_sections
    ):
        raise RouterError("ROUTER_ACTIVATION_INVALID.supporting_sections")
    if not isinstance(capsule_metadata, dict):
        raise RouterError("ROUTER_ACTIVATION_INVALID.capsule")
    budget = capsule_metadata.get("budget_bytes")
    if type(budget) is not int:
        raise RouterError("ROUTER_ACTIVATION_INVALID.capsule.budget_bytes")
    budget_override_reason = capsule_metadata.get("budget_override_reason")
    if not isinstance(budget_override_reason, str):
        raise RouterError(
            "ROUTER_ACTIVATION_INVALID.capsule.budget_override_reason"
        )
    if budget > DEFAULT_CAPSULE_BUDGET_BYTES and not budget_override_reason:
        raise RouterError(
            "ROUTER_ACTIVATION_INVALID.capsule.budget_override_reason: "
            "required above the default budget"
        )
    state = load_state(root)
    direct_ids = tuple(str(item["id"]) for item in raw_direct)
    unknown_whole = sorted(
        set(str(item) for item in raw_whole)
        - set(state.requirement_index.by_spec)
    )
    if unknown_whole:
        raise RouterError(
            "ROUTER_ACTIVATION_INVALID.whole_specs: "
            + ", ".join(unknown_whole)
        )
    resolved = requirement_dependency_closure(
        state.requirement_index,
        direct_ids,
    )
    direct_records = tuple(
        state.requirement_index.by_requirement[requirement_id]
        for requirement_id in direct_ids
    )
    direct_reasons = {
        str(item["id"]): str(item["reason"])
        for item in raw_direct
    }
    expected_direct = _direct_payload(
        direct_records,
        direct_reasons,
        include_enforcement=include_enforcement,
    )
    if raw_direct != expected_direct:
        raise RouterError(
            "ROUTER_ACTIVATION_REQUIREMENT_DRIFT: direct source metadata "
            "changed"
        )
    expected_resolved = _resolved_payload(
        resolved,
        direct_ids,
        include_enforcement=include_enforcement,
    )
    if raw_resolved != expected_resolved:
        raise RouterError(
            "ROUTER_ACTIVATION_REQUIREMENT_DRIFT: resolved source metadata "
            "changed"
        )
    if raw_edges != _dependency_edges(resolved):
        raise RouterError(
            "ROUTER_ACTIVATION_REQUIREMENT_DRIFT: dependency edges changed"
        )
    selected_ids: list[str] = []
    for record in resolved:
        if record.spec_id not in selected_ids:
            selected_ids.append(record.spec_id)
    for spec_id in raw_whole:
        if spec_id not in selected_ids:
            selected_ids.append(spec_id)
    expected_specs = [
        entry_payload(
            root,
            state.by_key[spec_id],
            state.requirement_index,
        )
        for spec_id in selected_ids
    ]
    if specs != expected_specs:
        raise RouterError(
            "ROUTER_ACTIVATION_SOURCE_DRIFT: activated Spec metadata changed"
        )
    sections = tuple(
        (str(item["spec_id"]), str(item["heading"]))
        for item in raw_sections
    )
    capsule, mode = compile_context_capsule(
        root,
        state,
        direct_ids,
        resolved,
        tuple(raw_whole),
        sections,
        _bounded_budget(budget, "ROUTER_CAPSULE_BUDGET_INVALID"),
    )
    encoded = capsule.encode("utf-8")
    if (
        capsule_metadata.get("mode") != mode
        or capsule_metadata.get("sha256") != _sha256(encoded)
        or capsule_metadata.get("bytes") != len(encoded)
    ):
        raise RouterError(
            "ROUTER_ACTIVATION_CAPSULE_DRIFT: receipt does not match exact context"
        )
    return capsule


def _deny(reason: str, *, context: str | None = None) -> dict[str, object]:
    output: dict[str, object] = {"decision": "deny", "reason": reason}
    if context is not None:
        output["context"] = context
    return output


def _event_identity(payload: dict[str, object]) -> tuple[str, str, str]:
    adapter_id = payload.get("adapter_id")
    session_id = payload.get("session_id")
    turn_id = payload.get("turn_id")
    if not isinstance(adapter_id, str) or not ADAPTER_ID_RE.fullmatch(adapter_id):
        raise RouterError("ROUTER_EVENT_INVALID.adapter_id")
    if not isinstance(session_id, str) or not session_id:
        raise RouterError("ROUTER_EVENT_INVALID.session_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise RouterError("ROUTER_EVENT_INVALID.turn_id")
    return adapter_id, session_id, turn_id


def _before_mutation(
    root: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    adapter_id, session_id, turn_id = _event_identity(payload)
    tool = payload.get("tool")
    if not isinstance(tool, dict):
        return _deny("Engineering Spec gate received an invalid normalized tool.")
    category = tool.get("category")
    if category not in TOOL_CATEGORIES:
        return _deny("Engineering Spec gate received an unsupported tool category.")
    if category == "read":
        return {"decision": "allow"}
    runtime = _load_runtime(root, adapter_id, session_id, turn_id)
    if runtime is not None:
        try:
            _, mode, _ = _governance(runtime)
        except RouterError as exc:
            return _deny(str(exc))
        if mode == "explore":
            return {"decision": "allow"}
    if runtime is None or not isinstance(runtime.get("activation"), dict):
        return _deny(
            "Record this turn's Engineering Spec activation before editing.\n"
            + _router_command(adapter_id, session_id, turn_id)
        )
    try:
        activation = _activation(runtime)
        if category == "file_write":
            raw_paths = tool.get("paths")
            if not isinstance(raw_paths, list) or not raw_paths or any(
                not isinstance(item, str) for item in raw_paths
            ):
                return _deny(
                    "Engineering Spec gate could not resolve mutation target paths."
                )
            targets = tuple(
                dict.fromkeys(_normalize_planned_path(root, item) for item in raw_paths)
            )
            planned = tuple(str(item) for item in activation["planned_paths"])
            uncovered = tuple(path for path in targets if not _covered(path, planned))
            if uncovered:
                return _deny(
                    "Extend Engineering Spec activation before editing uncovered paths: "
                    + ", ".join(uncovered)
                )
        epoch = runtime.get("context_epoch")
        if type(epoch) is not int or epoch < 1:
            raise RouterError("ROUTER_RUNTIME_INVALID.context_epoch")
        if runtime.get("context_injected_epoch") != epoch:
            context = _context_for_activation(root, activation)
            runtime["context_injected_epoch"] = epoch
            _atomic_json(
                _state_path(root, adapter_id, session_id, turn_id),
                runtime,
            )
            return _deny(
                "Activated Engineering Specs were injected. Re-evaluate and retry the edit.",
                context=context,
            )
    except RouterError as exc:
        return _deny(str(exc))
    return {"decision": "allow"}


def _stop(root: Path, payload: dict[str, object]) -> dict[str, object]:
    adapter_id, session_id, turn_id = _event_identity(payload)
    runtime = _load_runtime(root, adapter_id, session_id, turn_id)
    if runtime is None:
        return {"decision": "allow"}
    changed = _paths_changed_since(root, runtime.get("baseline"))
    if not changed:
        return {"decision": "allow"}
    try:
        _, mode, _ = _governance(runtime)
    except RouterError as exc:
        return {"decision": "deny", "reason": str(exc)}
    if mode == "explore" and not isinstance(runtime.get("activation"), dict):
        return {"decision": "allow"}
    if not isinstance(runtime.get("activation"), dict):
        return {
            "decision": "deny",
            "reason": "Repository files changed without an Engineering Spec activation decision; activate and complete the required handoff.",
        }
    message = payload.get("message")
    result = _audit(root, runtime, message if isinstance(message, str) else "")
    if not result["ok"]:
        return {
            "decision": "deny",
            "reason": "Engineering Spec audit failed:\n- " + "\n- ".join(result["errors"]),
        }
    return {"decision": "allow"}


def process_event(root: Path, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise RouterError(
            "ROUTER_PROTOCOL_UNSUPPORTED: expected protocol_version "
            f"{PROTOCOL_VERSION}"
        )
    event = payload.get("event")
    if event not in NORMALIZED_EVENTS:
        raise RouterError(f"ROUTER_EVENT_UNSUPPORTED: {event!r}")
    _event_identity(payload)
    if event in {"session_start", "subagent_start", "context_resume"}:
        context, context_plan = _route_context(root, payload)
        return {
            "decision": "allow",
            "context": context,
            "context_plan": context_plan,
        }
    if event == "before_mutation":
        return _before_mutation(root, payload)
    return _stop(root, payload)


def command_event(args: argparse.Namespace) -> int:
    raw = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise RouterError("ROUTER_EVENT_TOO_LARGE")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RouterError(f"ROUTER_EVENT_INVALID: {exc}") from exc
    if not isinstance(payload, dict):
        raise RouterError("ROUTER_EVENT_INVALID: expected object")
    root = repository_root(args.repo)
    _json_output(process_event(root, payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root or child directory")
    commands = parser.add_subparsers(dest="command", required=True)

    begin = commands.add_parser(
        "begin",
        help="Establish a manual turn baseline when lifecycle Hooks are unavailable",
    )
    begin.add_argument("--adapter-id", required=True)
    begin.add_argument("--session-id", required=True)
    begin.add_argument("--turn-id", required=True)
    begin.add_argument("--prompt")
    begin.set_defaults(handler=command_begin)

    candidates = commands.add_parser("candidates", help="List scope-matched task candidates")
    candidates.add_argument("--path", action="append", required=True)
    candidates.set_defaults(handler=command_candidates)

    classify = commands.add_parser(
        "classify",
        help="Record or promote this turn's risk-adaptive governance mode",
    )
    classify.add_argument("--adapter-id", required=True)
    classify.add_argument("--session-id", required=True)
    classify.add_argument("--turn-id", required=True)
    classify.add_argument("--mode", choices=GOVERNANCE_MODES, required=True)
    classify.add_argument("--reason", required=True)
    classify.set_defaults(handler=command_classify)

    requirements = commands.add_parser(
        "requirements",
        help="List bounded Requirement cards for applicable Specs",
    )
    requirements.add_argument("--path", action="append", required=True)
    requirements.add_argument("--spec", action="append", required=True)
    requirements.add_argument(
        "--card-budget-bytes",
        type=int,
        default=DEFAULT_CARD_BUDGET_BYTES,
    )
    requirements.set_defaults(handler=command_requirements)

    activate = commands.add_parser("activate", help="Record this turn's activation decision")
    activate.add_argument("--adapter-id", required=True)
    activate.add_argument("--session-id", required=True)
    activate.add_argument("--turn-id", required=True)
    activate.add_argument("--path", action="append", required=True)
    activate.add_argument("--spec", action="append")
    activate.add_argument("--requirement", action="append")
    activate.add_argument("--because", action="append")
    activate.add_argument("--whole-spec", action="append")
    activate.add_argument("--whole-spec-reason")
    activate.add_argument("--section", action="append")
    activate.add_argument(
        "--capsule-budget-bytes",
        type=int,
        default=DEFAULT_CAPSULE_BUDGET_BYTES,
    )
    activate.add_argument("--capsule-budget-reason")
    activate.add_argument("--none", action="store_true")
    activate.add_argument("--reason")
    activate.set_defaults(handler=command_activate)

    preflight = commands.add_parser(
        "preflight",
        help="Check exact intended files and expected Requirements before edits",
    )
    preflight.add_argument("--adapter-id", required=True)
    preflight.add_argument("--session-id", required=True)
    preflight.add_argument("--turn-id", required=True)
    preflight.add_argument("--path", action="append", required=True)
    preflight.add_argument("--expect-requirement", action="append")
    preflight.set_defaults(handler=command_preflight)

    status = commands.add_parser("status", help="Show the current turn receipt")
    status.add_argument("--adapter-id", required=True)
    status.add_argument("--session-id", required=True)
    status.add_argument("--turn-id", required=True)
    status.set_defaults(handler=command_status)

    evidence = commands.add_parser(
        "evidence",
        help="Export verified Requirement activation evidence without source text",
    )
    evidence.add_argument("--adapter-id", required=True)
    evidence.add_argument("--session-id", required=True)
    evidence.add_argument("--turn-id", required=True)
    evidence.set_defaults(handler=command_evidence)

    rehydrate = commands.add_parser(
        "rehydrate",
        help="Start a new context epoch and rehydrate the exact capsule",
    )
    rehydrate.add_argument("--adapter-id", required=True)
    rehydrate.add_argument("--session-id", required=True)
    rehydrate.add_argument("--turn-id", required=True)
    rehydrate.set_defaults(handler=command_rehydrate)

    audit = commands.add_parser("audit", help="Audit changed paths and optional handoff")
    audit.add_argument("--adapter-id", required=True)
    audit.add_argument("--session-id", required=True)
    audit.add_argument("--turn-id", required=True)
    audit_message = audit.add_mutually_exclusive_group()
    audit_message.add_argument("--message")
    audit_message.add_argument("--message-file")
    audit.set_defaults(handler=command_audit)

    event = commands.add_parser(
        "event",
        help="Handle one normalized RepoFoundry activation event from stdin",
    )
    event.set_defaults(handler=command_event)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except RouterError as exc:
        print(f"spec-router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
