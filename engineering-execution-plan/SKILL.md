---
name: engineering-execution-plan
description: 创建和维护 ADR、ExecPlan、Task、Checkpoint、Bugfix 与 ADR 历史。用于明确的工程治理或可恢复交付；普通编码、局部修复和代码解释不自动创建制品。
---

# Engineering Execution Plan

撰写、改写或评审文档正文前，读取并应用 [受控技术写作](references/controlled-writing.md)。
先用通用规则，再用当前制品对应的小节；保留现有语言选择和生命周期门禁。

把需要持久跟踪的工程决定与交付组织成可追溯、可恢复、可验证的仓库制品。
方向已明确时推进实现和验收；Owner 的决定与证据完整性由各自门禁持有。

## 选择工作深度

Explore 的有界可逆工作和 Build 的生产修改默认使用线程内契约。只有公共契约、
安全、数据、不可逆迁移、可靠性声明、发布、长期决定、跨会话恢复，或用户明确要求
持久制品时才进入对应治理流程。Explore/Build 不为“没有触发 Research”创建跳过制品。

| 需要的结果 | 路由 |
|---|---|
| 普通实现、局部修复、一次性实验 | 直接完成，不自动创建 EP 或 Bugfix |
| 用户要求持久记录的局部既有行为缺陷 | Bugfix |
| 可复用或参与验收的测量证据 | `engineering-benchmark` |
| 会改变工程决定且尚未解决的事实未知 | `engineering-research` 或兼容证据生产者 |
| 普通架构、组件、接口与实现合同文档 | `design-documentation` |
| 用户要求 DD-NNN、Design Package、批准或修订受治理设计 | `governed-design` |
| 有可信替代方案且影响长期边界的选择 | ADR |
| 需要可恢复交付、跨模块里程碑或实施已接受决定 | ExecPlan |
| 项目 Harness 初始化、升级或 Spec 安装 | `repo-foundry-ai` |

局部易逆转的实现选择可记录在 EP Decision Log。已经创建 EP 时，如 Research、
新 ADR 或 Architecture Compliance 不适用，记录具体 Gate 理由；跳过新决定不代表
忽略既有架构约束。

## 按任务读取契约

把 `<skill-dir>` 解析为本 skill 所在目录，使用
`python3 <skill-dir>/scripts/epctl.py --repo <repo> <command>`。
`status [--json]` 查看当前状态，`--help` 查询参数；只读取当前任务对应的说明：

| 当前操作 | 说明 |
|---|---|
| 判定制品、状态机或兼容输入 | [templates.md](references/templates.md) |
| 起草、决定、修订或替代 ADR | [adr.md](references/adr.md) |
| ADR 维护、Decision View、capsule 或记忆检索 | [adr.md](references/adr.md)；[记忆复核](references/memory-review.md)；[检索预览](references/memory-context.md)；[运行时降温](references/memory-runtime.md)；[引导式维护预览](references/memory-maintenance.md) |
| 创建或接手 ExecPlan、维护 Task 与验收 | [template.md](references/template.md) |
| 向负责人解释进展、取舍或验收依据 | [handoff.md](references/handoff.md) |
| 消费 Research / Synthesis | [research.md](references/research.md) |
| 使用 sealed Benchmark 验收 | [benchmark.md](references/benchmark.md) |
| 建立 Checkpoint、压缩或恢复历史 | [checkpoints.md](references/checkpoints.md) |
| 完成计划、处理摘要、CI 或 revision 证据 | [integrity.md](references/integrity.md) |
| 记录或升级 Bugfix | [bugfix.md](references/bugfix.md) |
| 用户要求共同权衡，或存在影响决定的实质取舍 | [collaboration.md](references/collaboration.md) |
| 命令示例、历史兼容操作 | [commands.md](references/commands.md) |

使用 CLI 分配 ID、维护索引、迁移状态和封存证据；`init` 只补缺失执行治理目录。
不要手工猜编号、复用高水位或改写封存摘要。专业生产者可独立安装，消费者只读取
仓库文件契约；本 skill 不持有 Research、Benchmark 或 Design 的写入生命周期。

## 决定与输入

- Agent 可以比较方案并起草完整 proposed ADR。只有用户或 Decision Owner 对具体
  ADR outcome 的明确接受/拒绝，才运行 `decide-adr`。当前会话已有精确授权时直接
  执行；一般实施授权、候选偏好、沉默和“继续研究”都不能代替该决定。
- 一份 ADR 记录一个原子决定。保留 Decision Statement、稳定的 C-NNN constraints、
  Confirmation、后果和 Revisit Triggers；关系与修改规则由 ADR 契约约束。
- Research Gate 只接受 concluded 证据与有效 seal；active 或 cancelled 不满足 Gate。
  在下游复述影响实施的结论、置信边界、负面证据和剩余未知。
- Design 的创建、批准、修订和替代属于 `governed-design`。未批准 revision 可供
  讨论，但 EP 完成必须固定全部依赖的有效 approved revision evidence。
- Architecture Input Set 包含适用的 current ADR closure 与 Design 输入；用
  Compliance Matrix 将 ADR-NNN#C-NNN 映射到实现与验证。历史 compatibility
  只按引用契约处理，不伪造旧 Owner 授权。
- 只对用户拥有且会实质改变范围、迁移或验收的未知进行校准。信息充分时直接起草
  或实施；局部技术细节从仓库取证，不逐项索取确认。

## 推进与完成

根 EXECPLAN.md 应足以让没有历史会话的 Agent 接手：明确目的、当前事实、路径、
独立可验证的里程碑、恢复方式和剩余阻塞。历史、完整日志和测量输出按需归入
Checkpoint / artifacts，不能成为继续工作的默认阅读前置。

面向负责人交接时，先说明行为变化、证据和未完成边界，再给准确下一步。按
[handoff.md](references/handoff.md) 从现有制品生成所需阅读视图；沿用用户语言，
解释术语，保留约束原文与证据入口。摘要不新增状态、审批或必须维护的文档。

按 `status` 给出的 working_set、scope 与 completion 信号维护计划。规模超限先
收敛当前事实和封存历史，不把长度、无活动时间或 ready_to_archive 当作完成证明。
对**当前正在维护的 active EP**，当 `working_set` 为 `checkpoint_recommended`
或 `checkpoint_required`，或在里程碑/交接边界需要收敛历史时，
自动调用 `epctl auto-checkpoint EP-NNN --apply`；命令自行判断阈值并仅封存已完成
Progress 和已解决 Blocker 等安全历史，不要求用户手写 checkpoint 参数。
若返回 `skipped`，按 reason 保留原文并报告，绝不强行编造 Snapshot。
普通 Explore/Build 工作不触发此命令。
Task 保持有限范围和独立完成边界；技术未知先取证，只在缺权限、外部状态、人类
决定或真实安全/兼容边界时保留 blocker，解除后恢复推进。

在已授权范围内持续完成实现、相关检查和失败修正。Benchmark 的失败或无结论也
保留 sealed evidence；修复后创建新 Run，不能按已看到的结果降低 Scenario 阈值。

完成 EP 时：

1. 全部 Validation 与 Task 有真实结果，没有 open blocker，填写 Outcomes & Retrospective。
2. 取得实际验证的 revision 与 evidence。预声明的每个 Benchmark Scenario 恰好对应
   一个同 revision 的 passed sealed Run；Design 输入有完整的批准 revision pin。
3. 运行 `adr-maintenance` 和 `validate`，再用 `archive-ep --outcome completed`
   记录 verified revision 与 evidence。无关 ADR 维护建议不阻止 EP 归档，也不授权改 ADR。

不完整计划继续推进，或在明确停止时以原因归档为 cancelled。批准请求应针对已准备好
的具体决定；不要在第一版实现后因惯例暂停。ADR lifecycle/storage 变化后及 Governed
交接前运行 `adr-maintenance`，其 typed actions 只授权准备预览。

accepted ADR、sealed Checkpoint 和 archived EP 的证据不能原地改写。正常验证保持
离线；出生即错误的 seal 只能走已证明精确原始字节的恢复契约。未知 author/owner
使用 `Unassigned`，不从 Git committer 猜测，也不把作者身份当作批准权限。

只有用户明确要求工程分享时才使用 `engineering-case-study`；EP 完成本身不触发文章。
端到端调用见 [Prompt 示例](references/examples.md)，多架构输入见
[Architecture Input Set 示例](examples/architecture-input-set/README.md)。
