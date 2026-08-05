#!/usr/bin/env python3
"""fetch_sources 单元测试 — 无 pytest 依赖，直接 `python3 test_fetch.py` 运行。

覆盖: fetch_rss RSS 解析（标题/链接/摘要/作者）、Atom 解析、strip_tags、
      fetch_page 兜底、fetch_all 写归档 + fetch_results.json。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_sources as fs

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Test Story One</title><link>https://example.com/1</link>
    <description>&lt;p&gt;A &lt;b&gt;test&lt;/b&gt; summary.&lt;/p&gt;</description>
    <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">John Smith</dc:creator>
    <pubDate>Mon, 05 Aug 2026 10:00:00 GMT</pubDate></item>
  <item><title>Test Story Two</title><link>https://example.com/2</link>
    <description>Second summary.</description></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Feed</title>
  <entry>
    <title>Atom Story One</title>
    <link href="https://example.com/a1"/>
    <summary>A &lt;b&gt;bold&lt;/b&gt; atom summary.</summary>
    <author><name>Jane Doe</name></author>
    <updated>2026-08-05T10:00:00Z</updated>
  </entry>
</feed>"""

# 无 h2/h3 结构的主页（模拟 globaltimes.cn），验证一般锚文本兜底
PAGE_HTML = """<html><head><title>x</title></head><body>
<div class="nav"><a href="/about">About Us Page</a></div>
<div class="hero"><a href="/page/202608/1.shtml">China launches first national security investigation in fore</a></div>
<h2><a href="/top/2.shtml">Short title</a></h2>
<div><a href="/page/202608/2.shtml">A very long headline about regional trade deals worth mentioning</a></div>
</body></html>"""

_FAILURES = []


def check(cond, msg):
    if not cond:
        _FAILURES.append(msg)


def test_fetch_rss_parses():
    orig = fs.http_get
    fs.http_get = lambda url: RSS_XML
    try:
        src = {"url": "https://example.com/rss", "name": "Test"}
        items = fs.fetch_rss(src)
        check(len(items) == 2, f"RSS: 期望 2 条，实际 {len(items)}")
        check(items[0]["title"] == "Test Story One", f"RSS title: {items[0]['title']!r}")
        check(items[0]["url"] == "https://example.com/1", f"RSS url: {items[0]['url']!r}")
        check(items[0]["summary"] == "A test summary.", f"RSS summary: {items[0]['summary']!r}")
        check(items[0]["author"] == "John Smith", f"RSS author: {items[0]['author']!r}")
        check(items[0]["date"] == "Mon, 05 Aug 2026 10:00:00 GMT", f"RSS date: {items[0]['date']!r}")
        check(items[1]["author"] == "", f"RSS item2 应无作者: {items[1]['author']!r}")
    finally:
        fs.http_get = orig


def test_fetch_rss_atom():
    orig = fs.http_get
    fs.http_get = lambda url: ATOM_XML
    try:
        items = fs.fetch_rss({"url": "https://example.com/atom", "name": "AtomTest"})
        check(len(items) == 1, f"Atom: 期望 1 条，实际 {len(items)}")
        check(items[0]["title"] == "Atom Story One", f"Atom title: {items[0]['title']!r}")
        check(items[0]["url"] == "https://example.com/a1", f"Atom url: {items[0]['url']!r}")
        check(items[0]["summary"] == "A bold atom summary.", f"Atom summary: {items[0]['summary']!r}")
        check(items[0]["author"] == "Jane Doe", f"Atom author: {items[0]['author']!r}")
        check(items[0]["date"] == "2026-08-05T10:00:00Z", f"Atom date: {items[0]['date']!r}")
    finally:
        fs.http_get = orig


def test_strip_tags():
    out = fs.strip_tags("<p>A <b>test</b> &amp; more.</p>")
    check(out == "A test & more.", f"strip_tags: {out!r}")
    out2 = fs.strip_tags("<script>bad()</script><style>.x{}</style><p>ok</p>")
    check("bad" not in out2 and out2 == "ok", f"strip_tags script/style: {out2!r}")


def test_fetch_page_fallback():
    orig = fs.http_get
    fs.http_get = lambda url: PAGE_HTML
    try:
        items = fs.fetch_page({"url": "https://site.example/", "name": "PageSrc"}, max_items=4)
        check(len(items) >= 2, f"fetch_page: 期望 >=2 条，实际 {len(items)}")
        titles = [i["title"] for i in items]
        check("China launches first national security investigation in fore" in titles,
              f"缺头条标题: {titles}")
        check(all(len(t) > 15 for t in titles), f"短标题(导航)泄漏: {titles}")
        check(all(i["url"].startswith("https://site.example/") for i in items),
              f"URL 未解析为绝对地址: {[i['url'] for i in items]}")
    finally:
        fs.http_get = orig


def test_fetch_all_writes_archive_and_json():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        sources = {"P1": [{"name": "S1", "url": "x", "kind": "china-official", "mode": "rss"}]}
        orig = fs.fetch_rss
        fs.fetch_rss = lambda src, max_items=8: [
            {"title": "N1", "url": "https://e.com/1", "summary": "s", "author": "A", "date": "d"}]
        try:
            results = fs.fetch_all(sources, out)
        finally:
            fs.fetch_rss = orig
        check(results["P1"][0]["source"] == "S1", f"source 字段: {results['P1'][0]['source']!r}")
        check(results["P1"][0]["plate"] == "P1", f"plate 字段: {results['P1'][0]['plate']!r}")
        check(results["P1"][0]["kind"] == "china-official", f"kind 字段: {results['P1'][0]['kind']!r}")
        archive = (out / "sources" / "p1.md").read_text(encoding="utf-8")
        check("# P1 信源归档" in archive, "归档头应为 '# P1 信源归档'（P 大写）")
        check("N1" in archive and "By A · S1" in archive, "归档缺标题/记者行")
        check("URL: https://e.com/1" in archive and "- 站点: S1" in archive, "归档缺 URL/站点字段")
        # E2E 接口: fetch_results.json
        res = json.loads((out / "fetch_results.json").read_text(encoding="utf-8"))
        check(res["P1"][0]["title"] == "N1", f"fetch_results.json: {res}")


def main():
    test_fetch_rss_parses()
    test_fetch_rss_atom()
    test_strip_tags()
    test_fetch_page_fallback()
    test_fetch_all_writes_archive_and_json()
    if _FAILURES:
        print(f"FAILED ({len(_FAILURES)} 项):")
        for f in _FAILURES:
            print("  -", f)
        sys.exit(1)
    print(f"ALL TESTS PASSED ({5} tests)")


if __name__ == "__main__":
    main()
