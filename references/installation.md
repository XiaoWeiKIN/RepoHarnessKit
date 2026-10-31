# 安装或升级 RepoHarnessKit

首次安装和后续升级使用同一条命令：

```bash
curl -fsSL https://raw.githubusercontent.com/XiaoWeiKIN/RepoHarnessKit/main/install.py | python3 -
curl -fsSL https://raw.githubusercontent.com/XiaoWeiKIN/RepoHarnessKit/main/install.py | python3 - --host claude
```

安装器选择最新稳定 GitHub Release，把 tag 固定到 commit，记录归档 SHA-256，
验证完整暂存包后原子切换当前版本，并暴露兼容保留的 `repofoundry` CLI。默认只为检测到的
Agent host 注册发现入口；`--host codex` 显式注册 Codex，`--host claude` 在
`$CLAUDE_CONFIG_DIR/skills/repo-foundry-ai`（未设置时为
`~/.claude/skills/repo-foundry-ai`）注册 Claude Code，
`--host none` 只安装产品中立的 CLI 且不改动既有宿主注册。`--host auto` 会注册
检测到的全部受支持宿主。`--version MAJOR.MINOR.PATCH` 固定版本，重复安装同一版本为
no-op，旧的不可变 release 和被替换的非托管宿主目录保留用于恢复。宿主注册只
提供个人 Skill 发现；项目级 Skill 必须由目标仓库的 adapter bootstrap 注册。

发行包升级不扫描或修改项目仓库。安装新版工具后，目标项目仍必须单独执行
`repofoundry --repo PATH upgrade --to VERSION` 预览 Harness migration，并在用户
明确要求后加 `--apply`。需要审查远程脚本时，先下载 `install.py`、阅读内容，
再用 `python3 install.py` 执行。

发行包中的项目 Skill 模板使用 `SKILL.md.template`，bootstrap 才将其写成项目内的
`SKILL.md`。个人发现目录只暴露根 skill 和七个专业 skill，避免模板参与自动选择。
