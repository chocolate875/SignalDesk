# SignalDesk 协作指南

日常开发从 `develop` 创建短期分支，完成一个可独立审查的改动后向 `develop` 发起 Pull Request（PR）。`main` 是 GitHub 默认分支，保存经过验收、可发布的版本。

## 分支与合并方向

| 分支 | 从哪里创建 | 合并目标 | 用途 |
| --- | --- | --- | --- |
| `main` | 首次发布基线 | — | 正式版本与 `vX.Y.Z` 发布标签 |
| `develop` | `main` | `main` | 集成已通过审查的改动，统一验收 |
| `feat/<主题>`、`fix/<主题>` | `develop` | `develop` | 单项功能、常规缺陷修复 |
| `docs/<主题>`、`chore/<主题>`、`codex/<主题>` | `develop` | `develop` | 文档、工程维护或智能体协作任务 |
| `release/<版本>` | `develop` | `main` | 发布稳定期间需要并行开发时创建，集中处理验收修正 |
| `hotfix/<主题>` | `main` | `main` | 已发布版本的紧急修复 |

主题用小写英文单词和连字符，例如 `fix/chart-zoom`。同一需求的接口、界面与测试由一个 PR 交付。短期分支合并后可删除。

- **日常 PR** 采用 Squash and merge，以通过检查的中文 PR 标题作为合并提交标题。
- **发布 PR** 从 `develop`（或 `release/<版本>`）合入 `main`，采用 Create a merge commit，保留共同祖先。在验收通过的 `main` 提交上打版本标签。
- **回同步** 通过 `main` → `develop` 的 PR 合并发布及热修复，使用 Create a merge commit，确保下一次发布能识别已交付的提交。紧急修复进入正在验收的发布分支时，也同步该修复。

## 第一次参与开发

在克隆后的仓库根目录执行以下命令，启用本仓库的提交模板和中文标题检查。钩子使用项目的 `uv` 环境。

```powershell
uv sync --frozen
git config --local core.hooksPath .githooks
git config --local commit.template .gitmessage
git fetch origin
git switch --no-track -c feat/chart-range origin/develop
```

将示例中的 `feat/chart-range` 换成本次任务的分支名。提交前用 `git diff --staged` 核对内容。推送自己的任务分支后，在 GitHub 选择 `develop` 作为 PR 的 base。

## 中文提交规范

提交和 PR 标题使用 `类型(范围): 中文摘要`。半角冒号后留一个空格，范围可省略。摘要用中文动词说明行为及对象，保留必要的英文模块名或协议名。正文按需填写，空一行后用中文交代原因、影响和验证结果。工单引用可另起一行，如 `Refs: #123`。

| 类型 | 使用场景 |
| --- | --- |
| `feat` / `fix` | 新增功能 / 修复缺陷 |
| `refactor` / `perf` / `style` | 重构 / 性能改进 / 格式调整 |
| `docs` / `test` | 文档 / 测试 |
| `build` / `ci` / `chore` | 构建和依赖 / 自动检查 / 仓库维护 |
| `revert` | 撤销改动，在正文引用被撤销的提交 |

范围使用小写模块名，如 `chart`、`forecast`、`agent`。不兼容改动可在冒号前加 `!`，并在正文说明迁移方式。一条提交对应一个可以单独解释和撤销的改动。

```text
fix(chart): 修复切换标的后缩放范围丢失的问题

切换标的时按日期恢复已选区间。已验证两个交易历史长度不同的标的。
```

```text
docs: 补充首次启动说明
chore(release): 发布 0.2.0 版本
```

本地钩子和 GitHub CI 使用同一校验脚本，检查类型、标点和摘要是否含汉字。审查人确认中文表意清楚、正文与改动一致。规则适用于新提交，旧版本的提交保留原文。

## GitHub 首次上线

1. 仓库管理员创建空的 GitHub 仓库。核对仓库可见性、成员和写入权限。确认发布后，在本地设置 `origin`，仅推送两个长期分支。

   ```powershell
   git remote add origin https://github.com/OWNER/SignalDesk.git
   git push -u origin main develop
   ```

2. 将默认分支设为 `main`。在 **Settings → General → Pull Requests** 启用 squash 和 merge commit，两者的默认提交信息均选 **Pull request title**。
3. 首次推送触发 Actions 后，在 **Settings → Rules → Rulesets** 为 `main` 和 `develop` 启用分支保护。要求通过 PR、至少一位其他成员批准、解决审查讨论，并将 **提交规范**、**工程验证** 设为必需检查。禁止强推和删除长期分支，允许发布流程使用合并提交。
4. **提交规范** 检查 PR 标题、该 PR 引入的每条提交和技能目录历史。首次推送从协作基线 `8cd4ba0` 起检查新增提交，后续推送从上次分支位置起检查。**工程验证** 在 Windows 上执行 Ruff、pytest、最小字号审计、锁定依赖安装和前端生产构建。

本地 `.agents/skills/` 供个人工具使用，Git 忽略该目录。共享的 UI、接口和数据安全约定见 [AGENTS.md](AGENTS.md)。首次发布仅使用上述明确列出的分支，尤其避免镜像推送本机归档引用。
