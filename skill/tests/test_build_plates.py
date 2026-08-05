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


def main():
    test_pick_main_stories_prefers_china()
    test_byline_with_and_without_author()
    test_write_plate_has_linotype_fields()
    test_tex_escape()
    test_write_plates_outputs_files()
    test_pick_main_stories_skips_empty_summary()
    test_write_plates_skips_empty_main_plate()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print(f"ALL TESTS PASSED ({7} tests)")


if __name__ == "__main__":
    main()
