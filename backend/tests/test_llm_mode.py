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


# 按论文原文写的段落（第二次真实测试发现：正文从不点名 wav2vec 的训练方式）
REAL_REF = ("For a detailed breakdown of this large improvement in robustness, Table 2 compares the performance of the "
            "best zero-shot Whisper model with a supervised LibriSpeech model that has the closest performance to it "
            "on LibriSpeech test-clean.")
REAL_LIST = ("facebook/wav2vec2-large-960h-lv60-self (Xu et al., 2021)\nfacebook/wav2vec2-large-robust-ft-libri-960h\n"
             "facebook/wav2vec2-base-960h (Baevski et al., 2020)")


def _real_like_paper(whisper_paragraphs):
    table = next(p for p in whisper_paragraphs if p["kind"] == "table")
    filler = [{"id": f"f{i}", "kind": "text", "section": "", "page": 10 + i, "boxes": [],
               "text": f"Whisper results on LibriSpeech test-clean WER {i}.{i} are discussed in section {i}."}
              for i in range(1, 15)]
    ref = {"id": "ref", "kind": "text", "section": "3.3", "page": 6, "boxes": [], "text": REAL_REF}
    lst = {"id": "lst", "kind": "text", "section": "D.1", "page": 20, "boxes": [], "text": REAL_LIST}
    return Paper(cache_key="real-like", paragraphs=[table, *filler, ref, lst]), table


def test_condition_paragraphs_include_table_reference_and_model_list(whisper_paragraphs):
    paper, table = _real_like_paper(whisper_paragraphs)
    ids = {p["id"] for p in condition_paragraphs(paper, {"subject": "wav2vec 2.0"}, [table])}
    assert "ref" in ids  # 引用 Table 2 的正文段落，虽然没点名 wav2vec
    assert "lst" in ids  # 附录模型清单


def test_quote_mentioning_both_sides_uses_value():
    # 原句同时有 zero-shot 和 supervised LibriSpeech，以值为准
    out = compare_conditions(
        _c(environment=("zero-shot", "Whisper models are evaluated zero-shot")),
        _c(environment=("supervised on LibriSpeech (fine-tuned)", REAL_REF)),
    )
    env = {f["field"]: f for f in out["fields"]}["environment"]
    assert env["severity"] == "major" and env["markers"][0]["b"] == "fine-tuned"
    # 值本身说不清时，原句同时命中两类 → 不乱判，按“一方未写明”提示
    out = compare_conditions(_c(environment=("zero-shot", "evaluated zero-shot")),
                             _c(environment=("baseline", REAL_REF)))
    env = {f["field"]: f for f in out["fields"]}["environment"]
    assert env["severity"] in ("minor", "major") and env["markers"]
