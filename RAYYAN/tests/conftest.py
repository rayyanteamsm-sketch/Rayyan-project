"""
إعداد الاختبارات: كل جلسة اختبار تعمل على نسخة مؤقتة من قاعدة البيانات حتى لا تلوث قاعدة التطوير،
ويُشغَّل خادم حقيقي (uvicorn) على منفذ حر لاختبارات التكامل والمتصفح.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.mkdtemp(prefix="rayyan_test_"))
TEST_DB = _tmp / "rayyan_test.sqlite"
shutil.copy2(ROOT / "data/database/rayyan.sqlite", TEST_DB)
os.environ["RAYYAN_DB"] = str(TEST_DB)  # يجب أن يسبق أي استيراد لـ backend


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    def __init__(self, base: str):
        self.base = base

    def request(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw), dict(r.headers)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw), dict(e.headers)
            except json.JSONDecodeError:
                return e.code, raw, dict(e.headers)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)


@pytest.fixture(scope="session")
def server():
    import uvicorn
    from backend.app.factory import create_app
    port = _free_port()
    cfg = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    assert srv.started, "الخادم لم يبدأ"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(timeout=10)


@pytest.fixture(scope="session")
def client(server):
    return Client(server)


@pytest.fixture()
def db():
    from backend.database.db import connect
    con = connect()
    yield con
    con.close()
