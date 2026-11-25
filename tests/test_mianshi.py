"""面试离线单测:不联网、不花 token。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mianshi import agent, cli, mock, tools, web
from mianshi.db import Database

ROOT = os.path.dirname(os.path.dirname(__file__))
RESUME = json.load(open(os.path.join(ROOT, "data", "resume-sample.json"), encoding="utf-8"))
JOBS = json.load(open(os.path.join(ROOT, "data", "job-sample.json"), encoding="utf-8"))


class TestTools(unittest.TestCase):
    def test_normalize_punct(self):
        self.assertEqual(tools.normalize("做 了，，问卷。。"), "做 了，问卷。")

    def test_skills(self):
        got = tools.skills("熟练使用 Excel 与 SQL,了解 RAG")
        self.assertIn("Excel", got)
        self.assertIn("RAG", got)

    def test_coverage_score_range(self):
        cov = tools.coverage(JOBS[0]["jd"], RESUME["text"])
        self.assertTrue(0 <= cov["score"] <= 100)
        self.assertIn("Excel", cov["matched"])
        self.assertIn("Figma", cov["missing"])

    def test_keywords_prefers_long(self):
        kws = tools.keywords("数据分析 指标体系 指标体系 指标体系")
        self.assertIn("指标体系", kws)

    def test_new_numbers(self):
        self.assertEqual(tools.new_numbers("写了 12 页", "写了 12 页,覆盖 268 人"), ["268"])

    def test_contains_quote(self):
        self.assertTrue(tools.contains_quote("写了 12 页需求文档", RESUME["text"]))
        self.assertFalse(tools.contains_quote("独立负责整条产品线", RESUME["text"]))

    def test_star_check(self):
        full = tools.star_check("当时在实习,我负责用户调研,我做了问卷,最终留存提升了 8%")
        self.assertGreaterEqual(full["count"], 3)
        self.assertFalse(tools.star_check("我觉得还行")["hits"]["result"])

    def test_vague(self):
        self.assertIn("差不多", tools.vague("大概差不多做完了"))

    def test_bullets(self):
        self.assertEqual(len(tools.bullets("- 写需求\n- 做调研")), 2)

    def test_match_line(self):
        cov = tools.coverage(JOBS[0]["jd"], RESUME["text"])
        self.assertIn("匹配度", tools.match_line(cov))


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        self.rid = self.db.add_resume(RESUME["title"], RESUME["text"])
        self.jid = self.db.add_job(JOBS[0]["title"], JOBS[0]["jd"], JOBS[0]["company"], self.rid)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class TestDb(BaseCase):
    def test_resume_crud(self):
        self.assertIsNotNone(self.db.get_resume("数据/产品"))
        self.assertTrue(self.db.delete_resume(self.rid))
        self.assertIsNone(self.db.get_resume(self.rid))

    def test_job_delete_cascades(self):
        self.db.add_question(self.jid, "请举例说明你用 Excel 做过什么")
        self.db.add_round(self.jid, 1, "q", "a")
        self.assertTrue(self.db.delete_job(self.jid))
        self.assertEqual(self.db.list_questions(), [])
        self.assertEqual(self.db.list_rounds(), [])

    def test_question_round(self):
        qid = self.db.add_question(self.jid, "问题", "意图")
        self.db.add_round(self.jid, qid, "问题", "回答", "点评", 4)
        self.assertEqual(self.db.list_rounds(self.jid)[0]["score"], 4)
        self.assertEqual(self.db.stats()["rounds"], 1)


class TestOffline(BaseCase):
    def test_mock_analyze(self):
        r = mock.analyze(RESUME["text"], JOBS[0]["jd"])
        self.assertTrue(r["offline"])
        self.assertTrue(r["advice"])
        self.assertIn("离线模式", r["note"])

    def test_mock_questions(self):
        qs = mock.questions(JOBS[0]["jd"], RESUME["text"], 5)
        self.assertEqual(len(qs), 5)
        self.assertTrue(all(len(q["question"]) < 100 for q in qs))

    def test_mock_review_score(self):
        r = mock.review("请介绍自己", "当时在实习,我负责调研,我做了问卷,最终留存提升 8%。")
        self.assertTrue(1 <= r["score"] <= 5)
        self.assertTrue(r["fix"])

    def test_agent_analyze_offline(self):
        r = agent.analyze(RESUME["text"], self.db.get_job(self.jid), {"api_key": ""}, True)
        self.assertEqual(r["score"], r["coverage"]["score"])
        self.assertIn("离线模式", r["note"])


class TestVerify(unittest.TestCase):
    def test_analysis_drops_ungrounded(self):
        body, problems = agent.verify_analysis(RESUME["text"], JOBS[0]["jd"], {
            "strengths": ["写了 12 页需求文档", "独立负责整条产品线"],
            "risks": ["缺少 Figma 经验"],
            "advice": ["把 3000 万用户写进简历", "补一条原型经历"],
        })
        self.assertEqual(body["strengths"], ["写了 12 页需求文档"])
        self.assertEqual(len(body["advice"]), 1)
        self.assertEqual(len(problems), 2)

    def test_questions_drop_offtopic(self):
        qs, problems = agent.verify_questions(JOBS[0]["jd"], RESUME["text"], {"questions": [
            {"question": "你最大的缺点是什么", "why": "通用题"},
            {"question": "请举例说明你用 Excel 做过什么分析", "why": "核实数据处理"},
            {"question": "请举例说明你用 Excel 做过什么分析", "why": "重复"},
        ]}, 5)
        self.assertEqual(len(qs), 1)
        self.assertTrue(problems)

    def test_review_grounding_and_numbers(self):
        answer = "当时在实习,我负责调研,我做了 268 份问卷调研,最终留存提升 8%"
        body, problems = agent.verify_review(answer, {
            "score": 9, "good": ["我做了 268 份问卷调研", "我独立完成了整个项目"],
            "fix": ["补上结果"], "rewrite": "把留存提升了 20%",
        })
        self.assertEqual(body["score"], 5)
        self.assertEqual(len(body["good"]), 1)
        self.assertEqual(body["rewrite"], "")
        self.assertTrue(problems)

    def test_polish_rejects_new_number(self):
        body, problems = agent.verify_polish(RESUME["text"], {"items": [
            {"orig": "累计 1200 名学生使用,留存 35%", "new": "累计 1200 名学生使用,留存 45%", "why": "改数字"},
            {"orig": "写了 12 页需求文档", "new": "写了 12 页需求文档,覆盖 3 个业务线", "why": "加事实"},
        ]})
        self.assertEqual(body["items"], [])
        self.assertEqual(len(problems), 2)


class TestCli(BaseCase):
    def _run(self, argv, db_path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", db_path] + argv)
        return buf.getvalue()

    def test_resume_jd_analyze_gen_review(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = os.path.join(tmp.name, "c.db")
        rf = os.path.join(tmp.name, "r.txt")
        jf = os.path.join(tmp.name, "j.txt")
        af = os.path.join(tmp.name, "a.txt")
        open(rf, "w", encoding="utf-8").write(RESUME["text"])
        open(jf, "w", encoding="utf-8").write(JOBS[0]["jd"])
        open(af, "w", encoding="utf-8").write("当时在实习,我负责用户调研,我做了 268 份问卷,最终输出 4 条结论并推动改版。")
        self.assertIn("[1]", self._run(["resume", rf, "--title", "我的简历"], db_path))
        self.assertIn("[1]", self._run(["jd", jf, "--title", "AI 产品经理", "--resume", "1"], db_path))
        out = self._run(["analyze", "1", "--mock"], db_path)
        self.assertIn("匹配度", out)
        self.assertIn("缺口", out)
        gen = self._run(["gen", "1", "--mock", "--n", "3"], db_path)
        self.assertIn("[1]", gen)
        review = self._run(["review", "1", "1", af, "--mock"], db_path)
        self.assertIn("STAR", review)
        self.assertIn("已记一轮", review)
        self.assertIn("#1", self._run(["history", "1"], db_path))
        tmp.cleanup()


class TestWeb(BaseCase):
    def test_api_flow(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(self.db, {"api_key": ""}, True))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urlopen(base + "/api/status", timeout=15) as resp:
                self.assertTrue(json.loads(resp.read().decode("utf-8"))["offline"])
            body = json.dumps({"title": "AI 产品经理", "jd": "太短", "resume": RESUME["text"]}).encode("utf-8")
            req = Request(base + "/api/analyze", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=15)
            self.assertEqual(ctx.exception.code, 400)
            body = json.dumps({"title": "AI 产品经理", "company": "某公司",
                               "jd": JOBS[0]["jd"], "resume": RESUME["text"]}).encode("utf-8")
            req = Request(base + "/api/analyze", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=20) as resp:
                r = json.loads(resp.read().decode("utf-8"))
            self.assertIn("匹配度", r["text"])
            gen = Request(base + "/api/gen", data=json.dumps({"job_id": r["job_id"]}).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(gen, timeout=20) as resp:
                g = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(g["questions"])
            rv = Request(base + "/api/review",
                         data=json.dumps({"job_id": r["job_id"], "question_id": g["questions"][0]["id"],
                                          "answer": "当时在实习,我负责调研,我做了 268 份问卷,最终留存提升 8%。"}).encode("utf-8"),
                         headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(rv, timeout=20) as resp:
                self.assertIn("STAR", json.loads(resp.read().decode("utf-8"))["text"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
