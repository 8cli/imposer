# Imposer — Linotype 的拼版工（会话状态交接）

> 保存：2026-08-05 13:20 UTC — 最终交付：终审 CLEAN + 公开仓库 + agent 改写架构
> 晚间更新（22:00 UTC）：P4 放宽（中国科技 + 国际突破）+ 全文优先供给（imposer 52/52 回归）
> 状态：**全部完成并验证**（imposer 52/52 回归 + linotype 25/25；双仓库已推送 GitHub；E2E 首期样报产出 + 全文路径实测）
> 完整开发史：`docs/DEVELOPMENT-HISTORY.md`（34 条提交的调试全记录）
> 公开仓库：**https://github.com/8cli/imposer**（MIT，master @ 4d6d39a）

## 一、项目定位

**Imposer 是 Linotype 排版引擎的拼版工（compositor）**——需求驱动的英文日报编排器：

- Linotype 是**需求方**：版面缺内容时输出补稿单 `demand.json`（fill % / 缺口 pt / 需求规格）
- Imposer 是**供给方**：按单找稿（topic × words × min_kind）→ 压缩改写 → 补稿 → 重排 → 直到"已填满"

**核心差异化**：需求-供给契约（比单向信号更精确——引擎明确说缺什么）。全面亲中（中国官方媒体为主源）、只压缩不扩写（用户铁律）、诚实失败（不编造）。

## 二、完整能力

### 核心组件（skill/scripts/）

| 组件 | 文件 | 能力 |
|---|---|---|
| 信源配置 | `sources.json` | 60 已验证源（P1 国际军事 / P2 AI 科技 / P3 太空 / P4 科技：中国 + 国际突破）；CNSA/ESA/OpenAI/Anthropic 带 `rsshub` 字段走本机 RSSHub（源码 dev 模式 @1201，含自定义路由） |
| 信源抓取器 | `fetch_sources.py` | 并发 RSS+主页（as_completed + 8s 超时，55 源 ~28s）、XML 实体容错、英文过滤 |
| 需求解析器 | `parse_demand.py` | 读 linotype 输出 + demand.json → 健康报告（4 种 Overfull 模式） |
| 需求-供给匹配器 | `supply.py` | 按单匹配（topic×words×min_kind）、rewrite 标注、used 去重 |
| 改写压缩器 | `rewrite.py` | **LLM 压缩兜底**（只压缩不扩写铁律；主路径是 agent 执行） |
| 素材成版器 | `build_plates.py` | 素材 → linotype 字段格式 plates（归属/配比/时效/跨版去重/题材降权） |
| 回归套件 | `tests/run_tests.py` | **54 项**（fetch 10 / demand 4 / supply 16 / build_plates 19 / rewrite 5） |

### 与 linotype 的接口（跨仓库协议）

- linotype `build.py --demand`：autofit 收敛后按 fill 缺口输出 demand.json（Task 3 完成，25/25 回归不破）
- linotype `--docopts fill_min=0.65`：可配置太空阈值（默认 0.45；0.65 严肃报纸标准），从 cls docopts 过滤防 keyval 错误

### 需求-供给契约（demand.json 协议）

```json
{"plates": {"P3": {"fill": 0.31, "deficit_pt": 104.2, "requests": [
  {"type": "brief", "count": 2, "words": [60, 90], "topic": "space", "min_kind": "agency"}]}}}
```

- 需求类型按缺口：`<100pt → brief` / `100-300pt → main` / `>300pt → deep_dive`
- topic/min_kind 按版：P1 world/military+china-official · P2 ai/tech+company · P3 space+agency · P4 china-tech+china-official

### 代理执行改写架构（用户决策，终审落地）

- **主路径**：supply 标注 `needs_rewrite` + `target_words` → **agent 按 SKILL.md 改写规则直接压缩**（agent 本身是 LLM，零 API 调用）
- **兜底**：rewrite.py 保留（headless cron 备胎，Claude API + SSE 兼容）
- 铁律：只压缩不扩写（≤上限逐字返回）、target_words 硬上限、保留归属

## 三、验证状态

- ✅ **终审 CLEAN**（opus 终审 → fix wave → 2 轮 re-review → 独立重跑实证全过）
- ✅ 回归：imposer **44/44** + linotype **25/25**
- ✅ E2E 实证（真实缓存重跑）：0 归档 URL（2017 旧闻过滤）、0 跨版重复、供给 NASA 简讯真正进版
- ✅ agent 架构：SKILL.md 8 步引导式闭环 + 改写规则章节，PYEOF 零遗留
- ✅ 文档诚实化：README×2 / HISTORY 声明与产物逐项比对通过（上轮虚假实证教训已纠正）
- ✅ 公开仓库推送：imposer @ 4d6d39a、linotype @ 74d5890（含 --demand + fill_min）
- ✅ 持久化：linotype-repo 从 /tmp 迁到 ~/news/linotype-repo（重启不丢）
- ✅ 首期样报：~/news/daily/2026-08-05/out.pdf（2 页 A3 横版 4 版）

## 四、关键架构决策

### 需求-供给契约（项目灵魂）

Linotype 缺内容时下补稿单（demand.json），Imposer 按单找稿。比单向信号更精确——引擎精确告诉你补什么。

### Agent 执行改写（用户洞察，终审落地）

imposer 是 skill，skill 由 agent 调用——agent 本身就是 LLM，改写应由 agent 直接执行。拆除了 rewrite.py 调 API 的绕路（anthropic 包/PEP 668/SSE 解析/CLI 污染一堆坑）。

### 严肃报纸标准（用户决策）

只允许正常留白，空白多就增报道/简讯。fill_min 0.65（可配置）触发补稿单。

### 只压缩不扩写铁律（用户决策）

允许压缩长报道，不允许扩写（质量 + 版面控制）。短素材原样使用，宁缺毋滥。

### 全面亲中（用户决策）

中国官方媒体（GT/Xinhua/CGTN/China Daily）为主源；西方媒体仅补充；智库每期一篇深度。

## 五、终审血泪经验（勿重蹈覆辙）

1. **SKILL.md 闭环脚本必须每轮 build_plates 再生成**——supply 回填缓存后不重成版，plates 永不更新 → 循环空转
2. **used 标记必须持久化**——supply 的 used 是局部集合，回写缓存不带标记 → 第 2 轮重复供给同一批素材
3. **按单供给的素材要槽位优先**——pick 只按 kind_rank 会忽略 request 规格（NASA 简讯被 china-official 压掉）
4. **主条最低词数门槛**——38 词素材不应拿主条头条（MIN_MAIN_WORDS=100）
5. **时效过滤三层兜底**——date 为空时用 URL 日期路径（`/201712/12/`）+ 标题旧年份保守排除
6. **跨版去重要池级**——P3/P4 共用 China Daily RSS、P1/P4 共用 GT/Xinhua，版内去重不够
7. **fix 报告实证必须可复现**——上轮 fix 报告"14 条唯一/P3 全 NASA/2017 不进版"与产物矛盾被否，教训深刻
8. **本地代理返回 SSE 字符串**——ANTHROPIC_BASE_URL 指向转发代理时 messages.create 返回原始 SSE，需解析 `data: {json}` 行
9. **Claude CLI --print 会话污染**——输出混入会话系统提示；stream-json + verbose 才可靠
10. **fill_min 不过 cls**——是 build.py 阈值不是 LaTeX keyval，不过滤会 keyval error + 空 fills 假收敛
11. **空 fills = 假收敛**——编译失败无 Plate content 行，autofit 以空 fills 收敛；必须验证日志有内容
12. **并发抓取用 as_completed**——ex.map 阻塞在最慢线程；as_completed 逐个返回 + 8s 超时

## 六、目录状态

```
~/news/imposer/                    ~/.claude/skills/imposer/ (symlink)
├── SKILL.md  (根, 由 skill/SKILL.md 提供)   ← 编排手册 (agent 面向)
├── README.md / README.zh-CN.md    ← 双语手册
├── LICENSE (MIT)
├── docs/
│   ├── ARCHITECTURE.md            ← 架构决策 + 12 条教训
│   ├── DEVELOPMENT-HISTORY.md     ← 完整开发史 + bug 日志 #1-29
│   └── superpowers/               ← 设计文档 + 实现计划（开发过程产物）
├── skill/
│   ├── SKILL.md                   ← 8 步引导式闭环 + 改写规则
│   ├── scripts/                   ← sources.json + 6 脚本
│   └── tests/                     ← run_tests.py + 5 测试文件（54 项）
├── SESSION-STATE.md               ← 本文件
└── .superpowers/sdd/              ← SDD 工作区（gitignored）

~/news/linotype-repo/              ← linotype 公开仓库（持久，含 --demand + fill_min）
~/news/daily/2026-08-05/           ← 首期样报（out.pdf + plates + demand.json + 归档）

GitHub：
  8cli/linotype  @ 74d5890  main   （排版引擎，需求方）
  8cli/imposer   @ 4d6d39a  master （拼版工，供给方）
```

## 七、未来方向（可选增强）

- ✅ **全文优先供给**（2026-08-05 晚间落地）：`fetch_fulltext()` + `supply.py fulltext_fn`——主条/深度规格（≥250 词）缓存只有短摘要时自动抓全文压缩（摘要兜底），实测 66 词摘要 → 272 词全文。缓存 `fulltext` 字段跨轮复用
- ✅ **P4 放宽**（2026-08-05 晚间落地）：中国科技 + 国际科技突破（核聚变等）——linotype 发 `topic:"tech"`/`min_kind:"tech-media"`，sources.json 加 ITER/Phys.org/TechXplore/Nature/IEEE Spectrum/New Scientist（实测 P4 池 80 条）；`_tech_gate` 正向题材门挡国际金融稿
- ✅ **本机 RSSHub**（2026-08-06 早落地）：**源码 dev 模式**（`~/news/rsshub-dev/start.sh`，端口 1201，crontab @reboot 自启）——dev 模式动态加载 `lib/routes/` 路由，加文件即生效。**自定义路由 2 个**：`/cnsa/news`（P3 中国航天官方，最大缺源补齐）、`/esa/newsroom`（ESA 新闻稿带日期）。已接入 sources.json（CNSA/ESA/OpenAI/Anthropic）。Docker 容器退役（1200 仅内置路由）。**教训**：官方 Docker 镜像只带 prod 构建（路由编译进 dist）；可扩展的是源码 dev 模式 / npm 包 registerRoute；反爬源（WaPo/MS/Blue Origin）任何路由都救不了，需换源
- **P3 中国航天新源**：P3 新鲜 china-official 素材仍为零（全被 2017 归档过滤）——需补充活跃中国航天英文源（CNSA 英文站更新慢）
- **topic 信号增强**：综合 RSS 仍会泄漏非科技稿（题材门已兜底主要路径）——可进一步按版块重整 sources.json
- **审料门自动化**：agent 引导式闭环已就位，可进一步自动预审（URL 合法性/题材/时效）减少人工
- **CI 集成**：GitHub Actions 跑 54 项回归（仿 linotype CI）
- **更多主题/版式**：随 linotype 演进

## 八、诚实的话

Imposer 的核心价值——需求-供给闭环——**机制完整、实证可复现、文档诚实**。但"一键日报"在真实信源下仍受素材质量约束（摘要短、综合 RSS 混归档），审料门（agent 引导）是质量兜底。真正的完善需要每日真实产出积累反馈，如同 linotype 的 0 star 起点——社区验证是下一步。
