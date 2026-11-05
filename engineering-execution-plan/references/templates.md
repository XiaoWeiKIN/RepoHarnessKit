# 制品路由与状态模型

## 制品选择

| 制品 | 适用条件 | 核心价值 |
|---|---|---|
| 线程内轻量计划 | 范围局部、上下文明确、无需恢复 | 降低记录成本 |
| Bugfix | 用户明确要求记录局部既有行为缺陷 | 保存问题闭环和验证证据 |
| Research | 决策相关事实不清，需要比较、实验或外部证据 | 由 `engineering-research` 把未知转成可追溯 corpus |
| Synthesis | Research 已具备决策输入 | 作为两个 Skill 之间的有界、sealed 契约 |
| Design Package | 已建立证据需要转成系统边界、组件、接口、数据与失败语义 | 由 `governed-design` 管理单文件或多文档设计、评审与 approved revision |
| ADR | 架构级选择会形成长期约束 | 保存选择、后果和确认方式 |
| ExecPlan | 已知方向需要跨模块、多里程碑或跨会话实施 | 让无历史会话的 Agent 可执行 |

验收项数量只能作为复杂度信号。关键问题依次是：

1. 是否存在会改变路线的未知？
2. 是否存在影响长期边界且逆转成本较高的选择？
3. 工作中断后是否需要持久、完整的执行上下文？

```mermaid
flowchart TD
    W["工程工作"] --> U{"决策相关未知？"}
    U -->|"是"| R["engineering-research<br/>Research + Synthesis"]
    U -->|"否，记录理由"| A
    R -.-> D{"需要显式技术设计？"}
    D -->|"是"| DD["governed-design<br/>Design Package"]
    DD --> A
    D -->|"否"| A{"架构级选择？"}
    A -->|"是"| ADR["Proposed ADR → 明确决定"]
    A -->|"否，记录理由"| E["ExecPlan 或轻量计划"]
    ADR --> E
    W --> B{"明确要求记录局部既有缺陷？"}
    B -->|"是且范围局部"| BF["Bugfix"]
```

## 路由规则

默认 Research：

- 现有行为、约束或失败边界不清。
- 需要比较库、协议、架构、迁移方案或成本。
- 需要 prototype、spike、benchmark、trace 或真实系统观察。
- 结论涉及公共契约、安全、可靠性、数据或高逆转成本。

需要新建、接管或维护 Research 时切换到独立的
`engineering-research` Skill。本 Skill 从 concluded Research 的文件契约开始，
不负责证据采集或 corpus authoring。

需要创建、评审、修订、放弃或替代 Design Package 时切换到独立的
`governed-design` Skill。本 Skill 只读消费其版本化 repository contract；
不得通过 `epctl` 改变 Design 生命周期。

可跳过 Research：

- 当前 accepted ADR 和代码事实已覆盖输入。
- 权威标准或用户已固定方案。
- 工作局部、可逆，没有会改变执行路线的未知。

跳过必须在 v2.2+ ExecPlan 中记录具体 `research_gate_reason`。

创建 ADR：

- 至少存在两个可信选项；并且
- 影响公共 API/schema/事件/配置、跨系统边界、长期技术约束、迁移成本、安全、数据一致性、可靠性或部署拓扑。

否则在 ExecPlan Decision Log 记录局部取舍，并填写
`architecture_decision_gate_reason`。随后仍要判断现有 ADR / Design Doc 是否适用；
只有确实没有 architecture input 时才填写 `architecture_compliance_reason`。

使用 Bugfix：

- 用户明确要求持久记录。
- 目标是恢复既有行为。
- 影响局部，不需要 Research、ADR、公共契约变更或任务拆分。

普通“帮我修 bug”直接复现、修复和验证。Bugfix 变复杂后升级为满足 Gate 的 ExecPlan。

## 状态机

### Research

```mermaid
stateDiagram-v2
    [*] --> active
    active --> blocked
    blocked --> active
    active --> active: "review-ready ↔ new Round"
    active --> concluded: "Research Owner 明确批准"
    active --> cancelled: "Research Owner 明确批准 + 原因"
    blocked --> cancelled: "Research Owner 明确批准 + 原因"
```

`review_ready` 是 maturity，不是结束状态；第一版之后可以在同一个 Research
中创建新 Round。`concluded` 除了没有 open Research Question、open blocker
或 REQUIRED 标记，还必须记录 Research Owner 的明确授权。`cancelled` 同样
需要授权和原因，不能满足 Gate。

### ADR

```mermaid
stateDiagram-v2
    [*] --> proposed
    proposed --> accepted
    proposed --> rejected
    accepted --> superseded
```

Agent 可以起草 proposed ADR。accepted/rejected 必须记录明确 Decision Owner；正文封存后不可修改。superseded 必须指向更新的 accepted ADR。

### ExecPlan

```mermaid
stateDiagram-v2
    [*] --> active
    active --> blocked
    blocked --> active
    active --> completed
    active --> cancelled
    blocked --> cancelled
```

`completed` 要求验收完成、Task 终态、无 open blocker、复盘完整；v2.3+ 还要求
`verified_revision` 和至少一个 `verification_evidence`。

### Task

```mermaid
stateDiagram-v2
    [*] --> todo
    todo --> in_progress
    todo --> cancelled
    in_progress --> blocked
    blocked --> in_progress
    in_progress --> done
    in_progress --> cancelled
    blocked --> cancelled
```

### Bugfix

```mermaid
stateDiagram-v2
    [*] --> open
    open --> in_progress
    open --> cancelled
    in_progress --> blocked
    blocked --> in_progress
    in_progress --> fixed
    in_progress --> escalated
    in_progress --> cancelled
    blocked --> escalated
    blocked --> cancelled
```

`fixed`、`escalated`、`cancelled` 移入 completed；`escalated` 必须链接真实 ExecPlan。

## 机械不变量

- 编号在仓库锁内分配，扫描 active、completed、索引和高水位后取最大值 +1。
- 允许故障跳号；删除文件后也不复用编号。
- `RESEARCH.md`、`DECISIONS.md`、`PLANS.md`、`BUGFIXES.md` 的托管区可由 `reindex` 重建，人工区必须保留。
- 新 ExecPlan 使用 `schema_version: "2.8"`，明确 Research Gate、Architecture
  Decision Gate、Architecture Compliance、ADR 依赖闭包、Design Doc 引用、可选
  架构入口和零到多个 `required_benchmark_scenarios`，并增加
  `adr_constraint_refs`、`adr_evidence`、`design_evidence` 与
  `Architecture Compliance Matrix`。
- Research Gate 只接受 valid + concluded Research；Decision Gate satisfied 和
  active Compliance input 只接受 valid + accepted + current ADR。
- manifest-bearing Research 还必须具有 sealed、摘要一致且文档完整的受支持 manifest；无 manifest 的旧包继续走兼容路径。
- Research Gate 可以为 `not_required`，但必须有理由且不能同时保留 Research 引用。
  Architecture Decision Gate 为 `not_required` 时仍可保留适用的既有 ADR；
  Architecture Compliance 为 `not_applicable` 时才要求 architecture inputs 为空。
- ADR 引用的 Research 必须同时进入 ExecPlan。
- ADR 的 `depends_on` / `amends` 必须无环，且传递闭包全部进入 ExecPlan；
  ADR 引用的 Design Docs 也必须进入 ExecPlan。
- schema 1.1 Design 的 typed dependency 必须无环且传递闭包全部进入 ExecPlan；
  completed EP 必须为每个依赖固定有效 approved revision evidence。
- schema 1.2/1.3 ADR 使用稳定 `C-NNN` constraints；局部 amendment 必须列出
  `amends_constraints`，active EP 不能漏掉命中其 constraint 的 current amendment。
- v2.6–2.8 EP 的结构化 constraint 集、ADR payload digest 和 Compliance Matrix 必须
  精确一致；Design Docs 不得覆盖 ADR。
- sealed Synthesis、decided ADR 和 Checkpoint 使用 Markdown body SHA-256 检测篡改。
- 新 Checkpoint 记录 `repository_revision`；completed v2.3+ EP 记录实际通过验证的
  revision 和证据引用，所有 archived v2.3+ EP 使用 `archive_sha256` 封存全文。
- completed v2.5+ EP 对每个必需 Benchmark Scenario 恰好接受一个 passed sealed
  Run；所有 Run 绑定同一 `verified_revision`，未声明或重复 Scenario evidence
  都会阻止归档。
- Task 使用 `parent_id: EP-NNN` 和 `depends_on: ["TASK-NNN"]`。
- Checkpoint 只封存已完成进度和已关闭 blocker；开放工作留在根计划。
- Frontmatter 仅支持简单标量和 JSON 风格一级字符串数组。
- `blocked` 与 open blocker 必须双向一致。

`archive` 是物理迁移操作，不是状态。ADR 例外：路径稳定，所有状态都留在 `docs/adr/`。

## 旧版兼容

- 继续读取旧 `ep-NNN_name.md` 和 `README.md + progress.md + tasks/`。
- v2.0–v2.7 `EXECPLAN.md` 保持可读、可验证、可归档；不要静默升级。
- v2.1 仍可 checkpoint。v2.0 建立 checkpoint 前显式迁移到至少 v2.1，并补 `Current Snapshot`。
- 新建统一使用 v2.8 `ep-NNN_slug/EXECPLAN.md`。
- 修改旧制品时保留原格式；用户要求迁移时先建立可恢复点，再合并当前事实与历史。
- 旧 `docs/tech-debt-tracker.md` 继续读取；新仓库使用 `docs/exec-plans/tech-debt-tracker.md`。
- `epctl` 中旧 Research 生产命令暂时保留，但新 Research 的主路径是
  `engineering-research`；不要把兼容命令解释成新的职责归属。
