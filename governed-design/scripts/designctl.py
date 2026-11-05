#!/usr/bin/env python3
"""Deterministic lifecycle and integrity operations for technical Designs."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


SKILL_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = SKILL_DIR / "assets"
EXECUTION_PLAN_CTL = (
    SKILL_DIR.parent / "engineering-execution-plan" / "scripts" / "epctl.py"
)
STATE_VERSION = 1
CURRENT_SCHEMA = "1.1"
CURRENT_METADATA_SCHEMA = "1"
MANIFEST_NAME = "DESIGN_MANIFEST.json"
INIT_DIRECTORIES = ("docs/.designctl", "docs/design-docs")
INIT_FILES = ("docs/.designctl/state.json", "docs/DESIGN-DOCS.md")
INDEX_START = "<!-- DESIGNCTL:INDEX:START -->"
INDEX_END = "<!-- DESIGNCTL:INDEX:END -->"
READING_START = "<!-- DESIGNCTL:READING:START -->"
READING_END = "<!-- DESIGNCTL:READING:END -->"
MAP_START = "<!-- DESIGNCTL:MAP:START -->"
MAP_END = "<!-- DESIGNCTL:MAP:END -->"

DESIGN_ID_RE = re.compile(r"^DD-(\d{3,})$", re.IGNORECASE)
DOCUMENT_ID_RE = re.compile(r"^DOC-(\d{3,})$", re.IGNORECASE)
ADR_ID_RE = re.compile(r"^ADR-(\d{3,})$", re.IGNORECASE)
RESEARCH_ID_RE = re.compile(r"^R-(\d{3,})$", re.IGNORECASE)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_RE = re.compile(r"<!--\s*REQUIRED(?:_[A-Z_]+)?\s*:", re.IGNORECASE)

DESIGN_STATUSES = {
    "draft",
    "review_ready",
    "current",
    "revising",
    "abandoned",
    "superseded",
}
TERMINAL_STATUSES = {"abandoned", "superseded"}
DEPENDENCY_TYPES = {"uses", "extends", "implements", "replaces"}
MEMBER_ROLES = {
    "architecture",
    "concept",
    "component",
    "contributor-guide",
    "deep-dive",
    "extension",
    "interface",
    "data",
    "flow",
    "subsystem",
    "security",
    "operations",
    "migration",
    "verification",
    "appendix",
}
CURRENT_ROLE_DIRECTORIES = {
    "architecture": "core-concepts",
    "concept": "core-concepts",
    "component": "subsystems",
    "contributor-guide": "contributor-guide",
    "deep-dive": "deep-dives",
    "extension": "extension-points",
    "interface": "core-concepts",
    "data": "core-concepts",
    "flow": "how-it-works",
    "subsystem": "subsystems",
    "security": "deep-dives",
    "operations": "deep-dives",
    "migration": "deep-dives",
    "verification": "deep-dives",
    "appendix": "deep-dives",
}
LEGACY_ROLE_DIRECTORIES = {
    "architecture": "architecture",
    "concept": "architecture",
    "component": "architecture",
    "contributor-guide": "docs",
    "deep-dive": "docs",
    "extension": "contracts",
    "interface": "contracts",
    "data": "data",
    "flow": "architecture",
    "subsystem": "architecture",
    "security": "operations",
    "operations": "operations",
    "migration": "migration",
    "verification": "verification",
    "appendix": "docs",
}
CURRENT_MANAGED_DIRECTORIES = {
    "how-it-works",
    "core-concepts",
    "subsystems",
    "extension-points",
    "deep-dives",
    "contributor-guide",
}
LEGACY_MANAGED_DIRECTORIES = {
    "architecture",
    "contracts",
    "data",
    "docs",
    "operations",
    "migration",
    "verification",
}
MANAGED_DIRECTORIES = CURRENT_MANAGED_DIRECTORIES | LEGACY_MANAGED_DIRECTORIES
READING_MAP_PATHS = ("README.md", "docs/README.md")
ROOT_SECTIONS = (
    "Design Summary",
    "Goals and Non-goals",
    "Research and Decision Inputs",
    "System Context and Invariants",
    "Proposed Architecture",
    "Control and Data Flows",
    "Alternatives, Open Questions, and Revisit Triggers",
)
RESEARCH_SUBSECTIONS: tuple[str, ...] = ()
COMMON_METADATA_FIELDS = (
    "title",
    "status",
    "author",
    "owner",
    "created",
    "updated",
)


class DesignctlError(RuntimeError):
    """Raised when a Design operation would violate the file contract."""


@dataclass(frozen=True)
class DesignRecord:
    path: Path
    data: dict[str, str]

    @property
    def design_id(self) -> str:
        return self.data.get("id", "").upper()

    @property
    def schema(self) -> str:
        return self.data.get("schema_version", "1")

    @property
    def layout(self) -> str:
        if self.schema == CURRENT_SCHEMA:
            return self.data.get("layout", "")
        return "single"

    @property
    def package(self) -> Path:
        return self.path.parent


def load_logical_adr_data(
    repo: Path,
) -> dict[str, dict[str, str]] | None:
    """Load the canonical logical ADR corpus when the bundled engine exists."""
    if not EXECUTION_PLAN_CTL.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        "_repo_foundry_designctl_epctl",
        EXECUTION_PLAN_CTL,
    )
    if spec is None or spec.loader is None:
        raise DesignctlError(
            "Unable to load bundled engineering-execution-plan component: "
            f"{EXECUTION_PLAN_CTL}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        resolver = getattr(module, "adr_corpus_data", None)
        if not callable(resolver):
            raise DesignctlError(
                "Bundled engineering-execution-plan component does not expose "
                "adr_corpus_data"
            )
        data = resolver(repo.resolve())
    except DesignctlError:
        sys.modules.pop(spec.name, None)
        raise
    except Exception as exc:
        sys.modules.pop(spec.name, None)
        raise DesignctlError(
            "Unable to resolve the logical ADR corpus through the bundled "
            f"engineering-execution-plan component: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise DesignctlError(
            "Bundled engineering-execution-plan adr_corpus_data returned an "
            "invalid corpus"
        )
    return data


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def date_string() -> str:
    return utc_now().date().isoformat()


def timestamp_string() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def normalize_repo(value: str) -> Path:
    repo = Path(value).expanduser().resolve()
    if not repo.is_dir():
        raise DesignctlError(f"Repository directory does not exist: {repo}")
    return repo


def validate_slug(value: str) -> str:
    if not SLUG_RE.fullmatch(value):
        raise DesignctlError(
            "Slug must be lowercase kebab-case, for example registry-api"
        )
    return value


def normalize_design_id(value: str) -> str:
    normalized = value.strip().upper()
    if not DESIGN_ID_RE.fullmatch(normalized):
        raise DesignctlError(f"Invalid Design ID: {value!r}")
    return normalized


def normalize_research_id(value: str) -> str:
    normalized = value.strip().upper()
    if not RESEARCH_ID_RE.fullmatch(normalized):
        raise DesignctlError(f"Invalid Research ID: {value!r}")
    return normalized


def normalize_adr_id(value: str) -> str:
    normalized = value.strip().upper()
    if not ADR_ID_RE.fullmatch(normalized):
        raise DesignctlError(f"Invalid ADR ID: {value!r}")
    return normalized


def normalize_dependency(value: str) -> str:
    raw = value.strip()
    if ":" not in raw:
        raw = f"uses:{raw}"
    kind, design_id = raw.split(":", 1)
    kind = kind.strip().lower()
    if kind not in DEPENDENCY_TYPES:
        raise DesignctlError(
            "Design dependency type must be one of: "
            + ", ".join(sorted(DEPENDENCY_TYPES))
        )
    return f"{kind}:{normalize_design_id(design_id)}"


def unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def asset_text(name: str) -> str:
    path = ASSET_DIR / name
    if not path.is_file():
        raise DesignctlError(f"Missing bundled asset: {path}")
    return path.read_text(encoding="utf-8")


def render_asset(name: str, values: dict[str, str]) -> str:
    text = asset_text(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", text)))
    if leftovers:
        raise DesignctlError(
            f"Unresolved template values in {name}: {', '.join(leftovers)}"
        )
    return text


def reject_symlink_path(repo: Path, path: Path) -> None:
    try:
        relative = path.relative_to(repo)
    except ValueError as exc:
        raise DesignctlError(f"Managed path escapes repository: {path}") from exc
    current = repo
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise DesignctlError(f"Refusing symbolic link: {current}")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = handle.name
    try:
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


@contextlib.contextmanager
def repo_lock(repo: Path):
    lock_path = repo / "docs" / ".designctl" / "lock"
    reject_symlink_path(repo, lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:  # pragma: no cover - Windows
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write("\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(?P<body>.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise DesignctlError("Missing or unclosed YAML frontmatter")
    data: dict[str, str] = {}
    for line_number, raw in enumerate(match.group("body").splitlines(), start=2):
        if "\t" in raw:
            raise DesignctlError(
                f"Tabs are not allowed in frontmatter (line {line_number})"
            )
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1].isspace() or ":" not in raw:
            raise DesignctlError(
                f"Only top-level key: value fields are supported (line {line_number})"
            )
        key, raw_value = raw.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise DesignctlError(
                f"Invalid frontmatter key {key!r} (line {line_number})"
            )
        value = raw_value.strip()
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError as exc:
                raise DesignctlError(
                    f"Invalid quoted scalar for {key!r} (line {line_number})"
                ) from exc
            if not isinstance(decoded, str):
                raise DesignctlError(f"{key!r} must be a scalar")
            value = decoded
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise DesignctlError(f"Invalid single-quoted scalar for {key!r}")
            value = value[1:-1].replace("''", "'")
        data[key] = value
    return data


def update_frontmatter(text: str, updates: dict[str, str]) -> str:
    match = re.match(
        r"\A---\n(?P<body>.*?)\n---\n(?P<rest>[\s\S]*)", text, re.DOTALL
    )
    if not match:
        raise DesignctlError("Missing or unclosed YAML frontmatter")
    remaining = dict(updates)
    lines: list[str] = []
    for line in match.group("body").splitlines():
        if line and not line[:1].isspace() and ":" in line:
            key = line.split(":", 1)[0].strip()
            if key in remaining:
                lines.append(f"{key}: {remaining.pop(key)}")
                continue
        lines.append(line)
    for key, value in remaining.items():
        lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---\n" + match.group("rest")


def json_list(data: dict[str, str], field: str) -> list[str]:
    raw = data.get(field, "[]").strip() or "[]"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DesignctlError(f"{field} must be a JSON array of strings") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DesignctlError(f"{field} must be a JSON array of strings")
    return value


def positive_int(data: dict[str, str], field: str, allow_zero: bool = False) -> int:
    raw = data.get(field, "")
    try:
        value = int(raw)
    except ValueError as exc:
        raise DesignctlError(f"{field} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise DesignctlError(f"{field} must be >= {minimum}")
    return value


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_path(repo: Path) -> Path:
    return repo / "docs" / ".designctl" / "state.json"


def load_state(repo: Path) -> dict[str, object]:
    path = state_path(repo)
    if not path.exists():
        return {"version": STATE_VERSION, "high_water": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignctlError(f"Invalid state file {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise DesignctlError(f"Unsupported state file: {path}")
    high_water = value.get("high_water")
    if not isinstance(high_water, dict) or any(
        not isinstance(key, str)
        or not isinstance(number, int)
        or isinstance(number, bool)
        or number < 0
        for key, number in high_water.items()
    ):
        raise DesignctlError(f"Invalid high_water map: {path}")
    return value


def save_state(repo: Path, value: dict[str, object]) -> None:
    atomic_write(
        state_path(repo),
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def safe_frontmatter(path: Path) -> dict[str, str] | None:
    try:
        return parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, DesignctlError):
        return None


def scan_designs(repo: Path) -> tuple[dict[str, DesignRecord], list[str]]:
    design_root = repo / "docs" / "design-docs"
    records: dict[str, DesignRecord] = {}
    errors: list[str] = []
    if not design_root.exists():
        return records, errors
    for path in sorted(design_root.rglob("*.md")):
        relative_parts = path.relative_to(design_root).parts
        if "snapshots" in relative_parts or "artifacts" in relative_parts:
            continue
        data = safe_frontmatter(path)
        if not data or data.get("artifact_type") != "design-doc":
            continue
        design_id = data.get("id", "").upper()
        if not DESIGN_ID_RE.fullmatch(design_id):
            errors.append(f"{path}: invalid Design id {data.get('id', '')!r}")
            continue
        if design_id in records:
            errors.append(
                f"duplicate Design id {design_id}: {records[design_id].path} and {path}"
            )
            continue
        records[design_id] = DesignRecord(path=path, data=data)
    return records, errors


def find_design(repo: Path, design_id: str) -> DesignRecord:
    normalized = normalize_design_id(design_id)
    records, errors = scan_designs(repo)
    if errors:
        raise DesignctlError("; ".join(errors))
    record = records.get(normalized)
    if record is None:
        raise DesignctlError(f"Design not found: {normalized}")
    return record


def next_design_id(repo: Path) -> str:
    state = load_state(repo)
    high_water = state["high_water"]
    assert isinstance(high_water, dict)
    records, errors = scan_designs(repo)
    if errors:
        raise DesignctlError("; ".join(errors))
    scanned = [int(DESIGN_ID_RE.fullmatch(value).group(1)) for value in records]
    number = max(max(scanned, default=0), int(high_water.get("DD", 0))) + 1
    high_water["DD"] = number
    save_state(repo, state)
    return f"DD-{number:03d}"


def scan_document_numbers(package: Path, design_id: str) -> set[int]:
    values: set[int] = set()
    for path in package.rglob("*.md"):
        if "snapshots" in path.relative_to(package).parts:
            continue
        data = safe_frontmatter(path)
        if not data or data.get("design_id", "").upper() != design_id:
            continue
        match = DOCUMENT_ID_RE.fullmatch(data.get("document_id", "").upper())
        if match:
            values.add(int(match.group(1)))
    return values


def next_document_id(repo: Path, record: DesignRecord) -> str:
    state = load_state(repo)
    high_water = state["high_water"]
    assert isinstance(high_water, dict)
    key = f"DOC:{record.design_id}"
    number = max(
        max(scan_document_numbers(record.package, record.design_id), default=0),
        int(high_water.get(key, 0)),
    ) + 1
    high_water[key] = number
    save_state(repo, state)
    return f"DOC-{number:03d}"


def initialize_state_high_water(repo: Path) -> None:
    state = load_state(repo)
    high_water = state["high_water"]
    assert isinstance(high_water, dict)
    records, errors = scan_designs(repo)
    if errors:
        raise DesignctlError("; ".join(errors))
    maximum = max(
        (
            int(DESIGN_ID_RE.fullmatch(design_id).group(1))
            for design_id in records
        ),
        default=0,
    )
    high_water["DD"] = max(int(high_water.get("DD", 0)), maximum)
    for record in records.values():
        if record.layout != "package":
            continue
        key = f"DOC:{record.design_id}"
        maximum_doc = max(
            scan_document_numbers(record.package, record.design_id), default=0
        )
        high_water[key] = max(int(high_water.get(key, 0)), maximum_doc)
    save_state(repo, state)


def init_repo(repo: Path) -> list[str]:
    created: list[str] = []
    for relative in INIT_DIRECTORIES:
        path = repo / relative
        reject_symlink_path(repo, path)
        if not path.exists():
            path.mkdir(parents=True)
            created.append(relative + "/")
    if not state_path(repo).exists():
        save_state(repo, {"version": STATE_VERSION, "high_water": {}})
        created.append("docs/.designctl/state.json")
    initialize_state_high_water(repo)
    index = repo / "docs" / "DESIGN-DOCS.md"
    if not index.exists():
        atomic_write(index, asset_text("design-index.md"))
        created.append("docs/DESIGN-DOCS.md")
    return created


def replace_generated_region(
    text: str, start: str, end: str, body: str
) -> tuple[str, bool]:
    start_count = text.count(start)
    end_count = text.count(end)
    if start_count != 1 or end_count != 1 or text.index(start) > text.index(end):
        return text, False
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return f"{before}{start}\n{body.rstrip()}\n{end}{after}", True


def section_body(text: str, heading: str, level: int = 2) -> str | None:
    hashes = "#" * level
    pattern = re.compile(
        rf"(?ms)^{re.escape(hashes)} {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^{re.escape(hashes)} |\Z)"
    )
    match = pattern.search(text)
    return match.group("body").strip() if match else None


def substantive(body: str | None) -> bool:
    if body is None or REQUIRED_RE.search(body):
        return False
    visible = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    visible = re.sub(r"(?m)^#{1,6}\s+.*$", "", visible)
    visible = re.sub(r"[`*_>|#\-]", " ", visible)
    visible = re.sub(r"\s+", " ", visible).strip()
    if re.search(r"(?i)not applicable\s*:\s*.{12,}", visible):
        return True
    return len(visible) >= 24


def locate_artifact(
    root: Path, filename: str, expected_id: str
) -> tuple[Path, dict[str, str]] | None:
    matches: list[tuple[Path, dict[str, str]]] = []
    if not root.exists():
        return None
    for path in root.rglob(filename):
        if "snapshots" in path.parts:
            continue
        data = safe_frontmatter(path)
        if data and data.get("id", "").upper() == expected_id:
            matches.append((path, data))
    if len(matches) > 1:
        raise DesignctlError(
            f"Duplicate artifact identity {expected_id}: "
            + ", ".join(str(path) for path, _ in matches)
        )
    return matches[0] if matches else None


def markdown_body_sha256(text: str) -> str:
    match = re.match(r"\A---\n.*?\n---\n", text, re.DOTALL)
    if not match:
        raise DesignctlError("Missing or unclosed YAML frontmatter")
    return sha256_bytes(text[match.end() :].encode("utf-8"))


def research_manifest_digest(value: dict[str, object]) -> str:
    payload = json.loads(json.dumps(value))
    payload["payload_sha256"] = ""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def research_manifest_document(
    repo: Path,
    package: Path,
    locator: dict[str, object],
) -> Path:
    base = locator.get("base")
    raw_path = locator.get("path")
    if base not in {"repo", "package"} or not isinstance(raw_path, str):
        raise DesignctlError(f"invalid Research manifest locator: {locator!r}")
    relative = Path(raw_path)
    if relative.is_absolute() or any(
        component in {"", ".", ".."} for component in relative.parts
    ):
        raise DesignctlError(f"unsafe Research manifest path: {raw_path!r}")
    candidate = (repo if base == "repo" else package) / relative
    reject_symlink_path(repo, candidate)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
    except FileNotFoundError as exc:
        raise DesignctlError(
            f"Research manifest document does not exist: {candidate}"
        ) from exc
    except ValueError as exc:
        raise DesignctlError(
            f"Research manifest document escapes repository: {candidate}"
        ) from exc
    if not resolved.is_file():
        raise DesignctlError(f"Research manifest document is not a file: {candidate}")
    return resolved


def validate_sealed_research_manifest(
    repo: Path,
    path: Path,
    research_id: str,
) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path}: missing Research manifest"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid Research manifest: {exc}"]
    if not isinstance(manifest, dict):
        return [f"{path}: Research manifest must be an object"]
    if manifest.get("schema_version") not in {"1", "1.1"}:
        errors.append(f"{path}: unsupported Research manifest schema")
    if manifest.get("research_id") != research_id:
        errors.append(f"{path}: research_id must be {research_id}")
    if manifest.get("status") != "sealed":
        errors.append(f"{path}: concluded Research requires sealed manifest")
    expected_digest = manifest.get("payload_sha256")
    actual_digest = research_manifest_digest(manifest)
    if not isinstance(expected_digest, str) or not expected_digest:
        errors.append(f"{path}: sealed manifest requires payload_sha256")
    elif expected_digest != actual_digest:
        errors.append(f"{path}: sealed Research manifest payload changed")

    documents = manifest.get("documents")
    entrypoints = manifest.get("entrypoints")
    if not isinstance(documents, list):
        errors.append(f"{path}: documents must be an array")
        documents = []
    if not isinstance(entrypoints, list):
        errors.append(f"{path}: entrypoints must be an array")
        entrypoints = []
    seen: set[tuple[str, str]] = set()
    for document in documents:
        if not isinstance(document, dict):
            errors.append(f"{path}: manifest document must be an object")
            continue
        key = (str(document.get("base")), str(document.get("path")))
        if key in seen:
            errors.append(f"{path}: duplicate manifest document {key}")
        seen.add(key)
        if document.get("base") != "package":
            errors.append(f"{path}: concluded manifest documents must be package-relative")
        try:
            document_path = research_manifest_document(repo, path.parent, document)
        except DesignctlError as exc:
            errors.append(f"{path}: {exc}")
            continue
        payload = document_path.read_bytes()
        if document.get("bytes") != len(payload):
            errors.append(f"{document_path}: sealed document size changed")
        if document.get("sha256") != sha256_bytes(payload):
            errors.append(f"{document_path}: sealed document digest changed")
    declared_entrypoints = {
        (str(item.get("base")), str(item.get("path")))
        for item in entrypoints
        if isinstance(item, dict)
    }
    missing_entrypoints = declared_entrypoints - seen
    if missing_entrypoints:
        errors.append(f"{path}: entrypoints are absent from documents")
    return errors


def validate_research_reference(repo: Path, research_id: str) -> list[str]:
    located = locate_artifact(
        repo / "docs" / "research", "RESEARCH.md", normalize_research_id(research_id)
    )
    if located is None:
        return [f"Research not found: {research_id}"]
    path, data = located
    errors: list[str] = []
    if data.get("status") != "concluded":
        errors.append(f"{path}: Research {research_id} must be concluded")
    schema = data.get("schema_version", "1")
    if schema in {"1.1", "1.2"}:
        if data.get("maturity") != "review_ready":
            errors.append(f"{path}: concluded Research must have review_ready maturity")
        for field in ("owner", "approved_by", "approved_at", "approval_ref"):
            if not data.get(field, "").strip():
                errors.append(f"{path}: concluded Research requires {field}")
    synthesis_name = data.get("synthesis", "SYNTHESIS.md") or "SYNTHESIS.md"
    if synthesis_name != "SYNTHESIS.md":
        errors.append(f"{path}: synthesis must be SYNTHESIS.md")
    synthesis = path.parent / "SYNTHESIS.md"
    if not synthesis.is_file():
        errors.append(f"{path}: concluded Research is missing SYNTHESIS.md")
    else:
        try:
            synthesis_text = synthesis.read_text(encoding="utf-8")
            synthesis_data = parse_frontmatter(synthesis_text)
        except (OSError, UnicodeDecodeError, DesignctlError) as exc:
            errors.append(f"{synthesis}: invalid Synthesis: {exc}")
        else:
            if synthesis_data.get("parent_id") != research_id:
                errors.append(f"{synthesis}: parent_id must be {research_id}")
            if synthesis_data.get("status") != "sealed":
                errors.append(f"{synthesis}: concluded Research requires sealed Synthesis")
            expected = synthesis_data.get("payload_sha256", "")
            actual = markdown_body_sha256(synthesis_text)
            if not expected or expected != actual:
                errors.append(f"{synthesis}: sealed Synthesis payload changed")
    manifest_name = data.get("manifest", "")
    if manifest_name:
        if manifest_name != "RESEARCH_MANIFEST.json":
            errors.append(f"{path}: manifest must be RESEARCH_MANIFEST.json")
        else:
            errors.extend(
                validate_sealed_research_manifest(
                    repo,
                    path.parent / manifest_name,
                    research_id,
                )
            )
    return errors


def validate_adr_reference(
    repo: Path,
    adr_id: str,
    require_current: bool,
    *,
    logical_adr_data: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    normalized_adr_id = normalize_adr_id(adr_id)
    located = locate_artifact(
        repo / "docs" / "adr", "*.md", normalized_adr_id
    )
    if located is not None:
        path, data = located
        source = str(path)
    elif logical_adr_data is not None and normalized_adr_id in logical_adr_data:
        data = logical_adr_data[normalized_adr_id]
        source = f"History Pack entry {normalized_adr_id}"
    else:
        return [f"ADR not found: {adr_id}"]
    if require_current and data.get("status") != "accepted":
        return [
            f"{source}: ADR {adr_id} is not current accepted architecture"
        ]
    if data.get("status") not in {
        "proposed",
        "accepted",
        "rejected",
        "under_review",
        "retired",
        "superseded",
    }:
        return [f"{source}: invalid ADR status {data.get('status', '')!r}"]
    return []


def managed_markdown_paths(record: DesignRecord) -> list[Path]:
    result: list[Path] = [record.path]
    root_readme = record.package / "README.md"
    if root_readme.is_file():
        result.append(root_readme)
    for directory in sorted(MANAGED_DIRECTORIES):
        root = record.package / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if "snapshots" not in path.relative_to(record.package).parts:
                result.append(path)
    return unique_paths(result)


def reading_map_relative_path(documents: list[dict[str, object]]) -> str:
    matches = [
        str(item["path"])
        for item in documents
        if item.get("role") == "reading-map"
    ]
    if len(matches) == 1 and matches[0] in READING_MAP_PATHS:
        return matches[0]
    return "README.md"


def role_directory(record: DesignRecord, role: str) -> str:
    mapping = (
        CURRENT_ROLE_DIRECTORIES
        if (record.package / "README.md").is_file()
        else LEGACY_ROLE_DIRECTORIES
    )
    return mapping[role]


def unique_paths(values: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def validate_member_metadata(
    record: DesignRecord, path: Path, data: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    document_id = data.get("document_id", "").upper()
    expected_id = f"{record.design_id}/{document_id}"
    if data.get("schema_version") != CURRENT_SCHEMA:
        errors.append(f"{path}: member schema_version must be {CURRENT_SCHEMA!r}")
    if data.get("metadata_schema") != CURRENT_METADATA_SCHEMA:
        errors.append(f"{path}: metadata_schema must be '1'")
    if data.get("artifact_type") != "design-member":
        errors.append(f"{path}: artifact_type must be 'design-member'")
    if data.get("design_id", "").upper() != record.design_id:
        errors.append(f"{path}: design_id must be {record.design_id}")
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        errors.append(f"{path}: invalid document_id {document_id!r}")
    if data.get("id", "").upper() != expected_id:
        errors.append(f"{path}: id must be {expected_id}")
    role = data.get("role", "")
    if role not in MEMBER_ROLES | {"reading-map"}:
        errors.append(f"{path}: invalid member role {role!r}")
    for field in COMMON_METADATA_FIELDS:
        if not data.get(field, "").strip():
            errors.append(f"{path}: metadata field {field} must be non-empty")
    return errors


def collect_package_documents(
    record: DesignRecord, root_override: bytes | None = None
) -> tuple[list[dict[str, object]], list[str]]:
    errors: list[str] = []
    documents: list[dict[str, object]] = []
    root_payload = root_override if root_override is not None else record.path.read_bytes()
    documents.append(
        {
            "id": record.design_id,
            "role": "entrypoint",
            "path": "DESIGN.md",
            "title": record.data.get("title", ""),
            "bytes": len(root_payload),
            "sha256": sha256_bytes(root_payload),
        }
    )
    seen_ids: dict[str, Path] = {}
    for path in managed_markdown_paths(record):
        if path == record.path:
            continue
        try:
            reject_symlink_path(record.package.parent.parent.parent, path)
        except DesignctlError as exc:
            errors.append(str(exc))
            continue
        try:
            relative = path.relative_to(record.package).as_posix()
        except ValueError:
            errors.append(f"{path}: package member escapes {record.package}")
            continue
        try:
            data = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, DesignctlError) as exc:
            errors.append(f"{path}: invalid managed Markdown: {exc}")
            continue
        errors.extend(validate_member_metadata(record, path, data))
        document_id = data.get("document_id", "").upper()
        if document_id in seen_ids:
            errors.append(
                f"duplicate package document id {document_id}: "
                f"{seen_ids[document_id]} and {path}"
            )
            continue
        seen_ids[document_id] = path
        payload = path.read_bytes()
        documents.append(
            {
                "id": document_id,
                "role": data.get("role", ""),
                "path": relative,
                "title": data.get("title", ""),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )
    documents[1:] = sorted(
        documents[1:],
        key=lambda item: int(DOCUMENT_ID_RE.fullmatch(str(item["id"])).group(1))
        if DOCUMENT_ID_RE.fullmatch(str(item["id"]))
        else 10**9,
    )
    reading = [item for item in documents if item["role"] == "reading-map"]
    if len(reading) != 1 or reading[0].get("path") not in READING_MAP_PATHS:
        errors.append(
            f"{record.package}: package must contain exactly one reading-map at "
            "README.md or legacy docs/README.md"
        )
    return documents, errors


def manifest_object(
    record: DesignRecord,
    *,
    data_override: dict[str, str] | None = None,
    root_override: bytes | None = None,
) -> tuple[dict[str, object], list[str]]:
    data = data_override or record.data
    proxy = DesignRecord(record.path, data)
    documents, errors = collect_package_documents(proxy, root_override=root_override)
    try:
        dependencies = [normalize_dependency(item) for item in json_list(data, "design_dependencies")]
        working = positive_int(data, "working_revision")
        published = positive_int(data, "published_revision", allow_zero=True)
    except DesignctlError as exc:
        errors.append(f"{record.path}: {exc}")
        dependencies = []
        working = 0
        published = 0
    result: dict[str, object] = {
        "schema_version": "1",
        "metadata_schema": CURRENT_METADATA_SCHEMA,
        "artifact_type": "design-manifest",
        "id": f"{record.design_id}-MANIFEST",
        "design_id": record.design_id,
        "title": f"{data.get('title', '')} — Design manifest",
        "status": data.get("status", ""),
        "layout": "package",
        "author": data.get("author", ""),
        "owner": data.get("owner", ""),
        "created": data.get("created", ""),
        "updated": data.get("updated", ""),
        "working_revision": working,
        "published_revision": published,
        "entrypoint": "DESIGN.md",
        "reading_map": reading_map_relative_path(documents),
        "design_dependencies": dependencies,
        "documents": documents,
    }
    return result, errors


def manifest_text(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def manifest_digest(value: dict[str, object]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def package_map_body(documents: list[dict[str, object]]) -> str:
    rows = [
        "| Stable reference | Role | Path | Title |",
        "|---|---|---|---|",
    ]
    for item in documents:
        stable = str(item["id"])
        if stable.startswith("DOC-"):
            stable = f"{documents[0]['id']}/{stable}"
        rows.append(
            f"| `{stable}` | `{item['role']}` | `{item['path']}` | {item['title']} |"
        )
    return "\n".join(rows)


def reading_map_body(
    record: DesignRecord,
    documents: list[dict[str, object]],
    reading_path: Path,
) -> str:
    rows = [
        "| Review route | Stable reference | Document |",
        "|---|---|---|",
    ]
    for item in documents:
        if item["role"] in {"entrypoint", "reading-map"}:
            continue
        target = os.path.relpath(
            str(item["path"]),
            start=reading_path.relative_to(record.package).parent.as_posix() or ".",
        )
        rows.append(
            f"| {item['role']} | `{record.design_id}/{item['id']}` | "
            f"[{item['title']}]({target}) |"
        )
    if len(rows) == 2:
        return "No focused member documents yet."
    return "\n".join(rows)


def sync_package(repo: Path, record: DesignRecord, force: bool = False) -> list[str]:
    if record.schema != CURRENT_SCHEMA or record.layout != "package":
        raise DesignctlError(f"{record.design_id} is not a schema-{CURRENT_SCHEMA} package")
    if not force and record.data.get("status") not in {"draft", "revising"}:
        raise DesignctlError(
            f"sync requires draft or revising status; {record.design_id} is "
            f"{record.data.get('status', '')}"
        )
    warnings: list[str] = []
    documents, errors = collect_package_documents(record)
    if errors:
        raise DesignctlError("\n".join(errors))

    reading_path = record.package / reading_map_relative_path(documents)
    reading_text = reading_path.read_text(encoding="utf-8")
    updated, managed = replace_generated_region(
        reading_text,
        READING_START,
        READING_END,
        reading_map_body(record, documents, reading_path),
    )
    if managed:
        if updated != reading_text:
            atomic_write(reading_path, updated)
    else:
        warnings.append(f"{reading_path}: reading map has no managed marker region")

    root_text = record.path.read_text(encoding="utf-8")
    documents, errors = collect_package_documents(record)
    if errors:
        raise DesignctlError("\n".join(errors))
    updated, managed = replace_generated_region(
        root_text, MAP_START, MAP_END, package_map_body(documents)
    )
    if managed:
        if updated != root_text:
            atomic_write(record.path, updated)
            record = DesignRecord(record.path, parse_frontmatter(updated))
    else:
        warnings.append(f"{record.path}: package map has no managed marker region")

    manifest, errors = manifest_object(record)
    if errors:
        raise DesignctlError("\n".join(errors))
    atomic_write(record.package / MANIFEST_NAME, manifest_text(manifest))
    return warnings


def read_manifest(record: DesignRecord) -> dict[str, object]:
    path = record.package / MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DesignctlError(f"Missing package manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DesignctlError(f"Invalid package manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignctlError(f"Package manifest must be an object: {path}")
    return value


def validate_manifest(record: DesignRecord) -> list[str]:
    errors: list[str] = []
    try:
        actual = read_manifest(record)
    except DesignctlError as exc:
        return [str(exc)]
    expected, collection_errors = manifest_object(record)
    errors.extend(collection_errors)
    if actual != expected:
        errors.append(
            f"{record.package / MANIFEST_NAME}: manifest drift; run designctl sync {record.design_id}"
        )
    return errors


def dependency_target(value: str) -> str:
    return normalize_dependency(value).split(":", 1)[1]


def design_is_published(record: DesignRecord) -> bool:
    if record.schema != CURRENT_SCHEMA:
        return record.data.get("status") not in TERMINAL_STATUSES
    try:
        return positive_int(record.data, "published_revision", allow_zero=True) > 0
    except DesignctlError:
        return False


def validate_dependency_graph(records: dict[str, DesignRecord]) -> list[str]:
    errors: list[str] = []
    graph: dict[str, list[str]] = {}
    for design_id, record in records.items():
        if record.schema != CURRENT_SCHEMA:
            graph[design_id] = []
            continue
        try:
            dependencies = [
                dependency_target(item)
                for item in json_list(record.data, "design_dependencies")
            ]
        except DesignctlError as exc:
            errors.append(f"{record.path}: {exc}")
            dependencies = []
        graph[design_id] = dependencies
        for dependency in dependencies:
            if dependency == design_id:
                errors.append(f"{record.path}: Design cannot depend on itself")
            elif dependency not in records:
                errors.append(f"{record.path}: Design dependency not found: {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            cycle = trail[trail.index(node) :] + [node]
            errors.append("Design dependency cycle: " + " -> ".join(cycle))
            return
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, []):
            if target in graph:
                visit(target, trail + [target])
        visiting.remove(node)
        visited.add(node)

    for design_id in graph:
        visit(design_id, [design_id])
    return unique(errors)


def validate_supersession_graph(records: dict[str, DesignRecord]) -> list[str]:
    errors: list[str] = []
    graph: dict[str, str] = {}
    for design_id, record in records.items():
        target = record.data.get("superseded_by", "").upper()
        if target:
            if not DESIGN_ID_RE.fullmatch(target):
                errors.append(f"{record.path}: invalid superseded_by {target!r}")
            elif target not in records:
                errors.append(f"{record.path}: superseding Design not found: {target}")
            else:
                graph[design_id] = target
    for start in graph:
        seen: list[str] = []
        current = start
        while current in graph:
            if current in seen:
                cycle = seen[seen.index(current) :] + [current]
                errors.append("Design supersession cycle: " + " -> ".join(cycle))
                break
            seen.append(current)
            current = graph[current]
    return unique(errors)


def validate_snapshot(record: DesignRecord) -> list[str]:
    errors: list[str] = []
    try:
        revision = positive_int(record.data, "published_revision", allow_zero=True)
    except DesignctlError as exc:
        return [f"{record.path}: {exc}"]
    if revision == 0:
        return errors
    if not all(
        record.data.get(field, "").strip()
        for field in ("approved_by", "approved_at", "approval_ref")
    ):
        errors.append(f"{record.path}: published Design lacks explicit approval metadata")
    if record.layout == "package":
        snapshot = record.package / "snapshots" / f"rev-{revision:03d}"
        manifest_path = snapshot / MANIFEST_NAME
        if not manifest_path.is_file():
            return errors + [f"{record.path}: missing published snapshot {manifest_path}"]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return errors + [f"{manifest_path}: invalid JSON: {exc}"]
        documents = manifest.get("documents") if isinstance(manifest, dict) else None
        if not isinstance(documents, list):
            return errors + [f"{manifest_path}: documents must be an array"]
        for item in documents:
            if not isinstance(item, dict):
                errors.append(f"{manifest_path}: document entry must be an object")
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str):
                errors.append(f"{manifest_path}: document path must be a string")
                continue
            source = snapshot / raw_path
            try:
                source.resolve().relative_to(snapshot.resolve())
            except ValueError:
                errors.append(f"{manifest_path}: snapshot path escapes: {raw_path}")
                continue
            if not source.is_file():
                errors.append(f"{manifest_path}: snapshot member missing: {raw_path}")
                continue
            payload = source.read_bytes()
            if item.get("bytes") != len(payload):
                errors.append(f"{manifest_path}: byte drift for {raw_path}")
            if item.get("sha256") != sha256_bytes(payload):
                errors.append(f"{manifest_path}: digest drift for {raw_path}")
    else:
        snapshot_directory = (
            record.path.parents[1]
            / ".designctl"
            / "snapshots"
            / record.design_id
            / f"rev-{revision:03d}"
        )
        snapshot = snapshot_directory / "DESIGN.md"
        manifest_path = snapshot_directory / MANIFEST_NAME
        if not snapshot.is_file() or not manifest_path.is_file():
            errors.append(
                f"{record.path}: missing published snapshot bundle {snapshot_directory}"
            )
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{manifest_path}: invalid JSON: {exc}")
            else:
                documents = (
                    manifest.get("documents") if isinstance(manifest, dict) else None
                )
                if not isinstance(documents, list) or len(documents) != 1:
                    errors.append(
                        f"{manifest_path}: single revision must declare one document"
                    )
                elif not isinstance(documents[0], dict):
                    errors.append(
                        f"{manifest_path}: document entry must be an object"
                    )
                else:
                    item = documents[0]
                    payload = snapshot.read_bytes()
                    if item.get("bytes") != len(payload):
                        errors.append(f"{manifest_path}: byte drift for DESIGN.md")
                    if item.get("sha256") != sha256_bytes(payload):
                        errors.append(f"{manifest_path}: digest drift for DESIGN.md")
    return errors


def validate_root_metadata(record: DesignRecord) -> list[str]:
    path = record.path
    data = record.data
    errors: list[str] = []
    if data.get("metadata_schema") != CURRENT_METADATA_SCHEMA:
        errors.append(f"{path}: metadata_schema must be '1'")
    if data.get("artifact_type") != "design-doc":
        errors.append(f"{path}: artifact_type must be 'design-doc'")
    if data.get("id", "").upper() != record.design_id:
        errors.append(f"{path}: invalid Design identity")
    for field in COMMON_METADATA_FIELDS:
        if not data.get(field, "").strip():
            errors.append(f"{path}: metadata field {field} must be non-empty")
    for field in ("created", "updated"):
        try:
            dt.date.fromisoformat(data.get(field, ""))
        except ValueError:
            errors.append(f"{path}: {field} must be an ISO date")
    return errors


def validate_design_record(
    repo: Path,
    record: DesignRecord,
    records: dict[str, DesignRecord],
    *,
    for_review: bool = False,
    logical_adr_data: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    data = record.data
    path = record.path
    if record.schema == "1":
        legacy_status = data.get("status", "")
        if legacy_status in TERMINAL_STATUSES:
            warnings.append(f"{path}: legacy Design is terminal: {legacy_status}")
        elif legacy_status != "current":
            warnings.append(
                f"{path}: legacy Design is unpublished: {legacy_status or 'unknown'}"
            )
        return errors, warnings
    if record.schema != CURRENT_SCHEMA:
        return [f"{path}: unsupported Design schema {record.schema!r}"], warnings

    errors.extend(validate_root_metadata(record))
    status = data.get("status", "")
    if status not in DESIGN_STATUSES:
        errors.append(f"{path}: invalid Design status {status!r}")
    if record.layout not in {"single", "package"}:
        errors.append(f"{path}: layout must be 'single' or 'package'")
    if record.layout == "single" and path.parent != repo / "docs" / "design-docs":
        errors.append(f"{path}: single Design must be directly under docs/design-docs")
    if record.layout == "package" and path.name != "DESIGN.md":
        errors.append(f"{path}: package entrypoint must be DESIGN.md")
    try:
        working = positive_int(data, "working_revision")
        published = positive_int(data, "published_revision", allow_zero=True)
        if published > working:
            errors.append(f"{path}: published_revision exceeds working_revision")
        if status == "current" and working != published:
            errors.append(f"{path}: current Design must publish its working revision")
        if status in {"draft", "review_ready"} and published == 0 and working != 1:
            errors.append(f"{path}: first unpublished Design must use working revision 1")
        if status in {"revising", "review_ready"} and published > 0 and working <= published:
            errors.append(f"{path}: revised working revision must exceed publication")
    except DesignctlError as exc:
        errors.append(f"{path}: {exc}")

    try:
        research_refs = [normalize_research_id(item) for item in json_list(data, "research_refs")]
    except DesignctlError as exc:
        errors.append(f"{path}: {exc}")
        research_refs = []
    reason = data.get("research_not_required_reason", "").strip()
    if bool(research_refs) == bool(reason):
        errors.append(
            f"{path}: exactly one of research_refs or research_not_required_reason is required"
        )
    if reason and len(reason) < 16:
        errors.append(f"{path}: research_not_required_reason is not concrete enough")
    if for_review or status in {"review_ready", "current", "revising"}:
        for research_id in research_refs:
            errors.extend(validate_research_reference(repo, research_id))

    try:
        adr_refs = [normalize_adr_id(item) for item in json_list(data, "adr_refs")]
    except DesignctlError as exc:
        errors.append(f"{path}: {exc}")
        adr_refs = []
    require_current = for_review or status in {"review_ready", "current"}
    for adr_id in adr_refs:
        errors.extend(
            validate_adr_reference(
                repo,
                adr_id,
                require_current,
                logical_adr_data=logical_adr_data,
            )
        )
    if require_current and not adr_refs and not data.get(
        "decision_not_required_reason", ""
    ).strip():
        errors.append(
            f"{path}: reviewable Design needs current adr_refs or decision_not_required_reason"
        )

    try:
        dependencies = [normalize_dependency(item) for item in json_list(data, "design_dependencies")]
    except DesignctlError as exc:
        errors.append(f"{path}: {exc}")
        dependencies = []
    if for_review or status in {"review_ready", "current"}:
        for dependency in dependencies:
            target_id = dependency_target(dependency)
            target = records.get(target_id)
            if target is None:
                continue
            if target.data.get("status") in TERMINAL_STATUSES or not design_is_published(target):
                errors.append(
                    f"{path}: dependency {target_id} has no consumable current publication"
                )

    if record.layout == "package":
        errors.extend(validate_manifest(record))

    if for_review or status in {"review_ready", "current"}:
        text = path.read_text(encoding="utf-8")
        for heading in ROOT_SECTIONS:
            if not substantive(section_body(text, heading)):
                errors.append(f"{path}: section {heading!r} lacks substantive coverage")
        for heading in RESEARCH_SUBSECTIONS:
            if not substantive(section_body(text, heading, level=3)):
                errors.append(f"{path}: subsection {heading!r} lacks substantive handoff")
        for member in managed_markdown_paths(record) if record.layout == "package" else [path]:
            if REQUIRED_RE.search(member.read_text(encoding="utf-8")):
                errors.append(f"{member}: unresolved REQUIRED marker")
    elif REQUIRED_RE.search(path.read_text(encoding="utf-8")):
        warnings.append(f"{path}: Design draft contains unresolved REQUIRED markers")

    if status in TERMINAL_STATUSES and not data.get("terminal_reason", "").strip():
        errors.append(f"{path}: terminal Design requires terminal_reason")
    if status == "superseded" and not data.get("superseded_by", "").strip():
        errors.append(f"{path}: superseded Design requires superseded_by")
    errors.extend(validate_snapshot(record))
    return unique(errors), unique(warnings)


def validate_repo(
    repo: Path,
    *,
    logical_adr_data: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    if logical_adr_data is None:
        logical_adr_data = load_logical_adr_data(repo)
    records, errors = scan_designs(repo)
    warnings: list[str] = []
    errors.extend(validate_dependency_graph(records))
    errors.extend(validate_supersession_graph(records))
    for record in records.values():
        item_errors, item_warnings = validate_design_record(
            repo,
            record,
            records,
            logical_adr_data=logical_adr_data,
        )
        errors.extend(item_errors)
        warnings.extend(item_warnings)
    try:
        state = load_state(repo)
        high_water = state["high_water"]
        assert isinstance(high_water, dict)
        maximum = max(
            (int(DESIGN_ID_RE.fullmatch(value).group(1)) for value in records),
            default=0,
        )
        if int(high_water.get("DD", 0)) < maximum:
            errors.append(f"{state_path(repo)}: DD high-water mark is below registered IDs")
        for record in records.values():
            if record.layout != "package":
                continue
            key = f"DOC:{record.design_id}"
            maximum_doc = max(
                scan_document_numbers(record.package, record.design_id), default=0
            )
            if int(high_water.get(key, 0)) < maximum_doc:
                errors.append(f"{state_path(repo)}: {key} high-water mark is below members")
    except DesignctlError as exc:
        errors.append(str(exc))
    return unique(errors), unique(warnings)


def index_body(repo: Path) -> str:
    records, errors = scan_designs(repo)
    if errors:
        raise DesignctlError("; ".join(errors))
    rows = [
        "| Design | Title | Status | Layout | Published | Entrypoint |",
        "|---|---|---|---|---:|---|",
    ]
    for design_id, record in sorted(
        records.items(), key=lambda item: int(DESIGN_ID_RE.fullmatch(item[0]).group(1))
    ):
        published = record.data.get("published_revision", "legacy")
        path = record.path.relative_to(repo / "docs").as_posix()
        rows.append(
            f"| {design_id} | {record.data.get('title', '')} | "
            f"{record.data.get('status', '')} | {record.layout} | {published} | "
            f"[{path}]({path}) |"
        )
    return "\n".join(rows) if len(rows) > 2 else "No Design Documents registered."


def reindex(repo: Path) -> list[str]:
    warnings: list[str] = []
    body = index_body(repo)
    for path in (repo / "docs" / "DESIGN-DOCS.md", repo / "docs" / "design-docs" / "index.md"):
        if not path.exists():
            if path.name == "DESIGN-DOCS.md":
                atomic_write(path, asset_text("design-index.md"))
            else:
                warnings.append(f"{path}: missing optional architecture index")
                continue
        text = path.read_text(encoding="utf-8")
        updated, managed = replace_generated_region(text, INDEX_START, INDEX_END, body)
        if not managed:
            warnings.append(f"{path}: no managed index region; preserved byte-for-byte")
            continue
        if updated != text:
            atomic_write(path, updated)
    return warnings


def new_design(
    repo: Path,
    *,
    slug: str,
    title: str,
    layout: str,
    research_refs: list[str],
    research_not_required_reason: str,
    adr_refs: list[str],
    dependencies: list[str],
    author: str,
    owner: str,
) -> Path:
    validate_slug(slug)
    if not title.strip():
        raise DesignctlError("Title must be non-empty")
    normalized_research = unique(normalize_research_id(item) for item in research_refs)
    reason = research_not_required_reason.strip()
    if bool(normalized_research) == bool(reason):
        raise DesignctlError(
            "Provide one or more --research values or one --research-not-required-reason"
        )
    if reason and len(reason) < 16:
        raise DesignctlError("Research-not-required reason must be concrete")
    for research_id in normalized_research:
        errors = validate_research_reference(repo, research_id)
        if errors:
            raise DesignctlError("\n".join(errors))
    normalized_adrs = unique(normalize_adr_id(item) for item in adr_refs)
    logical_adr_data = load_logical_adr_data(repo)
    for adr_id in normalized_adrs:
        errors = validate_adr_reference(
            repo,
            adr_id,
            require_current=False,
            logical_adr_data=logical_adr_data,
        )
        if errors:
            raise DesignctlError("\n".join(errors))
    normalized_dependencies = unique(normalize_dependency(item) for item in dependencies)
    records, scan_errors = scan_designs(repo)
    if scan_errors:
        raise DesignctlError("\n".join(scan_errors))
    for dependency in normalized_dependencies:
        target = dependency_target(dependency)
        if target not in records:
            raise DesignctlError(f"Design dependency not found: {target}")

    init_repo(repo)
    design_id = next_design_id(repo)
    author_value = author.strip() or "Unassigned"
    owner_value = owner.strip() or "Unassigned"
    today = date_string()
    package_map = (
        f"{MAP_START}\nNo focused member documents yet.\n{MAP_END}"
        if layout == "package"
        else "Single-file layout; this entrypoint owns the complete architecture narrative."
    )
    values = {
        "DESIGN_ID": design_id,
        "LAYOUT": layout,
        "TITLE": title.strip(),
        "TITLE_JSON": json.dumps(title.strip(), ensure_ascii=False),
        "RESEARCH_REFS": json.dumps(normalized_research, ensure_ascii=False),
        "RESEARCH_NOT_REQUIRED_REASON_JSON": json.dumps(reason, ensure_ascii=False),
        "ADR_REFS": json.dumps(normalized_adrs, ensure_ascii=False),
        "DESIGN_DEPENDENCIES": json.dumps(normalized_dependencies, ensure_ascii=False),
        "AUTHOR_JSON": json.dumps(author_value, ensure_ascii=False),
        "OWNER_JSON": json.dumps(owner_value, ensure_ascii=False),
        "DATE": today,
        "PACKAGE_MAP": package_map,
    }
    if layout == "single":
        path = repo / "docs" / "design-docs" / f"{design_id.lower()}_{slug}.md"
        atomic_write(path, render_asset("design.md", values))
    else:
        package = repo / "docs" / "design-docs" / f"{design_id.lower()}_{slug}"
        path = package / "DESIGN.md"
        if package.exists():
            raise DesignctlError(f"Design package path already exists: {package}")
        for directory in (
            *sorted(CURRENT_MANAGED_DIRECTORIES),
            "artifacts",
            "snapshots",
        ):
            (package / directory).mkdir(parents=True, exist_ok=True)
        atomic_write(path, render_asset("design.md", values))
        record = DesignRecord(path, parse_frontmatter(path.read_text(encoding="utf-8")))
        document_id = next_document_id(repo, record)
        reading_values = {
            "DESIGN_ID": design_id,
            "DOCUMENT_ID": document_id,
            "TITLE": f"{title.strip()} — Reading map",
            "TITLE_JSON": json.dumps(f"{title.strip()} — Reading map", ensure_ascii=False),
            "AUTHOR_JSON": json.dumps(author_value, ensure_ascii=False),
            "OWNER_JSON": json.dumps(owner_value, ensure_ascii=False),
            "DATE": today,
        }
        atomic_write(package / "README.md", render_asset("reading-map.md", reading_values))
        record = DesignRecord(path, parse_frontmatter(path.read_text(encoding="utf-8")))
        sync_package(repo, record, force=True)
    reindex(repo)
    return path


def new_member(
    repo: Path,
    design_id: str,
    *,
    role: str,
    slug: str,
    title: str,
    author: str,
    owner: str,
) -> Path:
    role = role.strip().lower()
    if role not in MEMBER_ROLES:
        raise DesignctlError("Role must be one of: " + ", ".join(sorted(MEMBER_ROLES)))
    validate_slug(slug)
    if not title.strip():
        raise DesignctlError("Title must be non-empty")
    record = find_design(repo, design_id)
    if record.schema != CURRENT_SCHEMA or record.layout != "package":
        raise DesignctlError(f"{record.design_id} is not a current-schema package")
    if record.data.get("status") not in {"draft", "revising"}:
        raise DesignctlError("Members can be added only while draft or revising")
    document_id = next_document_id(repo, record)
    directory = role_directory(record, role)
    path = record.package / directory / f"{document_id.lower()}_{slug}.md"
    if path.exists():
        raise DesignctlError(f"Member path already exists: {path}")
    values = {
        "DESIGN_ID": record.design_id,
        "DOCUMENT_ID": document_id,
        "ROLE": role,
        "TITLE": title.strip(),
        "TITLE_JSON": json.dumps(title.strip(), ensure_ascii=False),
        "AUTHOR_JSON": json.dumps(author.strip() or record.data.get("author", "Unassigned"), ensure_ascii=False),
        "OWNER_JSON": json.dumps(owner.strip() or record.data.get("owner", "Unassigned"), ensure_ascii=False),
        "DATE": date_string(),
    }
    atomic_write(path, render_asset("member.md", values))
    refreshed = find_design(repo, record.design_id)
    sync_package(repo, refreshed, force=True)
    return path


def mark_review_ready(repo: Path, design_id: str) -> Path:
    record = find_design(repo, design_id)
    if record.schema != CURRENT_SCHEMA:
        raise DesignctlError("Legacy Design Docs require explicit migration before lifecycle changes")
    if record.data.get("status") not in {"draft", "revising"}:
        raise DesignctlError(
            f"mark-review-ready requires draft or revising; found {record.data.get('status')}"
        )
    if record.layout == "package":
        sync_package(repo, record, force=True)
        record = find_design(repo, design_id)
    records, scan_errors = scan_designs(repo)
    errors = list(scan_errors)
    errors.extend(validate_dependency_graph(records))
    item_errors, _ = validate_design_record(
        repo,
        record,
        records,
        for_review=True,
        logical_adr_data=load_logical_adr_data(repo),
    )
    errors.extend(item_errors)
    if errors:
        raise DesignctlError("Review-ready gate failed:\n- " + "\n- ".join(unique(errors)))
    text = record.path.read_text(encoding="utf-8")
    updated = update_frontmatter(
        text,
        {"status": "review_ready", "updated": date_string()},
    )
    atomic_write(record.path, updated)
    record = find_design(repo, design_id)
    if record.layout == "package":
        sync_package(repo, record, force=True)
    reindex(repo)
    return record.path


def create_snapshot(
    repo: Path,
    record: DesignRecord,
    updated_root: str,
    updated_data: dict[str, str],
) -> tuple[str, dict[str, object] | None]:
    revision = positive_int(updated_data, "published_revision")
    root_payload = updated_root.encode("utf-8")
    if record.layout == "single":
        final = (
            repo
            / "docs"
            / ".designctl"
            / "snapshots"
            / record.design_id
            / f"rev-{revision:03d}"
        )
        revision_manifest: dict[str, object] = {
            "schema_version": "1",
            "metadata_schema": CURRENT_METADATA_SCHEMA,
            "artifact_type": "design-revision-manifest",
            "id": f"{record.design_id}-REV-{revision:03d}",
            "design_id": record.design_id,
            "title": f"{updated_data.get('title', '')} — approved revision {revision}",
            "status": "current",
            "layout": "single",
            "author": updated_data.get("author", ""),
            "owner": updated_data.get("owner", ""),
            "created": updated_data.get("created", ""),
            "updated": updated_data.get("updated", ""),
            "revision": revision,
            "approved_by": updated_data.get("approved_by", ""),
            "approved_at": updated_data.get("approved_at", ""),
            "approval_ref": updated_data.get("approval_ref", ""),
            "entrypoint": "DESIGN.md",
            "documents": [
                {
                    "id": record.design_id,
                    "role": "entrypoint",
                    "path": "DESIGN.md",
                    "title": updated_data.get("title", ""),
                    "bytes": len(root_payload),
                    "sha256": sha256_bytes(root_payload),
                }
            ],
        }
        digest = manifest_digest(revision_manifest)
        if final.exists():
            existing = final / "DESIGN.md"
            existing_manifest = final / MANIFEST_NAME
            if (
                not existing.is_file()
                or existing.read_bytes() != root_payload
                or not existing_manifest.is_file()
                or json.loads(existing_manifest.read_text(encoding="utf-8"))
                != revision_manifest
            ):
                raise DesignctlError(f"Published snapshot already exists with different bytes: {final}")
            return digest, None
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".rev-{revision:03d}.", dir=final.parent))
        try:
            (temporary / "DESIGN.md").write_bytes(root_payload)
            (temporary / MANIFEST_NAME).write_text(
                manifest_text(revision_manifest), encoding="utf-8"
            )
            os.replace(temporary, final)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return digest, None

    manifest, errors = manifest_object(
        record, data_override=updated_data, root_override=root_payload
    )
    if errors:
        raise DesignctlError("Cannot snapshot package:\n- " + "\n- ".join(errors))
    final = record.package / "snapshots" / f"rev-{revision:03d}"
    digest = manifest_digest(manifest)
    if final.exists():
        try:
            existing = json.loads((final / MANIFEST_NAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DesignctlError(f"Invalid existing snapshot {final}: {exc}") from exc
        if existing != manifest:
            raise DesignctlError(f"Published snapshot already exists with different content: {final}")
        return digest, manifest
    final.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".rev-{revision:03d}.", dir=final.parent))
    try:
        documents = manifest["documents"]
        assert isinstance(documents, list)
        for item in documents:
            assert isinstance(item, dict)
            relative = str(item["path"])
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative == "DESIGN.md":
                destination.write_bytes(root_payload)
            else:
                source = record.package / relative
                reject_symlink_path(repo, source)
                destination.write_bytes(source.read_bytes())
        (temporary / MANIFEST_NAME).write_text(
            manifest_text(manifest), encoding="utf-8"
        )
        os.replace(temporary, final)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return digest, manifest


def approve(
    repo: Path,
    design_id: str,
    *,
    approved_by: str,
    approval_ref: str,
) -> str:
    if not approved_by.strip() or not approval_ref.strip():
        raise DesignctlError("Approval requires explicit --approved-by and --approval-ref")
    record = find_design(repo, design_id)
    if record.schema != CURRENT_SCHEMA or record.data.get("status") != "review_ready":
        raise DesignctlError("approve requires a schema-1.1 review_ready Design")
    records, scan_errors = scan_designs(repo)
    errors = list(scan_errors) + validate_dependency_graph(records)
    item_errors, _ = validate_design_record(
        repo,
        record,
        records,
        for_review=True,
        logical_adr_data=load_logical_adr_data(repo),
    )
    errors.extend(item_errors)
    if errors:
        raise DesignctlError("Approval gate failed:\n- " + "\n- ".join(unique(errors)))
    working = positive_int(record.data, "working_revision")
    updated_root = update_frontmatter(
        record.path.read_text(encoding="utf-8"),
        {
            "status": "current",
            "published_revision": json.dumps(str(working)),
            "approved_by": json.dumps(approved_by.strip(), ensure_ascii=False),
            "approved_at": json.dumps(timestamp_string()),
            "approval_ref": json.dumps(approval_ref.strip(), ensure_ascii=False),
            "updated": date_string(),
        },
    )
    updated_data = parse_frontmatter(updated_root)
    digest, manifest = create_snapshot(repo, record, updated_root, updated_data)
    atomic_write(record.path, updated_root)
    if manifest is not None:
        atomic_write(record.package / MANIFEST_NAME, manifest_text(manifest))
    reindex(repo)
    return f"{record.design_id}@rev:{working}@sha256:{digest}"


def revise(repo: Path, design_id: str, reason: str) -> Path:
    if len(reason.strip()) < 8:
        raise DesignctlError("Revision reason must be concrete")
    record = find_design(repo, design_id)
    if record.schema != CURRENT_SCHEMA:
        raise DesignctlError("Legacy Design Docs require explicit migration before revision")
    status = record.data.get("status")
    published = positive_int(record.data, "published_revision", allow_zero=True)
    working = positive_int(record.data, "working_revision")
    if status == "current":
        target = "revising"
        working = published + 1
    elif status == "review_ready":
        target = "revising" if published else "draft"
    else:
        raise DesignctlError("revise requires current or review_ready status")
    updated = update_frontmatter(
        record.path.read_text(encoding="utf-8"),
        {
            "status": target,
            "working_revision": json.dumps(str(working)),
            "revision_reason": json.dumps(reason.strip(), ensure_ascii=False),
            "updated": date_string(),
        },
    )
    atomic_write(record.path, updated)
    record = find_design(repo, design_id)
    if record.layout == "package":
        sync_package(repo, record, force=True)
    reindex(repo)
    return record.path


def abandon(
    repo: Path,
    design_id: str,
    *,
    approved_by: str,
    approval_ref: str,
    reason: str,
) -> Path:
    if not all(value.strip() for value in (approved_by, approval_ref, reason)):
        raise DesignctlError("Abandonment requires authority, approval ref, and reason")
    record = find_design(repo, design_id)
    if record.schema != CURRENT_SCHEMA or record.data.get("status") not in {
        "draft",
        "review_ready",
        "revising",
    }:
        raise DesignctlError("abandon requires a mutable schema-1.1 Design")
    updated = update_frontmatter(
        record.path.read_text(encoding="utf-8"),
        {
            "status": "abandoned",
            "approved_by": json.dumps(approved_by.strip(), ensure_ascii=False),
            "approved_at": json.dumps(timestamp_string()),
            "approval_ref": json.dumps(approval_ref.strip(), ensure_ascii=False),
            "terminal_reason": json.dumps(reason.strip(), ensure_ascii=False),
            "updated": date_string(),
        },
    )
    atomic_write(record.path, updated)
    record = find_design(repo, design_id)
    if record.layout == "package":
        sync_package(repo, record, force=True)
    reindex(repo)
    return record.path


def supersede(
    repo: Path,
    old_id: str,
    new_id: str,
    *,
    approved_by: str,
    approval_ref: str,
    reason: str,
) -> Path:
    if not all(value.strip() for value in (approved_by, approval_ref, reason)):
        raise DesignctlError("Supersession requires authority, approval ref, and reason")
    old = find_design(repo, old_id)
    new = find_design(repo, new_id)
    if old.design_id == new.design_id:
        raise DesignctlError("A Design cannot supersede itself")
    if old.schema != CURRENT_SCHEMA or old.data.get("status") != "current":
        raise DesignctlError("Only a current schema-1.1 Design can be superseded")
    if not design_is_published(new) or new.data.get("status") in TERMINAL_STATUSES:
        raise DesignctlError("Superseding Design must have a current publication")
    cursor = new
    seen = {old.design_id}
    while cursor.data.get("superseded_by", "").strip():
        target = cursor.data["superseded_by"].upper()
        if target in seen:
            raise DesignctlError("Supersession would create a cycle")
        seen.add(target)
        cursor = find_design(repo, target)
    updated = update_frontmatter(
        old.path.read_text(encoding="utf-8"),
        {
            "status": "superseded",
            "superseded_by": new.design_id,
            "approved_by": json.dumps(approved_by.strip(), ensure_ascii=False),
            "approved_at": json.dumps(timestamp_string()),
            "approval_ref": json.dumps(approval_ref.strip(), ensure_ascii=False),
            "terminal_reason": json.dumps(reason.strip(), ensure_ascii=False),
            "updated": date_string(),
        },
    )
    atomic_write(old.path, updated)
    old = find_design(repo, old.design_id)
    if old.layout == "package":
        sync_package(repo, old, force=True)
    reindex(repo)
    return old.path


def evidence_for(record: DesignRecord) -> str:
    if record.schema != CURRENT_SCHEMA:
        return "legacy"
    revision = positive_int(record.data, "published_revision", allow_zero=True)
    if revision == 0:
        return ""
    if record.layout == "package":
        manifest_path = record.package / "snapshots" / f"rev-{revision:03d}" / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return f"{record.design_id}@rev:{revision}@sha256:{manifest_digest(manifest)}"
    snapshot_directory = (
        record.path.parents[1]
        / ".designctl"
        / "snapshots"
        / record.design_id
        / f"rev-{revision:03d}"
    )
    manifest = json.loads(
        (snapshot_directory / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    return f"{record.design_id}@rev:{revision}@sha256:{manifest_digest(manifest)}"


def status_payload(repo: Path, selected: str | None) -> list[dict[str, object]]:
    records, errors = scan_designs(repo)
    if errors:
        raise DesignctlError("; ".join(errors))
    if selected:
        design_id = normalize_design_id(selected)
        if design_id not in records:
            raise DesignctlError(f"Design not found: {design_id}")
        records = {design_id: records[design_id]}
    result: list[dict[str, object]] = []
    all_records, _ = scan_designs(repo)
    logical_adr_data = load_logical_adr_data(repo)
    for design_id, record in sorted(records.items()):
        item_errors, item_warnings = validate_design_record(
            repo,
            record,
            all_records,
            logical_adr_data=logical_adr_data,
        )
        try:
            dependencies = json_list(record.data, "design_dependencies") if record.schema == CURRENT_SCHEMA else []
        except DesignctlError:
            dependencies = []
        evidence = ""
        if design_is_published(record) and record.schema == CURRENT_SCHEMA:
            try:
                evidence = evidence_for(record)
            except (DesignctlError, OSError, json.JSONDecodeError) as exc:
                item_errors.append(f"{record.path}: cannot read published evidence: {exc}")
        result.append(
            {
                "id": design_id,
                "title": record.data.get("title", ""),
                "status": record.data.get("status", ""),
                "layout": record.layout,
                "working_revision": record.data.get("working_revision", "legacy"),
                "published_revision": record.data.get("published_revision", "legacy"),
                "evidence": evidence,
                "design_dependencies": dependencies,
                "path": record.path.relative_to(repo).as_posix(),
                "errors": item_errors,
                "warnings": item_warnings,
            }
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and govern single-file Designs and Design Packages."
    )
    parser.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize Design state and indexes")

    create = subparsers.add_parser("new-design", help="Allocate and scaffold a Design")
    create.add_argument("--slug", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--layout", required=True, choices=("single", "package"))
    create.add_argument("--research", action="append", default=[])
    create.add_argument("--research-not-required-reason", default="")
    create.add_argument("--adr", action="append", default=[])
    create.add_argument("--design-dependency", action="append", default=[])
    create.add_argument("--author", default="")
    create.add_argument("--owner", default="")

    member = subparsers.add_parser("new-member", help="Add a package-local Design member")
    member.add_argument("design_id")
    member.add_argument("--role", required=True, choices=tuple(sorted(MEMBER_ROLES)))
    member.add_argument("--slug", required=True)
    member.add_argument("--title", required=True)
    member.add_argument("--author", default="")
    member.add_argument("--owner", default="")

    sync = subparsers.add_parser("sync", aliases=["sync-design"], help="Refresh package map, reading map, and manifest")
    sync.add_argument("design_id")

    review = subparsers.add_parser(
        "mark-review-ready",
        aliases=["mark-design-review-ready"],
        help="Validate and mark the working revision ready for Design review",
    )
    review.add_argument("design_id")

    approve_parser = subparsers.add_parser("approve", aliases=["approve-design"], help="Publish one complete approved revision")
    approve_parser.add_argument("design_id")
    approve_parser.add_argument("--approved-by", required=True)
    approve_parser.add_argument("--approval-ref", required=True)

    revise_parser = subparsers.add_parser("revise", aliases=["revise-design"], help="Open a new mutable working revision")
    revise_parser.add_argument("design_id")
    revise_parser.add_argument("--reason", required=True)

    abandon_parser = subparsers.add_parser("abandon", aliases=["abandon-design"], help="Terminate an unpublished or revising Design")
    abandon_parser.add_argument("design_id")
    abandon_parser.add_argument("--approved-by", required=True)
    abandon_parser.add_argument("--approval-ref", required=True)
    abandon_parser.add_argument("--reason", required=True)

    supersede_parser = subparsers.add_parser("supersede", aliases=["supersede-design"], help="Replace a current Design with another published Design")
    supersede_parser.add_argument("design_id")
    supersede_parser.add_argument("--by", required=True, dest="replacement")
    supersede_parser.add_argument("--approved-by", required=True)
    supersede_parser.add_argument("--approval-ref", required=True)
    supersede_parser.add_argument("--reason", required=True)

    status_parser = subparsers.add_parser("status", help="Show Design lifecycle and integrity status")
    status_parser.add_argument("design_id", nargs="?")
    status_parser.add_argument("--json", action="store_true")

    subparsers.add_parser("reindex", help="Rebuild managed Design index regions")
    subparsers.add_parser("validate", help="Validate Design identities, graphs, manifests, and snapshots")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repo = normalize_repo(args.repo)
        if args.command == "init":
            with repo_lock(repo):
                created = init_repo(repo)
                warnings = reindex(repo)
            for item in created:
                print(item)
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            return 0
        if args.command == "new-design":
            with repo_lock(repo):
                path = new_design(
                    repo,
                    slug=args.slug,
                    title=args.title,
                    layout=args.layout,
                    research_refs=args.research,
                    research_not_required_reason=args.research_not_required_reason,
                    adr_refs=args.adr,
                    dependencies=args.design_dependency,
                    author=args.author,
                    owner=args.owner,
                )
            print(path)
            return 0
        if args.command == "new-member":
            with repo_lock(repo):
                path = new_member(
                    repo,
                    args.design_id,
                    role=args.role,
                    slug=args.slug,
                    title=args.title,
                    author=args.author,
                    owner=args.owner,
                )
            print(path)
            return 0
        if args.command in {"sync", "sync-design"}:
            with repo_lock(repo):
                record = find_design(repo, args.design_id)
                warnings = sync_package(repo, record)
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            print(record.package / MANIFEST_NAME)
            return 0
        if args.command in {"mark-review-ready", "mark-design-review-ready"}:
            with repo_lock(repo):
                path = mark_review_ready(repo, args.design_id)
            print(path)
            return 0
        if args.command in {"approve", "approve-design"}:
            with repo_lock(repo):
                evidence = approve(
                    repo,
                    args.design_id,
                    approved_by=args.approved_by,
                    approval_ref=args.approval_ref,
                )
            print(evidence)
            return 0
        if args.command in {"revise", "revise-design"}:
            with repo_lock(repo):
                path = revise(repo, args.design_id, args.reason)
            print(path)
            return 0
        if args.command in {"abandon", "abandon-design"}:
            with repo_lock(repo):
                path = abandon(
                    repo,
                    args.design_id,
                    approved_by=args.approved_by,
                    approval_ref=args.approval_ref,
                    reason=args.reason,
                )
            print(path)
            return 0
        if args.command in {"supersede", "supersede-design"}:
            with repo_lock(repo):
                path = supersede(
                    repo,
                    args.design_id,
                    args.replacement,
                    approved_by=args.approved_by,
                    approval_ref=args.approval_ref,
                    reason=args.reason,
                )
            print(path)
            return 0
        if args.command == "status":
            payload = status_payload(repo, args.design_id)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                for item in payload:
                    evidence = f" evidence={item['evidence']}" if item["evidence"] else ""
                    print(
                        f"{item['id']} {item['status']} {item['layout']} "
                        f"working={item['working_revision']} published={item['published_revision']}"
                        f"{evidence} {item['path']}"
                    )
            return 0
        if args.command == "reindex":
            with repo_lock(repo):
                warnings = reindex(repo)
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            return 0
        if args.command == "validate":
            errors, warnings = validate_repo(repo)
            for warning in warnings:
                print(f"WARNING: {warning}")
            for error in errors:
                print(f"ERROR: {error}")
            print(json.dumps({"errors": len(errors), "warnings": len(warnings)}))
            return 1 if errors else 0
        parser.error(f"Unsupported command: {args.command}")
    except DesignctlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
