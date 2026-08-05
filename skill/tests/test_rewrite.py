#!/usr/bin/env python3
"""rewrite 单元测试 — 无 pytest 依赖，直接 `python3 test_rewrite.py` 运行。

覆盖（终审 I-6）: 铁律三态——短文本逐字返回（不调 LLM）、长文本压缩到硬上限、
LLM 返回空时提取式兜底；以及 API+CLI 双失败 → RuntimeError 上抛（由 supply 容错）。
通过注入假 _call_anthropic 验证，不碰真实网络/API。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rewrite as rw

_FAILURES = []


def check(cond, msg):
    if not cond:
        _FAILURES.append(msg)


def test_short_input_verbatim_no_llm():
    """铁律：输入 ≤ max_words 逐字返回，且不调用 LLM。"""
    calls = []
    orig = rw._call_anthropic
    rw._call_anthropic = lambda *a, **k: calls.append(a) or "SHOULD NOT BE CALLED"
    try:
        short = "A short brief about China's trade policy. Five words total here."
        out = rw.rewrite(short, 20, 60, "Xinhua", "Test title")
        check(out == short.strip(), f"短文本应逐字返回，实际 {out!r}")
        check(calls == [], "短文本不应调用 LLM（铁律：只压缩不扩写）")
    finally:
        rw._call_anthropic = orig


def test_long_input_compressed_and_hard_capped():
    """长文本 → LLM 压缩；若 LLM 输出仍超限，硬钳制到 max_words（硬上限）。"""
    long_text = "word " * 300  # 600 词
    # ① LLM 返回合规压缩（60-90 词区间内）
    orig = rw._call_anthropic
    rw._call_anthropic = lambda *a, **k: "compressed story " * 20  # 40 词
    try:
        out = rw.rewrite(long_text, 30, 90, "NASA", "Rocket")
        check(20 <= len(out.split()) <= 90, f"压缩结果应在 [min,max] 内：{len(out.split())} 词")
    finally:
        rw._call_anthropic = orig
    # ② LLM 返回超限输出 → 硬钳制到 max_words
    orig = rw._call_anthropic
    rw._call_anthropic = lambda *a, **k: "overflow " * 200  # 400 词 > 90
    try:
        out = rw.rewrite(long_text, 30, 90, "NASA", "Rocket")
        check(len(out.split()) == 90, f"超限输出应硬截断到 90 词，实际 {len(out.split())}")
        check("overflow" in out, "截断应保留原文内容")
    finally:
        rw._call_anthropic = orig


def test_empty_llm_output_extractive_fallback():
    """LLM 返回空 → 提取式兜底：截取原文首 max_words 词。"""
    long_text = "The quick brown fox jumps over the lazy dog. " * 20
    orig = rw._call_anthropic
    rw._call_anthropic = lambda *a, **k: ""
    try:
        out = rw.rewrite(long_text, 10, 30, "GT", "Fallback")
        words = out.split()
        check(0 < len(words) <= 30, f"空输出兜底应为原文首 N 词，实际 {len(words)} 词")
        check("quick" in words and "dog" in words, f"兜底应保留原文内容：{out[:60]!r}")
    finally:
        rw._call_anthropic = orig


def test_both_apis_fail_raises():
    """API + CLI 双失败 → RuntimeError 上抛（由 supply_requests 容错，不炸整轮）。"""
    orig_api, orig_cli = rw._call_anthropic, rw._call_claude_cli
    rw._call_anthropic = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
    rw._call_claude_cli = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cli down"))
    try:
        raised = False
        try:
            rw.rewrite("word " * 200, 30, 90, "Src", "T")
        except RuntimeError as e:
            raised = True
            check("cli down" in str(e), f"应上抛 CLI 失败原因，实际 {e}")
        check(raised, "API+CLI 双失败应抛 RuntimeError")
    finally:
        rw._call_anthropic, rw._call_claude_cli = orig_api, orig_cli


def test_cli_fallback_on_api_failure():
    """API 失败 → 降级 Claude CLI（注入假 CLI 输出验证）。"""
    long_text = "word " * 200
    orig_api, orig_cli = rw._call_anthropic, rw._call_claude_cli
    rw._call_anthropic = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
    rw._call_claude_cli = lambda *a, **k: "cli compressed " * 15  # 30 词
    try:
        out = rw.rewrite(long_text, 30, 90, "Src", "T")
        check("cli compressed" in out, f"API 失败应降级 CLI，实际 {out[:40]!r}")
    finally:
        rw._call_anthropic, rw._call_claude_cli = orig_api, orig_cli


def main():
    test_short_input_verbatim_no_llm()
    test_long_input_compressed_and_hard_capped()
    test_empty_llm_output_extractive_fallback()
    test_both_apis_fail_raises()
    test_cli_fallback_on_api_failure()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL TESTS PASSED (5 tests)")


if __name__ == "__main__":
    main()
