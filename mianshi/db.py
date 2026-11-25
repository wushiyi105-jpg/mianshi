"""SQLite 持久层:简历、岗位、题目、模拟轮次。

Web 端是多线程的,所有读写都走同一把锁;连接用 check_same_thread=False。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

DDL = """
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    jd TEXT NOT NULL,
    resume_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    why TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    feedback TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str = "data/mianshi.db"):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(DDL)
            self._conn.commit()

    # 简历 ----------------------------------------------------------------
    def add_resume(self, title: str, text: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO resumes (title, text, created_at) VALUES (?,?,?)",
                (title, text, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_resume(self, key) -> dict | None:
        with self._lock:
            if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                row = self._conn.execute("SELECT * FROM resumes WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM resumes WHERE title LIKE ? ORDER BY id DESC LIMIT 1", (f"%{key}%",)
                ).fetchone()
            return dict(row) if row else None

    def list_resumes(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM resumes ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def delete_resume(self, key) -> bool:
        with self._lock:
            # 锁内直接查,不能调 get_resume(它也会拿锁,普通 Lock 会死锁)
            if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                row = self._conn.execute("SELECT id FROM resumes WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT id FROM resumes WHERE title LIKE ? ORDER BY id DESC LIMIT 1", (f"%{key}%",)
                ).fetchone()
            if not row:
                return False
            self._conn.execute("DELETE FROM resumes WHERE id=?", (int(row["id"]),))
            self._conn.commit()
            return True

    # 岗位 ----------------------------------------------------------------
    def add_job(self, title: str, jd: str, company: str = "", resume_id: int | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO jobs (title, company, jd, resume_id, created_at) VALUES (?,?,?,?,?)",
                (title, company, jd, resume_id, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_job(self, key) -> dict | None:
        with self._lock:
            if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM jobs WHERE title LIKE ? OR company LIKE ? ORDER BY id DESC LIMIT 1",
                    (f"%{key}%", f"%{key}%"),
                ).fetchone()
            return dict(row) if row else None

    def list_jobs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def delete_job(self, key) -> bool:
        with self._lock:
            if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                row = self._conn.execute("SELECT id FROM jobs WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT id FROM jobs WHERE title LIKE ? OR company LIKE ? ORDER BY id DESC LIMIT 1",
                    (f"%{key}%", f"%{key}%"),
                ).fetchone()
            if not row:
                return False
            jid = int(row["id"])
            self._conn.execute("DELETE FROM rounds WHERE job_id=?", (jid,))
            self._conn.execute("DELETE FROM questions WHERE job_id=?", (jid,))
            self._conn.execute("DELETE FROM jobs WHERE id=?", (jid,))
            self._conn.commit()
            return True

    # 题目 ----------------------------------------------------------------
    def add_question(self, job_id: int, question: str, why: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO questions (job_id, question, why, created_at) VALUES (?,?,?,?)",
                (job_id, question, why, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_questions(self, job_id: int | None = None) -> list[dict]:
        with self._lock:
            if job_id:
                rows = self._conn.execute(
                    "SELECT * FROM questions WHERE job_id=? ORDER BY id", (job_id,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM questions ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_question(self, qid: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
            return dict(row) if row else None

    def clear_questions(self, job_id: int) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM questions WHERE job_id=?", (job_id,))
            self._conn.commit()
            return cur.rowcount

    # 模拟轮次 -------------------------------------------------------------
    def add_round(self, job_id: int, question_id: int, question: str, answer: str,
                  feedback: str = "", score: int = 0) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO rounds (job_id, question_id, question, answer, feedback, score, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (job_id, question_id, question, answer, feedback, score, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_rounds(self, job_id: int | None = None) -> list[dict]:
        with self._lock:
            if job_id:
                rows = self._conn.execute(
                    "SELECT * FROM rounds WHERE job_id=? ORDER BY id", (job_id,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM rounds ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    # 汇总 ----------------------------------------------------------------
    def stats(self) -> dict:
        with self._lock:
            c = self._conn
            return {
                "resumes": c.execute("SELECT COUNT(*) FROM resumes").fetchone()[0],
                "jobs": c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                "questions": c.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
                "rounds": c.execute("SELECT COUNT(*) FROM rounds").fetchone()[0],
            }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
