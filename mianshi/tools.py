"""本地规则层:技能识别、匹配度、STAR 检查、数字校验。

模型负责说人话,这里负责给可复算的数。
"""

from __future__ import annotations

import re
import unicodedata

SKILL_WORDS = (
    "Python", "Java", "C++", "SQL", "Excel", "PPT", "SPSS", "Tableau", "Linux", "Git",
    "Axure", "Visio", "Figma", "A/B 测试", "埋点", "数据清洗", "数据可视化", "指标体系",
    "用户画像", "用户研究", "竞品分析", "需求文档", "原型", "项目管理", "数据分析",
    "商业分析", "机器学习", "深度学习", "NLP", "大模型", "RAG", "向量库", "提示词",
    "保险", "理赔", "核保", "精算", "风控", "客户维护", "活动策划", "文案", "新媒体",
    "运营", "增长", "销售", "谈判", "财务", "会计", "审计", "法律", "医学", "护理",
    "教育", "英语", "CET-6", "手语", "公文写作", "报表", "社群",
)

_STOP = set("""的 了 和 是 在 有 与 及 或 对 我们 你们 他们 这 那 个 岗位 工作 负责 能够
具备 要求 优先 熟悉 了解 相关 经验 能力 以上 以及 进行 一个 这个 公司 团队 职责
任职 描述 加分 项 者 优先考虑 请 你 将 会 可以 需要 良好 优秀 一定 较强 熟练""".split())

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_EN = re.compile(r"[A-Za-z][A-Za-z+#./-]{1,}")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_PUNCT_FIX = ((r"[，,]{2,}", "，"), (r"[。.]{2,}", "。"), (r"[ \t]{2,}", " "))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    for pat, rep in _PUNCT_FIX:
        text = re.sub(pat, rep, text)
    return text.replace("\r\n", "\n").strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。!?！？\n]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def bullets(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-·•*").strip()
        if not line:
            continue
        if len(line) > 80 and "；" in line:
            out.extend(p.strip() for p in line.split("；") if p.strip())
        else:
            out.append(line)
    return out


def contains_quote(quote: str, text: str, min_len: int = 6) -> bool:
    q = normalize(quote)
    return len(q) >= min_len and q in normalize(text)


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def grounded(claim: str, text: str, min_run: int = 8) -> bool:
    """claim 里是否有一段连续 min_run 字能在 text 里找到(忽略空格)。

    模型常把原句改写成「原句 + 对应 JD 的哪条」,逐字比对会全丢;
    但只放行整句又会放过纯概括。取最长公共连续片段更合适。
    """
    a, b = _squeeze(claim), _squeeze(text)
    if len(a) < min_run:
        return False
    return any(a[i:i + min_run] in b for i in range(len(a) - min_run + 1))


def numbers(text: str) -> list[str]:
    return _NUM.findall(text or "")


def new_numbers(before: str, after: str) -> list[str]:
    old = set(numbers(before))
    return [n for n in numbers(after) if n not in old]


def _grams(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in _CJK.findall(text):
        for size in (2, 3, 4):
            for i in range(len(run) - size + 1):
                g = run[i:i + size]
                if g in _STOP or any(ch in _STOP for ch in g) and len(g) <= 2:
                    continue
                counts[g] = counts.get(g, 0) + 1
    for w in _EN.findall(text):
        w = w.lower()
        if len(w) >= 2:
            counts[w] = counts.get(w, 0) + 1
    return counts


def keywords(text: str, limit: int = 30) -> list[str]:
    """按「词长 × 频次」排序取词,长词优先(短词太容易是通用字)。"""
    counts = _grams(text)
    ranked = sorted(counts.items(), key=lambda kv: (kv[1] * (len(kv[0]) ** 2), len(kv[0])), reverse=True)
    picked: list[str] = []
    for word, _ in ranked:
        if any(word in p for p in picked):
            continue
        picked.append(word)
        if len(picked) >= limit:
            break
    return picked


def skills(text: str) -> list[str]:
    low = (text or "").lower()
    return [s for s in SKILL_WORDS if s.lower() in low]


def coverage(jd: str, resume: str) -> dict:
    need = skills(jd)
    have = skills(resume)
    matched = [s for s in need if s in have]
    missing = [s for s in need if s not in have]
    ratio = round(len(matched) / len(need), 2) if need else 0.0
    kws = keywords(jd, 15)
    norm_resume = normalize(resume)
    kw_hit = [k for k in kws if k in norm_resume]
    kw_ratio = round(len(kw_hit) / len(kws), 2) if kws else 0.0
    if need:
        score = int(round(100 * (0.6 * ratio + 0.4 * kw_ratio)))
    else:
        score = int(round(100 * kw_ratio))
    return {
        "score": max(0, min(100, score)),
        "skills_need": need, "skills_have": have,
        "matched": matched, "missing": missing,
        "skill_ratio": ratio, "keyword_need": kws,
        "keywords_hit": kw_hit, "keyword_ratio": kw_ratio,
    }


_STAR_MARK = {
    "situation": ("当时", "背景", "那会儿", "期间", "实习", "项目里", "去年", "大三", "大四", "在"),
    "task": ("负责", "任务", "目标", "要解决", "需要我", "被要求", "指标", "要求我"),
    "action": ("我", "做了", "写了", "搭", "跑了", "沟通", "协调", "拆", "实现", "设计", "用", "拉"),
    "result": ("结果", "最终", "提升", "降低", "增长", "达到", "完成", "上线", "拿到", "节省", "%", "倍"),
}


def star_check(answer: str) -> dict:
    text = normalize(answer)
    hits = {k: any(m in text for m in marks) for k, marks in _STAR_MARK.items()}
    return {"hits": hits, "count": sum(hits.values())}


_VAGUE = ("大概", "可能", "应该", "差不多", "参与", "协助", "一些", "有点", "比较", "很多", "大量", "各种", "等等", "之类")


def vague(text: str) -> list[str]:
    return [w for w in _VAGUE if w in (text or "")]


def question_ok(question: str, terms: list[str]) -> bool:
    return any(t in question for t in terms)


def clamp(text: str, limit: int) -> str:
    text = normalize(text)
    return text if len(text) <= limit else text[:limit] + "…"


def match_line(result: dict) -> str:
    if not result["skills_need"]:
        return f"匹配度 {result['score']}/100(JD 里没识别到技能词,只按关键词覆盖算)"
    return (f"匹配度 {result['score']}/100"
            f"(技能覆盖 {len(result['matched'])}/{len(result['skills_need'])},"
            f"关键词覆盖 {len(result['keywords_hit'])}/{len(result['keyword_need'])} 项)")


TOOLS = [
    {"name": "job_detail", "desc": "读取当前岗位的标题、公司、JD 全文与简历全文"},
    {"name": "coverage", "desc": "返回技能与关键词覆盖明细(本地算,不是模型判断)"},
]


def execute(name: str, ctx: dict) -> dict:
    """执行一次工具调用;只读,不改状态。"""
    if name == "job_detail":
        return {
            "title": ctx.get("title", ""), "company": ctx.get("company", ""),
            "jd": ctx.get("jd", ""), "resume": ctx.get("resume", ""),
        }
    if name == "coverage":
        cov = coverage(ctx.get("jd", ""), ctx.get("resume", ""))
        return {k: cov[k] for k in ("score", "matched", "missing", "skill_ratio", "keyword_ratio")}
    return {"error": f"未知工具:{name}"}
