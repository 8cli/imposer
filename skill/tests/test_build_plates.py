#!/usr/bin/env python3
"""build_plates 单元测试 — 无 pytest 依赖，直接 `python3 test_build_plates.py` 运行。

覆盖: 主条亲中优先、归属（有/无记者）、linotype 字段齐全、tex_escape 字符集、
      写 plates 文件；外加空摘要兜底（page 源）与全空版跳过。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_plates as bp

NEWS = [
    {"title": "Main China Story: 5% Growth & Trade", "url": "https://e.com/1", "summary": "Para one. Para two. Para three. Para four. Para five.", "author": "A", "source": "Global Times", "kind": "china-official"},
    {"title": "Think Tank Analysis", "url": "https://e.com/2", "summary": "Deep analysis paragraph.", "author": "B", "source": "CSIS", "kind": "thinktank"},
    {"title": "Brief One", "url": "https://e.com/3", "summary": "Short.", "author": "", "source": "Al Jazeera", "kind": "independent"},
    {"title": "Brief Two", "url": "https://e.com/4", "summary": "Short two.", "author": "", "source": "Reuters", "kind": "aggregator"},
    {"title": "Brief Three", "url": "https://e.com/5", "summary": "Short three.", "author": "", "source": "TASS", "kind": "independent"},
]

_FAILURES = []


def check(cond, msg):
    if not cond:
        _FAILURES.append(msg)


def test_pick_main_stories_prefers_china():
    mains = bp.pick_main_stories(NEWS, 2)
    check(mains[0]["source"] == "Global Times", f"china-official 应优先: {[m['source'] for m in mains]}")
    check(len(mains) == 2, f"应选 2 条主条，实际 {len(mains)}")


def test_byline_with_and_without_author():
    check(bp.byline_of(NEWS[0]) == "By A · Global Times", f"记者归属: {bp.byline_of(NEWS[0])!r}")
    check(bp.byline_of(NEWS[2]) == "By Al Jazeera News Desk", f"无记者归属: {bp.byline_of(NEWS[2])!r}")


def test_write_plate_has_linotype_fields():
    plate = bp.write_plate({"news": NEWS}, 1)
    check("LAYOUT: main-aside" in plate, f"P1 应为 main-aside: {plate[:80]!r}")
    check("KICKER:" in plate and "HEADLINE:" in plate and "BYLINE:" in plate,
          "缺 KICKER/HEADLINE/BYLINE 字段")
    check("BRIEFS:" in plate, "缺 BRIEFS 字段")
    # 归属保留
    check("Global Times" in plate, "主条站点 Global Times 未保留")
    check("Al Jazeera" in plate, "简讯站点 Al Jazeera 未保留")
    # M-1: 含 %/& 的标题保持原始文本（不预转义——linotype build.py 统一转义）
    check("Main China Story: 5% Growth & Trade" in plate,
          "含 %/& 标题应保持原始文本")
    check(r"5\%" not in plate and r"\&" not in plate, "plates 不应预转义 %/&")
    # M-1: STORY-B 后直接正文段，且不得再有 BODY: 行（否则段落路由回主 body）
    check("STORY-B: " in plate, "缺 STORY-B 字段")
    sb_section = plate.split("STORY-B: ")[1].split("BRIEFS:")[0]
    check("Deep analysis paragraph." in sb_section, "STORY-B 正文段缺失")
    check("BODY:" not in sb_section, "STORY-B 后不应有 BODY: 行")


def test_tex_escape():
    check(bp.tex_escape("100% & $5") == r"100\% \& \$5", f"tex_escape: {bp.tex_escape('100% & $5')!r}")
    # 反斜杠不产生二次转义（brief 逐字版的链式 replace 会把 \textbackslash{} 花括号再转义）
    check(bp.tex_escape("a\\b") == r"a\textbackslash{}b", f"反斜杠: {bp.tex_escape('a\\b')!r}")


def test_write_plates_outputs_files():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        bp.write_plates({"P1": NEWS}, out)
        check((out / "plates" / "p1.md").exists(), "plates/p1.md 未生成")
        content = (out / "plates" / "p1.md").read_text(encoding="utf-8")
        check("Main China Story" in content, f"主条标题缺失: {content[:200]!r}")


def test_pick_main_stories_skips_empty_summary():
    """page 源空摘要素材不入选主条（宁缺勿滥）。"""
    news = [
        {"title": "Empty Summary", "url": "https://e.com/e1", "summary": "", "author": "", "source": "Global Times", "kind": "china-official"},
        {"title": "With Summary", "url": "https://e.com/e2", "summary": "Real content here.", "author": "", "source": "CSIS", "kind": "thinktank"},
    ]
    mains = bp.pick_main_stories(news, 2)
    check(len(mains) == 1 and mains[0]["title"] == "With Summary",
          f"空摘要主条未被过滤: {[m['title'] for m in mains]}")


def test_write_plates_skips_empty_main_plate():
    """全空摘要 → 不生成该版文件（宁缺勿滥）。"""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        bp.write_plates({"P1": [{"title": "T", "url": "https://e.com/x", "summary": "",
                                 "author": "", "source": "S", "kind": "china-official"}]}, out)
        check(not (out / "plates" / "p1.md").exists(), "空摘要主条不应生成 plates/p1.md")


def test_pick_briefs_prefers_supplied():
    """终审 C-1c：按单供给（used=True + brief 规格 request）的素材优先入选简讯。"""
    news = [
        {"title": "Unsupplied china-official", "url": "https://e.com/u1", "summary": "Short one.", "author": "", "source": "GT", "kind": "china-official"},
        {"title": "Supplied NASA brief", "url": "https://e.com/s1", "summary": "word " * 70,
         "author": "", "source": "NASA", "kind": "agency", "used": True,
         "request": {"type": "brief", "words": [60, 90], "topic": "space"}},
    ]
    briefs = bp.pick_briefs(news, set(), 2, plate=3)
    check(briefs[0]["title"] == "Supplied NASA brief",
          f"供给素材应优先入选简讯，实际 {[b['title'][:30] for b in briefs]}")


def test_pick_main_prefers_supplied_main():
    """终审 C-1c：按主条规格供给的素材优先入选主条。"""
    news = [
        {"title": "Unsupplied short china-official", "url": "https://e.com/m1",
         "summary": "word " * 40, "author": "", "source": "GT", "kind": "china-official"},
        {"title": "Supplied main story", "url": "https://e.com/m2", "summary": "word " * 300,
         "author": "", "source": "Reuters", "kind": "aggregator", "used": True,
         "request": {"type": "main", "words": [250, 400], "topic": "space"}},
    ]
    mains = bp.pick_main_stories(news, 2, plate=3)
    check(mains[0]["title"] == "Supplied main story",
          f"按主条规格供给的素材应优先，实际 {[m['title'][:30] for m in mains]}")
    # 简讯规格供给（target <200）不应抢占主条
    news2 = [
        {"title": "Long unsupplied", "url": "https://e.com/m3", "summary": "word " * 300,
         "author": "", "source": "GT", "kind": "china-official"},
        {"title": "Supplied brief", "url": "https://e.com/m4", "summary": "word " * 70,
         "author": "", "source": "NASA", "kind": "agency", "used": True,
         "request": {"type": "brief", "words": [60, 90], "topic": "space"}},
    ]
    mains2 = bp.pick_main_stories(news2, 1, plate=3)
    check(mains2[0]["title"] == "Long unsupplied",
          f"供给的简讯不应抢占主条，实际 {mains2[0]['title']!r}")


def test_dedup_same_url_and_title():
    """终审 I-2：同 URL / 同标题素材在选材时只入选一次。"""
    news = [
        {"title": "Story A", "url": "https://e.com/dup", "summary": "Short a.", "author": "", "source": "S1", "kind": "agency"},
        {"title": "Story A", "url": "https://e.com/other", "summary": "Short b.", "author": "", "source": "S2", "kind": "agency"},
        {"title": "Story B", "url": "https://e.com/2", "summary": "Short c.", "author": "", "source": "S3", "kind": "agency"},
    ]
    briefs = bp.pick_briefs(news, set(), 3, plate=3)
    titles = [b["title"] for b in briefs]
    check(titles == ["Story A", "Story B"], f"重复标题/URL 只应入选一次：{titles}")


def test_recency_filters_stale():
    """终审 I-3：date 过期（>30 天）素材排除；无 date 素材保留（RSS 通常有日期）。"""
    news = [
        {"title": "Archive 2017", "url": "https://e.com/old", "summary": "word " * 300,
         "author": "", "source": "China Daily", "kind": "china-official",
         "date": "Mon, 12 Dec 2017 10:00:00 GMT"},
        {"title": "Fresh story", "url": "https://e.com/new", "summary": "word " * 300,
         "author": "", "source": "NASA", "kind": "agency",
         "date": "Tue, 04 Aug 2026 20:00:14 GMT"},
        {"title": "No date story", "url": "https://e.com/nodate", "summary": "word " * 300,
         "author": "", "source": "GT", "kind": "china-official", "date": ""},
    ]
    mains = bp.pick_main_stories(news, 3, plate=3)
    titles = [m["title"] for m in mains]
    check("Archive 2017" not in titles, f"2017 归档稿应被排除：{titles}")
    check("Fresh story" in titles and "No date story" in titles,
          f"新稿与无日期稿应保留：{titles}")


def test_is_stale_url_date_fallback():
    """终审 I-3 加固：date 为空 → URL 日期路径兜底（/201712/12/ 过期、
    /202608/ 与 /2026/08/05/ 新鲜）；无日期信号 → 标题旧年份保守排除，否则保留。"""
    cases = [
        # (item, expected_stale, 说明)
        ({"title": "T", "url": "http://www.chinadaily.com.cn/a/201712/12/WS5a2f2514a3108bc8c67219fb.html", "date": ""},
         True, "China Daily 2017 归档 URL 应判过期"),
        ({"title": "T", "url": "https://www.globaltimes.cn/page/202608/1367571.shtml", "date": ""},
         False, "Global Times 2026-08 URL 应新鲜"),
        ({"title": "T", "url": "http://www.chinadaily.com.cn/a/2026/08/05/WSxxx.html", "date": ""},
         False, "2026-08-05 URL 应新鲜"),
        ({"title": "T", "url": "https://www.nasa.gov/news/1234", "date": ""},
         False, "无日期路径 → 保守保留"),
        ({"title": "2017 trade pact revisited", "url": "https://e.com/x", "date": ""},
         True, "标题自述旧年份 → 保守排除"),
        ({"title": "Fresh no-date story", "url": "https://e.com/y", "date": ""},
         False, "标题无旧年份 → 保留"),
        ({"title": "T", "url": "https://e.com/z", "date": "Tue, 04 Aug 2026 20:00:14 GMT"},
         False, "date 存在且新鲜 → 保留"),
    ]
    for item, expected, msg in cases:
        check(bp.is_stale(item) == expected, f"is_stale {msg}：实际 {bp.is_stale(item)}")


def test_cross_plate_dedup():
    """终审 I-2 加固：同一 URL 出现在多版缓存时只在首个版使用（四版池级去重）。"""
    shared = {"title": "Shared GT story", "url": "https://gt.com/shared", "summary": "word " * 40,
              "author": "", "source": "GT", "kind": "china-official"}
    alt = {"title": "P4 alternative", "url": "https://p4.com/alt", "summary": "word " * 45,
           "author": "", "source": "SCMP", "kind": "independent"}
    results = {"P1": [dict(shared)], "P4": [dict(shared), dict(alt)]}
    with tempfile.TemporaryDirectory() as td:
        bp.write_plates(results, Path(td))
        p1 = (Path(td) / "plates" / "p1.md").read_text(encoding="utf-8")
        p4 = (Path(td) / "plates" / "p4.md").read_text(encoding="utf-8")
        check("Shared GT story" in p1, "P1 应使用共享 URL 素材（首个版）")
        check("Shared GT story" not in p4, f"P4 不应重复使用共享 URL（换素材）：{p4[:120]!r}")
        check("P4 alternative" in p4, "P4 应换用替代素材")
        # 全被占用 → 该版跳过
        results2 = {"P1": [dict(shared)], "P4": [dict(shared)]}
        with tempfile.TemporaryDirectory() as td2:
            bp.write_plates(results2, Path(td2))
            check(not (Path(td2) / "plates" / "p4.md").exists(),
                  "P4 无替代素材时应跳过该版（宁缺勿滥）")


def test_main_min_words_gate():
    """终审 C-1c：≥100 词素材存在时，38 词供给简讯不拿主条头条；素材用尽才回退。"""
    short_supplied = {"title": "Supplied 38-word brief", "url": "https://e.com/s1",
                      "summary": "word " * 38, "author": "", "source": "GT", "kind": "china-official",
                      "used": True, "request": {"type": "brief", "words": [60, 90], "topic": "space"}}
    long_unsupplied = {"title": "Long unsupplied story", "url": "https://e.com/l1",
                       "summary": "word " * 150, "author": "", "source": "NASA", "kind": "agency"}
    mains = bp.pick_main_stories([short_supplied, long_unsupplied], 1, plate=3)
    check(mains[0]["title"] == "Long unsupplied story",
          f"≥100 词素材存在时短稿不应拿主条：{mains[0]['title']!r}")
    check(len(mains[0]["summary"].split()) >= bp.MIN_MAIN_WORDS,
          f"主条应 ≥{bp.MIN_MAIN_WORDS} 词：{len(mains[0]['summary'].split())}")
    # 素材用尽（全部 <100 词）→ 回退全池最优（宁缺毋滥边界，不跳过该版）
    all_short = [short_supplied]
    mains2 = bp.pick_main_stories(all_short, 1, plate=3)
    check(len(mains2) == 1 and mains2[0]["title"] == "Supplied 38-word brief",
          "素材用尽时应回退全池最优（不空版）")


def test_pick_briefs_nasa_beats_china_official():
    """终审 C-1c 加固：同槽位供给素材按规格距离优先——56 词 NASA 简讯
    不被亲中权重 0 的 china-official 素材压掉（此前 kind_rank 决定导致 NASA 进不了简讯槽）。"""
    news = [
        {"title": "Supplied China Daily brief", "url": "https://e.com/cd1", "summary": "word " * 33,
         "author": "", "source": "China Daily", "kind": "china-official", "used": True,
         "request": {"type": "brief", "words": [60, 90], "topic": "space"}},
        {"title": "Supplied NASA brief", "url": "https://e.com/n1", "summary": "word " * 56,
         "author": "", "source": "NASA", "kind": "agency", "used": True,
         "request": {"type": "brief", "words": [60, 90], "topic": "space"}},
    ]
    briefs = bp.pick_briefs(news, set(), 2, plate=3)
    check(briefs[0]["title"] == "Supplied NASA brief",
          f"NASA 供给简讯应按规格距离优先于 china-official：{[b['title'][:30] for b in briefs]}")


def test_topic_penalty_deprioritizes_off_topic():
    """终审 I-4：标题明显与版块题材不相关（如 P4 纪念稿）→ 降权到题材匹配素材之后。"""
    news = [
        {"title": "Memorial Day a time to remember", "url": "https://e.com/t1", "summary": "word " * 300,
         "author": "", "source": "China Daily", "kind": "china-official"},
        {"title": "China launches chip export controls", "url": "https://e.com/t2", "summary": "word " * 300,
         "author": "", "source": "GT", "kind": "china-official"},
    ]
    mains = bp.pick_main_stories(news, 2, plate=4)
    check(mains[0]["title"] == "China launches chip export controls",
          f"P4 纪念稿应降权：{mains[0]['title']!r}")


def test_pick_main_stories_filters_non_english():
    """非英文素材（西里尔/保加利亚语等）不入选主条——英文日报定位。"""
    news = [
        {"title": "Швейцарската банка UBS коригира", "url": "https://e.com/bg1",
         "summary": "Швейцарската банка UBS коригира в посока нагоре прогнозата си за Хонконг",
         "author": "", "source": "TASS", "kind": "independent"},
        {"title": "China launches probe mission", "url": "https://e.com/en1",
         "summary": "China launched a new probe mission on Tuesday to study the lunar south pole.",
         "author": "", "source": "Global Times", "kind": "china-official"},
    ]
    mains = bp.pick_main_stories(news, 2)
    check(len(mains) == 1 and mains[0]["title"].startswith("China"),
          f"非英文素材未被过滤: {[m['title'][:30] for m in mains]}")


def test_tech_gate_p4_international():
    """P4 放宽加固：国际科技源进科技版需题材门——金融稿降权到科技稿之后，中国源不误杀。"""
    news = [
        {"title": "Brazil to become regular borrower in China", "url": "https://e.com/b1",
         "summary": "word " * 120, "author": "", "source": "SCMP", "kind": "independent"},
        {"title": "Nuclear fusion reactor achieves record output", "url": "https://e.com/f1",
         "summary": "word " * 120, "author": "", "source": "Phys.org", "kind": "tech-media"},
        {"title": "China launches chip export controls", "url": "https://e.com/c1",
         "summary": "word " * 120, "author": "", "source": "GT", "kind": "china-official"},
    ]
    mains = bp.pick_main_stories(news, 3, plate=4)
    titles = [m["title"] for m in mains]
    check(titles.index("China launches chip export controls") < titles.index("Nuclear fusion reactor achieves record output"),
          f"亲中科技稿应居首（kind_rank 决胜）：{titles}")
    check(titles.index("Nuclear fusion reactor achieves record output") < titles.index("Brazil to become regular borrower in China"),
          f"科技稿应排在金融稿之前：{titles}")


def test_topic_to_plate_tech_mapping():
    """P4 放宽（2026-08-05）：linotype 发 topic='tech' → 版 4；旧 'china-tech' 兼容。"""
    check(bp.TOPIC_TO_PLATE.get("tech") == 4, "tech 应映射到版 4")
    check(bp.TOPIC_TO_PLATE.get("china-tech") == 4, "china-tech 兼容映射到版 4")



def test_main_story_prefers_fulltext_length():
    """2026-08-06 修复：选材长度轴用 fulltext 而非 summary——summary 截到 400
    字符（≈60-80 词）无区分度，长文全在 fulltext。短摘要+长全文应选中为主条。"""
    news = [
        {"title": "Short summary but long fulltext", "url": "https://e.com/f1",
         "summary": "word " * 70, "fulltext": "para " * 300,
         "author": "", "source": "CSIS", "kind": "thinktank"},
        {"title": "Short brief-like", "url": "https://e.com/f2",
         "summary": "word " * 70, "author": "", "source": "GT", "kind": "china-official"},
    ]
    mains = bp.pick_main_stories(news, 1, plate=1)
    check(mains[0]["title"] == "Short summary but long fulltext",
          f"fulltext 长文应入选主条，实际 {mains[0]['title']!r}")


def test_content_words_prefers_fulltext():
    """_content_words：有 fulltext 用全文词数，无则回退 summary。"""
    it = {"summary": "word " * 70, "fulltext": "para " * 400}
    check(bp._content_words(it) == 400, f"_content_words 应取 fulltext 词数: {bp._content_words(it)}")
    it2 = {"summary": "word " * 70}
    check(bp._content_words(it2) == 70, f"无 fulltext 应回退 summary: {bp._content_words(it2)}")


def test_write_plate_body_uses_fulltext_with_cap():
    """主条正文 fulltext 优先 + 按版上限截断：P1 400 词 / P2 280 词。"""
    # P2: 500 词全文 → BODY 截到 ~280 词
    sent = "word " * 23 + "end. "  # 每段约 24 词（真实句子长度）
    news2 = [{"title": "Long Tech Story", "url": "https://e.com/c1",
              "summary": "Lead para. " + "word " * 60,
              "fulltext": sent * 18,  # 432 词
              "author": "", "source": "IEEE", "kind": "tech-media"}]
    plate2 = bp.write_plate({"news": news2}, 2)
    body2 = plate2.split("BODY:")[1].split("STORY-B:")[0]
    words2 = len(body2.split())
    check(words2 <= 285, f"P2 主条应截到 ~280 词，实际 {words2}")
    check(words2 >= 200, f"P2 主条应保留主体内容，实际 {words2}")
    # P1: 600 词全文 → BODY 截到 ~400 词
    news1 = [{"title": "Long World Story", "url": "https://e.com/c2",
              "summary": "Lead para. " + "word " * 60,
              "fulltext": sent * 30,  # 720 词
              "author": "", "source": "DefenceTalk", "kind": "independent"}]
    plate1 = bp.write_plate({"news": news1}, 1)
    body1 = plate1.split("BODY:")[1].split("STORY-B:")[0]
    words1 = len(body1.split())
    check(words1 <= 405, f"P1 主条应截到 ~400 词，实际 {words1}")
    check(words1 >= 300, f"P1 主条应保留主体内容，实际 {words1}")



def test_is_stale_epoch_seconds():
    """2026-08-06 修复：FreshRSS entry.date 是 epoch 秒（'1786005159'），
    _parse_date 此前不支持 → is_stale 时效过滤全失效（2017 归档稿只要标题
    无年份就能进版）。epoch 秒/毫秒都必须正确解析并判定时效。"""
    import time
    now = int(time.time())
    old = {"date": str(now - 40 * 86400), "title": "Trade pact", "url": "https://e.com/o1"}  # 40 天前
    fresh = {"date": str(now - 86400), "title": "New story", "url": "https://e.com/n1"}       # 1 天前
    check(bp.is_stale(old), f"40 天前 epoch 应判过期: {bp.is_stale(old)}")
    check(not bp.is_stale(fresh), f"1 天前 epoch 不应判过期: {bp.is_stale(fresh)}")
    # 毫秒格式
    old_ms = {"date": str((now - 40 * 86400) * 1000), "title": "Old ms", "url": "https://e.com/o2"}
    check(bp.is_stale(old_ms), "40 天前 epoch 毫秒应判过期")
    # 三种格式互不破坏
    check(bp._parse_date("2026-08-05T10:00:00Z") is not None, "ISO 8601 仍应解析")
    check(bp._parse_date("Wed, 05 Aug 2026 12:20:10 +0000") is not None, "RFC 2822 仍应解析")
def main():
    test_topic_to_plate_tech_mapping()
    test_tech_gate_p4_international()
    test_pick_main_stories_prefers_china()
    test_byline_with_and_without_author()
    test_write_plate_has_linotype_fields()
    test_tex_escape()
    test_write_plates_outputs_files()
    test_pick_main_stories_skips_empty_summary()
    test_write_plates_skips_empty_main_plate()
    test_pick_main_stories_filters_non_english()
    test_pick_briefs_prefers_supplied()
    test_pick_main_prefers_supplied_main()
    test_dedup_same_url_and_title()
    test_recency_filters_stale()
    test_topic_penalty_deprioritizes_off_topic()
    test_is_stale_url_date_fallback()
    test_cross_plate_dedup()
    test_main_min_words_gate()
    test_pick_briefs_nasa_beats_china_official()
    test_main_story_prefers_fulltext_length()
    test_content_words_prefers_fulltext()
    test_write_plate_body_uses_fulltext_with_cap()
    test_is_stale_epoch_seconds()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print(f"ALL TESTS PASSED ({23} tests)")


if __name__ == "__main__":
    main()
