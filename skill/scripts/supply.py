#!/usr/bin/env python3
"""imposer 需求-供给匹配器 — 按 linotype 的 demand.json 找对应规格的报道。

规格匹配: topic（版块题材）× words（字数区间）× min_kind（最低信源层级）
素材来源: ① fetch 缓存（本日已抓未用）→ ② 定向抓取（该版块信源补抓）
用法: python3 supply.py <demand.json> <fetch_results.json> <sources.json> <out_dir>
"""
import argparse, json, re, sys
from pathlib import Path

from build_plates import TOPIC_TO_PLATE, _topic_penalty, is_stale  # 终审 I-3/I-4（与成版同标准）

_LATIN_RE = re.compile(r"[A-Za-z]")


def _is_english(text: str, threshold: float = 0.85) -> bool:
    """粗略英文判定：拉丁字母占非空白字符比例 ≥ threshold（与 build_plates 同逻辑）。

    过滤非英文素材（如 CGTN 语言选择链接、TASS 西里尔内容），保证英文日报定位。
    """
    stripped = "".join(text.split())
    if not stripped:
        return False
    latin = len(_LATIN_RE.findall(stripped))
    return latin / len(stripped) >= threshold


def match_cache(request: dict, cache: list[dict], used_urls: set,
                allow_rewrite: bool = False) -> dict | None:
    """从缓存挑符合规格（topic 由版块决定，用 kind 过滤）的素材。

    英文过滤：标题或摘要非英文（拉丁占比 < 85%）不匹配。
    allow_rewrite=True 时：精确规格匹配失败 → 返回最接近素材 + needs_rewrite 标注
    （AI 改写压缩到目标词数区间——SKILL.md 编排层职责）。
    """
    min_kind_rank = {"china-official": 0, "thinktank": 1, "agency": 2, "company": 3,
                     "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7,
                     "western": 8}
    # 题材过滤（终审 I-4）：demand 的 topic → 版号 → 负向关键词；明显不相关不补稿
    plate = TOPIC_TO_PLATE.get(request.get("topic", ""), 1)
    best_fallback = None
    best_dist = None
    for item in cache:
        if item["url"] in used_urls:
            continue
        if is_stale(item):
            continue  # 过期素材（date 存在且 >30 天）不补稿——成版也会排除
        if _topic_penalty(item.get("title", ""), plate):
            continue  # 题材明显不匹配（如 P4 的纪念稿）不补稿
        if not _is_english(item.get("title", "") + " " + item.get("summary", "")):
            continue  # 非英文素材不补稿
        kind_ok = min_kind_rank.get(item["kind"], 9) <= min_kind_rank.get(request["min_kind"], 9)
        words = len(item.get("summary", "").split())
        words_ok = request["words"][0] <= words <= request["words"][1]
        if kind_ok and words_ok:
            used_urls.add(item["url"])
            return item
        # 近似匹配：同 kind 层级内，摘要词数离目标区间最近的（供改写）
        if allow_rewrite and kind_ok:
            target_mid = (request["words"][0] + request["words"][1]) / 2
            dist = abs(words - target_mid)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_fallback = item
    if best_fallback:
        used_urls.add(best_fallback["url"])
        best_fallback["needs_rewrite"] = True
        best_fallback["target_words"] = request["words"]
    return best_fallback


def supply_requests(demand: dict, cache: dict, sources: dict, out_dir: Path,
                    fetch_fn=None, allow_rewrite: bool = True, rewrite_fn=None) -> dict:
    """按 demand 供给 → {plate: [补充素材]}。fetch_fn 可注入（测试用）。

    allow_rewrite=True（默认）: 精确规格匹配失败时返回最接近素材，由 rewrite_fn
    （rewrite.py，LLM 压缩）改写压缩到目标词数区间。rewrite_fn 签名:
        rewrite_fn(summary, min_words, max_words, source, title) -> str
    铁律：只压缩不扩写——素材词数 ≤ 需求上限时原样返回（不调用 LLM）。

    每供给一条：素材原地标记 used=True 并挂 request（终审 C-1b/C-1c）——编排层
    回写缓存后第 2 轮不再重复供给；build_plates 按 request 槽位优先入选。
    rewrite_fn 失败逐条容错（终审 I-6）：保留原素材 + 警告，不中断整轮。
    """
    results = {}
    for plate, info in demand.get("plates", {}).items():
        plate_cache = cache.get(plate, [])
        used = {x["url"] for x in plate_cache if x.get("used")}
        supplied = []
        for req in info.get("requests", []):
            for _ in range(req.get("count", 1)):
                item = match_cache(req, plate_cache, used, allow_rewrite)
                if item is None and fetch_fn:  # 缓存不足 → 定向抓取
                    item = fetch_fn(plate, req, sources, out_dir)
                    if item and item["url"] in used:  # 防 fetch 返回已供给 URL
                        item = None
                if item:
                    used.add(item["url"])  # fetch 素材也记 used，防重复供给
                    item["used"] = True    # 持久化标记：编排层回写缓存后，第 2 轮不再重复供给（终审 C-1b）
                    item["request"] = req  # 原条目也挂 request：成版 _dedup 保留原条目时槽位优先不丢失（终审 C-1c）
                    # LLM 改写压缩（铁律: 只压缩不扩写，由 rewrite_fn 内部保证）
                    if item.get("needs_rewrite") and rewrite_fn:
                        lo, hi = req["words"]
                        try:  # 改写失败保留原素材 + 警告（对比 fetch 的逐源容错，终审 I-6）
                            item["summary"] = rewrite_fn(
                                item.get("summary", ""), lo, hi,
                                item.get("source", ""), item.get("title", ""))
                        except Exception as e:
                            print(f"  ⚠️ 改写失败（{e}），保留原素材（宁缺勿滥）")
                        item.pop("needs_rewrite", None)
                        item.pop("target_words", None)
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
