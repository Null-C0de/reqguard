# 更新日志

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 变更

- `references/ground-truth.yaml`：10 条样本已于 2026-11-17 由人工逐条确认，`status` 由 `draft` 改为 `human-confirmed`，并记录 `confirmed_by` / `confirmed_at`。**评估本身仍未执行**，`results.md` 保持「未执行」。
- CI：`actions/checkout`（v4.4.0）与 `actions/setup-python`（v5.6.0）固定到 commit SHA，消除 tag 被移动带来的供应链风险。
- 仓库：`main` 启用分支保护（必须通过 `CI / validate` 检查、必须经 PR 合并、禁止强推与删除）。

### 说明

- ground-truth 确认不等于评估完成。对外引用漏报率仍要求样本数 ≥20 且 A/B 两组真实运行，见 `results.md` 第 1 节。

## [0.1.0] - 2026-11-10

首个公开版本：一个通用的「需求文档 vs 代码实现」覆盖检查 Skill，附带可复现的评估物料。**本版本尚未执行正式评估，`results.md` 中没有任何指标数字。**

### 新增 — 检查逻辑

- `SKILL.md`：角色定义（严格检查器，不做代码质量评审）、输入约定、七步工作流（建 MUST 清单 → 风险分级 → 抽判据 → 定位证据 → 三态判定 → 本地实现扫描 → 输出）、九条硬约束、九节报告结构、输出前自检、禁止清单、边界与调用示例。
- 证据强度分级 E1 / E2 / E3：**只有 E1（可反驳的实现证据）能支撑「符合」**；函数存在、中间件被定义、mock 路径被调用等 E2 证据一律不得判符合。
- 「不符合」拆为「违规实现」与「确认缺失」两种形态；后者必须声明检索范围。
- 需求判据必须从原文抽取，禁止自编；判不了的条款归入「待人工定级」，不允许模型硬猜风险等级。

### 新增 — 风险规则

- `risk-rules.yaml`：高风险 7 类（鉴权、密钥管理、授权、加密、支付、审计、数据隔离）、中风险 5 类（状态流转、幂等、异常回滚、并发、超时重试）、低风险 4 类（UI 文案、显示格式、排序、空状态），共 16 条可配置条款。
- 证据策略（高风险须 E1 + 三元组）、`mock / fake / stub / hardcode / TODO` 扫描词表、报告章节顺序、自定义覆盖规则与降级警示。

### 新增 — 参考文档

- `references/requirement-template.md`：需求写法模板（字段、反例改写、禁用词、编号拆分、提交前自检）。
- `references/report-template.md`：九节可填写报告模板与填写规则。
- `references/eval-protocol.md`：A/B 对比协议、体面版 A 组提示词、指标定义（漏报率主口径与严格口径、误报率、无法判定率、证据定位准确率）、统计口径、样本规模与反作弊条款。
- `references/design-rationale.md`：Skill 为什么不是模型也不是程序、四个作用点、E1–E3 如何切断「本地能跑即合规」、设计取舍与已知失效模式。
- `references/ground-truth.yaml`：10 条样本的评估预期（**草案，未经人工确认**），含匹配约定与人工确认清单。

### 新增 — 评估脚本

- `scripts/run_eval.py`：仅依赖 Python 3 与 PyYAML。
  - `--check`：校验评估物料自洽（YAML 可解析、字段齐全、`risk_rule` 指向真实规则、`dataset_size`/`composition` 与实际一致、ground-truth 的 `snippet` 与 `match_tokens` 确实存在于对应代码），不输出任何指标；
  - `--self-test`：解析器自检（三态归一化、表格抽取、证据切分、指标计算）；
  - `--prompts <run_dir>`：从 `references/eval-protocol.md` 原文抽取 A/B 提示词并落盘，记录协议与提示词的 `sha256`；同时校验 A 组未被弱化、未夹带 ReqGuard 的机制（脚本不保留任何提示词副本）；
  - `--score <run_dir>`：对 A1–A3 / B1–B3 报告计算逐条明细、五项指标与 A/B 差值，输出 `score.md` / `score.json`；缺失数据时以退出码 2 拒绝输出全 0「成绩」。
- 指标只统计 MUST；多次运行取中位数；无对应样本时显式打印 `n/a` 并附脚注，避免把「没有样本」误读成 0。

### 新增 — 测试集

- `testset/requirements.md`：10 条需求（MUST 9 / SHOULD 0 / MAY 1），覆盖密钥硬编码、接口无 token、MD5 存密码、支付 mock、回调不验签、权限缺 nurse/approver、订单状态缺 WITHDRAWN/EXPIRED、重复提交无幂等、无审计、UI 国际化；每条含 2–3 条验收判据。
- `testset/code/`：6 个 TypeScript 文件，语法合理、可通过 `tsc --strict --noEmit`，但存在 9 处「本地能跑但不合规」的隐性坑，另有 1 条合规对照（R-10）。
- 已知缺口：缺少「合规的 MUST 对照样本」，因此 MUST 维度上的误报率暂时无法被有效度量。

### 新增 — 结果与记录

- `results.md`：评估状态为**未执行**；含运行信息模板、指标表模板、结果解读纪律与已知局限。所有数字位置保持「待填」，未写入任何未经运行的结果。

### 新增 — 社区与自动化

- `LICENSE`（MIT，ReqGuard contributors）、`.gitignore`、`.editorconfig`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`requirements.txt`（仅 PyYAML）。
- `.github/workflows/ci.yml`：push / pull_request 触发，校验 YAML 与 Markdown 结构、跑评估脚本的冒烟检查（`--check` / `--self-test`）、检查必备文件齐全、阻止提交伪造的评分产物。
- `.github/ISSUE_TEMPLATE/`（bug / feature / sample proposal）与 `.github/PULL_REQUEST_TEMPLATE.md`。

### 说明

- **没有**发布到 PyPI，也没有 `setup.py` / `pyproject.toml`：本项目不是 Python 包，`requirements.txt` 只服务于评估脚本。
- 对外引用任何漏报率数字前，必须先把评估集扩到 ≥20 条并由人工确认 ground-truth。

<!-- 发布前：把下面两条链接里的 OWNER 替换为实际 GitHub 组织/用户名 -->
[Unreleased]: https://github.com/OWNER/reqguard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/reqguard/releases/tag/v0.1.0
