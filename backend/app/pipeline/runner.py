"""把 7 步串起来：读取论文 → 核对来源 → 识别论断 → 查找段落 → 判断支持并抽条件 → 判断可比 → 生成报告。"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from sqlalchemy import select

from ..db import Check, ConditionCache, Paper, SessionLocal, utcnow
from . import comparability, support
from .claims import extract_claims
from .retrieval import retrieve
from ..i18n import L, loads
from .sources import SOURCE_LABELS

log = logging.getLogger(__name__)

STAGES = [
    ("reading", L("读取论文", "Reading papers")),
    ("retrieving", L("查找段落", "Finding passages")),
    ("extracting", L("抽取条件", "Extracting conditions")),
    ("comparing", L("判断差异", "Comparing conditions")),
]
DISCLAIMER = L("系统只提示差异，不判断观点对错，也不保证两个结果可以放心比较。请核对原文。",
               "CiteCheck only flags differences. It does not judge whether claims are right, and never guarantees two results are safe to compare. Please check the original papers.")
_VERDICT_RANK = {"supported": 3, "number_mismatch": 2, "contradicted": 1, "not_found": 0}
_COLOR_RANK = {"green": 0, "yellow": 1, "red": 2}


def _set_stage(check_id: str, stage: str, status: str = "running") -> None:
    with SessionLocal() as session:
        check = session.get(Check, check_id)
        check.stage = stage
        check.status = status
        session.commit()


def _wait_for_papers(paper_ids: list[str], timeout: float = 120) -> list[Paper]:
    deadline = time.time() + timeout
    while True:
        with SessionLocal() as session:
            papers = [session.get(Paper, pid) for pid in paper_ids]
        if all(p and p.fulltext_status != "processing" for p in papers) or time.time() > deadline:
            return [p for p in papers if p]
        time.sleep(1)


def paper_summary(p: Paper) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "authors": p.authors or [],
        "year": p.year,
        "venue": p.venue,
        "doi": p.doi,
        "arxiv_id": p.arxiv_id,
        "source": {"status": p.source_status, "label": SOURCE_LABELS.get(p.source_status, p.source_status),
                   "checked": (p.source_detail or {}).get("checked", {})},
        "fulltext_status": p.fulltext_status,
        "parser": p.parser,
        "warning": loads(p.parse_warning),
        "has_pdf": bool(p.pdf_path),
        "n_paragraphs": len(p.paragraphs or []),
    }


def run_check(check_id: str) -> None:
    started = time.time()
    try:
        _run(check_id, started)
    except Exception as exc:
        log.exception("检查 %s 失败", check_id)
        with SessionLocal() as session:
            check = session.get(Check, check_id)
            check.status = "failed"
            check.error = str(exc)
            check.finished_at = utcnow()
            session.commit()


def _run(check_id: str, started: float) -> None:
    with SessionLocal() as session:
        check = session.get(Check, check_id)
        sentences, paper_ids = check.sentences, check.paper_ids

    # 1–2. 读取论文、核对来源（论文入库时已在后台开始，这里等它完成）
    _set_stage(check_id, "reading")
    papers = _wait_for_papers(paper_ids)
    usable = [p for p in papers if p.fulltext_status == "ok" and p.paragraphs]
    paper_dicts = [{"id": p.id, "title": p.title, "authors": p.authors, "year": p.year,
                    "paragraphs": p.paragraphs} for p in usable]
    by_id = {p.id: p for p in papers}

    # 3. 识别论断
    _set_stage(check_id, "retrieving")
    selected = [s for s in sentences if s.get("selected")]
    claims_by_sentence, claim_engine = extract_claims(selected, paper_dicts) if paper_dicts else ({}, "none")

    # 4. 查找原文段落
    jobs = []  # (sentence_idx, claim_idx, claim, paper)
    for idx, info in claims_by_sentence.items():
        for ci, claim in enumerate(info["claims"]):
            claim["id"] = f"s{idx}c{ci}"
            for pid in claim["paper_ids"]:
                paper = by_id.get(pid)
                if paper and paper.paragraphs:
                    jobs.append((idx, ci, claim, paper))
    candidates = {}
    for idx, ci, claim, paper in jobs:
        found = retrieve(paper.cache_key, paper.paragraphs, claim["query"], claim.get("values"))
        candidates[(claim["id"], paper.id)] = found + condition_paragraphs(paper, claim, found)

    # 5. 判断是否支持并抽取条件（大模型调用并行）
    _set_stage(check_id, "extracting")
    engines: set[str] = set()

    def work(job) -> tuple[str, str, dict]:
        _, _, claim, paper = job
        # 段落编号取决于解析器，缓存键带上解析器
        key = f"{paper.cache_key}|{paper.parser}"
        cached = _cache_get(key, claim)
        if cached:
            engines.add(cached[1] + " (cached)")
            return claim["id"], paper.id, _rehydrate(cached[0], paper.paragraphs)
        result, engine = support.judge(claim, candidates[(claim["id"], paper.id)], paper.paragraphs)
        engines.add(engine)
        if engine.startswith("llm"):
            _cache_put(key, claim, engine, result)
        return claim["id"], paper.id, result

    judged: dict[tuple[str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for claim_id, pid, result in pool.map(work, jobs):
            judged[(claim_id, pid)] = result

    # 6. 判断是否可比
    _set_stage(check_id, "comparing")
    out_sentences = []
    for s in sentences:
        out_sentences.append(_sentence_report(s, claims_by_sentence.get(s["idx"]), judged, by_id))

    # 7. 生成报告
    colors = [s["color"] for s in out_sentences]
    duration = round(time.time() - started, 1)
    report = {
        "papers": [paper_summary(p) for p in papers],
        "sentences": out_sentences,
        "summary": {
            "green": colors.count("green"), "yellow": colors.count("yellow"), "red": colors.count("red"),
            "no_claim": colors.count("gray"), "unselected": colors.count("none"), "duration_s": duration,
        },
        "engine": {"claims": claim_engine, "support": sorted(engines) or ["none"]},
        "disclaimer": DISCLAIMER,
    }
    with SessionLocal() as session:
        check = session.get(Check, check_id)
        check.report = report
        check.status = "done"
        check.stage = "done"
        check.finished_at = utcnow()
        check.duration_s = duration
        session.commit()


# 讲训练 / 评测方式的段落里常见的词（子串匹配）
_CONDITION_TERMS = ("train", "fine-tun", "finetun", "supervis", "zero-shot", "labeled", "labelled", "hours", "960h",
                    "-ft-", "language model", "decod", "oracle", "retriev", "pre-train", "pretrain", "crop")


def condition_paragraphs(paper: Paper, claim: dict, found: list[dict], limit: int = 3) -> list[dict]:
    """再检索一次“这个模型是怎么训练/评测的”。按数字找到的往往是结果表格，训练方式写在别的段落里。"""
    seen = {p["id"] for p in found}
    extra = []

    # ① 正文里引用同一张表的段落：表格各列模型的设置通常写在这里，而且不一定点名
    #   （例如 "Table 2 compares ... with a supervised LibriSpeech model"）
    for label in _table_labels(found[:3]):
        pattern = re.compile(rf"\b{label}(?!\d)", re.I)
        for p in paper.paragraphs:
            if p["id"] not in seen and p["kind"] == "text" and pattern.search(p["text"]):
                extra.append(p)
                seen.add(p["id"])
                if len(extra) >= 2:
                    break

    # ② 提到这个模型、并且讲训练/评测方式的段落（包括附录里的模型清单，如 "wav2vec2-large-960h"）
    subject = (claim.get("subject") or "").strip()
    if subject:
        head = subject.split()[0].lower()
        scored = []
        for p in paper.paragraphs:
            text = p["text"].lower()
            if p["id"] in seen or head not in text:
                continue
            score = sum(term in text for term in _CONDITION_TERMS)
            if score:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        extra.extend(p for _, p in scored[:limit])
    return extra


def _table_labels(paragraphs: list[dict]) -> list[str]:
    labels = []
    for p in paragraphs:
        if p["kind"] != "table":
            continue
        m = re.search(r"\btable\s*(\d+)", f"{p.get('section') or ''} {p['text'][:200]}", re.I)
        if m and f"Table {m.group(1)}" not in labels:
            labels.append(f"Table {m.group(1)}")
    return [l.replace(" ", r"\s*") for l in labels]


def _sentence_report(s: dict, info: Optional[dict], judged: dict, by_id: dict) -> dict:
    base = {"idx": s["idx"], "text": s["text"], "start": s.get("start"), "end": s.get("end"),
            "selected": bool(s.get("selected"))}
    if not s.get("selected"):
        return {**base, "color": "none"}
    if not info or not info["claims"]:
        return {**base, "color": "gray", "note": L("这句话没有可以对照原文核对的论断。", "This sentence has no claim that can be checked against the papers.")}

    # ① 来源
    paper_ids = list(dict.fromkeys(pid for c in info["claims"] for pid in c["paper_ids"]))
    source_items = []
    for pid in paper_ids:
        p = by_id.get(pid)
        if p:
            source_items.append({"paper_id": pid, "title": p.title, "status": p.source_status,
                                 "label": SOURCE_LABELS.get(p.source_status, p.source_status)})
    source_color = max((_source_color(i["status"]) for i in source_items), key=_COLOR_RANK.get, default="yellow")

    # ② 支持：每条论断取各篇论文中最好的结论
    results = []
    for claim in info["claims"]:
        options = [(pid, judged[(claim["id"], pid)]) for pid in claim["paper_ids"] if (claim["id"], pid) in judged]
        if not options:
            results.append({"claim_id": claim["id"], "subject": claim.get("subject"), "statement": claim["statement"],
                            "values": claim.get("values"), "stated": claim.get("stated"), "paper_id": None,
                            "verdict": "not_found", "label": support.SUPPORT_LABELS["not_found"],
                            "explanation": L("对应的论文没有可读取的全文。", "No readable full text for the cited paper."), "evidence": [], "conditions": {},
                            "notes": [], "candidates": []})
            continue
        pid, best = max(options, key=lambda o: _VERDICT_RANK[o[1]["verdict"]])
        results.append({"claim_id": claim["id"], "subject": claim.get("subject"), "statement": claim["statement"],
                        "values": claim.get("values"), "stated": claim.get("stated"), "paper_id": pid, **best})
    support_color = max((_support_color(r["verdict"]) for r in results), key=_COLOR_RANK.get)
    worst = max(results, key=lambda r: _COLOR_RANK[_support_color(r["verdict"])])
    support_level = {"level": worst["verdict"], "label": worst["label"], "results": results}

    # ③ 可比：句子在比较两个及以上结果时才检查
    if info["is_comparison"]:
        compared = [{"claim_id": r["claim_id"], "subject": r["subject"], "paper_id": r["paper_id"],
                     "conditions": _merge_stated(r.get("conditions") or {}, r.get("stated") or {})} for r in results]
        comp = comparability.check_sentence(compared)
    else:
        comp = comparability.check_sentence([])
    comp_color = {"major": "red", "minor": "yellow", "insufficient": "yellow"}.get(comp["level"], "green")

    color = max([source_color, support_color, comp_color], key=_COLOR_RANK.get)
    return {**base, "color": color, "is_comparison": info["is_comparison"],
            "source": {"color": source_color, "items": source_items},
            "support": {**support_level, "color": support_color},
            "comparability": {**comp, "color": comp_color if comp["level"] != "na" else None}}


def _merge_stated(conditions: dict, stated: dict) -> dict:
    """原文没写明的字段，不拿用户句子里的说法来补（避免把“没写”当成“一致”）；只做展示用的补充。"""
    merged = {}
    for field, item in conditions.items():
        merged[field] = dict(item)
        if not item.get("value") and stated.get(field):
            merged[field]["stated_in_text"] = stated[field]
    return merged


def _source_color(status: str) -> str:
    return {"published": "green", "preprint": "yellow", "unknown": "yellow"}.get(status, "red")


def _support_color(verdict: str) -> str:
    return {"supported": "green", "not_found": "yellow"}.get(verdict, "red")


# ---------------- 条件缓存 ----------------
def _cache_get(paper_key: str, claim: dict) -> Optional[tuple[dict, str]]:
    with SessionLocal() as session:
        row = session.scalars(select(ConditionCache).where(
            ConditionCache.paper_key == paper_key, ConditionCache.claim_hash == support.claim_hash(claim))).first()
        return (row.result, row.engine) if row else None


def _cache_put(paper_key: str, claim: dict, engine: str, result: dict) -> None:
    # 缓存只存结论、条件和短句引文，不存段落全文
    result = {**result, "evidence": [{k: v for k, v in ev.items() if k not in ("text", "boxes")}
                                     for ev in result.get("evidence", [])]}
    with SessionLocal() as session:
        session.add(ConditionCache(paper_key=paper_key, claim_hash=support.claim_hash(claim), engine=engine, result=result))
        session.commit()


def _rehydrate(result: dict, paragraphs: list[dict]) -> dict:
    by_id = {p["id"]: p for p in paragraphs}
    evidence = []
    for ev in result.get("evidence", []):
        para = by_id.get(ev["paragraph_id"], {})
        evidence.append({**ev, "text": para.get("text", ev.get("quote", ""))[:1500], "boxes": para.get("boxes", [])})
    return {**result, "evidence": evidence}


def stage_list() -> list[dict]:
    return [{"key": k, "label": v} for k, v in STAGES]

