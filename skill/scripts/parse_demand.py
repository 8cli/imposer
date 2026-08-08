#!/usr/bin/env python3
"""imposer 需求解析器 — 读取排版引擎输出 + demand.json → 版面健康报告 + 需求清单。

支持双引擎（2026-08-08 切换 presswire 为默认，linotype 分支保留向后兼容）:
  - presswire --json（首选，2026-08-08 内存通讯）: cli stdout 为结构化
    JSON（library.render 输出，fills/demand/article_mismatch 全字段），
    json.loads 直接消费，零正则
  - presswire（默认）: cli stdout 含 "plate-PN: fill X.XXX (标签)" 行 +
    demand.json（结构契约兼容）；无 xelatex log
  - linotype（旧引擎）: build.py stdout（"✅ 收敛"）+ xelatex log 正则
    （"Plate content: Xpt/ contentH Ypt"）+ demand.json
自动检测: stdout 可 json.loads 且含 engine=presswire → --json 分支；
stdout 含 "plate-P" 行 → presswire；含 "✅ 收敛" → linotype。

用法: python3 parse_demand.py <build_stdout.log> [--log <xelatex.log>] [--demand <demand.json>]
"""
import argparse, json, re, sys
from pathlib import Path

FILL_MIN = 0.95  # 与引擎 autofit 下限一致（血泪 #52: 原 0.45 是旧默认——
                 # 已是 0.95 严肃报纸标准，0.45 把"应补稿的版面"
                 # 报 OK，健康报告与 demand.json 发单信号自相矛盾）

# ---- linotype 分支正则（旧引擎向后兼容）----
# linotype.cls 的全部 Overfull 输出模式（终审 I-1）:
#   "Overfull plate: content ..."   (:557 整版溢出)
#   "Overfull main column: ..."     (:364 主栏超高截断)
#   "Overfull aside column: ..."    (:369 侧栏超高截断)
#   "Overfull mainstory: ..."       (:408 主条 vsplit 截断)
# 2026-08-06 血泪 #52: Overfull 判定与 linotype build.py parse_feedback
# 完全一致——只认 plate 级 truncated>5%（main/aside column 的 vsplit
# 截断是设计内兜底，autofit 不因它压字号，parse_demand 也不应报 overfull；
# 原 re.search 字样判定把 0.9% 微截断也报 overfull → 健康报告永不出现
# "✅ 版面健康"，与 autofit 收敛信号自相矛盾）。
_OVERFULL_TRUNC_RE = re.compile(
    r"Overfull plate: content [\d.]+pt\s*> contentH ([\d.]+)pt, truncated ([\d.]+)")
_LATIN_FILL_RE = re.compile(r"Plate content: ([\d.]+)pt/ contentH ([\d.]+)pt")

# ---- presswire 分支正则（默认引擎）----
# cli stdout: "  plate-P1: fill 0.228 (太空)" / "  plate-P1: fill 2.057 (溢出)"
_PW_FILL_RE = re.compile(r"plate-P(\d+): fill ([\d.]+)")
_PW_PANIC_RE = re.compile(r"panicked with: 严重溢出")
# 2026-08-08 用户决策: 字号固定适宜阅读（100% 不缩放），内容超出版心 →
# "文章不符合"信号——imposer 响应: 从 FreshRSS 选合适长度文章（原文直用），
# 无合适才改写缩小（不是字号缩放）
_PW_MIN_SCALE_RE = re.compile(r"内容超出版心")


def _from_library_json(res: dict, demand_path: Path | None = None) -> dict:
    """presswire --json 分支: library.render 结构化结果 → 统一报告（零正则）。"""
    report = {
        "converged": False, "autofit_failed": False, "overfull": False,
        "fills": [], "requests_by_plate": {}, "messages": [],
        "engine": "presswire", "backend": res.get("backend", ""),
        "visual_pass": None,
    }
    report["fills"] = [f["fill"] for f in res.get("fills", {}).values()]
    if res.get("ok"):
        report["converged"] = True
    if res.get("article_mismatch"):
        report["autofit_failed"] = True
        report["converged"] = False
        report["messages"].append("⚠️ 文章不符合版心（字号固定适宜阅读，不缩放）: 需选/改文章")
    if res.get("panic"):
        report["overfull"] = True
        report["messages"].append("⚠️ 严重溢出: typst panic（fill > 1.05）")
    if report["converged"]:
        report["messages"].append(
            "ℹ️ presswire autofit 模式 fill 报告失真，健康判定以 demand.json 为准")
    # demand 优先取内嵌（library 内存闭环）；无则读文件（兜底）
    if res.get("demand") and res["demand"].get("plates"):
        report["requests_by_plate"] = res["demand"]["plates"]
    elif demand_path and demand_path.exists():
        demand = json.loads(demand_path.read_text(encoding="utf-8"))
        report["requests_by_plate"] = demand.get("plates", {})
    if report["converged"] and not report["overfull"]:
        if not report["requests_by_plate"]:
            report["messages"].append(
                "✅ 版面健康: 无补稿需求（demand.json 为空 = 全部 fill ≥ 0.95）")
    return report


def parse_build_output(stdout: str, log_path: Path | None = None,
                       demand_path: Path | None = None) -> dict:
    # ---- presswire --json 分支（首选，2026-08-08 内存通讯）----
    # cli --json 模式 stdout 为 library.render 结构化 JSON（含 engine 字段）
    try:
        res = json.loads(stdout)
        if isinstance(res, dict) and res.get("engine") == "presswire":
            return _from_library_json(res, demand_path)
    except (json.JSONDecodeError, TypeError):
        pass
    report = {
        "converged": False, "autofit_failed": False, "overfull": False,
        "fills": [], "visual_pass": None, "requests_by_plate": {},
        "messages": [], "engine": "linotype" if "✅ 收敛" in stdout or "❌ 边界内" in stdout else "presswire",
    }
    if report["engine"] == "presswire":
        # ---- presswire 分支（默认）----
        # 收敛 = typst compile 成功（"✅ 已生成"）
        if "✅ 已生成" in stdout or "已生成" in stdout:
            report["converged"] = True
        # 严重溢出 panic（D4 红线: #panic → stderr "panicked with: 严重溢出"）
        if _PW_PANIC_RE.search(stdout):
            report["overfull"] = True
            report["messages"].append("⚠️ 严重溢出: typst panic（fill > 1.05）")
        # 2026-08-08 用户决策: 内容超出版心（字号固定 100% 不缩放）→
        # "文章不符合"信号——imposer 选合适长度文章/改写，非字号缩放
        if _PW_MIN_SCALE_RE.search(stdout):
            report["autofit_failed"] = True
            report["converged"] = False
            report["messages"].append("⚠️ 文章不符合版心（字号固定适宜阅读，不缩放）: 需选/改文章")
        # fill 逐版: autofit 模式 plate-frame measure 失真（架构决策——
        # severe-fill 100，收敛由 framefit 渲染保证），stdout fill 值不可靠
        # （实测 2-3 失真）。健康判定走 demand.json（权威信号）——
        # 有需求单 = 该版 fill < 0.95；无 demand.json = 全部达标。
        if report["converged"]:
            report["messages"].append("ℹ️ presswire autofit 模式 fill 报告失真，健康判定以 demand.json 为准")
    else:
        # ---- linotype 分支（向后兼容旧引擎）----
        if "✅ 收敛" in stdout: report["converged"] = True
        if "❌ 边界内无法放下" in stdout:
            report["autofit_failed"] = True; report["converged"] = False
        if "✅ 视觉验收通过" in stdout: report["visual_pass"] = True
        if "❌ 视觉验收未通过" in stdout: report["visual_pass"] = False
        log_text = ""
        if log_path and log_path.exists():
            log_text = log_path.read_text(errors="replace")
        for m in _OVERFULL_TRUNC_RE.finditer(log_text):
            content_h, truncated = float(m.group(1)), float(m.group(2))
            if truncated > content_h * 0.05:  # 与 linotype build.py 同阈值
                report["overfull"] = True
                report["messages"].append(f"⚠️ 严重溢出 truncated {truncated:.1f}pt > 5% 版心")
        for m in _LATIN_FILL_RE.finditer(log_text):
            c, ch = float(m.group(1)), float(m.group(2))
            if ch > 0: report["fills"].append(c / ch)
    # 需求清单（demand.json）——双引擎共用（契约兼容）
    if demand_path and demand_path.exists():
        demand = json.loads(demand_path.read_text(encoding="utf-8"))
        report["requests_by_plate"] = demand.get("plates", {})
    # 健康判定: linotype 用 fills（日志精确值）；presswire autofit 模式
    # fills 失真 → 以 demand.json 为空（无需求单）= 已填满
    if report["converged"] and not report["overfull"]:
        if report["engine"] == "presswire":
            if not report["requests_by_plate"]:
                report["messages"].append("✅ 版面健康: 无补稿需求（demand.json 为空 = 全部 fill ≥ 0.95）")
        elif report["fills"] and min(report["fills"]) >= FILL_MIN:
            report["messages"].append(f"✅ 版面健康: 各版 fill {[f'{f*100:.0f}%' for f in report['fills']]}")
    return report


def plate_health(fills: list[float]) -> list[str]:
    return [f"P{i+1} fill {f*100:.0f}% " + ("OK" if f >= FILL_MIN else "SPARSE→按单补稿")
            for i, f in enumerate(fills)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("build_stdout")
    ap.add_argument("--log", default=None)
    ap.add_argument("--demand", default=None, help="demand.json 路径")
    args = ap.parse_args()
    stdout = Path(args.build_stdout).read_text(errors="replace")
    report = parse_build_output(stdout, Path(args.log) if args.log else None,
                                Path(args.demand) if args.demand else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["fills"]:
        for line in plate_health(report["fills"]): print(line)
    for plate, info in report["requests_by_plate"].items():
        print(f"  📋 {plate} 需求: {len(info['requests'])} 项 — {info['requests']}")
