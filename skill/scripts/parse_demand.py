#!/usr/bin/env python3
"""imposer 需求解析器 — 读取 linotype build.py 输出 + demand.json → 版面健康报告 + 需求清单。

用法: python3 parse_demand.py <build_stdout.log> [--log <xelatex.log>] [--demand <demand.json>]
"""
import argparse, json, re, sys
from pathlib import Path

FILL_MIN = 0.95  # 与 linotype autofit 下限一致（血泪 #52: 原 0.45 是旧默认——
                 # linotype 已是 0.95 严肃报纸标准，0.45 把"应补稿的版面"
                 # 报 OK，健康报告与 demand.json 发单信号自相矛盾）

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


def parse_build_output(stdout: str, log_path: Path | None = None,
                       demand_path: Path | None = None) -> dict:
    report = {
        "converged": False, "autofit_failed": False, "overfull": False,
        "fills": [], "visual_pass": None, "requests_by_plate": {},
        "messages": [],
    }
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
    for m in re.finditer(r"Plate content: ([\d.]+)pt/ contentH ([\d.]+)pt", log_text):
        c, ch = float(m.group(1)), float(m.group(2))
        if ch > 0: report["fills"].append(c / ch)
    # 需求清单（demand.json）
    if demand_path and demand_path.exists():
        demand = json.loads(demand_path.read_text(encoding="utf-8"))
        report["requests_by_plate"] = demand.get("plates", {})
    if report["converged"] and not report["overfull"] and report["fills"] and min(report["fills"]) >= FILL_MIN:
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
