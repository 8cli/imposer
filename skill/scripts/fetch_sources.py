#!/usr/bin/env python3
"""imposer 信源抓取器 — RSS 首选 + 主页抓取。

用法: python3 fetch_sources.py <sources.json> <out_dir>
输出: <out_dir>/sources/pN.md（每版一个，含 URL/记者/站点/标题/摘要）
      <out_dir>/fetch_results.json（E2E 接口，供 build_plates.py 消费）
依赖: 仅标准库（urllib / xml.etree / re / json / argparse）
"""
import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 8
SUMMARY_TOP_N = 2   # fetch_page 只对前 N 条候选抓首段摘要（控请求数，防整轮超时）


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


_XML_ENTITY_FIXES = {
    "&nbsp;": " ", "&mdash;": "—", "&ndash;": "–",
    "&rsquo;": "'", "&lsquo;": "'", "&ldquo;": '"', "&rdquo;": '"',
    "&hellip;": "…", "&middot;": "·",
    "&eacute;": "é", "&egrave;": "è", "&agrave;": "à", "&oacute;": "ó",
    "&auml;": "ä", "&ouml;": "ö", "&uuml;": "ü",
}


def _parse_xml(xml_text: str) -> ET.Element:
    """解析 XML；遇 XML 1.0 未定义实体（&nbsp; 等）替换后重试一次。

    约束（实测验证）：
    1. 只替换 XML 1.0 非法实体；&amp;/&lt;/&gt;/&quot;/&apos; 五个预定义实体不动；
    2. 不用 html.unescape 预解码（会把 &lt;p&gt; 变真 <p> 破坏 XML 结构）；
    3. 第二次解析仍失败则让 ParseError 上抛，由 fetch_rss 的 except 兜底（保留降级路径）。
    """
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        for name, repl in _XML_ENTITY_FIXES.items():
            xml_text = xml_text.replace(name, repl)
        return ET.fromstring(xml_text)


def _strip_ns(root: ET.Element) -> None:
    """去掉所有元素的命名空间前缀，使 find/iter 能用简单标签匹配。

    Python 的 Element.find/iter 不解析文档内声明的 xmlns 前缀：
    find("dc:creator") 只匹配字面 tag，iter("entry") 对带默认命名空间的
    Atom feed 返回空。解析后统一去前缀即可兼容 RSS 2.0 与 Atom。
    """
    for el in root.iter():
        if el.tag.startswith("{"):
            el.tag = el.tag.rsplit("}", 1)[-1]


def fetch_rss(source: dict, max_items: int = 8) -> list[dict]:
    """解析 RSS → 新闻列表。返回 [{title, url, summary, author, date}]。"""
    try:
        xml_text = http_get(source["url"])
        root = _parse_xml(xml_text)
    except Exception as e:
        print(f"  ⚠️ {source['name']} RSS 失败: {e}")
        return []
    _strip_ns(root)
    items = []
    # 兼容 RSS 2.0 (item) 与 Atom (entry)
    is_atom = root.find(".//item") is None
    for item in root.iter("entry" if is_atom else "item"):
        def text(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        # RSS 2.0 取 item/title 文本；Atom 取 entry/title 文本
        # （Atom 的 title 若在子元素中，用 .// 遍历兜底）
        title = text("title")
        if not title:
            el = item.find(".//title")
            title = el.text.strip() if el is not None and el.text else ""
        link = text("link")
        if not link:  # Atom 的 link 是属性
            link_el = item.find("link")
            link = link_el.get("href", "") if link_el is not None else ""
        desc = text("description") or text("summary") or text("content")
        author = text("dc:creator") or text("creator") or text("author") or text("author/name") or ""
        date = text("pubDate") or text("updated") or ""
        if title and link:
            items.append({"title": title, "url": link, "summary": strip_tags(desc)[:400],
                          "author": author, "date": date})
        if len(items) >= max_items:
            break
    return items


def _fetch_summary(url: str, max_chars: int = 400) -> str:
    """抓取文章页首段文本作摘要（限时兜底：失败/超时返回空串）。

    新闻页常见结构：<p> 首段即导语。取前 max_chars 字符、按句截断。
    """
    try:
        html = http_get(url)
    except Exception:
        return ""
    # 优先 <p> 段落文本（跳过 script/style/nav/footer）
    paras = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, flags=re.S):
        text = strip_tags(m.group(1))
        if text and len(text) > 40:
            paras.append(text)
    if not paras:
        return ""
    first = paras[0]
    # 按句截断到 max_chars
    truncated = first[:max_chars]
    last_period = truncated.rfind(".")
    if last_period > max_chars * 0.5:
        truncated = truncated[: last_period + 1]
    return truncated


def fetch_page(source: dict, max_items: int = 8) -> list[dict]:
    """主页抓取：优先 h2/h3 内嵌链接；无此结构的站点（如 globaltimes.cn）兜底到一般锚文本。
    每条候选顺带抓正文首段作摘要（_fetch_summary），避免空摘要素材无法成版。"""
    try:
        html = http_get(source["url"])
    except Exception as e:
        print(f"  ⚠️ {source['name']} 主页失败: {e}")
        return []
    candidates = []
    # 1) 提取 h2/h3 内的链接标题（新闻站常见结构），兼容单/双引号 href
    for m in re.finditer(r"<h[23][^>]*>\s*<a[^>]*href=([\"'])([^\"']+)\1[^>]*>(.*?)</a>\s*</h[23]>",
                         html, flags=re.S):
        href, title = m.group(2), strip_tags(m.group(3))
        if title and len(title) > 15 and not href.startswith("#"):
            candidates.append({"title": title, "url": urllib.parse.urljoin(source["url"], href),
                               "summary": "", "author": "", "date": ""})
    # 2) 兜底：一般锚文本（无 h2/h3 的站点，如 globaltimes.cn）
    if len(candidates) < max_items:
        seen_titles = {c["title"] for c in candidates}
        for m in re.finditer(r"<a[^>]*href=([\"'])([^\"']+)\1[^>]*>(.*?)</a>", html, flags=re.S):
            href, title = m.group(2), strip_tags(m.group(3))
            if (title and len(title) > 15 and not href.startswith("#")
                    and " " not in href and title not in seen_titles):
                candidates.append({"title": title, "url": urllib.parse.urljoin(source["url"], href),
                                   "summary": "", "author": "", "date": ""})
                seen_titles.add(title)
            if len(candidates) >= max_items:
                break
    # 去重（同标题保留首个），限数量；只对前 SUMMARY_TOP_N 条抓首段摘要（控请求数防慢）
    seen, out = set(), []
    for c in candidates:
        if c["title"] not in seen:
            seen.add(c["title"])
            if len(out) < SUMMARY_TOP_N:
                c["summary"] = _fetch_summary(c["url"])
            out.append(c)
        if len(out) >= max_items:
            break
    return out


def fetch_all(sources: dict, out_dir: Path, max_workers: int = 8) -> dict:
    """抓取所有版块信源（并发）→ 返回 {plate: [news]} 并写归档 + fetch_results.json。

    max_workers=8 并发拉 RSS/主页，总耗时 ≈ 最坏单源耗时（而非串行累加）。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sources").mkdir(parents=True, exist_ok=True)

    # 摊平 (plate, src) 任务，并发抓取
    tasks = [(plate, src) for plate, srcs in sources.items() for src in srcs]
    fetched: dict[tuple, list] = {}

    def run(plate: str, src: dict) -> tuple:
        try:
            news = fetch_rss(src) if src["mode"] == "rss" else fetch_page(src)
            for n in news:
                n["plate"] = plate
                n["source"] = src["name"]
                n["kind"] = src["kind"]
            return plate, news
        except Exception as e:
            print(f"  ⚠️ {src['name']} 抓取异常: {e}")
            return plate, []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run, plate, src): plate for plate, src in tasks}
        for fut in as_completed(futures):
            plate, news = fut.result()
            fetched.setdefault(plate, []).extend(news)

    results = {plate: fetched.get(plate, []) for plate in sources}
    # 写信源归档（每版一个 md）
    for plate, plate_news in results.items():
        with open(out_dir / "sources" / f"{plate.lower()}.md", "w", encoding="utf-8") as f:
            f.write(f"# {plate} 信源归档\n\n")
            for n in plate_news:
                byline = f"By {n['author']} · {n['source']}" if n["author"] else f"By {n['source']} News Desk"
                f.write(f"## {n['title']}\n\n")
                f.write(f"- 站点: {n['source']}\n- 记者: {byline}\n- URL: {n['url']}\n")
                if n["date"]:
                    f.write(f"- 时间: {n['date']}\n")
                if n["summary"]:
                    f.write(f"- 摘要: {n['summary']}\n")
                f.write("\n")
    # 落盘 JSON 供 build_plates.py 消费（E2E 接口）
    with open(out_dir / "fetch_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sources_json")
    ap.add_argument("out_dir")
    args = ap.parse_args()
    sources = json.load(open(args.sources_json))
    results = fetch_all(sources, Path(args.out_dir))
    for plate, news in results.items():
        print(f"{plate}: {len(news)} 条新闻")
    print(f"信源归档已写入 {args.out_dir}/sources/ + fetch_results.json")
