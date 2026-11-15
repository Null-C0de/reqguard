# 贡献指南

感谢你愿意改进 ReqGuard。这个项目由三部分组成：**检查逻辑**（`SKILL.md`）、**风险规则**（`risk-rules.yaml`）、**评估物料**（`testset/` + `references/ground-truth.yaml` + `scripts/run_eval.py`）。三者耦合很紧，改动其中一处通常要同步另外两处，下面的流程就是围绕这件事设计的。

## 先建立正确的心智模型

1. **`testset/` 与 `ground-truth.yaml` 只用于评估 skill 本身，不是日常使用依赖。**
2. 日常用 ReqGuard 检查你自己的项目时，**不需要**使用本仓库的 `testset/`，也**不需要**编写 ground-truth。
3. 只有**新增评估样本**时才需要人工标注 ground-truth。
4. **ground-truth 必须由人确认，AI 只能出草案。禁止伪造评估结果。**
5. ReqGuard 是通用的「需求文档 vs 代码实现」覆盖检查 Skill，**不绑定 vibecoding**；vibecoding 只是典型场景之一。
6. 对外引用的漏报率等数字**必须来自 ≥20 条测试集**；10 条只够跑通流程与验证报告结构。

动手前建议先读：[`SKILL.md`](../SKILL.md)（检查逻辑与硬约束）、[`references/design-rationale.md`](../references/design-rationale.md)（为什么这样设计）、[`references/eval-protocol.md`](../references/eval-protocol.md)（怎么证明它有效）。

## 提 Issue

- 用 [bug 模板](.github/ISSUE_TEMPLATE/bug_report.md) 报缺陷，用 [feature 模板](.github/ISSUE_TEMPLATE/feature_request.md) 提改进，用 [样本模板](.github/ISSUE_TEMPLATE/sample_proposal.md) 提新增评估样本。
- 报「判定不对」时请附上**需求原文 + 相关代码片段 + 实际输出**，并说明你认为正确的判定是什么。脱敏后再贴，不要贴真实密钥、token、生产数据。
- **安全漏洞不要走公开 Issue**，请按 [`SECURITY.md`](../SECURITY.md) 私下报告。

## 提 PR

1. Fork → 从 `main` 拉分支（建议 `fix/…`、`docs/…`、`eval/…` 前缀）。
2. 改完在本地跑完「提交前必做」清单（见下），把命令与**真实**输出贴进 PR 描述。
3. 按 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 填全，逐项勾选确认项。
4. 一个 PR 只做一件事：修判定逻辑就只动 `SKILL.md` 及其联动文件；加样本就不要顺手改风险分级。

### 提交前必做

```bash
# 1. 评估物料是否自洽（YAML 可解析、字段齐全、ground-truth 片段与代码一致）
python scripts/run_eval.py --check

# 2. 解析器自检（三态归一化 / 表格抽取 / 证据切分 / 指标计算）
python scripts/run_eval.py --self-test
```

- 改了 `testset/` 或 `ground-truth.yaml`：上面两条必须过，并且**真实跑过一次** A/B 评估再更新 `results.md`；没跑就保留 `results.md` 的「未执行」状态，**不要填数字**。
- 改了 `scripts/run_eval.py`：额外确认 `--score` 的指标定义仍与 `references/eval-protocol.md` 第 3、4 节一致。
- 改了 TypeScript 样本：在 `testset/code/` 下临时装 `typescript` + `@types/node` 跑 `tsc --strict --noEmit` 确认「看起来能运行」属实，跑完删掉 `node_modules` 与临时 `tsconfig.json`（不要提交它们）。

## 修改 `SKILL.md`

`SKILL.md` 是**约束集**，不是提示词堆砌。修改时同步检查：

- `risk-rules.yaml` 的规则 id 是否仍被 `SKILL.md` 引用，风险分级是否还与第 3 节一致；
- `references/report-template.md` 的九节结构是否仍与第 6 节一致；
- `references/eval-protocol.md` 的解析口径是否仍能匹配输出结构（表格列名、三态措辞）；
- `references/design-rationale.md` 的取舍表与失效模式是否需要补一条。

并在 `CHANGELOG.md` 记录、按语义化版本调整 `SKILL.md` frontmatter 的 `version`。

## 修改 `risk-rules.yaml`

- 规则 `id` 是稳定标识，**被 `ground-truth.yaml` 引用后不得随意改名**；确需改名要同时更新所有引用并在此说明。
- 新增条款类型需带 `id`、`label`、`keywords`、`rationale`；关键词要能被真实需求文案命中。
- **把某类需求从高风险降级属于敏感改动**，必须在 PR 里说明理由（漏降级的代价高于误升级）。
- 改完执行 `python scripts/run_eval.py --check`。

## 新增评估样本

**规模**：单次新增不少于 5 条；正式评估集建议 20～30 条；对外引用的数字必须来自 ≥20 条。

1. 在 `testset/requirements.md` 追加需求条目：编号、标题、优先级、需求原文、2～3 条验收判据（**不写实现方案、不写风险等级**）。
2. 在 `testset/code/` 写「看起来能运行但故意违规」的样本代码，文件顶部**注释标明对应需求编号**；逻辑不要压成一行，保留可识别的函数名与片段，**不要依赖行号定位**。
3. 在 `references/ground-truth.yaml` 补一条样本：`id`、`priority`、`risk`、`risk_rule`、`expected`、`requirement`、`reason`、`code_location{file,function,snippet,match_tokens}`。`snippet` 与 `match_tokens` 必须**真的出现在代码里**（`--check` 会校验）。
4. 更新 `dataset_size` 与 `composition` 的计数。
5. **人工确认流程**（缺一不可）：
   - 先由人逐条核对 expected 是否与埋坑意图一致，把 `status` 从 `draft` 改为 `human-confirmed` 并填写 `confirmed_by` / `confirmed_at`；
   - **隔天复核**，或**由他人独立标注部分样本**做对照，避免自我确认偏差；
   - AI 只能生成草案，**禁止 AI 自行确认**，也禁止为了让数字好看而修改 `expected`。
6. 想补充「合规对照样本」请优先做：当前 10 条里只有 1 条合规样本，导致 MUST 维度的误报率无法有效度量。

## A/B 提示词必须保持「体面版」

`references/eval-protocol.md` 中的 A 组提示词是「正常给足上下文、逐条核对、三态结论、要求给证据」的体面版本。**不得为了让 ReqGuard 看起来更有效而弱化 A 组**（例如减少上下文、禁止给证据、改成一两句敷衍指令）。这种对比没有意义，且会被视为造假。B 组同样不得偷偷加强要求。

## 代码风格

- 编码 UTF-8、换行 LF、缩进规则见 [`.editorconfig`](../.editorconfig)。
- `scripts/run_eval.py` 只用 Python 3 标准库 + PyYAML（见 [`requirements.txt`](../requirements.txt)）；不要引入新的运行时依赖。
- Markdown 用中文全角标点，代码块标注语言；不要提交编辑器自动生成的临时文件。

## 不要把「无法判定」当默认结论

`无法判定` 是诚实的逃生口，不是偷懒的默认值。任何放宽判定口径、把无法判定当通过、或把数字口径写含糊的改动都请先开 Issue 讨论。

## 行为准则与许可

参与本项目即表示同意遵守 [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md)。提交的贡献按 [`LICENSE`](../LICENSE)（MIT）授权。
