from fastapi.testclient import TestClient

from app.config import settings
from app.db import Paper, SessionLocal
from app.main import app


def _paper_id() -> str:
    with SessionLocal() as session:
        p = Paper(cache_key="auth-test", title="t", fulltext_status="ok", paragraphs=[], parser="test")
        session.add(p)
        session.commit()
        return p.id


def test_login_and_quota(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.check_executor, "submit", lambda *a, **k: None)
    monkeypatch.setattr(settings, "monthly_quota", 2)
    monkeypatch.setattr(settings, "auth_required", True)
    client = TestClient(app)

    assert client.post("/api/auth/request-code", json={"email": "a@gmail.com"}).status_code == 400
    r = client.post("/api/auth/request-code", json={"email": "Student.A@student.xjtlu.edu.cn"}).json()
    assert r["sent"] is False and len(r["dev_code"]) == 6
    assert client.post("/api/auth/request-code", json={"email": "student.a@student.xjtlu.edu.cn"}).status_code == 429

    bad = "000000" if r["dev_code"] != "000000" else "111111"
    assert client.post("/api/auth/verify", json={"email": "student.a@student.xjtlu.edu.cn", "code": bad}).status_code == 400
    login = client.post("/api/auth/verify", json={"email": "student.a@student.xjtlu.edu.cn", "code": r["dev_code"]}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    assert login["user"]["used"] == 0 and login["user"]["quota"] == 2

    pid = _paper_id()
    payload = {"text": "Whisper 的 WER 是 2.7%。", "paper_ids": [pid]}
    assert client.post("/api/checks", json=payload).status_code == 401  # 未登录
    assert client.post("/api/checks", json=payload, headers=headers).status_code == 200
    assert client.post("/api/checks", json=payload, headers=headers).status_code == 200
    assert client.post("/api/checks", json=payload, headers=headers).status_code == 429  # 本月用完
    assert client.get("/api/me", headers=headers).json()["used"] == 2
    assert len(client.get("/api/me/checks", headers=headers).json()) == 2

    client.post("/api/auth/logout", headers=headers)
    assert client.get("/api/me", headers=headers).status_code == 401


def test_errors_are_bilingual():
    client = TestClient(app)
    detail = client.post("/api/split", json={"text": "字" * 1501}).json()["detail"]
    assert "1500" in detail["zh"] and "characters" in detail["en"]
