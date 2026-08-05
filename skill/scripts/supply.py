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
                     "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7,
                     "western": 8}
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
                    if item and item["url"] in used:  # 防 fetch 返回已供给 URL
                        item = None
                if item:
                    used.add(item["url"])  # fetch 素材也记 used，防重复供给
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
