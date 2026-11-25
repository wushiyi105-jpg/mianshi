"""离线模式:没有 key 时用规则给结果,并明确说明哪些是算出来的、哪些没做。"""

from __future__ import annotations

from . import tools


def analyze(resume: str, jd: str) -> dict:
    cov = tools.coverage(jd, resume)
    strengths = [f"简历里已经出现 {s}" for s in cov["matched"][:3]] or ["简历与 JD 的关键词重合较少"]
    risks = [f"JD 要求 {s},简历里没找到对应证据" for s in cov["missing"][:3]]
    advice = []
    if cov["missing"]:
        advice.append(f"补一条能证明「{cov['missing'][0]}」的经历,写清你做了什么")
    if cov["score"] < 60:
        advice.append("把 JD 里的原词写进简历,别只写同义说法")
    advice.append("每条经历补一个可核对的数字,没有数字就写清范围与角色")
    return {
        "score": cov["score"], "coverage": cov,
        "strengths": strengths[:3], "risks": risks[:3], "advice": advice[:4],
        "offline": True,
        "note": "离线模式:匹配度按技能词与关键词覆盖率算,句子只做模板拼接,不做语义判断",
    }


_TEMPLATES = (
    "请举一个你用「{term}」真正做出结果的例子,说清当时的情况和你的动作。",
    "JD 里要求「{term}」,你简历上没有直接体现,如果入职你打算怎么补?",
    "讲一次你在「{term}」上踩坑的经历,你后来改了什么?",
)


def questions(jd: str, resume: str, n: int = 5) -> list[dict]:
    terms = (tools.skills(jd) or tools.keywords(jd, 8))[:n]
    out = []
    for i, term in enumerate(terms):
        out.append({"question": _TEMPLATES[i % len(_TEMPLATES)].format(term=term),
                    "why": f"围绕 JD 里的「{term}」核实真实经验"})
    if len(out) < n:
        extra = [
            ("请用两分钟介绍你自己,重点说和这个岗位最相关的一段经历。", "开场必问,看表达结构"),
            ("你为什么想做这个岗位?说说你了解到的具体工作内容。", "筛掉只看title的人"),
            ("讲一次你和别人意见不一致、最后推动下去的经历。", "看协作与推动力"),
        ]
        out.extend({"question": q, "why": w} for q, w in extra[: n - len(out)])
    return out


def review(question: str, answer: str) -> dict:
    star = tools.star_check(answer)
    vague = tools.vague(answer)
    length = len(tools.normalize(answer))
    score = max(1, min(5, 1 + star["count"] + (1 if length >= 120 else 0)))
    missing = [k for k, v in star["hits"].items() if not v]
    good = []
    if star["hits"]["action"]:
        good.append("有具体动作,不是只讲态度")
    if star["hits"]["result"]:
        good.append("提到了结果")
    fix = []
    if missing:
        fix.append("补上缺少的要素:" + "、".join(missing))
    if vague:
        fix.append("把模糊词换掉:" + "、".join(vague[:4]))
    if length < 80:
        fix.append("回答太短,至少说满 3 句:背景、你做的、结果")
    return {
        "score": score, "star": star, "vague": vague, "length": length,
        "good": good[:3], "fix": fix[:4] or ["结构基本完整,补一个可核对的数字会更稳"],
        "rewrite": "",
        "offline": True,
        "note": "离线模式:只按 STAR 关键词与模糊词做规则检查,不判断内容对不对",
    }


def polish(resume: str) -> dict:
    items = []
    for line in tools.bullets(resume):
        tidy = tools.normalize(line)
        if tidy != line.strip():
            items.append({"orig": line.strip(), "new": tidy, "why": "清理空格与重复标点"})
    return {
        "items": items,
        "offline": True,
        "note": "离线模式:只清理空格、重复标点与列表符号,不替你改写措辞",
    }
