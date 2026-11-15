#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReqGuard 评估脚本：校验评估物料，并按 references/eval-protocol.md 计算指标。

三种用法
--------
1) 只校验（CI 冒烟用，不产生任何评估数字）：

       python scripts/run_eval.py --check

   校验 ground-truth.yaml / risk-rules.yaml 能否解析、必填字段是否齐全、
   声明的 composition 与实际条目数是否一致、风险规则 id 是否都存在。
   任何一项失败都会以非零码退出。

2) 解析器自检（不依赖真实评估数据）：

       python scripts/run_eval.py --self-test

   用内置的极小样例字符串验证“三态归一化 / 表格行抽取 / 证据块切分”，
   只打印 PASS/FAIL，不输出任何指标。

3) 正式评分（需要真实跑过 A/B 两组并留下报告）：

       python scripts/run_eval.py --score eval_output/2026-11-10T12-00

   目录结构按 eval-protocol.md 第 2 节：

       eval_output/<run>/{A1,A2,A3,B1,B2,B3}.md   （或 A/*.md、B/*.md）

   输出：<run>/score.md（人读）与 <run>/score.json（机读）。
   报告里没有出现过的 MUST 记为“未列出”，严格口径下计为漏报。

设计约束
--------
* 不伪造数字：找不到任何报告文件时直接报错退出，不输出全 0 的“成绩”。
* 不做跨模型比较：只比较同一 run 内的 A/B 两组。
* 行号不参与证据命中判定（见 eval-protocol.md 3.4）。
* 本脚本只依赖标准库 + PyYAML。

已知局限（必须知道，否则会误读结果）
------------------------------------
* 报告是人/模型写的 Markdown，结构可能有出入；抽取器基于“需求编号 + 三态词”，
  遇到自由叙述会抽不到，从而记为“未列出”（严格口径下算漏报，偏保守）。
* 证据命中按报告条目块内的文本匹配，块边界由“下一个需求编号”切分；
  若报告把证据集中写在文末，会命中失败（偏严格）。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 环境问题，直接告知怎么修
    sys.stderr.write(
        "缺少依赖 PyYAML。请先执行：\n"
        "    pip install -r requirements.txt\n"
        "（或者只跑 --self-test，它同样需要 PyYAML 读取规则文件。）\n"
    )
    raise SystemExit(1)

# Windows 控制台默认 GBK：中文在 cmd 里可能是乱码，遇到 GBK 无法表示的字符
# 还会直接抛 UnicodeEncodeError，把“评估脚本崩了”伪装成“数据有问题”。
# 这里统一按 UTF-8 输出（错误字符用替代符，绝不中断），保证日志可被机器读取。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # 老版本解释器或重定向场景，忽略
        pass

# 仓库根目录：testset / references 的相对路径都从这里解析。
# 用脚本自身位置推导，而不是当前工作目录——否则从别的目录调用就会找不到文件。
REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

VERDICT_PASS = "符合"
VERDICT_FAIL = "不符合"
VERDICT_UNKNOWN = "无法判定"
VERDICT_MISSING = "未列出"

# 顺序很重要：先匹配长的/带否定的词，再匹配短词，否则“不符合”会被吃成“符合”。
VERDICT_PATTERNS = [
    (VERDICT_FAIL, ["不符合", "未满足", "不满足", "未实现", "未覆盖", "缺失", "未通过"]),
    (VERDICT_UNKNOWN, ["无法判定", "无法判断", "无法确认", "不确定", "待人工定级", "证据不足"]),
    (VERDICT_PASS, ["符合", "已满足", "满足", "已实现", "已覆盖", "通过"]),
]

# 模糊措辞：协议 4.3 规定不算“符合”，这里统一降级为“无法判定”。
FUZZY_WORDS = ["基本符合", "部分符合", "大体满足", "基本满足", "大致符合", "部分满足"]

ID_RE = re.compile(r"\bR-(\d{2,3})\b")
ID_ANY_RE = re.compile(r"\bR-\d{2,3}\b")

REQUIRED_SAMPLE_FIELDS = ("id", "priority", "risk", "expected", "requirement")
VALID_PRIORITIES = ("MUST", "SHOULD", "MAY")
VALID_RISKS = ("high", "mid", "low")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class Sample:
    id: str
    priority: str
    risk: str
    risk_rule: str
    expected: str
    requirement: str
    file: str = ""
    function: str = ""
    snippet: str = ""
    match_tokens: list = field(default_factory=list)


@dataclass
class Judgment:
    """报告里抽到的一条判定。"""

    req_id: str
    verdict: str
    evidence_block: str = ""
    fuzzy: bool = False
    source: str = ""


@dataclass
class ItemScore:
    sample: Sample
    verdict: str            # 归一化后的判定；未抽出为 未列出
    evidence_hit: bool
    note: str = ""


# ---------------------------------------------------------------------------
# 读取与校验
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层不是映射（mapping），无法作为配置读取。")
    return data


def load_ground_truth(path: Path) -> tuple:
    data = load_yaml(path)
    raw = data.get("samples")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path} 缺少 samples 列表，或列表为空。")
    samples = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path} 第 {idx} 条样本不是映射。")
        missing = [k for k in REQUIRED_SAMPLE_FIELDS if not item.get(k)]
        if missing:
            raise ValueError(f"{path} 第 {idx} 条样本缺少字段：{', '.join(missing)}")
        loc = item.get("code_location") or {}
        samples.append(
            Sample(
                id=str(item["id"]).strip(),
                priority=str(item["priority"]).strip().upper(),
                risk=str(item["risk"]).strip().lower(),
                risk_rule=str(item.get("risk_rule", "")).strip(),
                expected=str(item["expected"]).strip(),
                requirement=str(item["requirement"]).strip(),
                file=str(loc.get("file", "")).strip(),
                function=str(loc.get("function", "")).strip(),
                snippet=str(loc.get("snippet", "")).strip(),
                match_tokens=[str(t) for t in (loc.get("match_tokens") or [])],
            )
        )
    return data, samples


def load_rules(path: Path) -> dict:
    data = load_yaml(path)
    grades = data.get("grades")
    if not isinstance(grades, dict) or not grades:
        raise ValueError(f"{path} 缺少 grades 段。")
    return data


def all_rule_ids(rules: dict) -> set:
    ids = set()
    for grade_key, grade in (rules.get("grades") or {}).items():
        for clause in (grade or {}).get("clause_types") or []:
            cid = str((clause or {}).get("id", "")).strip()
            if cid:
                ids.add(cid)
    return ids


def check_materials(gt_path: Path, rules_path: Path, verbose: bool = True) -> list:
    """返回 (errors, warnings) 里的 errors；warnings 直接打印。"""
    errors = []
    gt_data, samples = load_ground_truth(gt_path)
    rules = load_rules(rules_path)
    rule_ids = all_rule_ids(rules)
    repo_root = REPO_ROOT

    ids = [s.id for s in samples]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"样本编号重复：{', '.join(dup)}")

    for s in samples:
        if s.priority not in VALID_PRIORITIES:
            errors.append(f"{s.id}: priority={s.priority} 不在 {VALID_PRIORITIES} 内")
        if s.risk not in VALID_RISKS:
            errors.append(f"{s.id}: risk={s.risk} 不在 {VALID_RISKS} 内")
        if s.expected not in (VERDICT_PASS, VERDICT_FAIL, VERDICT_UNKNOWN):
            errors.append(f"{s.id}: expected={s.expected} 不是三态取值之一")
        if rule_ids and s.risk_rule and s.risk_rule not in rule_ids:
            errors.append(f"{s.id}: risk_rule={s.risk_rule} 在 {rules_path.name} 中不存在")
        if s.expected == VERDICT_FAIL and not s.file:
            errors.append(f"{s.id}: expected=不符合 但没有 code_location.file，评估时无法核对证据")
        if s.expected == VERDICT_FAIL and not s.match_tokens:
            errors.append(f"{s.id}: expected=不符合 但没有 match_tokens，证据定位准确率无法计算")

        # 漂移检查：ground-truth 里的片段与 token 必须真的出现在对应代码里。
        # 代码改了而 ground-truth 没跟着改，是评估集最常见、也最致命的失配。
        if s.file:
            code_path = repo_root / s.file
            if not code_path.is_file():
                errors.append(
                    f"{s.id}: code_location.file={s.file} 不存在"
                    f"（按仓库根目录 {repo_root} 解析）"
                )
            else:
                body = squash(code_path.read_text(encoding="utf-8", errors="replace"))
                if s.snippet and squash(s.snippet) not in body:
                    errors.append(
                        f"{s.id}: snippet 在 {s.file} 中找不到，"
                        "ground-truth 与代码可能已不同步"
                    )
                for token in s.match_tokens:
                    if token and squash(token) not in body:
                        errors.append(
                            f"{s.id}: match_token={token!r} 在 {s.file} 中找不到"
                        )

    declared_size = gt_data.get("dataset_size")
    if declared_size is not None and int(declared_size) != len(samples):
        errors.append(f"dataset_size={declared_size} 与实际样本数 {len(samples)} 不一致")

    declared = gt_data.get("composition") or {}
    actual = {
        "MUST": sum(1 for s in samples if s.priority == "MUST"),
        "SHOULD": sum(1 for s in samples if s.priority == "SHOULD"),
        "MAY": sum(1 for s in samples if s.priority == "MAY"),
        f"expected_{VERDICT_FAIL}": sum(1 for s in samples if s.expected == VERDICT_FAIL),
        f"expected_{VERDICT_PASS}": sum(1 for s in samples if s.expected == VERDICT_PASS),
        f"expected_{VERDICT_UNKNOWN}": sum(1 for s in samples if s.expected == VERDICT_UNKNOWN),
    }
    for key, got in actual.items():
        if key in declared and int(declared[key]) != got:
            errors.append(f"composition.{key} 声明为 {declared[key]}，实际为 {got}")

    status = str(gt_data.get("status", "")).strip()
    if status != "human-confirmed":
        print(
            f"[WARN] ground-truth.status = {status or '(空)'}，尚未人工确认；"
            "此时任何评分结果只能内部参考，不得对外引用。"
        )
    size = len(samples)
    if size < 20:
        print(
            f"[WARN] 样本数 {size} < 20：只够跑通流程与验证报告结构，"
            "不得作为对外数字引用（见 references/eval-protocol.md 第 6 节）。"
        )
    if not any(s.priority == "MUST" and s.expected == VERDICT_PASS for s in samples):
        print(
            "[WARN] 缺少“合规的 MUST 对照样本”：MUST 维度上的误报率无法被有效度量。"
        )

    if verbose:
        print(f"[OK] ground-truth：{size} 条样本，编号 {ids[0]}～{ids[-1]}")
        print(f"[OK] risk-rules：{len(rule_ids)} 条规则可分派风险等级")
        print(f"[OK] 一致性：dataset_size / composition / risk_rule 引用均已核对")
    return errors


# ---------------------------------------------------------------------------
# 解析报告
# ---------------------------------------------------------------------------


def normalize_verdict(text: str) -> tuple:
    """把一段文本归一化成三态。返回 (verdict, fuzzy)。

    注意：文本中可能同时出现多个三态词（例如“不符合，不能算符合”），
    因此先查否定词，再查“无法判定”，最后才查“符合”。
    """
    if not text:
        return (None, False)
    compact = re.sub(r"[\s\u3000]+", "", text)

    for word in FUZZY_WORDS:
        if word in compact:
            return (VERDICT_UNKNOWN, True)

    for verdict, words in VERDICT_PATTERNS:
        for word in words:
            if word in compact:
                return (verdict, False)
    return (None, False)


def split_cells(line: str) -> list:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip())) and "-" in line


def parse_report(text: str, source: str = "") -> dict:
    """从一个 Markdown 报告里抽出 {需求编号: Judgment}。

    只做两件事：
      1) 找带需求编号的行（表格行或列表行），从中定位三态词；
      2) 以“下一个需求编号”为界，切出该条目的文本块作为证据区。

    同一编号出现多次时取最严格判定（不符合 > 无法判定 > 符合），与协议 4.5/4.8 一致。
    """
    lines = text.splitlines()
    hits = []  # (line_index, req_id)

    for idx, line in enumerate(lines):
        if is_separator(line):
            continue
        for m in ID_ANY_RE.finditer(line):
            hits.append((idx, m.group(0)))
            break

    result = {}
    for pos, (line_idx, req_id) in enumerate(hits):
        next_idx = hits[pos + 1][0] if pos + 1 < len(hits) else len(lines)
        line = lines[line_idx]
        verdict, fuzzy = (None, False)

        if line.strip().startswith("|"):
            # 表格行：只在单元格里找判定，绝不把后续行拉进来——否则下一行的
            # “不符合”会把本行的“已满足”覆盖掉。优先“整格就是一个三态词”的列。
            cells = [c for c in split_cells(line) if not ID_ANY_RE.fullmatch(c.strip())]
            for cell in cells:
                if normalize_verdict(cell)[0] is not None and len(squash(cell)) <= 8:
                    verdict, fuzzy = normalize_verdict(cell)
                    break
            if verdict is None:
                for cell in cells:
                    v, fz = normalize_verdict(cell)
                    if v:
                        verdict, fuzzy = v, fz
                        break
        else:
            # 列表/叙述式：判定常写在编号之后的一两行内。
            head = "\n".join(lines[line_idx : min(line_idx + 3, len(lines))])
            verdict, fuzzy = normalize_verdict(head)

        block = "\n".join(lines[line_idx:next_idx])
        judgment = Judgment(
            req_id=req_id,
            verdict=verdict or VERDICT_UNKNOWN,
            evidence_block=block,
            fuzzy=fuzzy,
            source=source,
        )
        prev = result.get(req_id)
        if prev is None:
            result[req_id] = judgment
        else:
            order = {VERDICT_FAIL: 0, VERDICT_UNKNOWN: 1, VERDICT_PASS: 2}
            if order[judgment.verdict] < order[prev.verdict]:
                result[req_id] = judgment  # 取更严格的判定
    return result


def idents(text: str) -> list:
    """从“函数名”字段里抽标识符，兼容 'Role 枚举 / canApprove()' 这种写法。"""
    return [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")]


def squash(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text or "")


def evidence_hit(block: str, sample: Sample) -> bool:
    """协议 3.4：文件命中 + 函数名（≥1 个标识符）命中 + match_tokens ≥1 命中。"""
    if not block:
        return False
    block_s = squash(block)
    file_ok = bool(sample.file) and Path(sample.file).name in block
    fn_tokens = idents(sample.function)
    fn_ok = bool(fn_tokens) and any(t in block for t in fn_tokens)
    tok_ok = any(squash(t) and squash(t) in block_s for t in sample.match_tokens)
    return file_ok and fn_ok and tok_ok


def score_report(judgments: dict, samples: list, source: str) -> list:
    scored = []
    for s in samples:
        j = judgments.get(s.id)
        if j is None:
            scored.append(
                ItemScore(sample=s, verdict=VERDICT_MISSING, evidence_hit=False,
                          note="报告中未出现该编号")
            )
            continue
        note = ""
        if j.fuzzy:
            note = "模糊结论，按协议 4.3 归为未匹配"
        elif j.verdict == VERDICT_UNKNOWN and re.search(r"无法|不确定|证据不足", j.evidence_block or ""):
            note = "报告自述无法判定"
        scored.append(
            ItemScore(
                sample=s,
                verdict=j.verdict,
                evidence_hit=evidence_hit(j.evidence_block, s) if j.verdict == VERDICT_FAIL else False,
                note=note,
            )
        )
    return scored


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------


def metrics(scored: list) -> dict:
    """按 eval-protocol.md 第 3、4 节计算。主指标只用 MUST。"""
    must = [i for i in scored if i.sample.priority == "MUST"]
    gold_neg = [i for i in must if i.sample.expected == VERDICT_FAIL]
    gold_pos = [i for i in must if i.sample.expected == VERDICT_PASS]

    def ratio(num: int, den: int):
        return (num / den) if den else None

    miss_main = sum(1 for i in gold_neg if i.verdict == VERDICT_PASS)
    miss_strict = sum(
        1 for i in gold_neg if i.verdict in (VERDICT_PASS, VERDICT_UNKNOWN, VERDICT_MISSING)
    )
    false_pos = sum(1 for i in gold_pos if i.verdict == VERDICT_FAIL)
    unknown = sum(1 for i in must if i.verdict == VERDICT_UNKNOWN)
    judged_fail = [i for i in must if i.verdict == VERDICT_FAIL]
    ev_hit = sum(1 for i in judged_fail if i.evidence_hit)

    return {
        "n_must": len(must),
        "n_gold_neg": len(gold_neg),
        "n_gold_pos": len(gold_pos),
        "miss_rate_main": ratio(miss_main, len(gold_neg)),
        "miss_rate_strict": ratio(miss_strict, len(gold_neg)),
        "false_positive_rate": ratio(false_pos, len(gold_pos)),
        "undetermined_rate": ratio(unknown, len(must)),
        "evidence_accuracy": ratio(ev_hit, len(judged_fail)),
        "counts": {
            "miss_main": miss_main,
            "miss_strict": miss_strict,
            "false_pos": false_pos,
            "undetermined": unknown,
            "judged_fail": len(judged_fail),
            "evidence_hit": ev_hit,
        },
    }


def median_metrics(items: list) -> dict:
    """对多次重复取中位数（None 不参与，避免把“无样本”当成 0）。"""
    keys = [
        "miss_rate_main",
        "miss_rate_strict",
        "false_positive_rate",
        "undetermined_rate",
        "evidence_accuracy",
    ]
    out = {}
    for k in keys:
        vals = [m[k] for m in items if m.get(k) is not None]
        out[k] = statistics.median(vals) if vals else None
    out["n_must"] = items[0]["n_must"] if items else 0
    out["n_gold_neg"] = items[0]["n_gold_neg"] if items else 0
    out["n_gold_pos"] = items[0]["n_gold_pos"] if items else 0
    return out


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def delta(b, a):
    if b is None or a is None:
        return "n/a"
    return f"{(b - a) * 100:+.1f} pt"


def render_score_md(summary: dict, gt_meta: dict, run_dir: Path) -> str:
    lines = []
    add = lines.append
    add("# ReqGuard 评估结果")
    add("")
    add(f"- 数据目录：`{run_dir.name}`")
    add(f"- ground-truth 状态：`{gt_meta.get('status')}`")
    add(f"- 样本规模：{gt_meta.get('dataset_size')} 条（MUST {summary['n_must']} 条）")
    add(f"- 宿主/模型/参数：{gt_meta.get('host_note') or '**未记录 —— 结果不可复现**'}")
    add("")
    if str(gt_meta.get("status")) != "human-confirmed":
        add("> ⚠ ground-truth 未人工确认，本结果仅供内部参考，**不得对外引用**。")
        add("")
    if (gt_meta.get("dataset_size") or 0) < 20:
        add("> ⚠ 样本数 < 20，只说明流程跑通，**不得对外引用**。")
        add("")
    add("## 汇总（中位数）")
    add("")
    add("| 组别 | 漏报率（主） | 漏报率（严格） | 误报率 | 无法判定率 | 证据定位准确率 |")
    add("| --- | --- | --- | --- | --- | --- |")
    a, b = summary["A"], summary["B"]
    add(
        f"| A（中位数） | {pct(a['miss_rate_main'])} | {pct(a['miss_rate_strict'])} | "
        f"{pct(a['false_positive_rate'])} | {pct(a['undetermined_rate'])} | {pct(a['evidence_accuracy'])} |"
    )
    add(
        f"| B（中位数） | {pct(b['miss_rate_main'])} | {pct(b['miss_rate_strict'])} | "
        f"{pct(b['false_positive_rate'])} | {pct(b['undetermined_rate'])} | {pct(b['evidence_accuracy'])} |"
    )
    add(
        f"| 差值（B−A） | {delta(b['miss_rate_main'], a['miss_rate_main'])} | "
        f"{delta(b['miss_rate_strict'], a['miss_rate_strict'])} | "
        f"{delta(b['false_positive_rate'], a['false_positive_rate'])} | "
        f"{delta(b['undetermined_rate'], a['undetermined_rate'])} | "
        f"{delta(b['evidence_accuracy'], a['evidence_accuracy'])} |"
    )
    add("")
    add("> 漏报率、误报率、无法判定率：负值表示 B 更低（更好）；证据定位准确率：正值表示 B 更高（更好）。")
    if not summary.get("n_gold_pos"):
        add("")
        add(
            "> 误报率为 n/a：本测试集没有「期望符合」的 MUST 样本，无法度量误报"
            "（已知局限，见 `references/eval-protocol.md` 第 6 节）。"
        )
    if not any(
        r.get("evidence_accuracy") is not None for r in summary["repeats"].get("A", [])
    ):
        add("")
        add("> 证据定位准确率为 n/a：该组没有判定为「不符合」的 MUST 条目可供核对。")
    add("")
    add("## 逐次明细")
    add("")
    for group in ("A", "B"):
        add(f"### {group} 组")
        add("")
        add("| 重复 | 主漏报 | 严格漏报 | 误报 | 无法判定 | 证据命中 |")
        add("| --- | --- | --- | --- | --- | --- |")
        for rep in summary["repeats"][group]:
            add(
                f"| {rep['source']} | {pct(rep['miss_rate_main'])} | {pct(rep['miss_rate_strict'])} | "
                f"{pct(rep['false_positive_rate'])} | {pct(rep['undetermined_rate'])} | "
                f"{pct(rep['evidence_accuracy'])} |"
            )
        add("")

    if summary.get("per_item"):
        add("## 逐条对照（以 B 组首次重复为例）")
        add("")
        add("| 编号 | 优先级 | 期望 | 实际 | 证据命中 | 备注 |")
        add("| --- | --- | --- | --- | --- | --- |")
        for row in summary["per_item"]:
            add(
                f"| {row['id']} | {row['priority']} | {row['expected']} | {row['actual']} | "
                f"{'是' if row['evidence_hit'] else '否'} | {row['note']} |"
            )
        add("")
    add("---")
    add("")
    add("统计口径见 `references/eval-protocol.md` 第 3、4 节；脚本不参与任何人工补判。")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------


def self_test() -> int:
    failures = []

    def expect(name, got, want):
        if got != want:
            failures.append(f"{name}: 期望 {want!r}，实际 {got!r}")

    expect("不符合 优先于 符合", normalize_verdict("不符合")[0], VERDICT_FAIL)
    expect("已满足→符合", normalize_verdict("已满足")[0], VERDICT_PASS)
    expect("无法判断→无法判定", normalize_verdict("无法判断")[0], VERDICT_UNKNOWN)
    expect("基本符合→无法判定(模糊)", normalize_verdict("基本符合")[0], VERDICT_UNKNOWN)
    expect("模糊标记", normalize_verdict("部分符合")[1], True)
    expect("无三态词→None", normalize_verdict("说明文字")[0], None)

    table = "\n".join(
        [
            "| 编号 | 需求 | 风险 | 判定 | 证据 |",
            "| --- | --- | --- | --- | --- |",
            "| R-01 | 密钥 | 高 | 不符合 | auth.ts :: const JWT_SECRET :: dev-secret |",
            "| R-02 | 鉴权 | 高 | 已满足 | order.ts :: requireAuth |",
        ]
    )
    parsed = parse_report(table, "t.md")
    expect("表格抽取条数", len(parsed), 2)
    expect("R-01 判定", parsed["R-01"].verdict, VERDICT_FAIL)
    expect("R-02 判定", parsed["R-02"].verdict, VERDICT_PASS)

    sample = Sample(
        id="R-01", priority="MUST", risk="high", risk_rule="high.x",
        expected=VERDICT_FAIL, requirement="x",
        file="testset/code/auth.ts", function="const JWT_SECRET",
        snippet="dev-secret-123456", match_tokens=["JWT_SECRET", "dev-secret-123456"],
    )
    expect("证据命中(函数名+token)", evidence_hit(parsed["R-01"].evidence_block, sample), True)
    expect("证据不命中(缺文件)", evidence_hit("JWT_SECRET dev-secret-123456", sample), False)

    s = score_report(parsed, [sample], "t.md")
    expect("未列出的 MUST 记未列出", s[0].verdict, VERDICT_FAIL)

    m = metrics(
        [
            ItemScore(sample=sample, verdict=VERDICT_PASS, evidence_hit=False),
            ItemScore(
                sample=Sample("R-02", "MUST", "high", "", VERDICT_PASS, "y"), verdict=VERDICT_FAIL,
                evidence_hit=True,
            ),
        ]
    )
    expect("主漏报 1/1", m["miss_rate_main"], 1.0)
    expect("误报 1/1", m["false_positive_rate"], 1.0)

    if failures:
        print("SELF-TEST FAILED")
        for f in failures:
            print("  - " + f)
        return 1
    print("SELF-TEST PASSED（三态归一化 / 表格抽取 / 证据切分 / 指标计算）")
    return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def collect_reports(run_dir: Path) -> "OrderedDict[str, list]":
    """按 eval-protocol 的命名收集报告：A1..A3 / B1..B3，或 A/*.md / B/*.md。"""
    groups = OrderedDict((("A", []), ("B", [])))
    if not run_dir.exists():
        raise FileNotFoundError(f"找不到评估目录：{run_dir}")

    md_files = sorted(p for p in run_dir.glob("*.md") if p.name not in ("score.md",))
    for p in md_files:
        m = re.match(r"^([AB])(\d*)", p.stem.upper())
        if m:
            groups[m.group(1)].append(p)

    for sub in ("A", "B"):
        sub_dir = run_dir / sub
        if sub_dir.is_dir():
            groups[sub].extend(sorted(sub_dir.glob("*.md")))

    return groups


def run_score(run_dir: Path, gt_path: Path, rules_path: Path, out_md: Path, out_json: Path) -> int:
    gt_data, samples = load_ground_truth(gt_path)
    groups = collect_reports(run_dir)
    if not groups["A"] and not groups["B"]:
        sys.stderr.write(
            f"[ERROR] {run_dir} 下没有任何 A/B 组报告（期望 A1..A3.md / B1..B3.md，或 A/、B/ 子目录）。\n"
            "        本脚本不会在缺少数据时输出全 0 的“成绩”。请先按 eval-protocol.md 第 5 节跑评估。\n"
        )
        return 2

    summary = {
        "A": {},
        "B": {},
        "repeats": {"A": [], "B": []},
        "n_must": sum(1 for s in samples if s.priority == "MUST"),
        "n_gold_neg": sum(1 for s in samples if s.priority == "MUST" and s.expected == VERDICT_FAIL),
        "n_gold_pos": sum(1 for s in samples if s.priority == "MUST" and s.expected == VERDICT_PASS),
        "reports": {},
    }

    per_group_metrics = {"A": [], "B": []}
    for group, files in groups.items():
        for p in files:
            text = p.read_text(encoding="utf-8")
            judgments = parse_report(text, source=p.name)
            scored = score_report(judgments, samples, p.name)
            m = metrics(scored)
            m["source"] = p.name
            summary["repeats"][group].append(m)
            per_group_metrics[group].append(m)
            summary["reports"][p.name] = len(judgments)

    for group in ("A", "B"):
        summary[group] = median_metrics(per_group_metrics[group]) if per_group_metrics[group] else None

    if summary["A"] is None or summary["B"] is None:
        sys.stderr.write("[WARN] 只有一组有数据，差值列会显示 n/a。\n")

    # 逐条对照：取 B 组第一份报告；没有 B 组就取 A 组第一份。
    ref_group = "B" if groups["B"] else "A"
    if groups[ref_group]:
        ref_file = groups[ref_group][0]
        judgments = parse_report(ref_file.read_text(encoding="utf-8"), source=ref_file.name)
        scored = score_report(judgments, samples, ref_file.name)
        summary["per_item"] = [
            {
                "id": i.sample.id,
                "priority": i.sample.priority,
                "expected": i.sample.expected,
                "actual": i.verdict,
                "evidence_hit": i.evidence_hit,
                "note": i.note or ("—" if i.sample.priority == "MUST" else "非 MUST，不计入主指标"),
            }
            for i in scored
        ]

    gt_meta = {
        "status": gt_data.get("status"),
        "dataset_size": gt_data.get("dataset_size", len(samples)),
        "host_note": gt_data.get("host_note"),
    }
    md = render_score_md({"A": summary["A"] or {}, "B": summary["B"] or {}, **summary}, gt_meta, run_dir)
    out_md.write_text(md, encoding="utf-8")
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已写入：{out_md}")
    print(f"已写入：{out_json}")
    print(f"解析到的报告：{summary['reports']}")
    if summary["A"] and summary["B"]:
        print(
            "严格漏报率 A={} B={}".format(
                pct(summary["A"].get("miss_rate_strict")), pct(summary["B"].get("miss_rate_strict"))
            )
        )
    return 0


def main(argv=None) -> int:
    default_gt = Path(__file__).resolve().parent.parent / "references" / "ground-truth.yaml"
    default_rules = Path(__file__).resolve().parent.parent / "risk-rules.yaml"

    ap = argparse.ArgumentParser(
        prog="run_eval.py",
        description="ReqGuard 评估脚本：校验物料 / 自检解析器 / 按 A/B 报告计算漏报率等指标。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python scripts/run_eval.py --check\n"
            "  python scripts/run_eval.py --self-test\n"
            "  python scripts/run_eval.py --score eval_output/2026-11-10T12-00\n"
        ),
    )
    ap.add_argument("--check", action="store_true", help="只校验评估物料，不产生任何指标")
    ap.add_argument("--self-test", action="store_true", help="解析器自检，不依赖真实数据")
    ap.add_argument("--score", metavar="RUN_DIR", help="对一次 A/B 评估目录计算指标")
    ap.add_argument("--ground-truth", type=Path, default=default_gt, help="ground-truth.yaml 路径")
    ap.add_argument("--rules", type=Path, default=default_rules, help="risk-rules.yaml 路径")
    ap.add_argument("--out", type=Path, help="score.md 输出路径（默认 <RUN_DIR>/score.md）")
    ap.add_argument("--json", type=Path, help="score.json 输出路径（默认 <RUN_DIR>/score.json）")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.check:
        errors = check_materials(args.ground_truth, args.rules)
        if errors:
            print("\n[FAIL] 发现 %d 个问题：" % len(errors))
            for e in errors:
                print("  - " + e)
            return 1
        print("[PASS] 评估物料校验通过（未计算任何指标）")
        return 0

    if args.score:
        run_dir = Path(args.score)
        out_md = args.out or (run_dir / "score.md")
        out_json = args.json or (run_dir / "score.json")
        return run_score(run_dir, args.ground_truth, args.rules, out_md, out_json)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
