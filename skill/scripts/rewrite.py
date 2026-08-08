#!/usr/bin/env python3
"""imposer 改写压缩器 — 用 LLM（Claude）把报道压缩到目标词数。

铁律（用户决策 2026-08-05）:
  - 只允许在版面紧张情况下压缩概括，**不允许扩写**
  - target_words 是硬上限：改写后词数 ≤ target_words[1]
  - 忠实原文：不新增事实、不编造来源、保留记者名与站点归属

用法: python3 rewrite.py <summary> <min_words> <max_words> [--source NAME] [--title TITLE]
输出: 改写后的压缩文本（stdout）
依赖: anthropic 包（ANTHROPIC_API_KEY 环境变量）或 Claude CLI
"""
import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_MODEL = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-5")
MAX_INPUT_CHARS = 6000  # 超长输入截断（防止 token 超限）


def _call_anthropic(system: str, prompt: str, model: str, max_tokens: int = 800) -> str:
    """调 Anthropic Messages API。失败时抛 RuntimeError。

    兼容两种返回：
      - 标准 SDK：Message 对象（content 是 TextBlock 列表）
      - 本地代理（ANTHROPIC_BASE_URL 指向 SSE 转发）：原始 SSE 流字符串
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 包未安装（pip install anthropic）")

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # 情况 1: 本地代理返回 SSE 流字符串（data: {json} 行）
    if isinstance(msg, str):
        return _parse_sse_text(msg)
    # 情况 2: 标准 SDK Message 对象
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.strip()
        return "".join(b.get("text", "") for b in content if isinstance(b, dict)).strip()
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = []
    for b in content:
        if isinstance(b, str):
            parts.append(b)
        elif hasattr(b, "text"):
            parts.append(b.text)
        elif isinstance(b, dict):
            parts.append(b.get("text", ""))
    return "".join(parts).strip()


def _parse_sse_text(sse: str) -> str:
    """解析 SSE 流字符串（data: {...} 行）→ 提取 text_delta 拼接。"""
    texts = []
    for line in sse.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        try:
            evt = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "content_block_delta":
            delta = evt.get("delta", {})
            if delta.get("type") == "text_delta":
                texts.append(delta.get("text", ""))
    return "".join(texts).strip()


def _call_claude_cli(system: str, prompt: str) -> str:
    """兜底：Claude CLI（--print 模式，--output-format stream-json 提取 assistant 消息）。"""
    r = subprocess.run(
        ["claude", "--print", "--verbose", "--output-format", "stream-json",
         "-p", prompt, "--system-prompt", system],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Claude CLI 失败: {r.stderr[:200]}")
    # stream-json 每行一个事件，取 assistant message 的 text content
    texts = []
    for line in r.stdout.splitlines():
        try:
            evt = json.loads(line)
            if evt.get("type") == "content_block_delta" and evt.get("delta", {}).get("type") == "text_delta":
                texts.append(evt["delta"]["text"])
        except (json.JSONDecodeError, KeyError):
            continue
    if not texts:
        raise RuntimeError(f"Claude CLI 无 assistant 输出: {r.stdout[:200]}")
    return "".join(texts).strip()


def rewrite(summary: str, min_words: int, max_words: int,
            source: str = "", title: str = "", model: str = DEFAULT_MODEL) -> str:
    """压缩 summary 到 [min_words, max_words] 词区间。永不扩写（输入短则原样返回）。"""
    input_words = len(summary.split())
    if input_words <= max_words:
        return summary.strip()  # 已达标，不扩写（铁律）

    system = (
        "You are a newspaper copy editor compressing a story to fit a fixed column. "
        "RULES (absolute):\n"
        f"1. Compress to {min_words}-{max_words} words. NEVER exceed {max_words} words.\n"
        "2. NEVER expand or add facts beyond the source. Only condense what is given.\n"
        "3. Keep the lead (first paragraph) information: who/what/where/when.\n"
        "4. Preserve attribution phrases (e.g. 'Reuters reported', 'according to X').\n"
        "5. Output only the compressed story text, no preamble, no quotes around it."
    )
    prompt = f"Title: {title}\nSource: {source}\n\nStory to compress:\n{summary[:MAX_INPUT_CHARS]}"
    try:
        text = _call_anthropic(system, prompt, model)
    except Exception as e:
        print(f"  ⚠️ Anthropic API 失败（{e}），降级 Claude CLI", file=sys.stderr)
        text = _call_claude_cli(system, prompt)
    # 硬性词数钳制：LLM 偶尔超限，强制截断到 max_words（提取式兜底）
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    if not text.strip():
        # LLM 返回空（如输入无意义填充）：提取式兜底——截取原文首段到 max_words
        text = " ".join(summary.split()[:max_words])
    return text.strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", help="待压缩的报道原文/摘要")
    ap.add_argument("min_words", type=int, help="目标词数下限")
    ap.add_argument("max_words", type=int, help="目标词数上限（硬上限，不超）")
    ap.add_argument("--source", default="", help="信源站点名（保留归属）")
    ap.add_argument("--title", default="", help="报道标题（供上下文）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="LLM 模型")
    args = ap.parse_args()
    print(rewrite(args.summary, args.min_words, args.max_words,
                  args.source, args.title, args.model))
