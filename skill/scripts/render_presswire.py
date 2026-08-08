#!/usr/bin/env python3
"""imposer → presswire 排版调用器（内存通讯，2026-08-08）

一步替代 SKILL.md 旧两步（cli 编译 + parse_demand 解析）:
    cd ~/news/presswire && python3 -m presswire.cli $PLATES $OUT --root ~/news \
        --docopts "..." --demand > build.log 2>&1
    python3 parse_demand.py build.log --demand demand.json

用法:
    python3 render_presswire.py <plates_dir> <output.pdf> \
        [--root DIR] [--docopts "paper=a3,landscape,plates=2,columns=3,fill_min=0.95"] \
        [--demand] [--no-autofit] [--backend auto|typstpy|cli]

输出: stdout 纯净 JSON（parse_demand 同构报告 + code/article_mismatch/panic/pdf）。
退出码: 0 成功 / 1 编译失败（文章不符合或严重溢出，JSON 含信号）/ 2 参数错误。

后端三级递进（--backend auto 默认）:
  1. inmem 单进程: 当前 python 有 typst-py（在 .venv312 下运行）→
     直接 import presswire.library.render，typst 进程内编译——真正内存通讯
  2. inmem 半内存: 当前无 typst-py（系统 3.14）但 ~/news/presswire/.venv312
     存在 → subprocess .venv312 python 内嵌渲染（无 typst CLI subprocess、
     无日志正则，一次 JSON 返回）
  3. cli 兜底: subprocess typst CLI --json（进程边界，字节兼容）
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
PRESSWIRE = Path(os.environ.get('PRESSWIRE', Path.home() / 'news' / 'presswire'))
VENV_PY = PRESSWIRE / '.venv312' / 'bin' / 'python'
DEFAULT_DOCOPTS = 'paper=a3,landscape,plates=2,columns=3'

# 半内存模式内嵌脚本: .venv312 python 内 import presswire.library 渲染
_INMEM_SCRIPT = r'''
import json, sys
sys.path.insert(0, {repo!r})
from presswire.library import render
res = render(
    plates_dir={plates!r}, output={out!r}, docopts={docopts!r},
    autofit={autofit}, root={root!r}, backend='typstpy',
    write_demand={demand})
print(json.dumps(res, ensure_ascii=False))
'''


def _finish(res: dict) -> dict:
    """library.render 结果 → parse_demand 同构报告（合并健康判定字段）。"""
    sys.path.insert(0, str(SKILL_SCRIPTS))
    from parse_demand import _from_library_json
    report = _from_library_json(res)
    report['code'] = res.get('code', 0 if res.get('ok') else 1)
    report['article_mismatch'] = res.get('article_mismatch', False)
    report['panic'] = res.get('panic', False)
    report['pdf'] = res.get('pdf')
    return report


def _render_inmem_single(args) -> dict:
    """真单进程: 当前 python 有 typst-py（.venv312 下运行）→ 直接 import。"""
    sys.path.insert(0, str(PRESSWIRE))
    from presswire.library import render
    res = render(
        plates_dir=args.plates_dir, output=args.output, docopts=args.docopts,
        autofit=not args.no_autofit, root=args.root,
        backend='typstpy', write_demand=args.demand)
    return _finish(res)


def _render_inmem_subprocess(args) -> dict:
    """半内存: 系统 python 无 typst-py → 委托 .venv312 python 进程内渲染。"""
    code = _INMEM_SCRIPT.format(
        repo=str(PRESSWIRE), plates=args.plates_dir, out=args.output,
        docopts=args.docopts, autofit=not args.no_autofit,
        root=args.root, demand=args.demand)
    r = subprocess.run([str(VENV_PY), '-c', code],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {'engine': 'presswire', 'ok': False, 'code': r.returncode,
                'converged': False, 'autofit_failed': False, 'overfull': False,
                'fills': [], 'requests_by_plate': {}, 'messages': [],
                'article_mismatch': False, 'panic': False, 'pdf': '',
                'error': f'inmem 渲染失败: {r.stderr[:300]}'}
    return _finish(json.loads(r.stdout))


def _render_cli(args) -> dict:
    """兜底: subprocess typst CLI --json（进程边界，字节兼容）。"""
    cmd = [sys.executable, '-m', 'presswire.cli',
           args.plates_dir, args.output, '--json', '--backend', 'cli',
           '--root', args.root, '--docopts', args.docopts]
    if args.demand:
        cmd.append('--demand')
    if args.no_autofit:
        cmd.append('--no-autofit')
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=str(PRESSWIRE))
    if not r.stdout.strip():
        return {'engine': 'presswire', 'ok': False, 'code': r.returncode,
                'converged': False, 'autofit_failed': False, 'overfull': False,
                'fills': [], 'requests_by_plate': {}, 'messages': [],
                'article_mismatch': False, 'panic': False, 'pdf': '',
                'error': f'cli 渲染失败: {r.stderr[:300]}'}
    return _finish(json.loads(r.stdout))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plates_dir', help='plates/ 目录')
    ap.add_argument('output', help='输出 .pdf 路径')
    ap.add_argument('--root', default=str(PRESSWIRE),
                    help='Typst 项目根（日报场景 ~/news）')
    ap.add_argument('--docopts', default=DEFAULT_DOCOPTS)
    ap.add_argument('--demand', action='store_true',
                    help='写 demand.json（无需求清旧单）')
    ap.add_argument('--no-autofit', action='store_true')
    ap.add_argument('--backend', default='auto',
                    choices=['auto', 'typstpy', 'cli'])
    args = ap.parse_args(argv)

    # 后端分派（三级递进）
    backend = args.backend
    try:
        import typst  # noqa: F401
        have_typst = True
    except ImportError:
        have_typst = False
    if backend == 'auto':
        backend = 'typstpy' if have_typst else \
                  ('typstpy-sub' if VENV_PY.exists() else 'cli')

    if backend == 'typstpy' and have_typst:
        report = _render_inmem_single(args)
    elif backend in ('typstpy', 'typstpy-sub') and VENV_PY.exists():
        report = _render_inmem_subprocess(args)
    else:
        report = _render_cli(args)

    print(json.dumps(report, ensure_ascii=False))
    return int(report.get('code', 1))


if __name__ == '__main__':
    sys.exit(main())
