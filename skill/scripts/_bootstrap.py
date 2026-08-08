"""imposer 脚本统一运行时引导（2026-08-08 最后一公里）

imposer 全部脚本纯 stdlib，但 render_presswire 需要 typst-py（仅
~/news/presswire/.venv312 安装）。为保证全流程统一解释器（行为一致 +
真单进程路径可达），每个入口脚本在 __main__ 时调用 ensure_venv()：
若 .venv312 存在且当前解释器不是它，则 os.execv 重启到 .venv312——
任何环境可跑，best-effort 统一运行时（与 render_presswire 三级后端同哲学）。

设计约束:
- 仅在 __main__ 触发（被 tests 以 import 方式加载时绝不 re-exec）
- 已处于 venv 中或 venv 不存在 → 原样继续（幂等 + 优雅降级）
- os.execv 保留 environ/stdin/stdout/stderr，脚本在 execv 前不装信号处理器
- venv 路径可用 PRESSWIRE 环境变量覆盖（与 render_presswire 一致，供测试降级路径）
"""
import os
import sys
from pathlib import Path

PRESSWIRE = Path(os.environ.get('PRESSWIRE', Path.home() / 'news' / 'presswire'))
VENV_PY = PRESSWIRE / '.venv312' / 'bin' / 'python'


def ensure_venv() -> None:
    """若可切则切到 .venv312 统一运行时；否则（已在其下/不存在）原样继续。"""
    if not VENV_PY.exists():
        return  # venv 不存在 → 降级当前解释器（如 CI 或未初始化环境）
    if os.path.realpath(sys.executable) == os.path.realpath(str(VENV_PY)):
        return  # 已在统一运行时中（幂等，防死循环）
    os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])
