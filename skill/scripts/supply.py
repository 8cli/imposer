#!/usr/bin/env python3
"""imposer 需求-供给匹配器 — 按 linotype 的 demand.json 找对应规格的报道。

规格匹配: topic（版块题材）× words（字数区间）× min_kind（最低信源层级）
素材来源: ① fetch 缓存（本日已抓未用）→ ② 定向抓取（该版块信源补抓）
用法: python3 supply.py <demand.json> <fetch_results.json> <sources.json> <out_dir>
"""
import argparse, json, re, sys
from pathlib import Path

from build_plates import TOPIC_TO_PLATE, _topic_penalty, _tech_gate, is_stale  # 终审 I-3/I-4 + P4 题材门（与成版同标准）

_LATIN_RE = re.compile(r"[A-Za-z]")


# 信源层级（与 build_plates.KIND_RANK 一致；模块级供预取/匹配共用，2026-08-06）
MIN_KIND_RANK = {"china-official": 0, "thinktank": 1, "agency": 2, "company": 3,
                 "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7,
                 "western": 8}


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
    （改写压缩到目标词数区间——agent 执行，见 SKILL.md 改写规则；rewrite.py 仅兜底）。

    全文优先（2026-08-05 用户决策）：词数按 fulltext（若有）计算——缓存经前轮
    全文抓取富集后，主条规格直接命中全文而不重复抓取；全文命中仍需 needs_rewrite
    （正文仍是摘要，需压缩全文回填 summary，只压缩不扩写）。
    """
    min_kind_rank = MIN_KIND_RANK  # 模块级（预取也用它）
    # 题材过滤（终审 I-4）：demand 的 topic → 版号 → 负向关键词；明显不相关不补稿
    plate = TOPIC_TO_PLATE.get(request.get("topic", ""), 1)
    best_fallback = None
    best_dist = None
    for item in cache:
        if item["url"] in used_urls:
            continue
        if is_stale(item):
            continue  # 过期素材（date 存在且 >30 天）不补稿——成版也会排除
        if _topic_penalty(item.get("title", ""), plate) or _tech_gate(item, plate):
            continue  # 题材明显不匹配（如 P4 的纪念稿/国际金融稿）不补稿
        if not _is_english(item.get("title", "") + " " + item.get("summary", "")):
            continue  # 非英文素材不补稿
        kind_ok = min_kind_rank.get(item["kind"], 9) <= min_kind_rank.get(request["min_kind"], 9)
        body = item.get("fulltext") or item.get("summary", "")  # 全文优先：有全文按全文算
        words = len(body.split())
        words_ok = request["words"][0] <= words <= request["words"][1]
        if kind_ok and words_ok:
            used_urls.add(item["url"])
            if item.get("fulltext"):
                # 全文达标但正文仍是摘要 → 标改写：agent/rewrite 压缩全文回填 summary
                item["needs_rewrite"] = True
                item["target_words"] = request["words"]
            return item
        # 近似匹配：同 kind 层级内，优先选全文/正文词数 ≥ 下限的（主条素材要够长），
        # 其次才按距离 target 最近（2026-08-06：全文预取后 fallback 应选长全文，
        # 否则 CFR 68 词摘要抢走 DefenceTalk 400 词全文的主条槽）
        if allow_rewrite and kind_ok:
            target_mid = (request["words"][0] + request["words"][1]) / 2
            dist = abs(words - target_mid)
            # 达标优先：正文 ≥ 下限的候选排最前（满分），否则按距离
            score = 0 if words >= request["words"][0] else dist + 1000  # 未达标大幅落后
            if best_dist is None or score < best_dist:
                best_dist = score
                best_fallback = item
    if best_fallback:
        used_urls.add(best_fallback["url"])
        best_fallback["needs_rewrite"] = True
        best_fallback["target_words"] = request["words"]
    return best_fallback


def supply_requests(demand: dict, cache: dict, sources: dict, out_dir: Path,
                    fetch_fn=None, allow_rewrite: bool = True, rewrite_fn=None,
                    fulltext_fn=None) -> dict:
    """按 demand 供给 → {plate: [补充素材]}。fetch_fn/fulltext_fn 可注入（测试用）。

    **主路径（agent 执行改写，用户决策 2026-08-05）**：rewrite_fn 默认 None——
    近似匹配的素材保留 `needs_rewrite: true` + `target_words: [lo, hi]` 标注，
    **agent（skill 调用方，本身即 LLM）按 SKILL.md 改写规则直接压缩回填**，
    不再由脚本调一次 Claude API（anthropic 包/PEP 668/SSE 解析/CLI 污染等坑的绕路）。
    标注即信号：agent 看到 needs_rewrite 就知道该改写哪条、改写到多少词。

    **全文优先（2026-08-05 用户决策）**：主条/深度规格（words[0] ≥ 250）缓存只有
    短摘要时，对最优候选调 fulltext_fn(url) 抓全文——全文比摘要更能满足排版需求，
    摘要是全文不可得（失败/太短）时的兜底。抓到全文 → 素材带 `fulltext` 字段，
    agent/rewrite 从全文压缩到 target_words（只压缩不扩写，绝不从短摘要扩写）。

    **兜底（可选）**：rewrite_fn 传入（如 rewrite.py 的 rewrite）时在此压缩——
    保留给 headless cron 自动化（无 agent 场景）。签名:
        rewrite_fn(text, min_words, max_words, source, title) -> str
    有 fulltext 时压缩全文；铁律：只压缩不扩写——输入词数 ≤ 需求上限时原样返回。

    每供给一条：素材原地标记 used=True 并挂 request（终审 C-1b/C-1c）——编排层
    回写缓存后第 2 轮不再重复供给；build_plates 按 request 槽位优先入选。
    fulltext/rewrite 失败逐条容错（终审 I-6）：保留原素材 + 警告，不中断整轮。
    """
    results = {}
    for plate, info in demand.get("plates", {}).items():
        plate_cache = cache.get(plate, [])
        used = {x["url"] for x in plate_cache if x.get("used")}
        supplied = []
        for req in info.get("requests", []):
            for _ in range(req.get("count", 1)):
                # 主条/深度规格全文预取（2026-08-06）：抓缓存里前 N 个候选的全文，
                # 选全文最长者——充分利用信源，避免"最优候选全文短"导致薄主条。
                # 只在缓存候选的摘要都 < 需求下限时触发（达标素材无需预取）。
                if (req["words"][0] >= 250 and fulltext_fn
                        and not any(len((x.get("fulltext") or x.get("summary", "")).split()) >= req["words"][0]
                                    for x in plate_cache if x["url"] not in used)):
                    plate_no = TOPIC_TO_PLATE.get(req.get("topic", ""), 1)
                    best_item, best_w = None, 0
                    # 预筛选：英文 + 题材匹配 + kind 达标 + 未用（避免抓阿拉伯语/题材不符的占位）
                    prefetch_cands = [
                        c for c in plate_cache
                        if c["url"] not in used and not is_stale(c)
                        and _is_english(c.get("title", "") + " " + c.get("summary", ""))
                        and not _topic_penalty(c.get("title", ""), plate_no)
                        and not _tech_gate(c, plate_no)
                        and MIN_KIND_RANK.get(c.get("kind"), 9) <= MIN_KIND_RANK.get(req["min_kind"], 9)
                    ]
                    for cand in prefetch_cands[:15]:  # 预筛选后前 15 个
                        w = 0
                        if cand.get("fulltext"):
                            w = len(cand["fulltext"].split())
                        else:
                            try:
                                text = fulltext_fn(cand["url"])
                                if text and len(text.split()) > len(cand.get("summary", "").split()):
                                    cand["fulltext"] = text  # 全文写回缓存 item（match_cache 按全文词数匹配）
                                    w = len(text.split())
                            except Exception:
                                pass
                        if w > best_w:
                            best_w, best_item = w, cand
                        if best_w >= req["words"][1]:
                            break  # 已达标，不再多抓
                    if best_item and best_item.get("fulltext"):
                        print(f"  ✅ {req['type']} 全文预取: {best_item['source']} {len(best_item['fulltext'].split())}词")
                item = match_cache(req, plate_cache, used, allow_rewrite)
                if item is None and fetch_fn:  # 缓存不足 → 定向抓取
                    item = fetch_fn(plate, req, sources, out_dir)
                    if item and item["url"] in used:  # 防 fetch 返回已供给 URL
                        item = None
                    if item and req["words"][0] > len(item.get("summary", "").split()):
                        item["needs_rewrite"] = True  # fetch 新素材未达主条规格 → 同样走改写
                        item["target_words"] = req["words"]
                if item:
                    used.add(item["url"])  # fetch 素材也记 used，防重复供给
                    item["used"] = True    # 持久化标记：编排层回写缓存后，第 2 轮不再重复供给（终审 C-1b）
                    item["request"] = req  # 原条目也挂 request：成版 _dedup 保留原条目时槽位优先不丢失（终审 C-1c")
                    # 全文优先（用户决策 2026-08-05）：主条/深度规格缓存只有短摘要 → 抓全文
                    if (item.get("needs_rewrite") and not item.get("fulltext")
                            and req["words"][0] >= 250 and fulltext_fn):
                        try:
                            text = fulltext_fn(item["url"])
                            if text and len(text.split()) > len(item.get("summary", "").split()):
                                item["fulltext"] = text  # 全文可用 → agent 从全文压缩
                            elif text:
                                print(f"  ⚠️ 全文不足（{len(text.split())} 词），摘要兜底")
                        except Exception as e:
                            print(f"  ⚠️ 全文抓取失败（{e}），摘要兜底（宁缺勿滥）")
                    # LLM 改写压缩（铁律: 只压缩不扩写，由 rewrite_fn 内部保证）
                    if item.get("needs_rewrite") and rewrite_fn:
                        lo, hi = req["words"]
                        try:  # 改写失败保留原素材 + 警告（对比 fetch 的逐源容错，终审 I-6）
                            src = item.get("fulltext") or item.get("summary", "")  # 全文优先
                            item["summary"] = rewrite_fn(
                                src, lo, hi, item.get("source", ""), item.get("title", ""))
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
    ap.add_argument("--write-back", action="store_true",
                    help="把供给结果（used=True + request 标记）写回 fetch_results.json——"
                         "headless cron 无 agent 编排时的持久化兜底（隐患 #57 修复："
                         "原只 stdout 输出，used 持久化依赖编排层，断链即跨轮重复供给）")
    args = ap.parse_args()
    demand = json.load(open(args.demand_json))
    cache = json.load(open(args.fetch_results_json))
    sources = json.load(open(args.sources_json))
    from fetch_sources import fetch_fulltext  # 生产默认：全文优先（摘要兜底）
    results = supply_requests(demand, cache, sources, Path(args.out_dir),
                              fulltext_fn=fetch_fulltext)
    for plate, items in results.items():
        print(f"{plate}: 供给 {len(items)} 条 — {[i['title'][:40] for i in items]}")
    if args.write_back:
        # 回写缓存：按 URL 原地更新（血泪 #13: 不可 append——同 URL 双条目
        # 致 _dedup 保留旧摘要，供给素材永不进版）
        for plate, items in results.items():
            for it in items:
                for c in cache.get(plate, []):
                    if c["url"] == it["url"]:
                        c["used"] = True
                        c["request"] = it["request"]
                        if it.get("summary") and len(it["summary"]) > len(c.get("summary", "")):
                            c["summary"] = it["summary"]  # 改写交付稿
                        if it.get("fulltext"):
                            c["fulltext"] = it["fulltext"]  # 预取全文
                        break
        with open(args.fetch_results_json, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"✅ 已回写 {args.fetch_results_json}（{sum(len(v) for v in results.values())} 条标记 used）")
    print(json.dumps(results, ensure_ascii=False, indent=2))
