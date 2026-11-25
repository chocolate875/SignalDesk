# SignalDesk 协作指南

日常开发从 `develop` 创建短期分支，完成一个可独立审查的改动后向 `develop` 发起 Pull Request（PR）。`main` 是 GitHub 默认分支，保存经过验收、可发布的版本。

## 分支与合并方向

| 分支 | 从哪里创建 | 合并目标 | 用途 |
| --- | --- | --- | --- |
| `main` | 首次发布基线 | — | 正式版本与 `vX.Y.Z` 发布标签 |
| `develop` | `main` | `main` | 集成已通过审查的改动，统一验收 |
| `feat/<主题>`、`fix/<主题>` | `develop` | `develop` | 单项功能、常规缺陷修复 |
| `docs/<主题>`、`chore/<主题>` | `develop` | `develop` | 文档与工程维护 |
| `codex/<主题>`、`agent/<主题>` | 当前任务基线 | 仅本地 | Agent 临时工作区，独立于用于提交 PR 的正式分支 |
| `release/<版本>` | `develop` | `main` | 发布稳定期间需要并行开发时创建，集中处理验收修正 |
| `hotfix/<主题>` | `main` | `main` | 已发布版本的紧急修复 |

主题用小写英文单词和连字符，例如 `fix/chart-zoom`。同一需求的接口、界面与测试由一个 PR 交付。正式任务分支合并后可删除。

### 使用 Agent 时

从任务基线创建本地临时分支，例如 `git switch --no-track -c codex/chart-zoom develop`。保留中间提交供本机回看。结束工作后切回原分支，临时分支继续保存在本地，不设置 upstream。

需要提交 PR 时，由贡献者确认交付范围和推送权限，从最新目标分支新建正式任务分支（如 `fix/chart-zoom`），用 `git cherry-pick <已审阅的提交>` 挑选成果，再推送该正式分支。只推送明确指定的分支。仓库的 pre-push 钩子会拦截从临时工作区直接推送，以及将临时分支作为推送源或目标。`codex`、`agent` 及其子分支名在上游 GitHub 仓库均已保留给本地使用。

- **日常 PR** 采用 Squash and merge，以通过检查的中文 PR 标题作为合并提交标题。
- **发布 PR** 从 `develop`（或 `release/<版本>`）合入 `main`，采用 Create a merge commit，保留共同祖先。在验收通过的 `main` 提交上打版本标签。
- **回同步** 通过 `main` → `develop` 的 PR 合并发布及热修复，使用 Create a merge commit，确保下一次发布能识别已交付的提交。紧急修复进入正在验收的发布分支时，也同步该修复。

## 第一次参与开发

外部贡献者先在 GitHub 上 fork 仓库，把自己的 fork 克隆到本机。在克隆后的仓库根目录执行以下命令。`origin` 指向你的 fork，`upstream` 指向项目仓库。

```powershell
uv sync --frozen
git config --local core.hooksPath .githooks
git config --local commit.template .gitmessage
git remote add upstream https://github.com/chocolate875/SignalDesk.git
git fetch upstream
git switch --no-track -c feat/chart-range upstream/develop
```

将 `feat/chart-range` 换成本次任务的分支名。提交前用 `git diff --staged` 核对内容。执行 `git push -u origin feat/chart-range` 后，向 `chocolate875/SignalDesk:develop` 创建 PR。已有仓库写权限且直接克隆上游的成员，可从 `origin/develop` 建立任务分支。

用 Agent 开发时，先让它读取 [AGENTS.md](AGENTS.md)。提交者负责审阅最终差异，在 PR 里列出实际运行的验证，以及需要维护者重点检查的地方。测试行情、通知与 Agent 出站内容时使用合成数据。首次从 fork 提交的工作流可能需要维护者批准运行。

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

## 审查与合并条件

- `main` 和 `develop` 都通过 PR 更新，禁止强推和删除。合并前须与目标分支保持最新、解决所有审查讨论，并通过 GitHub Actions 的 **提交规范** 和 **工程验证**。若 GitHub 提示分支已落后，先将目标分支的最新提交同步到任务分支，再等待 CI。
- [CODEOWNERS](.github/CODEOWNERS) 指定 `@chocolate875` 审查全仓库，包括 CI 和规则文件。贡献者的 PR 需要维护者批准，推送影响已有审查的新改动后须重新审批。维护者可以通过 PR 自合，但同样需要通过两项 CI。默认合并标题取自中文 PR 标题。
- **提交规范** 检查中文 PR 标题与新增提交、误跟踪的忽略文件、本机技能目录历史，以及合入 `main` 的来源分支。**工程验证** 在 Windows 上运行 Ruff、最小字号审计、前端锁定依赖安装、生产构建和全量 pytest。
- CI 在 `pull_request` 事件下用只读令牌验证外部代码。同一 PR 推送新改动时，旧运行会取消。规则可在仓库的 [Rulesets](https://github.com/chocolate875/SignalDesk/settings/rules) 中查看。
