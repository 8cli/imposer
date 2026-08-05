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
import json
import re
from pathlib import Path

# 素材亲中优先级（与 supply.py 的 min_kind_rank 一致）：越小越优先
KIND_RANK = {"china-official": 0, "thinktank": 1, "agency": 2, "company": 3,
             "china-ai": 4, "independent": 5, "tech-media": 6, "aggregator": 7,
             "western": 8}

# 每版结构: 中长篇主条 ×2 + BRIEFS ×3（linotype inbrief/asidebriefs 各渲染 3 条）
PLATE_KICKERS = {1: "WORLD & DIPLOMACY", 2: "AI & TECH", 3: "SPACE EXPLORATION", 4: "CHINA TECH"}

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


def pick_main_stories(news: list[dict], n: int = 2) -> list[dict]:
    """选 n 条中长篇主条：优先亲中信源 + 长摘要。

    空摘要素材（page 源 words=0）不入选——宁缺勿滥，避免 BODY 空版；
    非英文素材（标题或摘要）同样过滤。
    """
    pool = [x for x in news if x.get("summary", "").strip() and _is_english(x["title"] + " " + x["summary"])]
    return sorted(pool, key=lambda x: (KIND_RANK.get(x["kind"], 9), -len(x["summary"])))[:n]


def pick_briefs(news: list[dict], exclude: set, n: int = 4) -> list[dict]:
    """选 n 条简讯（排除主条），优先亲中信源 + 短摘要；空摘要/非英文不入选。"""
    pool = [x for x in news if x["url"] not in exclude and x.get("summary", "").strip()
            and _is_english(x["title"] + " " + x["summary"])]
    pool.sort(key=lambda x: (KIND_RANK.get(x["kind"], 9), len(x["summary"])))
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
    main = pick_main_stories(p["news"], 2)
    if not main:
        print(f"  ⚠️ 版 P{idx}: 无带摘要主条素材，跳过该版（宁缺勿滥）")
        return ""
    briefs = pick_briefs(p["news"], {x["url"] for x in main}, 4)
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
