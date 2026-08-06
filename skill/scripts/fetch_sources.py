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

# RSSHub 本机部署（2026-08-05 用户决策，源码 dev 模式 @ :1201）
# dev 模式动态加载 lib/routes/ 下的路由——含自定义路由（cnsa/news、esa/newsroom），
# 加路由文件即生效（tsx watch 自动重启），无需重建镜像。容器版（1200，仅内置路由）已退役。
# 有 "rsshub" 字段的 page 源优先走 RSSHub 路由（社区维护 + 自定义的精确解析），
# 失败/为空自动回退原主页直抓——RSSHub 是稳定性补强，不是替换。
RSSHUB_BASE = "http://localhost:1201"

# ---- 审料门前置过滤（终审 I-5）：URL 合法性 + 明显非文章链接 ----
# 路径标记：命中即视为导航/列表/多媒体页而非文章页
NON_ARTICLE_URL_MARKERS = (
    "/about", "/careers", "/jobs", "/podcast", "/podcasts", "/video",
    "/multimedia", "/audio", "/newsletter", "/privacy", "/terms", "/sitemap",
    "/rss", "/feed/", "/tag/", "/tags/", "/topics/", "/author/", "/login",
    "/signup", "/subscribe", "/advertise", "/wp-login", "/search",
    "/category/", "/categories/",
)
# 标题标记：导航/非文章标题（如 Anthropic 页的 "Download press kit"、
# 无障碍跳转链接 "Skip to main content"）
JUNK_TITLE_MARKERS = (
    "how to get support", "download press kit", "press kit", "contact us",
    "about us", "sign in", "log in", "subscribe", "newsletter",
    "privacy policy", "terms of service", "cookie policy", "advertise with",
    "skip to main content", "skip to page content", "skip to navigation",
    "skip to content", "opens in a new window", "opens in a new tab",
)
_EMAIL_TITLE_RE = re.compile(r"^[\w.+-]+@[\w-]+\.\w+$")
# 摘要段落垃圾标记（中文媒体英文版 stub 页常见）：跳过非文章段落
JUNK_PARA_MARKERS = ("file photo", "additional context from", "all rights reserved")


def is_article_url(url: str) -> bool:
    """URL 合法性过滤：仅 http/https、非备案页、非明显导航/列表链接。

    排除: javascript:; 空链接、mailto:/tel:、beian.miit.gov.cn ICP 备案页、
    /about /podcast /rss 等导航路径（成版前的第一道审料门）。
    """
    url = url.strip()
    if url.startswith(("javascript:", "mailto:", "tel:", "#", "/", "?")):
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    if host == "beian.miit.gov.cn" or host.endswith(".beian.miit.gov.cn"):
        return False
    path = parsed.path.lower()
    return not any(marker in path for marker in NON_ARTICLE_URL_MARKERS)


def is_junk_title(title: str) -> bool:
    """标题垃圾过滤：邮箱样标题、导航文案（如 'Download press kit'）。"""
    t = title.strip().lower()
    if _EMAIL_TITLE_RE.match(t):
        return True
    return any(m in t for m in JUNK_TITLE_MARKERS)


def is_junk_paragraph(text: str) -> bool:
    """摘要段落垃圾过滤：图片说明/stub 填充文案不作文本段。"""
    t = text.lower()
    return any(m in t for m in JUNK_PARA_MARKERS)


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
    seen_urls, seen_titles = set(), set()
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
        if link:
            link = urllib.parse.urljoin(source["url"], link)  # 相对链接解析为绝对
        desc = text("description") or text("summary") or text("content")
        author = text("dc:creator") or text("creator") or text("author") or text("author/name") or ""
        date = text("pubDate") or text("updated") or ""
        if not (title and link):
            continue
        if not is_article_url(link) or is_junk_title(title):
            continue  # 审料门第一道：非法/导航 URL 与垃圾标题不进入素材
        # 去重（终审 I-2）：同 URL 只保留首个；同标题（含大小写/空白差异）只保留首个
        norm_title = " ".join(title.lower().split())
        if link in seen_urls or norm_title in seen_titles:
            continue
        seen_urls.add(link)
        seen_titles.add(norm_title)
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
    # 优先 <p> 段落文本（跳过 script/style/nav/footer；图片说明/stub 填充段落剔除；
    # 无句末标点（.?!）的段落视为导航/列表文本——真实导语必有句号）
    paras = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, flags=re.S):
        text = strip_tags(m.group(1))
        if (text and len(text) > 40 and not is_junk_paragraph(text)
                and re.search(r"[.!?]", text)):
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


def fetch_fulltext(url: str, max_chars: int = 8000) -> str:
    """抓取文章页全文（全文优先铁律 2026-08-05）——提取全部正文段落拼接。

    与 _fetch_summary 的区别：不只首段，而是所有合格 <p> 段落（同样跳过
    script/style/nav/footer、图片说明与 stub 填充），空格拼接后按句界截到
    max_chars（≈1300 词，足够 250-600 词主条/深度规格压缩用）。

    调用方：supply 对主条/深度规格（words[0] ≥ 250）的最优候选抓全文——
    agent/rewrite 从全文压缩到 target_words（只压缩不扩写铁律），摘要是全文
    不可得时的兜底。失败/超时返回空串（由 supply 侧兜底摘要，不中断整轮）。
    """
    try:
        html = http_get(url)
    except Exception:
        return ""
    paras = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, flags=re.S):
        text = strip_tags(m.group(1))
        if (text and len(text) > 40 and not is_junk_paragraph(text)
                and re.search(r"[.!?]", text)):
            paras.append(text)
    body = " ".join(paras)
    if not body.strip():
        return ""
    if len(body) > max_chars:
        body = body[:max_chars]
        cut = body.rfind(". ")
        if cut > max_chars * 0.6:  # 句界截断（找不到句界则硬截）
            body = body[: cut + 1]
    return body.strip()


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
        url = urllib.parse.urljoin(source["url"], href)
        if title and len(title) > 15 and is_article_url(url) and not is_junk_title(title):
            candidates.append({"title": title, "url": url,
                               "summary": "", "author": "", "date": ""})
    # 2) 兜底：一般锚文本（无 h2/h3 的站点，如 globaltimes.cn）
    if len(candidates) < max_items:
        seen_titles = {" ".join(c["title"].lower().split()) for c in candidates}
        for m in re.finditer(r"<a[^>]*href=([\"'])([^\"']+)\1[^>]*>(.*?)</a>", html, flags=re.S):
            href, title = m.group(2), strip_tags(m.group(3))
            url = urllib.parse.urljoin(source["url"], href)
            norm_title = " ".join(title.lower().split())
            if (title and len(title) > 15 and is_article_url(url) and not is_junk_title(title)
                    and " " not in href and norm_title not in seen_titles):
                candidates.append({"title": title, "url": url,
                                   "summary": "", "author": "", "date": ""})
                seen_titles.add(norm_title)
            if len(candidates) >= max_items:
                break
    # 去重（同标题/同 URL 各保留首个，终审 I-2），限数量；只对前 SUMMARY_TOP_N 条抓首段摘要
    seen_titles, seen_urls, out = set(), set(), []
    for c in candidates:
        norm_title = " ".join(c["title"].lower().split())
        if norm_title in seen_titles or c["url"] in seen_urls:
            continue
        seen_titles.add(norm_title)
        seen_urls.add(c["url"])
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
            if src.get("rsshub"):
                # RSSHub 路由优先；空/失败回退原主页直抓（RSSHub 是补强不是单点）
                news = fetch_rss({**src, "url": RSSHUB_BASE + src["rsshub"], "mode": "rss"})
                if not news:
                    print(f"  ⚠️ {src['name']} RSSHub 空 → 回退主页直抓")
                    news = fetch_page(src)
            else:
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
