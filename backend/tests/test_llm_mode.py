"""大模型模式（用假的 DeepSeek 回答）：复现第一次真实测试里 ③ 判错的情况。"""
import json

from app import llm
from app.config import settings
from app.db import Check, Paper, SessionLocal
from app.pipeline.comparability import compare_conditions
from app.pipeline.runner import condition_paragraphs, run_check


def _c(**fields):
    return {k: {"value": v, "quote": q} for k, (v, q) in fields.items()}


def test_split_shorthand_is_not_a_difference():
    out = compare_conditions(_c(split=("clean", "LibriSpeech Clean | 2.7 | 2.7")),
                             _c(split=("test-clean", "LibriSpeech test-clean")))
    assert {f["field"]: f["severity"] for f in out["fields"]}["split"] == "same"
    # 无法归一的简写：不能断定不同，标“原文未写明/请核对”而不是 major
    out = compare_conditions(_c(split=("test", "test")), _c(split=("test-clean", "test-clean")))
    assert {f["field"]: f["severity"] for f in out["fields"]}["split"] == "unknown"


def test_one_sided_zero_shot_is_flagged():
    out = compare_conditions(_c(environment=("zero-shot", "Whisper models are evaluated zero-shot")),
                             _c(baseline=("Large (no LM)", "wav2vec 2.0 Large (no LM)")))
    env = {f["field"]: f for f in out["fields"]}["environment"]
    assert env["severity"] == "minor" and env["markers"][0]["b"] == "原文未写明"


def test_training_regime_found_in_other_fields():
    # 训练方式写在 dataset 字段的原句里，也要识别出来
    out = compare_conditions(
        _c(environment=("zero-shot", "Whisper models are evaluated zero-shot")),
        _c(dataset=("LibriSpeech", "a supervised model fine-tuned on the 960 hours of labeled LibriSpeech training data")),
    )
    assert out["level"] == "major"


def test_condition_paragraphs_finds_training_setup(whisper_paragraphs):
    paper = Paper(cache_key="cond", paragraphs=whisper_paragraphs)
    table = [p for p in whisper_paragraphs if p["kind"] == "table"]
    extra = condition_paragraphs(paper, {"subject": "wav2vec 2.0"}, table)
    assert any("fine-tuned on the 960 hours" in p["text"] for p in extra)


def test_whisper_example_llm_mode(whisper_paragraphs, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    seen_paragraphs = {}

    def fake_chat_json(system, user, **kw):
        data = json.loads(user)
        if "sentences" in data:  # 第 3 步：识别论断
            return {"sentences": [{"idx": 0, "is_comparison": True, "claims": [
                {"subject": "Whisper large-v2", "statement": "Whisper 在 LibriSpeech 上 WER 2.7%", "values": ["2.7%"],
                 "query": "Whisper LibriSpeech WER 2.7", "papers": ["P1"], "stated": {"dataset": "LibriSpeech"}},
                {"subject": "wav2vec 2.0", "statement": "wav2vec 2.0 在 LibriSpeech 上 WER 2.7%", "values": ["2.7%"],
                 "query": "wav2vec 2.0 LibriSpeech WER 2.7", "papers": ["P1"], "stated": {"dataset": "LibriSpeech"}},
            ]}]}
        subject = data["claim"]["subject"]
        seen_paragraphs[subject] = [p["text"] for p in data["paragraphs"]]
        row = "LibriSpeech Clean | 2.7 | 2.7 | 0.0"
        if subject.startswith("Whisper"):
            env = {"value": "zero-shot", "quote": "Whisper models are evaluated zero-shot"}
            split = {"value": "clean", "quote": row}  # 第一次真实测试里出现过的简写
        else:
            env = {"value": "fine-tuned on 960h labeled LibriSpeech",
                   "quote": "a supervised model fine-tuned on the 960 hours of labeled LibriSpeech training data"}
            split = {"value": "test-clean", "quote": row}
        return {"verdict": "supported", "paper_value": "2.7", "explanation": "表 2 中两者都是 2.7",
                "evidence": [{"paragraph_id": "p3", "quote": row}],
                "conditions": {"dataset": {"value": "LibriSpeech", "quote": row}, "split": split,
                               "metric": {"value": "WER", "quote": "Results reported in word error rate (WER)"},
                               "baseline": {"value": "Large (no LM)" if "wav2vec" in subject else "Large V2",
                                            "quote": "Dataset | wav2vec 2.0 Large (no LM) | Whisper Large V2"},
                               "environment": env}}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    text = "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。"
    with SessionLocal() as session:
        paper = Paper(cache_key="llm-mode", title="Whisper", source_status="published", fulltext_status="ok",
                      paragraphs=whisper_paragraphs, parser="test")
        session.add(paper)
        session.flush()
        check = Check(text=text, paper_ids=[paper.id], sentences=[
            {"idx": 0, "text": text, "start": 0, "end": len(text), "selected": True, "has_number": True,
             "has_comparison": True, "has_citation": False, "suggested": True}])
        session.add(check)
        session.commit()
        check_id = check.id
    run_check(check_id)
    with SessionLocal() as session:
        report = session.get(Check, check_id).report

    # 训练方式所在的段落确实送给了大模型
    assert any("fine-tuned on the 960 hours" in t for t in seen_paragraphs["wav2vec 2.0"])
    sentence = report["sentences"][0]
    fields = {f["field"]: f for f in sentence["comparability"]["pairs"][0]["fields"]}
    assert fields["split"]["severity"] == "same"
    assert fields["environment"]["severity"] == "major"
    assert fields["environment"]["markers"][0]["name"] == "训练方式"
    assert {fields["environment"]["markers"][0]["a"], fields["environment"]["markers"][0]["b"]} == {"zero-shot", "fine-tuned"}
    assert sentence["color"] == "red"
