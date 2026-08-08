#!/usr/bin/env python3
"""parse_demand 单元测试 — 无 pytest 依赖，直接 `python3 test_demand.py` 运行。

覆盖: 收敛+视觉通过+fill 解析（fill<45% 版标 SPARSE→按单补稿）、
      demand.json → requests_by_plate、plate_health 标签、
      presswire --json 分支（library.render 结构化，零正则，2026-08-08）。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import parse_demand as pd

STDOUT_OK = "=== autofit ===\n  ✅ 收敛 — 最终配置: paper=a3\n  ✅ 视觉验收通过\n"
LOG_OK = "Plate content: 700pt/ contentH 742pt\nPlate content: 300pt/ contentH 742pt\n"
DEMAND = {"plates": {"P2": {"fill": 0.31, "deficit_pt": 104.2,
    "requests": [{"type": "brief", "count": 2, "words": [60, 90], "topic": "ai/tech", "min_kind": "company"}]}}}

_FAILURES = []


def check(cond, msg):
    if not cond:
        _FAILURES.append(msg)


def test_converged_visual_and_fills():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "out.log"
        log.write_text(LOG_OK)
        r = pd.parse_build_output(STDOUT_OK, log)
    check(r["converged"], "期望 converged=True")
    check(r["visual_pass"] is True, f"期望 visual_pass=True，实际 {r['visual_pass']}")
    check(not r["overfull"], "期望无 overfull")
    check(abs(r["fills"][0] - 700/742) < 0.01, f"P1 fill 期望 ~700/742，实际 {r['fills'][0]}")
    check(r["fills"][1] < 0.45, f"P2 fill 期望 <0.45，实际 {r['fills'][1]}")
    # fill<45% 版标 SPARSE→按单补稿
    h = pd.plate_health(r["fills"])
    check(h[1].endswith("SPARSE→按单补稿"), f"稀疏版应标 SPARSE→按单补稿: {h[1]!r}")


def test_overfull_plate_truncated_threshold():
    """终审 I-1 + 血泪 #52：只认 plate 级 truncated>5%（vsplit 截断是设计内兜底）。

    语义（parse_demand 注释）: 仅 "Overfull plate ... truncated N" 且
    N > 5%×contentH 报 overfull；main/aside/mainstory 的 vsplit 截断
    不报（autofit 不因它压字号）。
    """
    logs_ok = [
        "Overfull plate: content 1000pt > contentH 900pt, truncated 200pt",   # >5% → 报
    ]
    for log in logs_ok:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.log"
            p.write_text(log)
            r = pd.parse_build_output(STDOUT_OK, p)  # STDOUT_OK → linotype 分支
        check(r["overfull"], f"truncated>5% 应报 overfull: {log}")
        check(any("严重溢出" in m for m in r["messages"]), f"缺 Overfull 提示: {r['messages']}")
    # 非 plate 级 / truncated≤5% / 正常日志 → 不报
    logs_no = [
        "Overfull plate: content 1000pt > contentH 900pt, truncated 10pt",    # ≤5% → 不报
        "Overfull main column: 内容 500pt > contentH 450pt，截断",             # 设计内兜底
        "Overfull aside column: 内容 300pt > contentH 250pt，截断",
        "Overfull mainstory: 内容超高，截断 40pt",
        "Plate content: 700pt/ contentH 742pt",                               # 正常日志
    ]
    for log in logs_no:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.log"
            p.write_text(log)
            r = pd.parse_build_output(STDOUT_OK, p)
        check(not r["overfull"], f"不应误报 overfull: {log}")


def test_demand_parsed():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "demand.json"
        d.write_text(json.dumps(DEMAND))
        r = pd.parse_build_output(STDOUT_OK, None, d)
    check("P2" in r["requests_by_plate"], f"requests_by_plate 缺 P2: {r['requests_by_plate']}")
    reqs = r["requests_by_plate"]["P2"]["requests"]
    check(reqs[0]["type"] == "brief", f"request type 期望 brief，实际 {reqs[0]['type']}")
    check(reqs[0]["count"] == 2, f"request count 期望 2，实际 {reqs[0]['count']}")


def test_plate_health_labels():
    """血泪 #52: FILL_MIN=0.95（严肃报纸标准）——0.8 属稀疏，0.97 才 OK。"""
    h = pd.plate_health([0.97, 0.3])
    check("OK" in h[0], f"充足版应含 OK: {h[0]!r}")
    check("按单补稿" in h[1], f"稀疏版应含 按单补稿: {h[1]!r}")
    h2 = pd.plate_health([0.8, 0.3])
    check("OK" not in h2[0], f"0.8 < 0.95 不应标 OK（血泪 #52）: {h2[0]!r}")


def test_presswire_json_branch():
    """presswire --json: library.render 结构化 stdout → 零正则解析（2026-08-08）。"""
    # 黄金路径: library.render 成功结果（模拟 cli --json stdout）
    lib_ok = {
        "engine": "presswire", "ok": True, "backend": "typstpy",
        "fills": {"plate-P1": {"fill": 0.228, "deficit_pt": 571.0, "overflow": False}},
        "demand": {"plates": {"P1": {"fill": 0.228, "deficit_pt": 533.9, "requests": [
            {"type": "deep_dive", "count": 1, "words": [400, 600],
             "topic": "world/military", "min_kind": "thinktank"}]}}},
    }
    r = pd.parse_build_output(json.dumps(lib_ok, ensure_ascii=False))
    check(r["engine"] == "presswire" and r["backend"] == "typstpy",
          f"引擎/后端识别失败: {r}")
    check(r["converged"], "黄金路径应 converged=True")
    check(not r["autofit_failed"] and not r["overfull"], "不应报失败信号")
    check(abs(r["fills"][0] - 0.228) < 0.001, f"fills 解析失败: {r['fills']}")
    check("P1" in r["requests_by_plate"], f"内嵌 demand 应解析: {r['requests_by_plate']}")
    check(any("版面健康" in m for m in r["messages"]) is False,
          "有补稿需求不应报版面健康")

    # 文章不符合（长文 autofit 字号固定）: article_mismatch → autofit_failed
    lib_mismatch = {
        "engine": "presswire", "ok": False, "code": 1, "backend": "cli",
        "article_mismatch": True, "panic": False, "fills": {},
        "demand": None, "error": "❌ 内容超出版心...",
    }
    r2 = pd.parse_build_output(json.dumps(lib_mismatch, ensure_ascii=False))
    check(r2["autofit_failed"], "文章不符合应标 autofit_failed")
    check(not r2["converged"], "文章不符合不应 converged")

    # 严重溢出 panic: panic → overfull
    lib_panic = {
        "engine": "presswire", "ok": False, "code": 1, "backend": "cli",
        "article_mismatch": False, "panic": True, "fills": {},
        "demand": None, "error": "❌ 严重溢出",
    }
    r3 = pd.parse_build_output(json.dumps(lib_panic, ensure_ascii=False))
    check(r3["overfull"], "严重溢出应标 overfull")

    # 非 JSON stdout（旧 presswire 正则分支）不受影响
    r4 = pd.parse_build_output("  plate-P1: fill 0.228 (太空)\n✅ 已生成 out.pdf（2 版）\n")
    check(r4["engine"] == "presswire" and r4["converged"],
          f"旧正则分支回归: {r4}")


def main():
    test_converged_visual_and_fills()
    test_demand_parsed()
    test_plate_health_labels()
    test_overfull_plate_truncated_threshold()
    test_presswire_json_branch()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL TESTS PASSED (5 tests)")


if __name__ == "__main__":
    main()
