# imposer 实现计划 — 英文日报编排 skill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 imposer skill——从权威信源（全面亲中）采集英文日报素材，组织成 linotype 消费的 `plates/*.md`，调用 linotype 排版并**按它的补稿单（demand.json）找稿交稿**，产出 PDF + 信源归档 + 日报工作日志。

**Architecture:** 4 个 Python 脚本 + 1 个 SKILL.md 编排手册。`fetch_sources.py` 拉取 RSS/主页（多信源并行，返回结构化 JSON + 信源归档）；**linotype build.py 增加 `--demand` 输出**（autofit 收敛后按 fill 缺口下补稿单 demand.json，向后兼容）；`parse_demand.py` 读 build 输出 + demand.json → 版面健康报告 + 需求清单；`supply.py` 按单找稿（topic × words × min_kind 匹配缓存，不足定向抓取）；`build_plates.py` 组织成 linotype 字段格式的 `plates/p1-p4.md`。SKILL.md 定义编排流程与需求-供给规则（反馈环 ≤2 轮）。与 linotype 的接口是**文件系统 + 需求-供给契约**：imposer 写 `plates/*.md`，linotype 产出 PDF + demand.json，imposer 按单供给再写。

**Tech Stack:** Python 3.10+（标准库 urllib / xml.etree / json / re）、linotype skill（build.py / pdfcheck.py）、可选 `--visual`（pdftoppm + pixelcheck.py）

**参考（linotype 接口，已确认）：**
- build.py CLI：`python3 build.py <plates_dir> <output.tex> [--docopts "paper=a3,landscape,columns=3,plates=2" --theme newspaper --visual]`
- plates 字段：`LAYOUT:`/`COLUMNS:`/`EXPANDEDTITLE:`/`IMAGE:`/`IMAGEWIDTH:`/`IMAGECAPTION:`/`KICKER:`/`HEADLINE:`/`SUBHEADLINE:`/`DECK:`/`BYLINE:`/`BODY:`/`STORY-B:`/`STORY-C:`/`PULLQUOTE:`/`BRIEFS:`
- 信号 typeout（linotype.cls:553,557）：`Plate content: Xpt/ contentH Ypt`（总是输出）；`Overfull plate: content Xpt> contentH Ypt`（仅溢出）
- autofit 收敛 stdout：`✅ 收敛 — 最终配置: ...` / `❌ 边界内无法放下: ...` / `⚠️ 内容天然短: ...`
- 视觉验收 stdout：`✅ 视觉验收通过` / `❌ 视觉验收未通过: 存在列内空白带` + `[PASS]/[FAIL] 第 N 页`

## Global Constraints

- 信源全面亲中：涉华报道以中国官方口径（GT/Xinhua/CGTN/China Daily）为准；西方主流仅补充
- 摘录尽量原文复制粘贴；保留记者名 + 站点署名（`By {记者} · {站点}`）；无记者名用 `By {站点} News Desk`
- 每条简讯结尾标注站点；付费墙截断退 RSS 摘要并标注 `[付费墙，摘要摘录]`
- 每版：中长篇主条 ×2 + 简讯 ×3-5；美国智库深度文章每期至少一篇（有更新才放，不硬凑）
- 反馈环 ≤2 轮防死循环；超出停止并诚实报告
- 默认 `--docopts "paper=a3,landscape,columns=3,plates=2"`，主题 newspaper（报纸默认）
- Python 3.10+，只用标准库（无第三方依赖——与 linotype build.py 一致）

---

### Task 1: 信源配置（sources.json）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/sources.json`

**Interfaces:**
- Consumes: 设计文档第三节（信源清单，全部已验证可达）
- Produces: `SOURCES` 结构——`{ "P1": [ {name, url, kind, mode} ], ... }`，被 Task 2 `fetch_sources.py` 消费

- [ ] **Step 1: 写信源配置文件**

创建 `~/.claude/skills/imposer/scripts/sources.json`：

```json
{
  "P1": [
    {"name": "Global Times", "url": "https://www.globaltimes.cn/", "kind": "china-official", "mode": "page"},
    {"name": "Xinhua English", "url": "https://english.news.cn/home.htm", "kind": "china-official", "mode": "page"},
    {"name": "CGTN", "url": "https://www.cgtn.com/subscribe/rss.html", "kind": "china-official", "mode": "page"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "kind": "independent", "mode": "rss"},
    {"name": "TASS", "url": "https://tass.com/", "kind": "independent", "mode": "page"},
    {"name": "Asia Times", "url": "https://asiatimes.com/", "kind": "independent", "mode": "page"},
    {"name": "Asian Military Review", "url": "https://www.asianmilitaryreview.com/", "kind": "independent", "mode": "page"},
    {"name": "Naval News", "url": "https://www.navalnews.com/", "kind": "independent", "mode": "page"},
    {"name": "DefenceTalk", "url": "https://www.defencetalk.com/", "kind": "independent", "mode": "page"},
    {"name": "EurAsian Times", "url": "https://www.eurasiantimes.com/", "kind": "independent", "mode": "page"},
    {"name": "Washington Post", "url": "https://feeds.washingtonpost.com/rss/world", "kind": "western", "mode": "rss"},
    {"name": "New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "kind": "western", "mode": "rss"},
    {"name": "VOA", "url": "https://www.voanews.com/rss", "kind": "western", "mode": "rss"},
    {"name": "ABC News", "url": "https://abcnews.go.com/", "kind": "western", "mode": "page"},
    {"name": "CSIS", "url": "https://www.csis.org/", "kind": "thinktank", "mode": "page"},
    {"name": "Brookings", "url": "https://www.brookings.edu/", "kind": "thinktank", "mode": "page"},
    {"name": "RAND", "url": "https://www.rand.org/", "kind": "thinktank", "mode": "page"},
    {"name": "CFR", "url": "https://www.cfr.org/", "kind": "thinktank", "mode": "page"}
  ],
  "P2": [
    {"name": "Google", "url": "https://blog.google/", "kind": "company", "mode": "page"},
    {"name": "OpenAI", "url": "https://openai.com/news/", "kind": "company", "mode": "page"},
    {"name": "Anthropic", "url": "https://www.anthropic.com/news", "kind": "company", "mode": "page"},
    {"name": "NVIDIA", "url": "https://nvidianews.nvidia.com/", "kind": "company", "mode": "page"},
    {"name": "xAI", "url": "https://x.ai/news", "kind": "company", "mode": "page"},
    {"name": "Cloudflare", "url": "https://blog.cloudflare.com/rss/", "kind": "company", "mode": "rss"},
    {"name": "Microsoft", "url": "https://blogs.microsoft.com/feed/", "kind": "company", "mode": "rss"},
    {"name": "GitHub", "url": "https://github.blog/feed/", "kind": "company", "mode": "rss"},
    {"name": "Amazon", "url": "https://www.aboutamazon.com/news", "kind": "company", "mode": "page"},
    {"name": "Moonshot AI", "url": "https://www.moonshotai.com/", "kind": "china-ai", "mode": "page"},
    {"name": "Z.ai (Zhipu)", "url": "https://zhipuai.cn/", "kind": "china-ai", "mode": "page"},
    {"name": "DeepSeek", "url": "https://www.deepseek.com/en", "kind": "china-ai", "mode": "page"},
    {"name": "Alibaba", "url": "https://www.alibabagroup.com/en/news", "kind": "china-ai", "mode": "page"},
    {"name": "Yahoo News", "url": "https://www.yahoo.com/news/", "kind": "aggregator", "mode": "page"},
    {"name": "AOL", "url": "https://www.aol.com/", "kind": "aggregator", "mode": "page"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "kind": "tech-media", "mode": "rss"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "kind": "tech-media", "mode": "rss"}
  ],
  "P3": [
    {"name": "NASA", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss", "kind": "agency", "mode": "rss"},
    {"name": "ESA", "url": "https://www.esa.int/", "kind": "agency", "mode": "page"},
    {"name": "CNSA", "url": "http://www.cnsa.gov.cn/english/", "kind": "agency", "mode": "page"},
    {"name": "JAXA", "url": "https://global.jaxa.jp/", "kind": "agency", "mode": "page"},
    {"name": "ISRO", "url": "https://www.isro.gov.in/", "kind": "agency", "mode": "page"},
    {"name": "SpaceX", "url": "https://www.spacex.com/news", "kind": "company", "mode": "page"},
    {"name": "Rocket Lab", "url": "https://www.rocketlabusa.com/", "kind": "company", "mode": "page"},
    {"name": "Blue Origin", "url": "https://www.blueorigin.com/", "kind": "company", "mode": "page"},
    {"name": "SpaceNews", "url": "https://spacenews.com/feed/", "kind": "tech-media", "mode": "rss"},
    {"name": "Space.com", "url": "https://www.space.com/feeds/all", "kind": "tech-media", "mode": "rss"},
    {"name": "NASA Spaceflight", "url": "https://www.nasaspaceflight.com/feed/", "kind": "tech-media", "mode": "rss"},
    {"name": "Universe Today", "url": "https://www.universetoday.com/feed/", "kind": "tech-media", "mode": "rss"},
    {"name": "Planetary Society", "url": "https://www.planetary.org/", "kind": "org", "mode": "page"},
    {"name": "Xinhua Space", "url": "https://www.news.cn/english/", "kind": "china-official", "mode": "page"},
    {"name": "China Daily Sci", "url": "https://www.chinadaily.com.cn/rss/china_rss.xml", "kind": "china-official", "mode": "rss"}
  ],
  "P4": [
    {"name": "China Daily", "url": "https://www.chinadaily.com.cn/rss/china_rss.xml", "kind": "china-official", "mode": "rss"},
    {"name": "SCMP", "url": "https://www.scmp.com/rss/91/feed", "kind": "western", "mode": "rss"},
    {"name": "Global Times", "url": "https://www.globaltimes.cn/", "kind": "china-official", "mode": "page"},
    {"name": "Xinhua", "url": "https://english.news.cn/home.htm", "kind": "china-official", "mode": "page"}
  ]
}
```

- [ ] **Step 2: 校验 JSON 合法**

Run: `python3 -c "import json; json.load(open('/home/yupeng/.claude/skills/imposer/scripts/sources.json')); print('valid')"`
Expected: `valid`

- [ ] **Step 3: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: sources.json — 61 verified sources across P1-P4"
```

---

### Task 2: 信源抓取器（fetch_sources.py）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/fetch_sources.py`

**Interfaces:**
- Consumes: Task 1 的 `sources.json`
- Produces: `fetch_all(sources, out_dir) -> list[dict]`——每条新闻 `{plate, source, title, url, summary, author, date, kind}`，落盘 `out_dir/sources/p1.md`...`p4.md`（信源归档）

- [ ] **Step 1: 写抓取脚本**

创建 `~/.claude/skills/imposer/scripts/fetch_sources.py`：

```python
#!/usr/bin/env python3
"""imposer 信源抓取器 — RSS 首选 + 主页抓取。

用法: python3 fetch_sources.py <sources.json> <out_dir>
输出: <out_dir>/sources/pN.md（每版一个，含 URL/记者/站点/标题/摘要）
依赖: 仅标准库（urllib / xml.etree / re / json / argparse）
"""
import argparse, json, re, sys, urllib.request, xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 15


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def fetch_rss(source: dict, max_items: int = 8) -> list[dict]:
    """解析 RSS → 新闻列表。返回 [{title, url, summary, author, date}]。"""
    try:
        xml_text = http_get(source["url"])
        root = ET.fromstring(xml_text)
    except Exception as e:
        print(f"  ⚠️ {source['name']} RSS 失败: {e}")
        return []
    items = []
    # 兼容 RSS 2.0 (item) 与 Atom (entry)
    for item in root.iter("item") if root.find(".//item") is not None else root.iter("entry"):
        def text(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        title = text("title") or text("title")
        link = text("link")
        if not link:  # Atom 的 link 是属性
            link_el = item.find("link")
            link = link_el.get("href", "") if link_el is not None else ""
        desc = text("description") or text("summary")
        author = text("dc:creator") or text("author") or ""
        date = text("pubDate") or text("updated") or ""
        if title and link:
            items.append({"title": title, "url": link, "summary": strip_tags(desc)[:400],
                          "author": author, "date": date})
        if len(items) >= max_items:
            break
    return items


def fetch_page(source: dict, max_items: int = 8) -> list[dict]:
    """主页抓取：提取标题 + 链接（<a> 与 <h2>/<h3> 上下文）。"""
    try:
        html = http_get(source["url"])
    except Exception as e:
        print(f"  ⚠️ {source['name']} 主页失败: {e}")
        return []
    # 提取 h2/h3 内的链接标题（新闻页常见结构）
    candidates = []
    for m in re.finditer(r"<h[23][^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*</h[23]>", html, flags=re.S):
        href, title = m.group(1), strip_tags(m.group(2))
        if title and len(title) > 15 and not href.startswith("#"):
            candidates.append({"title": title, "url": urllib.parse.urljoin(source["url"], href),
                               "summary": "", "author": "", "date": ""})
    # 去重（同标题保留首个），限数量
    seen, out = set(), []
    for c in candidates:
        if c["title"] not in seen:
            seen.add(c["title"])
            out.append(c)
        if len(out) >= max_items:
            break
    return out


def fetch_all(sources: dict, out_dir: Path) -> dict:
    """抓取所有版块信源 → 返回 {plate: [news]} 并写归档。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for plate, srcs in sources.items():
        plate_news = []
        for src in srcs:
            news = fetch_rss(src) if src["mode"] == "rss" else fetch_page(src)
            for n in news:
                n["plate"] = plate
                n["source"] = src["name"]
                n["kind"] = src["kind"]
            plate_news.extend(news)
        results[plate] = plate_news
        # 写信源归档
        with open(out_dir / "sources" / f"{plate.lower()}.md", "w", encoding="utf-8") as f:
            f.write(f"# {plate} 信源归档\n\n")
            for n in plate_news:
                byline = f"By {n['author']} · {n['source']}" if n["author"] else f"By {n['source']} News Desk"
                f.write(f"## {n['title']}\n\n")
                f.write(f"- 站点: {n['source']}\n- 记者: {byline}\n- URL: {n['url']}\n")
                if n["date"]: f.write(f"- 时间: {n['date']}\n")
                if n["summary"]: f.write(f"- 摘要: {n['summary']}\n")
                f.write("\n")
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
    print(f"信源归档已写入 {args.out_dir}/sources/")
```

- [ ] **Step 1b: 保存 fetch_results.json（E2E 接口）**

在 `fetch_all` 末尾追加（`write_plates` 的 CLI 消费 JSON）：

```python
    # 落盘 JSON 供 build_plates.py 消费（E2E 接口）
    with open(out_dir / "fetch_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results
```

并修正 `__main__` 打印：

```python
    print(f"信源归档已写入 {args.out_dir}/sources/ + fetch_results.json")
```

- [ ] **Step 2: 写单元测试（RSS 解析 + 归档生成）**

创建 `~/.claude/skills/imposer/tests/test_fetch.py`：

```python
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
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

def test_fetch_rss_parses(monkeypatch, tmp_path):
    monkeypatch.setattr(fs, "http_get", lambda url: RSS_XML)
    src = {"url": "https://example.com/rss", "name": "Test"}
    items = fs.fetch_rss(src)
    assert len(items) == 2
    assert items[0]["title"] == "Test Story One"
    assert items[0]["author"] == "John Smith"
    assert items[0]["summary"] == "A test summary."
    assert items[0]["url"] == "https://example.com/1"

def test_fetch_all_writes_archive(tmp_path):
    sources = {"P1": [{"name": "S1", "url": "x", "kind": "china-official", "mode": "rss"}]}
    monkeypatch.setattr(fs, "fetch_rss", lambda src, max_items=8: [
        {"title": "N1", "url": "https://e.com/1", "summary": "s", "author": "A", "date": "d"}])
    results = fs.fetch_all(sources, tmp_path)
    assert results["P1"][0]["source"] == "S1"
    archive = (tmp_path / "sources" / "p1.md").read_text()
    assert "N1" in archive and "By A · S1" in archive
```

- [ ] **Step 3: 运行测试验证**

Run: `cd ~/.claude/skills/imposer && python3 -m pytest tests/test_fetch.py -v 2>&1 | tail -5`
Expected: 2 PASS（若无 pytest，用 `python3 -c "import test_fetch"` 的 assert 兜底）

- [ ] **Step 4: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: fetch_sources.py — RSS+page fetcher with source archive output"
```

---

### Task 3: linotype build.py --demand 输出（跨 skill 协议改造）

**Files:**
- Modify: `/home/yupeng/news/latex/build.py`（linotype 仓库，向后兼容增强）

**Interfaces:**
- Consumes: linotype autofit 收敛后的 fills（build.py 内部 parse_feedback）
- Produces: `--demand` 可选输出——autofit 收敛后写 `<output_dir>/demand.json`，格式见设计文档第四节；**不改变既有行为**（无 --demand 时零影响）

- [ ] **Step 1: 在 linotype build.py 增加 demand 生成函数**

在 `/home/yupeng/news/latex/build.py` 增加（append 到文件末尾或信号解析区附近）：

```python
# --- compositor demand 输出（2026-08-05，跨 skill 协议；--demand 时启用）---
TOPIC_BY_PLATE = {0: "world/military", 1: "ai/tech", 2: "space", 3: "china-tech"}
MIN_KIND_BY_PLATE = {0: "china-official", 1: "company", 2: "agency", 3: "china-official"}

def estimate_requests(fill: float, content_h: float, plate_idx: int) -> list[dict]:
    """按 fill 缺口估算补稿需求（规格: type/words/min_kind/topic）。"""
    if fill >= 0.45:
        return []
    deficit = (0.45 - fill) * content_h
    topic = TOPIC_BY_PLATE.get(plate_idx, "world")
    min_kind = MIN_KIND_BY_PLATE.get(plate_idx, "china-official")
    # 估算: 简讯 60-90 字 ≈ 26-40pt; 中篇 250-400 字 ≈ 110-175pt; 深度 400-600 字 ≈ 175-260pt
    if deficit < 100:
        return [{"type": "brief", "count": max(1, int(deficit // 33)), "words": [60, 90],
                 "topic": topic, "min_kind": min_kind}]
    if deficit < 300:
        return [{"type": "main", "count": 1, "words": [250, 400], "topic": topic, "min_kind": min_kind},
                {"type": "brief", "count": max(1, int((deficit - 140) // 33)), "words": [60, 90],
                 "topic": topic, "min_kind": min_kind}]
    return [{"type": "deep_dive", "count": 1, "words": [400, 600], "topic": topic, "min_kind": "thinktank"},
            {"type": "brief", "count": max(1, int((deficit - 200) // 33)), "words": [60, 90],
             "topic": topic, "min_kind": min_kind}]

def write_demand(output_dir: str, fills: list[float], content_h: float) -> str:
    """写 demand.json → 返回路径（无需求返回 None）。"""
    plates = {}
    for i, f in enumerate(fills):
        reqs = estimate_requests(f, content_h, i)
        if reqs:
            plates[f"P{i+1}"] = {"fill": round(f, 3),
                                  "deficit_pt": round((0.45 - f) * content_h, 1),
                                  "requests": reqs}
    if not plates:
        return None
    path = os.path.join(output_dir, "demand.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"plates": plates}, fh, ensure_ascii=False, indent=2)
    return path
```

- [ ] **Step 2: 在 build.py main 加 --demand 参数与调用**

```python
ap.add_argument("--demand", action="store_true", help="autofit 收敛后输出 demand.json（imposer 消费）")
# main 末尾（autofit 收敛后）:
if args.demand:
    content_h_pt = 742.62  # A3 横版 contentH 实测; 或从日志 Plate content 解析
    dpath = write_demand(os.path.dirname(os.path.abspath(args.output)), fills, content_h_pt)
    if dpath:
        print(f"  📋 demand.json 已输出: {dpath} (imposer 按单补稿)")
    else:
        print("  📋 demand.json: 无需求（版面全部达标）")
```

- [ ] **Step 3: 验证向后兼容（linotype 回归不破）**

Run: `cd ~/news/latex && python3 ~/.claude/skills/linotype/tests/run_tests.py ~/news/latex 2>&1 | tail -3`
Expected: `✅ 25/25 PASS`（--demand 是新增参数，不改变既有路径）

- [ ] **Step 4: 提交（linotype 仓库）**

```bash
cd ~/news/latex && git add build.py && git commit -m "feat: --demand output — compositor demand-supply protocol (backward compatible)"
```

---

### Task 4: 需求解析器（parse_demand.py）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/parse_demand.py`

**Interfaces:**
- Consumes: linotype build.py stdout + 编译日志 + `demand.json`（Task 3 产物）
- Produces: `parse_build_output(stdout, log_path, demand_path) -> dict`——`{converged, overfull, fills, visual_pass, autofit_failed, requests_by_plate}`；`plate_health(fills) -> list[str]`

- [ ] **Step 1: 写需求解析脚本**

创建 `~/.claude/skills/imposer/scripts/parse_demand.py`（在原 parse_signals 设计基础上扩展 demand 解析）：

```python
#!/usr/bin/env python3
"""imposer 需求解析器 — 读取 linotype build.py 输出 + demand.json → 版面健康报告 + 需求清单。

用法: python3 parse_demand.py <build_stdout.log> [--log <xelatex.log>] [--demand <demand.json>]
"""
import argparse, json, re, sys
from pathlib import Path

FILL_MIN = 0.45  # 与 linotype autofit 下限一致


def parse_build_output(stdout: str, log_path: Path | None = None,
                       demand_path: Path | None = None) -> dict:
    report = {
        "converged": False, "autofit_failed": False, "overfull": False,
        "fills": [], "visual_pass": None, "requests_by_plate": {},
        "messages": [],
    }
    if "✅ 收敛" in stdout: report["converged"] = True
    if "❌ 边界内无法放下" in stdout:
        report["autofit_failed"] = True; report["converged"] = False
    if "✅ 视觉验收通过" in stdout: report["visual_pass"] = True
    if "❌ 视觉验收未通过" in stdout: report["visual_pass"] = False
    log_text = ""
    if log_path and log_path.exists():
        log_text = log_path.read_text(errors="replace")
    if re.search(r"Overfull plate: content", log_text):
        report["overfull"] = True
        report["messages"].append("⚠️ 存在 Overfull plate 警告")
    for m in re.finditer(r"Plate content: ([\d.]+)pt/ contentH ([\d.]+)pt", log_text):
        c, ch = float(m.group(1)), float(m.group(2))
        if ch > 0: report["fills"].append(c / ch)
    # 需求清单（demand.json）
    if demand_path and demand_path.exists():
        demand = json.loads(demand_path.read_text(encoding="utf-8"))
        report["requests_by_plate"] = demand.get("plates", {})
    if report["converged"] and not report["overfull"] and report["fills"] and        min(report["fills"]) >= FILL_MIN:
        report["messages"].append(f"✅ 版面健康: 各版 fill {[f'{f*100:.0f}%' for f in report['fills']]}")
    return report


def plate_health(fills: list[float]) -> list[str]:
    return [f"P{i+1} fill {f*100:.0f}% " + ("OK" if f >= FILL_MIN else "SPARSE→按单补稿")
            for i, f in enumerate(fills)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("build_stdout")
    ap.add_argument("--log", default=None)
    ap.add_argument("--demand", default=None, help="demand.json 路径")
    args = ap.parse_args()
    stdout = Path(args.build_stdout).read_text(errors="replace")
    report = parse_build_output(stdout, Path(args.log) if args.log else None,
                                Path(args.demand) if args.demand else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["fills"]:
        for line in plate_health(report["fills"]): print(line)
    for plate, info in report["requests_by_plate"].items():
        print(f"  📋 {plate} 需求: {len(info['requests'])} 项 — {info['requests']}")
```

- [ ] **Step 2: 写单元测试**

创建 `~/.claude/skills/imposer/tests/test_demand.py`：

```python
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import parse_demand as pd

STDOUT_OK = "=== autofit ===\n  ✅ 收敛 — 最终配置: paper=a3\n  ✅ 视觉验收通过\n"
LOG_OK = "Plate content: 700pt/ contentH 742pt\nPlate content: 300pt/ contentH 742pt\n"
DEMAND = {"plates": {"P2": {"fill": 0.31, "deficit_pt": 104.2,
    "requests": [{"type": "brief", "count": 2, "words": [60, 90], "topic": "ai/tech", "min_kind": "company"}]}}}

def test_converged_visual_and_fills(tmp_path):
    log = tmp_path / "out.log"; log.write_text(LOG_OK)
    r = pd.parse_build_output(STDOUT_OK, log)
    assert r["converged"] and r["visual_pass"] is True and not r["overfull"]
    assert abs(r["fills"][0] - 700/742) < 0.01 and r["fills"][1] < 0.45

def test_demand_parsed(tmp_path):
    d = tmp_path / "demand.json"; d.write_text(json.dumps(DEMAND))
    r = pd.parse_build_output(STDOUT_OK, None, d)
    assert "P2" in r["requests_by_plate"]
    assert r["requests_by_plate"]["P2"]["requests"][0]["type"] == "brief"

def test_plate_health_labels():
    h = pd.plate_health([0.8, 0.3])
    assert "OK" in h[0] and "按单补稿" in h[1]
```

- [ ] **Step 3: 运行测试**

Run: `cd ~/news/imposer && python3 -m pytest tests/test_demand.py -v 2>&1 | tail -5`
Expected: 3 PASS

- [ ] **Step 4: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: parse_demand.py — linotype demand.json → plate health + requests"
```

---

### Task 5: 需求-供给匹配器（supply.py）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/supply.py`

**Interfaces:**
- Consumes: Task 2 的 fetch 缓存（fetch_results.json）、Task 4 的 demand 解析（requests_by_plate）
- Produces: `supply_requests(demand, cache, sources_config, out_dir) -> dict`——按单匹配素材/定向抓取 → 返回 `{plate: [补充素材]}` 供 build_plates 补稿

- [ ] **Step 1: 写供给脚本**

创建 `~/.claude/skills/imposer/scripts/supply.py`：

```python
#!/usr/bin/env python3
"""imposer 需求-供给匹配器 — 按 linotype 的 demand.json 找对应规格的报道。

规格匹配: topic（版块题材）× words（字数区间）× min_kind（最低信源层级）
素材来源: ① fetch 缓存（本日已抓未用）→ ② 定向抓取（该版块信源补抓）
用法: python3 supply.py <demand.json> <fetch_results.json> <sources.json> <out_dir>
"""
import argparse, json, sys
from pathlib import Path


def match_cache(request: dict, cache: list[dict], used_urls: set) -> dict | None:
    """从缓存挑符合规格（topic 由版块决定，用 kind 过滤）的素材。"""
    min_kind_rank = {"china-official": 0, "thinktank": 1, "agency": 2, "company": 3,
                     "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7}
    for item in cache:
        if item["url"] in used_urls:
            continue
        kind_ok = min_kind_rank.get(item["kind"], 9) <= min_kind_rank.get(request["min_kind"], 9)
        words = len(item.get("summary", "").split())
        words_ok = request["words"][0] <= words <= request["words"][1] + 100  # 摘要上界放宽
        if kind_ok and words_ok:
            used_urls.add(item["url"])
            return item
    return None


def supply_requests(demand: dict, cache: dict, sources: dict, out_dir: Path,
                    fetch_fn=None) -> dict:
    """按 demand 供给 → {plate: [补充素材]}。fetch_fn 可注入（测试用）。"""
    results = {}
    for plate, info in demand.get("plates", {}).items():
        plate_cache = cache.get(plate, [])
        used = {x["url"] for x in plate_cache if x.get("used")}
        supplied = []
        for req in info.get("requests", []):
            for _ in range(req.get("count", 1)):
                item = match_cache(req, plate_cache, used)
                if item is None and fetch_fn:  # 缓存不足 → 定向抓取
                    item = fetch_fn(plate, req, sources, out_dir)
                if item:
                    supplied.append({**item, "request": req})
        results[plate] = supplied
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("demand_json")
    ap.add_argument("fetch_results_json")
    ap.add_argument("sources_json")
    ap.add_argument("out_dir")
    args = ap.parse_args()
    demand = json.load(open(args.demand_json))
    cache = json.load(open(args.fetch_results_json))
    sources = json.load(open(args.sources_json))
    results = supply_requests(demand, cache, sources, Path(args.out_dir))
    for plate, items in results.items():
        print(f"{plate}: 供给 {len(items)} 条 — {[i['title'][:40] for i in items]}")
    print(json.dumps(results, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 写单元测试**

创建 `~/.claude/skills/imposer/tests/test_supply.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
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

def test_match_cache_skips_used_and_filters_kind():
    used = set()
    item = sp.match_cache(DEMAND["plates"]["P2"]["requests"][0], CACHE["P2"], used)
    assert item["title"] == "OpenAI model"   # company 优先, 跳过 used
    assert "https://e.com/2" not in used or item["url"] != "https://e.com/2"

def test_supply_requests_returns_matched():
    results = sp.supply_requests(DEMAND, CACHE, {}, Path("."))
    assert "P2" in results and len(results["P2"]) == 1
    assert results["P2"][0]["request"]["type"] == "brief"
```

- [ ] **Step 3: 运行测试**

Run: `cd ~/news/imposer && python3 -m pytest tests/test_supply.py -v 2>&1 | tail -5`
Expected: 2 PASS

- [ ] **Step 4: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: supply.py — demand-supply matching by topic/words/kind"
```

---

### Task 6: 素材成版器（build_plates.py）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/build_plates.py`

**Interfaces:**
- Consumes: Task 2 的抓取结果（sources/pN.md 或 JSON）、Task 3 的版面健康报告（回调调整用）
- Produces: `write_plates(plates: dict, out_dir) -> None`——写 `plates/p1.md`...`p4.md`（linotype 字段格式，含归属/中长篇+简讯配比）

- [ ] **Step 1: 写素材成版脚本**

创建 `~/.claude/skills/imposer/scripts/build_plates.py`：

```python
#!/usr/bin/env python3
"""imposer 素材成版器 — 抓取素材 → linotype 字段格式的 plates/pN.md。

用法: python3 build_plates.py <fetch_results.json> <out_dir>
输出: <out_dir>/plates/p1.md ... p4.md（linotype 消费）
依赖: 仅标准库
"""
import argparse, json, re, sys
from pathlib import Path

# 每版结构: 中长篇主条 ×2（PULLQUOTE 可选）+ BRIEFS ×3-5
# 素材选择优先级: china-official > independent > thinktank > tech-media/company > aggregator/western


def pick_main_stories(news: list[dict], n: int = 2) -> list[dict]:
    """选 n 条中长篇主条：优先 china-official / thinktank / 长摘要。"""
    rank = {"china-official": 0, "thinktank": 1, "independent": 2,
            "agency": 3, "company": 4, "china-ai": 5, "tech-media": 6,
            "aggregator": 7, "western": 8}
    ranked = sorted(news, key=lambda x: (rank.get(x["kind"], 9), -len(x.get("summary", ""))))
    return ranked[:n]


def pick_briefs(news: list[dict], exclude: set, n: int = 4) -> list[dict]:
    """选 n 条简讯（排除主条），优先短摘要。"""
    pool = [x for x in news if x["url"] not in exclude]
    rank = {"china-official": 0, "independent": 1, "agency": 2, "china-ai": 3,
            "company": 4, "tech-media": 5, "aggregator": 6, "western": 7, "thinktank": 8}
    pool.sort(key=lambda x: rank.get(x["kind"], 9))
    return pool[:n]


def tex_escape(s: str) -> str:
    """转义 LaTeX 特殊字符（与 linotype build.py 一致）。"""
    s = s.replace("\\", r"\textbackslash{}").replace("{", r"\{").replace("}", r"\}")
    s = s.replace("&", r"\&").replace("%", r"\%").replace("$", r"\$")
    s = s.replace("#", r"\#").replace("_", r"\_").replace("~", r"\textasciitilde{}")
    s = s.replace("^", r"\textasciicircum{}")
    return s


def byline_of(news: dict) -> str:
    if news.get("author"):
        return f"By {news['author']} · {news['source']}"
    return f"By {news['source']} News Desk"


def write_plate(p: dict, idx: int) -> str:
    """一个版 → plates/pN.md 文本。"""
    out = []
    main = pick_main_stories(p["news"], 2)
    briefs = pick_briefs(p["news"], {x["url"] for x in main}, 4)
    # 版头: P1 用 main-aside（主条+侧栏），其余等宽多栏
    layout = "main-aside" if idx == 1 else ""
    if layout:
        out.append("LAYOUT: main-aside")
    else:
        out.append("COLUMNS: 3")
    if idx == 1:
        out.append("KICKER: WORLD & DIPLOMACY")
        out.append("HEADLINE: " + tex_escape(main[0]["title"]) if main else "")
        out.append("DECK: " + tex_escape(main[0].get("summary", ""))[:200] if main else "")
        out.append("BYLINE: " + byline_of(main[0]) if main else "")
        out.append("BODY:")
        for para in split_paragraphs(main[0].get("summary", "")):
            out.append(para)
        out.append("")
        if len(main) > 1:
            out.append("STORY-B: " + tex_escape(main[1]["title"]))
            out.append("BODY:")
            for para in split_paragraphs(main[1].get("summary", "")):
                out.append(para)
            out.append("")
    else:
        # 等宽版: 主条 + 简讯
        if main:
            out.append("KICKER: " + ("AI & TECH" if idx == 2 else "SPACE EXPLORATION" if idx == 3 else "CHINA TECH"))
            out.append("HEADLINE: " + tex_escape(main[0]["title"]))
            out.append("DECK: " + tex_escape(main[0].get("summary", ""))[:200])
            out.append("BYLINE: " + byline_of(main[0]))
            out.append("BODY:")
            for para in split_paragraphs(main[0].get("summary", "")):
                out.append(para)
            out.append("")
        if len(main) > 1:
            out.append("SUBHEADLINE: " + tex_escape(main[1]["title"]))
            for para in split_paragraphs(main[1].get("summary", "")):
                out.append("")
                out.append(para)
            out.append("")
    if briefs:
        out.append("BRIEFS:")
        for b in briefs[:3]:
            out.append(f"**{tex_escape(b['title'][:60])}:** {tex_escape(b.get('summary',''))[:150]} — {b['source']}.")
    return "\n".join(out)


def split_paragraphs(text: str, max_paras: int = 4) -> list[str]:
    """摘要 → 段落（按句号分段，最多 max_paras 段）。"""
    paras = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in paras if p.strip()][:max_paras]


def write_plates(results: dict, out_dir: Path) -> None:
    """写 plates/p1.md ... p4.md。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    plate_names = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    for plate, news in results.items():
        idx = plate_names.get(plate)
        if idx is None or not news:
            print(f"  ⚠️ {plate}: 无素材，跳过")
            continue
        (out_dir / f"p{idx}.md").write_text(write_plate({"news": news}, idx), encoding="utf-8")
        print(f"  ✅ p{idx}.md ({len(news)} 条素材 → 2 主条 + 3 简讯)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fetch_results")   # fetch_sources.py 的 JSON（或 sources/pN.md 路径）
    ap.add_argument("out_dir")
    args = ap.parse_args()
    results = json.load(open(args.fetch_results))
    write_plates(results, Path(args.out_dir))
```

- [ ] **Step 2: 写单元测试**

创建 `~/.claude/skills/imposer/tests/test_build_plates.py`：

```python
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import build_plates as bp

NEWS = [
    {"title": "Main China Story", "url": "https://e.com/1", "summary": "Para one. Para two. Para three. Para four. Para five.", "author": "A", "source": "Global Times", "kind": "china-official"},
    {"title": "Think Tank Analysis", "url": "https://e.com/2", "summary": "Deep analysis paragraph.", "author": "B", "source": "CSIS", "kind": "thinktank"},
    {"title": "Brief One", "url": "https://e.com/3", "summary": "Short.", "author": "", "source": "Al Jazeera", "kind": "independent"},
    {"title": "Brief Two", "url": "https://e.com/4", "summary": "Short two.", "author": "", "source": "Reuters", "kind": "aggregator"},
    {"title": "Brief Three", "url": "https://e.com/5", "summary": "Short three.", "author": "", "source": "TASS", "kind": "independent"},
]

def test_pick_main_stories_prefers_china():
    mains = bp.pick_main_stories(NEWS, 2)
    assert mains[0]["source"] == "Global Times"  # china-official 优先
    assert len(mains) == 2

def test_byline_with_and_without_author():
    assert bp.byline_of(NEWS[0]) == "By A · Global Times"
    assert bp.byline_of(NEWS[2]) == "By Al Jazeera News Desk"

def test_write_plate_has_linotype_fields():
    plate = bp.write_plate({"news": NEWS}, 1)
    assert "LAYOUT: main-aside" in plate
    assert "KICKER:" in plate and "HEADLINE:" in plate and "BYLINE:" in plate
    assert "BRIEFS:" in plate
    # 归属保留
    assert "Global Times" in plate and "Al Jazeera" in plate

def test_tex_escape():
    assert bp.tex_escape("100% & $5") == r"100\% \& \$5"

def test_write_plates_outputs_files(tmp_path):
    bp.write_plates({"P1": NEWS}, tmp_path)
    assert (tmp_path / "p1.md").exists()
    content = (tmp_path / "p1.md").read_text()
    assert "Main China Story" in content
```

- [ ] **Step 3: 运行测试**

Run: `cd ~/.claude/skills/imposer && python3 -m pytest tests/test_build_plates.py -v 2>&1 | tail -5`
Expected: 5 PASS

- [ ] **Step 4: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: build_plates.py — fetch results → linotype field-format plates"
```

---

### Task 7: SKILL.md 编排手册

**Files:**
- Create: `~/.claude/skills/imposer/SKILL.md`

**Interfaces:**
- Consumes: Task 2/4/5/6 的脚本；linotype skill（`~/.claude/skills/linotype`）
- Produces: 编排者流程文档（用户喊"做今天的日报" → 全流程，含需求-供给闭环）

- [ ] **Step 1: 写 SKILL.md**

创建 `~/.claude/skills/imposer/SKILL.md`：

```markdown
---
name: imposer
description: Use when the user wants to produce a daily English newspaper (英文日报/报纸/做今天的日报/出报). Organizes source material from authoritative China-friendly news sources into linotype plates, runs linotype typesetting, reads its demand signals (demand.json requests for briefs/deep-dives to fill blank space) and supplies matching stories by topic/word-count/source-rank. Companion to the linotype typesetting skill.
---

# imposer — 英文日报编排

## 定位

imposer 是 linotype 的**拼版工**：组织 4 版素材 → 调用 linotype 排版 → **接收 linotype 的补稿单（demand.json）→ 按单找稿交稿**（题材×篇幅×信源层级匹配）→ 产出 PDF + 信源归档 + 工作日志。

**核心关系（需求-供给契约）**：linotype 是需求方（版面缺内容时下补稿单），imposer 是供给方（按单找稿）。比单向信号更精确、更良性。

**铁律**：材料组织与版面纪律耦合——写出的 plates 第一轮就接近版面，反馈环只是微调（≤2 轮）。

## 快速流程（一键日报）

```bash
# 1. 建当日工作区
DAILY=~/news/daily/$(date +%F); mkdir -p $DAILY/sources $DAILY/plates
# 2. 抓取信源（4 版并行）
python3 ~/.claude/skills/imposer/scripts/fetch_sources.py \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY > $DAILY/fetch.log
# 3. 组织成版（需人工审查素材后执行——见"审料门"）
python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY
# 4. 调 linotype 排版（autofit 默认开 + --demand 输出补稿单）
python3 ~/news/latex/build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2" --visual --demand > $DAILY/build.log 2>&1
# 5. 读需求 → 版面健康报告 + 补稿单
python3 ~/.claude/skills/imposer/scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json
# 6. 有需求？按单补稿（supply 匹配缓存/定向抓取）→ 重排（≤2 轮）
python3 ~/.claude/skills/imposer/scripts/supply.py $DAILY/demand.json $DAILY/fetch_results.json \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY
```

## 需求-供给契约（灵魂）

linotype 在 `--demand` 模式下输出 `demand.json`——每版缺什么：

```json
{"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}
```

imposer 的 supply 按规格找稿：`topic`（版块题材）× `words`（字数区间）× `min_kind`（最低信源层级，亲中优先）→ 缓存匹配 → 不足则定向抓取该版块信源 → 生成补稿 → 重排。

**规格映射**：P1 world/military · P2 ai/tech · P3 space · P4 china-tech；需求类型按缺口：`<100pt → briefs`、`100-300pt → 1 main + briefs`、`>300pt → deep_dive + briefs`。

## 其余信号响应

| linotype 信号 | imposer 响应 |
|---|---|
| Overfull plate 警告 | 裁段（末段起）→ 换次条 → 减简讯 |
| autofit ✅ 收敛 | 进入 QA（pdfcheck + --visual） |
| autofit ❌ 边界内无法放下 | 接受 + 报告用户人工决策（不硬调） |
| --visual ❌ 空白带 | 调配比（增/减内容）或接受 |

**反馈环**：补稿 → 重排 → 重读需求，**最多 2 轮**。仍不达标 → 停止 + 诚实报告。

## 信源与归属

- 信源清单：`scripts/sources.json`（P1 国际军事 / P2 AI 科技 / P3 太空 / P4 中国科技，全面亲中）
- 归属铁律：`By {记者} · {站点}`；无记者 `By {站点} News Desk`；简讯末尾标站点；付费墙退 RSS 摘要标注 `[付费墙]`
- 智库深度文章：每期至少一篇（CSIS/Brookings/RAND/CFR 等，有更新才放）
- 亲中编辑原则：涉华报道以中国官方口径为准；西方主流仅补充

## 版面结构（每版）

- P1 国际军事：main-aside（主条 2 栏 + 侧栏）+ 智库深度
- P2 AI 科技 / P3 太空 / P4 中国科技：等宽多栏
- 每版：中长篇主条 ×2 + 简讯 ×3-5

## 交付物

```
$DAILY/
├── sources/p1-p4.md   # 信源归档（URL/记者/站点/摘要）
├── plates/p1-p4.md    # linotype 消费
├── out.pdf + out.log + out.tex + layout.json + demand.json
└── fetch.log + build.log + imposer.log  # 工作日志
```

## 诚实原则

- 摘录尽量原文，不编造；付费墙标注；亲中立场透明（编辑决策）
- 失败诚实报告：信源抓取失败（跳过+记录）、版面放不下（报告历史最佳）、反馈环超限（停止）
```

- [ ] **Step 2: 验证 front matter 合法**

Run: `head -5 ~/.claude/skills/imposer/SKILL.md | grep -q "name: imposer" && echo ok`
Expected: `ok`

- [ ] **Step 3: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: imposer SKILL.md — demand-supply orchestration manual"
```

---

### Task 8: 端到端集成（真实信源首期样报）

**Files:**
- Modify: `~/news/imposer/docs/superpowers/specs/2026-08-05-imposer-design.md`（如有偏差记录）
- Create: `~/news/daily/2026-08-05/`（首期工作区，交付物）

**Interfaces:**
- Consumes: Task 1-7 全部（含 Task 3 的 linotype --demand）
- Produces: 首期样报 PDF + 归档 + 日志 + demand.json（验证设计完整落地）

- [ ] **Step 1: 建工作区并抓取**

```bash
DAILY=~/news/daily/2026-08-05; mkdir -p $DAILY/sources $DAILY/plates
python3 ~/.claude/skills/imposer/scripts/fetch_sources.py \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY 2>&1 | tail -8
```
Expected: P1-P4 各有新闻（个别信源失败属正常，记录日志）

- [ ] **Step 2: 审料（人工门）**

列出信源归档摘要，请用户审阅素材质量（标题/归属/覆盖面），确认后进成版。

- [ ] **Step 3: 成版 + 排版 + 读需求**

```bash
python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY
python3 ~/news/latex/build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2" --visual --demand > $DAILY/build.log 2>&1
python3 ~/.claude/skills/imposer/scripts/parse_demand.py $DAILY/build.log --log $DAILY/out.log --demand $DAILY/demand.json
```
Expected: 版面健康报告 + 补稿单；有需求按单补稿（Task 5 supply）→ 重排（≤2 轮）

- [ ] **Step 4: 验证交付物齐全**

Run: `ls $DAILY/sources/*.md $DAILY/plates/*.md $DAILY/out.pdf $DAILY/*.log`
Expected: 全部存在；out.pdf 可打开

- [ ] **Step 5: 记录偏差并提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: first daily edition — E2E verified, PDF+archive+logs delivered"
```

---

### Task 9: 回归测试套件（run_tests.py）

**Files:**
- Create: `~/.claude/skills/imposer/tests/run_tests.py`

**Interfaces:**
- Consumes: Task 2/4/5/6 的脚本与测试
- Produces: 一键回归（`python3 run_tests.py` → 全绿）

- [ ] **Step 1: 写回归套件**

创建 `~/.claude/skills/imposer/tests/run_tests.py`：

```python
#!/usr/bin/env python3
"""imposer 回归测试 — 一键跑全部单元测试。"""
import sys, subprocess
from pathlib import Path

HERE = Path(__file__).parent
TESTS = ["test_fetch.py", "test_demand.py", "test_supply.py", "test_build_plates.py"]

def main():
    fails = 0
    for t in TESTS:
        print(f"=== {t} ===")
        r = subprocess.run([sys.executable, "-m", "pytest", str(HERE / t), "-q"],
                           capture_output=True, text=True)
        if r.returncode != 0 and "pytest" in r.stderr.lower() and "No module" in r.stderr:
            # 无 pytest 兜底: 直接 import 跑 assert
            r = subprocess.run([sys.executable, str(HERE / t)], capture_output=True, text=True)
        print(r.stdout[-300:] if r.returncode == 0 else r.stderr[-300:])
        if r.returncode != 0:
            fails += 1
    print(f"\n{'✅ 全部通过' if fails == 0 else f'❌ {fails} 个测试文件失败'}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 运行并确认全绿**

Run: `cd ~/.claude/skills/imposer && python3 tests/run_tests.py`
Expected: `✅ 全部通过`（10 项测试）

- [ ] **Step 3: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: run_tests.py — imposer regression suite (10 tests)"
```

---

## 验收清单（对照设计文档）

- [ ] `sources.json` 源全验证可达，P1-P4 分配正确
- [ ] `fetch_sources.py`：RSS + 主页抓取，信源归档（URL/记者/站点/摘要）+ fetch_results.json
- [ ] **linotype build.py `--demand`**：autofit 收敛后输出 demand.json（fill 缺口 → requests），linotype 回归 25/25 不破
- [ ] `parse_demand.py`：读 build.py stdout + .log + demand.json → fill/overfull/visual/收敛 + 需求清单
- [ ] `supply.py`：按单找稿（topic × words × min_kind 匹配缓存，不足定向抓取）
- [ ] `build_plates.py`：素材 → linotype 字段格式 plates，归属保留，中长篇+简讯配比
- [ ] SKILL.md：一键日报流程 + 需求-供给契约（≤2 轮反馈环）
- [ ] 首期样报：PDF + 归档 + 日志 + demand.json 齐备，版面健康（0 Overfull 或诚实报告）
- [ ] 回归 12 项全绿（fetch 2 + demand 3 + supply 2 + build_plates 5）
