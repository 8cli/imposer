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
    for r in cur.execute("SELECT id, name, url FROM feed").fetchall():
        u = r["url"] or ""
        for path in path_to_sources:
            if u.endswith(path):
                feed_url_to_path[r["id"]] = path

    # 查最新文章（含全文），按 feed 归属
    rows = cur.execute("""
        SELECT e.id_feed, f.name AS feed_name, e.title, e.content, e.author, e.link, e.date,
               e.guid, e.is_read
        FROM entry e JOIN feed f ON e.id_feed = f.id
        ORDER BY e.id DESC
    """).fetchall()

    results = {}
    for r in rows:
        path = feed_url_to_path.get(r["id_feed"])
        if not path:
            continue
        content = r["content"] or ""
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        for plate, src_name in path_to_sources[path]:
            entry = {
                "title": r["title"] or "",
                "url": r["link"] or r["guid"] or "",
                "summary": text[:400] if text else "",
                "fulltext": text if len(text) > MIN_FULLTEXT_CHARS else "",
                "author": r["author"] or "",
                "date": str(r["date"]) if r["date"] else "",
                "source": src_name,
                "kind": _kind_for_feed(src_name),
            }
            results.setdefault(plate, []).append(entry)
            if len(results[plate]) >= max_items * 5:
                continue  # 每版留足候选

    conn.close()
    # 按 sources.json 的版块顺序返回
    return {p: results.get(p, []) for p in sources}


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
