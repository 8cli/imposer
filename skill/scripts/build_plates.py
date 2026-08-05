#!/usr/bin/env python3
"""imposer 素材成版器 — 抓取素材 → linotype 字段格式的 plates/pN.md。

用法: python3 build_plates.py <fetch_results.json> <out_dir>
输出: <out_dir>/p1.md ... p4.md（linotype build.py 消费）
依赖: 仅标准库

字段格式（linotype SKILL.md）：
  P1 用 LAYOUT: main-aside（主条 → mainstory 2 栏，STORY-B → 侧栏，BRIEFS → aside）
  P2/P3/P4 用 COLUMNS: 3（等宽多栏，副条 STORY-B 渲染为 subheadline+正文）
  BRIEFS 每条: `**标题:** 内容 — 站点.`（**bold** 由 linotype build.py 转义）

转义约定：plates 写原始文本，不预转义——linotype build.py 的 parse_plate 对每个
字段统一 tex_escape（含 `**x**`→`\\textbf{x}`）；预转义会造成双重转义
（实测 `5%` 预转义后经 build.py 变 `5\\\\%`，LaTeX 渲染成换行+百分号）。
"""
import argparse
import email.utils
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 素材亲中优先级（与 supply.py 的 min_kind_rank 一致）：越小越优先
KIND_RANK = {"china-official": 0, "thinktank": 1, "agency": 2, "company": 3,
             "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7,
             "western": 8}

# 每版结构: 中长篇主条 ×2 + BRIEFS ×3（linotype inbrief/asidebriefs 各渲染 3 条）
PLATE_KICKERS = {1: "WORLD & DIPLOMACY", 2: "AI & TECH", 3: "SPACE EXPLORATION", 4: "CHINA TECH"}

# demand 的 topic 字段 → 版号（终审 I-4：supply 端也用 topic 过滤）
TOPIC_TO_PLATE = {"world/military": 1, "ai/tech": 2, "space": 3, "china-tech": 4}

# 时效过滤（终审 I-3）：date 字段存在且超过此天数 → 过期素材（如 RSS 里的 2017 归档稿）
MAX_STALE_DAYS = 30

# 题材负向关键词（终审 I-4 轻量实现）：标题命中即与版块题材明显不相关 → 降权
# （P1 题材广不设负向词；P3/P4 共用的 China Daily 综合 RSS 会泄漏纪念/体育类稿件）
TOPIC_OFF_KEYWORDS = {
    1: (),
    2: ("memorial", "massacre", "anniversary", "sports", "football", "cricket", "celebrity"),
    3: ("memorial", "massacre", "anniversary", "sports", "football", "cricket", "celebrity"),
    4: ("memorial", "massacre", "anniversary", "sports", "football", "cricket", "celebrity"),
}

_LATIN_RE = re.compile(r"[A-Za-z]")


def _is_english(text: str, threshold: float = 0.85) -> bool:
    """粗略英文判定：拉丁字母占非空白字符比例 ≥ threshold。

    过滤非英文信源内容（如 TASS/东欧媒体返回的西里尔/保加利亚语），
    保证英文日报定位。全空/无拉丁字符 → False。
    """
    stripped = "".join(text.split())
    if not stripped:
        return False
    latin = len(_LATIN_RE.findall(stripped))
    return latin / len(stripped) >= threshold


def _parse_date(s: str) -> datetime | None:
    """解析 RSS RFC 2822（'Wed, 05 Aug 2026 12:20:10 +0000'）与 Atom ISO 8601
    （'2026-08-05T10:00:00Z'）。解析失败/空 → None（视为无日期素材）。"""
    if not s:
        return None
    s = s.strip()
    try:  # ISO 8601（含 Z 结尾与 date-only）
        iso = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:  # RFC 2822
        dt = email.utils.parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def is_stale(item: dict, max_age_days: int = MAX_STALE_DAYS) -> bool:
    """时效过滤：date 字段存在且明显过期（> max_age_days）→ True（排除/降权）；
    无 date 字段（page 源、无 pubDate 的 RSS）→ False（保留，RSS 通常有日期）。"""
    dt = _parse_date(item.get("date", ""))
    if dt is None:
        return False
    return datetime.now(timezone.utc) - dt > timedelta(days=max_age_days)


def _topic_penalty(title: str, plate: int) -> int:
    """题材降权（终审 I-4）：标题命中版块负向关键词 → 1（明显不相关，降权）。"""
    t = title.lower()
    return 1 if any(k in t for k in TOPIC_OFF_KEYWORDS.get(plate, ())) else 0


def _dedup(items: list[dict]) -> list[dict]:
    """去重（终审 I-2）：同 URL / 同标题（归一化）只保留首个。"""
    seen_urls, seen_titles, out = set(), set(), []
    for it in items:
        url = it.get("url", "")
        norm_title = " ".join(it.get("title", "").lower().split())
        if url in seen_urls or norm_title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(norm_title)
        out.append(it)
    return out


def _supply_priority(item: dict, slot: str) -> int:
    """按单供给优先（终审 C-1c）：已按单供给（used=True）且规格匹配该槽位的素材优先入选。

    slot: 'main'（目标 ≥200 词）或 'brief'（目标 <200 词）——用 request.words
    判断供给时的目标槽位。used 但槽位不匹配的素材与未供给素材同等对待
    （宁缺勿滥：供给的 60 词简讯不抢占主条，反之亦然）。
    """
    req = item.get("request") or {}
    target_max = (req.get("words") or [0, 0])[1]
    spec_match = bool(req) and ((slot == "main" and target_max >= 200)
                                or (slot == "brief" and target_max < 200))
    return 0 if (item.get("used") and spec_match) else 1


def pick_main_stories(news: list[dict], n: int = 2, plate: int = 1) -> list[dict]:
    """选 n 条中长篇主条：题材匹配 > 按单供给 > 亲中信源 > 长摘要。

    空摘要素材（page 源 words=0）不入选——宁缺勿滥，避免 BODY 空版；
    非英文素材（标题或摘要）同样过滤；过期素材（date >30 天）排除（I-3）；
    同 URL/同标题去重（I-2）；明显与版块题材不相关的标题降权（I-4）。
    """
    pool = [x for x in _dedup(news)
            if not is_stale(x)
            and x.get("summary", "").strip()
            and _is_english(x["title"] + " " + x["summary"])]
    return sorted(pool, key=lambda x: (
        _topic_penalty(x["title"], plate),
        _supply_priority(x, "main"),
        KIND_RANK.get(x["kind"], 9),
        -len(x["summary"])))[:n]


def pick_briefs(news: list[dict], exclude: set, n: int = 4, plate: int = 1) -> list[dict]:
    """选 n 条简讯（排除主条）：题材匹配 > 按单供给 > 亲中信源 > 短摘要。

    过滤与 pick_main_stories 一致（时效/去重/英文/空摘要）。
    """
    pool = [x for x in _dedup(news)
            if x["url"] not in exclude
            and not is_stale(x)
            and x.get("summary", "").strip()
            and _is_english(x["title"] + " " + x["summary"])]
    pool.sort(key=lambda x: (
        _topic_penalty(x["title"], plate),
        _supply_priority(x, "brief"),
        KIND_RANK.get(x["kind"], 9),
        len(x["summary"])))
    return pool[:n]


_TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(s: str) -> str:
    r"""仅供测试/参考：管线统一由 linotype build.py 转义，本函数不参与成版。

    字符集（`\ { } & % $ # _ ~ ^`，除反斜杠外与 linotype build.py 一致——
    build.py 故意不转义 `\` 以保护自身 **bold** 渲染）。注意不要用它预转义
    plates，会造成双重转义。
    """
    return re.sub(r"[\\{}&%$#_~^]", lambda m: _TEX_ESCAPES[m.group()], s)


def byline_of(news: dict) -> str:
    """归属铁律：有记者 `By {记者} · {站点}`，无记者 `By {站点} News Desk`。"""
    if news.get("author"):
        return f"By {news['author']} · {news['source']}"
    return f"By {news['source']} News Desk"


def split_paragraphs(text: str, max_paras: int = 4) -> list[str]:
    """摘要 → 段落（按句号+空白分段，最多 max_paras 段）。"""
    paras = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [p.strip() for p in paras if p.strip()][:max_paras]


def write_plate(p: dict, idx: int) -> str:
    """一个版 → plates/pN.md 文本（linotype 字段格式）。

    主条若无带摘要素材则返回 ""（宁缺勿滥，跳过该版并告警）。
    字段值一律原始文本：转义（含 **bold**）由 linotype build.py 统一处理。
    """
    out = []
    # 题材降权记录（终审 I-4）：列出池内被负向关键词命中的素材，供审料门人工复核
    off_topic = [x["title"] for x in p["news"]
                 if x.get("summary", "").strip() and _topic_penalty(x["title"], idx)]
    if off_topic:
        shown = "、".join(t[:40] for t in off_topic[:3])
        print(f"  ⚠️ P{idx}: {len(off_topic)} 条题材不匹配素材降权（{shown}…）")
    main = pick_main_stories(p["news"], 2, idx)
    if not main:
        print(f"  ⚠️ 版 P{idx}: 无带摘要主条素材，跳过该版（宁缺勿滥）")
        return ""
    briefs = pick_briefs(p["news"], {x["url"] for x in main}, 4, idx)
    # 版头: P1 用 main-aside（主条 2 栏 + 侧栏），其余等宽多栏
    if idx == 1:
        out.append("LAYOUT: main-aside")
    else:
        out.append("COLUMNS: 3")
    out.append("KICKER: " + PLATE_KICKERS.get(idx, "CHINA TECH"))
    out.append("HEADLINE: " + main[0]["title"])
    out.append("DECK: " + main[0].get("summary", "")[:200])
    out.append("BYLINE: " + byline_of(main[0]))
    out.append("BODY:")
    for para in split_paragraphs(main[0].get("summary", "")):
        out.append(para)
    out.append("")
    # 副主条: STORY-B（build.py 解析后 P1 进侧栏 aside，P2-P4 渲染为 subheadline+正文）
    # 注意: STORY-B 后直接跟正文段，不能再写 "BODY:"（会把段落路由回主 body）
    if len(main) > 1:
        out.append("STORY-B: " + main[1]["title"])
        for para in split_paragraphs(main[1].get("summary", "")):
            out.append(para)
        out.append("")
    if briefs:
        out.append("BRIEFS:")
        for b in briefs[:3]:
            out.append(f"**{b['title'][:60]}:** {b.get('summary', '')[:150]} — {b['source']}.")
    return "\n".join(out)


def write_plates(results: dict, out_dir: Path) -> None:
    """写 <out_dir>/plates/p1.md ... p4.md（linotype build.py 消费 plates/ 目录）。"""
    plates_dir = out_dir / "plates"
    plates_dir.mkdir(parents=True, exist_ok=True)
    plate_names = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    for plate, news in results.items():
        idx = plate_names.get(plate)
        if idx is None or not news:
            print(f"  ⚠️ {plate}: 无素材，跳过")
            continue
        text = write_plate({"news": news}, idx)
        if not text:
            continue  # write_plate 已告警（无带摘要主条）
        (plates_dir / f"p{idx}.md").write_text(text, encoding="utf-8")
        print(f"  ✅ plates/p{idx}.md ({len(news)} 条素材 → 2 主条 + 3 简讯)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fetch_results")   # fetch_sources.py 的 fetch_results.json（或 supply 补充后的合并 JSON）
    ap.add_argument("out_dir")
    args = ap.parse_args()
    results = json.load(open(args.fetch_results))
    write_plates(results, Path(args.out_dir))
