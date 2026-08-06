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
# P4 2026-08-05 放宽：linotype 发 "tech"（中国科技 + 国际科技突破，如核聚变）；
# 旧 "china-tech" 保留兼容历史 demand 文件
TOPIC_TO_PLATE = {"world/military": 1, "ai/tech": 2, "space": 3, "china-tech": 4, "tech": 4}

# 时效过滤（终审 I-3）：date 字段存在且超过此天数 → 过期素材（如 RSS 里的 2017 归档稿）
MAX_STALE_DAYS = 30

# 主条最低词数（终审 C-1c）：短稿（如 38 词供给简讯）不拿主条头条。
# 素材用尽（版内无 ≥MIN_MAIN_WORDS 词的素材）时回退全池最优——宁缺毋滥的边界。
MIN_MAIN_WORDS = 100

# 主条正文按版上限（2026-08-06 修复：选材/正文用 fulltext 而非 summary）：
#   P1 main-aside 主栏容量大 → 400 词（完整排，填满主栏消除左下角留白）
#   P2-P4 等宽 3 栏容量 ~280 词 → 280 词（防溢出：
#     P3 327 词实测 753pt > 742pt 溢出 141pt）
MAX_MAIN_WORDS = {1: 300, 2: 280, 3: 280, 4: 280}  # P1 血泪 #44/#45/#46: DECK 120 字符后版头 213pt、两栏 264pt/栏（528pt 总容量 ≈ 250 词正文）。主条尽量长让两栏截断后排满；main 栏短于 aside 是版面平衡特性（fill 已达标，报纸允许列尾空隙）

# URL 日期路径兜底（终审 I-3）：China Daily 综合 RSS 部分条目 date 为空，
# 但 URL 携带归档路径 —— /a/201712/12/（YYYYMM/DD）、/page/202608/（YYYYMM）、
# /2026/08/、/2026/08/05/（YYYY/MM[/DD]）
_URL_DATE_RE1 = re.compile(r"/(\d{4})(\d{2})(?:/(\d{2}))?(?=/|\.|\?|$)")
_URL_DATE_RE2 = re.compile(r"/(\d{4})/(\d{2})(?:/(\d{2}))?(?=/|\.|\?|$)")
_YEAR_TOKEN_RE = re.compile(r"\b(?:19\d{2}|20\d{2})\b")

# 题材负向关键词（终审 I-4 轻量实现）：标题命中即与版块题材明显不相关 → 降权
# （P1 题材广不设负向词；P3/P4 共用的 China Daily 综合 RSS 会泄漏纪念/体育类稿件）
TOPIC_OFF_KEYWORDS = {
    # P1 world/military（2026-08-06 血泪 #42: 原为空 → 长度优先把 Brookings
    # 医保论文 11649 词推上主条）。负向词只降权不删除（素材用尽可回退）：
    # 医药/教育/纯国内政策论文，不误杀 China trade/security 国际时事。
    1: ("medicare", "healthcare", "medicaid", "hospital", "student", "loan",
        "tuition", "university", "housing", "weather", "climate change", "ai "),
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
    """解析三种日期格式：
      - epoch 秒/毫秒（'1786005159'，FreshRSS entry.date——2026-08-06 实测
        全部 1508 条是这个格式，此前 _parse_date 不支持 → is_stale 时效过滤
        三层全失效，2017 归档稿只要标题无年份就能进版）
      - Atom ISO 8601（'2026-08-05T10:00:00Z'）
      - RSS RFC 2822（'Wed, 05 Aug 2026 12:20:10 +0000'）
    解析失败/空 → None（视为无日期素材）。"""
    if not s:
        return None
    s = s.strip()
    if s.isdigit():  # epoch 秒（10 位）或毫秒（13 位），时区 UTC
        try:
            ts = int(s)
            if ts > 10**12:  # 毫秒 → 秒
                ts //= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
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


def _url_date(item: dict) -> datetime | None:
    """从 URL 路径提取发布日期（date 为空时的兜底，终审 I-3）。

    覆盖：China Daily `/a/201712/12/WS…`（YYYYMM/DD）、Global Times
    `/page/202608/…`（YYYYMM，日默认 1）、以及 `/2026/08/`、`/2026/08/05/`。
    提取失败/无日期路径 → None（不误判）。
    """
    url = item.get("url", "")
    for rex in (_URL_DATE_RE1, _URL_DATE_RE2):
        m = rex.search(url)
        if not m:
            continue
        parts = [int(g) for g in m.groups() if g]
        try:
            return datetime(parts[0], parts[1],
                            parts[2] if len(parts) > 2 else 1,
                            tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _title_reports_old_year(title: str) -> bool:
    """标题含明显旧年份（比当前年早 ≥2 年）→ 保守排除的辅助信号。

    仅用于 date 空 + URL 无日期路径的条目（终审 I-3 兜底第 2 层）：
    无任何日期信号的条目若标题自述旧年份（如 "2017 trade pact"），
    视为综合 RSS 泄漏的归档稿。真实时间戳（"1900 GMT"）在标题中极罕见，
    摘要中的时间不进此检查（避免 1900 GMT 类误判）。
    """
    now_year = datetime.now(timezone.utc).year
    return any(y <= now_year - 2 for y in
               (int(y) for y in _YEAR_TOKEN_RE.findall(title or "")))


def is_stale(item: dict, max_age_days: int = MAX_STALE_DAYS) -> bool:
    """时效过滤（终审 I-3 三层兜底）：

    1. date 字段存在且明显过期（> max_age_days）→ 排除；
    2. date 为空 → URL 日期路径兜底（`/201712/12/` 等，同标准）→ 排除；
    3. date 空且 URL 无日期路径 → 标题含明显旧年份的保守排除；
       其余真无日期信号的条目保留（RSS 通常有日期，审料门兜底）。
    """
    dt = _parse_date(item.get("date", ""))
    if dt is None:
        dt = _url_date(item)
    if dt is not None:
        return datetime.now(timezone.utc) - dt > timedelta(days=max_age_days)
    return _title_reports_old_year(item.get("title", ""))


def _topic_penalty(title: str, plate: int) -> int:
    """题材降权（终审 I-4）：标题命中版块负向关键词 → 1（明显不相关，降权）。"""
    t = title.lower()
    return 1 if any(k in t for k in TOPIC_OFF_KEYWORDS.get(plate, ())) else 0


# P4 放宽（2026-08-05 用户决策）：P4 从"只中国科技"放宽为"中国科技 + 国际科技突破
# （如核聚变）"。sources.json 新增 6 个国际科技源后，池内 80% 是国际综合新闻 RSS——
# 负向过滤拦不住金融/政治稿（实测 SCMP 巴西借款稿曾命中 main 规格）。加正向题材门：
# 非中国源标题无科技关键词 → 降权；中国官方源（china-official）是 P4 身份核心，
# 仍只走负向过滤（不误杀，中国科技突破仍是主位）。
_TECH_TITLE_RE = re.compile(
    r"\b(fusion|nuclear|energy|solar|wind|electric|battery|chip|semiconductor|quantum|"
    r"robot|robotics|artificial intelligence|\bai\b|algorithm|machine learning|software|"
    r"hardware|computer|computing|data|network|internet|telecom|5g|6g|satellite|launch|"
    r"orbit|rocket|space|lunar|mars|physics|science|scientific|research|biotech|"
    r"biotechnology|gene|genome|drug|vaccine|carbon|climate|material|materials|engineering|"
    r"innovation|startup|technology|tech|smart|digital|cloud|cyber|vehicle|\bev\b)\b", re.I)


def _tech_gate(item: dict, plate: int) -> int:
    """P4 科技题材门：非中国源标题无科技关键词 → 1（降权到题材匹配素材之后）。

    返回 1 的素材仅降权不删除（宁缺毋滥边界：素材用尽仍可回退，正常被科技稿压掉）。
    plate ≠ 4 恒返回 0（其他版块不设正门，保持既有行为）。
    """
    if plate != 4:
        return 0
    if item.get("kind") == "china-official":
        return 0  # 中国官方源 = P4 身份核心，仍只走负向过滤
    return 0 if _TECH_TITLE_RE.search(item.get("title", "")) else 1


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


def _content_words(item: dict) -> int:
    """素材真实长度（2026-08-06 修复）：优先 fulltext（全文词数），
    无 fulltext 才用 summary。

    背景：fetch 层 summary 截到 400 字符（≈60-80 词），长文全在 fulltext
    字段（P1 实测 379 条 ≥200 词全文）。此前按 summary 词数选主条，
    永远选到短摘要 → 主条填不满版面（P1 84% 根因）。按 fulltext 选材
    后主条才真正落到长文。
    """
    text = item.get("fulltext") or item.get("summary") or ""
    return len(text.split())


def _supply_tier(item: dict, slot: str) -> int:
    """按单供给槽位优先（终审 C-1c 加固，3 层）——槽位匹配优先于 kind_rank：

      0 = 按单供给（used=True）+ 槽位匹配 + 词数已在需求区间内（达标填充）
      1 = 按单供给 + 槽位匹配（词数未达标，按距 target 最近者优先）
      2 = 未供给 / 槽位不匹配（中性，与未供给素材同等对待）

    slot: 'main'（目标 ≥200 词）或 'brief'（目标 <200 词）——用 request.words
    判断供给时的目标槽位。原 2 层机制（0/1）在层内仍由 kind_rank 决定，导致
    供给的 NASA 简讯被同层 china-official 素材（亲中权重 0）压掉、进不了
    p3.md 简讯槽——3 层 + 距离轴修复此问题（见 _length_key）。
    """
    req = item.get("request") or {}
    words = req.get("words") or [0, 0]
    spec_match = bool(req) and ((slot == "main" and words[1] >= 200)
                                or (slot == "brief" and words[1] < 200))
    if not (item.get("used") and spec_match):
        return 2
    w = len(item.get("summary", "").split())
    return 0 if words[0] <= w <= words[1] else 1


def _length_key(item: dict, slot: str) -> float:
    """排序长度轴（终审 C-1c）：槽位匹配的供给素材按与 target 的距离（达标先），
    其余按词数（主条长者先 -w、简讯短者先 +w）。

    距离轴先于 kind_rank：56 词的 NASA 供给简讯（距 [60,90] 中值 19）优先于
    33 词的 china-official 素材（距 41）——按单交付的素材真正落到目标槽位。
    """
    req = item.get("request") or {}
    words = req.get("words") or [0, 0]
    spec_match = bool(req) and ((slot == "main" and words[1] >= 200)
                                or (slot == "brief" and words[1] < 200))
    # 供给素材（used=True）已交付改写稿，长度轴用交付词数（summary）匹配规格；
    # 未供给素材用真实长度（fulltext 优先，2026-08-06 修复）——长文才排得上主条
    w = len(item.get("summary", "").split()) if item.get("used") else _content_words(item)
    if item.get("used") and spec_match and words[1]:
        return abs(w - (words[0] + words[1]) / 2)
    return -w if slot == "main" else w


def pick_main_stories(news: list[dict], n: int = 2, plate: int = 1) -> list[dict]:
    """选 n 条中长篇主条：题材匹配 > 按单供给槽位 > 亲中信源 > 长度（达标供给/长者先）。

    过滤：空摘要素材（page 源 words=0）不入选——宁缺勿滥，避免 BODY 空版；
    非英文素材（标题或摘要）同样过滤；过期素材排除（I-3，含 URL 日期兜底）；
    同 URL/同标题去重（I-2）；明显与版块题材不相关的标题降权（I-4）。

    主条最低词数（C-1c）：优先取 ≥MIN_MAIN_WORDS(100) 词的素材；≥100 词素材
    不足 n 条（素材用尽）才回退全池最优补足——38 词的供给简讯不拿头条。
    槽位匹配（tier）先于 kind_rank：供给的主条素材不被未供给素材抢位。
    """
    pool = [x for x in _dedup(news)
            if not is_stale(x)
            and x.get("summary", "").strip()
            and _is_english(x["title"] + " " + x["summary"])]
    ordered = sorted(pool, key=lambda x: (
        _topic_penalty(x["title"], plate),
        _tech_gate(x, plate),
        _supply_tier(x, "main"),
        _length_key(x, "main"),        # 长度（主条长者先）先于信源层级（2026-08-06 去 china-official 优先）
        KIND_RANK.get(x["kind"], 9)))  # 同分决胜：亲中仍占优，但不再独占主条
    big = [x for x in ordered if _content_words(x) >= MIN_MAIN_WORDS]
    if len(big) >= n:
        # 2026-08-06: P1 main-aside 侧栏容量大 → 保持两长主条（侧栏填满）；
        # P2-P4 等宽 3 栏 → 主条1 长（≥250 词深稿）+ STORY-B 中等（150-250 词）——
        # 两个 300+ 词主条在 3 栏超容量（P2 实测 907pt > 742pt 溢出 122%）。
        if plate == 1:
            return big[:n]
        if n == 2:  # 实际成版 n=2：主条1 长 + STORY-B 短副条
            main1 = big[0]
            # STORY-B 选短稿（60-120 词，副条）——3 栏布局两个长主条必超容量
            # （P2 实测 334+297 词 → 907pt > 742pt 溢出 107%）。
            # P3/P4 短副条（78/75 词）不溢出——短副条是 3 栏布局的正确形态。
            # 注意: 从全 ordered 池选（短稿不在 big 里，big 只含 ≥100 词）；
            # 长度判定用 fulltext（2026-08-06：summary 一律 60-80 词，无区分度）
            short = [x for x in ordered if 60 <= _content_words(x) <= 120]
            if short:
                return [main1, short[0]]
        return big[:n]
    return ordered[:n]  # 素材用尽：无 ≥100 词素材（宁缺毋滥边界）


def pick_briefs(news: list[dict], exclude: set, n: int = 4, plate: int = 1) -> list[dict]:
    """选 n 条简讯（排除主条）：题材匹配 > 按单供给槽位 > 规格距离（达标供给/短者先）> 亲中信源。

    过滤与 pick_main_stories 一致（时效/去重/英文/空摘要）。
    规格距离先于 kind_rank（C-1c）：供给的 NASA 简讯（56 词，距 [60,90] 中值 19）
    不被亲中权重 0 的 china-official 素材压掉——按单交付的素材真正落到简讯槽。
    """
    pool = [x for x in _dedup(news)
            if x["url"] not in exclude
            and not is_stale(x)
            and x.get("summary", "").strip()
            and _is_english(x["title"] + " " + x["summary"])]
    pool.sort(key=lambda x: (
        _topic_penalty(x["title"], plate),
        _tech_gate(x, plate),
        _supply_tier(x, "brief"),
        _length_key(x, "brief"),
        KIND_RANK.get(x["kind"], 9)))
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


def _clean_headline(title: str, max_chars: int = 60) -> str:
    """标题清洗（2026-08-06）：超长标题截断到 max_chars（按词界），
    防 3.58× 字号 display 标题溢出/过大（P3 ISRO 84 字符标题实测
    左上角标题过大、单词间距不协调）。按句点/括号截断更自然。
    """
    t = title.strip()
    if len(t) <= max_chars:
        return t
    # 优先在括号前截（去掉补充说明）
    paren = re.search(r'\s*[\(（]', t)
    if paren and paren.start() > 20:
        return t[:paren.start()].strip()
    # 按词界截断到 max_chars
    cut = t[:max_chars]
    last_space = cut.rfind(' ')
    return (cut[:last_space] + '…') if last_space > 15 else cut + '…'


def _clean_deck(summary: str, title: str) -> str:
    """DECK 清洗（2026-08-06）：去掉导航残留（'Home /'）与标题重复开头——
    ISRO 摘要以 'Home / ISRO successfully...' 开头，DECK 重复标题首词。
    """
    s = summary.strip()
    # 去导航残留：'Home /'、'Home/'、'By ...' 前缀
    s = re.sub(r'^Home\s*/?\s*', '', s)
    s = re.sub(r'^(Home|Topics|Latest)\s+', '', s)
    # 标题重复：DECK 以标题开头时去掉（标题已在 HEADLINE）
    t = title.strip()
    if t and (s.startswith(t) or s.startswith(t[:40])):
        s = s[len(t):].strip()
    # 2026-08-06 血泪 #45: DECK 截 120 字符（≈2 行 45pt）而非 250——
    # main-aside 版头 = KICKER+HEADLINE+DECK+BYLINE，DECK 250 字符在 mainW
    # 下排 4-5 行 ≈ 90pt，版头总高 275pt 吃掉版心 37% → main 两栏只剩
    # 233pt/栏，190 词正文被 vsplit 截断 → main 栏底部空 38mm。120 字符
    # 版头降到 ~180pt，main 栏空间 281pt/栏，正文可完整容纳。
    s = s[:120]
    last_space = s.rfind(' ')
    return (s[:last_space] + '…') if last_space > 40 else s + '…'


def split_paragraphs(text: str, max_paras: int = 4) -> list[str]:
    """摘要 → 段落（按句号+空白分段，最多 max_paras 段）。"""
    paras = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [p.strip() for p in paras if p.strip()][:max_paras]


def write_plate(p: dict, idx: int, used_urls: list | None = None, n_briefs: int = 6) -> str:
    """一个版 → plates/pN.md 文本（linotype 字段格式）。

    主条若无带摘要素材则返回 ""（宁缺勿滥，跳过该版并告警）。
    used_urls（可选）：跨版池级去重收集器（终审 I-2）——本版实际采用的
    主条+简讯 URL 追加于此，供 write_plates 累积成四版共享已用集合。
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
    briefs = pick_briefs(p["news"], {x["url"] for x in main}, n_briefs, idx)
    if used_urls is not None:
        used_urls.extend(x["url"] for x in main)
        used_urls.extend(b["url"] for b in briefs)
    # 版头: P1 用 main-aside（主条 2 栏 + 侧栏），其余等宽多栏
    if idx == 1:
        out.append("LAYOUT: main-aside")
    else:
        out.append("COLUMNS: 3")
    out.append("KICKER: " + PLATE_KICKERS.get(idx, "CHINA TECH"))
    out.append("HEADLINE: " + _clean_headline(main[0]["title"]))
    out.append("DECK: " + _clean_deck(main[0].get("summary", ""), main[0]["title"]))
    out.append("BYLINE: " + byline_of(main[0]))
    out.append("BODY:")
    # 主条正文（2026-08-06 修复：优先 fulltext 全文——summary 只截 400 字符
    # ≈60-80 词，主条用摘要永远填不满版面；fulltext 才是真实报道长度）。
    # 按版上限截断（血泪 #18/#19）：
    #   P1 main-aside 主栏容量大 → 400 词（填满主栏消除左下角留白）
    #   P2-P4 等宽 3 栏容量 ~280 词 → 280 词（防溢出：
    #     P3 327 词实测 753pt > 742pt 溢出 141pt）
    main_paras = 25 if idx == 1 else 12  # P1 主条尽量达 400 词 cap（14 段仅 383 词，main 栏底部空 30-40mm）
    cap = MAX_MAIN_WORDS.get(idx, 280)
    main_body = main[0].get("fulltext") or main[0].get("summary", "")
    if len(main_body.split()) > cap:
        # 按词界截到 cap，尽量在句界截（句子完整性优先于字数）
        words = main_body.split()
        cut = words[:cap]
        joined = ' '.join(cut)
        last_sent = max(joined.rfind('. '), joined.rfind('! '), joined.rfind('? '))
        if last_sent > cap * 0.7:
            joined = joined[:last_sent + 1]
        main_body = joined
    for para in split_paragraphs(main_body, max_paras=main_paras):
        out.append(para)
    out.append("")
    # 副主条: STORY-B（build.py 解析后 P1 进侧栏 aside，P2-P4 渲染为 subheadline+正文）
    # 注意: STORY-B 后直接跟正文段，不能再写 "BODY:"（会把段落路由回主 body）
    # 2026-08-06：正文同样 fulltext 优先（P1 侧栏容量大，第二条长文用全文截断填侧栏；
    # P2-P4 副条按 fulltext 60-120 词选定，正文即全文长度）
    if len(main) > 1:
        out.append("STORY-B: " + _clean_headline(main[1]["title"]))
        story_b = main[1].get("fulltext") or main[1].get("summary", "")
        story_b_cap = 200 if idx == 1 else 120
        if len(story_b.split()) > story_b_cap:
            words = story_b.split()
            joined = ' '.join(words[:story_b_cap])
            last_sent = max(joined.rfind('. '), joined.rfind('! '), joined.rfind('? '))
            if last_sent > story_b_cap * 0.7:
                joined = joined[:last_sent + 1]
            story_b = joined
        for para in split_paragraphs(story_b, max_paras=main_paras):
            out.append(para)
        out.append("")
    if briefs:
        out.append("BRIEFS:")
        for b in briefs[:n_briefs]:
            out.append(f"**{_clean_headline(b['title'])}:** {b.get('summary', '')[:150]} — {b['source']}.")
    return "\n".join(out)


def write_plates(results: dict, out_dir: Path) -> None:
    """写 <out_dir>/plates/p1.md ... p4.md（linotype build.py 消费 plates/ 目录）。

    跨版去重（终审 I-2）：四版共享一个已用 URL 集合 seen——同一 URL 的素材
    只在首个版使用，后续版跳过（换素材/跳过）。根因是 P3/P4 共用 China Daily
    综合 RSS、P1/P4 共用 GT/Xinhua：池级去重直接从源头消除跨版重复。
    """
    plates_dir = out_dir / "plates"
    plates_dir.mkdir(parents=True, exist_ok=True)
    plate_names = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    # 简讯数按版（2026-08-06 fulltext 修复后实测）：
    #   P1 main-aside 达标 97%（主条 359 + STORY-B 171 + 3 简讯已满版心）
    #   P3 达标 99.9%（主条 265 + STORY-B 100 + 3 简讯恰满）
    #   P2 89% / P4 90.7% —— 主条+副条偏短，需 4 条简讯补填充
    #     （P2 缺 44.6pt、P4 缺 31.7pt；实测 +2 条（5 条）致 P2 溢出 744.5pt
    #      > 742.6pt 且 autofit 压字号拖累 P3 掉到 90.6%——只 +1 条）
    #   血泪 #16：inbrief 宏支持多组（每 3 条一组），3 条硬编码上限早已解除
    # 2026-08-06 第七轮实测微调: P3 92.1% 缺 1 条（3→4 补填充），
    # P4 104.5% 超量（4→3 防全局压字号拖累 P2/P3——P4 超 33.7pt 微超
    # 会触发 autofit 溢出迭代压字号，P2/P3 掉到 92%）
    briefs_per_plate = {1: 3, 2: 6, 3: 4, 4: 3}
    seen = set()  # 四版池级已用 URL（终审 I-2 跨版去重）
    for plate, news in results.items():
        idx = plate_names.get(plate)
        if idx is None or not news:
            print(f"  ⚠️ {plate}: 无素材，跳过")
            continue
        pool = [x for x in news if x["url"] not in seen]
        if not pool:
            print(f"  ⚠️ {plate}: 素材 URL 已全部被其他版使用（跨版去重），跳过")
            continue
        used_urls = []
        text = write_plate({"news": pool}, idx, used_urls, briefs_per_plate.get(idx, 6))
        if not text:
            continue  # write_plate 已告警（无带摘要主条）
        seen.update(used_urls)
        (plates_dir / f"p{idx}.md").write_text(text, encoding="utf-8")
        print(f"  ✅ plates/p{idx}.md ({len(pool)} 条素材 → 2 主条 + 3 简讯)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fetch_results")   # fetch_sources.py 的 fetch_results.json（或 supply 补充后的合并 JSON）
    ap.add_argument("out_dir")
    args = ap.parse_args()
    results = json.load(open(args.fetch_results))
    write_plates(results, Path(args.out_dir))
