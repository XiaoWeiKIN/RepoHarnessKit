# Coordinator-owned Verification Completion Check (opt-in)

This is a **fail-closed completion status check**, not an automated Requirement
applicability classifier, a native Hook, a Spec compliance verdict, or an
approval to merge. It composes existing `verification_receipt.py` evidence
without altering its schema or published semantics.

## When to use

Before an Agent starts, a **trusted coordinator** freezes the exact required
checks into a policy JSON file outside the Agent's editable worktree, and
preserves its SHA-256 **outside the Agent's control**. The CLI requires this
predeclared digest and rejects a different policy. A digest does not authenticate
the author; the trusted caller must control that argument.

A Requirement's natural-language Verification text is **not** automatically
translated into commands. The coordinator chooses commands appropriate to that
repository and risk; all applicable Requirements still need independent review.

Example coordinator policy at /trusted/check-policy.json:

```json
{
  "schema_version": 1,
  "required_checks": [
    {"id": "go-tidy", "command": ["go", "mod", "tidy", "-diff"]},
    {"id": "go-race", "command": ["go", "test", "-race", "./..."]},
    {"id": "go-vet", "command": ["go", "vet", "./..."]}
  ]
}
```

The Agent or coordinator runs those exact commands through the existing
revision-bound Receipt CLI, with separate output paths **outside the worktree**:

```sh
python3 -B <distribution>/scripts/verification_receipt.py --repo . run \
  --output /trusted/receipts/go-tidy.json -- go mod tidy -diff
python3 -B <distribution>/scripts/verification_receipt.py --repo . run \
  --output /trusted/receipts/go-race.json -- go test -race ./...
python3 -B <distribution>/scripts/verification_receipt.py --repo . run \
  --output /trusted/receipts/go-vet.json -- go vet ./...
```

The evidence index /trusted/receipts/evidence.json identifies saved Receipts,
but is **not** the source of required commands:

```json
{
  "schema_version": 1,
  "receipts": [
    {"id": "go-tidy", "path": "/trusted/receipts/go-tidy.json"},
    {"id": "go-race", "path": "/trusted/receipts/go-race.json"},
    {"id": "go-vet", "path": "/trusted/receipts/go-vet.json"}
  ]
}
```

After final source freeze, a trusted caller runs the completion check with the
**previously frozen policy digest** (do not let the Agent regenerate it):

```sh
python3 -B <distribution>/scripts/verification_completion.py --repo . \
  --policy /trusted/check-policy.json \
  --policy-sha256 "$FROZEN_COORDINATOR_POLICY_SHA256" \
  --evidence /trusted/receipts/evidence.json
```

Exit codes: 0 if all required checks have matching, current PASS Receipts;
1 if any required check is FAIL, STALE or UNVERIFIED;
2 on invalid input or environmental failure.
The result is bounded JSON on stdout. The checker rereads coordinator inputs
and detects replacement of Receipts between its two validation steps.

Never report complete verification when its exit status is nonzero.

## Limitations

- Policy, expected SHA-256, and evidence paths must be supplied by a **trusted
  caller**, not invented by the Agent. An ordinary hash is not authentication.
- Receipt data is digest-checked, **not authenticated**. This tool cannot
  attest to actual tool identity, runtime isolation, complete session capture,
  or OS-level enforcement.
- Source binding covers Git-observed changes and paths explicitly observed by
  the saved Receipts, including Git-ignored files. Unbound ignored inputs and
  external dependencies remain unknown.
- The gate rejects content-identical Receipt copies and hardlinks used for more
  than one required check. Receipt contents and identity are rechecked after all
  per-command checks, rather than only during each individual check.
- Coordinator JSON, evidence index and Receipt paths must not contain symlinks
  in any ancestor directory. On macOS, use canonical paths (for example under
  /private/var rather than /var when /var is a symlink).
- Path checks and before/after snapshots are best-effort. They do not prevent
  hostile concurrent mutation, including a change reverted between snapshots;
  trusted isolation and source freeze remain mandatory.
- This checks a **predeclared command list**, not all Requirement obligations;
  independent Requirement-level grading remains necessary.
- The CLI is **opt-in**; it does not install a Codex native completion Hook.
- Formatters must have a nonzero exit on detected format drift: plain
  `gofmt -l` exits zero even when files need formatting.
- A Receipt obtained before a code rewrite becomes STALE. Freeze final code,
  rerun necessary checks, then create new Receipts rather than overwriting old.
- A coordinator must prevent additional writes after the successful gate if
  its result is to describe the submitted source snapshot.

## Run tests

```sh
python3 -B -m unittest tests.test_verification_completion \
  tests.test_verification_receipt -v
```

Do not interpret passing unit tests as proof of Agent-level behavioral compliance.
