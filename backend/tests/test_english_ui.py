"""英文界面不能出现中文：系统生成的每段文字都要有不含中文的英文版。
用户自己的文字、论文标题、原文引文属于内容，不在检查范围内。"""
import copy
import json

from app import llm
from app.config import settings
from app.db import Check, Paper, SessionLocal
from app.i18n import has_cjk, loads
from app.pipeline.legacy import upgrade_report
from app.pipeline.runner import run_check

# 这些字段是用户输入或论文原文，不属于界面文字
CONTENT_KEYS = {"text", "statement", "subject", "quote", "title", "a", "b", "a_quote", "b_quote", "section",
                "values", "paper_value", "stated", "stated_in_text", "authors", "venue", "query", "value"}


def assert_no_chinese_in_english(node, path="report"):
    if isinstance(node, dict):
        if set(node) == {"zh", "en"}:
            assert not has_cjk(node["en"]), f"{path}.en 含中文：{node['en']}"
            return
        for k, v in node.items():
            if k in CONTENT_KEYS:
                continue
            assert_no_chinese_in_english(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            assert_no_chinese_in_english(v, f"{path}[{i}]")
    elif isinstance(node, str):
        assert not has_cjk(node), f"{path} 是纯中文、没有英文版：{node}"


def _run(paragraphs, text, sentence_flags=None):
    with SessionLocal() as session:
        paper = Paper(cache_key=f"en-ui-{len(text)}", title="Whisper", source_status="preprint", fulltext_status="ok",
                      paragraphs=paragraphs, parser="test")
        session.add(paper)
        session.flush()
        check = Check(text=text, paper_ids=[paper.id], sentences=[
            {"idx": 0, "text": text, "start": 0, "end": len(text), "selected": True, "has_number": True,
             "has_comparison": True, "has_citation": False, "suggested": True, **(sentence_flags or {})}])
        session.add(check)
        session.commit()
        check_id = check.id
    run_check(check_id)
    with SessionLocal() as session:
        return session.get(Check, check_id).report


def test_rule_mode_report_has_english_everywhere(whisper_paragraphs):
    report = _run(whisper_paragraphs, "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。")
    assert report["sentences"][0]["color"] == "red"
    assert_no_chinese_in_english(report)


def _to_old_format(node):
    """模拟加入双语之前的报告：所有 {zh, en} 都只剩中文。"""
    if isinstance(node, dict):
        if set(node) == {"zh", "en"}:
            return node["zh"]
        return {k: _to_old_format(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_to_old_format(v) for v in node]
    return node


def test_old_reports_are_upgraded(whisper_paragraphs):
    report = _run(whisper_paragraphs, "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。")
    old = _to_old_format(copy.deepcopy(report))
    old["papers"][0]["warning"] = "使用简易解析（未连接 GROBID），表格结构和段落边界可能不准确，也无法在 PDF 中高亮段落。"
    upgraded = upgrade_report(old)
    assert_no_chinese_in_english(upgraded)
    env = {f["field"]: f for f in upgraded["sentences"][0]["comparability"]["pairs"][0]["fields"]}["environment"]
    assert env["markers"][0]["name"]["en"] == "Training regime"
    assert "GROBID" in upgraded["papers"][0]["warning"]["en"]


def test_llm_missing_or_chinese_english_is_replaced(whisper_paragraphs, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def fake_chat_json(system, user, **kw):
        data = json.loads(user)
        if "sentences" in data:
            return {"sentences": [{"idx": 0, "is_comparison": False, "claims": [
                {"subject": "Whisper", "statement": "Whisper 的 WER 是 2.7%", "values": ["2.7%"],
                 "query": "Whisper WER 2.7", "papers": ["P1"]}]}]}
        row = "LibriSpeech Clean | 2.7 | 2.7 | 0.0"
        return {"verdict": "supported", "explanation": "表 2 中 Whisper 是 2.7。",
                "explanation_en": "表 2 中 Whisper 是 2.7。",  # 模型没按要求写英文
                "evidence": [{"paragraph_id": "p3", "quote": row}],
                "conditions": {"environment": {"value": "零样本", "quote": "Whisper models are evaluated zero-shot"}}}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    report = _run(whisper_paragraphs, "Whisper 的 WER 是 2.7%。", {"has_comparison": False})
    result = report["sentences"][0]["support"]["results"][0]
    assert result["explanation"]["en"] == "The paper states this claim, and the numbers match."
    # 中文的条件值换成论文原句里的英文
    assert result["conditions"]["environment"]["value"] == "Whisper models are evaluated zero-shot"
    assert_no_chinese_in_english(report)


def test_rule_without_english_falls_back_to_english():
    from app.pipeline.comparability import _l

    out = _l({"name": "新规则", "reason": "新规则的理由"}, "reason")
    assert out["zh"] == "新规则的理由" and not has_cjk(out["en"])


def test_legacy_paper_warning():
    out = loads("没有找到开放获取的全文，请上传 PDF。（download failed）")
    assert out["en"].startswith("No open-access full text")


def test_login_email_follows_language(monkeypatch):
    from app import auth

    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(auth.smtplib, "SMTP_SSL", FakeSMTP)
    auth._send_email("a@student.xjtlu.edu.cn", "123456", "en")
    auth._send_email("a@student.xjtlu.edu.cn", "123456", "zh")
    assert not has_cjk(sent[0]["Subject"]) and not has_cjk(sent[0].get_content())
    assert has_cjk(sent[1]["Subject"])
