# ReqGuard

> 通用的「需求覆盖检查」Skill：把需求文档逐条映射到代码证据，输出 `符合 / 不符合 / 无法判定` 的覆盖报告，**优先暴露高风险漏报**。

一句话定位：**它不判断代码写得好不好，只判断需求到底满足了没有、证据在哪。**

## 1. 项目简介

ReqGuard 解决的是交付流程里最常见的一类失效：**把「本地能跑」当成「规范已满足」**。

典型现场：需求文档明确要求「密钥不得硬编码，必须走配置」；实现方（人或 AI）在代码里写死了密钥，因为本地跑得通，检查方看了一眼运行结果就判定「已覆盖」。上线前被打回，返工重来。

造成这个结果的不是能力不足，而是**检查方式缺少举证结构**——自由对比天然倾向于"看起来没问题"。ReqGuard 把检查从「自由对比」改成「逐条举证」：

- 每条 MUST 需求必须落到代码证据，否则不许写「符合」；
- 高风险条款（鉴权、密钥、权限、加密、支付、审计、数据隔离）强制要求 `文件 :: 函数 :: 片段` 三元定位；
- 找不到证据只能判「无法判定」，不允许用运行结果替代证据。

适用范围不绑定任何单一开发模式：AI 辅助生成的代码复核、外包/供应商交付验收、开源项目验收、传统软件交付的验收环节，都可以用。

## 2. 核心指标

核心量化指标是**漏报率**（该判"不符合"的条款被放过）。

A 组 = 一份"正常的、体面的"通用提示词（不加载本 skill）；B 组 = 加载 `SKILL.md` 后的调用指令。两组喂同一份需求文档与同一份代码。

| 组别 | 提示词 | 漏报率 ↓ | 误报率 ↓ | 无法判定率 ↓ | 证据定位准确率 ↑ |
| --- | --- | --- | --- | --- | --- |
| A 组 | 通用提示词（见 `references/eval-protocol.md`） | 待填 | 待填 | 待填 | 待填 |
| B 组 | 加载 ReqGuard `SKILL.md` | 待填 | 待填 | 待填 | 待填 |

> **对外引用的数字必须来自 ≥20 条测试集。** 仓库当前 `testset/` 为 10 条起步规模，**只用于跑通流程与验证报告结构，不具备统计意义**，不得对外引用。结果记录见 [`results.md`](results.md)，评估口径见 [`references/eval-protocol.md`](references/eval-protocol.md)。

## 3. 快速开始

```bash
git clone <your-repo-url> reqguard
cd reqguard
```

1. 把 `SKILL.md` 加载到你的 agent（支持 Skill / 自定义指令的宿主，例如 Claude Code、DSH 等），并让 `risk-rules.yaml` 与 `references/` 一并可读；
2. 准备**你自己的**需求文档（格式参考 `references/requirement-template.md`）；
3. 发出检查指令（见下一节）。

无需安装依赖。`scripts/run_eval.py` 只在复现漏报率时才需要（见第 6 节）。

## 4. 使用方式

**使用者准备的是「自己的需求文档 + 自己的代码仓库」。** 不需要使用本项目的 `testset/`，也不需要写 `ground-truth`——这两个文件只服务于「评估 skill 本身」。

### 4.1 加载

把 `SKILL.md` 作为系统提示 / skill 定义加载，告诉 agent：完成检查前必须先读 `SKILL.md` 全文，并同时提供 `risk-rules.yaml` 的路径（不提供则使用默认规则）。

### 4.2 发出调用指令

```
请使用 reqguard 检查本次交付的覆盖情况：
- 需求文档：docs/requirements.md
- 代码：src/（重点 src/api/、src/services/）
- 风险规则：risk-rules.yaml（默认）
- 检查范围：仅本次改动的模块
输出：按 SKILL.md 报告结构，高风险未通过项置顶。
```

指令里**不需要**解释判定标准——标准写在 `SKILL.md` 里。你只需要说清三件事：需求文档在哪、代码在哪、范围多大。

### 4.3 读输出报告

报告固定九节，按这个顺序读：

1. **概览**——先看"高风险未通过数"和一句话结论，决定能不能放行；
2. **高风险未通过项（置顶）**——这些是发布前必须处理的；
3. **中风险 / 低风险**——排期处理，不阻断；
4. **全部 MUST 明细表**——逐条核对判定与证据，这一节不允许省略任何 MUST；
5. **待人工定级项**——规则归类不了的需求，需要人给个等级；
6. **疑似本地实现清单**——`mock / hardcode / stub / TODO` 命中点，涉及支付、鉴权、密钥、加密、权限、审计时**必须人工确认**；
7. **SHOULD / MAY 清单**、**检索范围与限制**——了解边界。

判断报告是否可信，看两件事：每条"符合"能不能点出 `文件 :: 函数 :: 片段`；每条"无法判定"有没有写清卡在哪。

## 5. 与其他项目的差异

**适用场景不同，不构成"全面优于"。**

- 相对**需求追溯矩阵类工具**：追溯矩阵擅长"需求 ↔ 用例 ↔ 提交"的链接与统计，用于过程管理与审计留痕；ReqGuard 不做全生命周期追踪，只做一次交付前的"条款是否真正落地"判定，并把"高风险自动分级 + 高风险强制证据定位 + 本地 mock/hardcode 标记"压进同一条推理路径。
- 相对**PR 级自动检查器 / 静态规则扫描**：它们适合在 CI 里做持续门禁、拦截已知模式；ReqGuard 不替代 CI 门禁，也不做代码规范检查，它面向"需求文档"这一侧，处理的是判据来自自然语言、需要跨文件追调用链的场景。
- 相对**通用的"让 AI 再对比一遍"**：那类做法没有强制结构与强制举证，容易在"看起来能跑"处收敛；ReqGuard 用硬约束把结论逼到"要么给证据，要么承认无法判定"。

如果你的场景是持续集成门禁、性能回归、代码风格治理，ReqGuard 不是合适工具。

## 6. 评估复现

> `testset/` 仅用于评估 skill 本身是否有效，**不是日常使用依赖**。

只有想复现「漏报率」数字的人才需要跑测试集与 `scripts/run_eval.py`。日常检查自己的项目，跳过本节。

```bash
pip install -r requirements.txt
python scripts/run_eval.py --check      # 1. 物料是否自洽（不出数字）
python scripts/run_eval.py --self-test  # 2. 解析器自检（不出数字）
python scripts/run_eval.py --prompts eval_output/2026-11-10T12-00  # 3. 把 A/B 提示词原文落盘
python scripts/run_eval.py --score eval_output/2026-11-10T12-00    # 4. 计分
```

脚本**不代替你调用模型**，它只做四件事：

1. `--check`：校验评估物料是否自洽（YAML 可解析、字段齐全、`risk_rule` 指向真实规则、`dataset_size` 与实际条数一致、**ground-truth 里的片段确实还存在于对应代码中**），不产生任何指标；
2. `--self-test`：解析器自检（三态归一化、表格抽取、证据切分、指标计算），不需要真实数据；
3. `--prompts eval_output/<时间戳>`：把 `references/eval-protocol.md` 的 A/B 提示词**原文**写进 `<run>/prompts/{A,B}.md`，并记录 `sha256`；同时校验 A 组没有被弱化成一句话版、没有夹带 ReqGuard 的机制（两者都是协议 §2.1 明令禁止的）；
4. `--score eval_output/<时间戳>`：对**你自己按协议跑出来的** A1–A3 / B1–B3 报告计算逐条明细与指标，并写 `score.md` / `score.json`。

A/B 组的提示词以 `references/eval-protocol.md` 的原文为准，**脚本内不保留任何提示词副本**（副本就是弱化版的来源），只做抽取 + 校验；没有报告数据时脚本会报错退出（`exit 2`），绝不输出一份全 0 的"成绩"。

评估协议（提示词原文、指标定义、统计口径、计分流程）见 [`references/eval-protocol.md`](references/eval-protocol.md)。

## 7. ground-truth 说明

- `references/ground-truth.yaml` **仅用于评估 skill 本身的漏报率**，不是日常使用依赖。
- **日常检查自己的项目不需要编写 ground-truth。**
- 只有**新增评估样本**时才需要人工标注预期判定。
- **ground-truth 必须由人确认。AI 只能出草案，禁止 AI 自写标准答案、禁止伪造评估结果。**
- 建议人工确认后**隔天复核**，或**由他人独立标注部分样本**做对照，避免自我确认偏差。
- 文件内 `code_location` 以「函数名 + 代码片段」为主，行号仅作辅助——行号会随提交漂移。

## 8. 风险规则自定义

风险分级规则在 `risk-rules.yaml`，可配置、可覆盖：

```bash
cp risk-rules.yaml risk-rules.local.yaml
# 修改 grades.*.clause_types 的 keywords / 新增条款类型
```

- 复制为 `risk-rules.local.yaml` 后按需修改，调用时作为「风险规则」传入，**无需改动 `SKILL.md`**；
- 只改关键词不会破坏结构；新增条款类型需带 `id`、`label`、`keywords`、`rationale`；
- 自动判不了的条款一律归入 `待人工定级`（`settings.unclassified_bucket`），不允许模型硬猜；
- 降级默认高风险规则（例如把支付类移出高风险）属于敏感改动，需在 PR 中说明理由。

修改后请用 `python -c "import yaml;yaml.safe_load(open('risk-rules.yaml'))"` 校验可解析，并确认 CI 通过。

## 9. 局限性

- **不能替代人工验收。** 它把"漏什么、证据在哪"摆上桌，放行责任仍在人。
- **无证据只能判「无法判定」。** 代码不可读、范围无法界定、判据歧义时，它给不出结论。
- **「无法判定」率过高说明 skill 在该场景失效**，需要人工介入——这不等于漏报率低。看指标时要两个一起看，只看漏报率会被"一律无法判定"的策略刷分。
- **检查依赖 agent 的文件读取能力。** 只有截图、压缩包未展开、仓库权限不足时，拿不到证据。
- **不提供修复代码**，也不做代码质量评价、性能评估、架构建议。
- 关键词分级是**召回优先的粗筛**：可能把中风险误升为高风险（可通过 `risk-rules.yaml` 调整），但设计上宁可升级不可漏级。
- 10 条规模的 testset **不能支撑任何对外性能声明**。

## 10. 维护与贡献

- 提交方式、Issue/PR 流程、新增测试样本与 ground-truth 确认流程：见 [`CONTRIBUTING.md`](CONTRIBUTING.md)；
- 参与讨论前请先读 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)；
- 安全问题请按 [`SECURITY.md`](SECURITY.md) 私下报告，不要开公开 Issue 贴漏洞细节；
- 版本变更记录见 [`CHANGELOG.md`](CHANGELOG.md)；许可证见 [`LICENSE`](LICENSE)（MIT）；
- 提交前必须跑 `python scripts/run_eval.py --check` 与 `--self-test`；若新增或修改了评估样本，需**真实跑一次** A/B 评估再更新 `results.md`，没跑就保持「未执行」、不得填数字。新增样本单次不少于 5 条，正式评估集建议 20～30 条。

## 11. 设计原理

原理不在 README 展开，见 [`references/design-rationale.md`](references/design-rationale.md)。

---

MIT License · 版权归 ReqGuard contributors
