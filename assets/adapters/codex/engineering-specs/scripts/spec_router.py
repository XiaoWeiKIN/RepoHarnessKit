#!/usr/bin/env python3
"""Translate Codex lifecycle Hooks to RepoFoundry activation events."""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path
from types import ModuleType


ADAPTER_ID = "codex"
CORE_PATH = ".repo-foundry/engineering-specs/spec_router.py"
MAX_JSON_BYTES = 1024 * 1024
PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$",
    re.MULTILINE,
)
EVENTS = {
    "UserPromptSubmit": "session_start",
    "SubagentStart": "subagent_start",
    "PreToolUse": "before_mutation",
    "Stop": "stop",
}
READ_ONLY_COMMANDS = frozenset(
    {
        "basename",
        "cut",
        "dirname",
        "du",
        "file",
        "git",
        "grep",
        "head",
        "ls",
        "pwd",
        "readlink",
        "rg",
        "sed",
        "stat",
        "tail",
        "test",
        "type",
        "wc",
        "which",
    }
)


class AdapterError(RuntimeError):
    """Raised when a Codex Hook payload cannot be translated safely."""


def _load_core(root: Path) -> ModuleType:
    path = root / CORE_PATH
    if path.is_symlink() or not path.is_file():
        raise AdapterError(
            f"CODEX_ADAPTER_CORE_MISSING: expected a regular file at {CORE_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "_repo_foundry_spec_activation_core",
        path,
    )
    if spec is None or spec.loader is None:
        raise AdapterError(f"CODEX_ADAPTER_CORE_INVALID: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for attribute in ("PROTOCOL_VERSION", "RouterError", "process_event"):
        if not hasattr(module, attribute):
            raise AdapterError(
                f"CODEX_ADAPTER_CORE_INVALID: missing {attribute}"
            )
    return module


def _repository_root(start: object) -> Path:
    if not isinstance(start, str) or not start:
        start = "."
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / CORE_PATH).is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise AdapterError(f"CODEX_ADAPTER_REPOSITORY_NOT_FOUND: {start}")


def _json_output(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _is_router_command(command: str) -> bool:
    if any(
        token in command
        for token in (";", "&&", "||", "|", ">", "<", "`", "$(")
    ):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return (
        len(tokens) >= 3
        and tokens[0] in {"python", "python3"}
        and (
            tokens[1].endswith(CORE_PATH)
            or tokens[1].endswith(
                ".agents/skills/engineering-specs/scripts/spec_router.py"
            )
        )
        and tokens[2] in {
            "begin",
            "candidates",
            "classify",
            "requirements",
            "activate",
            "status",
            "evidence",
            "rehydrate",
            "preflight",
            "audit",
        }
    )


def _is_read_only_command(command: str) -> bool:
    stripped = command.strip()
    if not stripped or _is_router_command(stripped):
        return True
    lowered = stripped.lower()
    dangerous_tokens = (
        ">",
        "| tee",
        " -delete",
        " -exec",
        "git add",
        "git commit",
        "git push",
        "git merge",
        "git rebase",
        "git tag",
        "git switch",
        "git checkout",
        "git restore",
        "git clean",
        "git rm",
        "git mv",
        "sed -i",
        "rg --pre",
    )
    if any(token in lowered for token in dangerous_tokens):
        return False
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return False
    if not tokens:
        return True
    first = tokens[0]
    if first != "git":
        if first == "sed" and any(token.startswith("-i") for token in tokens[1:]):
            return False
        if first == "rg" and any(
            token == "--pre" or token.startswith("--pre=")
            for token in tokens[1:]
        ):
            return False
        return first in READ_ONLY_COMMANDS
    if len(tokens) < 2:
        return False
    if any(
        token == "--output" or token.startswith("--output=")
        for token in tokens[2:]
    ):
        return False
    return tokens[1] in {
        "diff",
        "log",
        "ls-files",
        "rev-parse",
        "show",
        "status",
    }


def _patch_paths(core: ModuleType, root: Path, command: str) -> list[str]:
    raw_paths = [left or right for left, right in PATCH_PATH_RE.findall(command)]
    return list(
        dict.fromkeys(
            core._normalize_planned_path(root, value.strip())
            for value in raw_paths
        )
    )


def _normalized_event(
    core: ModuleType,
    root: Path,
    payload: dict[str, object],
) -> tuple[str, dict[str, object]]:
    product_event = payload.get("hook_event_name")
    if product_event not in EVENTS:
        raise AdapterError(
            f"CODEX_ADAPTER_EVENT_UNSUPPORTED: {product_event!r}"
        )
    event = EVENTS[str(product_event)]
    normalized: dict[str, object] = {
        "protocol_version": core.PROTOCOL_VERSION,
        "event": event,
        "adapter_id": ADAPTER_ID,
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
    }
    if event in {"session_start", "subagent_start"}:
        normalized["prompt"] = payload.get("prompt", "")
    elif event == "before_mutation":
        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            normalized["tool"] = {
                "category": "unsupported",
                "name": str(tool_name or "unknown"),
                "input": {},
            }
        elif tool_name == "Bash":
            normalized["tool"] = {
                "category": (
                    "read" if _is_read_only_command(command) else "command_write"
                ),
                "name": "shell",
                "input": {},
            }
        elif tool_name == "apply_patch":
            normalized["tool"] = {
                "category": "file_write",
                "name": "patch",
                "paths": _patch_paths(core, root, command),
                "input": {},
            }
        else:
            normalized["tool"] = {
                "category": "unsupported",
                "name": str(tool_name or "unknown"),
                "input": {},
            }
    else:
        normalized["message"] = payload.get("last_assistant_message", "")
    return str(product_event), normalized


def _translate_result(
    product_event: str,
    result: dict[str, object],
) -> dict[str, object]:
    decision = result.get("decision")
    if product_event in {"UserPromptSubmit", "SubagentStart"}:
        context = result.get("context")
        if not isinstance(context, str):
            raise AdapterError("CODEX_ADAPTER_RESULT_INVALID.context")
        return {
            "hookSpecificOutput": {
                "hookEventName": product_event,
                "additionalContext": (
                    "Use the repository Skill `$engineering-specs`.\n\n"
                    + context
                ),
            }
        }
    if product_event == "PreToolUse":
        if decision == "allow":
            return {}
        if decision != "deny" or not isinstance(result.get("reason"), str):
            raise AdapterError("CODEX_ADAPTER_RESULT_INVALID.before_mutation")
        output: dict[str, object] = {
            "hookEventName": product_event,
            "permissionDecision": "deny",
            "permissionDecisionReason": result["reason"],
        }
        if isinstance(result.get("context"), str):
            output["additionalContext"] = result["context"]
        return {"hookSpecificOutput": output}
    if decision == "allow":
        return {}
    if decision != "deny" or not isinstance(result.get("reason"), str):
        raise AdapterError("CODEX_ADAPTER_RESULT_INVALID.stop")
    return {"decision": "block", "reason": result["reason"]}


def command_hook() -> int:
    raw = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise AdapterError("CODEX_ADAPTER_INPUT_TOO_LARGE")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"CODEX_ADAPTER_INPUT_INVALID: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdapterError("CODEX_ADAPTER_INPUT_INVALID: expected object")
    root = _repository_root(payload.get("cwd"))
    core = _load_core(root)
    product_event, normalized = _normalized_event(core, root, payload)
    try:
        result = core.process_event(root, normalized)
    except core.RouterError as exc:
        raise AdapterError(str(exc)) from exc
    translated = _translate_result(product_event, result)
    if translated:
        _json_output(translated)
    return 0


def _delegate_to_core(arguments: list[str]) -> int:
    root = _repository_root(".")
    core = _load_core(root)
    commands_requiring_identity = {
        "begin",
        "classify",
        "activate",
        "status",
        "rehydrate",
        "preflight",
        "audit",
    }
    command_index = next(
        (
            index
            for index, value in enumerate(arguments)
            if value in commands_requiring_identity
            or value in {"candidates", "requirements", "event"}
        ),
        None,
    )
    if (
        command_index is not None
        and arguments[command_index] in commands_requiring_identity
        and "--adapter-id" not in arguments
    ):
        arguments[command_index + 1:command_index + 1] = [
            "--adapter-id",
            ADAPTER_ID,
        ]
    return int(core.main(arguments))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments == ["hook"]:
            return command_hook()
        return _delegate_to_core(arguments)
    except AdapterError as exc:
        print(f"codex-spec-adapter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
