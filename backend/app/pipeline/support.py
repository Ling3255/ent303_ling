"""第 5 步：判断是否支持（②）并抽取条件。

大模型按固定 JSON 输出支持结论和五个条件字段，每个字段必须附原文原句；
程序逐句核对原句是否真的出现在论文里，找不到就把该字段置空。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Optional

from .. import llm
from ..config import settings
from .claims import FIELDS
from .comparability import load_rules
from .evidence import locate_quote, normalize, sentence_containing, shorten
from .retrieval import number_hits
from .vocab import find_terms

log = logging.getLogger(__name__)

SUPPORT_LABELS = {
    "supported": "原文支持",
    "not_found": "原文没有",
    "contradicted": "说法相反",
    "number_mismatch": "数字不一致",
}
PROMPT_VERSION = "v2"  # 改提示词时加一，旧的条件缓存自动失效

SUPPORT_SYSTEM = """你是 CiteCheck 的原文核对模块。给你一条论断和同一篇论文中检索出的候选段落（含表格）。
任务一：判断论文是否支持这条论断。
- supported：候选段落明确写了这个说法，数字（如有）一致。
- number_mismatch：论文报告了同一个结果，但数字不同。
- contradicted：论文的说法和论断相反。
- not_found：候选段落里没有这个说法。拿不准时选 not_found。
任务二：抽取论文中“这个结果”的测试条件，五个字段：
- dataset 数据集（如 LibriSpeech、ImageNet-1k、Natural Questions）
- split 数据划分，用规范写法（如 test-clean、test-other、val、dev）。表格里的 "LibriSpeech Clean" 指 test-clean，"LibriSpeech Other" 指 test-other
- metric 指标（如 WER、top-1 accuracy、Exact Match）
- baseline 模型配置：模型规模/版本，以及解码时是否用外部语言模型（如 "Large (no LM)"、"large-v2"）
- environment 训练与评测方式。先写训练方式：zero-shot（没在该数据集的训练集上训练）、fine-tuned on X / trained on X（在该数据集训练集上有监督训练或微调）；
  再写其他评测设置（是否给 oracle 段落、测试时增强、硬件）。是否用语言模型写在 baseline，不要写在这里
特别注意：结果如果属于对比表里的另一个模型（基线），要在候选段落里找这个模型本身的训练方式
（例如“a supervised LibriSpeech model”“fine-tuned on 960 hours of labeled LibriSpeech”），而不是照抄论文主模型的设置。
规则：
- 每个字段的 quote 必须从候选段落中逐字复制（英文原文，不要翻译、不要改写、不要拼接）。
- 找不到原句支持的字段，value 和 quote 都填 null。绝对不要凭常识补。
- evidence 列出支撑结论的段落编号和逐字原句，最多 3 条。
- explanation 用中文一句话说明判断理由。
只输出 JSON：
{"verdict":"supported","paper_value":"2.7","explanation":"……",
 "evidence":[{"paragraph_id":"p12","quote":"……"}],
 "conditions":{"dataset":{"value":"LibriSpeech","quote":"……"},"split":{"value":null,"quote":null},
   "metric":{"value":"WER","quote":"……"},"baseline":{"value":null,"quote":null},"environment":{"value":"zero-shot","quote":"……"}}}"""


def claim_hash(claim: dict) -> str:
    key = json.dumps([PROMPT_VERSION, claim.get("subject"), claim.get("statement"), claim.get("values")],
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


def judge(claim: dict, candidates: list[dict], all_paragraphs: list[dict]) -> tuple[dict, str]:
    """返回 (结果, engine)。结果字段：verdict, label, explanation, paper_value, evidence, conditions。"""
    if not candidates:
        return _finalize({"verdict": "not_found", "explanation": "论文中没有检索到相关段落。"}, [], all_paragraphs), "rules"
    if settings.llm_enabled:
        try:
            raw = _judge_llm(claim, candidates)
            return _finalize(raw, candidates, all_paragraphs), f"llm:{settings.llm_model}"
        except (llm.LLMError, ValueError, KeyError, TypeError) as exc:
            log.warning("大模型核对失败，改用规则：%s", exc)
    return _finalize(_judge_rules(claim, candidates, all_paragraphs), candidates, all_paragraphs), "rules"


def _judge_llm(claim: dict, candidates: list[dict]) -> dict:
    user = json.dumps({
        "claim": {"subject": claim.get("subject"), "statement": claim.get("statement"), "values": claim.get("values")},
        "paragraphs": [{"id": p["id"], "page": p.get("page"), "kind": p["kind"], "section": p.get("section"),
                        "text": p["text"][:2000]} for p in candidates],
    }, ensure_ascii=False)
    return llm.chat_json(SUPPORT_SYSTEM, user, max_tokens=1500)


def _finalize(raw: dict, candidates: list[dict], all_paragraphs: list[dict]) -> dict:
    """统一格式，并核对每一句原文是否真的在论文里。"""
    verdict = raw.get("verdict")
    if verdict not in SUPPORT_LABELS:
        verdict = "not_found"
    candidate_ids = {p["id"] for p in candidates}
    pool = candidates + [p for p in all_paragraphs if p["id"] not in candidate_ids]
    notes: list[str] = []

    evidence = []
    for ev in (raw.get("evidence") or [])[:3]:
        para = locate_quote(ev.get("quote"), pool)
        if para:
            evidence.append(_evidence(para, ev["quote"]))
        else:
            notes.append("有一条模型给出的原句在论文中找不到，已丢弃。")
    if verdict != "not_found" and not evidence:
        notes.append("没有能在论文中核实的原句，结论改为“原文没有”。")
        verdict = "not_found"

    conditions = {}
    dropped = []
    for field in FIELDS:
        item = (raw.get("conditions") or {}).get(field) or {}
        value, quote = item.get("value"), item.get("quote")
        para = locate_quote(quote, pool) if value and quote else None
        if value and not para:
            dropped.append(field)
        conditions[field] = (
            {"value": str(value), "quote": quote, "paragraph_id": para["id"], "page": para.get("page")}
            if para else {"value": None, "quote": None, "paragraph_id": None, "page": None}
        )
    if dropped:
        notes.append(f"{len(dropped)} 个条件字段的原句无法在论文中找到，已置空。")

    return {
        "verdict": verdict,
        "label": SUPPORT_LABELS[verdict],
        "explanation": raw.get("explanation") or "",
        "paper_value": raw.get("paper_value"),
        "evidence": evidence,
        "conditions": conditions,
        "notes": notes,
        "candidates": [{"paragraph_id": p["id"], "page": p.get("page"), "score": p.get("score")} for p in candidates],
    }


def _evidence(para: dict, quote: str) -> dict:
    return {
        "paragraph_id": para["id"],
        "page": para.get("page"),
        "kind": para["kind"],
        "section": para.get("section"),
        "quote": quote,
        "text": para["text"][:1500],
        "boxes": para.get("boxes") or [],
    }


# ---------------- 规则兜底（没有大模型时） ----------------
def _rows(p: dict) -> list[str]:
    return [r for r in p["text"].split("\n") if r.strip()] if p["kind"] == "table" else re.split(r"(?<=[.!?])\s+", p["text"])


def _mentions(text: str, subject: Optional[str]) -> bool:
    if not subject:
        return True
    head = subject.split()[0].lower()
    return head in text.lower()


def _judge_rules(claim: dict, candidates: list[dict], all_paragraphs: list[dict]) -> dict:
    values = claim.get("values") or []
    subject = claim.get("subject")
    if not values:
        return {"verdict": "not_found",
                "explanation": "未配置大模型，规则模式只能核对含数字的论断；请人工查看下方候选段落。"}

    for p in candidates:
        if len(number_hits(p["text"], values)) == len(values) and _mentions(p["text"], subject):
            # 取包含数字的那一行 / 那句话作为原句
            line = next((r for r in _rows(p) if number_hits(r, values)), p["text"])
            line = shorten(line, values[0].rstrip("%"))
            return {
                "verdict": "supported",
                "paper_value": values[0].rstrip("%"),
                "explanation": f"在第 {p.get('page') or '?'} 页找到包含数字 {', '.join(values)} 的原文（规则匹配，未经大模型确认）。",
                "evidence": [{"paragraph_id": p["id"], "quote": line.strip()}],
                "conditions": _conditions_rules(p, line, subject, all_paragraphs),
            }

    # 同一行提到了这个模型和同一个数据集 / 指标，但数字不同 → 数字不一致
    claim_terms = {m.canonical for m in find_terms(claim.get("statement") or "")}
    for p in candidates:
        if p["kind"] != "table":
            continue
        for row in _rows(p):
            if subject and _mentions(row, subject) and re.search(r"\d", row):
                row_terms = {m.canonical for m in find_terms(row + " " + p["text"].split("\n")[0])}
                if claim_terms & row_terms:
                    return {
                        "verdict": "number_mismatch",
                        "explanation": "表格中这个模型的结果与文字中的数字不同（规则匹配，请核对）。",
                        "evidence": [{"paragraph_id": p["id"], "quote": shorten(row, subject.split()[0])}],
                        "conditions": _conditions_rules(p, row, subject, all_paragraphs),
                    }
    return {"verdict": "not_found", "explanation": "候选段落中没有找到文字里的数字。"}


def _conditions_rules(para: dict, line: str, subject: Optional[str], all_paragraphs: list[dict]) -> dict:
    """用词表和规则文件里的关键词抽条件；每个字段都带原句。"""
    conditions: dict = {}
    caption = para["text"].split("\n")[0] if para["kind"] == "table" else ""
    for field in ("dataset", "split", "metric"):
        for source in (line, caption, para["text"]):
            hits = [m for m in find_terms(source, (field,))]
            if hits:
                conditions[field] = {"value": hits[0].canonical, "quote": sentence_containing(source, hits[0].text)}
                break

    # baseline / environment：在提到这个模型的句子里找规则文件中的关键词
    sentences = []
    for p in [para] + all_paragraphs:
        for s in _rows(p):
            if _mentions(s, subject):
                sentences.append(s)
        if len(sentences) > 200:
            break
    for marker in load_rules().get("markers") or []:
        field = next((f for f in marker["fields"] if f in ("environment", "baseline") and f not in conditions), None)
        if not field:
            continue
        for s in sentences:
            low = normalize(s)
            hit = next((k for ks in marker["categories"].values() for k in ks if k.lower() in low), None)
            if hit:
                conditions[field] = {"value": hit, "quote": shorten(s, hit)}
                break
    return conditions
