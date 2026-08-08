#!/usr/bin/env python3
"""render_presswire 回归测试 — 内存通讯排版调用器（2026-08-08）

覆盖:
- 黄金路径: fixtures → 退出码 0 + converged + P1 补稿需求（JSON 报告）
- 文章不符合: 长文 autofit（字号固定 100%）→ 退出码 1 + article_mismatch
- cli 兜底: --backend cli → 同结构报告

用法:
    python3 test_render_presswire.py     # 独立运行（退出码 0=全过）
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
PRESSWIRE = Path.home() / 'news' / 'presswire'
FIXTURES = PRESSWIRE / 'tests' / 'fixtures' / 'layouts'
LATIN_PLATES = Path.home() / 'news' / 'latex' / 'examples' / 'plates'  # 真实溢出 12%
# 输出须在 --root 内（Typst 沙箱）→ 用 ~/news/presswire/tests/tmp-rpw-test/
TMP_ROOT = PRESSWIRE / 'tests' / 'tmp-rpw-test'
PY = sys.executable


def _run(plates, name, extra=None):
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    out = str(TMP_ROOT / f'{name}.pdf')
    cmd = [PY, str(SCRIPTS / 'render_presswire.py'), str(plates), out,
           '--root', str(Path.home() / 'news')]
    if extra:
        cmd += extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    res = json.loads(r.stdout) if r.stdout.strip() else {}
    return r.returncode, res, out


def _cleanup():
    import shutil
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


def test_golden_path():
    """黄金路径: JSON 报告含 converged + P1 补稿需求 + PDF 留盘。"""
    code, res, out = _run(FIXTURES, 'out')
    assert code == 0, f'退出码 {code}: {res.get("error")}'
    assert res.get('converged') is True, f'应 converged: {res}'
    assert res.get('backend') in ('typstpy', 'cli'), f'backend: {res.get("backend")}'
    assert os.path.exists(out), 'PDF 未生成'
    assert 'P1' in res.get('requests_by_plate', {}), 'fixtures 太空应发补稿单'
    assert res.get('article_mismatch') is False


def test_article_mismatch_signal():
    """长文 autofit: 退出码 1 + article_mismatch（字号固定 100% 不缩放）。"""
    code, res, _ = _run(LATIN_PLATES, 'bad')
    assert code == 1, f'长文应报文章不符合: {code}'
    assert res.get('article_mismatch') is True, f'{res}'
    assert res.get('autofit_failed') is True, f'{res}'


def test_cli_fallback():
    """--backend cli 兜底: 同结构报告（进程边界字节兼容）。"""
    code, res, _ = _run(FIXTURES, 'out-cli', extra=['--backend', 'cli'])
    assert code == 0, f'{res.get("error")}'
    assert res.get('backend') == 'cli'
    assert res.get('converged') is True
    assert 'P1' in res.get('requests_by_plate', {})


if __name__ == '__main__':
    _cleanup()
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f'[PASS] {name}')
            except Exception:
                failures += 1
                print(f'[FAIL] {name}')
                traceback.print_exc()
    _cleanup()
    sys.exit(1 if failures else 0)
