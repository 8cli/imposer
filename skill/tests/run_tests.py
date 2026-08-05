#!/usr/bin/env python3
"""imposer 回归测试 — 一键跑全部单元测试。"""
import sys, subprocess
from pathlib import Path

HERE = Path(__file__).parent
TESTS = ["test_fetch.py", "test_demand.py", "test_supply.py", "test_build_plates.py"]

def main():
    fails = 0
    for t in TESTS:
        print(f"=== {t} ===")
        r = subprocess.run([sys.executable, "-m", "pytest", str(HERE / t), "-q"],
                           capture_output=True, text=True)
        if r.returncode != 0 and "pytest" in r.stderr.lower() and "No module" in r.stderr:
            # 无 pytest 兜底: 直接 import 跑 assert
            r = subprocess.run([sys.executable, str(HERE / t)], capture_output=True, text=True)
        print(r.stdout[-300:] if r.returncode == 0 else r.stderr[-300:])
        if r.returncode != 0:
            fails += 1
    print(f"\n{'✅ 全部通过' if fails == 0 else f'❌ {fails} 个测试文件失败'}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
