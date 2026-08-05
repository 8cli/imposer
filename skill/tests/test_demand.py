#!/usr/bin/env python3
"""parse_demand 单元测试 — 无 pytest 依赖，直接 `python3 test_demand.py` 运行。

覆盖: 收敛+视觉通过+fill 解析（fill<45% 版标 SPARSE→按单补稿）、
      demand.json → requests_by_plate、plate_health 标签。
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
    h = pd.plate_health([0.8, 0.3])
    check("OK" in h[0], f"充足版应含 OK: {h[0]!r}")
    check("按单补稿" in h[1], f"稀疏版应含 按单补稿: {h[1]!r}")


def main():
    test_converged_visual_and_fills()
    test_demand_parsed()
    test_plate_health_labels()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL TESTS PASSED (3 tests)")


if __name__ == "__main__":
    main()
