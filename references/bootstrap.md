# Agent-neutral Repository Harness Bootstrap

## 目标

`repo-foundry-ai` Bootstrap 把项目共享的工程控制面与具体 Coding Agent 的接入方式
分开：一个 Agent-neutral Core 持有工程文档、Harness manifest、Engineering Spec
lock 与任务激活语义；一个或多个 adapter 负责 instruction discovery、生命周期事件、
上下文注入、写入门禁与信任提示。

```mermaid
flowchart LR
    P["foundryctl 预检"] --> C["Harness Core"]
    P --> S["Spec Resolver + immutable lock"]
    P --> A["Adapter protocol"]
    C --> E["Shared activation engine"]
    A --> X["Codex adapter<br/>native Hooks"]
    A --> D["Claude adapter<br/>native Skills + CLI"]
    A --> M["Portable adapter<br/>CLI + advisory"]
    S --> E
    E --> X
    E --> D
    E --> M
```

Core 不包含产品事件名、产品配置路径、工具 payload 或信任模型。adapter 只能接入
Core 的公开契约，不得复制或改写 Engineering Specifications。

## Bootstrap 与 adapter 选择

查看当前发行版提供的 adapter、版本、enforcement 和能力：

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . adapter list
```

Bootstrap 默认 dry-run。明确选择一个或多个 adapter：

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  bootstrap --adapter portable

python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  bootstrap --adapter claude

python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  bootstrap --all-adapters \
  --spec languages/go --apply
```

adapter ID 不得重复，生成路径不得发生 ownership collision。现有 schema 3 Harness
可以追加 adapter；删除 adapter 不在当前范围内，因为删除定制配置需要独立的
所有权和迁移决策。

`--all-adapters` 确定性展开为 `codex`、`claude`、`portable`，不能与 `--profile`
或显式 `--adapter` 组合。它不做本机宿主检测，因此不同维护者会生成相同项目状态。

兼容期内：

- `--profile codex` 等价于 `--adapter codex`，并返回
  `HARNESS_PROFILE_ALIAS_DEPRECATED`；
- 同时传 `--profile` 与 `--adapter` 会失败；
- 两者都省略时暂时默认 `codex`，并返回
  `HARNESS_ADAPTER_DEFAULT_DEPRECATED`；
- schema 1/2 只读兼容，只有显式 `upgrade --to VERSION --apply`（VERSION 为已安装发行包支持的目标版本）写 schema 3。

## Core 与 adapter 的安装结构

Core 路径由所有 adapter 共享：

```text
ARCHITECTURE.md
docs/
├── .engineering/
│   ├── harness.json
│   ├── specs.json
│   └── specs.lock.json
├── agent-guides/
│   └── managed/
│       ├── index.md
│       ├── requirements.json
│       └── <locked-spec>.md
├── index.md
├── QUALITY_SCORE.md
├── RELIABILITY.md
├── SECURITY.md
└── design-docs/index.md
.repo-foundry/
├── engineering-specs/spec_router.py
└── skills/repo-foundry-ai/SKILL.md
```

canonical 项目 Skill 先选择激活深度。普通只读代码解释、导航、调用链追踪和既有行为
总结不启动完整 Harness，也不产生 Spec receipt 或治理制品；正式评审、显式 Spec
合规判断、诊断和仓库修改才按任务范围升级。Codex、Claude 与 Portable 的发现入口
必须保持相同边界，不能因宿主不同而扩大触发范围。

Codex adapter 增加：

```text
AGENTS.md
.agents/skills/repo-foundry-ai/SKILL.md
.agents/skills/engineering-specs/
├── SKILL.md
├── agents/openai.yaml
└── scripts/spec_router.py
.codex/hooks.json
```

`.agents/.../scripts/spec_router.py` 是薄翻译器，不包含第二份激活逻辑。它把 Codex
Hook 输入翻译成 Core event，再把 Core decision 翻译回 Codex Hook 输出。

Claude adapter 增加：

```text
.claude/skills/
├── repo-foundry-ai/SKILL.md
└── engineering-specs/SKILL.md
```

两个文件都是普通、仓库相对的项目 Skill。根入口读取 Core 中的 canonical Skill；
Engineering Specs 入口以 `adapter_id: claude` 调用唯一的 Core Router。当前版本不
创建 `CLAUDE.md` 或 Claude Hooks，enforcement 为 CLI/advisory。

Claude Code 中个人同名 Skill 优先于项目同名 Skill。因此发行包的个人
`repo-foundry-ai` 入口也必须在目标仓库存在 canonical Skill 时读取它；没有个人
注册时，`.claude/skills/repo-foundry-ai/SKILL.md` 直接提供同一发现入口。两条路径
最终都消费同一个仓库版本契约。

Portable adapter 只增加：

```text
docs/agent-guides/README.md
```

它通过 `begin`、`candidates`、`requirements`、`activate`、`rehydrate`、`status`、
`audit` 显式使用共享引擎，
enforcement 为 CLI/advisory，不声称原生拦截写入。

## 受控技术写作入口

当前源码的 Core `1.6.3` 与 Codex adapter `2.4.5` 保留显式写作路由；分发版本 `0.15.5` 是未发布的候选。
新建 Codex `AGENTS.md` 和共享 project Skill 会要求：撰写、修订或评审工程正文前，
先解析负责该工作的专业 Skill，再读取该 Skill 内的 `references/controlled-writing.md`。
此路径相对于专业 Skill，不相对于目标仓库或共享 project Skill。

规则正文仍由[共用写作指导](controlled-writing.md)及其专业 Skill 分发副本持有。
Bootstrap 不向项目复制该文件，不安装专业 Skill，也不向 Catalog 添加 `writing/*`。
这是 STE-inspired 写作指导，不是完整 ASD-STE100 合规验证。专业 Skill 或指导缺失时，
报告缺口并沿用项目约定；不能为了写作风格自动安装组件或创建治理制品。

Bootstrap 保留已有 `AGENTS.md`，不会静默追加路由。显式 upgrade 只替换仍等于
已记录 `installed_sha256` 的旧 seed；定制的 `AGENTS.md` 保留，定制的生成型 Core
Skill 报告 conflict 并要求显式合并。缺少写作路由本身不增加新的校验错误或审批门禁。
旧项目必须采用包含本改动的 RF 源码或后续发行版，再按预览迁移；升级用户级安装
不会自动修改任何项目。Codex `AGENTS.md` 的 100 行上限和 Core Skill 的 120 行
预算保持不变。

## 能力与 enforcement

adapter 能力由 `adapter list` 的结构化输出声明：

| 能力 | Codex | Claude | Portable |
|---|---|---|---|
| instructions | file | none | file |
| skills | file | native | none |
| lifecycle events | 五类标准化事件 | none | none |
| context injection | native | advisory | advisory |
| mutation gate | native | cli | cli |
| completion audit | native | cli | cli |
| project trust | user review | user review | none |

`native`、`cli`、`advisory` 是验证边界，不可互相冒充。Codex 的 native 声明只覆盖
已注册 Hook 与受支持工具形状；Claude 的 native 只表示 Skill discovery；Claude
与 Portable 的 CLI 检查都不等于运行时沙箱。

## Harness schema 3

`docs/.engineering/harness.json` 记录独立版本面和每个文件的唯一 owner：

下例是已发布 RepoHarnessKit `v0.15.4` 的历史清单示例：Core `1.6.2`、Codex `2.4.4`、Claude `1.3.3`、
Portable `1.3.4`。

```json
{
  "schema_version": 3,
  "owner": "repo-foundry",
  "producer": {
    "name": "repo-foundry",
    "version": "0.15.4"
  },
  "core": {
    "version": "1.6.2"
  },
  "adapters": [
    {
      "id": "codex",
      "version": "2.4.4",
      "enforcement": "native"
    },
    {
      "id": "claude",
      "version": "1.3.3",
      "enforcement": "cli"
    },
    {
      "id": "portable",
      "version": "1.3.4",
      "enforcement": "cli"
    }
  ],
  "components": ["engineering-design", "engineering-execution-plan"],
  "instruction_files": [],
  "files": [],
  "applied_migrations": []
}
```

每个 `files` 记录保留 `path`、`ownership`、`template_id`、
`template_version`、`template_sha256`、`installed_sha256`，并增加
`owner_kind: core|adapter`；adapter 文件另有 `owner_id`。未知未来 schema、Core、
adapter、template、producer 或 migration 版本一律 fail closed。

RepoHarnessKit distribution、Harness schema、Core、每个 adapter、Spec Activation
protocol 与 Engineering Specifications Catalog 分别版本化。改变 Codex Hook 字节不应
提升 Catalog；改变规范正文也不应提升 Codex adapter。

## 版本与 Harness 升级

从本源码候选发行包运行时，迁移目标为 `0.15.5`（尚未发布）：

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  upgrade --to 0.15.5
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  upgrade --to 0.15.5 --apply
```

0.8.0 引入、并由后续版本保持的 migration 会以 additive 方式创建
`docs/.epctl/decision-views.json`、`docs/DECISION-VIEWS.md` 与
`docs/decision-views/`。preview 必须逐项显示，apply 后 registry 保持空集合；迁移
不得创建领域 View 或修改任何 ADR。目标路径已有 repository-owned 内容时保留原字节，
若内容不满足新契约则失败并回滚本次新建路径，交由 owner 显式协调。

迁移默认只预览，并遵循以下证据规则：

- 文件等于当前模板：只登记当前 provenance；
- 文件等于旧记录的 `installed_sha256`：可安全替换；
- 生成文件已修改或来源未知：保留原字节并报告 conflict，要求显式合并；
- 定制的 repository document：保留原字节并清除不可信模板 provenance；
- schema 2 的 Codex profile 映射为 `codex@2.0.0` adapter；
- 安装唯一的 Core activation engine，并在来源可证明时把旧 Router 改成薄 adapter；
- schema 3 的旧 Core 与 adapter 版本保持可读；升级到候选 Core `1.6.3`、Codex
  `2.4.5`、Claude `1.3.4`、Portable `1.3.4` 时按已记录 provenance 替换生成文件并记录
  组件 migration；
- Spec manifest、lock、managed Markdown 与 Catalog 版本不参与 Harness migration；
- 写入后 validation 失败：恢复全部触碰文件并清理本次创建的空目录；
- 重复 apply：不再更新任何字节。

0.9.0 把 Core 提升到 `1.5.2`，并把 Portable adapter 提升到 `1.3.1`，以分发
ADR lifecycle/storage 变更后及 Governed 交接前的 `adr-maintenance` 检查。该迁移
只替换 provenance 可证明未修改的 Skill/guide seed；不创建维护时间戳、确认状态、
Decision View 或 History Pack，也不修改任何 ADR。Codex 与 Claude 的 discovery
Skill 继续读取同一 Core project Skill，因此无需复制策略或提升 adapter 版本。

迁移历史分别记录 `harness-schema-v1-to-v3` 或
`harness-schema-v2-to-v3`。普通 Bootstrap 不会静默迁移旧 manifest，也不会在旧
schema 上追加新的 adapter。

## Engineering Specifications

规范正文来自独立 Git Catalog。Bootstrap 安装必选 Spec 和用户通过重复
`--spec <id>` 明确选择的可选 Spec；仓库检测只生成推荐。选择写入
`docs/.engineering/specs.json`，精确 Git revision、Catalog digest、依赖闭包和内容
SHA-256 写入 `specs.lock.json`，本地副本写入
`docs/agent-guides/managed/`。

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . spec plan
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . spec sync --apply
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  spec update --spec-version 1.5.0 --spec languages/go --apply
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . spec validate
```

Catalog 更新后，只要出现尚未配置的可选 Spec，dry-run 就会返回
`selection_decision.status=required`，列出所有 candidate 的 ID、描述、依赖、推荐态
与配置态。CLI 在用户通过完整 `--spec` 集合、`--required-only` 或
`--keep-selection` 明确决策前拒绝 apply；Agent 必须展示候选并询问用户，不得自行
推断“保持原选择”。

`scripts/spec_manager.py` 只验证 Catalog、selection、lock、dependency、managed
content、路由 index 与 `requirements.json`。它不读取 `AGENTS.md`、
`.codex/hooks.json` 或 OpenAI metadata。
`foundryctl spec validate` 在 schema 3 项目中另外验证共享 activation engine，但不
验证任意 adapter route。

## 标准化任务激活

Core activation protocol version 2 接受五类事件：

```text
session_start
subagent_start
context_resume
before_mutation
stop
```

event envelope 只包含 RepoFoundry 概念：protocol version、adapter ID、不透明的
session/turn ID、可选 prompt/planned paths，以及中立 tool category。receipt 按
repository、adapter、session、turn 隔离；内部 `context_epoch` 在新上下文、子 Agent
或 `rehydrate` 时递增，因此 compaction 后能重新注入同一份精确胶囊。

```mermaid
flowchart LR
    P["计划路径"] --> S["Spec 候选 + Applicability"]
    S --> C["有界 Requirement 卡片"]
    C --> R["直接 ID + 任务理由"]
    R --> D["精确依赖闭包"]
    I["requirements.json<br/>源码范围 + SHA-256"] --> X["上下文胶囊"]
    D --> X
    X --> W["实现 / 评审 / rehydrate"]
```

`requirements.json` 是从已锁定 Spec 原字节确定性生成的派生索引。它记录每个
Requirement 的卡片、所属 Spec、精确 UTF-8 字节范围和摘要、上下文依赖、解释框架
范围、Verification 行范围与发布自动执法等级，不复制规范正文。schema v2 还记录
等级来自源码声明还是旧格式的 Advisory 默认值；Router 继续读取 schema v1。
`spec validate` 会重新生成索引并做
逐字节比较，同时再次核验每个范围与摘要。

候选仍只由 path scope 产生；Agent 必须结合任务意图判断 Spec Applicability，再从
16 KiB 卡片预算内选择最小但完整的直接 Requirement 集合。Core 计算闭包，并在
32 KiB 默认预算内按固定顺序拼装：合成身份、强制解释框架、Requirement 原文块、
对应 Verification 行与显式选取的支持章节。任何预算超限都失败，规范原文绝不摘要
或截断；提高默认预算必须用 `--capsule-budget-reason` 记录评审理由。没有正式
Requirement 的旧 Spec、迁移和全库审计可用带理由的 whole-Spec
回退；旧项目缺少派生索引时，Router 也只提供兼容性 whole-Spec 模式，执行一次
`spec sync --apply` 即生成新索引。

协议 v2 receipt 记录适用 Spec、直接/闭包 Requirement ID、逐 ID 理由、源码范围、
发布/有效自动执法等级、胶囊模式、SHA-256、字节数、预算和 epoch。`evidence`
命令会再次复核 receipt 与源码范围，并导出不含规范原文的激活证据。RepoFoundry
没有 finding 判定器，因此有效等级固定为 Advisory，导出明确标记 finding lifecycle
未实现。依赖闭包、explicit-none、digest
verification、changed-path audit 与五字段 handoff 对所有 adapter 完全相同。

## SessionStart 上下文预算

Core 的 Session Context Planner 对 `session_start`、`subagent_start`、
`context_resume` 的**非规范性路由说明**使用统一的 8 KiB UTF-8 字节预算。
它按稳定优先级选择必须内容与可选内容；预算不足时，可选的 routing index
改为 `[ContextRef:routing-index] docs/agent-guides/managed/index.md` 指针，
而不是截断或摘要索引。输出 `context_plan` 记录预算、实际使用字节数及各片段
是正文还是引用。必须内容和全部来源指针超预算时显式失败。

**此预算不约束**已激活的精确 Requirement Capsule：它仍按 32 KiB 默认预算、
摘要和完整源码范围验证来注入，不能被 Planner 截断、降级为摘要或静默省略。
Adapter 自己的引导前缀不计入 Core 的路由预算；该预算不是 Agent 整个上下文
窗口的上限。Planner 不产生新持久文件或第二套 Spec 权威。


### 按任务引用 EP 和 ADR，不扫描无关历史

SessionStart / SubagentStart 的任务文本中只有**一个明确的 `EP-NNN` 引用**时，
Core 才只读该 active EP 的 `## Current Snapshot`，连同 `adr_refs`
在 `docs/DECISIONS.md` 的 `ADRCTL:CURRENT` 投影中查找对应的当前决策导航。
任务文本显式包含的 `ADR-NNN` 也参与导航。没有 EP 引用或引用了多个不同 EP
时，不猜测“当前”计划，也不扫描所有 EP / ADR。Resume 使用同一会话先前记录
的 ID 重新读取源文件，不把旧快照当作最新事实。

上述片段作为 **optional** 内容加入 Session Context Planner：源路径必须在仓库内，
拒绝 symlink、损坏索引和不匹配的 EP 状态；过大的 Snapshot 自动降为文件指针，
不自动生成摘要，也不写入 EP / ADR。ADR 导航来自可重建投影，**不等同于**
当前效力的最终验证；在决定或实施前仍须读取并校验原始 ADR / Constraint。
缺失来源只提供“不可用”提示，不阻止普通 Explore 工作。所有规范性 Requirement
Capsule 与 `before_mutation` 门禁保持原样。

## 非破坏性与验证

Bootstrap/upgrade 的 action 包括 `create_directory`、`create_file`、`register`、
`preserve`、`update_metadata`、`replace_file`、`update_manifest` 与 `conflict`。
任意 conflict 都阻止 apply。所有 managed path 拒绝 traversal、symlink、文件/目录
类型冲突和重复 owner。

验证入口：

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . validate --harness
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  validate --adapter codex
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  validate --adapter claude
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  validate --adapter portable
```

Core 总是验证；未指定 `--adapter` 时验证全部已安装 adapter。指定 adapter 时，只在
Core 之外验证所选 adapter，因此一个 Claude 或 Portable route 的问题不会伪装成
Codex route 问题。Codex `AGENTS.md` 保持 100 个物理行硬上限；项目 Skill 也由
manifest 记录各自的物理行预算。

## 可选运行时记忆降温

Core 1.6.0 增加两个版本化 memory 模块，但不创建配置、不默认开启降温。
显式配置、升级和回退边界见 [运行时记忆](../engineering-execution-plan/references/memory-runtime.md)。
