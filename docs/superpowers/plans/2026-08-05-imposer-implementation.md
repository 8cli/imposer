# imposer 实现计划 — 英文日报编排 skill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 imposer skill——从权威信源（全面亲中）采集英文日报素材，组织成 linotype 消费的 `plates/*.md`，调用 linotype 排版并读取/响应其信号，产出 PDF + 信源归档 + 日报工作日志。

**Architecture:** 3 个 Python 脚本 + 1 个 SKILL.md 编排手册。`fetch_sources.py` 拉取 RSS/主页（多信源并行，返回结构化 JSON）；`build_plates.py` 把素材组织成 linotype 字段格式的 `plates/p1-p4.md`（含归属/中长篇+简讯配比）；`parse_signals.py` 读取 linotype build.py 输出与 .log，解析版面健康报告（fill / overfull / autofit 状态）。SKILL.md 定义编排流程与信号响应规则（反馈环 ≤2 轮）。与 linotype 的接口是**文件系统**：imposer 写 `plates/*.md`，linotype 读它产出 PDF + 信号，imposer 读信号调整再写。

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

### Task 3: 信号解析器（parse_signals.py）

**Files:**
- Create: `~/.claude/skills/imposer/scripts/parse_signals.py`

**Interfaces:**
- Consumes: linotype build.py stdout + 编译日志（格式见计划头）
- Produces: `parse_build_output(stdout, log_path) -> dict`——`{converged, overfull, fills: list[float], visual_pass, autofit_failed}`；`plate_health(fills) -> list[str]`（每版 fill% + 健康标签）

- [ ] **Step 1: 写信号解析脚本**

创建 `~/.claude/skills/imposer/scripts/parse_signals.py`：

```python
#!/usr/bin/env python3
"""imposer 信号解析器 — 读取 linotype build.py 输出与 .log，产出版面健康报告。

用法: python3 parse_signals.py <build_stdout.log> [--log <xelatex.log>]
输出: 版面健康报告（stdout，人类可读 + 结构化）
"""
import argparse, json, re, sys
from pathlib import Path

FILL_MIN = 0.45  # 与 linotype autofit 下限一致


def parse_build_output(stdout: str, log_path: Path | None = None) -> dict:
    """解析 build.py stdout + 编译日志 → 版面健康报告。"""
    report = {
        "converged": False,        # autofit 是否收敛
        "autofit_failed": False,   # 边界内无法放下
        "overfull": False,         # 是否有 Overfull plate 警告
        "fills": [],               # 每版 fill（[P1, P2, ...] 顺序）
        "visual_pass": None,       # 视觉验收: True/False/None(未跑)
        "messages": [],            # 人类可读消息
    }
    if "✅ 收敛" in stdout:
        report["converged"] = True
    if "❌ 边界内无法放下" in stdout:
        report["autofit_failed"] = True
        report["converged"] = False
    if "✅ 视觉验收通过" in stdout:
        report["visual_pass"] = True
    if "❌ 视觉验收未通过" in stdout:
        report["visual_pass"] = False
    # 从编译日志解析 fill / overfull（与 linotype build.py parse_feedback 同正则）
    log_text = ""
    if log_path and log_path.exists():
        log_text = log_path.read_text(errors="replace")
    if re.search(r"Overfull plate: content", log_text):
        report["overfull"] = True
        report["messages"].append("⚠️ 存在 Overfull plate 警告")
    for m in re.finditer(r"Plate content: ([\d.]+)pt/ contentH ([\d.]+)pt", log_text):
        content, content_h = float(m.group(1)), float(m.group(2))
        if content_h > 0:
            report["fills"].append(content / content_h)
    if report["converged"] and not report["overfull"] and report["fills"] and min(report["fills"]) >= FILL_MIN:
        report["messages"].append(f"✅ 版面健康: 各版 fill {[f'{f*100:.0f}%' for f in report['fills']]}")
    return report


def plate_health(fills: list[float]) -> list[str]:
    """每版健康标签: fill < 45% → 太空(补简讯); >= 45% → OK。"""
    return [f"P{i+1} fill {f*100:.0f}% " + ("OK" if f >= FILL_MIN else "SPARSE→补简讯")
            for i, f in enumerate(fills)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("build_stdout")
    ap.add_argument("--log", default=None, help="xelatex .log 路径")
    args = ap.parse_args()
    stdout = Path(args.build_stdout).read_text(errors="replace")
    report = parse_build_output(stdout, Path(args.log) if args.log else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["fills"]:
        for line in plate_health(report["fills"]):
            print(line)
```

- [ ] **Step 2: 写单元测试**

创建 `~/.claude/skills/imposer/tests/test_signals.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import parse_signals as ps

STDOUT_OK = "=== autofit ===\n  ✅ 收敛 — 最终配置: paper=a3\n  ✅ 视觉验收通过\n"
LOG_OK = "Plate content: 700pt/ contentH 742pt\nPlate content: 300pt/ contentH 742pt\n"
LOG_OVER = "Plate content: 800pt/ contentH 742pt\nOverfull plate: content 800pt> contentH 742pt\n"

def test_converged_and_visual_pass(tmp_path):
    log = tmp_path / "out.log"; log.write_text(LOG_OK)
    r = ps.parse_build_output(STDOUT_OK, log)
    assert r["converged"] and r["visual_pass"] is True and not r["overfull"]
    assert abs(r["fills"][0] - 700/742) < 0.01 and r["fills"][1] < 0.45

def test_overfull_detected(tmp_path):
    log = tmp_path / "out.log"; log.write_text(LOG_OVER)
    r = ps.parse_build_output("", log)
    assert r["overfull"] and len(r["fills"]) == 1

def test_plate_health_labels():
    h = ps.plate_health([0.8, 0.3])
    assert "OK" in h[0] and "补简讯" in h[1]
```

- [ ] **Step 3: 运行测试**

Run: `cd ~/.claude/skills/imposer && python3 -m pytest tests/test_signals.py -v 2>&1 | tail -5`
Expected: 3 PASS

- [ ] **Step 4: 提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: parse_signals.py — linotype build output → plate health report"
```

---

### Task 4: 素材成版器（build_plates.py）

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

### Task 5: SKILL.md 编排手册

**Files:**
- Create: `~/.claude/skills/imposer/SKILL.md`

**Interfaces:**
- Consumes: Task 2-4 的脚本；linotype skill（`~/.claude/skills/linotype`）
- Produces: 编排者流程文档（用户喊"做今天的日报" → 全流程）

- [ ] **Step 1: 写 SKILL.md**

创建 `~/.claude/skills/imposer/SKILL.md`：

```markdown
---
name: imposer
description: Use when the user wants to produce a daily English newspaper (英文日报/报纸/做今天的日报/出报). Organizes source material from authoritative China-friendly news sources into linotype plates, runs linotype typesetting, reads its signals (Overfull/fill/visual diagnostics) and responds by trimming/adding/swapping content. Companion to the linotype typesetting skill.
---

# imposer — 英文日报编排

## 定位

imposer 是 linotype 的**排字工**：组织 4 版素材 → 调用 linotype 排版 → 读取其信号（Overfull/fill/视觉诊断）→ 自动响应（裁段/补简讯/换条）→ 产出 PDF + 信源归档 + 工作日志。

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
# 4. 调 linotype 排版（autofit 默认开）
python3 ~/news/latex/build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2" --visual > $DAILY/build.log 2>&1
# 5. 读信号 → 版面健康报告
python3 ~/.claude/skills/imposer/scripts/parse_signals.py $DAILY/build.log --log $DAILY/out.log
```

## 信号响应规则（灵魂）

| linotype 信号 | imposer 响应 |
|---|---|
| fill < 45%（某版太空） | 该版补 1-2 条简讯 / 扩写主条段落 |
| Overfull plate 警告 | 裁段（末段起）→ 换次条 → 减简讯 |
| autofit ✅ 收敛 | 进入 QA（pdfcheck + --visual） |
| autofit ❌ 边界内无法放下 | 接受 + 报告用户人工决策（不硬调） |
| --visual ❌ 空白带 | 调配比（增/减内容）或接受 |

**反馈环**：调整 plates → 重排 → 重读信号，**最多 2 轮**。仍不达标 → 停止 + 诚实报告。

## 信源与归属

- 信源清单：`scripts/sources.json`（P1 国际军事 / P2 AI 科技 / P3 太空 / P4 中国科技，61 源，全面亲中）
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
├── out.pdf + out.log + out.tex + layout.json
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
cd ~/news/imposer && git add -A && git commit -m "feat: imposer SKILL.md — one-key daily newspaper orchestration manual"
```

---

### Task 6: 端到端集成（真实信源首期样报）

**Files:**
- Modify: `~/news/imposer/docs/superpowers/specs/2026-08-05-imposer-design.md`（如有偏差记录）
- Create: `~/news/daily/2026-08-05/`（首期工作区，交付物）

**Interfaces:**
- Consumes: Task 1-5 全部
- Produces: 首期样报 PDF + 归档 + 日志（验证设计完整落地）

- [ ] **Step 1: 建工作区并抓取**

```bash
DAILY=~/news/daily/2026-08-05; mkdir -p $DAILY/sources $DAILY/plates
python3 ~/.claude/skills/imposer/scripts/fetch_sources.py \
  ~/.claude/skills/imposer/scripts/sources.json $DAILY 2>&1 | tail -8
```
Expected: P1-P4 各有新闻（个别信源失败属正常，记录日志）

- [ ] **Step 2: 审料（人工门）**

列出信源归档摘要，请用户审阅素材质量（标题/归属/覆盖面），确认后进成版。

- [ ] **Step 3: 成版 + 排版 + 读信号**

```bash
python3 ~/.claude/skills/imposer/scripts/build_plates.py $DAILY/fetch_results.json $DAILY
python3 ~/news/latex/build.py $DAILY/plates $DAILY/out.tex \
  --docopts "paper=a3,landscape,columns=3,plates=2" --visual > $DAILY/build.log 2>&1
python3 ~/.claude/skills/imposer/scripts/parse_signals.py $DAILY/build.log --log $DAILY/out.log
```
Expected: 版面健康报告；不达标按信号规则自动调（≤2 轮）

- [ ] **Step 4: 验证交付物齐全**

Run: `ls $DAILY/sources/*.md $DAILY/plates/*.md $DAILY/out.pdf $DAILY/*.log`
Expected: 全部存在；out.pdf 可打开

- [ ] **Step 5: 记录偏差并提交**

```bash
cd ~/news/imposer && git add -A && git commit -m "feat: first daily edition — E2E verified, PDF+archive+logs delivered"
```

---

### Task 7: 回归测试套件（run_tests.py）

**Files:**
- Create: `~/.claude/skills/imposer/tests/run_tests.py`

**Interfaces:**
- Consumes: Task 2-4 的脚本与测试
- Produces: 一键回归（`python3 run_tests.py` → 全绿）

- [ ] **Step 1: 写回归套件**

创建 `~/.claude/skills/imposer/tests/run_tests.py`：

```python
#!/usr/bin/env python3
"""imposer 回归测试 — 一键跑全部单元测试。"""
import sys, subprocess
from pathlib import Path

HERE = Path(__file__).parent
TESTS = ["test_fetch.py", "test_signals.py", "test_build_plates.py"]

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

- [ ] `sources.json` 61 源全验证可达，P1-P4 分配正确
- [ ] `fetch_sources.py`：RSS + 主页抓取，信源归档（URL/记者/站点/摘要）
- [ ] `parse_signals.py`：读 build.py stdout + .log → fill/overfull/visual/收敛 状态
- [ ] `build_plates.py`：素材 → linotype 字段格式 plates，归属保留，中长篇+简讯配比
- [ ] SKILL.md：一键日报流程 + 信号响应规则（≤2 轮反馈环）
- [ ] 首期样报：PDF + 归档 + 日志齐备，版面健康（0 Overfull 或诚实报告）
- [ ] 回归 10 项全绿
