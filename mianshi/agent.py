"""模型主路径:评审、出题、点评、措辞建议。没 key 时整体退回 mock。"""

from __future__ import annotations

import json

from . import llm, mock, tools

MAX_STEPS = 12

ANALYZE_SYSTEM = """你是招聘方的简历评审,只依据给定的 JD 与简历原文说话。

规则:
1. 只输出 JSON,不要解释。
2. strengths 每一条都必须能在简历原文里找到对应表述,不许脑补。
3. risks 说明 JD 要什么、简历缺什么,不许出现两份原文里都没有的数字。
4. advice 最多 4 条,每条不超过 60 字,可执行,不许写"提升综合能力"这类空话。
5. 匹配度分数由外部系统计算,你不要输出分数。

JSON 模板:
{"strengths": ["..."], "risks": ["..."], "advice": ["..."]}"""

GEN_SYSTEM = """你是面试官,依据 JD 与简历出面试题。

规则:
1. 只输出 JSON。
2. 每道题必须落在 JD 里的某个具体要求上,题干里要出现那个要求的原词。
3. 不出"你最大的缺点是什么"这类与岗位无关的通用题,除非题量还不够。
4. why 用一句话说明这道题想核实什么,不超过 50 字。

JSON 模板:
{"questions": [{"question": "...", "why": "..."}]}"""

REVIEW_SYSTEM = """你是面试陪练,评价候选人对一道面试题的回答。

可用工具:
- job_detail: 读取岗位 JD 与简历全文
- coverage: 读取技能覆盖明细

每一步只输出一个 JSON 对象,二选一:
{"tool": "job_detail", "args": {}}
{"final": {"score": 1, "good": ["..."], "fix": ["..."], "rewrite": "..."}}

final 字段规则:
- score 取 1-5 的整数。
- good 每条必须是回答原文里能找到的句子(≥6 字),不许概括。
- fix 最多 4 条,每条不超过 60 字,指出具体缺什么。
- rewrite 是改好的回答示范;不许出现回答里没有的数字、公司名、人名;没有把握就给空字符串。

当前题目: __QUESTION__"""

POLISH_SYSTEM = """你是简历编辑,只做措辞层面的修改。

规则:
1. 只输出 JSON。
2. items 里每条给出 orig(必须是简历里的原句,一字不改)与 new(改后版本)。
3. new 不许新增原句里没有的数字;原句有的数字必须保留。
4. 不许多出事实:不新增公司、项目、时间、头衔。
5. why 一句话说明改了什么,不超过 30 字。

JSON 模板:
{"items": [{"orig": "...", "new": "...", "why": "..."}]}"""


def _use_model(cfg) -> bool:
    return bool((cfg or {}).get("api_key"))


# 校验 ------------------------------------------------------------------
def verify_analysis(resume: str, jd: str, data: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    strengths = []
    for s in data.get("strengths") or []:
        s = tools.clamp(str(s), 80)
        if tools.grounded(s, resume):
            strengths.append(s)
        else:
            problems.append(f"「{tools.clamp(s, 30)}」在简历里找不到对应原句,已丢弃")
    risks = []
    for r in data.get("risks") or []:
        r = tools.clamp(str(r), 80)
        if tools.new_numbers(resume + jd, r):
            # 风险项里的数字常是从日期区间推出来的月数,不当成造假;
            # 只提示一句,让它自己去核。
            problems.append(f"提示:风险项「{tools.clamp(r, 30)}」含原文没有的数字,请自行核对")
        risks.append(r)
    advice = []
    for a in data.get("advice") or []:
        a = tools.clamp(str(a), 60)
        if tools.new_numbers(resume + jd, a):
            problems.append(f"建议「{a}」出现原文没有的数字,已丢弃")
            continue
        advice.append(a)
    return {"strengths": strengths[:3], "risks": risks[:3], "advice": advice[:4]}, problems


def verify_questions(jd: str, resume: str, data: dict, n: int) -> tuple[list[dict], list[str]]:
    terms = tools.skills(jd) or tools.keywords(jd, 10)
    terms = list(terms) + tools.keywords(jd, 12)
    problems: list[str] = []
    out: list[dict] = []
    seen: set[str] = set()
    items = data.get("questions") if isinstance(data, dict) else data
    for item in items or []:
        if not isinstance(item, dict):
            problems.append("有一道题不是对象,已丢弃")
            continue
        q = tools.clamp(str(item.get("question", "")), 100)
        if not q:
            continue
        if q in seen:
            continue
        if not tools.question_ok(q, terms):
            problems.append(f"「{tools.clamp(q, 30)}」没有落到 JD 的具体要求上,已丢弃")
            continue
        seen.add(q)
        out.append({"question": q, "why": tools.clamp(str(item.get("why", "")), 50)})
        if len(out) >= n:
            break
    return out, problems


def verify_review(answer: str, data: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(1, min(5, score or 1))
    good = []
    for g in data.get("good") or []:
        g = tools.clamp(str(g), 80)
        if tools.contains_quote(g, answer, 6):
            good.append(g)
        else:
            problems.append(f"「{g}」在回答里找不到原句,已丢弃")
    fix = [tools.clamp(str(f), 60) for f in (data.get("fix") or []) if str(f).strip()][:4]
    rewrite = tools.clamp(str(data.get("rewrite") or ""), 400)
    if rewrite and tools.new_numbers(answer, rewrite):
        problems.append("示范回答里出现原回答没有的数字,已退回不给示范")
        rewrite = ""
    return {"score": score, "good": good[:3], "fix": fix, "rewrite": rewrite}, problems


def verify_polish(resume: str, data: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    items = []
    for it in (data.get("items") if isinstance(data, dict) else data) or []:
        if not isinstance(it, dict):
            continue
        orig = str(it.get("orig", "")).strip()
        new = str(it.get("new", "")).strip()
        if not orig or not new or not tools.contains_quote(orig, resume, 4):
            problems.append("有一条改动对不上简历原句,已丢弃")
            continue
        if tools.new_numbers(orig, new):
            problems.append(f"「{tools.clamp(orig, 20)}」的改法新增了数字,已丢弃")
            continue
        if len(new) > max(20, int(len(orig) * 2.5)):
            problems.append(f"「{tools.clamp(orig, 20)}」改后长度翻倍过多,已丢弃")
            continue
        items.append({"orig": orig, "new": new, "why": tools.clamp(str(it.get("why", "")), 30)})
    return {"items": items[:6]}, problems


# 主流程 -------------------------------------------------------------------
def analyze(resume: str, job: dict, cfg: dict | None = None, force_mock: bool = False) -> dict:
    jd = job.get("jd", "")
    cov = tools.coverage(jd, resume)
    if force_mock or not _use_model(cfg):
        result = mock.analyze(resume, jd)
        result["score"] = cov["score"]
        result["coverage"] = cov
        return result
    user = f"【岗位】{job.get('title', '')} @ {job.get('company', '')}\n【JD】\n{jd}\n\n【简历】\n{resume}"
    text = llm.chat(
        [{"role": "system", "content": ANALYZE_SYSTEM}, {"role": "user", "content": user}],
        cfg, temperature=0.2, max_tokens=1200,
    )
    data = llm.extract_json(text)
    body, problems = verify_analysis(resume, jd, data if isinstance(data, dict) else {})
    return {"score": cov["score"], "coverage": cov, **body, "problems": problems, "offline": False}


def gen_questions(job: dict, resume: str, n: int = 5, cfg: dict | None = None,
                  force_mock: bool = False) -> dict:
    jd = job.get("jd", "")
    if force_mock or not _use_model(cfg):
        qs = mock.questions(jd, resume, n)
        return {"questions": qs, "problems": [], "offline": True}
    user = f"【岗位】{job.get('title', '')}\n【JD】\n{jd}\n\n【简历要点】\n{tools.clamp(resume, 2000)}\n\n请出 {n} 道题。"
    data, problems = {}, []
    for _ in range(2):
        text = llm.chat(
            [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": user}],
            cfg, temperature=0.5, max_tokens=1400,
        )
        data = llm.extract_json(text)
        qs, problems = verify_questions(jd, resume, data, n)
        if len(qs) >= min(2, n):
            return {"questions": qs, "problems": problems, "offline": False}
    return {"questions": [], "problems": problems + ["两轮都没出到合规的题"], "offline": False}


def review(job: dict, resume: str, question: str, answer: str,
           cfg: dict | None = None, force_mock: bool = False) -> dict:
    if force_mock or not _use_model(cfg):
        return mock.review(question, answer)
    ctx = {"title": job.get("title", ""), "company": job.get("company", ""),
           "jd": job.get("jd", ""), "resume": resume}
    system = REVIEW_SYSTEM.replace("__QUESTION__", question)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"【回答】\n{answer}"},
    ]
    final: dict | None = None
    problems: list[str] = []
    for _ in range(MAX_STEPS):
        text = llm.chat(messages, cfg, temperature=0.3, max_tokens=1200)
        try:
            obj = llm.extract_json(text)
        except llm.LLMError:
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "上一步不是合法 JSON,只输出一个 JSON 对象。"})
            continue
        if isinstance(obj, dict) and obj.get("tool"):
            result = tools.execute(str(obj["tool"]), ctx)
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "工具返回:" + json.dumps(result, ensure_ascii=False)})
            continue
        if isinstance(obj, dict) and isinstance(obj.get("final"), dict):
            final = obj["final"]
            break
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": '要么 {"tool": ...},要么 {"final": {...}}。'})
    if final is None:
        result = mock.review(question, answer)
        result["problems"] = ["模型没给出最终点评,退回规则检查"]
        return result
    body, problems2 = verify_review(answer, final)
    star = tools.star_check(answer)
    body.update({"star": star, "vague": tools.vague(answer), "length": len(tools.normalize(answer)),
                 "problems": problems + problems2, "offline": False})
    return body


def polish(resume: str, job: dict | None = None, cfg: dict | None = None,
           force_mock: bool = False) -> dict:
    if force_mock or not _use_model(cfg):
        return mock.polish(resume)
    user = f"【简历】\n{resume}"
    if job and job.get("jd"):
        user += f"\n\n【目标岗位 JD】\n{tools.clamp(job['jd'], 1200)}"
    text = llm.chat(
        [{"role": "system", "content": POLISH_SYSTEM}, {"role": "user", "content": user}],
        cfg, temperature=0.3, max_tokens=1600,
    )
    data = llm.extract_json(text)
    body, problems = verify_polish(resume, data if isinstance(data, dict) else {})
    body.update({"problems": problems, "offline": False})
    return body
