# Real Agent activation pilot — prepared, not executed

This follow-up to [PR #111](https://github.com/XiaoWeiKIN/RepoHarnessKit/pull/111)
prepares a small real-Agent trial. It **does not run a model**, score provisional
labels, introduce a Router gate, or claim independent Gold Set acceptance.
The original 2026-11-04 host could not start Codex: the executable was absent. The
[host observation](evidence/20261104-preflight.json) records zero Agent trials,
null activation metrics and unresolved runtime/isolation prerequisites.

The parent is `1e8c6a1d5b5ecfa9262cc9908721702734bc98b1`. This change is stacked on
#111 without merging or changing it. The existing production Router and all
old Benchmark Runs, labels, Specifications and version planes remain unchanged.

## Question and prospective protocol

Can a fresh Coding Agent use the installed repository workflow to select and
receive applicable Requirements before a bounded code change, without being
shown expected IDs? Candidate retrieval alone cannot answer this question.

The initial diagnostic pilot uses four self-contained tasks from the fixed
PR-A corpus: formatting, private-parameter renaming, ordinary read-only
explanation, and an underspecified parsing decision. These cover mutation,
workflow exemption and uncertainty without an unavailable generator or private
historical final patch. The other eight PR-A cases are not deleted or regraded;
within-turn scope refresh and historical behavioral compliance are **not tested
by this initial subset**. The selected cases and order precede any model output.

The prospective schedule is three fresh sessions per task: 12 planned trials,
not 12 observations. Use round-robin case order for each of three rounds. Record
every attempted session, startup error, timeout and guided recovery. Never
replace a failed first attempt with a later successful attempt. No A/B or causal
benefit claim is part of this pilot.

The treatment uses the official upgrader to select **strict governance in
throwaway subjects only**. This is an explicit change from the fixture's
adaptive policy, not a claim about default deployed projects. Ordinary
explanation still follows the entrypoint's exemption; absence of an activation
receipt is not automatically an error for that task. An underspecified boundary
must retain its missing-context status rather than acquiring a fabricated
binary label.

Hypotheses for the later trial are prospective: supported edit tasks obtain
source-matching activation and context before their first protected mutation;
ordinary explanation does not acquire an invented edit obligation; ambiguous
inputs produce explicit missing facts rather than unsupported certainty.
Violating an obligation with sufficient independently frozen applicability and
host trace evidence falsifies its hypothesis. Missing labels, incomplete traces
or unknown ordering give **unverified**, not a passing outcome. Do not select
semantic thresholds after observing model output.

This document is an execution-protocol draft, **not a sealed Benchmark Run**.
Before a real trial, freeze the runtime version/binary identity, requested model
(and reported identity where available), tool permissions, hook capability,
time/token/cost limits, independent review records and input tree hashes in a
new native Benchmark Scenario using `engineering-benchmark`. Allocate IDs
against the owner's current registry, including retained unpublished BR-003 /
BR-004; do not overwrite or reuse those IDs. This host preparation/probe is not
relabelled as a model experiment.

## Prepare answer-free subjects

The preparation code reuses the repaired #111 evaluator's pin and fixture
validation; it does not copy the Router implementation or select Requirement
IDs. Use the original fixture with SHA-256
`4681634fe89b8ba56e46e73d943ded022f86666b476f9209eb847ca203414398`,
from benchmark commit `73f08883f4cdd17f7aef90f4962f2872a0b9d9a3`, path
`fixtures/task3/initial-B.tar.gz`. Retrieval details remain in the
[baseline guide](../spec-activation/README.md).

```sh
python3 -B evals/agent-activation/pilot.py prepare \
  --fixture /external/initial-B.tar.gz \
  --output /external/new-agent-pilot
python3 -B evals/agent-activation/pilot.py probe
python3 -B -m unittest tests.test_agent_activation_pilot -v
```

`prepare` refuses an existing output or output inside this checkout. It validates
the original fixture and pinned inputs, previews and applies the official
`upgrade --to 0.15.3 --governance-profile strict`, then runs Harness and Spec
validation. Business Go/module and managed Spec bytes must remain unchanged by
the upgrade. Only the declared **before** snapshots are overlaid afterward.
Each subject gets fresh one-commit Git history containing only its initial
files. The preparation copies no original corpus, category/review labels,
reference patches, after-snapshots, or candidate observations into the subject.

The output separates `subjects/case-NN/{TASK.md,project/}` from
`coordinator/{setup.log,preparation.json}`. The allowlisted model input consists
of the task plus that subject's full repository, including the locked normative
Specifications and existing project guidance. **Directory separation is not
process isolation.** Mount just one subject into a new isolated runner; do not
mount this source checkout, any reproduction ZIP, coordinator directory,
adjudication matrix, hidden acceptance tests or previous conversations.
The supplied fixture retains its ordinary project documents; those are not
claimed to be blinded or independently curated evaluation data.

A successful prepare exits 0 and writes `PREPARED_NOT_EXECUTED`. This is neither
a trial nor approval to execute arbitrary repository code. Setup failures retain
a failure record and no completed preparation manifest. Setup logs contain
source paths and may include normative information: retain them privately.

## Runtime and evidence boundary

`probe` runs only `codex --version` and `codex login status` when Codex exists.
It never installs software, reads authentication caches, prints token values,
starts `codex exec`, contacts a model on purpose, or grants approval. Missing
CLI/auth is `BLOCKED_NOT_STARTED`, exit 2. Even `LOCAL_PREREQUISITES_ONLY`, exit
0, does **not** establish model access, OS isolation or a working native Hook.

On a trusted isolated host, an operator must verify that the Agent cannot read
a coordinator-only canary or other subjects/labels, and that logs are collected
outside its writable filesystem. Use fresh runtime state and no resumed
conversation for each repetition. Authenticate on that host through its normal
secure mechanism; do not put credentials in Git, fixtures, evidence or chat.

The official [non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes `codex exec --json`, and the
[CLI reference](https://learn.chatgpt.com/docs/cli/reference) describes model,
sandbox and login-status options. A later operator can supply a task on stdin
with the following argv, after checking the pinned CLI's help and local policy:

```sh
codex exec --json --sandbox workspace-write --model "$MODEL_ID" -
```

The process cwd must be the prepared project. Feed only its `TASK.md` on stdin;
collect stdout/stderr in the **trusted coordinator**, not in an Agent-writable
output file. `MODEL_ID` is intentionally not guessed. Do not add `--yolo`, pass
gold IDs via `--expect-requirement`, inject a reference patch, or quietly enable
unreviewed Hooks. Runtime sandbox settings alone do not prove read isolation.

Preserve the prompt, input tree, runtime/model configuration, unedited event
stream, actual Router commands and receipt/capsule outputs, code diff and
completion. Score initial direct selections separately from resolved context
dependencies. A capsule digest is not evidence that the model understood it.
Use trusted host mutation ordering for the pre-edit assertion: JSONL summaries
and final filesystem comparisons alone cannot establish every shell write or
an edit subsequently reverted. Where coverage is unavailable, mark ordering
and native enforcement **UNVERIFIED / NOT_TESTED**.

## Scoring and unresolved evidence

The current corpus and the later same-conversation adjudication are not an
independently accepted Gold Set. Any collected diagnostic trials stay unscored
until a genuinely unexposed reviewer freezes the task/Requirement judgements.
Do not convert the 33 disputed rows into false positives or false negatives.
For a later declared scoring analysis, publish TP/FP/FN, assessed denominators,
excluded pairs and coverage; undefined denominators remain null. Separate
first attempts, dependency closure and prompted recovery, and report each
replicate rather than treating repeated CLI reads as new Agent samples.

The unlocated original 17 omissions / seven violations stay quarantined in the
existing history ledger. This preparer neither repeats the source search nor
turns those aggregates into labels. It does not claim code behavior satisfies
the Specification or replace PR #110's independent completion-verification work.

## Current handoff

Prepared subjects are available privately with a digest inventory. The recorded
host has no Codex executable and no `CODEX_API_KEY` environment value; saved-login
status is **not tested**, rather than inferred from that environment alone.
No fresh Agent or independent reviewer was launched, and no activation
accuracy was measured. The next operational prerequisite is an authenticated,
isolated Agent runner. More Router code or another semantic validator will not
remove this runtime blocker.


## Updated target on current main (2026-11-05)

The prospective preparation now uses distribution 0.15.3 and still requires an authenticated isolated runner and independently frozen labels for any scored Agent trial. The earlier 0.15.2 preflight evidence is historical and has not been rewritten. Preparation is not an executed Agent benchmark; zero model executions remain recorded.
