#!/usr/bin/env python3
"""imposer 回归测试 — 一键跑全部单元测试。"""
import sys, subprocess
from pathlib import Path

HERE = Path(__file__).parent
TESTS = ["test_fetch.py", "test_demand.py", "test_supply.py", "test_build_plates.py",
         "test_rewrite.py", "test_render_presswire.py"]

def main():
    fails = 0
    for t in TESTS:
        print(f"=== {t} ===")
        # 统一直接执行：所有 test 文件自带 __main__ 收集 + check() 失败报告。
        # 不走 pytest——pytest 收集 test_* 函数时 check() 失败不抛异常 → 假绿
        # （2026-08-08 血泪：3.14 有 pytest 假绿 5 passed，.venv312 无 pytest
        #  真红 FAILED 1 项，双模式结果不一致；直接执行是唯一可靠模式）。
        r = subprocess.run([sys.executable, str(HERE / t)], capture_output=True, text=True)
        print(r.stdout[-300:] + r.stderr[-300:])
        if r.returncode != 0:
            fails += 1
    print(f"\n{'✅ 全部通过' if fails == 0 else f'❌ {fails} 个测试文件失败'}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
