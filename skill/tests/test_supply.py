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


def test_match_cache_skips_stale():
    """终审 I-3：过期素材（date >30 天）不参与供给——成版同样排除，避免供给作废。"""
    req = {"words": [60, 90], "min_kind": "china-official"}
    cache = [
        {"title": "Fresh story", "url": "https://f.com/1", "summary": "word " * 70,
         "source": "GT", "kind": "china-official",
         "date": "Wed, 05 Aug 2026 10:00:00 GMT"},
        {"title": "Archive story", "url": "https://a.com/1", "summary": "word " * 70,
         "source": "GT", "kind": "china-official",
         "date": "Mon, 12 Dec 2017 10:00:00 GMT"},
    ]
    item = sp.match_cache(req, cache, set())
    check(item is not None and item["title"] == "Fresh story",
          f"应跳过 2017 归档稿命中新稿，实际 {item and item['title']!r}")
    item2 = sp.match_cache(req, [cache[1]], set())
    check(item2 is None, "只剩归档稿时不应供给")


def test_match_cache_skips_stale_via_url_date():
    """终审 I-3 加固：date 为空的 2017 归档稿（China Daily URL 日期路径）同样不供给。"""
    req = {"words": [60, 90], "min_kind": "china-official"}
    cache = [
        {"title": "Archive no-date", "url": "http://www.chinadaily.com.cn/a/201712/12/WS5a2f23eba3108bc8c67219f0.html",
         "summary": "word " * 70, "source": "China Daily", "kind": "china-official", "date": ""},
        {"title": "Fresh no-date", "url": "https://www.globaltimes.cn/page/202608/1367571.shtml",
         "summary": "word " * 70, "source": "GT", "kind": "china-official", "date": ""},
    ]
    item = sp.match_cache(req, cache, set())
    check(item is not None and item["title"] == "Fresh no-date",
          f"应跳过 date 空但 URL 是 2017 归档的条目，实际 {item and item['title']!r}")
    item2 = sp.match_cache(req, [cache[0]], set())
    check(item2 is None, "只剩 URL 归档条目时不应供给")


def test_match_cache_filters_off_topic():
    """终审 I-4：demand 的 topic 端到端生效——明显不相关标题（如 P4 纪念稿）不补稿。"""
    req = {"words": [60, 90], "min_kind": "china-official", "topic": "china-tech"}
    cache = [
        {"title": "Memorial Day a time to remember", "url": "https://m.com/1", "summary": "word " * 70,
         "source": "China Daily", "kind": "china-official"},
        {"title": "China launches chip export controls", "url": "https://c.com/1", "summary": "word " * 70,
         "source": "GT", "kind": "china-official"},
    ]
    item = sp.match_cache(req, cache, set())
    check(item is not None and item["title"] == "China launches chip export controls",
          f"P4 纪念稿应按 topic 过滤，实际 {item and item['title']!r}")
    # 只剩纪念稿 → 不供给（宁缺勿滥，诚实报告）
    item2 = sp.match_cache(req, [cache[0]], set())
    check(item2 is None, "题材不匹配素材不应兜底供给")


def test_supply_marks_used_persistent():
    """终审 C-1b：供给输出携带 used=True，回写缓存后第 2 轮不重复供给同一批素材。"""
    demand = {"plates": {"P2": {"requests": [
        {"type": "brief", "count": 2, "words": [60, 90], "topic": "ai/tech", "min_kind": "company"}]}}}
    cache = {"P2": [
        {"title": "One", "url": "https://e.com/1", "summary": "word " * 70, "source": "S", "kind": "company"},
        {"title": "Two", "url": "https://e.com/2", "summary": "word " * 70, "source": "S", "kind": "company"},
        {"title": "Three", "url": "https://e.com/3", "summary": "word " * 70, "source": "S", "kind": "company"},
    ]}
    # 第 1 轮供给
    r1 = sp.supply_requests(demand, cache, {}, Path("."))
    check(all(i.get("used") for i in r1["P2"]), "供给输出每条都应带 used=True")
    # 回写缓存（SKILL.md 循环的做法）：附加供给结果；原 cache 条目已被 match_cache 原地标记 used
    for i in r1["P2"]:
        cache["P2"].append(i)
    used_urls = {x["url"] for x in cache["P2"] if x.get("used")}
    # 第 2 轮供给：应匹配到第 3 条（未被 used），而非重复前两条
    r2 = sp.supply_requests(demand, cache, {}, Path("."))
    urls2 = [i["url"] for i in r2["P2"]]
    check(urls2 == ["https://e.com/3"], f"第 2 轮应供给新素材 e.com/3，实际 {urls2}")


def test_supply_agent_path_keeps_rewrite_markers():
    """任务一：agent 执行改写为主路径——rewrite_fn 默认 None（不传），
    needs_rewrite + target_words 标注保留，作为 agent 知道"改哪条、改到多少词"的信号。"""
    demand = {"plates": {"P3": {"requests": [
        {"type": "brief", "count": 1, "words": [250, 400], "topic": "space", "min_kind": "agency"}]}}}
    cache = {"P3": [{"title": "Short NASA item", "url": "https://e.com/ns1", "summary": "word " * 60,
                     "source": "NASA", "kind": "agency"}]}
    results = sp.supply_requests(demand, cache, {}, Path("."))  # rewrite_fn=None（agent 路径）
    item = results["P3"][0]
    check(item.get("needs_rewrite") is True,
          f"agent 路径应保留 needs_rewrite 标注，实际 {item.get('needs_rewrite')}")
    check(item.get("target_words") == [250, 400],
          f"target_words 应保留供 agent 改写，实际 {item.get('target_words')}")
    check(item.get("used") is True, "供给素材仍应标记 used（防重复供给）")


def test_supply_rewrite_failure_keeps_original():
    """终审 I-6：rewrite_fn 抛异常 → 保留原素材 + 警告，不中断整轮供给。"""
    demand = {"plates": {"P2": {"requests": [
        {"type": "main", "count": 1, "words": [250, 400], "topic": "ai/tech", "min_kind": "company"}]}}}
    cache = {"P2": [{"title": "Long story", "url": "https://e.com/l", "summary": "word " * 60,
                     "source": "OpenAI", "kind": "company"}]}

    def bad_rewrite(*a, **k):
        raise RuntimeError("LLM unavailable")

    results = sp.supply_requests(demand, cache, {}, Path("."), rewrite_fn=bad_rewrite)
    check(len(results["P2"]) == 1, "改写失败不应丢弃素材")
    check(results["P2"][0]["summary"].startswith("word"), "改写失败应保留原摘要")
    check(results["P2"][0].get("used") is True, "改写失败素材仍应标记 used（防重复供给）")


def test_match_cache_rewrite_fallback():
    """精确规格匹配失败 → 返回最接近素材 + needs_rewrite（AI 改写压缩）。"""
    req = {"words": [250, 400], "min_kind": "china-official"}
    # 无 250-400 词素材，只有 60 词 china-official → 应 fallback 并标 needs_rewrite
    cache = [{"title": "China story", "url": "https://c.com/1", "summary": "word " * 60,
              "source": "Global Times", "kind": "china-official"}]
    item = sp.match_cache(req, cache, set(), allow_rewrite=True)
    check(item is not None and item.get("needs_rewrite") is True,
          f"期望 fallback 素材 + needs_rewrite，实际 {item and item.get('needs_rewrite')}")
    check(item.get("target_words") == [250, 400], "target_words 应为需求词数区间")

    # allow_rewrite=False 时不 fallback
    item2 = sp.match_cache(req, cache, set(), allow_rewrite=False)
    check(item2 is None, "allow_rewrite=False 时精确匹配失败应返回 None")


def test_supply_fulltext_fetched_for_main_spec():
    """全文优先（2026-08-05）：主条规格缓存只有短摘要 → 抓全文附到素材上，agent 从全文压缩。"""
    demand = {"plates": {"P3": {"requests": [
        {"type": "main", "count": 1, "words": [250, 400], "topic": "space", "min_kind": "agency"}]}}}
    cache = {"P3": [{"title": "Short NASA item", "url": "https://e.com/ns1", "summary": "word " * 60,
                     "source": "NASA", "kind": "agency"}]}
    calls = []

    def fulltext_fn(url):
        calls.append(url)
        return "word " * 800  # 全文 800 词

    results = sp.supply_requests(demand, cache, {}, Path("."), fulltext_fn=fulltext_fn)
    item = results["P3"][0]
    check(calls == ["https://e.com/ns1"], f"应抓最优候选全文：{calls}")
    check(item.get("fulltext") is not None, "主条规格应抓全文")
    check(len(item["fulltext"].split()) == 800, f"fulltext 应为 800 词，实际 {len(item['fulltext'].split())}")
    check(item.get("needs_rewrite") is True, "全文达标仍需 needs_rewrite（压缩全文回填 summary）")
    check(item.get("target_words") == [250, 400], "target_words 应保留供 agent 压缩")


def test_supply_fulltext_fallback_summary():
    """全文抓取失败/太短 → 保留摘要兜底（诚实薄主条，不中断整轮）。"""
    demand = {"plates": {"P3": {"requests": [
        {"type": "main", "count": 1, "words": [250, 400], "topic": "space", "min_kind": "agency"}]}}}
    cache = {"P3": [{"title": "Short item", "url": "https://e.com/ns1", "summary": "word " * 60,
                     "source": "NASA", "kind": "agency"}]}

    def bad_fulltext(url):
        raise RuntimeError("page blocked")

    results = sp.supply_requests(demand, cache, {}, Path("."), fulltext_fn=bad_fulltext)
    check(len(results["P3"]) == 1, "全文失败不应丢素材")
    check("fulltext" not in results["P3"][0], "全文失败不应带 fulltext")
    check(results["P3"][0]["summary"].startswith("word"), "应保留摘要兜底")


def test_supply_no_fulltext_for_brief():
    """简讯规格（下限 <250 词）不抓全文——摘要本够用，避免无谓请求。"""
    calls = []
    demand = {"plates": {"P3": {"requests": [
        {"type": "brief", "count": 1, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
    cache = {"P3": [{"title": "Brief item", "url": "https://e.com/ns1", "summary": "word " * 70,
                     "source": "NASA", "kind": "agency"}]}

    def fulltext_fn(url):
        calls.append(url)
        return "word " * 500

    results = sp.supply_requests(demand, cache, {}, Path("."), fulltext_fn=fulltext_fn)
    check(len(calls) == 0, f"简讯不应触发全文抓取：{calls}")
    check(len(results["P3"]) == 1 and "fulltext" not in results["P3"][0], "简讯不应带 fulltext")


def test_supply_rewrite_uses_fulltext():
    """rewrite_fn（headless 兜底）路径：有 fulltext 时压缩全文而非短摘要。"""
    demand = {"plates": {"P3": {"requests": [
        {"type": "main", "count": 1, "words": [250, 400], "topic": "space", "min_kind": "agency"}]}}}
    cache = {"P3": [{"title": "Item", "url": "https://e.com/ns1", "summary": "word " * 60,
                     "source": "NASA", "kind": "agency"}]}
    seen = {}

    def fulltext_fn(url):
        return "word " * 800

    def rewrite_fn(text, lo, hi, source, title):
        seen["input_words"] = len(text.split())
        return "word " * 300

    results = sp.supply_requests(demand, cache, {}, Path("."),
                                 fulltext_fn=fulltext_fn, rewrite_fn=rewrite_fn)
    check(seen.get("input_words") == 800,
          f"rewrite 应压缩全文而非摘要，实际输入 {seen.get('input_words')} 词")
    check(results["P3"][0]["summary"].count("word") == 300, "改写后 summary 应为压缩全文")
    check("fulltext" in results["P3"][0], "fulltext 保留（缓存富集，供后续轮直接匹配）")


def test_match_cache_uses_fulltext_words():
    """缓存已有 fulltext 时按全文词数匹配主条规格（跨轮复用，不重复抓全文）。"""
    req = {"words": [250, 400], "min_kind": "agency"}
    cache = [{"title": "Long article", "url": "https://e.com/l1", "summary": "word " * 60,
              "source": "NASA", "kind": "agency", "fulltext": "word " * 300}]
    item = sp.match_cache(req, cache, set())
    check(item is not None, "fulltext 300 词应命中 main 规格")
    check(item.get("needs_rewrite") is True, "全文命中仍需 needs_rewrite（压缩回填 summary）")
    check(item.get("target_words") == [250, 400], "target_words 应保留")


def test_match_cache_tech_gate_p4():
    """P4 题材门：国际金融稿不补科技版；国际科技稿命中；只剩金融稿不兜底。"""
    req = {"words": [250, 400], "min_kind": "tech-media", "topic": "tech"}
    cache = [
        {"title": "Brazil to become regular borrower in China", "url": "https://e.com/b1",
         "summary": "word " * 300, "source": "SCMP", "kind": "independent"},
        {"title": "Nuclear fusion reactor achieves record output", "url": "https://e.com/f1",
         "summary": "word " * 300, "source": "Phys.org", "kind": "tech-media"},
    ]
    item = sp.match_cache(req, cache, set())
    check(item is not None and item["title"].startswith("Nuclear fusion"),
          f"国际金融稿应按题材门排除，命中科技稿：{item and item['title'][:40]!r}")
    item2 = sp.match_cache(req, [cache[0]], set())
    check(item2 is None, "只剩国际金融稿时不兜底供给")


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
    test_match_cache_rewrite_fallback()
    test_supply_requests_fetch_fn_no_duplicate()
    test_match_cache_skips_stale()
    test_match_cache_filters_off_topic()
    test_supply_marks_used_persistent()
    test_supply_rewrite_failure_keeps_original()
    test_supply_agent_path_keeps_rewrite_markers()
    test_match_cache_skips_stale_via_url_date()
    test_supply_fulltext_fetched_for_main_spec()
    test_supply_fulltext_fallback_summary()
    test_supply_no_fulltext_for_brief()
    test_supply_rewrite_uses_fulltext()
    test_match_cache_uses_fulltext_words()
    test_match_cache_tech_gate_p4()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL TESTS PASSED (16 tests)")


if __name__ == "__main__":
    main()
