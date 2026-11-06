# 升级 Harness

先读取发行包的 `VERSION`，再检查目标仓库的 `docs/.engineering/harness.json`。RepoFoundry
产品版本、Harness schema、Core 版本、各 adapter 版本、激活协议版本和
Engineering Specs Catalog 版本是独立版本线；不要用 `spec update` 代替 Harness
migration。schema 迁移必须走 upgrade；schema 3 中追加 adapter 时，bootstrap
可以在预览中明确列出并记录 Core/adapter 组件迁移。

```bash
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  upgrade --to 0.15.4
python3 <repo-foundry-ai-dir>/scripts/foundryctl.py --repo . \
  upgrade --to 0.15.4 --apply
```

必须先展示 dry-run 结果。只有用户已要求实施升级且计划无 conflict 时才使用
`--apply`。versioned seed 只有在实际 SHA-256 等于 manifest 记录的
`installed_sha256` 时才可自动替换；修改过的 versioned seed 必须停止并要求人工
合并。`legacy-unversioned` seed 保持原字节，除非它已经与当前模板完全一致。apply
后必须报告更新路径和验证结果；验证失败由 CLI 回滚。详细兼容矩阵见
[Bootstrap 契约](bootstrap.md#版本与-harness-升级)。

0.15.3 将 Core 提升到 1.6.2、Codex 到 2.4.4、Claude 到 1.3.3、Portable 到
1.3.4。任务工作流先审阅候选 Requirement 触发条件再排除，并把原文交付与状态输出
分开。Router 算法、激活协议 2、Spec Catalog 1.9.0 和已有治理 profile 保持不变。
升级只替换来源摘要仍匹配的模板；不修改旧执行证据，也不把内部 epoch 状态当作
模型可见内容完整的证明。参见 [0.15.3 发布候选说明](../docs/releases/0.15.3.md)。

0.15.2 将 Core 提升到 1.6.1、Codex 到 2.4.3、Claude 到 1.3.2、Portable 到
1.3.3，以恢复 0.15.1 / Core 1.6.0 旧安装的官方升级兼容性。旧 seed 必须仍匹配
原 manifest 的安装摘要；生成文件有未知改动时 preview 报告 conflict，apply 拒绝
全部写入。不要修改旧 manifest 或绕过摘要验证。完整版本面与回归范围见
[0.15.2 发布候选说明](../docs/releases/0.15.2.md)。

0.8.0 及以上的显式升级还会补齐空的 Decision View registry、索引和投影目录。它不会
创建领域 View、修改 ADR、推断 retirement 或执行语义合并。大型 ADR corpus 的
健康度、View、exact capsule 与 consolidation preview 后续路由到
`engineering-execution-plan`。

0.8.2 为 schema 1.2 Checkpoint 增加 preview-first 的出生缺陷 seal 恢复：Git 只在
显式登记时证明 ancestor commit 首次引入精确路径与 bytes，随后把自校验 receipt
写入仓库；正常验证保持离线，并且只豁免该精确 payload mismatch，不改写 checkpoint。

0.8.3 允许 accepted replacement 后续继续被新的 accepted/current ADR supersede，
保留每一跳双向证据并拒绝 supersession cycle。Decision context 仍只消费链尾的
accepted/current ADR；旧 Decision View 进入 `review_required`，等待 owner 显式换锚点。

0.8.4 增加显式、无损、可逆的终态 ADR History Pack。只有 strict 且状态为
`rejected`、`retired` 或 `superseded` 的 live ADR 才能被选择；preview 先验证完整
候选 corpus，apply 才在锁内生成 content-addressed pack、删除已验证源文件并再次
全量验证，任何失败回滚原字节。逻辑 ADR、关系、证据和索引保持可解析；生命周期
修改或降级到不识别 pack 的版本前必须先完整 unpack。升级本身不会自动打包任何 ADR。

0.8.6 让 Harness 的 Design contract 校验复用同一 logical ADR resolver，因此
Design 引用已进入 History Pack 的终态 ADR 时仍能验证其身份和状态；pack 损坏、重复
身份或 current Design 引用 non-current ADR 继续失败关闭。

0.8.7 把同一 resolver 接入独立 `designctl new-design`、`status`、`validate`、
`mark-review-ready` 与 `approve` 路径。完整发行版中的直接 Design 操作与 Harness
校验现在对 live ADR 和 History Pack 使用同一逻辑语料；独立 Design skill 在没有
Execution Plan sibling 时仍保持 live-only 兼容模式。

0.8.8 区分当前架构输入与已封存的历史证据：terminal Design 仍会被新的 ADR 和
active ExecPlan 拒绝，但它后来进入 `abandoned`、`obsolete`、`superseded` 或
`rejected`，不会再使引用其已发布 revision 的 superseded/packed ADR 与
completed/cancelled ExecPlan 失效。

0.9.0 把 ADR 维护检测内置为确定性 `default-v1` 策略。`adr-maintenance`、`status`
与 `validate` 共享同一组可解释 hard indicators；Agent 在 ADR 生命周期/存储变更后及
Governed 交接前运行检查，外部定时 CI 使用同一命令的 `--check`。检测会区分当前
决策复杂度、View/Plan 上下文和终态物理归档，输出 typed preview action；它不会
自动 retire、supersede、合并、打包或执行任何 apply。数值越过 review/action 边界才
升级状态，三个及以上可机械验证的 strict 终态 live ADR 独立触发 `pack_history`。

## 0.15.4 distribution and Skill naming

The distribution version advances to 0.15.4 without changing Core 1.6.2 or
adapter template versions. It adds the independently discoverable
`architecture-design` capability and renames the document and governed-design
Skills to `design-documentation` and `governed-design`, respectively.
Existing schema-3 manifest component identities and locked Spec selections
remain unchanged. Historical pinned releases keep their original Skill paths;
the installer verifies a complete historical or modern layout, not a mix.
Preview and validate project upgrades; user-owned and modified generated files
must not be silently overwritten.
