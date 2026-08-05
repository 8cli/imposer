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


def main():
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
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print(f"ALL TESTS PASSED ({13} tests)")


if __name__ == "__main__":
    main()
