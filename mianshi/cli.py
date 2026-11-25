"""命令行入口:python -m mianshi <子命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, llm, tools
from .db import Database

MOCK_BANNER = "· 离线模式:没配 LLM_API_KEY,或显式 --mock。规则给结论,句子只做模板拼接。"

_OPEN: list[Database] = []


def _db(args) -> Database:
    db = Database(args.db)
    _OPEN.append(db)
    return db


def _close_all() -> None:
    for db in _OPEN:
        try:
            db.close()
        except Exception:
            pass
    _OPEN.clear()


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_analysis(result: dict) -> str:
    cov = result.get("coverage") or {}
    lines = [tools.match_line(cov)] if cov else []
    if cov:
        lines.append(f"  已覆盖:{'、'.join(cov['matched']) or '(无)'}")
        lines.append(f"  缺口:{'、'.join(cov['missing']) or '(无)'}")
    lines.append("")
    lines.append("优势:")
    if result.get("strengths"):
        lines.extend(f"  - {s}" for s in result["strengths"])
    else:
        lines.append("  (无)")
    lines.append("风险:")
    lines.extend(f"  - {r}" for r in result.get("risks", []))
    lines.append("建议:")
    lines.extend(f"  {i}. {a}" for i, a in enumerate(result.get("advice", []), 1))
    if result.get("problems"):
        lines.append("")
        lines.append("校验丢弃:")
        lines.extend(f"  ! {p}" for p in result["problems"])
    if result.get("note"):
        lines.append(result["note"])
    return "\n".join(lines)


def render_questions(result: dict) -> str:
    lines = []
    for i, q in enumerate(result.get("questions", []), 1):
        lines.append(f"[{i}] {q['question']}")
        if q.get("why"):
            lines.append(f"    意图:{q['why']}")
    if result.get("problems"):
        lines.extend(f"! {p}" for p in result["problems"])
    if not lines:
        lines.append("没有合规的题。")
    return "\n".join(lines)


def render_review(result: dict) -> str:
    star = result.get("star", {})
    lines = [f"评分:{result.get('score')}/5"]
    if star:
        hit = [k for k, v in star.get("hits", {}).items() if v]
        lines.append(f"STAR:{len(hit)}/4({'、'.join(hit) or '一个都没提到'})")
    if result.get("vague"):
        lines.append(f"模糊词:{'、'.join(result['vague'])}")
    lines.append("")
    lines.append("站得住的地方:")
    lines.extend(f"  + {g}" for g in result.get("good", []) or ["(无)"])
    lines.append("该改的地方:")
    lines.extend(f"  - {f}" for f in result.get("fix", []) or ["(无)"])
    if result.get("rewrite"):
        lines.append("")
        lines.append("示范:")
        lines.append(result["rewrite"])
    if result.get("problems"):
        lines.append("")
        lines.extend(f"! {p}" for p in result["problems"])
    if result.get("note"):
        lines.append(result["note"])
    return "\n".join(lines)


def render_polish(result: dict) -> str:
    lines = []
    for it in result.get("items", []):
        lines.append(f"- 原:{it['orig']}")
        lines.append(f"  改:{it['new']}")
        if it.get("why"):
            lines.append(f"  因:{it['why']}")
    if not lines:
        lines.append("没有可改的句子。")
    lines.extend(f"! {p}" for p in result.get("problems", []))
    if result.get("note"):
        lines.append(result["note"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mianshi", description="面试 · 求职助手:简历匹配、出题、点评、措辞。")
    p.add_argument("--version", action="version", version=f"mianshi {__version__}")
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    p.add_argument("--db", default="data/mianshi.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("resume", help="导入简历")
    a.add_argument("file")
    a.add_argument("--title", default="")
    sub.add_parser("resumes", help="简历列表")
    g = sub.add_parser("show-resume", help="看一份简历")
    g.add_argument("key")
    r = sub.add_parser("rm-resume", help="删一份简历")
    r.add_argument("key")

    j = sub.add_parser("jd", help="导入岗位 JD")
    j.add_argument("file")
    j.add_argument("--title", required=True)
    j.add_argument("--company", default="")
    j.add_argument("--resume", default="", help="绑定的简历 id 或标题")
    sub.add_parser("jobs", help="岗位列表")
    s = sub.add_parser("show-job", help="看一个岗位")
    s.add_argument("key")

    an = sub.add_parser("analyze", help="匹配度分析")
    an.add_argument("job")
    ge = sub.add_parser("gen", help="生成面试题")
    ge.add_argument("job")
    ge.add_argument("--n", type=int, default=5)
    sub.add_parser("mock", help="看已生成的题").add_argument("job")
    rv = sub.add_parser("review", help="点评一次回答")
    rv.add_argument("job")
    rv.add_argument("qid")
    rv.add_argument("answer")
    sub.add_parser("history", help="模拟记录").add_argument("job")
    po = sub.add_parser("polish", help="措辞建议(不覆盖原稿)")
    po.add_argument("resume")
    po.add_argument("--job", default="")
    sub.add_parser("stats", help="统计")
    w = sub.add_parser("web", help="启动 Web 界面")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8771)
    return p


def _job_or_exit(db: Database, key, as_json: bool) -> dict:
    job = db.get_job(key)
    if not job:
        print(f"❌ 找不到岗位「{key}」", file=sys.stderr)
        raise SystemExit(1)
    return job


def _resume_text(db: Database, job: dict) -> str:
    rid = job.get("resume_id")
    if rid:
        r = db.get_resume(int(rid))
        if r:
            return r["text"]
    r = db.get_resume(job.get("title", ""))
    if r:
        return r["text"]
    rs = db.list_resumes()
    return rs[0]["text"] if rs else ""


def run(args) -> None:
    db = _db(args)
    cfg = llm.config_from_args(args)
    force = args.mock or not cfg.get("api_key")
    cmd = args.cmd

    if cmd == "resume":
        text = _read(args.file)
        if len(tools.normalize(text)) < 100:
            print("❌ 简历太短(少于 100 字),先补全经历再导入", file=sys.stderr)
            raise SystemExit(1)
        title = args.title or text.strip().splitlines()[0][:30]
        rid = db.add_resume(title, text)
        print(f"· 简历 [{rid}] {title}  {len(text)} 字")
    elif cmd == "resumes":
        rows = db.list_resumes()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for r in rows:
            print(f"[{r['id']}] {r['title']}  {len(r['text'])} 字  {r['created_at']}")
        if not rows:
            print("还没有简历。python -m mianshi resume resume.txt --title 我的简历")
    elif cmd == "show-resume":
        r = db.get_resume(args.key)
        if not r:
            print(f"❌ 找不到简历「{args.key}」", file=sys.stderr)
            raise SystemExit(1)
        print(f"[{r['id']}] {r['title']}  {r['created_at']}\n")
        print(r["text"])
    elif cmd == "rm-resume":
        print("· 已删" if db.delete_resume(args.key) else "❌ 没找到")
    elif cmd == "jd":
        jd = _read(args.file)
        if len(tools.normalize(jd)) < 60:
            print("❌ JD 太短(少于 60 字)", file=sys.stderr)
            raise SystemExit(1)
        resume = db.get_resume(args.resume) if args.resume else None
        jid = db.add_job(args.title, jd, args.company, int(resume["id"]) if resume else None)
        print(f"· 岗位 [{jid}] {args.company} {args.title}  {len(jd)} 字")
    elif cmd == "jobs":
        rows = db.list_jobs()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for row in rows:
            print(f"[{row['id']}] {row['company']} {row['title']}  JD {len(row['jd'])} 字")
    elif cmd == "show-job":
        job = _job_or_exit(db, args.key, args.json)
        print(f"[{job['id']}] {job['company']} {job['title']}  简历 #{job['resume_id']}\n")
        print(job["jd"])
    elif cmd == "analyze":
        job = _job_or_exit(db, args.job, args.json)
        resume = _resume_text(db, job)
        if not resume:
            print("❌ 还没有简历,先 import 一份", file=sys.stderr)
            raise SystemExit(1)
        result = agent.analyze(resume, job, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_analysis(result))
    elif cmd == "gen":
        job = _job_or_exit(db, args.job, args.json)
        resume = _resume_text(db, job)
        if not resume:
            print("❌ 还没有简历,先 import 一份", file=sys.stderr)
            raise SystemExit(1)
        n = max(1, min(8, args.n))
        result = agent.gen_questions(job, resume, n, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        db.clear_questions(int(job["id"]))
        for q in result["questions"]:
            qid = db.add_question(int(job["id"]), q["question"], q.get("why", ""))
            q["id"] = qid
        print(render_questions(result))
    elif cmd == "mock":
        job = _job_or_exit(db, args.job, args.json)
        rows = db.list_questions(int(job["id"]))
        if not rows:
            print("还没有题,先 python -m mianshi gen " + str(job["id"]))
            return
        for q in rows:
            print(f"[{q['id']}] {q['question']}")
            if q.get("why"):
                print(f"    意图:{q['why']}")
    elif cmd == "review":
        job = _job_or_exit(db, args.job, args.json)
        qrow = db.get_question(int(args.qid))
        if not qrow or int(qrow["job_id"]) != int(job["id"]):
            print(f"❌ 这个岗位下没有题号 {args.qid}", file=sys.stderr)
            raise SystemExit(1)
        answer = _read(args.answer).strip()
        if len(tools.normalize(answer)) < 30:
            print("❌ 回答太短(少于 30 字),先写完整再点评", file=sys.stderr)
            raise SystemExit(1)
        result = agent.review(job, _resume_text(db, job), qrow["question"], answer, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_review(result))
        rid = db.add_round(int(job["id"]), int(qrow["id"]), qrow["question"], answer,
                           render_review(result), int(result.get("score") or 0))
        print(f"\n· 已记一轮 #{rid}")
    elif cmd == "history":
        job = _job_or_exit(db, args.job, args.json)
        rows = db.list_rounds(int(job["id"]))
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for r in rows:
            print(f"#{r['id']} {r['created_at']}  {r['score']}/5  {tools.clamp(r['question'], 40)}")
        if not rows:
            print("还没有模拟记录。")
    elif cmd == "polish":
        r = db.get_resume(args.resume)
        if not r:
            print(f"❌ 找不到简历「{args.resume}」", file=sys.stderr)
            raise SystemExit(1)
        job = db.get_job(args.job) if args.job else None
        result = agent.polish(r["text"], job, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_polish(result))
        print("\n· 只是建议,原稿没有改动")
    elif cmd == "stats":
        print(json.dumps(db.stats(), ensure_ascii=False, indent=2))
    elif cmd == "web":
        from .web import serve
        serve(args.host, args.port, args.db, force, cfg)


def hoist_globals(argv: list[str]) -> list[str]:
    """把全局开关挪到子命令前,让 `mianshi analyze 1 --mock` 也能用。"""
    takes_value = {"--model", "--base-url", "--api-key", "--db"}
    flags = {"--mock", "--json"}
    head: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            head.append(a)
            i += 1
        elif a in takes_value and i + 1 < len(argv):
            head.extend(argv[i:i + 2])
            i += 2
        else:
            rest.append(a)
            i += 1
    return head + rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(hoist_globals(argv))
        run(args)
        return 0
    except llm.LLMError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    finally:
        _close_all()


if __name__ == "__main__":
    raise SystemExit(main())
