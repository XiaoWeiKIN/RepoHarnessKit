#!/usr/bin/env python3
"""Install or upgrade RepoFoundry AI from one deterministic entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is rejected by this release
    fcntl = None


PRODUCT_ID = "repo-foundry-ai"
PRODUCT_NAME = "RepoFoundry AI"
DEFAULT_REPOSITORY = "XiaoWeiKIN/RepoHarnessKit"
INSTALL_SCHEMA_VERSION = 1
MINIMUM_PYTHON = (3, 10)
MAX_JSON_BYTES = 1 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MANAGED_LAUNCHER_MARKER = "# Managed by RepoFoundry AI installer"
EXCLUDED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}


class InstallError(RuntimeError):
    """Raised when installation cannot complete without risking local state."""


@dataclass(frozen=True)
class PackageSource:
    root: Path
    version: str
    provenance: dict[str, str]


@dataclass(frozen=True)
class PathSnapshot:
    kind: str
    content: bytes | None = None
    mode: int | None = None
    link_target: str | None = None


class ActivationTransaction:
    """Capture small managed paths and recover moved user-owned paths."""

    def __init__(self) -> None:
        self.snapshots: list[tuple[Path, PathSnapshot]] = []
        self.moved: list[tuple[Path, Path]] = []
        self.committed = False

    def snapshot(self, path: Path) -> None:
        if path.is_symlink():
            value = PathSnapshot("symlink", link_target=os.readlink(path))
        elif not path.exists():
            value = PathSnapshot("absent")
        elif path.is_file():
            value = PathSnapshot(
                "file",
                content=path.read_bytes(),
                mode=stat.S_IMODE(path.stat().st_mode),
            )
        else:
            raise InstallError(
                f"cannot snapshot non-file managed path without a backup: {path}"
            )
        self.snapshots.append((path, value))

    def move_to_backup(self, path: Path, backup: Path) -> None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup))
        self.moved.append((path, backup))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        if self.committed:
            return
        for path, snapshot in reversed(self.snapshots):
            remove_generated_path(path)
            if snapshot.kind == "file":
                assert snapshot.content is not None
                atomic_write(path, snapshot.content, snapshot.mode or 0o644)
            elif snapshot.kind == "symlink":
                assert snapshot.link_target is not None
                atomic_symlink(path, snapshot.link_target)
        for original, backup in reversed(self.moved):
            remove_generated_path(original)
            if backup.exists() or backup.is_symlink():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(original))


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def semver_tuple(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise InstallError(
            f"version must use exact MAJOR.MINOR.PATCH syntax: {value!r}"
        )
    return tuple(int(item) for item in match.groups())  # type: ignore[return-value]


def normalize_repository(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise InstallError(
            "repository must use the exact OWNER/NAME form without a URL"
        )
    return value


def default_prefix() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "repofoundry-ai"


def default_bin_dir() -> Path:
    bin_home = os.environ.get("XDG_BIN_HOME")
    return Path(bin_home).expanduser() if bin_home else Path.home() / ".local" / "bin"


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def default_claude_home() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def normalized_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_install_locations(
    prefix: Path,
    bin_dir: Path,
    source: Path | None,
) -> None:
    filesystem_root = Path(prefix.anchor)
    if prefix in (filesystem_root, normalized_path(Path.home())):
        raise InstallError("install prefix cannot be a filesystem or home root")
    if prefix.is_symlink():
        raise InstallError(f"install prefix cannot be a symbolic link: {prefix}")
    if source is None:
        return
    source = normalized_path(source)
    if path_is_within(prefix, source):
        raise InstallError("install prefix cannot be inside the local source tree")
    if path_is_within(bin_dir, source):
        raise InstallError("bin directory cannot be inside the local source tree")


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RepoFoundryAI-Installer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def read_response(response: Any, maximum: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = response.read(min(1024 * 1024, maximum + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise InstallError(
                f"remote response exceeds the {maximum}-byte safety limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def curl_config_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise InstallError("HTTP configuration cannot contain line breaks")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def curl_url(url: str, maximum: int) -> bytes:
    lines = [
        "fail",
        "silent",
        "show-error",
        "location",
        'proto = "=https"',
        "connect-timeout = 10",
        "max-time = 30",
        f"max-filesize = {maximum}",
    ]
    for name, value in github_headers().items():
        header = curl_config_value(f"{name}: {value}")
        lines.append(f'header = "{header}"')
    lines.append(f'url = "{curl_config_value(url)}"')
    configuration = ("\n".join(lines) + "\n").encode("utf-8")
    process = subprocess.Popen(
        ["curl", "--config", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        process.stdin.write(configuration)
        process.stdin.close()
        payload = read_response(process.stdout, maximum)
        stderr = read_response(process.stderr, MAX_JSON_BYTES)
        return_code = process.wait(timeout=35)
    except Exception:
        process.kill()
        process.wait()
        raise
    if return_code:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise InstallError(
            f"GitHub request failed through curl with exit {return_code}: "
            f"{detail or url}"
        )
    return payload


def open_url(url: str, maximum: int) -> bytes:
    if shutil.which("curl"):
        return curl_url(url, maximum)
    request = urllib.request.Request(url, headers=github_headers())
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return read_response(response, maximum)
    except urllib.error.HTTPError as exc:
        raise InstallError(
            f"GitHub request failed with HTTP {exc.code}: {url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise InstallError(f"GitHub request failed: {exc.reason}") from exc


def github_json(repository: str, endpoint: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/{endpoint}"
    payload = open_url(url, MAX_JSON_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"GitHub returned invalid JSON for {endpoint}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"GitHub returned a non-object for {endpoint}")
    return value


def release_tag(repository: str, requested: str) -> str:
    if requested == "latest":
        release = github_json(repository, "releases/latest")
    else:
        semver_tuple(requested)
        encoded = urllib.parse.quote(f"v{requested}", safe="")
        release = github_json(repository, f"releases/tags/{encoded}")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise InstallError("GitHub release does not declare a valid version tag")
    semver_tuple(tag[1:])
    if release.get("draft") is True or release.get("prerelease") is True:
        raise InstallError(f"release {tag} is not a stable published release")
    if requested != "latest" and tag != f"v{requested}":
        raise InstallError(
            f"GitHub returned release {tag!r} for requested version {requested!r}"
        )
    return tag


def resolve_tag_commit(repository: str, tag: str) -> str:
    encoded = urllib.parse.quote(tag, safe="")
    reference = github_json(repository, f"git/ref/tags/{encoded}")
    current = reference.get("object")
    for _ in range(8):
        if not isinstance(current, dict):
            break
        object_type = current.get("type")
        sha = current.get("sha")
        if not isinstance(sha, str) or not COMMIT_RE.fullmatch(sha):
            break
        if object_type == "commit":
            return sha
        if object_type != "tag":
            break
        current = github_json(repository, f"git/tags/{sha}").get("object")
    raise InstallError(f"release tag {tag} does not resolve to a Git commit")


def download_archive(repository: str, commit: str, destination: Path) -> str:
    if not COMMIT_RE.fullmatch(commit):
        raise InstallError("archive download requires a full Git commit SHA")
    url = f"https://api.github.com/repos/{repository}/tarball/{commit}"
    payload = open_url(url, MAX_ARCHIVE_BYTES)
    digest = hashlib.sha256(payload).hexdigest()
    destination.write_bytes(payload)
    return digest


def safe_member_parts(name: str) -> tuple[str, ...]:
    if "\\" in name:
        raise InstallError(f"archive contains an unsafe path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts:
        raise InstallError(f"archive contains an unsafe path: {name!r}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if not parts or ".." in parts or parts[0].endswith(":"):
        raise InstallError(f"archive contains an unsafe path: {name!r}")
    return parts


def extract_archive(archive: Path, destination: Path) -> Path:
    try:
        package = tarfile.open(archive, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise InstallError("downloaded release is not a valid gzip tar archive") from exc
    with package:
        members = package.getmembers()
        if not members:
            raise InstallError("downloaded release archive is empty")
        extracted_size = sum(member.size for member in members if member.isfile())
        if extracted_size > MAX_EXTRACTED_BYTES:
            raise InstallError(
                "release archive expands beyond the "
                f"{MAX_EXTRACTED_BYTES}-byte safety limit"
            )
        for member in members:
            parts = safe_member_parts(member.name)
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            if not member.isfile():
                raise InstallError(
                    f"archive member must be a regular file or directory: {member.name}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            source = package.extractfile(member)
            if source is None:
                raise InstallError(f"cannot read archive member: {member.name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    roots = sorted(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise InstallError("release archive must contain exactly one package root")
    return roots[0]


def should_exclude(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts) or path.suffix == ".pyc"


def package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if should_exclude(relative):
            continue
        if path.is_symlink():
            raise InstallError(f"package sources cannot contain symlinks: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise InstallError(
                f"package sources must contain only directories and files: {relative}"
            )
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def package_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in package_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        executable = b"1" if path.stat().st_mode & 0o111 else b"0"
        size = path.stat().st_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(executable)
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def package_version(root: Path) -> str:
    version_file = root / "VERSION"
    if not version_file.is_file() or version_file.is_symlink():
        raise InstallError("package VERSION is missing or unsafe")
    value = version_file.read_text(encoding="utf-8").strip()
    semver_tuple(value)
    return value


def validate_package(root: Path, expected_version: str | None = None) -> str:
    required = (
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("scripts/foundryctl.py"),
        Path("assets/core/repo-foundry-ai/SKILL.md.template"),
        Path("assets/adapters/codex/repo-foundry-ai/SKILL.md.template"),
        Path("assets/adapters/codex/engineering-specs/SKILL.md.template"),
        Path("assets/adapters/claude/repo-foundry-ai/SKILL.md.template"),
        Path("assets/adapters/claude/engineering-specs/SKILL.md.template"),
        Path("engineering-benchmark/SKILL.md"),
        Path("detailed-design/SKILL.md"),
        Path("engineering-design/SKILL.md"),
        Path("engineering-research/SKILL.md"),
        Path("engineering-execution-plan/SKILL.md"),
        Path("engineering-case-study/SKILL.md"),
    )
    package_files(root)
    # Older pinned releases predate this optional professional capability.
    # If a distribution includes it, validate its entrypoints without
    # making installation of historical releases incompatible.
    if (root / "architecture-design").exists():
        required += (
            Path("architecture-design/SKILL.md"),
            Path("architecture-design/agents/openai.yaml"),
        )
    for relative in required:
        target = root / relative
        # Pinned older releases used discoverable names for their templates.
        if relative.name == "SKILL.md.template" and not target.exists():
            target = target.with_name("SKILL.md")
        if not target.is_file() or target.is_symlink():
            raise InstallError(f"package entrypoint is missing or unsafe: {relative}")
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not re.search(r"(?m)^name:\s*repo-foundry-ai\s*$", skill):
        raise InstallError("root SKILL.md does not declare repo-foundry-ai")
    version = package_version(root)
    if expected_version is not None and version != expected_version:
        raise InstallError(
            f"package VERSION {version} does not match release {expected_version}"
        )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(root / "scripts" / "foundryctl.py"), "--version"],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    expected = f"{PRODUCT_NAME} {version}"
    if result.returncode or result.stdout.strip() != expected:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise InstallError(f"staged package validation failed: {detail}")
    return version


def source_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED_NAMES or name.endswith(".pyc")
    }


def acquire_source(
    source: Path | None,
    repository: str,
    requested_version: str,
    scratch: Path,
) -> PackageSource:
    if source is not None:
        root = normalized_path(source)
        if not root.is_dir() or root.is_symlink():
            raise InstallError(f"local source is not a safe directory: {root}")
        version = validate_package(root)
        if requested_version != "latest" and requested_version != version:
            raise InstallError(
                f"local package VERSION {version} does not match requested "
                f"version {requested_version}"
            )
        return PackageSource(
            root=root,
            version=version,
            provenance={"kind": "local", "path": str(root)},
        )

    tag = release_tag(repository, requested_version)
    version = tag[1:]
    commit = resolve_tag_commit(repository, tag)
    archive = scratch / "release.tar.gz"
    archive_digest = download_archive(repository, commit, archive)
    extracted = scratch / "extracted"
    extracted.mkdir()
    root = extract_archive(archive, extracted)
    validate_package(root, version)
    return PackageSource(
        root=root,
        version=version,
        provenance={
            "kind": "github-release",
            "repository": repository,
            "tag": tag,
            "commit": commit,
            "archive_sha256": archive_digest,
        },
    )


def copy_package(source: Path, destination: Path) -> None:
    package_files(source)
    shutil.copytree(source, destination, ignore=source_ignore)


def load_install_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_file() or path.is_symlink():
        raise InstallError(f"install metadata is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"install metadata is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise InstallError("install metadata must be a JSON object")
    schema = value.get("schema_version")
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise InstallError("install metadata schema_version must be an integer")
    if schema > INSTALL_SCHEMA_VERSION:
        raise InstallError(
            f"install metadata schema {schema} is newer than this installer"
        )
    if schema != INSTALL_SCHEMA_VERSION or value.get("product") != PRODUCT_ID:
        raise InstallError("install metadata does not belong to this installer")
    active = value.get("active_release")
    if not isinstance(active, dict):
        raise InstallError("install metadata active_release must be an object")
    for key in ("version", "release_id", "package_sha256", "source"):
        if key not in active:
            raise InstallError(f"install metadata active_release is missing {key}")
    if not isinstance(active["version"], str):
        raise InstallError("install metadata version must be a string")
    semver_tuple(active["version"])
    if not isinstance(active["release_id"], str):
        raise InstallError("install metadata release_id must be a string")
    digest = active["package_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise InstallError("install metadata package_sha256 is invalid")
    if not isinstance(active["source"], dict):
        raise InstallError("install metadata source must be an object")
    return value


def remove_generated_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def atomic_write(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            remove_generated_path(temporary)


def atomic_symlink(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        os.symlink(target, temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            remove_generated_path(temporary)


def backup_path(prefix: Path, label: str) -> Path:
    base = prefix / "backups" / f"{label}-{utc_stamp()}"
    candidate = base
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = base.with_name(f"{base.name}-{counter}")
        counter += 1
    return candidate


def launcher_bytes(current: Path) -> bytes:
    script = current / "scripts" / "foundryctl.py"
    quoted = shlex.quote(str(script))
    return (
        "#!/bin/sh\n"
        f"{MANAGED_LAUNCHER_MARKER}\n"
        f"exec python3 {quoted} \"$@\"\n"
    ).encode("utf-8")


def launcher_is_managed(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        head = path.read_text(encoding="utf-8")[:512]
    except (OSError, UnicodeDecodeError):
        return False
    return MANAGED_LAUNCHER_MARKER in head


def symlink_resolves_to(path: Path, expected: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        return path.resolve(strict=False) == expected.resolve(strict=False)
    except OSError:
        return False


def select_hosts(
    selection: str,
    codex_home: Path,
    explicit_codex_home: bool,
    claude_home: Path | None = None,
    explicit_claude_home: bool = False,
) -> list[str]:
    if selection == "none":
        return []
    if selection in ("codex", "claude"):
        return [selection]

    resolved_claude_home = claude_home or default_claude_home()
    hosts: list[str] = []
    if (
        explicit_codex_home
        or os.environ.get("CODEX_HOME")
        or codex_home.exists()
    ):
        hosts.append("codex")
    if (
        explicit_claude_home
        or os.environ.get("CLAUDE_CONFIG_DIR")
        or resolved_claude_home.exists()
    ):
        hosts.append("claude")
    return hosts


def retained_host_integrations(
    previous: dict[str, Any] | None,
    current: Path,
    excluded_hosts: set[str] | None = None,
) -> list[dict[str, str]]:
    if previous is None:
        return []
    records = previous.get("host_integrations", [])
    if not isinstance(records, list):
        raise InstallError("install metadata host_integrations must be an array")
    retained: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, dict):
            raise InstallError("install metadata host integration must be an object")
        host = record.get("host")
        raw_path = record.get("path")
        if not isinstance(host, str) or not isinstance(raw_path, str):
            raise InstallError("install metadata host integration is invalid")
        if excluded_hosts and host in excluded_hosts:
            continue
        path = normalized_path(Path(raw_path))
        if symlink_resolves_to(path, current):
            retained.append(
                {"host": host, "path": str(path), "target": str(current)}
            )
    return retained


def action_for(previous: dict[str, Any] | None, version: str, release_id: str) -> str:
    if previous is None:
        return "installed"
    active = previous["active_release"]
    previous_version = active["version"]
    if active["release_id"] == release_id:
        return "unchanged"
    if semver_tuple(version) > semver_tuple(previous_version):
        return "upgraded"
    if semver_tuple(version) < semver_tuple(previous_version):
        return "downgraded"
    return "reinstalled"


def validate_existing_release(
    release: Path,
    version: str,
    expected_digest: str,
) -> None:
    if release.is_symlink() or not release.is_dir():
        raise InstallError(f"release path is not a safe directory: {release}")
    validate_package(release, version)
    actual = package_sha256(release)
    if actual != expected_digest:
        raise InstallError(
            f"installed release content differs from the requested package: {release}"
        )


def _install_package_locked(
    source: PackageSource,
    prefix: Path,
    bin_dir: Path,
    hosts: list[str],
    codex_home: Path,
    allow_downgrade: bool,
    claude_home: Path | None = None,
) -> dict[str, Any]:
    prefix = normalized_path(prefix)
    bin_dir = normalized_path(bin_dir)
    codex_home = normalized_path(codex_home)
    claude_home = normalized_path(claude_home or default_claude_home())
    releases = prefix / "releases"
    metadata_path = prefix / "install.json"
    current = prefix / "current"
    launcher = bin_dir / "repofoundry"
    previous = load_install_metadata(metadata_path)

    if previous is not None:
        old_version = previous["active_release"]["version"]
        if (
            semver_tuple(source.version) < semver_tuple(old_version)
            and not allow_downgrade
        ):
            raise InstallError(
                f"refusing to downgrade {old_version} to {source.version}; "
                "pass --allow-downgrade explicitly"
            )
        old_source = previous["active_release"].get("source", {})
        if (
            source.provenance.get("kind") == "github-release"
            and old_source.get("kind") == "github-release"
            and old_version == source.version
            and old_source.get("commit") != source.provenance.get("commit")
        ):
            raise InstallError(
                f"release tag v{source.version} resolves to a different commit "
                "than the installed immutable release"
            )

    prefix.mkdir(parents=True, exist_ok=True)
    releases.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=releases) as temporary:
        staged = Path(temporary) / "package"
        copy_package(source.root, staged)
        version = validate_package(staged, source.version)
        digest = package_sha256(staged)
        identity = source.provenance.get("commit", digest)
        if not re.fullmatch(r"[0-9a-f]{40,64}", identity):
            raise InstallError("package source identity is invalid")
        release_id = f"{version}-{identity[:12]}"
        release = releases / release_id
        created_release = False
        if release.exists() or release.is_symlink():
            validate_existing_release(release, version, digest)
        else:
            os.replace(staged, release)
            created_release = True

    action = action_for(previous, version, release_id)
    selected_host_links: list[dict[str, str]] = []
    backups: list[str] = []
    transaction = ActivationTransaction()
    try:
        desired_current_target = str(Path("releases") / release_id)
        if current.exists() or current.is_symlink():
            if previous is None or not current.is_symlink():
                backup = backup_path(prefix, "current")
                transaction.move_to_backup(current, backup)
                backups.append(str(backup))
            else:
                transaction.snapshot(current)
        else:
            transaction.snapshot(current)
        atomic_symlink(current, desired_current_target)

        if launcher.exists() or launcher.is_symlink():
            if launcher_is_managed(launcher):
                transaction.snapshot(launcher)
            else:
                backup = backup_path(prefix, "repofoundry-launcher")
                transaction.move_to_backup(launcher, backup)
                backups.append(str(backup))
        else:
            transaction.snapshot(launcher)
        atomic_write(launcher, launcher_bytes(current), 0o755)

        host_homes = {
            "codex": codex_home,
            "claude": claude_home,
        }
        selected_hosts: set[str] = set()
        for host in hosts:
            try:
                host_home = host_homes[host]
            except KeyError as exc:
                raise InstallError(f"unsupported Agent host: {host}") from exc
            link = host_home / "skills" / PRODUCT_ID
            desired = current
            if not symlink_resolves_to(link, desired):
                if link.exists() or link.is_symlink():
                    backup = backup_path(prefix, f"{host}-skill")
                    transaction.move_to_backup(link, backup)
                    backups.append(str(backup))
                else:
                    transaction.snapshot(link)
                atomic_symlink(link, str(desired))
            selected_host_links.append(
                {"host": host, "path": str(link), "target": str(desired)}
            )
            selected_hosts.add(host)
        selected_host_links.extend(
            retained_host_integrations(previous, current, selected_hosts)
        )

        result = subprocess.run(
            [str(launcher), "--version"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode or result.stdout.strip() != f"{PRODUCT_NAME} {version}":
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise InstallError(f"installed launcher validation failed: {detail}")

        metadata = {
            "schema_version": INSTALL_SCHEMA_VERSION,
            "product": PRODUCT_ID,
            "active_release": {
                "version": version,
                "release_id": release_id,
                "package_sha256": digest,
                "source": source.provenance,
            },
            "launcher": str(launcher),
            "host_integrations": selected_host_links,
        }
        transaction.snapshot(metadata_path)
        atomic_write(
            metadata_path,
            (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        transaction.commit()
    except Exception:
        transaction.rollback()
        if created_release and release.exists() and not release.is_symlink():
            shutil.rmtree(release)
        raise

    return {
        "schema_version": INSTALL_SCHEMA_VERSION,
        "action": action,
        "version": version,
        "source": source.provenance,
        "package_sha256": digest,
        "home": str(current),
        "cli": str(launcher),
        "host_integrations": selected_host_links,
        "backups": backups,
        "project_harnesses_modified": False,
    }


def install_package(
    source: PackageSource,
    prefix: Path,
    bin_dir: Path,
    hosts: list[str],
    codex_home: Path,
    allow_downgrade: bool,
    claude_home: Path | None = None,
) -> dict[str, Any]:
    locked_prefix = normalized_path(prefix)
    locked_prefix.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        raise InstallError("this platform does not provide a supported install lock")
    lock_path = locked_prefix / ".install.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return _install_package_locked(
                source,
                locked_prefix,
                bin_dir,
                hosts,
                codex_home,
                allow_downgrade,
                claude_home,
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Install or upgrade the latest stable RepoFoundry AI release."
    )
    result.add_argument(
        "--version",
        default="latest",
        help="stable release version (MAJOR.MINOR.PATCH) or latest",
    )
    result.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help="GitHub repository in OWNER/NAME form",
    )
    result.add_argument("--prefix", type=Path, default=default_prefix())
    result.add_argument("--bin-dir", type=Path, default=default_bin_dir())
    result.add_argument(
        "--host",
        choices=("auto", "codex", "claude", "none"),
        default="auto",
        help=(
            "Agent host registration: auto detects supported hosts, codex or "
            "claude ensures that host link, and none leaves registrations unchanged"
        ),
    )
    result.add_argument("--codex-home", type=Path)
    result.add_argument("--claude-home", type=Path)
    result.add_argument(
        "--source",
        type=Path,
        help="install an explicit local checkout instead of a GitHub release",
    )
    result.add_argument("--allow-downgrade", action="store_true")
    result.add_argument("--json", action="store_true")
    return result


def print_human(result: dict[str, Any]) -> None:
    print(
        f"{PRODUCT_NAME} {result['version']} {result['action']}.\n"
        f"Home: {result['home']}\n"
        f"CLI: {result['cli']}"
    )
    for integration in result["host_integrations"]:
        print(
            f"{integration['host'].capitalize()} Skill: "
            f"{integration['path']} -> {integration['target']}"
        )
    for backup in result["backups"]:
        print(f"Backup preserved: {backup}")
    print("Project Harnesses modified: no")
    if str(Path(result["cli"]).parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"Add {Path(result['cli']).parent} to PATH to use `repofoundry`.")


def main(arguments: list[str] | None = None) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print(
            f"install: Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+ is required",
            file=sys.stderr,
        )
        return 1
    if os.name != "posix":
        print(
            "install: this release supports macOS and Linux installation; "
            "Windows host integration is not yet available",
            file=sys.stderr,
        )
        return 1
    args = parser().parse_args(arguments)
    try:
        repository = normalize_repository(args.repository)
        if args.version != "latest":
            semver_tuple(args.version)
        prefix = normalized_path(args.prefix)
        bin_dir = normalized_path(args.bin_dir)
        validate_install_locations(prefix, bin_dir, args.source)
        explicit_codex_home = args.codex_home is not None
        codex_home = normalized_path(args.codex_home or default_codex_home())
        explicit_claude_home = args.claude_home is not None
        claude_home = normalized_path(args.claude_home or default_claude_home())
        hosts = select_hosts(
            args.host,
            codex_home,
            explicit_codex_home,
            claude_home,
            explicit_claude_home,
        )
        scratch_parent = prefix.parent
        scratch_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".repofoundry-download-", dir=scratch_parent
        ) as temporary:
            source = acquire_source(
                args.source,
                repository,
                args.version,
                Path(temporary),
            )
            result = install_package(
                source,
                prefix,
                bin_dir,
                hosts,
                codex_home,
                args.allow_downgrade,
                claude_home,
            )
    except (InstallError, OSError, subprocess.SubprocessError) as exc:
        print(f"install: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
