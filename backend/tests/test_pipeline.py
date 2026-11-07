"""端到端：用计划书里的 Whisper 例子，从建检查跑到出报告（规则模式，离线）。"""
from fastapi.testclient import TestClient

from app.db import Check, Paper, SessionLocal
from app.main import app
from app.pipeline.runner import run_check


def _add_whisper(paragraphs) -> str:
    with SessionLocal() as session:
        paper = Paper(cache_key="arxiv:2212.04356", arxiv_id="2212.04356",
                      title="Robust Speech Recognition via Large-Scale Weak Supervision",
                      authors=["Alec Radford", "Jong Wook Kim"], year=2023, venue="ICML",
                      source_status="published", fulltext_status="ok", paragraphs=paragraphs, parser="test")
        session.add(paper)
        session.commit()
        return paper.id


def test_whisper_example_end_to_end(whisper_paragraphs, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.check_executor, "submit", lambda *a, **k: None)  # 测试里同步运行
    pid = _add_whisper(whisper_paragraphs)
    client = TestClient(app)
    text = "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。这个结论很有意思。"

    split = client.post("/api/split", json={"text": text}).json()["sentences"]
    assert [s["suggested"] for s in split] == [True, False]

    r = client.post("/api/checks", json={"text": text, "paper_ids": [pid],
                                         "sentences": [{"idx": s["idx"], "selected": s["suggested"]} for s in split]})
    assert r.status_code == 200
    check_id = r.json()["id"]
    run_check(check_id)

    data = client.get(f"/api/checks/{check_id}").json()
    assert data["status"] == "done", data["error"]
    first, second = data["report"]["sentences"]
    assert second["color"] == "none"

    assert first["source"]["items"][0]["label"] == {"zh": "存在", "en": "Exists"}
    assert first["support"]["label"] == {"zh": "原文支持", "en": "Supported"}
    evidence = first["support"]["results"][0]["evidence"][0]
    assert evidence["page"] == 7 and "2.7" in evidence["quote"]

    comp = first["comparability"]
    assert comp["level"] == "major"
    env = {f["field"]: f for f in comp["pairs"][0]["fields"]}["environment"]
    assert env["markers"] and env["markers"][0]["name"]["en"] == "Training regime"
    assert first["color"] == "red"
    assert "请核对原文" in data["report"]["disclaimer"]["zh"]
    assert "check the original papers" in data["report"]["disclaimer"]["en"]

    fb = client.post(f"/api/checks/{check_id}/feedback",
                     json={"sentence_idx": 0, "layer": "comparability", "system_label": "major", "reason": "我觉得可以比"})
    assert fb.json()["ok"]


def test_number_mismatch(whisper_paragraphs):
    pid = _add_whisper(whisper_paragraphs)
    with SessionLocal() as session:
        text = "Whisper Large V2 在 Common Voice 上的 WER 是 5.1%。"
        check = Check(text=text, paper_ids=[pid], sentences=[
            {"idx": 0, "text": text, "start": 0, "end": len(text), "selected": True,
             "has_number": True, "has_comparison": False, "has_citation": False, "suggested": True}])
        session.add(check)
        session.commit()
        check_id = check.id
    run_check(check_id)
    with SessionLocal() as session:
        report = session.get(Check, check_id).report
    sentence = report["sentences"][0]
    assert sentence["support"]["label"]["en"] == "Number mismatch"
    assert sentence["color"] == "red"


def test_input_limits():
    client = TestClient(app)
    assert client.post("/api/split", json={"text": "字" * 1501}).status_code == 400
    assert client.post("/api/checks", json={"text": "abc", "paper_ids": []}).status_code == 400
