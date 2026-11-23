"""طبقة الوصول إلى SQLite. اتصال جديد لكل عملية، مع تفعيل المفاتيح الأجنبية دائمًا."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.app.config import DB_PATH, ROOT


def connect(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    con = connect(path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def ensure_schema(path: Path | None = None) -> None:
    """ينشئ جداول التطبيق إن لم تكن موجودة. لا يلمس جداول الحزمة."""
    sql = (ROOT / "backend/database/schema_app.sql").read_text(encoding="utf-8")
    with session(path) as con:
        con.executescript(sql)


def rows(con: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(con: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_request_start(method: str, path: str, query: str) -> int:
    """يُسجَّل الطلب عند وصوله (status 0) ليُربط رقمه بالتوصيات والمحاكاة المحفوظة أثناء معالجته."""
    with session() as con:
        cur = con.execute("INSERT INTO app_requests(created_at,method,path,query,status_code,duration_ms,error) "
                          "VALUES (?,?,?,?,0,0,NULL)", (utcnow(), method, path, query))
        return int(cur.lastrowid)


def log_request_end(request_id: int, status: int, ms: float, error: str | None = None) -> None:
    with session() as con:
        con.execute("UPDATE app_requests SET status_code=?, duration_ms=?, error=? WHERE request_id=?",
                    (status, round(ms, 2), error, request_id))


def dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)
