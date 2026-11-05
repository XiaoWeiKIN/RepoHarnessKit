#!/usr/bin/env python3
"""Bootstrap and validate the RepoFoundry AI project Harness."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import spec_manager as specctl

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
VERSION_FILE = SKILL_DIR / "VERSION"
EXECUTION_PLAN_CTL = (
    SKILL_DIR / "engineering-execution-plan" / "scripts" / "epctl.py"
)
DESIGN_CTL = SKILL_DIR / "engineering-design" / "scripts" / "designctl.py"
PROFESSIONAL_COMPONENTS = [
    "engineering-design",
    "engineering-execution-plan",
]
DEFAULT_SPEC_REPOSITORY = (
    "https://github.com/XiaoWeiKIN/EngineeringSpecifications.git"
)
DEFAULT_SPEC_VERSION = "1.9.0"

LEGACY_HARNESS_SCHEMA_VERSION = 1
PROFILE_HARNESS_SCHEMA_VERSION = 2
HARNESS_SCHEMA_VERSION = 3
HARNESS_OWNER = "repo-foundry"
LEGACY_HARNESS_OWNERS = frozenset({"engineering-workflow"})
CODEX_HARNESS_PROFILE = "codex"
CODEX_HARNESS_PROFILE_VERSION = "1.0.0"
CORE_HARNESS_VERSION = "1.6.2"
CODEX_ADAPTER_VERSION = "2.4.4"
CLAUDE_ADAPTER_VERSION = "1.3.3"
PORTABLE_ADAPTER_VERSION = "1.3.4"
ACTIVATION_PROTOCOL_VERSION = 2
GOVERNANCE_POLICY_SCHEMA = 1
GOVERNANCE_PROFILES = ("adaptive", "strict")
DEFAULT_GOVERNANCE_PROFILE = "adaptive"
LEGACY_GOVERNANCE_PROFILE = "strict"
CODEX_AGENT_MAX_LINES = 100
CODEX_AGENT_TEMPLATE_TARGET_LINES = 80
CORE_SKILL_MAX_LINES = 120
ADAPTER_SKILL_MAX_LINES = 80
CLAUDE_SPEC_SKILL_MAX_LINES = 120
PORTABLE_GUIDE_MAX_LINES = 120
BOOTSTRAP_TODO_MARKER = "BOOTSTRAP_TODO"
LEGACY_UNVERSIONED = "legacy-unversioned"
HARNESS_V1_TO_V2_MIGRATION = "harness-schema-v1-to-v2"
HARNESS_V1_TO_V3_MIGRATION = "harness-schema-v1-to-v3"
HARNESS_V2_TO_V3_MIGRATION = "harness-schema-v2-to-v3"

HARNESS_STATE_DIRECTORY = "docs/.engineering"
HARNESS_MANIFEST = f"{HARNESS_STATE_DIRECTORY}/harness.json"
CODEX_BOOTSTRAP_DIRECTORIES = (
    HARNESS_STATE_DIRECTORY,
    "docs/design-docs",
    ".agents/skills/engineering-specs/agents",
    ".agents/skills/engineering-specs/scripts",
    ".codex",
)
CODEX_DOCUMENT_FILE_ASSETS = (
    ("AGENTS.md", "adapters/codex/AGENTS.md"),
    ("ARCHITECTURE.md", "core/harness-architecture.md"),
    ("docs/index.md", "core/harness-docs-index.md"),
    ("docs/QUALITY_SCORE.md", "core/harness-quality-score.md"),
    ("docs/RELIABILITY.md", "core/harness-reliability.md"),
    ("docs/SECURITY.md", "core/harness-security.md"),
    ("docs/design-docs/index.md", "core/harness-design-docs-index.md"),
)
CODEX_ROUTER_FILE_ASSETS = (
    (
        ".agents/skills/engineering-specs/SKILL.md",
        "adapters/codex/engineering-specs/SKILL.md.template",
    ),
    (
        ".agents/skills/engineering-specs/agents/openai.yaml",
        "adapters/codex/engineering-specs/agents/openai.yaml",
    ),
    (
        ".agents/skills/engineering-specs/scripts/spec_router.py",
        "adapters/codex/engineering-specs/scripts/spec_router.py",
    ),
    (".codex/hooks.json", "adapters/codex/hooks.json"),
)
CODEX_BOOTSTRAP_FILE_ASSETS = (
    *CODEX_DOCUMENT_FILE_ASSETS,
    *CODEX_ROUTER_FILE_ASSETS,
)
CODEX_TEMPLATE_IDS = {
    "AGENTS.md": "codex/agents",
    "ARCHITECTURE.md": "codex/architecture",
    "docs/index.md": "codex/docs-index",
    "docs/QUALITY_SCORE.md": "codex/quality-score",
    "docs/RELIABILITY.md": "codex/reliability",
    "docs/SECURITY.md": "codex/security",
    "docs/design-docs/index.md": "codex/design-docs-index",
    ".agents/skills/engineering-specs/SKILL.md": (
        "codex/engineering-specs-router-skill"
    ),
    ".agents/skills/engineering-specs/agents/openai.yaml": (
        "codex/engineering-specs-router-agent"
    ),
    ".agents/skills/engineering-specs/scripts/spec_router.py": (
        "codex/engineering-specs-router-script"
    ),
    ".codex/hooks.json": "codex/engineering-specs-hooks",
}
CODEX_REQUIRED_FILES = tuple(
    relative for relative, _ in CODEX_DOCUMENT_FILE_ASSETS
)
CODEX_SEEDED_FILES = tuple(
    relative for relative, _ in CODEX_BOOTSTRAP_FILE_ASSETS
)
CODEX_GENERATED_FILES = frozenset(
    relative for relative, _ in CODEX_ROUTER_FILE_ASSETS
)
CODEX_ROUTER_SKILL_FILES = frozenset(
    relative
    for relative, _ in CODEX_ROUTER_FILE_ASSETS
    if relative != ".codex/hooks.json"
)
CODEX_HOOKS_FILE = ".codex/hooks.json"
CODEX_ROUTER_SCRIPT = (
    ".agents/skills/engineering-specs/scripts/spec_router.py"
)
CODEX_ROUTER_COMMAND_FRAGMENT = (
    ".agents/skills/engineering-specs/scripts/spec_router.py\" hook"
)
CODEX_ROUTER_AGENTS_ROUTES = (
    "$engineering-specs",
    "docs/agent-guides/managed/index.md",
)
CODEX_REQUIRED_HOOK_EVENTS = (
    "UserPromptSubmit",
    "SubagentStart",
    "PreToolUse",
    "Stop",
)

CORE_BOOTSTRAP_DIRECTORIES = (
    HARNESS_STATE_DIRECTORY,
    "docs/design-docs",
    ".repo-foundry/engineering-specs",
    ".repo-foundry/skills/repo-foundry-ai",
)
CORE_MEMORY_INTRODUCED = "1.6.0"
CORE_MEMORY_FILE_ASSETS = (
    (
        ".repo-foundry/engineering-specs/memory_retrieval.py",
        "core/engineering-specs/memory_retrieval.py",
    ),
    (
        ".repo-foundry/engineering-specs/memory_runtime.py",
        "core/engineering-specs/memory_runtime.py",
    ),
)
CORE_FILE_ASSETS = (
    *CORE_MEMORY_FILE_ASSETS,
    ("ARCHITECTURE.md", "core/harness-architecture.md"),
    ("docs/index.md", "core/harness-docs-index.md"),
    ("docs/QUALITY_SCORE.md", "core/harness-quality-score.md"),
    ("docs/RELIABILITY.md", "core/harness-reliability.md"),
    ("docs/SECURITY.md", "core/harness-security.md"),
    ("docs/design-docs/index.md", "core/harness-design-docs-index.md"),
    (
        ".repo-foundry/engineering-specs/spec_router.py",
        "core/engineering-specs/spec_router.py",
    ),
    (
        ".repo-foundry/skills/repo-foundry-ai/SKILL.md",
        "core/repo-foundry-ai/SKILL.md.template",
    ),
)
CODEX_ADAPTER_DIRECTORIES = (
    ".agents/skills/repo-foundry-ai",
    ".agents/skills/engineering-specs/agents",
    ".agents/skills/engineering-specs/scripts",
    ".codex",
)
CODEX_ADAPTER_FILE_ASSETS = (
    ("AGENTS.md", "adapters/codex/AGENTS.md"),
    (
        ".agents/skills/repo-foundry-ai/SKILL.md",
        "adapters/codex/repo-foundry-ai/SKILL.md.template",
    ),
    *CODEX_ROUTER_FILE_ASSETS,
)
CLAUDE_ADAPTER_DIRECTORIES = (
    ".claude/skills/repo-foundry-ai",
    ".claude/skills/engineering-specs",
)
CLAUDE_ADAPTER_FILE_ASSETS = (
    (
        ".claude/skills/repo-foundry-ai/SKILL.md",
        "adapters/claude/repo-foundry-ai/SKILL.md.template",
    ),
    (
        ".claude/skills/engineering-specs/SKILL.md",
        "adapters/claude/engineering-specs/SKILL.md.template",
    ),
)
PORTABLE_ADAPTER_DIRECTORIES = ("docs/agent-guides",)
PORTABLE_ADAPTER_FILE_ASSETS = (
    ("docs/agent-guides/README.md", "adapters/portable/agent-guide.md"),
)
ADAPTER_ORDER = ("codex", "claude", "portable")
ADAPTER_VERSIONS = {
    "codex": CODEX_ADAPTER_VERSION,
    "claude": CLAUDE_ADAPTER_VERSION,
    "portable": PORTABLE_ADAPTER_VERSION,
}
ADAPTER_ENFORCEMENT = {
    "codex": "native",
    "claude": "cli",
    "portable": "cli",
}
ADAPTER_CAPABILITIES: dict[str, dict[str, object]] = {
    "codex": {
        "instructions": "file",
        "skills": "file",
        "lifecycle_events": [
            "session_start",
            "subagent_start",
            "before_mutation",
            "stop",
        ],
        "context_injection": "native",
        "mutation_gate": "native",
        "completion_audit": "native",
        "project_trust": "user_review",
        "automated_enforcement_effective_maximum": "Advisory",
        "finding_lifecycle": "unsupported",
    },
    "claude": {
        "instructions": "none",
        "skills": "native",
        "lifecycle_events": [],
        "context_injection": "advisory",
        "mutation_gate": "cli",
        "completion_audit": "cli",
        "project_trust": "user_review",
        "automated_enforcement_effective_maximum": "Advisory",
        "finding_lifecycle": "unsupported",
    },
    "portable": {
        "instructions": "file",
        "skills": "none",
        "lifecycle_events": [],
        "context_injection": "advisory",
        "mutation_gate": "cli",
        "completion_audit": "cli",
        "project_trust": "none",
        "automated_enforcement_effective_maximum": "Advisory",
        "finding_lifecycle": "unsupported",
    },
}
ADAPTER_DIRECTORIES = {
    "codex": CODEX_ADAPTER_DIRECTORIES,
    "claude": CLAUDE_ADAPTER_DIRECTORIES,
    "portable": PORTABLE_ADAPTER_DIRECTORIES,
}
ADAPTER_FILE_ASSETS = {
    "codex": CODEX_ADAPTER_FILE_ASSETS,
    "claude": CLAUDE_ADAPTER_FILE_ASSETS,
    "portable": PORTABLE_ADAPTER_FILE_ASSETS,
}
CORE_TEMPLATE_IDS = {
    ".repo-foundry/engineering-specs/memory_retrieval.py": "core/engineering-specs-memory-retrieval",
    ".repo-foundry/engineering-specs/memory_runtime.py": "core/engineering-specs-memory-runtime",
    "ARCHITECTURE.md": "core/architecture",
    "docs/index.md": "core/docs-index",
    "docs/QUALITY_SCORE.md": "core/quality-score",
    "docs/RELIABILITY.md": "core/reliability",
    "docs/SECURITY.md": "core/security",
    "docs/design-docs/index.md": "core/design-docs-index",
    ".repo-foundry/engineering-specs/spec_router.py": (
        "core/engineering-specs-activation-engine"
    ),
    ".repo-foundry/skills/repo-foundry-ai/SKILL.md": (
        "core/repo-foundry-ai-project-skill"
    ),
}
ADAPTER_TEMPLATE_IDS = {
    "codex": {
        "AGENTS.md": "codex/agents",
        ".agents/skills/repo-foundry-ai/SKILL.md": (
            "codex/repo-foundry-ai-project-skill"
        ),
        ".agents/skills/engineering-specs/SKILL.md": (
            "codex/engineering-specs-skill"
        ),
        ".agents/skills/engineering-specs/agents/openai.yaml": (
            "codex/engineering-specs-openai-metadata"
        ),
        ".agents/skills/engineering-specs/scripts/spec_router.py": (
            "codex/engineering-specs-adapter"
        ),
        ".codex/hooks.json": "codex/engineering-specs-hooks",
    },
    "claude": {
        ".claude/skills/repo-foundry-ai/SKILL.md": (
            "claude/repo-foundry-ai-project-skill"
        ),
        ".claude/skills/engineering-specs/SKILL.md": (
            "claude/engineering-specs-skill"
        ),
    },
    "portable": {
        "docs/agent-guides/README.md": "portable/agent-guide",
    },
}
CORE_GENERATED_FILES = frozenset(
    {
        ".repo-foundry/engineering-specs/memory_retrieval.py",
        ".repo-foundry/engineering-specs/memory_runtime.py",
        ".repo-foundry/engineering-specs/spec_router.py",
        ".repo-foundry/skills/repo-foundry-ai/SKILL.md",
    }
)
ADAPTER_GENERATED_FILES = {
    "codex": frozenset(
        {
            ".agents/skills/repo-foundry-ai/SKILL.md",
            ".agents/skills/engineering-specs/SKILL.md",
            ".agents/skills/engineering-specs/agents/openai.yaml",
            ".agents/skills/engineering-specs/scripts/spec_router.py",
            ".codex/hooks.json",
        }
    ),
    "claude": frozenset(
        {
            ".claude/skills/repo-foundry-ai/SKILL.md",
            ".claude/skills/engineering-specs/SKILL.md",
        }
    ),
    "portable": frozenset({"docs/agent-guides/README.md"}),
}
CORE_ROUTER_PATH = ".repo-foundry/engineering-specs/spec_router.py"
CORE_PROJECT_SKILL_PATH = ".repo-foundry/skills/repo-foundry-ai/SKILL.md"
CODEX_PROJECT_SKILL_PATH = ".agents/skills/repo-foundry-ai/SKILL.md"
CLAUDE_PROJECT_SKILL_PATH = ".claude/skills/repo-foundry-ai/SKILL.md"
CLAUDE_SPEC_SKILL_PATH = ".claude/skills/engineering-specs/SKILL.md"
CORE_PROJECT_SKILL_INTRODUCED = "1.1.0"
CODEX_PROJECT_SKILL_INTRODUCED = "2.1.0"


class FoundryctlError(RuntimeError):
    pass


def distribution_version() -> str:
    if not VERSION_FILE.is_file():
        raise FoundryctlError(
            f"RepoFoundry VERSION file is missing: {VERSION_FILE}"
        )
    value = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not specctl.SEMVER_RE.fullmatch(value):
        raise FoundryctlError(
            "RepoFoundry VERSION must use MAJOR.MINOR.PATCH"
        )
    return value


REPO_FOUNDRY_VERSION = distribution_version()


def semver_tuple(value: str, label: str) -> tuple[int, int, int]:
    if not specctl.SEMVER_RE.fullmatch(value):
        raise FoundryctlError(f"{label}: expected MAJOR.MINOR.PATCH")
    major, minor, patch = (int(part) for part in value.split("."))
    return major, minor, patch


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spec_source(
    repository: str,
    *,
    version: str | None,
    ref: str | None,
    use_default_version: bool = True,
) -> dict[str, str] | None:
    if version is not None and ref is not None:
        raise FoundryctlError(
            "--spec-version and --spec-ref are mutually exclusive"
        )
    if version is None and ref is None:
        if not use_default_version:
            return None
        version = DEFAULT_SPEC_VERSION
    try:
        selected_ref = specctl.release_ref(version) if version else ref
    except specctl.SpecError as exc:
        raise FoundryctlError(str(exc)) from exc
    if selected_ref is None:  # pragma: no cover - guarded above
        raise FoundryctlError("A Specification version or ref is required")
    return {
        "kind": "git",
        "url": repository,
        "ref": selected_ref,
    }


def selected_spec_repository(
    repo: Path,
    requested: str | None,
    *,
    preserve_manifest_source: bool,
) -> str:
    if requested is not None:
        return requested
    manifest = repo / specctl.SPEC_MANIFEST
    if preserve_manifest_source and manifest.exists():
        try:
            return specctl.parse_manifest(manifest).catalog["url"]
        except specctl.SpecError as exc:
            raise FoundryctlError(str(exc)) from exc
    return DEFAULT_SPEC_REPOSITORY


def normalize_repo(value: str) -> Path:
    repo = Path(value).expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        raise FoundryctlError(
            f"Repository directory does not exist: {repo}"
        )
    return repo


def load_execution_plan_ctl() -> ModuleType:
    if not EXECUTION_PLAN_CTL.is_file():
        raise FoundryctlError(
            "Bundled engineering-execution-plan component is missing: "
            f"{EXECUTION_PLAN_CTL}"
        )
    spec = importlib.util.spec_from_file_location(
        "_repo_foundry_epctl",
        EXECUTION_PLAN_CTL,
    )
    if spec is None or spec.loader is None:
        raise FoundryctlError(
            f"Unable to load engineering-execution-plan: {EXECUTION_PLAN_CTL}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    for attribute in (
        "INIT_DIRECTORIES",
        "INIT_FILE_ASSETS",
        "config_path",
        "init_repo",
        "load_config",
        "repo_lock",
        "save_config",
        "adr_corpus_data",
    ):
        if not hasattr(module, attribute):
            raise FoundryctlError(
                "engineering-execution-plan component does not expose "
                f"the required bootstrap contract: {attribute}"
            )
    return module


def load_design_ctl() -> ModuleType:
    if not DESIGN_CTL.is_file():
        raise FoundryctlError(
            "Bundled engineering-design component is missing: "
            f"{DESIGN_CTL}"
        )
    spec = importlib.util.spec_from_file_location(
        "_repo_foundry_designctl",
        DESIGN_CTL,
    )
    if spec is None or spec.loader is None:
        raise FoundryctlError(
            f"Unable to load engineering-design: {DESIGN_CTL}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    for attribute in (
        "INIT_DIRECTORIES",
        "INIT_FILES",
        "init_repo",
        "reindex",
        "repo_lock",
        "validate_repo",
    ):
        if not hasattr(module, attribute):
            raise FoundryctlError(
                "engineering-design component does not expose the required "
                f"bootstrap contract: {attribute}"
            )
    return module


def reject_symlink_path(repo: Path, path: Path) -> None:
    try:
        relative = path.relative_to(repo)
    except ValueError as exc:
        raise FoundryctlError(
            f"Managed path escapes repository: {path}"
        ) from exc
    current = repo
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise FoundryctlError(
                f"Refusing to manage symbolic link: {current}"
            )


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    try:
        os.replace(temp_name, path)
        if hasattr(os, "O_DIRECTORY"):
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def asset_text(name: str) -> str:
    path = ASSET_DIR / name
    if not path.is_file():
        raise FoundryctlError(f"Missing bundled asset: {path}")
    return path.read_text(encoding="utf-8")


def router_asset_by_target(relative: str) -> str | None:
    for target, asset in CODEX_ROUTER_FILE_ASSETS:
        if target == relative:
            return asset
    return None


def validate_hook_config_data(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["HARNESS_SPEC_HOOKS_INVALID: expected a JSON object"]
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return ["HARNESS_SPEC_HOOKS_INVALID: hooks must be an object"]
    for event in CODEX_REQUIRED_HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list) or not groups:
            errors.append(
                f"HARNESS_SPEC_HOOK_MISSING: {event}: add the RepoFoundry "
                "Engineering Spec Hook group"
            )
            continue
        matched = False
        for group in groups:
            if not isinstance(group, dict):
                continue
            if event == "PreToolUse":
                matcher = group.get("matcher")
                if not isinstance(matcher, str) or not all(
                    value in matcher for value in ("Bash", "apply_patch")
                ):
                    continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                if (
                    handler.get("type") == "command"
                    and isinstance(handler.get("command"), str)
                    and CODEX_ROUTER_COMMAND_FRAGMENT in handler["command"]
                ):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            errors.append(
                f"HARNESS_SPEC_HOOK_MISSING: {event}: no command handler "
                f"routes to {CODEX_ROUTER_SCRIPT}"
            )
    return errors


def validate_hook_config_file(repo: Path) -> list[str]:
    path = repo / CODEX_HOOKS_FILE
    reason = managed_path_conflict(repo, path, "file")
    if reason:
        return [f"HARNESS_SPEC_HOOKS_INVALID: {CODEX_HOOKS_FILE}: {reason}"]
    if not path.is_file():
        return [
            f"HARNESS_SPEC_HOOKS_MISSING: {CODEX_HOOKS_FILE}: rerun "
            "foundryctl bootstrap --profile codex --apply"
        ]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"HARNESS_SPEC_HOOKS_INVALID: {CODEX_HOOKS_FILE}: {exc}"]
    return validate_hook_config_data(data)


def validate_spec_router(repo: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in sorted(CODEX_ROUTER_SKILL_FILES):
        target = repo / relative
        reason = managed_path_conflict(repo, target, "file")
        if reason:
            errors.append(
                f"HARNESS_SPEC_ROUTER_INVALID: {relative}: {reason}"
            )
            continue
        if not target.is_file():
            errors.append(
                f"HARNESS_SPEC_ROUTER_MISSING: {relative}: rerun "
                "foundryctl bootstrap --profile codex --apply"
            )
            continue
        asset = router_asset_by_target(relative)
        if asset is None:  # pragma: no cover - constant contract
            errors.append(f"HARNESS_SPEC_ROUTER_INVALID: {relative}: no asset")
            continue
        try:
            actual = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(
                f"HARNESS_SPEC_ROUTER_INVALID: {relative}: {exc}"
            )
            continue
        if actual != asset_text(asset):
            errors.append(
                f"HARNESS_SPEC_ROUTER_DRIFT: {relative}: generated Router "
                "bytes differ from this RepoFoundry release"
            )
    errors.extend(validate_hook_config_file(repo))
    agents = repo / "AGENTS.md"
    if not agents.is_file() or agents.is_symlink():
        errors.append(
            "HARNESS_SPEC_ROUTE_MISSING: AGENTS.md: expected a non-symlink "
            "regular file"
        )
    else:
        try:
            text = agents.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"HARNESS_SPEC_ROUTE_INVALID: AGENTS.md: {exc}")
        else:
            missing = [
                value for value in CODEX_ROUTER_AGENTS_ROUTES if value not in text
            ]
            if missing:
                errors.append(
                    "HARNESS_SPEC_ROUTE_MISSING: AGENTS.md: add the mandatory "
                    "Router route for " + ", ".join(missing)
                )
    return errors, warnings


def ensure_file(path: Path, asset: str) -> bool:
    if path.exists():
        return False
    atomic_write(path, asset_text(asset))
    return True


@contextlib.contextmanager
def repo_lock(repo: Path):
    lock_path = repo / HARNESS_STATE_DIRECTORY / "lock"
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


def harness_path(repo: Path) -> Path:
    return repo / HARNESS_MANIFEST


def legacy_codex_harness_manifest(
    *,
    owner: str = HARNESS_OWNER,
) -> dict[str, object]:
    """Return the schema-v1 contract kept only for compatibility checks."""
    return {
        "version": LEGACY_HARNESS_SCHEMA_VERSION,
        "owner": owner,
        "profile": CODEX_HARNESS_PROFILE,
        "components": ["engineering-execution-plan"],
        "instruction_files": [
            {
                "path": "AGENTS.md",
                "max_lines": CODEX_AGENT_MAX_LINES,
            }
        ],
        "required_files": list(CODEX_REQUIRED_FILES),
    }


def codex_file_record(
    relative: str,
    asset: str,
    *,
    installed_path: Path | None = None,
) -> dict[str, object]:
    template_digest = sha256_text(asset_text(asset))
    if (
        installed_path is None
        or (
            installed_path.is_file()
            and not installed_path.is_symlink()
            and sha256_file(installed_path) == template_digest
        )
    ):
        return {
            "path": relative,
            "ownership": "seeded",
            "template_id": CODEX_TEMPLATE_IDS[relative],
            "template_version": CODEX_HARNESS_PROFILE_VERSION,
            "template_sha256": template_digest,
            "installed_sha256": template_digest,
        }
    return {
        "path": relative,
        "ownership": "seeded",
        "template_id": CODEX_TEMPLATE_IDS[relative],
        "template_version": LEGACY_UNVERSIONED,
        "template_sha256": None,
        "installed_sha256": None,
    }


def codex_harness_manifest(
    repo: Path | None = None,
    *,
    applied_migrations: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    assets = dict(CODEX_BOOTSTRAP_FILE_ASSETS)
    return {
        "schema_version": PROFILE_HARNESS_SCHEMA_VERSION,
        "owner": HARNESS_OWNER,
        "producer": {
            "name": HARNESS_OWNER,
            "version": REPO_FOUNDRY_VERSION,
        },
        "profile": {
            "id": CODEX_HARNESS_PROFILE,
            "version": CODEX_HARNESS_PROFILE_VERSION,
        },
        "components": ["engineering-execution-plan"],
        "instruction_files": [
            {
                "path": "AGENTS.md",
                "max_lines": CODEX_AGENT_MAX_LINES,
            }
        ],
        "required_files": list(CODEX_REQUIRED_FILES),
        "files": [
            codex_file_record(
                relative,
                assets[relative],
                installed_path=(repo / relative) if repo else None,
            )
            for relative in CODEX_SEEDED_FILES
        ],
        "applied_migrations": list(applied_migrations or []),
    }


def normalize_adapter_ids(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    requested = tuple(values)
    duplicates = sorted(
        {item for item in requested if requested.count(item) > 1}
    )
    if duplicates:
        raise FoundryctlError(
            "HARNESS_ADAPTER_DUPLICATE: " + ", ".join(duplicates)
        )
    unknown = sorted(set(requested) - set(ADAPTER_ORDER))
    if unknown:
        raise FoundryctlError(
            "HARNESS_ADAPTER_UNSUPPORTED: " + ", ".join(unknown)
        )
    return tuple(item for item in ADAPTER_ORDER if item in requested)


def normalize_governance_profile(value: str) -> str:
    if value not in GOVERNANCE_PROFILES:
        raise FoundryctlError(
            "HARNESS_GOVERNANCE_PROFILE_UNSUPPORTED: "
            f"{value!r}; supported profiles: {', '.join(GOVERNANCE_PROFILES)}"
        )
    return value


def governance_manifest(profile: str) -> dict[str, object]:
    return {
        "policy_schema": GOVERNANCE_POLICY_SCHEMA,
        "profile": normalize_governance_profile(profile),
    }


def harness_governance_profile(manifest: dict[str, object]) -> str:
    if harness_schema_version(manifest) < HARNESS_SCHEMA_VERSION:
        return LEGACY_GOVERNANCE_PROFILE
    governance = manifest.get("governance")
    if governance is None:
        return LEGACY_GOVERNANCE_PROFILE
    if not isinstance(governance, dict):  # validated manifests never reach this
        raise FoundryctlError("Harness governance contract is invalid")
    return normalize_governance_profile(str(governance.get("profile")))


def selected_file_assets(
    adapter_ids: tuple[str, ...],
) -> tuple[tuple[str, str, str, str | None], ...]:
    records: list[tuple[str, str, str, str | None]] = [
        (relative, asset, "core", None)
        for relative, asset in CORE_FILE_ASSETS
    ]
    for adapter_id in adapter_ids:
        records.extend(
            (relative, asset, "adapter", adapter_id)
            for relative, asset in ADAPTER_FILE_ASSETS[adapter_id]
        )
    paths = [item[0] for item in records]
    if len(paths) != len(set(paths)):
        duplicates = sorted(
            {item for item in paths if paths.count(item) > 1}
        )
        raise FoundryctlError(
            "HARNESS_PATH_OWNERSHIP_COLLISION: " + ", ".join(duplicates)
        )
    return tuple(records)


def versioned_file_assets(
    core_version: str,
    adapter_versions: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str, str, str | None], ...]:
    """Return the file contract declared by a schema 3 manifest.

    Schema 3 predates project-local Skills, so component versions—not the
    schema number—determine whether those newer managed paths are required.
    """
    core_cutoff = semver_tuple(
        CORE_PROJECT_SKILL_INTRODUCED,
        "Core project Skill introduction",
    )
    core_assets = tuple(
        (relative, asset, "core", None)
        for relative, asset in CORE_FILE_ASSETS
        if (
            relative != CORE_PROJECT_SKILL_PATH
            or semver_tuple(core_version, "core.version") >= core_cutoff
        ) and (
            relative not in {path for path, _ in CORE_MEMORY_FILE_ASSETS}
            or semver_tuple(core_version, "core.version") >= semver_tuple(
                CORE_MEMORY_INTRODUCED, "Core memory runtime introduction"
            )
        )
    )
    records = list(core_assets)
    for adapter_id, version in adapter_versions:
        assets = ADAPTER_FILE_ASSETS[adapter_id]
        if adapter_id == "codex" and semver_tuple(
            version,
            "codex adapter version",
        ) < semver_tuple(
            CODEX_PROJECT_SKILL_INTRODUCED,
            "Codex project Skill introduction",
        ):
            assets = tuple(
                item for item in assets if item[0] != CODEX_PROJECT_SKILL_PATH
            )
        records.extend(
            (relative, asset, "adapter", adapter_id)
            for relative, asset in assets
        )
    return tuple(records)


def instruction_files_for_versions(
    core_version: str,
    adapter_versions: tuple[tuple[str, str], ...],
) -> list[dict[str, object]]:
    instruction_files: list[dict[str, object]] = []
    if semver_tuple(core_version, "core.version") >= semver_tuple(
        CORE_PROJECT_SKILL_INTRODUCED,
        "Core project Skill introduction",
    ):
        instruction_files.append(
            {"path": CORE_PROJECT_SKILL_PATH, "max_lines": CORE_SKILL_MAX_LINES}
        )
    for adapter_id, version in adapter_versions:
        if adapter_id == "codex":
            instruction_files.append(
                {"path": "AGENTS.md", "max_lines": CODEX_AGENT_MAX_LINES}
            )
            if semver_tuple(version, "codex adapter version") >= semver_tuple(
                CODEX_PROJECT_SKILL_INTRODUCED,
                "Codex project Skill introduction",
            ):
                instruction_files.append(
                    {
                        "path": CODEX_PROJECT_SKILL_PATH,
                        "max_lines": ADAPTER_SKILL_MAX_LINES,
                    }
                )
        elif adapter_id == "claude":
            instruction_files.extend(
                (
                    {
                        "path": CLAUDE_PROJECT_SKILL_PATH,
                        "max_lines": ADAPTER_SKILL_MAX_LINES,
                    },
                    {
                        "path": CLAUDE_SPEC_SKILL_PATH,
                        "max_lines": CLAUDE_SPEC_SKILL_MAX_LINES,
                    },
                )
            )
        elif adapter_id == "portable":
            instruction_files.append(
                {
                    "path": "docs/agent-guides/README.md",
                    "max_lines": PORTABLE_GUIDE_MAX_LINES,
                }
            )
    return instruction_files


def file_template_id(
    relative: str,
    owner_kind: str,
    owner_id: str | None,
) -> str:
    if owner_kind == "core":
        return CORE_TEMPLATE_IDS[relative]
    if owner_kind == "adapter" and owner_id is not None:
        return ADAPTER_TEMPLATE_IDS[owner_id][relative]
    raise FoundryctlError(f"Invalid generated-file owner for {relative}")


def file_template_version(owner_kind: str, owner_id: str | None) -> str:
    if owner_kind == "core":
        return CORE_HARNESS_VERSION
    if owner_kind == "adapter" and owner_id is not None:
        return ADAPTER_VERSIONS[owner_id]
    raise FoundryctlError("Invalid generated-file owner")


def harness_file_record(
    relative: str,
    asset: str,
    owner_kind: str,
    owner_id: str | None,
    *,
    installed_path: Path | None = None,
) -> dict[str, object]:
    template_digest = sha256_text(asset_text(asset))
    current = (
        installed_path is None
        or not installed_path.exists()
        or (
            installed_path.is_file()
            and not installed_path.is_symlink()
            and sha256_file(installed_path) == template_digest
        )
    )
    record: dict[str, object] = {
        "path": relative,
        "ownership": "seeded",
        "owner_kind": owner_kind,
        "template_id": file_template_id(relative, owner_kind, owner_id),
        "template_version": (
            file_template_version(owner_kind, owner_id)
            if current
            else LEGACY_UNVERSIONED
        ),
        "template_sha256": template_digest if current else None,
        "installed_sha256": template_digest if current else None,
    }
    if owner_kind == "adapter":
        record["owner_id"] = owner_id
    return record


def harness_manifest(
    repo: Path | None,
    adapter_ids: tuple[str, ...],
    *,
    governance_profile: str = DEFAULT_GOVERNANCE_PROFILE,
    applied_migrations: list[dict[str, str]] | None = None,
    existing_records: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    adapters = normalize_adapter_ids(adapter_ids)
    records: list[dict[str, object]] = []
    for relative, asset, owner_kind, owner_id in selected_file_assets(adapters):
        previous = (existing_records or {}).get(relative)
        target = repo / relative if repo is not None else None
        current = harness_file_record(
            relative,
            asset,
            owner_kind,
            owner_id,
            installed_path=target,
        )
        if (
            previous is not None
            and current["template_version"] == LEGACY_UNVERSIONED
            and previous.get("owner_kind") == owner_kind
            and previous.get("owner_id") == owner_id
        ):
            records.append(dict(previous))
        else:
            records.append(current)
    adapter_versions = tuple(
        (adapter_id, ADAPTER_VERSIONS[adapter_id]) for adapter_id in adapters
    )
    instruction_files = instruction_files_for_versions(
        CORE_HARNESS_VERSION,
        adapter_versions,
    )
    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "owner": HARNESS_OWNER,
        "producer": {
            "name": HARNESS_OWNER,
            "version": REPO_FOUNDRY_VERSION,
        },
        "core": {"version": CORE_HARNESS_VERSION},
        "adapters": [
            {
                "id": adapter_id,
                "version": ADAPTER_VERSIONS[adapter_id],
                "enforcement": ADAPTER_ENFORCEMENT[adapter_id],
            }
            for adapter_id in adapters
        ],
        "governance": governance_manifest(governance_profile),
        "components": list(PROFESSIONAL_COMPONENTS),
        "instruction_files": instruction_files,
        "files": records,
        "applied_migrations": list(applied_migrations or []),
    }


def adapter_list_payload() -> dict[str, object]:
    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "activation_protocol_version": ACTIVATION_PROTOCOL_VERSION,
        "governance": {
            "policy_schema": GOVERNANCE_POLICY_SCHEMA,
            "fresh_default": DEFAULT_GOVERNANCE_PROFILE,
            "profiles": list(GOVERNANCE_PROFILES),
            "modes": ["explore", "build", "governed"],
        },
        "adapters": [
            {
                "id": adapter_id,
                "version": ADAPTER_VERSIONS[adapter_id],
                "enforcement": ADAPTER_ENFORCEMENT[adapter_id],
                "capabilities": ADAPTER_CAPABILITIES[adapter_id],
            }
            for adapter_id in ADAPTER_ORDER
        ],
    }


def harness_schema_version(data: dict[str, object]) -> int:
    if "schema_version" in data:
        value = data["schema_version"]
    elif "version" in data:
        value = data["version"]
    else:
        raise FoundryctlError(
            "Harness manifest does not declare schema_version"
        )
    if not isinstance(value, int) or isinstance(value, bool):
        raise FoundryctlError("Harness schema version must be an integer")
    return value


def _validate_migrations(
    path: Path,
    value: object,
    prefix: str,
) -> None:
    if not isinstance(value, list):
        raise FoundryctlError(f"{prefix} applied_migrations contract")
    seen: set[str] = set()
    for index, migration in enumerate(value):
        label = f"applied_migrations[{index}]"
        if not isinstance(migration, dict) or set(migration) != {
            "id",
            "kind",
            "from",
            "to",
            "applied_by_version",
        }:
            raise FoundryctlError(f"{prefix} {label} contract")
        if not all(
            isinstance(migration[key], str) and migration[key]
            for key in migration
        ):
            raise FoundryctlError(f"{prefix} {label} values")
        migration_id = migration["id"]
        if migration_id in seen:
            raise FoundryctlError(
                f"{prefix} duplicate migration {migration_id}"
            )
        seen.add(migration_id)
        try:
            applied_by = semver_tuple(
                migration["applied_by_version"],
                f"{label}.applied_by_version",
            )
        except FoundryctlError as exc:
            raise FoundryctlError(f"{prefix} {exc}") from exc
        if applied_by > semver_tuple(
            REPO_FOUNDRY_VERSION,
            "RepoFoundry version",
        ):
            raise FoundryctlError(
                f"HARNESS_MIGRATION_TOO_NEW: {path}: {migration_id}"
            )


def validate_harness_v3_manifest_data(
    path: Path,
    data: dict[str, object],
) -> dict[str, object]:
    prefix = f"HARNESS_MANIFEST_INVALID: {path}:"
    required_keys = {
        "schema_version",
        "owner",
        "producer",
        "core",
        "adapters",
        "components",
        "instruction_files",
        "files",
        "applied_migrations",
    }
    allowed_keys = {*required_keys, "governance"}
    if not required_keys.issubset(data) or not set(data).issubset(allowed_keys):
        raise FoundryctlError(
            f"{prefix} schema 3 keys must contain "
            + ", ".join(sorted(required_keys))
            + "; optional keys: governance"
        )
    supported_owners = {HARNESS_OWNER, *LEGACY_HARNESS_OWNERS}
    if data["owner"] not in supported_owners:
        raise FoundryctlError(
            f"{prefix} unsupported owner {data['owner']!r}"
        )
    producer = data["producer"]
    if not isinstance(producer, dict) or set(producer) != {"name", "version"}:
        raise FoundryctlError(f"{prefix} producer contract")
    if producer["name"] not in supported_owners:
        raise FoundryctlError(
            f"{prefix} unsupported producer {producer['name']!r}"
        )
    if not isinstance(producer["version"], str):
        raise FoundryctlError(f"{prefix} producer.version")
    parsed_producer = semver_tuple(producer["version"], "producer.version")
    if parsed_producer > semver_tuple(REPO_FOUNDRY_VERSION, "RepoFoundry version"):
        raise FoundryctlError(
            f"HARNESS_PRODUCER_TOO_NEW: {path}: produced by RepoFoundry "
            f"{producer['version']}; installed version is {REPO_FOUNDRY_VERSION}"
        )

    core = data["core"]
    if not isinstance(core, dict) or set(core) != {"version"}:
        raise FoundryctlError(f"{prefix} core contract")
    if not isinstance(core["version"], str):
        raise FoundryctlError(f"{prefix} core.version")
    parsed_core = semver_tuple(core["version"], "core.version")
    if parsed_core > semver_tuple(CORE_HARNESS_VERSION, "Harness Core version"):
        raise FoundryctlError(
            f"HARNESS_CORE_TOO_NEW: {path}: Core {core['version']}; "
            f"installed Core is {CORE_HARNESS_VERSION}"
        )

    raw_adapters = data["adapters"]
    if not isinstance(raw_adapters, list) or not raw_adapters:
        raise FoundryctlError(f"{prefix} adapters contract")
    adapter_ids: list[str] = []
    declared_adapter_versions: list[tuple[str, str]] = []
    for index, adapter in enumerate(raw_adapters):
        label = f"adapters[{index}]"
        if not isinstance(adapter, dict) or set(adapter) != {
            "id",
            "version",
            "enforcement",
        }:
            raise FoundryctlError(f"{prefix} {label} contract")
        adapter_id = adapter["id"]
        if not isinstance(adapter_id, str) or adapter_id not in ADAPTER_ORDER:
            raise FoundryctlError(
                f"HARNESS_ADAPTER_UNSUPPORTED: {path}: {adapter_id!r}"
            )
        if adapter_id in adapter_ids:
            raise FoundryctlError(
                f"{prefix} duplicate adapter {adapter_id!r}"
            )
        adapter_ids.append(adapter_id)
        version = adapter["version"]
        if not isinstance(version, str):
            raise FoundryctlError(f"{prefix} {label}.version")
        if semver_tuple(version, f"{label}.version") > semver_tuple(
            ADAPTER_VERSIONS[adapter_id],
            f"{adapter_id} adapter version",
        ):
            raise FoundryctlError(
                f"HARNESS_ADAPTER_TOO_NEW: {path}: {adapter_id}@{version}; "
                f"installed is {ADAPTER_VERSIONS[adapter_id]}"
            )
        declared_adapter_versions.append((adapter_id, version))
        if adapter["enforcement"] != ADAPTER_ENFORCEMENT[adapter_id]:
            raise FoundryctlError(f"{prefix} {label}.enforcement")
    normalized_adapters = normalize_adapter_ids(adapter_ids)
    if tuple(adapter_ids) != normalized_adapters:
        raise FoundryctlError(f"{prefix} adapters order contract")
    governance = data.get("governance")
    if governance is not None:
        if not isinstance(governance, dict) or set(governance) != {
            "policy_schema",
            "profile",
        }:
            raise FoundryctlError(f"{prefix} governance contract")
        if governance["policy_schema"] != GOVERNANCE_POLICY_SCHEMA:
            raise FoundryctlError(
                f"{prefix} governance.policy_schema must be "
                f"{GOVERNANCE_POLICY_SCHEMA}"
            )
        try:
            normalize_governance_profile(str(governance["profile"]))
        except FoundryctlError as exc:
            raise FoundryctlError(f"{prefix} {exc}") from exc
    core_supports_project_skill = parsed_core >= semver_tuple(
        CORE_PROJECT_SKILL_INTRODUCED,
        "Core project Skill introduction",
    )
    for adapter_id, version in declared_adapter_versions:
        requires_project_skill = adapter_id == "claude" or (
            adapter_id == "codex"
            and semver_tuple(version, "codex adapter version") >= semver_tuple(
                CODEX_PROJECT_SKILL_INTRODUCED,
                "Codex project Skill introduction",
            )
        )
        if requires_project_skill and not core_supports_project_skill:
            raise FoundryctlError(
                f"HARNESS_COMPONENT_INCOMPATIBLE: {path}: "
                f"{adapter_id}@{version} requires Core "
                f">={CORE_PROJECT_SKILL_INTRODUCED}"
            )

    if data["components"] not in (
        ["engineering-execution-plan"],
        PROFESSIONAL_COMPONENTS,
    ):
        raise FoundryctlError(f"{prefix} components contract")
    expected_instruction_files = instruction_files_for_versions(
        str(core["version"]),
        tuple(declared_adapter_versions),
    )
    if data["instruction_files"] != expected_instruction_files:
        raise FoundryctlError(f"{prefix} instruction_files contract")

    raw_files = data["files"]
    if not isinstance(raw_files, list):
        raise FoundryctlError(f"{prefix} files contract")
    expected_assets = versioned_file_assets(
        str(core["version"]),
        tuple(declared_adapter_versions),
    )
    expected_paths = [item[0] for item in expected_assets]
    actual_paths = [
        item.get("path") if isinstance(item, dict) else None
        for item in raw_files
    ]
    if actual_paths != expected_paths:
        raise FoundryctlError(f"{prefix} files path and ownership contract")
    assets_by_path = {
        relative: (asset, owner_kind, owner_id)
        for relative, asset, owner_kind, owner_id in expected_assets
    }
    for index, record in enumerate(raw_files):
        label = f"files[{index}]"
        if not isinstance(record, dict):
            raise FoundryctlError(f"{prefix} {label} contract")
        relative = record.get("path")
        assert isinstance(relative, str)
        asset, owner_kind, owner_id = assets_by_path[relative]
        keys = {
            "path",
            "ownership",
            "owner_kind",
            "template_id",
            "template_version",
            "template_sha256",
            "installed_sha256",
        }
        if owner_kind == "adapter":
            keys.add("owner_id")
        if set(record) != keys:
            raise FoundryctlError(f"{prefix} {label} contract")
        if record["ownership"] != "seeded":
            raise FoundryctlError(f"{prefix} {label}.ownership")
        if record["owner_kind"] != owner_kind:
            raise FoundryctlError(f"{prefix} {label}.owner_kind")
        if owner_kind == "adapter" and record["owner_id"] != owner_id:
            raise FoundryctlError(f"{prefix} {label}.owner_id")
        if record["template_id"] != file_template_id(
            relative,
            owner_kind,
            owner_id,
        ):
            raise FoundryctlError(f"{prefix} {label}.template_id")
        version = record["template_version"]
        template_digest = record["template_sha256"]
        installed_digest = record["installed_sha256"]
        if version == LEGACY_UNVERSIONED:
            if template_digest is not None or installed_digest is not None:
                raise FoundryctlError(
                    f"{prefix} {label}: legacy-unversioned hashes must be null"
                )
            continue
        if not isinstance(version, str):
            raise FoundryctlError(f"{prefix} {label}.template_version")
        maximum = (
            str(core["version"])
            if owner_kind == "core"
            else dict(declared_adapter_versions)[str(owner_id)]
        )
        if semver_tuple(version, f"{label}.template_version") > semver_tuple(
            maximum,
            f"{label} owner version",
        ):
            raise FoundryctlError(
                f"HARNESS_TEMPLATE_TOO_NEW: {path}: {relative} uses {version}"
            )
        if (
            not isinstance(template_digest, str)
            or not specctl.SHA256_RE.fullmatch(template_digest)
            or not isinstance(installed_digest, str)
            or not specctl.SHA256_RE.fullmatch(installed_digest)
        ):
            raise FoundryctlError(
                f"{prefix} {label}: expected lowercase SHA-256 hashes"
            )
        installed_maximum = file_template_version(owner_kind, owner_id)
        if (
            maximum == installed_maximum
            and version == installed_maximum
            and template_digest != sha256_text(asset_text(asset))
        ):
            raise FoundryctlError(
                f"{prefix} {label}.template_sha256 does not match the "
                "installed RepoFoundry template"
            )
    _validate_migrations(path, data["applied_migrations"], prefix)
    return data


def validate_codex_harness_manifest_data(
    path: Path,
    data: object,
) -> dict[str, object]:
    prefix = f"HARNESS_MANIFEST_INVALID: {path}:"
    if not isinstance(data, dict):
        raise FoundryctlError(f"{prefix} expected a JSON object")
    try:
        schema_version = harness_schema_version(data)
    except FoundryctlError as exc:
        raise FoundryctlError(f"{prefix} {exc}") from exc
    supported_owners = {HARNESS_OWNER, *LEGACY_HARNESS_OWNERS}

    if schema_version == LEGACY_HARNESS_SCHEMA_VERSION:
        owner = data.get("owner")
        if owner not in supported_owners:
            raise FoundryctlError(f"{prefix} unsupported owner {owner!r}")
        if data != legacy_codex_harness_manifest(owner=str(owner)):
            raise FoundryctlError(
                f"{prefix} expected the Codex Harness schema version 1 "
                f"contract with AGENTS.md max_lines "
                f"{CODEX_AGENT_MAX_LINES}"
            )
        return data

    if schema_version > HARNESS_SCHEMA_VERSION:
        raise FoundryctlError(
            f"HARNESS_SCHEMA_TOO_NEW: {path}: schema {schema_version}; "
            f"this RepoFoundry supports up to {HARNESS_SCHEMA_VERSION}"
        )
    if schema_version == HARNESS_SCHEMA_VERSION:
        return validate_harness_v3_manifest_data(path, data)
    if schema_version != PROFILE_HARNESS_SCHEMA_VERSION:
        raise FoundryctlError(
            f"{prefix} unsupported schema version {schema_version}"
        )

    expected_keys = {
        "schema_version",
        "owner",
        "producer",
        "profile",
        "components",
        "instruction_files",
        "required_files",
        "files",
        "applied_migrations",
    }
    if set(data) != expected_keys:
        raise FoundryctlError(
            f"{prefix} schema {PROFILE_HARNESS_SCHEMA_VERSION} keys must be "
            + ", ".join(sorted(expected_keys))
        )
    owner = data["owner"]
    if owner not in supported_owners:
        raise FoundryctlError(f"{prefix} unsupported owner {owner!r}")

    producer = data["producer"]
    if not isinstance(producer, dict) or set(producer) != {
        "name",
        "version",
    }:
        raise FoundryctlError(f"{prefix} producer contract")
    if producer["name"] not in supported_owners:
        raise FoundryctlError(
            f"{prefix} unsupported producer {producer['name']!r}"
        )
    producer_version = producer["version"]
    if not isinstance(producer_version, str):
        raise FoundryctlError(f"{prefix} producer.version")
    try:
        parsed_producer = semver_tuple(
            producer_version,
            "producer.version",
        )
    except FoundryctlError as exc:
        raise FoundryctlError(f"{prefix} {exc}") from exc
    if parsed_producer > semver_tuple(
        REPO_FOUNDRY_VERSION,
        "RepoFoundry version",
    ):
        raise FoundryctlError(
            f"HARNESS_PRODUCER_TOO_NEW: {path}: produced by "
            f"RepoFoundry {producer_version}; installed version is "
            f"{REPO_FOUNDRY_VERSION}"
        )

    profile = data["profile"]
    if not isinstance(profile, dict) or set(profile) != {"id", "version"}:
        raise FoundryctlError(f"{prefix} profile contract")
    if profile["id"] != CODEX_HARNESS_PROFILE:
        raise FoundryctlError(
            f"{prefix} unsupported profile {profile['id']!r}"
        )
    profile_version = profile["version"]
    if not isinstance(profile_version, str):
        raise FoundryctlError(f"{prefix} profile.version")
    try:
        parsed_profile = semver_tuple(profile_version, "profile.version")
    except FoundryctlError as exc:
        raise FoundryctlError(f"{prefix} {exc}") from exc
    if parsed_profile > semver_tuple(
        CODEX_HARNESS_PROFILE_VERSION,
        "Codex profile version",
    ):
        raise FoundryctlError(
            f"HARNESS_PROFILE_TOO_NEW: {path}: Codex profile "
            f"{profile_version}; installed profile is "
            f"{CODEX_HARNESS_PROFILE_VERSION}"
        )

    expected_static = codex_harness_manifest()
    for key in ("components", "instruction_files", "required_files"):
        if data[key] != expected_static[key]:
            raise FoundryctlError(f"{prefix} {key} contract")

    files = data["files"]
    if not isinstance(files, list):
        raise FoundryctlError(f"{prefix} files contract")
    file_paths = [
        item.get("path") if isinstance(item, dict) else None
        for item in files
    ]
    if any(not isinstance(relative, str) for relative in file_paths):
        raise FoundryctlError(f"{prefix} files path contract")
    if (
        len(set(file_paths)) != len(file_paths)
        or any(relative not in CODEX_SEEDED_FILES for relative in file_paths)
        or file_paths
        != [
            relative
            for relative in CODEX_SEEDED_FILES
            if relative in file_paths
        ]
        or any(relative not in file_paths for relative in CODEX_REQUIRED_FILES)
        or (
            parsed_profile
            == semver_tuple(
                CODEX_HARNESS_PROFILE_VERSION,
                "Codex profile version",
            )
            and file_paths != list(CODEX_SEEDED_FILES)
        )
    ):
        raise FoundryctlError(f"{prefix} files path contract")
    assets = dict(CODEX_BOOTSTRAP_FILE_ASSETS)
    for index, item in enumerate(files):
        label = f"files[{index}]"
        if not isinstance(item, dict) or set(item) != {
            "path",
            "ownership",
            "template_id",
            "template_version",
            "template_sha256",
            "installed_sha256",
        }:
            raise FoundryctlError(f"{prefix} {label} contract")
        relative = item["path"]
        assert isinstance(relative, str)
        if item["ownership"] != "seeded":
            raise FoundryctlError(f"{prefix} {label}.ownership")
        if item["template_id"] != CODEX_TEMPLATE_IDS[relative]:
            raise FoundryctlError(f"{prefix} {label}.template_id")
        template_version = item["template_version"]
        template_digest = item["template_sha256"]
        installed_digest = item["installed_sha256"]
        if template_version == LEGACY_UNVERSIONED:
            if template_digest is not None or installed_digest is not None:
                raise FoundryctlError(
                    f"{prefix} {label}: legacy-unversioned hashes must be null"
                )
            continue
        if not isinstance(template_version, str):
            raise FoundryctlError(f"{prefix} {label}.template_version")
        try:
            parsed_template = semver_tuple(
                template_version,
                f"{label}.template_version",
            )
        except FoundryctlError as exc:
            raise FoundryctlError(f"{prefix} {exc}") from exc
        if parsed_template > semver_tuple(
            CODEX_HARNESS_PROFILE_VERSION,
            "Codex profile version",
        ):
            raise FoundryctlError(
                f"HARNESS_TEMPLATE_TOO_NEW: {path}: {relative} uses "
                f"template {template_version}"
            )
        if (
            not isinstance(template_digest, str)
            or not specctl.SHA256_RE.fullmatch(template_digest)
            or not isinstance(installed_digest, str)
            or not specctl.SHA256_RE.fullmatch(installed_digest)
        ):
            raise FoundryctlError(
                f"{prefix} {label}: expected lowercase SHA-256 hashes"
            )
        # Schema 2 records refer to the v0.1.x Codex profile. RepoFoundry 0.2
        # intentionally no longer compares those template bytes with current
        # adapter assets; migration safety uses the recorded installed digest.

    migrations = data["applied_migrations"]
    if not isinstance(migrations, list):
        raise FoundryctlError(f"{prefix} applied_migrations contract")
    seen_migrations: set[str] = set()
    for index, migration in enumerate(migrations):
        label = f"applied_migrations[{index}]"
        if not isinstance(migration, dict) or set(migration) != {
            "id",
            "kind",
            "from",
            "to",
            "applied_by_version",
        }:
            raise FoundryctlError(f"{prefix} {label} contract")
        if not all(
            isinstance(migration[key], str) and migration[key]
            for key in migration
        ):
            raise FoundryctlError(f"{prefix} {label} values")
        migration_id = migration["id"]
        if migration_id in seen_migrations:
            raise FoundryctlError(f"{prefix} duplicate migration {migration_id}")
        seen_migrations.add(migration_id)
        try:
            applied_by = semver_tuple(
                migration["applied_by_version"],
                f"{label}.applied_by_version",
            )
        except FoundryctlError as exc:
            raise FoundryctlError(f"{prefix} {exc}") from exc
        if applied_by > semver_tuple(
            REPO_FOUNDRY_VERSION,
            "RepoFoundry version",
        ):
            raise FoundryctlError(
                f"HARNESS_MIGRATION_TOO_NEW: {path}: {migration_id}"
            )
    return data


def load_codex_harness_manifest(repo: Path) -> dict[str, object]:
    path = harness_path(repo)
    if not path.exists():
        raise FoundryctlError(
            f"HARNESS_MANIFEST_MISSING: {path}: "
            "run foundryctl bootstrap --adapter <id> --apply"
        )
    reject_symlink_path(repo, path)
    if not path.is_file():
        raise FoundryctlError(
            f"HARNESS_MANIFEST_INVALID: {path}: expected a regular file"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FoundryctlError(
            f"HARNESS_MANIFEST_INVALID: {path}: {exc}"
        ) from exc
    return validate_codex_harness_manifest_data(path, data)


def load_harness_manifest(repo: Path) -> dict[str, object]:
    """Load every supported Harness schema through one public boundary."""
    return load_codex_harness_manifest(repo)


def harness_manifest_warnings(
    manifest: dict[str, object],
) -> list[str]:
    warnings: list[str] = []
    owner = manifest["owner"]
    if owner in LEGACY_HARNESS_OWNERS:
        warnings.append(
            f"HARNESS_LEGACY_OWNER: {HARNESS_MANIFEST}: {owner!r} remains "
            f"readable; upgrade rewrites it as {HARNESS_OWNER!r}"
        )
    schema = harness_schema_version(manifest)
    if schema < HARNESS_SCHEMA_VERSION:
        warnings.append(
            f"HARNESS_SCHEMA_UPGRADE_AVAILABLE: {HARNESS_MANIFEST}: "
            f"schema {schema} remains readable; preview `foundryctl --repo . "
            f"upgrade --to {REPO_FOUNDRY_VERSION}`"
        )
        return warnings

    if "governance" not in manifest:
        warnings.append(
            f"HARNESS_GOVERNANCE_STRICT_COMPATIBILITY: {HARNESS_MANIFEST}: "
            "schema 3 manifest predates governance profiles and remains strict; "
            "select adaptive only through an explicit previewed migration"
        )

    if manifest.get("components") != PROFESSIONAL_COMPONENTS:
        warnings.append(
            f"HARNESS_COMPONENT_UPGRADE_AVAILABLE: {HARNESS_MANIFEST}: "
            "register engineering-design through an explicit bootstrap or upgrade"
        )

    producer = manifest["producer"]
    assert isinstance(producer, dict)
    if producer["version"] != REPO_FOUNDRY_VERSION:
        warnings.append(
            f"HARNESS_PRODUCT_UPGRADE_AVAILABLE: {HARNESS_MANIFEST}: "
            f"{producer['version']} -> {REPO_FOUNDRY_VERSION}"
        )
    core = manifest["core"]
    assert isinstance(core, dict)
    if core["version"] != CORE_HARNESS_VERSION:
        warnings.append(
            f"HARNESS_CORE_UPGRADE_AVAILABLE: {HARNESS_MANIFEST}: "
            f"{core['version']} -> {CORE_HARNESS_VERSION}"
        )
    adapters = manifest["adapters"]
    assert isinstance(adapters, list)
    for adapter in adapters:
        assert isinstance(adapter, dict)
        adapter_id = str(adapter["id"])
        if adapter["version"] != ADAPTER_VERSIONS[adapter_id]:
            warnings.append(
                f"HARNESS_ADAPTER_UPGRADE_AVAILABLE: {HARNESS_MANIFEST}: "
                f"{adapter_id}@{adapter['version']} -> "
                f"{ADAPTER_VERSIONS[adapter_id]}"
            )
    files = manifest["files"]
    assert isinstance(files, list)
    legacy_paths = [
        str(item["path"])
        for item in files
        if isinstance(item, dict)
        and item.get("template_version") == LEGACY_UNVERSIONED
    ]
    if legacy_paths:
        warnings.append(
            "HARNESS_CUSTOMIZED_SEEDS_PRESERVED: template provenance is "
            "unknown for " + ", ".join(legacy_paths)
        )
    return warnings


def physical_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def managed_path_conflict(
    repo: Path,
    path: Path,
    expected: str,
) -> str:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return "path escapes repository"
    current = repo
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            return f"parent is a symbolic link: {current.relative_to(repo)}"
        if current.exists() and not current.is_dir():
            return f"parent is not a directory: {current.relative_to(repo)}"
    if path.is_symlink():
        return "symbolic links are not supported"
    if path.exists():
        if expected == "directory" and not path.is_dir():
            return "expected a directory"
        if expected == "file" and not path.is_file():
            return "expected a regular file"
    return ""


def execution_plan_contract(
    epctl: ModuleType,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    directories = tuple(str(item) for item in epctl.INIT_DIRECTORIES)
    files = tuple(
        str(relative) for relative, _ in epctl.INIT_FILE_ASSETS
    ) + ("docs/.epctl/state.json",)
    return directories, files


def design_contract(
    designctl: ModuleType,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(str(item) for item in designctl.INIT_DIRECTORIES),
        tuple(str(item) for item in designctl.INIT_FILES),
    )


# Frozen v0.1 profile algorithms are kept as executable migration references.
# Current CLI dispatch uses the schema 3 functions defined later in this file.
def _legacy_profile_bootstrap_plan(
    repo: Path,
    profile: str,
    initial_spec_source: dict[str, str],
    requested_spec_ids: tuple[str, ...] | None,
) -> dict[str, object]:
    if profile != CODEX_HARNESS_PROFILE:
        raise FoundryctlError(
            f"Unsupported bootstrap profile {profile!r}; "
            f"supported profiles: {CODEX_HARNESS_PROFILE}"
        )

    epctl = load_execution_plan_ctl()
    ep_directories, ep_files = execution_plan_contract(epctl)
    actions: list[dict[str, object]] = []
    warnings: list[str] = []

    directories = tuple(
        dict.fromkeys((*ep_directories, *CODEX_BOOTSTRAP_DIRECTORIES))
    )
    for relative in directories:
        path = repo / relative
        reason = managed_path_conflict(repo, path, "directory")
        if reason:
            actions.append(
                {
                    "action": "conflict",
                    "path": relative,
                    "reason": reason,
                }
            )
        elif path.is_dir():
            actions.append({"action": "preserve", "path": relative + "/"})
        else:
            actions.append(
                {"action": "create_directory", "path": relative + "/"}
            )

    expected_files = (
        *ep_files,
        *(relative for relative, _ in CODEX_BOOTSTRAP_FILE_ASSETS),
    )
    for relative in expected_files:
        path = repo / relative
        reason = managed_path_conflict(repo, path, "file")
        if not reason and relative == "AGENTS.md" and path.is_file():
            line_count = physical_line_count(path)
            if line_count > CODEX_AGENT_MAX_LINES:
                reason = (
                    f"HARNESS_AGENTS_LINE_LIMIT: actual {line_count} physical "
                    f"lines; required <= {CODEX_AGENT_MAX_LINES}"
                )
            elif line_count > CODEX_AGENT_TEMPLATE_TARGET_LINES:
                warnings.append(
                    f"HARNESS_AGENTS_LINE_BUDGET: AGENTS.md: actual "
                    f"{line_count} physical lines; hard limit is "
                    f"{CODEX_AGENT_MAX_LINES}"
                )
            if not reason:
                try:
                    agents_text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    reason = f"HARNESS_SPEC_ROUTE_INVALID: {exc}"
                else:
                    missing_routes = [
                        value
                        for value in CODEX_ROUTER_AGENTS_ROUTES
                        if value not in agents_text
                    ]
                    if missing_routes:
                        reason = (
                            "HARNESS_SPEC_ROUTE_MISSING: add the mandatory "
                            "Router route for " + ", ".join(missing_routes)
                        )
        if not reason and relative in CODEX_ROUTER_SKILL_FILES and path.is_file():
            asset = router_asset_by_target(relative)
            try:
                current_router_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                reason = f"HARNESS_SPEC_ROUTER_INVALID: {exc}"
            if (
                not reason
                and (
                    asset is None
                    or current_router_text != asset_text(asset)
                )
            ):
                reason = (
                    "HARNESS_SPEC_ROUTER_DRIFT: generated Router bytes differ "
                    "from this RepoFoundry release"
                )
        if not reason and relative == CODEX_HOOKS_FILE and path.is_file():
            hook_errors = validate_hook_config_file(repo)
            if hook_errors:
                reason = (
                    "; ".join(hook_errors)
                    + "; preserve existing Hooks and merge the RepoFoundry "
                    "groups explicitly"
                )
        if reason:
            actions.append(
                {
                    "action": "conflict",
                    "path": relative,
                    "reason": reason,
                }
            )
        elif path.is_file():
            actions.append({"action": "preserve", "path": relative})
        else:
            actions.append({"action": "create_file", "path": relative})

    manifest = harness_path(repo)
    reason = managed_path_conflict(repo, manifest, "file")
    if not reason and manifest.is_file():
        try:
            loaded_manifest = load_codex_harness_manifest(repo)
        except FoundryctlError as exc:
            reason = str(exc)
        else:
            warnings.extend(harness_manifest_warnings(loaded_manifest))
    if reason:
        actions.append(
            {
                "action": "conflict",
                "path": HARNESS_MANIFEST,
                "reason": reason,
            }
        )
    elif manifest.is_file():
        actions.append({"action": "preserve", "path": HARNESS_MANIFEST})
    else:
        actions.append({"action": "create_file", "path": HARNESS_MANIFEST})

    config = epctl.config_path(repo)
    reason = managed_path_conflict(repo, config, "file")
    roots: list[str] = []
    if not reason:
        try:
            loaded_config = epctl.load_config(repo)
            loaded_roots = loaded_config["architecture_roots"]
            if not isinstance(loaded_roots, list):
                raise FoundryctlError(
                    "engineering-execution-plan returned an invalid "
                    "architecture_roots contract"
                )
            roots = [str(item) for item in loaded_roots]
        except Exception as exc:
            reason = str(exc)
    if reason:
        actions.append(
            {
                "action": "conflict",
                "path": config.relative_to(repo).as_posix(),
                "reason": reason,
            }
        )
    elif "docs/design-docs" in roots:
        actions.append(
            {
                "action": "preserve",
                "path": config.relative_to(repo).as_posix(),
            }
        )
    else:
        actions.append({"action": "register", "path": "docs/design-docs"})

    selected_specs: list[str] = []
    configured_specs: list[str] = []
    required_specs: list[str] = []
    recommended_specs: list[str] = []
    available_specs: list[dict[str, object]] = []
    try:
        spec_plan = specctl.plan_spec_state(
            repo,
            initial_spec_source,
            operation="sync",
            allow_replace=False,
            requested_spec_ids=requested_spec_ids,
        )
    except specctl.SpecError as exc:
        actions.append(
            {
                "action": "conflict",
                "path": specctl.SPEC_MANIFEST,
                "reason": str(exc),
            }
        )
    else:
        actions.extend(spec_plan.actions)
        warnings.extend(spec_plan.warnings)
        selected_specs.extend(spec_plan.selected_spec_ids)
        spec_payload = specctl.plan_payload(spec_plan, mode="dry-run")
        configured_specs.extend(spec_payload["configured_specs"])
        required_specs.extend(spec_payload["required_specs"])
        recommended_specs.extend(spec_payload["recommended_specs"])
        available_specs.extend(spec_payload["available_specs"])

    return {
        "profile": profile,
        "components": ["engineering-execution-plan"],
        "specs": selected_specs,
        "configured_specs": configured_specs,
        "required_specs": required_specs,
        "recommended_specs": recommended_specs,
        "available_specs": available_specs,
        "actions": actions,
        "warnings": warnings,
    }


def _legacy_validate_codex_harness(
    repo: Path,
    *,
    require_manifest: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = harness_path(repo)
    if not path.exists():
        if require_manifest:
            errors.append(
                f"HARNESS_MANIFEST_MISSING: {path}: "
                "run foundryctl bootstrap --profile codex --apply"
            )
        return errors, warnings
    try:
        manifest = load_codex_harness_manifest(repo)
    except FoundryctlError as exc:
        return [str(exc)], warnings
    warnings.extend(harness_manifest_warnings(manifest))

    required_files = manifest["required_files"]
    if not isinstance(required_files, list):
        return [f"HARNESS_MANIFEST_INVALID: {path}: required_files"], warnings
    for relative in required_files:
        if not isinstance(relative, str):
            errors.append(
                f"HARNESS_MANIFEST_INVALID: {path}: non-string required file"
            )
            continue
        target = repo / relative
        reason = managed_path_conflict(repo, target, "file")
        if reason:
            errors.append(
                f"HARNESS_REQUIRED_FILE_INVALID: {relative}: {reason}"
            )
            continue
        if not target.is_file():
            errors.append(
                f"HARNESS_REQUIRED_FILE_MISSING: {relative}: "
                "run foundryctl bootstrap --profile codex --apply"
            )
            continue
        todo_count = target.read_text(encoding="utf-8").count(
            BOOTSTRAP_TODO_MARKER
        )
        if todo_count:
            warnings.append(
                f"HARNESS_BOOTSTRAP_TODO: {relative}: "
                f"{todo_count} bootstrap TODO marker(s) remain"
            )

    instruction_files = manifest["instruction_files"]
    if not isinstance(instruction_files, list):
        return [
            f"HARNESS_MANIFEST_INVALID: {path}: instruction_files"
        ], warnings
    for item in instruction_files:
        if not isinstance(item, dict):
            errors.append(
                f"HARNESS_MANIFEST_INVALID: {path}: instruction file entry"
            )
            continue
        relative = item.get("path")
        maximum = item.get("max_lines")
        if not isinstance(relative, str) or not isinstance(maximum, int):
            errors.append(
                f"HARNESS_MANIFEST_INVALID: {path}: instruction file contract"
            )
            continue
        target = repo / relative
        if not target.is_file() or target.is_symlink():
            continue
        actual = physical_line_count(target)
        if actual > maximum:
            errors.append(
                f"HARNESS_AGENTS_LINE_LIMIT: {relative}: actual {actual} "
                f"physical lines; required <= {maximum}"
            )
        elif actual > CODEX_AGENT_TEMPLATE_TARGET_LINES:
            warnings.append(
                f"HARNESS_AGENTS_LINE_BUDGET: {relative}: actual {actual} "
                f"physical lines; hard limit is {maximum}"
            )

    try:
        epctl = load_execution_plan_ctl()
        roots = epctl.load_config(repo)["architecture_roots"]
        if not isinstance(roots, list):
            raise FoundryctlError("architecture_roots is not a list")
    except Exception as exc:
        errors.append(f"HARNESS_ARCHITECTURE_ROOT_INVALID: {exc}")
    else:
        if "docs/design-docs" not in roots:
            errors.append(
                "HARNESS_ARCHITECTURE_ROOT_MISSING: docs/design-docs: "
                "run foundryctl bootstrap --profile codex --apply"
            )
    spec_errors, spec_warnings = specctl.validate_spec_state(
        repo,
        require_manifest=False,
    )
    errors.extend(spec_errors)
    warnings.extend(spec_warnings)
    router_errors, router_warnings = validate_spec_router(repo)
    errors.extend(router_errors)
    warnings.extend(router_warnings)
    return errors, warnings


def migration_record(
    migration_id: str,
    kind: str,
    from_value: str,
    to_value: str,
) -> dict[str, str]:
    return {
        "id": migration_id,
        "kind": kind,
        "from": from_value,
        "to": to_value,
        "applied_by_version": REPO_FOUNDRY_VERSION,
    }


def append_migration(
    manifest: dict[str, object],
    migration: dict[str, str],
) -> None:
    migrations = manifest["applied_migrations"]
    if not isinstance(migrations, list):  # pragma: no cover - validated
        raise FoundryctlError("Harness applied_migrations is invalid")
    if not any(
        isinstance(item, dict) and item.get("id") == migration["id"]
        for item in migrations
    ):
        migrations.append(migration)


def append_component_migrations(
    candidate: dict[str, object],
    previous: dict[str, object],
) -> None:
    """Record schema 3 Core/adapter version transitions once."""
    if harness_schema_version(previous) != HARNESS_SCHEMA_VERSION:
        return
    previous_components = previous.get("components")
    if previous_components != PROFESSIONAL_COMPONENTS:
        old_components = (
            ",".join(str(item) for item in previous_components)
            if isinstance(previous_components, list)
            else "unknown"
        )
        append_migration(
            candidate,
            migration_record(
                "components-add-engineering-design",
                "components",
                old_components,
                ",".join(PROFESSIONAL_COMPONENTS),
            ),
        )
    previous_core = previous["core"]
    if not isinstance(previous_core, dict):  # pragma: no cover - validated
        raise FoundryctlError("Harness Core contract is invalid")
    old_core = str(previous_core["version"])
    if old_core != CORE_HARNESS_VERSION:
        append_migration(
            candidate,
            migration_record(
                f"core-{old_core}-to-{CORE_HARNESS_VERSION}",
                "core",
                old_core,
                CORE_HARNESS_VERSION,
            ),
        )
    raw_adapters = previous["adapters"]
    if not isinstance(raw_adapters, list):  # pragma: no cover - validated
        raise FoundryctlError("Harness adapter contract is invalid")
    for adapter in raw_adapters:
        if not isinstance(adapter, dict):  # pragma: no cover - validated
            continue
        adapter_id = str(adapter["id"])
        old_version = str(adapter["version"])
        new_version = ADAPTER_VERSIONS[adapter_id]
        if old_version == new_version:
            continue
        append_migration(
            candidate,
            migration_record(
                f"adapter-{adapter_id}-{old_version}-to-{new_version}",
                "adapter",
                f"{adapter_id}@{old_version}",
                f"{adapter_id}@{new_version}",
            ),
        )


def _legacy_plan_harness_upgrade(
    repo: Path,
    target_version: str,
) -> tuple[
    dict[str, object],
    dict[str, str],
    dict[str, object],
    bool,
]:
    try:
        semver_tuple(target_version, "--to")
    except FoundryctlError as exc:
        raise FoundryctlError(f"UPGRADE_TARGET_INVALID: {exc}") from exc
    if target_version != REPO_FOUNDRY_VERSION:
        raise FoundryctlError(
            f"UPGRADE_TARGET_UNAVAILABLE: installed RepoFoundry contains "
            f"only migration target {REPO_FOUNDRY_VERSION}; requested "
            f"{target_version}"
        )

    manifest = load_codex_harness_manifest(repo)
    schema = harness_schema_version(manifest)
    actions: list[dict[str, object]] = []
    warnings: list[str] = []
    file_writes: dict[str, str] = {}
    assets = dict(CODEX_BOOTSTRAP_FILE_ASSETS)

    conflict_paths: set[str] = set()
    for relative in CODEX_SEEDED_FILES:
        target = repo / relative
        reason = managed_path_conflict(repo, target, "file")
        if (
            not reason
            and relative in CODEX_REQUIRED_FILES
            and not target.is_file()
        ):
            reason = "required seeded file is missing"
        if reason:
            conflict_paths.add(relative)
            actions.append(
                {"action": "conflict", "path": relative, "reason": reason}
            )

    if schema == LEGACY_HARNESS_SCHEMA_VERSION:
        candidate = codex_harness_manifest(
            repo,
            applied_migrations=[
                migration_record(
                    HARNESS_V1_TO_V2_MIGRATION,
                    "schema",
                    "1",
                    str(HARNESS_SCHEMA_VERSION),
                )
            ],
        )
        records = candidate["files"]
        assert isinstance(records, list)
        for record in records:
            assert isinstance(record, dict)
            relative = str(record["path"])
            if relative in conflict_paths:
                continue
            if relative in CODEX_GENERATED_FILES:
                if record["template_version"] == LEGACY_UNVERSIONED:
                    target = repo / relative
                    if not target.exists():
                        file_writes[relative] = asset_text(assets[relative])
                        record.clear()
                        record.update(
                            codex_file_record(relative, assets[relative])
                        )
                        actions.append(
                            {
                                "action": "create_file",
                                "path": relative,
                                "reason": "new generated profile seed",
                            }
                        )
                    else:
                        conflict_paths.add(relative)
                        actions.append(
                            {
                                "action": "conflict",
                                "path": relative,
                                "reason": (
                                    "generated profile path differs from "
                                    "the bundled seed; merge explicitly"
                                ),
                            }
                        )
                else:
                    actions.append(
                        {
                            "action": "record_provenance",
                            "path": relative,
                            "template_version": (
                                CODEX_HARNESS_PROFILE_VERSION
                            ),
                        }
                    )
                continue
            if record["template_version"] == LEGACY_UNVERSIONED:
                actions.append(
                    {
                        "action": "preserve",
                        "path": relative,
                        "reason": "legacy file differs from the current seed",
                    }
                )
                warnings.append(
                    f"HARNESS_CUSTOMIZED_SEED_PRESERVED: {relative}: "
                    "template provenance is unknown; future upgrades will "
                    "not overwrite it automatically"
                )
            else:
                actions.append(
                    {
                        "action": "record_provenance",
                        "path": relative,
                        "template_version": CODEX_HARNESS_PROFILE_VERSION,
                    }
                )
        actions.append(
            {
                "action": "update_manifest",
                "path": HARNESS_MANIFEST,
                "from_schema": LEGACY_HARNESS_SCHEMA_VERSION,
                "to_schema": HARNESS_SCHEMA_VERSION,
            }
        )
        from_state: dict[str, object] = {
            "distribution": LEGACY_UNVERSIONED,
            "schema": LEGACY_HARNESS_SCHEMA_VERSION,
            "profile": f"{CODEX_HARNESS_PROFILE}@{LEGACY_UNVERSIONED}",
        }
    else:
        candidate = json.loads(json.dumps(manifest))
        producer = manifest["producer"]
        profile = manifest["profile"]
        records = candidate["files"]
        assert isinstance(producer, dict)
        assert isinstance(profile, dict)
        assert isinstance(records, list)
        from_state = {
            "distribution": producer["version"],
            "schema": schema,
            "profile": (
                f"{profile['id']}@{profile['version']}"
            ),
        }
        old_profile_version = str(profile["version"])
        changed_templates = False
        records_by_path = {
            str(record["path"]): record
            for record in records
            if isinstance(record, dict)
        }
        next_records: list[dict[str, object]] = []
        for relative in CODEX_SEEDED_FILES:
            target = repo / relative
            record = records_by_path.get(relative)
            current_record = codex_file_record(relative, assets[relative])
            current_digest = str(current_record["template_sha256"])
            if relative in conflict_paths:
                next_records.append(
                    record
                    if record is not None
                    else codex_file_record(
                        relative,
                        assets[relative],
                        installed_path=target,
                    )
                )
                continue

            if record is None:
                changed_templates = True
                if not target.exists() and relative in CODEX_GENERATED_FILES:
                    file_writes[relative] = asset_text(assets[relative])
                    next_records.append(current_record)
                    actions.append(
                        {
                            "action": "create_file",
                            "path": relative,
                            "reason": "new generated profile seed",
                        }
                    )
                    continue
                inferred = codex_file_record(
                    relative,
                    assets[relative],
                    installed_path=target,
                )
                if inferred["template_version"] != LEGACY_UNVERSIONED:
                    next_records.append(inferred)
                    actions.append(
                        {
                            "action": "update_metadata",
                            "path": relative,
                            "template_version": (
                                CODEX_HARNESS_PROFILE_VERSION
                            ),
                        }
                    )
                elif relative in CODEX_GENERATED_FILES:
                    conflict_paths.add(relative)
                    next_records.append(inferred)
                    actions.append(
                        {
                            "action": "conflict",
                            "path": relative,
                            "reason": (
                                "generated profile path differs from the "
                                "bundled seed; merge explicitly"
                            ),
                        }
                    )
                else:
                    next_records.append(inferred)
                    actions.append(
                        {
                            "action": "preserve",
                            "path": relative,
                            "reason": "customized seed has no safe base",
                        }
                    )
                    warnings.append(
                        f"HARNESS_CUSTOMIZED_SEED_PRESERVED: {relative}: "
                        "manual reconciliation is required to adopt the "
                        "current template"
                    )
                continue

            if not target.is_file() or target.is_symlink():
                if not target.exists() and relative in CODEX_GENERATED_FILES:
                    file_writes[relative] = asset_text(assets[relative])
                    next_records.append(current_record)
                    changed_templates = True
                    actions.append(
                        {
                            "action": "create_file",
                            "path": relative,
                            "reason": "restore generated profile seed",
                        }
                    )
                else:
                    next_records.append(record)
                continue

            actual_digest = sha256_file(target)
            template_version = record["template_version"]
            if template_version == CODEX_HARNESS_PROFILE_VERSION:
                if (
                    relative in CODEX_GENERATED_FILES
                    and actual_digest != current_digest
                ):
                    conflict_paths.add(relative)
                    actions.append(
                        {
                            "action": "conflict",
                            "path": relative,
                            "reason": (
                                "generated profile bytes drifted from the "
                                "current template"
                            ),
                        }
                    )
                next_records.append(record)
                continue
            if template_version == LEGACY_UNVERSIONED:
                if actual_digest == current_digest:
                    record.clear()
                    record.update(current_record)
                    changed_templates = True
                    actions.append(
                        {
                            "action": "update_metadata",
                            "path": relative,
                            "template_version": (
                                CODEX_HARNESS_PROFILE_VERSION
                            ),
                        }
                    )
                    next_records.append(record)
                elif relative in CODEX_GENERATED_FILES:
                    conflict_paths.add(relative)
                    next_records.append(record)
                    actions.append(
                        {
                            "action": "conflict",
                            "path": relative,
                            "reason": (
                                "generated profile path has unknown "
                                "provenance; merge explicitly"
                            ),
                        }
                    )
                else:
                    next_records.append(record)
                    actions.append(
                        {
                            "action": "preserve",
                            "path": relative,
                            "reason": "customized seed has no safe base",
                        }
                    )
                    warnings.append(
                        f"HARNESS_CUSTOMIZED_SEED_PRESERVED: {relative}: "
                        "manual reconciliation is required to adopt the "
                        "current template"
                    )
                continue

            installed_digest = record["installed_sha256"]
            if actual_digest == current_digest:
                record.clear()
                record.update(current_record)
                changed_templates = True
                actions.append(
                    {
                        "action": "update_metadata",
                        "path": relative,
                        "template_version": CODEX_HARNESS_PROFILE_VERSION,
                    }
                )
                next_records.append(record)
            elif actual_digest == installed_digest:
                file_writes[relative] = asset_text(assets[relative])
                record.clear()
                record.update(current_record)
                changed_templates = True
                actions.append(
                    {
                        "action": "replace_file",
                        "path": relative,
                        "reason": "seed is unchanged from its recorded base",
                        "template_version": CODEX_HARNESS_PROFILE_VERSION,
                    }
                )
                next_records.append(record)
            else:
                conflict_paths.add(relative)
                next_records.append(record)
                actions.append(
                    {
                        "action": "conflict",
                        "path": relative,
                        "reason": (
                            "file changed since its recorded template was "
                            "installed; merge manually"
                        ),
                    }
                )

        candidate["files"] = next_records

        candidate["owner"] = HARNESS_OWNER
        candidate_producer = candidate["producer"]
        candidate_profile = candidate["profile"]
        assert isinstance(candidate_producer, dict)
        assert isinstance(candidate_profile, dict)
        candidate_producer["name"] = HARNESS_OWNER
        candidate_producer["version"] = REPO_FOUNDRY_VERSION
        candidate_profile["id"] = CODEX_HARNESS_PROFILE
        candidate_profile["version"] = CODEX_HARNESS_PROFILE_VERSION
        if old_profile_version != CODEX_HARNESS_PROFILE_VERSION:
            append_migration(
                candidate,
                migration_record(
                    (
                        f"codex-profile-{old_profile_version}-to-"
                        f"{CODEX_HARNESS_PROFILE_VERSION}"
                    ),
                    "profile",
                    old_profile_version,
                    CODEX_HARNESS_PROFILE_VERSION,
                ),
            )
        elif changed_templates:
            append_migration(
                candidate,
                migration_record(
                    f"codex-templates-to-{CODEX_HARNESS_PROFILE_VERSION}",
                    "templates",
                    "mixed",
                    CODEX_HARNESS_PROFILE_VERSION,
                ),
            )
        if candidate != manifest:
            actions.append(
                {
                    "action": "update_manifest",
                    "path": HARNESS_MANIFEST,
                    "from_schema": schema,
                    "to_schema": HARNESS_SCHEMA_VERSION,
                }
            )

    write_manifest = candidate != manifest
    payload: dict[str, object] = {
        "mode": "dry-run",
        "from": from_state,
        "to": {
            "distribution": target_version,
            "schema": HARNESS_SCHEMA_VERSION,
            "profile": (
                f"{CODEX_HARNESS_PROFILE}@"
                f"{CODEX_HARNESS_PROFILE_VERSION}"
            ),
        },
        "actions": actions,
        "warnings": list(dict.fromkeys(warnings)),
        "created": [],
        "updated": [],
    }
    return payload, file_writes, candidate, write_manifest


def _legacy_upgrade_harness(
    repo: Path,
    target_version: str,
    *,
    apply_changes: bool,
) -> dict[str, object]:
    planned, file_writes, candidate, write_manifest = _legacy_plan_harness_upgrade(
        repo,
        target_version,
    )
    conflicts = [
        item
        for item in planned["actions"]
        if isinstance(item, dict) and item.get("action") == "conflict"
    ]
    if not apply_changes:
        return planned
    if conflicts:
        details = "; ".join(
            f"{item.get('path')}: {item.get('reason')}"
            for item in conflicts
        )
        raise FoundryctlError(f"Harness upgrade preflight failed: {details}")

    created: list[str] = []
    updated: list[str] = []
    with repo_lock(repo):
        locked = _legacy_plan_harness_upgrade(repo, target_version)
        if locked != (planned, file_writes, candidate, write_manifest):
            raise FoundryctlError(
                "Harness upgrade preflight changed while acquiring the "
                "lock; rerun the dry-run"
            )
        touched = [*(repo / relative for relative in file_writes)]
        manifest_path = harness_path(repo)
        if write_manifest:
            touched.append(manifest_path)
        originals: dict[Path, str | None] = {
            path: (
                path.read_text(encoding="utf-8")
                if path.exists()
                else None
            )
            for path in touched
        }
        try:
            for relative, content in file_writes.items():
                target = repo / relative
                existed = target.exists()
                reject_symlink_path(repo, target)
                atomic_write(target, content)
                if existed:
                    updated.append(relative)
                else:
                    created.append(relative)
            if write_manifest:
                reject_symlink_path(repo, manifest_path)
                atomic_write(
                    manifest_path,
                    json.dumps(
                        candidate,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )
                updated.append(HARNESS_MANIFEST)
            errors, validation_warnings = _legacy_validate_codex_harness(
                repo,
                require_manifest=True,
            )
            if errors:
                raise FoundryctlError(
                    "Harness validation failed after upgrade: "
                    + "; ".join(errors)
                )
        except Exception as exc:
            rollback_errors: list[str] = []
            for path, content in originals.items():
                try:
                    if content is None:
                        if path.exists():
                            path.unlink()
                    else:
                        atomic_write(path, content)
                except Exception as rollback_exc:  # pragma: no cover
                    rollback_errors.append(f"{path}: {rollback_exc}")
            if rollback_errors:
                raise FoundryctlError(
                    f"{exc}; rollback also failed: "
                    + "; ".join(rollback_errors)
                ) from exc
            if isinstance(exc, FoundryctlError):
                raise
            raise FoundryctlError(f"Harness upgrade failed: {exc}") from exc

    result = dict(planned)
    result["mode"] = "apply"
    result["created"] = created
    result["updated"] = updated
    result["warnings"] = list(
        dict.fromkeys(
            [*list(planned["warnings"]), *validation_warnings]
        )
    )
    return result


def _legacy_bootstrap_repo(
    repo: Path,
    profile: str,
    *,
    apply_changes: bool,
    initial_spec_source: dict[str, str],
    requested_spec_ids: tuple[str, ...] | None,
) -> dict[str, object]:
    planned = _legacy_profile_bootstrap_plan(
        repo,
        profile,
        initial_spec_source,
        requested_spec_ids,
    )
    actions = planned["actions"]
    if not isinstance(actions, list):
        raise FoundryctlError("Bootstrap plan returned invalid actions")
    conflicts = [
        action
        for action in actions
        if isinstance(action, dict) and action.get("action") == "conflict"
    ]
    payload: dict[str, object] = {
        "profile": profile,
        "mode": "apply" if apply_changes else "dry-run",
        "components": list(planned["components"]),
        "specs": list(planned["specs"]),
        "configured_specs": list(planned["configured_specs"]),
        "required_specs": list(planned["required_specs"]),
        "recommended_specs": list(planned["recommended_specs"]),
        "available_specs": list(planned["available_specs"]),
        "actions": actions,
        "warnings": list(planned["warnings"]),
        "created": [],
        "updated": [],
    }
    if not apply_changes:
        return payload
    if conflicts:
        details = "; ".join(
            f"{item.get('path')}: {item.get('reason')}" for item in conflicts
        )
        raise FoundryctlError(
            f"Bootstrap preflight failed: {details}"
        )

    epctl = load_execution_plan_ctl()
    created: list[str] = []
    updated: list[str] = []
    harness_state_existed = (repo / HARNESS_STATE_DIRECTORY).is_dir()
    with repo_lock(repo):
        second_plan = _legacy_profile_bootstrap_plan(
            repo,
            profile,
            initial_spec_source,
            requested_spec_ids,
        )
        second_actions = second_plan["actions"]
        if not isinstance(second_actions, list):
            raise FoundryctlError(
                "Bootstrap locked plan returned invalid actions"
            )
        second_conflicts = [
            action
            for action in second_actions
            if isinstance(action, dict) and action.get("action") == "conflict"
        ]
        if second_conflicts:
            details = "; ".join(
                f"{item.get('path')}: {item.get('reason')}"
                for item in second_conflicts
            )
            raise FoundryctlError(
                f"Bootstrap preflight changed while locking: {details}"
            )

        if not harness_state_existed:
            created.append(HARNESS_STATE_DIRECTORY + "/")
        try:
            with epctl.repo_lock(repo):
                created.extend(epctl.init_repo(repo))
                for relative in CODEX_BOOTSTRAP_DIRECTORIES:
                    directory = repo / relative
                    reject_symlink_path(repo, directory)
                    if not directory.exists():
                        directory.mkdir(parents=True)
                        created.append(relative + "/")
                for relative, asset in CODEX_BOOTSTRAP_FILE_ASSETS:
                    target = repo / relative
                    reject_symlink_path(repo, target)
                    if ensure_file(target, asset):
                        created.append(relative)

                manifest = harness_path(repo)
                reject_symlink_path(repo, manifest)
                if not manifest.exists():
                    atomic_write(
                        manifest,
                        json.dumps(
                            codex_harness_manifest(repo),
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                    )
                    created.append(HARNESS_MANIFEST)

                config = epctl.config_path(repo)
                config_existed = config.exists()
                loaded_config = epctl.load_config(repo)
                roots = loaded_config["architecture_roots"]
                if not isinstance(roots, list):
                    raise FoundryctlError(
                        "engineering-execution-plan returned invalid "
                        "architecture_roots"
                    )
                if "docs/design-docs" not in roots:
                    roots.append("docs/design-docs")
                    epctl.save_config(repo, loaded_config)
                    if config_existed:
                        updated.append(config.relative_to(repo).as_posix())
                    else:
                        created.append(config.relative_to(repo).as_posix())

                spec_plan = specctl.plan_spec_state(
                    repo,
                    initial_spec_source,
                    operation="sync",
                    allow_replace=False,
                    requested_spec_ids=requested_spec_ids,
                )
                spec_created, spec_updated, spec_removed = (
                    specctl.apply_spec_plan(repo, spec_plan)
                )
                created.extend(spec_created)
                updated.extend(spec_updated)
                if spec_removed:
                    raise FoundryctlError(
                        "Bootstrap unexpectedly planned Spec removals"
                    )
        except FoundryctlError:
            raise
        except specctl.SpecError as exc:
            raise FoundryctlError(str(exc)) from exc
        except Exception as exc:
            raise FoundryctlError(
                f"engineering-execution-plan initialization failed: {exc}"
            ) from exc

    harness_errors, harness_warnings = _legacy_validate_codex_harness(
        repo,
        require_manifest=True,
    )
    if harness_errors:
        raise FoundryctlError(
            "Bootstrap Harness validation failed: "
            + "; ".join(harness_errors)
        )
    payload["warnings"] = list(
        dict.fromkeys(
            [
                *list(planned["warnings"]),
                *harness_warnings,
            ]
        )
    )
    payload["created"] = list(dict.fromkeys(created))
    payload["updated"] = list(dict.fromkeys(updated))
    return payload


def plan_harness_upgrade(
    repo: Path,
    target_version: str,
    *,
    governance_profile: str | None = None,
) -> tuple[
    dict[str, object],
    dict[str, str],
    dict[str, object],
    bool,
]:
    try:
        semver_tuple(target_version, "--to")
    except FoundryctlError as exc:
        raise FoundryctlError(f"UPGRADE_TARGET_INVALID: {exc}") from exc
    if target_version != REPO_FOUNDRY_VERSION:
        raise FoundryctlError(
            "UPGRADE_TARGET_UNAVAILABLE: installed RepoFoundry contains "
            f"only migration target {REPO_FOUNDRY_VERSION}; requested "
            f"{target_version}"
        )
    manifest = load_harness_manifest(repo)
    schema = harness_schema_version(manifest)
    previous_governance_profile = harness_governance_profile(manifest)
    target_governance_profile = normalize_governance_profile(
        governance_profile or previous_governance_profile
    )
    adapter_ids = _manifest_adapter_ids(manifest)
    old_records: dict[str, dict[str, object]] = {}
    raw_records = manifest.get("files")
    if isinstance(raw_records, list):
        old_records = {
            str(record["path"]): record
            for record in raw_records
            if isinstance(record, dict) and isinstance(record.get("path"), str)
        }
    migrations = (
        list(manifest.get("applied_migrations", []))
        if schema >= PROFILE_HARNESS_SCHEMA_VERSION
        else []
    )
    if schema == LEGACY_HARNESS_SCHEMA_VERSION:
        append_migration(
            {"applied_migrations": migrations},
            migration_record(
                HARNESS_V1_TO_V3_MIGRATION,
                "schema",
                "1",
                "3",
            ),
        )
    elif schema == PROFILE_HARNESS_SCHEMA_VERSION:
        append_migration(
            {"applied_migrations": migrations},
            migration_record(
                HARNESS_V2_TO_V3_MIGRATION,
                "schema",
                "2",
                "3",
            ),
        )

    actions: list[dict[str, object]] = []
    warnings: list[str] = []
    file_writes: dict[str, str] = {}
    record_overrides: dict[str, dict[str, object]] = {}
    epctl = load_execution_plan_ctl()
    additive_directories = tuple(
        str(item)
        for item in getattr(epctl, "UPGRADE_ADDITIVE_DIRECTORIES", ())
    )
    additive_files = tuple(
        (str(relative), str(asset))
        for relative, asset in getattr(
            epctl,
            "UPGRADE_ADDITIVE_FILE_ASSETS",
            (),
        )
    )
    for relative in additive_directories:
        target = repo / relative
        reason = managed_path_conflict(repo, target, "directory")
        if reason:
            actions.append(
                {"action": "conflict", "path": relative, "reason": reason}
            )
        elif target.is_dir():
            actions.append({"action": "preserve", "path": relative + "/"})
        else:
            actions.append(
                {
                    "action": "create_directory",
                    "path": relative + "/",
                    "reason": "new additive execution-plan infrastructure",
                }
            )
    for relative, asset in additive_files:
        target = repo / relative
        reason = managed_path_conflict(repo, target, "file")
        if reason:
            actions.append(
                {"action": "conflict", "path": relative, "reason": reason}
            )
        elif target.is_file():
            actions.append(
                {
                    "action": "preserve",
                    "path": relative,
                    "reason": "existing repository-owned additive file",
                }
            )
        else:
            file_writes[relative] = epctl.asset_text(asset)
            actions.append(
                {
                    "action": "create_file",
                    "path": relative,
                    "reason": "new additive execution-plan infrastructure",
                }
            )
    contract = selected_file_assets(adapter_ids)
    for relative, asset, owner_kind, owner_id in contract:
        target = repo / relative
        reason = managed_path_conflict(repo, target, "file")
        current_record = harness_file_record(
            relative,
            asset,
            owner_kind,
            owner_id,
        )
        generated = relative in _generated_for_owner(owner_kind, owner_id)
        if reason:
            actions.append(
                {"action": "conflict", "path": relative, "reason": reason}
            )
            record_overrides[relative] = current_record
            continue
        if not target.exists():
            if generated:
                file_writes[relative] = asset_text(asset)
                actions.append(
                    {
                        "action": "create_file",
                        "path": relative,
                        "reason": "new generated Core or adapter seed",
                    }
                )
                record_overrides[relative] = current_record
            else:
                actions.append(
                    {
                        "action": "conflict",
                        "path": relative,
                        "reason": "required seeded document is missing",
                    }
                )
                record_overrides[relative] = current_record
            continue
        actual_digest = sha256_file(target)
        current_digest = sha256_text(asset_text(asset))
        if actual_digest == current_digest:
            record_overrides[relative] = current_record
            previous = old_records.get(relative)
            if previous == current_record:
                actions.append({"action": "preserve", "path": relative})
            else:
                actions.append(
                    {
                        "action": "update_metadata",
                        "path": relative,
                        "template_version": file_template_version(
                            owner_kind,
                            owner_id,
                        ),
                    }
                )
            continue
        previous = old_records.get(relative)
        recorded_digest = (
            previous.get("installed_sha256")
            if isinstance(previous, dict)
            else None
        )
        if (
            isinstance(recorded_digest, str)
            and specctl.SHA256_RE.fullmatch(recorded_digest)
            and actual_digest == recorded_digest
        ):
            file_writes[relative] = asset_text(asset)
            record_overrides[relative] = current_record
            actions.append(
                {
                    "action": "replace_file",
                    "path": relative,
                    "reason": "seed is unchanged from its recorded base",
                    "template_version": file_template_version(
                        owner_kind,
                        owner_id,
                    ),
                }
            )
            continue
        customized = harness_file_record(
            relative,
            asset,
            owner_kind,
            owner_id,
            installed_path=target,
        )
        record_overrides[relative] = customized
        if generated:
            actions.append(
                {
                    "action": "conflict",
                    "path": relative,
                    "reason": (
                        "generated path is customized or has unknown "
                        "provenance; preserve bytes and merge explicitly"
                    ),
                }
            )
        else:
            actions.append(
                {
                    "action": "preserve",
                    "path": relative,
                    "reason": "repository-customized seeded document",
                }
            )
            warnings.append(
                f"HARNESS_CUSTOMIZED_SEED_PRESERVED: {relative}: template "
                "provenance is intentionally cleared"
            )

    candidate = harness_manifest(
        None,
        adapter_ids,
        governance_profile=target_governance_profile,
        applied_migrations=migrations,
    )
    candidate_records = candidate["files"]
    assert isinstance(candidate_records, list)
    candidate["files"] = [
        record_overrides[str(record["path"])]
        for record in candidate_records
        if isinstance(record, dict)
    ]
    if schema == HARNESS_SCHEMA_VERSION:
        append_component_migrations(candidate, manifest)
        producer = manifest["producer"]
        core = manifest["core"]
        assert isinstance(producer, dict)
        assert isinstance(core, dict)
        from_state: dict[str, object] = {
            "distribution": producer["version"],
            "schema": schema,
            "core": core["version"],
            "adapters": [
                f"{item['id']}@{item['version']}"
                for item in manifest["adapters"]
                if isinstance(item, dict)
            ],
        }
        if producer["version"] != REPO_FOUNDRY_VERSION:
            append_migration(
                candidate,
                migration_record(
                    f"distribution-{producer['version']}-to-{REPO_FOUNDRY_VERSION}",
                    "distribution",
                    str(producer["version"]),
                    REPO_FOUNDRY_VERSION,
                ),
            )
    else:
        from_state = {
            "distribution": (
                manifest.get("producer", {}).get("version", LEGACY_UNVERSIONED)
                if isinstance(manifest.get("producer"), dict)
                else LEGACY_UNVERSIONED
            ),
            "schema": schema,
            "profile": (
                "codex@1.0.0"
                if schema == PROFILE_HARNESS_SCHEMA_VERSION
                else f"codex@{LEGACY_UNVERSIONED}"
            ),
        }
    if target_governance_profile != previous_governance_profile:
        append_migration(
            candidate,
            migration_record(
                (
                    "governance-"
                    f"{previous_governance_profile}-to-{target_governance_profile}"
                ),
                "governance",
                previous_governance_profile,
                target_governance_profile,
            ),
        )
    validate_harness_v3_manifest_data(harness_path(repo), candidate)
    write_manifest = candidate != manifest
    if write_manifest:
        actions.append(
            {
                "action": "update_manifest",
                "path": HARNESS_MANIFEST,
                "from_schema": schema,
                "to_schema": HARNESS_SCHEMA_VERSION,
            }
        )
    payload: dict[str, object] = {
        "mode": "dry-run",
        "from": from_state,
        "to": {
            "distribution": target_version,
            "schema": HARNESS_SCHEMA_VERSION,
            "core": CORE_HARNESS_VERSION,
            "adapters": [
                f"{adapter_id}@{ADAPTER_VERSIONS[adapter_id]}"
                for adapter_id in adapter_ids
            ],
            "governance_profile": target_governance_profile,
        },
        "actions": actions,
        "warnings": list(dict.fromkeys(warnings)),
        "created": [],
        "updated": [],
    }
    return payload, file_writes, candidate, write_manifest


def upgrade_harness(
    repo: Path,
    target_version: str,
    *,
    apply_changes: bool,
    governance_profile: str | None = None,
) -> dict[str, object]:
    planned, file_writes, candidate, write_manifest = plan_harness_upgrade(
        repo,
        target_version,
        governance_profile=governance_profile,
    )
    conflicts = [
        item
        for item in planned["actions"]
        if isinstance(item, dict) and item.get("action") == "conflict"
    ]
    if not apply_changes:
        return planned
    if conflicts:
        details = "; ".join(
            f"{item.get('path')}: {item.get('reason')}" for item in conflicts
        )
        raise FoundryctlError(f"Harness upgrade preflight failed: {details}")
    additive_directories = [
        str(item["path"]).rstrip("/")
        for item in planned["actions"]
        if isinstance(item, dict) and item.get("action") == "create_directory"
    ]
    epctl = load_execution_plan_ctl()
    created: list[str] = []
    updated: list[str] = []
    validation_warnings: list[str] = []
    with repo_lock(repo):
        locked = plan_harness_upgrade(
            repo,
            target_version,
            governance_profile=governance_profile,
        )
        if locked != (planned, file_writes, candidate, write_manifest):
            raise FoundryctlError(
                "Harness upgrade preflight changed while acquiring the lock; "
                "rerun preview"
            )
        manifest_path = harness_path(repo)
        touched = [repo / relative for relative in file_writes]
        if write_manifest:
            touched.append(manifest_path)
        originals: dict[Path, str | None] = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in touched
        }
        missing_parents = {
            parent
            for path in touched
            for parent in path.parents
            if parent != repo and repo in parent.parents and not parent.exists()
        }
        missing_parents.update(
            repo / relative
            for relative in additive_directories
            if not (repo / relative).exists()
        )
        try:
            for relative in additive_directories:
                directory = repo / relative
                reject_symlink_path(repo, directory)
                if not directory.exists():
                    directory.mkdir(parents=True)
                    created.append(relative + "/")
            for relative, content in file_writes.items():
                target = repo / relative
                existed = target.exists()
                reject_symlink_path(repo, target)
                atomic_write(target, content)
                (updated if existed else created).append(relative)
            if write_manifest:
                atomic_write(
                    manifest_path,
                    json.dumps(
                        candidate,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ) + "\n",
                )
                updated.append(HARNESS_MANIFEST)
            errors, validation_warnings = validate_harness(
                repo,
                require_manifest=True,
            )
            view_errors, view_warnings = epctl.validate_decision_views(repo)
            errors.extend(view_errors)
            validation_warnings.extend(view_warnings)
            if errors:
                raise FoundryctlError(
                    "Harness validation failed after upgrade: " + "; ".join(errors)
                )
        except Exception as exc:
            rollback_errors: list[str] = []
            for path, content in originals.items():
                try:
                    if content is None:
                        if path.exists():
                            path.unlink()
                    else:
                        atomic_write(path, content)
                except Exception as rollback_exc:  # pragma: no cover
                    rollback_errors.append(f"{path}: {rollback_exc}")
            for directory in sorted(
                missing_parents,
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                raise FoundryctlError(
                    f"{exc}; rollback also failed: " + "; ".join(rollback_errors)
                ) from exc
            if isinstance(exc, FoundryctlError):
                raise
            raise FoundryctlError(f"Harness upgrade failed: {exc}") from exc
    result = dict(planned)
    result["mode"] = "apply"
    result["created"] = created
    result["updated"] = updated
    result["warnings"] = list(
        dict.fromkeys([*list(planned["warnings"]), *validation_warnings])
    )
    return result


def manage_specs(
    repo: Path,
    operation: str,
    *,
    apply_changes: bool,
    initial_spec_source: dict[str, str],
    update_spec_source: dict[str, str] | None,
    requested_spec_ids: tuple[str, ...] | None,
    keep_selection: bool = False,
) -> dict[str, object]:
    try:
        planned = specctl.plan_spec_state(
            repo,
            initial_spec_source,
            operation=operation,
            allow_replace=True,
            update_source=update_spec_source,
            requested_spec_ids=requested_spec_ids,
            keep_selection=keep_selection,
        )
    except specctl.SpecError as exc:
        raise FoundryctlError(str(exc)) from exc
    if planned.conflicts:
        details = "; ".join(
            f"{item.get('path')}: {item.get('reason')}"
            for item in planned.conflicts
        )
        if apply_changes:
            raise FoundryctlError(f"Spec preflight failed: {details}")
    if not apply_changes:
        return specctl.plan_payload(planned, mode="dry-run")

    with repo_lock(repo):
        try:
            locked_plan = specctl.plan_spec_state(
                repo,
                initial_spec_source,
                operation=operation,
                allow_replace=True,
                update_source=update_spec_source,
                requested_spec_ids=requested_spec_ids,
                keep_selection=keep_selection,
            )
        except specctl.SpecError as exc:
            raise FoundryctlError(str(exc)) from exc
        if locked_plan != planned:
            raise FoundryctlError(
                "Spec preflight changed while acquiring the Harness lock; "
                "rerun the dry-run"
            )
        try:
            created, updated, removed = specctl.apply_spec_plan(
                repo,
                locked_plan,
            )
        except specctl.SpecError as exc:
            raise FoundryctlError(str(exc)) from exc

    errors, validation_warnings = specctl.validate_spec_state(
        repo,
        require_manifest=True,
    )
    if errors:
        raise FoundryctlError(
            "Spec validation failed after apply: " + "; ".join(errors)
        )
    payload = specctl.plan_payload(
        planned,
        mode="apply",
        created=created,
        updated=updated,
        removed=removed,
    )
    payload["warnings"] = list(
        dict.fromkeys(
            [
                *list(planned.warnings),
                *validation_warnings,
            ]
        )
    )
    return payload


# Schema 3 Core and adapter implementation. The schema 1/2 helpers above remain
# intentionally available as read-only compatibility code and migration input.


def _manifest_adapter_ids(manifest: dict[str, object]) -> tuple[str, ...]:
    if harness_schema_version(manifest) < HARNESS_SCHEMA_VERSION:
        return ("codex",)
    adapters = manifest["adapters"]
    assert isinstance(adapters, list)
    return tuple(
        str(adapter["id"])
        for adapter in adapters
        if isinstance(adapter, dict)
    )


def _asset_contract(
    adapter_ids: tuple[str, ...],
) -> dict[str, tuple[str, str, str | None]]:
    return {
        relative: (asset, owner_kind, owner_id)
        for relative, asset, owner_kind, owner_id in selected_file_assets(
            adapter_ids
        )
    }


def _generated_for_owner(owner_kind: str, owner_id: str | None) -> frozenset[str]:
    if owner_kind == "core":
        return CORE_GENERATED_FILES
    if owner_kind == "adapter" and owner_id is not None:
        return ADAPTER_GENERATED_FILES[owner_id]
    return frozenset()


def _validate_template_file(
    repo: Path,
    relative: str,
    asset: str,
    label: str,
) -> list[str]:
    target = repo / relative
    reason = managed_path_conflict(repo, target, "file")
    if reason:
        return [f"{label}_INVALID: {relative}: {reason}"]
    if not target.is_file():
        return [f"{label}_MISSING: {relative}"]
    try:
        actual = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}_INVALID: {relative}: {exc}"]
    if actual != asset_text(asset):
        return [
            f"{label}_DRIFT: {relative}: generated bytes differ from this "
            "RepoFoundry release"
        ]
    return []


def validate_activation_engine(
    repo: Path,
    core_version: str = CORE_HARNESS_VERSION,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    assets = {
        relative: asset
        for relative, asset, owner_kind, _ in versioned_file_assets(
            core_version,
            (),
        )
        if owner_kind == "core" and relative in CORE_GENERATED_FILES
    }
    errors.extend(
        _validate_template_file(
            repo,
            CORE_ROUTER_PATH,
            assets[CORE_ROUTER_PATH],
            "HARNESS_SPEC_ENGINE",
        )
    )
    if CORE_PROJECT_SKILL_PATH in assets:
        errors.extend(
            _validate_template_file(
                repo,
                CORE_PROJECT_SKILL_PATH,
                assets[CORE_PROJECT_SKILL_PATH],
                "HARNESS_CORE_SKILL",
            )
        )
    return errors, []


def validate_adapter(
    repo: Path,
    adapter_id: str,
    adapter_version: str | None = None,
) -> tuple[list[str], list[str]]:
    if adapter_id not in ADAPTER_ORDER:
        return [f"HARNESS_ADAPTER_UNSUPPORTED: {adapter_id}"], []
    errors: list[str] = []
    warnings: list[str] = []
    selected_version = adapter_version or ADAPTER_VERSIONS[adapter_id]
    assets = tuple(
        (relative, asset)
        for relative, asset, _, owner_id in versioned_file_assets(
            "1.0.0",
            ((adapter_id, selected_version),),
        )
        if owner_id == adapter_id
    )
    if adapter_id == "codex":
        for relative, asset in assets:
            if relative in {
                "AGENTS.md",
                CODEX_HOOKS_FILE,
            }:
                continue
            errors.extend(
                _validate_template_file(
                    repo,
                    relative,
                    asset,
                    "HARNESS_CODEX_ADAPTER",
                )
            )
        errors.extend(validate_hook_config_file(repo))
        agents = repo / "AGENTS.md"
        if not agents.is_file() or agents.is_symlink():
            errors.append(
                "HARNESS_CODEX_ROUTE_MISSING: AGENTS.md: expected a "
                "non-symlink regular file"
            )
        else:
            try:
                text = agents.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                errors.append(f"HARNESS_CODEX_ROUTE_INVALID: AGENTS.md: {exc}")
            else:
                missing = [
                    route for route in CODEX_ROUTER_AGENTS_ROUTES
                    if route not in text
                ]
                if missing:
                    errors.append(
                        "HARNESS_CODEX_ROUTE_MISSING: AGENTS.md: "
                        + ", ".join(missing)
                    )
    elif adapter_id == "claude":
        for relative, asset in assets:
            errors.extend(
                _validate_template_file(
                    repo,
                    relative,
                    asset,
                    "HARNESS_CLAUDE_ADAPTER",
                )
            )
    else:
        for relative, asset in assets:
            errors.extend(
                _validate_template_file(
                    repo,
                    relative,
                    asset,
                    "HARNESS_PORTABLE_ADAPTER",
                )
            )
    return errors, warnings


def _validate_legacy_harness_files(
    repo: Path,
    manifest: dict[str, object],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required = manifest.get("required_files")
    if not isinstance(required, list):
        return ["HARNESS_MANIFEST_INVALID: required_files"], warnings
    for relative in required:
        if not isinstance(relative, str):
            errors.append("HARNESS_MANIFEST_INVALID: required file path")
            continue
        target = repo / relative
        if not target.is_file() or target.is_symlink():
            errors.append(f"HARNESS_REQUIRED_FILE_MISSING: {relative}")
    agents = repo / "AGENTS.md"
    if agents.is_file() and not agents.is_symlink():
        actual = physical_line_count(agents)
        if actual > CODEX_AGENT_MAX_LINES:
            errors.append(
                f"HARNESS_AGENTS_LINE_LIMIT: AGENTS.md: actual {actual} "
                f"physical lines; required <= {CODEX_AGENT_MAX_LINES}"
            )
    for relative in CODEX_ROUTER_SKILL_FILES:
        target = repo / relative
        if not target.is_file() or target.is_symlink():
            errors.append(f"HARNESS_SPEC_ROUTER_MISSING: {relative}")
    errors.extend(validate_hook_config_file(repo))
    return errors, warnings


def validate_harness(
    repo: Path,
    *,
    require_manifest: bool,
    adapter_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = harness_path(repo)
    if not path.exists():
        if require_manifest:
            errors.append(
                f"HARNESS_MANIFEST_MISSING: {path}: run foundryctl "
                "bootstrap --adapter <id> --apply"
            )
        return errors, warnings
    try:
        manifest = load_harness_manifest(repo)
    except FoundryctlError as exc:
        return [str(exc)], warnings
    warnings.extend(harness_manifest_warnings(manifest))
    schema = harness_schema_version(manifest)
    if schema < HARNESS_SCHEMA_VERSION:
        legacy_errors, legacy_warnings = _validate_legacy_harness_files(
            repo,
            manifest,
        )
        errors.extend(legacy_errors)
        warnings.extend(legacy_warnings)
    else:
        installed = _manifest_adapter_ids(manifest)
        core = manifest["core"]
        raw_adapters = manifest["adapters"]
        assert isinstance(core, dict)
        assert isinstance(raw_adapters, list)
        core_version = str(core["version"])
        installed_versions = {
            str(item["id"]): str(item["version"])
            for item in raw_adapters
            if isinstance(item, dict)
        }
        requested = installed if adapter_ids is None else normalize_adapter_ids(
            list(adapter_ids)
        )
        missing = [item for item in requested if item not in installed]
        if missing:
            errors.append(
                "HARNESS_ADAPTER_NOT_INSTALLED: " + ", ".join(missing)
            )
        files = manifest["files"]
        assert isinstance(files, list)
        records = {
            str(record["path"]): record
            for record in files
            if isinstance(record, dict)
        }
        checked_contract = versioned_file_assets(
            core_version,
            tuple(
                (adapter_id, installed_versions[adapter_id])
                for adapter_id in requested
                if adapter_id in installed
            ),
        )
        checked_paths = {relative for relative, _, _, _ in checked_contract}
        for relative in sorted(checked_paths):
            target = repo / relative
            reason = managed_path_conflict(repo, target, "file")
            if reason:
                errors.append(
                    f"HARNESS_REQUIRED_FILE_INVALID: {relative}: {reason}"
                )
            elif not target.is_file():
                errors.append(f"HARNESS_REQUIRED_FILE_MISSING: {relative}")
            elif BOOTSTRAP_TODO_MARKER in target.read_text(encoding="utf-8"):
                count = target.read_text(encoding="utf-8").count(
                    BOOTSTRAP_TODO_MARKER
                )
                warnings.append(
                    f"HARNESS_BOOTSTRAP_TODO: {relative}: {count} "
                    "bootstrap TODO marker(s) remain"
                )
            if relative not in records:
                errors.append(
                    f"HARNESS_FILE_UNREGISTERED: {relative}: missing manifest record"
                )
        engine_errors, engine_warnings = validate_activation_engine(
            repo,
            core_version,
        )
        errors.extend(engine_errors)
        warnings.extend(engine_warnings)
        for adapter_id in requested:
            if adapter_id not in installed:
                continue
            adapter_errors, adapter_warnings = validate_adapter(
                repo,
                adapter_id,
                installed_versions[adapter_id],
            )
            errors.extend(adapter_errors)
            warnings.extend(adapter_warnings)
        instruction_files = manifest["instruction_files"]
        assert isinstance(instruction_files, list)
        checked_instruction_paths = checked_paths
        for item in instruction_files:
            assert isinstance(item, dict)
            relative = str(item["path"])
            if relative not in checked_instruction_paths:
                continue
            target = repo / relative
            if not target.is_file() or target.is_symlink():
                continue
            actual = physical_line_count(target)
            maximum = int(item["max_lines"])
            if actual > maximum:
                code = (
                    "HARNESS_AGENTS_LINE_LIMIT"
                    if relative == "AGENTS.md"
                    else "HARNESS_INSTRUCTION_LINE_LIMIT"
                )
                errors.append(
                    f"{code}: {relative}: actual "
                    f"{actual} physical lines; required <= {maximum}"
                )
            elif relative == "AGENTS.md" and actual > CODEX_AGENT_TEMPLATE_TARGET_LINES:
                warnings.append(
                    f"HARNESS_AGENTS_LINE_BUDGET: {relative}: actual {actual}; "
                    f"hard limit is {maximum}"
                )

    try:
        epctl = load_execution_plan_ctl()
        roots = epctl.load_config(repo)["architecture_roots"]
        if not isinstance(roots, list):
            raise FoundryctlError("architecture_roots is not a list")
    except Exception as exc:
        errors.append(f"HARNESS_ARCHITECTURE_ROOT_INVALID: {exc}")
    else:
        if "docs/design-docs" not in roots:
            errors.append(
                "HARNESS_ARCHITECTURE_ROOT_MISSING: docs/design-docs"
            )
    try:
        designctl = load_design_ctl()
        epctl = load_execution_plan_ctl()
        logical_adr_data = epctl.adr_corpus_data(repo)
        design_errors, design_warnings = designctl.validate_repo(
            repo,
            logical_adr_data=logical_adr_data,
        )
    except Exception as exc:
        errors.append(f"HARNESS_DESIGN_CONTRACT_INVALID: {exc}")
    else:
        errors.extend(
            f"HARNESS_DESIGN_CONTRACT_INVALID: {item}"
            for item in design_errors
        )
        warnings.extend(
            f"HARNESS_DESIGN_CONTRACT_WARNING: {item}"
            for item in design_warnings
        )
    spec_errors, spec_warnings = specctl.validate_spec_state(
        repo,
        require_manifest=False,
    )
    errors.extend(spec_errors)
    warnings.extend(spec_warnings)
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def validate_codex_harness(
    repo: Path,
    *,
    require_manifest: bool,
) -> tuple[list[str], list[str]]:
    """Compatibility alias for callers of the v0.1 API."""
    return validate_harness(repo, require_manifest=require_manifest)


def _bootstrap_file_conflict(
    repo: Path,
    relative: str,
    asset: str,
    owner_kind: str,
    owner_id: str | None,
) -> tuple[str, str | None]:
    target = repo / relative
    reason = managed_path_conflict(repo, target, "file")
    if reason:
        return reason, None
    if not target.is_file():
        return "", None
    warning: str | None = None
    if relative == "AGENTS.md":
        lines = physical_line_count(target)
        if lines > CODEX_AGENT_MAX_LINES:
            return (
                f"HARNESS_AGENTS_LINE_LIMIT: actual {lines} physical lines; "
                f"required <= {CODEX_AGENT_MAX_LINES}",
                None,
            )
        if lines > CODEX_AGENT_TEMPLATE_TARGET_LINES:
            warning = (
                f"HARNESS_AGENTS_LINE_BUDGET: AGENTS.md: actual {lines} "
                f"physical lines; hard limit is {CODEX_AGENT_MAX_LINES}"
            )
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return f"HARNESS_CODEX_ROUTE_INVALID: {exc}", warning
        missing = [route for route in CODEX_ROUTER_AGENTS_ROUTES if route not in text]
        if missing:
            return (
                "HARNESS_CODEX_ROUTE_MISSING: " + ", ".join(missing),
                warning,
            )
        return "", warning
    if relative == CODEX_HOOKS_FILE:
        hook_errors = validate_hook_config_file(repo)
        return (
            (
                "; ".join(hook_errors)
                + "; preserve existing Hooks and merge the RepoFoundry "
                "groups explicitly"
            )
            if hook_errors
            else ""
        ), warning
    if relative in _generated_for_owner(owner_kind, owner_id):
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return str(exc), warning
        if current != asset_text(asset):
            return (
                "generated adapter/Core bytes differ from this RepoFoundry "
                "release; merge explicitly",
                warning,
            )
    return "", warning


def bootstrap_plan(
    repo: Path,
    adapter_ids: tuple[str, ...],
    initial_spec_source: dict[str, str],
    requested_spec_ids: tuple[str, ...] | None,
    *,
    governance_profile: str | None = None,
    compatibility_warnings: tuple[str, ...] = (),
) -> dict[str, object]:
    requested = normalize_adapter_ids(list(adapter_ids))
    epctl = load_execution_plan_ctl()
    ep_directories, ep_files = execution_plan_contract(epctl)
    designctl = load_design_ctl()
    design_directories, design_files = design_contract(designctl)
    actions: list[dict[str, object]] = []
    warnings = list(compatibility_warnings)
    existing_manifest: dict[str, object] | None = None
    manifest_path = harness_path(repo)
    if manifest_path.exists():
        try:
            existing_manifest = load_harness_manifest(repo)
        except FoundryctlError as exc:
            actions.append(
                {
                    "action": "conflict",
                    "path": HARNESS_MANIFEST,
                    "reason": str(exc),
                }
            )
        else:
            warnings.extend(harness_manifest_warnings(existing_manifest))
    if existing_manifest is not None and harness_schema_version(existing_manifest) < HARNESS_SCHEMA_VERSION:
        if requested != ("codex",):
            actions.append(
                {
                    "action": "conflict",
                    "path": HARNESS_MANIFEST,
                    "reason": (
                        "HARNESS_UPGRADE_REQUIRED: migrate schema "
                        f"{harness_schema_version(existing_manifest)} before "
                        "adding adapters"
                    ),
                }
            )
        desired = ("codex",)
    elif existing_manifest is not None:
        desired = normalize_adapter_ids(
            list(
                dict.fromkeys(
                    (*_manifest_adapter_ids(existing_manifest), *requested)
                )
            )
        )
    else:
        desired = requested
    effective_governance_profile = normalize_governance_profile(
        governance_profile
        or (
            harness_governance_profile(existing_manifest)
            if existing_manifest is not None
            else DEFAULT_GOVERNANCE_PROFILE
        )
    )

    directories = [*ep_directories, *design_directories]
    directories.extend(CORE_BOOTSTRAP_DIRECTORIES)
    for adapter_id in desired:
        directories.extend(ADAPTER_DIRECTORIES[adapter_id])
    for relative in dict.fromkeys(directories):
        path = repo / relative
        reason = managed_path_conflict(repo, path, "directory")
        if reason:
            actions.append({"action": "conflict", "path": relative, "reason": reason})
        elif path.is_dir():
            actions.append({"action": "preserve", "path": relative + "/"})
        else:
            actions.append({"action": "create_directory", "path": relative + "/"})

    expected_assets = selected_file_assets(desired)
    professional_files = {*ep_files, *design_files}
    for relative in (*ep_files, *design_files, *(item[0] for item in expected_assets)):
        path = repo / relative
        if relative in professional_files:
            reason = managed_path_conflict(repo, path, "file")
            warning = None
        else:
            asset, owner_kind, owner_id = _asset_contract(desired)[relative]
            reason, warning = _bootstrap_file_conflict(
                repo,
                relative,
                asset,
                owner_kind,
                owner_id,
            )
        if warning:
            warnings.append(warning)
        if reason:
            actions.append({"action": "conflict", "path": relative, "reason": reason})
        elif path.is_file():
            actions.append({"action": "preserve", "path": relative})
        else:
            actions.append({"action": "create_file", "path": relative})

    candidate_manifest: dict[str, object] | None = None
    if existing_manifest is None:
        candidate_manifest = harness_manifest(
            repo,
            desired,
            governance_profile=effective_governance_profile,
        )
        actions.append({"action": "create_file", "path": HARNESS_MANIFEST})
    elif harness_schema_version(existing_manifest) == HARNESS_SCHEMA_VERSION:
        old_records = {
            str(item["path"]): item
            for item in existing_manifest["files"]
            if isinstance(item, dict)
        }
        candidate_manifest = harness_manifest(
            repo,
            desired,
            governance_profile=effective_governance_profile,
            applied_migrations=list(existing_manifest["applied_migrations"]),
            existing_records=old_records,
        )
        previous_governance_profile = harness_governance_profile(existing_manifest)
        if effective_governance_profile != previous_governance_profile:
            append_migration(
                candidate_manifest,
                migration_record(
                    (
                        "governance-"
                        f"{previous_governance_profile}-to-"
                        f"{effective_governance_profile}"
                    ),
                    "governance",
                    previous_governance_profile,
                    effective_governance_profile,
                ),
            )
        append_component_migrations(candidate_manifest, existing_manifest)
        if candidate_manifest == existing_manifest:
            actions.append({"action": "preserve", "path": HARNESS_MANIFEST})
        else:
            actions.append(
                {
                    "action": "update_manifest",
                    "path": HARNESS_MANIFEST,
                    "reason": "register selected adapters",
                }
            )
    elif not any(
        item.get("path") == HARNESS_MANIFEST
        for item in actions
        if isinstance(item, dict)
    ):
        actions.append({"action": "preserve", "path": HARNESS_MANIFEST})

    config = epctl.config_path(repo)
    reason = managed_path_conflict(repo, config, "file")
    roots: list[str] = []
    if not reason:
        try:
            roots = [str(item) for item in epctl.load_config(repo)["architecture_roots"]]
        except Exception as exc:
            reason = str(exc)
    if reason:
        actions.append(
            {
                "action": "conflict",
                "path": config.relative_to(repo).as_posix(),
                "reason": reason,
            }
        )
    elif "docs/design-docs" in roots:
        actions.append({"action": "preserve", "path": config.relative_to(repo).as_posix()})
    else:
        actions.append({"action": "register", "path": "docs/design-docs"})

    selected_specs: list[str] = []
    configured_specs: list[str] = []
    required_specs: list[str] = []
    recommended_specs: list[str] = []
    available_specs: list[dict[str, object]] = []
    try:
        spec_plan = specctl.plan_spec_state(
            repo,
            initial_spec_source,
            operation="sync",
            allow_replace=False,
            requested_spec_ids=requested_spec_ids,
        )
    except specctl.SpecError as exc:
        actions.append(
            {"action": "conflict", "path": specctl.SPEC_MANIFEST, "reason": str(exc)}
        )
    else:
        actions.extend(spec_plan.actions)
        warnings.extend(spec_plan.warnings)
        selected_specs.extend(spec_plan.selected_spec_ids)
        spec_payload = specctl.plan_payload(spec_plan, mode="dry-run")
        configured_specs.extend(spec_payload["configured_specs"])
        required_specs.extend(spec_payload["required_specs"])
        recommended_specs.extend(spec_payload["recommended_specs"])
        available_specs.extend(spec_payload["available_specs"])
    return {
        "adapters": list(desired),
        "profile": "codex" if desired == ("codex",) else None,
        "governance_profile": effective_governance_profile,
        "components": list(PROFESSIONAL_COMPONENTS),
        "specs": selected_specs,
        "configured_specs": configured_specs,
        "required_specs": required_specs,
        "recommended_specs": recommended_specs,
        "available_specs": available_specs,
        "actions": actions,
        "warnings": list(dict.fromkeys(warnings)),
        "candidate_manifest": candidate_manifest,
    }


def bootstrap_repo(
    repo: Path,
    adapter_ids: tuple[str, ...],
    *,
    apply_changes: bool,
    initial_spec_source: dict[str, str],
    requested_spec_ids: tuple[str, ...] | None,
    governance_profile: str | None = None,
    compatibility_warnings: tuple[str, ...] = (),
) -> dict[str, object]:
    planned = bootstrap_plan(
        repo,
        adapter_ids,
        initial_spec_source,
        requested_spec_ids,
        governance_profile=governance_profile,
        compatibility_warnings=compatibility_warnings,
    )
    actions = planned["actions"]
    assert isinstance(actions, list)
    conflicts = [
        item for item in actions
        if isinstance(item, dict) and item.get("action") == "conflict"
    ]
    payload = {
        key: value
        for key, value in planned.items()
        if key != "candidate_manifest"
    }
    payload.update(
        {
            "mode": "apply" if apply_changes else "dry-run",
            "created": [],
            "updated": [],
        }
    )
    if not apply_changes:
        return payload
    if conflicts:
        details = "; ".join(
            f"{item.get('path')}: {item.get('reason')}" for item in conflicts
        )
        raise FoundryctlError(f"Bootstrap preflight failed: {details}")
    candidate = planned["candidate_manifest"]
    if candidate is None:
        raise FoundryctlError(
            "HARNESS_UPGRADE_REQUIRED: run the explicit Harness upgrade first"
        )
    assert isinstance(candidate, dict)
    desired = tuple(str(item) for item in planned["adapters"])
    epctl = load_execution_plan_ctl()
    designctl = load_design_ctl()
    created: list[str] = []
    updated: list[str] = []
    design_bootstrap_warnings: list[str] = []
    with repo_lock(repo):
        locked = bootstrap_plan(
            repo,
            adapter_ids,
            initial_spec_source,
            requested_spec_ids,
            governance_profile=governance_profile,
            compatibility_warnings=compatibility_warnings,
        )
        locked_actions = locked["actions"]
        assert isinstance(locked_actions, list)
        locked_conflicts = [
            item
            for item in locked_actions
            if isinstance(item, dict) and item.get("action") == "conflict"
        ]
        if locked_conflicts or locked["candidate_manifest"] != candidate:
            raise FoundryctlError(
                "Bootstrap preflight changed while acquiring the lock; "
                + "; ".join(
                    f"{item.get('path')}: {item.get('reason')}"
                    for item in locked_conflicts
                )
            )
        locked_spec_plan = specctl.plan_spec_state(
            repo,
            initial_spec_source,
            operation="sync",
            allow_replace=False,
            requested_spec_ids=requested_spec_ids,
        )
        ep_directories, ep_files = execution_plan_contract(epctl)
        design_directories, design_files = design_contract(designctl)
        managed_directories = [
            *ep_directories,
            *design_directories,
            *CORE_BOOTSTRAP_DIRECTORIES,
        ]
        for adapter_id in desired:
            managed_directories.extend(ADAPTER_DIRECTORIES[adapter_id])
        touched_relatives = {*ep_files, *design_files}
        touched_relatives.update(
            relative
            for relative, _, _, _ in selected_file_assets(desired)
        )
        touched_relatives.add(HARNESS_MANIFEST)
        touched_relatives.update(item.path for item in locked_spec_plan.writes)
        touched_relatives.update(item.path for item in locked_spec_plan.deletes)
        touched_paths = {repo / relative for relative in touched_relatives}
        originals: dict[Path, str | None] = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in touched_paths
        }
        missing_directories = {
            repo / relative
            for relative in managed_directories
            if not (repo / relative).exists()
        }
        missing_directories.update(
            parent
            for path in touched_paths
            for parent in path.parents
            if parent != repo and repo in parent.parents and not parent.exists()
        )
        try:
            with epctl.repo_lock(repo):
                created.extend(epctl.init_repo(repo))
                with designctl.repo_lock(repo):
                    created.extend(designctl.init_repo(repo))
                directories = list(CORE_BOOTSTRAP_DIRECTORIES)
                for adapter_id in desired:
                    directories.extend(ADAPTER_DIRECTORIES[adapter_id])
                for relative in dict.fromkeys(directories):
                    directory = repo / relative
                    reject_symlink_path(repo, directory)
                    if not directory.exists():
                        directory.mkdir(parents=True)
                        created.append(relative + "/")
                for relative, asset, _, _ in selected_file_assets(desired):
                    target = repo / relative
                    reject_symlink_path(repo, target)
                    if ensure_file(target, asset):
                        created.append(relative)
                manifest = harness_path(repo)
                previous_manifest = (
                    manifest.read_text(encoding="utf-8") if manifest.exists() else None
                )
                rendered = json.dumps(
                    candidate,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + "\n"
                if previous_manifest != rendered:
                    atomic_write(manifest, rendered)
                    (updated if previous_manifest is not None else created).append(
                        HARNESS_MANIFEST
                    )
                config = epctl.config_path(repo)
                config_existed = config.exists()
                loaded_config = epctl.load_config(repo)
                roots = loaded_config["architecture_roots"]
                if "docs/design-docs" not in roots:
                    roots.append("docs/design-docs")
                    epctl.save_config(repo, loaded_config)
                    (updated if config_existed else created).append(
                        config.relative_to(repo).as_posix()
                    )
                with designctl.repo_lock(repo):
                    reindex_warnings = designctl.reindex(repo)
                    if isinstance(reindex_warnings, list):
                        design_bootstrap_warnings.extend(
                            str(item) for item in reindex_warnings
                        )
                spec_created, spec_updated, spec_removed = specctl.apply_spec_plan(
                    repo,
                    locked_spec_plan,
                )
                if spec_removed:
                    raise FoundryctlError("Bootstrap unexpectedly planned Spec removals")
                created.extend(spec_created)
                updated.extend(spec_updated)
            harness_errors, harness_warnings = validate_harness(
                repo,
                require_manifest=True,
            )
            if harness_errors:
                raise FoundryctlError(
                    "Bootstrap Harness validation failed: "
                    + "; ".join(harness_errors)
                )
        except Exception as exc:
            rollback_errors: list[str] = []
            for path, content in originals.items():
                try:
                    if content is None:
                        if path.exists():
                            path.unlink()
                    else:
                        atomic_write(path, content)
                except Exception as rollback_exc:  # pragma: no cover
                    rollback_errors.append(f"{path}: {rollback_exc}")
            for directory in sorted(
                missing_directories,
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                raise FoundryctlError(
                    f"{exc}; rollback also failed: "
                    + "; ".join(rollback_errors)
                ) from exc
            if isinstance(exc, specctl.SpecError):
                raise FoundryctlError(str(exc)) from exc
            if isinstance(exc, FoundryctlError):
                raise
            raise FoundryctlError(f"Bootstrap initialization failed: {exc}") from exc
    payload["warnings"] = list(
        dict.fromkeys(
            [
                *list(planned["warnings"]),
                *design_bootstrap_warnings,
                *harness_warnings,
            ]
        )
    )
    payload["created"] = list(dict.fromkeys(created))
    payload["updated"] = list(dict.fromkeys(updated))
    return payload


def add_spec_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--spec-repository",
        help=(
            "Initial Git specification repository when specs.json is absent "
            f"(default: {DEFAULT_SPEC_REPOSITORY})"
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--spec-version",
        help=(
            "Released Catalog version MAJOR.MINOR.PATCH; normalized to "
            "refs/tags/vMAJOR.MINOR.PATCH "
            f"(initial default: {DEFAULT_SPEC_VERSION})"
        ),
    )
    source.add_argument(
        "--spec-ref",
        help=(
            "Explicit development Git branch, tag, or commit; production "
            "use should select --spec-version"
        ),
    )


def add_spec_selection_arguments(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--spec",
        dest="spec_ids",
        action="append",
        metavar="ID",
        help=(
            "Select an optional Specification by stable ID; repeat to set "
            "the complete desired optional direct selection"
        ),
    )
    selection.add_argument(
        "--required-only",
        action="store_true",
        help="Select no optional Specifications; required Specs remain",
    )
    selection.add_argument(
        "--keep-selection",
        action="store_true",
        help=(
            "Explicitly acknowledge Catalog candidates and preserve the "
            "current direct Spec selection"
        ),
    )


def requested_spec_ids(args: argparse.Namespace) -> tuple[str, ...] | None:
    if getattr(args, "required_only", False):
        return ()
    values = getattr(args, "spec_ids", None)
    return tuple(values) if values is not None else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version=f"RepoFoundry AI {REPO_FOUNDRY_VERSION}",
    )
    parser.add_argument("--repo", default=".", help="Target repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser(
        "bootstrap",
        help="Preview or create an Agent-first project documentation Harness",
    )
    bootstrap.add_argument(
        "--profile",
        choices=(CODEX_HARNESS_PROFILE,),
        help="Deprecated compatibility alias for --adapter codex",
    )
    bootstrap.add_argument(
        "--adapter",
        dest="adapter_ids",
        action="append",
        choices=ADAPTER_ORDER,
        help="Install an Agent adapter; repeat to install multiple adapters",
    )
    bootstrap.add_argument(
        "--all-adapters",
        action="store_true",
        help="Install every bundled adapter in deterministic registry order",
    )
    bootstrap.add_argument(
        "--governance-profile",
        choices=GOVERNANCE_PROFILES,
        help=(
            "Select adaptive or strict governance; fresh Harnesses default "
            "to adaptive, while existing Harnesses preserve their profile "
            "unless this option is explicit"
        ),
    )
    add_spec_source_arguments(bootstrap)
    add_spec_selection_arguments(bootstrap)
    bootstrap_mode = bootstrap.add_mutually_exclusive_group()
    bootstrap_mode.add_argument(
        "--apply",
        action="store_true",
        help="Create only missing paths after a conflict-free preflight",
    )
    bootstrap_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing; this is the default",
    )

    validate_parser = sub.add_parser(
        "validate",
        help="Validate the RepoFoundry AI project Harness",
    )
    validate_parser.add_argument(
        "--harness",
        action="store_true",
        help="Require a bootstrapped Harness manifest",
    )
    validate_parser.add_argument(
        "--adapter",
        dest="adapter_ids",
        action="append",
        choices=ADAPTER_ORDER,
        help="Validate only this adapter plus the shared Core; repeatable",
    )

    adapter_parser = sub.add_parser(
        "adapter",
        help="Inspect available Agent adapters and their capabilities",
    )
    adapter_commands = adapter_parser.add_subparsers(
        dest="adapter_command",
        required=True,
    )
    adapter_commands.add_parser(
        "list",
        help="List bundled adapters, versions, enforcement, and capabilities",
    )

    upgrade_parser = sub.add_parser(
        "upgrade",
        help="Preview or apply a versioned Harness migration",
    )
    upgrade_parser.add_argument(
        "--to",
        required=True,
        metavar="VERSION",
        help=(
            "Target RepoFoundry release bundled with this installation "
            f"(available: {REPO_FOUNDRY_VERSION})"
        ),
    )
    upgrade_parser.add_argument(
        "--governance-profile",
        choices=GOVERNANCE_PROFILES,
        help=(
            "Explicitly migrate the Harness governance profile; omitted "
            "preserves the existing effective profile"
        ),
    )
    upgrade_mode = upgrade_parser.add_mutually_exclusive_group()
    upgrade_mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the conflict-free migration after a locked recheck",
    )
    upgrade_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing; this is the default",
    )

    spec_parser = sub.add_parser(
        "spec",
        help="Plan, synchronize, update, or validate Engineering Specs",
    )
    spec_commands = spec_parser.add_subparsers(
        dest="spec_command",
        required=True,
    )
    plan_parser = spec_commands.add_parser(
        "plan",
        help="Preview the current or inferred Spec selection",
    )
    add_spec_source_arguments(plan_parser)
    for command, help_text in (
        ("sync", "Materialize the explicit Spec selection"),
        (
            "update",
            "Replace explicit selection or refresh selected Specs",
        ),
    ):
        command_parser = spec_commands.add_parser(command, help=help_text)
        add_spec_source_arguments(command_parser)
        if command == "update":
            add_spec_selection_arguments(command_parser)
        command_mode = command_parser.add_mutually_exclusive_group()
        command_mode.add_argument(
            "--apply",
            action="store_true",
            help="Apply the conflict-free preview",
        )
        command_mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview actions without writing; this is the default",
        )
    spec_commands.add_parser(
        "validate",
        help="Validate the Spec manifest, lock, local content, and routing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = normalize_repo(args.repo)
        if args.command == "bootstrap":
            if args.all_adapters and (
                args.profile is not None or args.adapter_ids is not None
            ):
                raise FoundryctlError(
                    "HARNESS_ADAPTER_SELECTION_CONFLICT: --all-adapters "
                    "cannot be combined with --profile or --adapter"
                )
            if args.profile is not None and args.adapter_ids is not None:
                raise FoundryctlError(
                    "HARNESS_ADAPTER_SELECTION_CONFLICT: --profile cannot be "
                    "combined with --adapter"
                )
            compatibility_warnings: tuple[str, ...] = ()
            if args.all_adapters:
                adapters = ADAPTER_ORDER
            elif args.profile is not None:
                adapters = ("codex",)
                compatibility_warnings = (
                    "HARNESS_PROFILE_ALIAS_DEPRECATED: --profile codex maps "
                    "to --adapter codex for this compatibility release",
                )
            elif args.adapter_ids is None:
                adapters = ("codex",)
                compatibility_warnings = (
                    "HARNESS_ADAPTER_DEFAULT_DEPRECATED: omitted adapter "
                    "selection currently defaults to codex; pass --adapter "
                    "codex explicitly",
                )
            else:
                adapters = normalize_adapter_ids(args.adapter_ids)
            selection = requested_spec_ids(args)
            source_override = any(
                value is not None
                for value in (
                    args.spec_repository,
                    args.spec_version,
                    args.spec_ref,
                )
            )
            if (
                (repo / specctl.SPEC_MANIFEST).exists()
                and (source_override or selection is not None)
            ):
                raise FoundryctlError(
                    "SPEC_BOOTSTRAP_OVERRIDE_REQUIRES_UPDATE: specs.json "
                    "already exists; use spec update to change source or "
                    "selection"
                )
            initial_source = spec_source(
                selected_spec_repository(
                    repo,
                    args.spec_repository,
                    preserve_manifest_source=False,
                ),
                version=args.spec_version,
                ref=args.spec_ref,
            )
            if initial_source is None:  # pragma: no cover - default enabled
                raise FoundryctlError("Initial Spec source is missing")
            print(
                json.dumps(
                    bootstrap_repo(
                        repo,
                        adapters,
                        apply_changes=args.apply,
                        initial_spec_source=initial_source,
                        requested_spec_ids=selection,
                        governance_profile=args.governance_profile,
                        compatibility_warnings=compatibility_warnings,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "validate":
            adapters = (
                normalize_adapter_ids(args.adapter_ids)
                if args.adapter_ids is not None
                else None
            )
            errors, warnings = validate_harness(
                repo,
                require_manifest=bool(args.harness or adapters is not None),
                adapter_ids=adapters,
            )
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            print(
                json.dumps(
                    {"errors": len(errors), "warnings": len(warnings)},
                    ensure_ascii=False,
                )
            )
            return 1 if errors else 0
        elif args.command == "adapter":
            if args.adapter_command == "list":
                print(
                    json.dumps(
                        adapter_list_payload(),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:  # pragma: no cover - argparse guarantees a command
                raise FoundryctlError(
                    f"Unknown adapter command: {args.adapter_command}"
                )
        elif args.command == "upgrade":
            print(
                json.dumps(
                    upgrade_harness(
                        repo,
                        args.to,
                        apply_changes=args.apply,
                        governance_profile=args.governance_profile,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "spec":
            if args.spec_command == "validate":
                errors, warnings = specctl.validate_spec_state(
                    repo,
                    require_manifest=True,
                )
                if harness_path(repo).exists():
                    manifest = load_harness_manifest(repo)
                    if harness_schema_version(manifest) == HARNESS_SCHEMA_VERSION:
                        core = manifest["core"]
                        assert isinstance(core, dict)
                        engine_errors, engine_warnings = validate_activation_engine(
                            repo,
                            str(core["version"]),
                        )
                        errors.extend(engine_errors)
                        warnings.extend(engine_warnings)
                for warning in warnings:
                    print(f"WARNING: {warning}", file=sys.stderr)
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                print(
                    json.dumps(
                        {"errors": len(errors), "warnings": len(warnings)},
                        ensure_ascii=False,
                    )
                )
                return 1 if errors else 0
            operation = (
                "plan"
                if args.spec_command == "plan"
                else args.spec_command
            )
            selection = (
                requested_spec_ids(args)
                if operation == "update"
                else None
            )
            manifest_exists = (repo / specctl.SPEC_MANIFEST).exists()
            source_override = any(
                value is not None
                for value in (
                    args.spec_repository,
                    args.spec_version,
                    args.spec_ref,
                )
            )
            if (
                manifest_exists
                and operation != "update"
                and source_override
            ):
                raise FoundryctlError(
                    "SPEC_SOURCE_OVERRIDE_REQUIRES_UPDATE: specs.json "
                    "already exists; preview spec update instead"
                )
            if (
                operation == "update"
                and manifest_exists
                and args.spec_repository is not None
                and args.spec_version is None
                and args.spec_ref is None
            ):
                raise FoundryctlError(
                    "SPEC_SOURCE_SELECTOR_REQUIRED: --spec-repository on an "
                    "existing project requires --spec-version or --spec-ref"
                )
            apply_changes = bool(
                args.spec_command != "plan" and args.apply
            )
            initial_repository = selected_spec_repository(
                repo,
                args.spec_repository,
                preserve_manifest_source=False,
            )
            initial_source = spec_source(
                initial_repository,
                version=args.spec_version,
                ref=args.spec_ref,
            )
            if initial_source is None:  # pragma: no cover - default enabled
                raise FoundryctlError("Initial Spec source is missing")
            update_source = (
                spec_source(
                    selected_spec_repository(
                        repo,
                        args.spec_repository,
                        preserve_manifest_source=True,
                    ),
                    version=args.spec_version,
                    ref=args.spec_ref,
                    use_default_version=False,
                )
                if operation == "update"
                else None
            )
            print(
                json.dumps(
                    manage_specs(
                        repo,
                        operation,
                        apply_changes=apply_changes,
                        initial_spec_source=initial_source,
                        update_spec_source=update_source,
                        requested_spec_ids=selection,
                        keep_selection=bool(
                            getattr(args, "keep_selection", False)
                        ),
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:  # pragma: no cover - argparse guarantees a command
            raise FoundryctlError(f"Unknown command: {args.command}")
    except FoundryctlError as exc:
        print(f"foundryctl: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
