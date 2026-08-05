#!/usr/bin/env python3
"""supply 单元测试 — 无 pytest 依赖，直接 `python3 test_supply.py` 运行。

覆盖: match_cache 跳过 used 素材 + 按 min_kind 过滤（素材层级优于或等于需求最差层级即可）、
      supply_requests 按 demand 供给 → {plate: [补充素材]} 且每条含 request 引用。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import supply as sp

CACHE = {
    "P2": [
        {"title": "OpenAI model", "url": "https://e.com/1", "summary": "word " * 70, "source": "OpenAI", "kind": "company"},
        {"title": "Used item", "url": "https://e.com/2", "summary": "word " * 30, "source": "Alibaba", "kind": "china-ai", "used": True},
        {"title": "Short one", "url": "https://e.com/3", "summary": "word " * 15, "source": "Yahoo", "kind": "aggregator"},
    ]
}
DEMAND = {"plates": {"P2": {"fill": 0.31, "requests": [
    {"type": "brief", "count": 1, "words": [60, 90], "topic": "ai/tech", "min_kind": "company"}]}}}

# 按 kind 过滤的正例：min_kind=aggregator 允许层级 ≤7，western(8) 被排除
CACHE_KIND = [
    {"title": "Western story", "url": "https://w.com/1", "summary": "word " * 70, "source": "WSJ", "kind": "western"},
    {"title": "Agg story", "url": "https://a.com/1", "summary": "word " * 70, "source": "Yahoo", "kind": "aggregator"},
]

_FAILURES = []


def check(cond, msg):
    if not cond:
        _FAILURES.append(msg)


def test_match_cache_skips_used_and_filters_kind():
    req = DEMAND["plates"]["P2"]["requests"][0]
    used = set()
    # ① 首个匹配：company(3) ≤ company(3) 且 70 词在 [60,90] → OpenAI；used 的 Alibaba 被跳过
    item = sp.match_cache(req, CACHE["P2"], used)
    check(item is not None and item["title"] == "OpenAI model",
          f"期望命中 OpenAI model（company 优先），实际 {item and item['title']!r}")
    check(item["url"] != "https://e.com/2", "used 素材（e.com/2）不应被再次匹配")
    check("https://e.com/2" not in used, "used 素材不应被标记进 used 集合")
    check("https://e.com/1" in used, "已命中素材应记入 used，避免重复供给")
    # ② 再匹配一次：剩余 items 全被 used/字数/kind 过滤 → None
    check(sp.match_cache(req, CACHE["P2"], used) is None,
          "剩余素材（used/字数不足/kind 不合）应无可匹配")
    # ③ kind 过滤正例：min_kind=aggregator 时 western(8) 被排除，aggregator(7) 命中
    item = sp.match_cache({"words": [60, 90], "min_kind": "aggregator"}, CACHE_KIND, set())
    check(item is not None and item["title"] == "Agg story",
          f"min_kind=aggregator 应排除 western 命中 Agg story，实际 {item and item['title']!r}")


def test_supply_requests_returns_matched():
    results = sp.supply_requests(DEMAND, CACHE, {}, Path("."))
    check("P2" in results, f"结果应含 P2 版：{results.keys()}")
    check(len(results["P2"]) == 1, f"P2 期望供给 1 条，实际 {len(results['P2'])}")
    check(results["P2"][0]["title"] == "OpenAI model",
          f"P2 素材应为 OpenAI model，实际 {results['P2'][0]['title']!r}")
    check(results["P2"][0]["request"]["type"] == "brief",
          "每条补充素材应携带 request 引用（type=brief）")
    check(results["P2"][0]["request"] is DEMAND["plates"]["P2"]["requests"][0],
          "request 引用应为 demand 中的原始 request 对象")


def test_supply_requests_fetch_fn_no_duplicate():
    # 审查修复 I-1：fetch_fn 返回的素材必须记入 used，同一 URL 不得重复供给
    demand = {"plates": {"P3": {"requests": [
        {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "company"}]}}}
    calls = []

    def fetch_fn(plate, req, sources, out_dir):
        calls.append(plate)
        return {"title": "Fetched story", "url": "https://f.com/1",
                "summary": "word " * 70, "source": "Fetcher", "kind": "company"}

    results = sp.supply_requests(demand, {}, {}, Path("."), fetch_fn)
    check(len(results["P3"]) == 1,
          f"fetch 重复 URL（count=2）应只供给 1 条，实际 {len(results['P3'])}")
    check(results["P3"][0]["url"] == "https://f.com/1", "供给素材应为 fetch 结果")
    check(len(calls) == 2, f"fetch_fn 应按 count 调用 2 次，实际 {len(calls)}")
    # 混合路径：缓存 1 条 + fetch 补第 2 条，fetch 结果记 used 后不再与缓存冲突
    cache = {"P3": [{"title": "Cached story", "url": "https://c.com/1",
                     "summary": "word " * 70, "source": "Cacher", "kind": "company"}]}
    results = sp.supply_requests(demand, cache, {}, Path("."), fetch_fn)
    check(len(results["P3"]) == 2, f"缓存1条+fetch1条 期望 2 条，实际 {len(results['P3'])}")
    urls = {i["url"] for i in results["P3"]}
    check(len(urls) == 2, f"混合路径不应有重复 URL：{urls}")


def main():
    test_match_cache_skips_used_and_filters_kind()
    test_supply_requests_returns_matched()
    test_supply_requests_fetch_fn_no_duplicate()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL TESTS PASSED (3 tests)")


if __name__ == "__main__":
    main()
