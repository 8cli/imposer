#!/usr/bin/env python3
"""imposer FreshRSS 查询器 — 直接查本机 FreshRSS SQLite 库选文（替代实时抓取 RSSHub）。

用户架构决策（2026-08-06）：RSSHub(标题+链接) → FreshRSS 聚合 + af-readability
全文入库（Fivefilters Readability.php）→ imposer 直接查库选文，不再实时抓取分析，
省算力（全文提取入库时一次，出报查库零实时抓取）。

用法: python3 fetch_freshrss.py <sources.json> <out_dir>
输出: <out_dir>/fetch_results.json（与 fetch_sources.py 同格式，供 build_plates/supply 消费）

FreshRSS 信息（Docker :1202，SQLite）：
  容器: freshrss（--restart unless-stopped，卷 freshrss-data）
  库:   /var/www/FreshRSS/data/users/imposer/db.sqlite（entry 表 content 含全文）
  注:   用 docker cp 拷贝库再读（避免容器内 sqlite3 客户端缺失），
        每次查询拷贝最新库（FreshRSS 定时刷新 CRON_MIN=0,30）。

af-readability 全文扩展（Niehztog/freshrss-af-readability v0.4）：
  安装: extensions/af_readability/（vendor/ 自带 Fivefilters Readability.php，纯客户端无外部依赖）
  启用: 用户 data/users/imposer/config.php 两处缺一不可——
    1) 'extensions_enabled' => array('Af_Readability' => true)  ← 决定扩展加载
    2) 'ext_af_readability_categories' => '{"2":true,"3":true,"4":true,"5":true}'
       ← JSON 字符串！扩展用 attributeString() 读，PHP 数组格式读不到 → 静默跳过所有文章
       （2026-08-06 血泪：此格式坑 + 容器重建丢扩展文件，导致 88.7% 入库无全文）
  只处理新入库文章：改配置后需清空 entry 表 + 重置 feed.lastUpdate 全量重灌（见 SESSION-STATE）
"""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path

CONTAINER = "freshrss"
DB_PATH_IN_CONTAINER = "/var/www/FreshRSS/data/users/imposer/db.sqlite"
MIN_FULLTEXT_CHARS = 500  # 视为"有全文"的最小 content 长度


def _copy_db() -> Path:
    """docker cp 最新库到临时文件，返回路径。"""
    tmp = Path(tempfile.mkdtemp()) / "freshrss.sqlite"
    r = subprocess.run(["docker", "cp", f"{CONTAINER}:{DB_PATH_IN_CONTAINER}", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"docker cp 失败: {r.stderr[:100]}")
    return tmp


def fetch_from_freshrss(sources: dict, out_dir: Path, max_items: int = 8) -> dict:
    """直接查 FreshRSS SQLite 库 → {plate: [news]}（与 fetch_sources.py 同格式）。

    entry 表：content 是 af-readability 提取的全文（HTML），转纯文本后进 summary/fulltext。
    feed 表：name 与 sources.json 的源名对应，映射到版块。
    """
    db_path = _copy_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # rsshub path → (版块, 源名) 映射（2026-08-06：同一 feed 可能服务多版块，
    # 如 Global Times/Xinhua 同时在 P1/P3/P4——按 rsshub path 而非 feed 名映射，
    # 每个版块的源条目独立取到同一 feed 内容，source 名用各自的源名）
    path_to_sources = {}  # rsshub path → [(plate, src_name), ...]
    for plate, srcs in sources.items():
        for s in srcs:
            if s.get("rsshub"):
                path_to_sources.setdefault(s["rsshub"], []).append((plate, s["name"]))
    # feed URL → rsshub path（FreshRSS feed.url = http://172.17.0.1:1201<rsshub>）
    feed_url_to_path = {}
    subscribed_paths = set()
    for r in cur.execute("SELECT id, name, url FROM feed").fetchall():
        u = r["url"] or ""
        for path in path_to_sources:
            if u.endswith(path):
                feed_url_to_path[r["id"]] = path
                subscribed_paths.add(path)

    # 启动校验（2026-08-06 血泪 #30）: 配置源 vs 已订阅 feed 对照——
    # 未订阅的 rsshub path 静默导致对应源全空（实测 /xinhuaenglish/news
    # 未订阅 → P1 Xinhua English / P3 Xinhua Space / P4 Xinhua 三源颗粒无收，
    # 版块覆盖静默萎缩）。缺失必须告警，否则用户只看条数永远发现不了。
    for path, plate_srcs in path_to_sources.items():
        if path not in subscribed_paths:
            for plate, src_name in plate_srcs:
                print(f"  ⚠️ {src_name} ({plate}) 未订阅 {path} — 该源在 FreshRSS 路径下为空!")

    # 无 rsshub 的源（直抓源）: 标注走 fetch_sources 路径（诚实说明，非错误）
    no_rsshub = [(p, s["name"]) for p, srcs in sources.items() for s in srcs
                 if not s.get("rsshub")]
    if no_rsshub:
        names = "、".join(f"{n}({p})" for p, n in no_rsshub[:5])
        more = f" 等 {len(no_rsshub)} 源" if len(no_rsshub) > 5 else ""
        print(f"  ℹ️ {len(no_rsshub)} 个直抓源不走 FreshRSS（SPA/反爬，fetch_sources 直抓）: {names}{more}")

    # 查最新文章（含全文），按 feed 归属
    rows = cur.execute("""
        SELECT e.id_feed, f.name AS feed_name, e.title, e.content, e.author, e.link, e.date,
               e.guid, e.is_read
        FROM entry e JOIN feed f ON e.id_feed = f.id
        ORDER BY e.id DESC
    """).fetchall()

    results = {}
    feed_counts = {}  # 2026-08-06 修复（血泪 #29）: 按 feed 配额截断——
                      # 原 max_items*5 截断是 no-op（continue 只跳内层循环），
                      # 每版拉到全库历史（477 条 vs 预期 40），旧稿与新闻同池
                      # 竞争（29 天前长文压掉 2 天前新文）。按 feed 每源取最新
                      # N 条，低量智库源（CSIS/Brookings/RAND/CFR）不被高量源
                      # （Asia Times 112 条）挤掉。
    for r in rows:
        path = feed_url_to_path.get(r["id_feed"])
        if not path:
            continue
        fc = feed_counts.get(r["id_feed"], 0)
        if fc >= max_items:
            continue  # 该 feed 已取满最新 max_items 条（id 倒序 = 时间倒序）
        feed_counts[r["id_feed"]] = fc + 1
        content = r["content"] or ""
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        # 内容清洗（2026-08-06）：HTML 实体转回字符——af-readability 存的是
        # 纯 ASCII 实体（mb_encode_numericentity），出报前必须 unescape，
        # 否则 &#8220;（"）、&#8217;（'）、&amp; 直出到 plates（实测 571 条）
        text = unescape(text)
        # title 同样可能含实体（RSSHub 路由原样带出）
        title = unescape(r["title"] or "")
        for plate, src_name in path_to_sources[path]:
            entry = {
                "title": title,
                "url": r["link"] or r["guid"] or "",
                "summary": text[:400] if text else "",
                "fulltext": text if len(text) > MIN_FULLTEXT_CHARS else "",
                "author": r["author"] or "",
                "date": str(r["date"]) if r["date"] else "",
                "source": src_name,
                "kind": _kind_for_feed(src_name),
            }
            results.setdefault(plate, []).append(entry)

    conn.close()
    ordered = {p: results.get(p, []) for p in sources}

    # 写信源归档（血泪 #33）: SKILL.md 审料门要求成版前人工复核
    # sources/pN.md——fetch_freshrss 此前不写该目录 → 审料门失去输入
    # （人审环节静默消失）。与 fetch_sources 同格式。
    sources_dir = out_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for plate, plate_news in ordered.items():
        with open(sources_dir / f"{plate.lower()}.md", "w", encoding="utf-8") as f:
            f.write(f"# {plate} 信源归档\n\n")
            for n in plate_news:
                byline = (f"By {n['author']} · {n['source']}"
                          if n["author"] else f"By {n['source']} News Desk")
                f.write(f"## {n['title']}\n\n")
                f.write(f"- 站点: {n['source']}\n- 记者: {byline}\n- URL: {n['url']}\n")
                if n["date"]:
                    f.write(f"- 时间: {n['date']}\n")
                if n.get("fulltext"):
                    f.write(f"- 全文: {len(n['fulltext'].split())} 词\n")
                if n["summary"]:
                    f.write(f"- 摘要: {n['summary'][:150]}\n")
                f.write("\n")

    return ordered


def _kind_for_feed(feed_name: str) -> str:
    """feed 名 → kind（查 sources.json 匹配）。默认 tech-media 由 build_plates 用。"""
    import json as _json
    try:
        d = _json.load(open(Path(__file__).parent / "sources.json"))
        for srcs in d.values():
            for s in srcs:
                if s["name"] == feed_name:
                    return s.get("kind", "tech-media")
    except Exception:
        pass
    return "tech-media"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sources_json")
    ap.add_argument("out_dir")
    args = ap.parse_args()
    sources = json.load(open(args.sources_json))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = fetch_from_freshrss(sources, out)
    for p, items in results.items():
        with_ft = sum(1 for i in items if i.get("fulltext"))
        print(f"{p}: {len(items)} 条（有全文 {with_ft} 条）")
    json.dump(results, open(out / "fetch_results.json", "w"), ensure_ascii=False, indent=2)
    print(f"已写 {out}/fetch_results.json")
