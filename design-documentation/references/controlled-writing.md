# Controlled technical writing

This is RepoFoundry authoring guidance, not a Catalog Specification. It combines
selected Google developer-documentation practices for readers, organization,
procedures, and accessibility with STE-inspired precision. It does not reproduce
ASD-STE100 or its dictionary, claim full ASD-STE100 conformance, or imply Google
endorsement. Source references and RF-specific adaptations are identified below.

Read the shared guidance through documentation maintenance, then the section for
the artifact being written. Apply it to new prose and authorized revisions, not
to an entire repository at once. This guide adds no approval step or lifecycle gate.

## Editorial basis and precedence

Technical facts, artifact contracts, installed Specifications, evidence, and
authority boundaries remain controlling. Follow project-specific writing and
language conventions before this guide's editorial defaults. Within those
boundaries, use Google-informed organization and natural prose together with
STE-inspired terminology and unambiguous actions. Style never overrides meaning.
Do not create a separate Google-writing policy, mandatory document fields, or
an extra Skill. A useful exception should be consistent and preserve meaning.

## Language and fidelity

Keep the user's requested language; otherwise follow the Skill and repository
language conventions. Use STE-inspired English for English prose. For Chinese
and other languages, use the clarity principles without imposing English
vocabulary, grammar, or word-count rules. Do not translate a document merely to
apply this guide. Keep bilingual versions aligned in meaning and evidence.
English sentence case and word-count advice do not become Chinese writing rules.

Preserve conditions, negation, quantifiers, uncertainty, units, and requirement
strength. Do not replace `MUST` with `SHOULD`, turn a possibility into a fact, or
remove a qualification to shorten a sentence. Keep technical terms, identifiers,
commands, paths, interface names, schema fields, and evidence references exact.
Do not replace distinct operations with one word just because they look similar.

In ordinary guidance, make requirements, recommendations, options, and predicted
results distinguishable. Do not replace normative `MUST`, `SHOULD`, or `MAY` to
follow an editorial preference against "should". Prefer present tense for verified
current behavior, but keep proposed behavior, future actions, and historical
observations in their actual state. Changing tense does not implement a proposal.

Do not rewrite quoted source text, raw logs, code, or normative source excerpts
for style. Do not change metadata, IDs, required headings, generator markers,
digests, or lifecycle fields. Do not rewrite accepted ADRs, approved snapshots,
sealed Checkpoints, sealed Benchmark bundles, or archived plans in place. Use
the owning workflow's revision or supersession process when a change is needed.

## Common guidance

Use one stable term for each concept. Define an unfamiliar term at first use.
Retain established software terminology, including backpressure, idempotency,
and write-ahead log. A plain synonym is not an improvement if it changes meaning.

Prefer short, complete sentences with one main claim or action. Keep conditions
and exceptions with the claim they limit. Split a sentence when that makes the
logic clearer; do not enforce an arbitrary word limit or produce fragments.
Use connected paragraphs to explain mechanisms and trade-offs, rather than a
sequence of disconnected bullets.

Name the actor when several components or people could perform the action.
Use a direct verb when it is clearer than an abstract noun phrase. Imperatives
can address the operator directly. Passive voice is acceptable when the actor
is irrelevant or unknown; do not invent an actor to avoid it.

Replace an ambiguous reference such as "this", "it", or "the relevant component"
with the actual subject. Put a prerequisite before the action that requires it.
State failure and stop conditions when the source contract supplies them. If a
required detail is unknown, name the gap instead of inventing a command or rule.

Remove filler, idioms, and promotional wording. Support a comparison with its
criterion, evidence, and scope. Words such as "robust" or "significant" are not
banned: a defined statistical term or a supported claim can require them.
Do not invent a measurement to justify an adjective.

Separate observations, interpretations, proposals, decisions, and unknowns.
Keep the evidence and its limits near the claim. Retain negative evidence and
uncertainty. Clear prose must not imply acceptance, approval, completion, or
verification that did not occur.

## Reader and structure

Identify the reader's task, relevant prior knowledge, and what they need to learn
or decide. Use context already available; ask only about gaps that change the
result. Do not require an audience form or a new section in every artifact.
Open with the answer or system model the reader needs, plus material limits.
Introduce unfamiliar concepts before their internals and keep deep detail after
the main explanation or behind a meaningful link.

Give each paragraph a clear point, then connect its evidence and consequences.
Use transitions that explain cause, contrast, or sequence, not decorative filler.
Write naturally and respectfully; do not describe a task as "easy" or "obvious".
Use lists for steps or parallel choices, not to replace a connected explanation.

Use descriptive headings in a logical hierarchy. For new English headings,
prefer sentence case, action phrases for tasks, and noun phrases for concepts.
Keep required headings and existing anchors stable; check inbound links before
an authorized rename. Use code formatting for identifiers, paths, commands, and
literal output; use bold for named UI controls. Link text should name its target
or purpose, not say "click here". Avoid unnecessary formatting for emphasis.

## Procedures and examples

Before a procedure, state the relevant environment, prerequisites, and authority
needed. Use numbered steps for ordered multi-step work, usually one main action
per step. Put conditions and the action's location before the dependent action.
Introduce a command by its purpose, explain every placeholder, and describe the
expected result after the action. Mark optional steps and failure or stop branches
explicitly. Keep preview, apply, verification, and release distinct.

Keep code examples small enough to inspect. Identify pseudocode, omitted setup,
and illustrative output; label measured output with its actual source. Verify
commands against available tools and interfaces, but do not execute destructive
or external actions merely to validate prose. Report untested examples instead
of claiming success. Never invent flags, output values, or a recovery procedure.

## Accessible explanations

Provide an equivalent text explanation for a diagram, image, or animation.
Describe its relevant relationships or conclusion, not merely "architecture
image". Use appropriate alt text for informative images and empty alt text for
pure decoration. Keep code and output as selectable text, not screenshots alone.
Do not communicate status only through color, position, shape, or sound.

For requested interactive views, use semantic controls with clear labels and
keyboard access. Keep focus and reading order meaningful, and offer a static text
or table route to the same facts. For audio or video, provide captions, a transcript,
or a description that conveys the content. Avoid flashing or unnecessary motion;
provide playback controls when animation is used. Check the rendered reading path
when tools permit, and report which accessibility checks were not performed.
These are authoring and review expectations, not a claim of accessibility certification.

Do not generate HTML or video just to satisfy this guide. When a derived view is
requested, keep its source revision, assumptions, and limits visible. It does not
become a second fact owner. Source changes require rechecking or regeneration;
a polished view is not proof of actual behavior or approval.

## Preserve meaning while editing

Decide whether the task is polishing, rebuilding, or review before changing prose.
Polishing may change wording and organization but not the factual model, source
status, headings, anchors, commands, or evidence. Rebuilding may correct facts
only from inspected sources and within the requested scope. Review-only work
returns findings instead of editing the artifact.

After an edit, compare the revision with its source rather than checking style in
isolation. Confirm that every material condition, exception, failure branch, and
empty-input behavior still limits the same claim. Confirm that the same actor owns
each action and that caller-controlled state has not become component-owned state.
Keep negation, quantities, units, uncertainty, and normative strength unchanged.
Keep proposal, authorization, implementation, verification, and historical status
distinct. Preserve code, quotations, raw output, IDs, links, required headings,
digests, and sealed content exactly.

Shorter wording is useful only when it preserves the decision tree. For example,
consider a constructed configuration loader with three outcomes: a missing file
uses defaults, an invalid file stops with an error, and a valid file is parsed.
The sentence "the loader uses defaults" loses two branches even though every word
is clear. A keyword scan cannot establish equivalence; compare the branches.

Use project terminology before editorial preferences. Read the repository's
glossary, writing conventions, entry instructions, and affected sources when they
exist. If the project has no terminology owner, keep terms stable within the
document and define only unfamiliar concepts. Do not create a repository-wide
glossary, rename code, or rewrite historical terms merely to make prose uniform.


## Precise Chinese technical prose

中文技术说明应保留完整的条件、主体和因果关系。拆句后，条件仍应约束原来的动作；
主语改变时，应写出组件、工具或操作人的名称。不要为了句子更短而省略失败分支。

优先使用项目已经采用的术语。代码名、命令、测试名和规范关键词保持原样。同一个概念
在一个说明中不应为了文风变化而反复换名；但不同概念也不应为了统一措辞被合并。

抽象动词和长修饰语可作为复核线索。只有在来源明确主体和动作时，才把“对配置进行
检查”改成“加载器检查配置”。如果来源没有说明主体，应报告缺口，而不是猜一个主体。
指代词可能造成两个解释时，直接写出被指代的对象。

新写要求应先采用项目已有的规范关键词。项目没有规定时，用明确措辞区分硬性要求、
推荐、许可和能力，但不要为了文风统一发明新的规范词表。已有的 MUST、SHOULD、MAY
及项目固定译名保持原有强度。

操作步骤和机制说明使用不同结构。给操作人员的步骤应把前提和停止条件放在依赖它们的
动作旁边。描述软件自动事件时，说明触发条件、组件动作和结果，不要改写成给读者执行的
命令。Architecture、Research 和 Case Study 可以保留连贯段落来解释机制和取舍。


## Optional source-bound prose hints

The full RF checkout includes `scripts/check_writing.py`. The script reads only
explicitly named UTF-8 Markdown or text files. It reports source-bound review
candidates with line locations and an input SHA-256. It does not edit files,
traverse a project, fetch policy, call a model, or decide whether a statement is
true. Independently installed professional Skills do not require the script.

Run it only when a mechanical pass is useful:

```bash
python3 -B scripts/check_writing.py PATH --lang zh --json
python3 -B scripts/check_writing.py PATH --lang zh --line-range 12:35 --json
```

The second command limits hints to an explicitly selected inclusive range while
still reading the file for Markdown context. Repeat `--line-range` for additional
ranges. Omit `--lang` for per-line Chinese/English detection. The detector is a
heuristic and does not translate or validate other languages.

The checker looks for a small set of patterns already covered by this guide, such
as abstract action phrases, vague scope words, and potentially ambiguous English
subjects. A match is a review candidate, not a defect. The scanner masks code
fences, inline code, quotations, metadata, link destinations, and HTML blocks
conservatively, so it can also omit prose.

Findings return exit status 0. Unreadable files, invalid ranges, invalid UTF-8, and
files larger than 1 MiB return 2. Tool errors must not be described as a clean
scan. There is no autofix, recursive scan, compliance score, or blocking style
mode. Keep checker unit tests in repository CI; do not make prose findings a merge
gate.


## Report writing verification

Report what actually happened. If a checker ran, record its command, input revision
or digest, exit status, candidate count, and unperformed checks. If it did not run,
say so. Reading the script is not execution, and zero candidates do not prove
semantic fidelity, accessibility, model adherence, or ASD-STE100 conformance.

Keep the document readable. Execution-critical prerequisites, risks, and stop
conditions belong beside the action they control. Missing evidence or noncritical
editorial questions can go in a short author handoff. Use a placeholder only when
the reader cannot perform the task without the missing value. Never invent a
command, measurement, owner, recovery path, or successful result to fill a gap.

Keep factual corrections separate from wording changes. During polishing, retain
an unsupported claim at its original strength and flag the evidence gap; if an
inspected source contradicts the claim, do not present it as verified current
behavior.

For comparative writing evaluations, fix the source material, task, model settings,
output budget, and scoring assertions before generation. Prefer isolated runs and
hidden treatment labels when practical. Retain failures. Packaging tests and eval
catalogs do not run a model, and same-session reconstructions are demonstrations
rather than blind evidence of quality improvement.

## Documentation maintenance

When authorized code changes affect documentation, update the current explanation
in the same change when feasible, or identify the remaining gap. Link shared facts
and procedures rather than maintaining independent copies. Use the project's
existing owner and navigation conventions; do not invent a new ownership registry.

Distinguish historical decisions from present behavior. General advice to trim
outdated docs does not authorize deleting or rewriting accepted ADRs, approved
snapshots, sealed evidence, or archived plans. Propose a current explanation or
route revision through the owning workflow. Stay within the requested scope.

## ADR

State one concrete decision or proposal, then explain its rationale. Preserve
the ADR's actual status. Identify affected behavior, constraints, alternatives,
and costs. Keep consequences separate from promised outcomes. Preserve stable
constraint IDs and the existing Confirmation and Revisit Triggers sections.
Name the evidence that supports a claimed benefit; do not turn an expected
benefit into a measured result. Writing an ADR does not accept it.

## ExecPlan, Task, and Bugfix

Describe the target, action, prerequisites, expected result, and verification
for each bounded unit of work. Use exact repository commands only when verified.
Keep ordering and failure branches explicit. Distinguish planned work from work
already performed. Separate test execution from acceptance and release authority.
Record actual blockers and recovery information, not "handle as appropriate".

## Checkpoint

State the verified revision, completed work, remaining work, evidence, and
blockers. Keep the current handoff readable without replaying the whole session.
Do not compress away a failure, unresolved condition, or evidence locator.
A stylistic revision does not justify changing sealed history.

## Architecture and Design

Explain the system model before listing files. Name boundaries, ownership,
interfaces, invariants, failure behavior, and material trade-offs. Use paragraphs,
examples, tables, or Mermaid where they explain the mechanism. Distinguish
observed behavior from proposed or approved design. Do not reduce an explanation
to short sentences that no longer establish why the design works.

## Research and Synthesis

Separate observations from interpretations and recommendations. State confidence,
applicability, counterevidence, and remaining unknowns. Explain the reasoning
between evidence and conclusion. Preserve correlation/causation distinctions
and source references. Do not turn review-ready prose into a concluded Research.

## Benchmark Scenario and Result

In a Scenario, state hypotheses, controlled variables, workload, repetitions,
units, thresholds, and failure or stop conditions before measurement. In a
Result, distinguish raw observations from interpretation and report uncertainty.
Do not change a frozen protocol, discard negative results, or rewrite an outcome
for readability. A valid digest does not prove experimental validity.

## Case Study

Use the common guidance with a lighter narrative style. Preserve the central
claim, causal explanation, examples, and trade-offs. Do not force an article into
maintenance instructions. Keep claims traceable and respect publication and
redaction boundaries. A polished article does not become a normative source.

## Examples for ADR and ExecPlan

These examples illustrate wording, not facts about a target repository.

Given an unaccepted proposal to use a read cache, a database that remains the
source of truth, and a specified fallback on cache-read failure:

> Proposed decision: Use a cache for reads. If a cache read fails, read from the
> database. The database remains the source of truth. The latency effect has not
> been measured.

Given an authorized task to run RepoFoundry's repository check, with no release
authorization:

> Run `python3 -B scripts/check.py` from the repository root. If the check fails,
> record the failure and keep the task open. If it passes, record the command,
> exit status, and tested revision. Passing this check does not authorize release.

Do not replace either example with an unsupported claim such as "the system is
now more robust" or omit its status, failure branch, or evidence limitation.

## Review before handoff

Compare the revision with its sources. Check terminology, actors, references,
conditions, uncertainty, requirement strength, evidence, and lifecycle status.
Walk the intended reader's task: can they find the answer, follow the reasoning
or procedure, and reach its evidence without relying on images, sound, or color?
Check examples, links, headings, and available keyboard paths. Separate editorial
suggestions from factual errors and record checks that could not be performed.
Correct misleading prose within the authorized scope. Report unresolved gaps
without filling them with invented facts. Then run the artifact's existing
validators; writing review is not a substitute for them.

Sentence length and keyword matches can identify review candidates. They cannot
prove clarity, truth, authorization, or ASD-STE100 compliance. Do not label a
heuristic pass as semantic verification or add a blocking style gate.

## Source references

This is RF's selective paraphrase and adaptation, not a copy of either guide.
The Google sources below inform the editorial defaults. RF adds artifact-state,
authority, exact-source, and immutable-history safeguards; it deliberately does
not impose a fixed sentence length or an English grammar on other languages.
These links are optional maintainer references, not runtime dependencies.
Use the packaged guidance offline; do not fetch the full guides for every task.

| Editorial topic | Official source |
|---|---|
| Reference hierarchy and exceptions | Google Developer Documentation Style Guide: https://developers.google.com/style |
| Reader knowledge and goals | Google Technical Writing, Audience: https://developers.google.com/tech-writing/one/audience |
| Document scope and organization | Google Technical Writing, Documents: https://developers.google.com/tech-writing/one/documents |
| Natural tone and transitions | https://developers.google.com/style/tone |
| Ordered instructions and placeholders | https://developers.google.com/style/procedures |
| Headings and inline formatting | https://developers.google.com/style/headings and https://developers.google.com/style/text-formatting |
| Requirements and tense | https://developers.google.com/style/prescriptive-documentation and https://developers.google.com/style/tense |
| Text alternatives and keyboard access | https://developers.google.com/style/accessibility |
| Current docs and shared fact ownership | Google Documentation Best Practices: https://google.github.io/styleguide/docguide/best_practices.html |
| Controlled-language background | ASD-STE100: https://www.asd-ste100.org/ |

Google Developers prose is licensed under CC BY 4.0 unless otherwise noted:
https://creativecommons.org/licenses/by/4.0/. The adaptations here are identified
above. No Google code samples or ASD-STE100 dictionary entries are reproduced.

## Distribution maintenance

The distribution source is `references/controlled-writing.md`. Each professional
Skill contains an identical file at that relative path so it works independently
and offline. These are packaged copies, not separate policy owners. From the
RepoFoundry source checkout, run `python3 scripts/sync_controlled_writing.py` to
check them or add `--apply` to refresh them after editing the source. Repository
tests check both copy integrity and the Skill reading links. Those tests do not
measure an LLM's adherence to the writing guidance.
