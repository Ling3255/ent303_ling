"""实验 2（条件抽取）和实验 3（来源匹配）的回归评测。

每次改提示词、规则或代码后跑一遍，正确率低于通过线时退出码为 1，CI 里就不能合并。

    python -m eval.run_eval extraction eval/data/extraction.jsonl --papers eval/data/papers
    python -m eval.run_eval sources eval/data/sources.jsonl

extraction.jsonl 每行一条人工标注（两人分别标注、讨论定稿后的结果）：
    {"id": "w1", "paper": "whisper.json", "claim": {"subject": "...", "statement": "...", "values": ["2.7%"]},
     "gold": {"verdict": "supported", "dataset": "LibriSpeech", "split": "test-clean", "metric": "WER",
              "baseline": null, "environment": "zero-shot"}}
  paper 指向 --papers 目录里的段落文件（GET /api/papers/{id} 之后从数据库导出的 paragraphs 列表）。

sources.jsonl 每行一条参考文献：
    {"id": "r1", "title": "...", "doi": "10....", "arxiv_id": null, "real": true}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.pipeline.claims import FIELDS
from app.pipeline.retrieval import retrieve
from app.pipeline.sources import check_source
from app.pipeline.support import judge
from app.pipeline.vocab import canonical

# 计划书里的通过线
EXTRACTION_FIELD_ACC = 0.85
EXTRACTION_FABRICATION = 0.05
SOURCES_MIN_FAKE_CAUGHT = 0.9   # 10 条编造的至少识别 9 条
SOURCES_MAX_REAL_WRONG = 0.05   # 40 条真实的误判不超过 2 条


def _same(field: str, pred, gold) -> bool:
    if not pred and not gold:
        return True
    if not pred or not gold:
        return False
    kind = field if field in ("dataset", "split", "metric") else None
    if kind:
        return canonical(pred, kind) == canonical(gold, kind)
    return str(pred).strip().lower() == str(gold).strip().lower()


def eval_extraction(path: Path, papers_dir: Path) -> bool:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    correct = total = fabricated = filled = verdict_ok = 0
    for row in rows:
        paragraphs = json.loads((papers_dir / row["paper"]).read_text(encoding="utf-8"))
        claim = {"query": row["claim"].get("query") or row["claim"]["statement"], **row["claim"]}
        candidates = retrieve(row["paper"], paragraphs, claim["query"], claim.get("values"))
        result, _ = judge(claim, candidates, paragraphs)
        gold = row["gold"]
        verdict_ok += result["verdict"] == gold.get("verdict")
        for field in FIELDS:
            pred = result["conditions"][field]["value"]
            total += 1
            correct += _same(field, pred, gold.get(field))
            if pred:
                filled += 1
                # 编造：标注里这一项为空（原文没写），系统却填了值
                fabricated += not gold.get(field)
    acc = correct / max(total, 1)
    fab = fabricated / max(filled, 1)
    print(f"条数 {len(rows)}  支持结论正确率 {verdict_ok / max(len(rows), 1):.1%}")
    print(f"字段正确率 {acc:.1%}（通过线 ≥ {EXTRACTION_FIELD_ACC:.0%}）  编造率 {fab:.1%}（通过线 < {EXTRACTION_FABRICATION:.0%}）")
    return acc >= EXTRACTION_FIELD_ACC and fab < EXTRACTION_FABRICATION


def eval_sources(path: Path) -> bool:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fake = [r for r in rows if not r["real"]]
    real = [r for r in rows if r["real"]]
    fake_caught = real_wrong = 0
    for r in rows:
        res = check_source(doi=r.get("doi"), arxiv_id=r.get("arxiv_id"), title=r.get("title"))
        flagged = res.status == "not_found"
        if r["real"] and flagged:
            real_wrong += 1
            print(f"  误判为找不到：{r['id']} {r.get('title')}")
        if not r["real"]:
            fake_caught += flagged
            if not flagged:
                print(f"  漏掉编造：{r['id']} {r.get('title')} → {res.status}")
    caught = fake_caught / max(len(fake), 1)
    wrong = real_wrong / max(len(real), 1)
    print(f"编造识别 {fake_caught}/{len(fake)}  真实误判 {real_wrong}/{len(real)}")
    return caught >= SOURCES_MIN_FAKE_CAUGHT and wrong <= SOURCES_MAX_REAL_WRONG


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=["extraction", "sources"])
    ap.add_argument("data", type=Path)
    ap.add_argument("--papers", type=Path, default=Path("eval/data/papers"))
    args = ap.parse_args()
    ok = eval_extraction(args.data, args.papers) if args.task == "extraction" else eval_sources(args.data)
    print("通过" if ok else "未通过")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
