#!/usr/bin/env python3
"""imposer 需求解析器 — 读取 linotype build.py 输出 + demand.json → 版面健康报告 + 需求清单。

用法: python3 parse_demand.py <build_stdout.log> [--log <xelatex.log>] [--demand <demand.json>]
"""
import argparse, json, re, sys
from pathlib import Path

FILL_MIN = 0.45  # 与 linotype autofit 下限一致

# linotype.cls 的全部 Overfull 输出模式（终审 I-1）:
#   "Overfull plate: content ..."   (:557 整版溢出)
#   "Overfull main column: ..."     (:364 主栏超高截断)
#   "Overfull aside column: ..."    (:369 侧栏超高截断)
#   "Overfull mainstory: ..."       (:408 主条 vsplit 截断)
_OVERFULL_RE = re.compile(r"Overfull (?:plate: content|main column|aside column|mainstory)")


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
    if _OVERFULL_RE.search(log_text):
        report["overfull"] = True
        report["messages"].append("⚠️ 存在 Overfull 警告（plate/main column/aside column/mainstory）")
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
