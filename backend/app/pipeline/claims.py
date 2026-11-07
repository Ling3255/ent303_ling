"""第 3 步后半：识别句子里可核对的论断，并对应到用户给的论文。

优先用大模型；没有配置或调用失败时用规则兜底（结果更粗，但流程能跑通）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .. import llm
from .sentences import numbers_in
from .vocab import find_terms

log = logging.getLogger(__name__)

FIELDS = ("dataset", "split", "metric", "baseline", "environment")

CLAIM_SYSTEM = """你是 CiteCheck 的论断识别模块，服务对象是 AI/ML 方向的研究生。
给你若干篇论文的元数据和一段文字中被选中的句子。对每个句子：
1. 找出可以拿原文核对的论断：具体数字、两个结果的比较、“某论文表明/提出”之类的说法。观点、建议、过渡句不算。
2. 一个论断只对应一个结果（一个模型/方法在一个设置下的一个数字或结论）。
   例如“A 和 B 在 X 上都是 2.7%”要拆成 A 的论断和 B 的论断两条。
3. 每条论断对应到给出的论文编号（P1…）。如果某个结果出现在某篇论文的对比表里（如作为基线），也对应到那篇论文。
   看不出对应哪篇时，列出所有可能的论文。
4. values 只能抄句子里出现过的数字，不要自己补。
5. stated 记录句子本身写明的条件（没写就填 null），不要从论文里补。
6. query 用英文写一句检索语句，包含模型名、数据集、指标和数字，用来在英文论文中查找段落。
7. is_comparison：句子是否把两个及以上的结果放在一起比较（包括“差不多”“都是”“优于”）。

只输出 JSON，格式：
{"sentences":[{"idx":0,"is_comparison":true,"claims":[
  {"subject":"Whisper large-v2","statement":"Whisper 在 LibriSpeech test-clean 上 WER 为 2.7%",
   "query":"Whisper large-v2 LibriSpeech test-clean WER 2.7","values":["2.7%"],
   "stated":{"dataset":"LibriSpeech","split":null,"metric":"WER","baseline":null,"environment":null},
   "papers":["P1"]}]}]}"""


def _paper_brief(papers: list[dict]) -> list[dict]:
    return [
        {"id": f"P{i + 1}", "title": p.get("title"), "authors": (p.get("authors") or [])[:3], "year": p.get("year")}
        for i, p in enumerate(papers)
    ]


def extract_claims(sentences: list[dict], papers: list[dict]) -> tuple[dict[int, dict], str]:
    """返回 ({sentence_idx: {"is_comparison": bool, "claims": [...]}}, engine)。

    papers: [{"id", "title", "authors", "year", "paragraphs"}]
    """
    if not sentences:
        return {}, "none"
    if llm.settings.llm_enabled:
        try:
            return _extract_llm(sentences, papers), "llm"
        except (llm.LLMError, ValueError, KeyError, TypeError) as exc:
            log.warning("大模型识别论断失败，改用规则：%s", exc)
    return {s["idx"]: _extract_rules(s, papers) for s in sentences}, "rules"


def _extract_llm(sentences: list[dict], papers: list[dict]) -> dict[int, dict]:
    user = json.dumps(
        {"papers": _paper_brief(papers), "sentences": [{"idx": s["idx"], "text": s["text"]} for s in sentences]},
        ensure_ascii=False,
    )
    data = llm.chat_json(CLAIM_SYSTEM, user, max_tokens=3000)
    id_map = {f"P{i + 1}": p["id"] for i, p in enumerate(papers)}
    by_idx = {s["idx"]: s for s in sentences}
    out: dict[int, dict] = {}
    for item in data.get("sentences", []):
        idx = item.get("idx")
        if idx not in by_idx:
            continue
        sentence_numbers = set(numbers_in(by_idx[idx]["text"]))
        claims = []
        for c in item.get("claims") or []:
            paper_ids = [id_map[p] for p in c.get("papers") or [] if p in id_map] or list(id_map.values())
            # 只保留句子里真实出现的数字，防止模型自己补数字
            values = [v for v in (c.get("values") or []) if _norm_num(v) in {_norm_num(n) for n in sentence_numbers}]
            stated = {f: (c.get("stated") or {}).get(f) for f in FIELDS}
            claims.append({
                "subject": (c.get("subject") or "").strip() or None,
                "statement": c.get("statement") or by_idx[idx]["text"],
                "query": c.get("query") or by_idx[idx]["text"],
                "values": values,
                "stated": stated,
                "paper_ids": paper_ids,
            })
        out[idx] = {"is_comparison": bool(item.get("is_comparison")) and len(claims) >= 2, "claims": claims}
    for idx, s in by_idx.items():
        out.setdefault(idx, _extract_rules(s, papers))
    return out


def _norm_num(v: str) -> str:
    return str(v).replace(" ", "").rstrip("%")


# ---------------- 规则兜底 ----------------
_NAME = re.compile(
    r"(?<![A-Za-z0-9\-])"
    r"([A-Za-z][A-Za-z0-9\-]*(?:[ ](?:\d+(?:\.\d+)?(?![\d%]|\.\d)|[Ll]arge|[Bb]ase|[Ss]mall|[Mm]edium|[Tt]iny)(?:-v\d)?)?)"
)
_NOT_NAMES = {
    "the", "a", "an", "and", "or", "on", "in", "of", "to", "is", "are", "was", "with", "than", "both", "we", "our",
    "this", "that", "it", "its", "as", "by", "for", "at", "but", "so", "while", "which", "model", "models", "paper",
    "results", "result", "accuracy", "error", "rate", "score", "also", "achieves", "achieve", "reaches", "gets",
    "about", "around", "same", "similar", "better", "worse", "compared", "comparable", "matching", "matches",
    "outperforms", "state", "art", "sota", "et", "al", "vs", "versus", "llm", "ai", "chatgpt", "kimi",
}


def find_subjects(text: str) -> list[str]:
    """找出句子里像模型/方法名的词（含大写字母或数字，且不是数据集、指标名）。"""
    vocab_spans = [(m.start, m.end) for m in find_terms(text)]
    names: list[str] = []
    for m in _NAME.finditer(text):
        name = m.group(1).strip()
        if name.lower() in _NOT_NAMES or len(name) < 2:
            continue
        if not (re.search(r"[A-Z]", name) or re.search(r"\d", name)):
            continue
        if any(s <= m.start(1) < e for s, e in vocab_spans):
            continue
        if re.fullmatch(r"[A-Z]{1,2}", name):
            continue
        if name not in names:
            names.append(name)
    return names


def _assign_papers(subject: Optional[str], papers: list[dict]) -> list[str]:
    if len(papers) <= 1 or not subject:
        return [p["id"] for p in papers]
    key = subject.split()[0].lower()
    scored = []
    for p in papers:
        title = (p.get("title") or "").lower()
        body = " ".join(x["text"] for x in (p.get("paragraphs") or [])[:40]).lower()
        scored.append((3 * title.count(key) + body.count(key), p["id"]))
    best = max(s for s, _ in scored)
    if best == 0:
        return [p["id"] for p in papers]
    return [pid for s, pid in scored if s == best]


def _extract_rules(sentence: dict, papers: list[dict]) -> dict:
    text = sentence["text"]
    values = numbers_in(text)
    terms = find_terms(text)
    stated = {f: None for f in FIELDS}
    for kind in ("dataset", "split", "metric"):
        hits = [t.canonical for t in terms if t.kind == kind]
        if hits:
            stated[kind] = hits[0]
    if not (values or sentence.get("has_comparison") or sentence.get("has_citation")):
        return {"is_comparison": False, "claims": []}

    subjects = find_subjects(text) or [None]
    is_comparison = bool(sentence.get("has_comparison")) and len(subjects) >= 2
    claims = []
    for i, subject in enumerate(subjects if is_comparison else subjects[:1]):
        # 两个名字两个数字时按顺序配对；只有一个数字（“都是 2.7%”）时两边共用
        if is_comparison and len(values) == len(subjects):
            vals = [values[i]]
        else:
            vals = values
        query_terms = [subject or "", *(t.text for t in terms), *(v.rstrip("%") for v in vals)]
        claims.append({
            "subject": subject,
            "statement": text,
            "query": " ".join(x for x in query_terms if x) or text,
            "values": vals,
            "stated": dict(stated),
            "paper_ids": _assign_papers(subject, papers),
        })
    return {"is_comparison": is_comparison, "claims": claims}
