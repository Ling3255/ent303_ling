"""第 6 步：判断是否可比（③）。逐字段对照两个结果的条件，按 rules/comparability.yaml 分级。不用大模型。"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Optional

import yaml

from .vocab import RULES_DIR, canonical

SEVERITY_ORDER = {"same": 0, "unknown": 1, "minor": 2, "major": 3}
LEVEL_LABELS = {
    "consistent": "条件一致",
    "insufficient": "原文未写明部分条件",
    "minor": "有差异但通常不影响",
    "major": "有差异且可能影响结论",
    "na": "不涉及比较",
}
_CANONICAL_KIND = {"dataset": "dataset", "split": "split", "metric": "metric"}


@lru_cache(maxsize=1)
def load_rules(path: Optional[str] = None) -> dict:
    return yaml.safe_load(Path(path or RULES_DIR / "comparability.yaml").read_text(encoding="utf-8"))


def reload_rules() -> None:
    load_rules.cache_clear()


def _value(cond: dict, field: str) -> Optional[str]:
    item = cond.get(field) or {}
    return item.get("value") if isinstance(item, dict) else item


def _field_text(cond: dict, field: str) -> str:
    item = cond.get(field)
    if isinstance(item, dict):
        return f"{item.get('value') or ''} {item.get('quote') or ''}".strip()
    return item or ""


def _quote(cond: dict, field: str) -> Optional[str]:
    item = cond.get(field)
    return item.get("quote") if isinstance(item, dict) else None


def _page(cond: dict, field: str) -> Optional[int]:
    item = cond.get(field)
    return item.get("page") if isinstance(item, dict) else None


def _marker_category(marker: dict, text: str) -> Optional[str]:
    lowered = text.lower()
    for name, keywords in marker["categories"].items():
        if any(k.lower() in lowered for k in keywords):
            return name
    return None


def compare_conditions(a: dict, b: dict) -> dict:
    """a、b 是两个结果的条件：{field: {"value", "quote", ...}}。返回逐字段结果和总等级。"""
    rules = load_rules()
    fields_out = []
    for field, spec in rules["fields"].items():
        va, vb = _value(a, field), _value(b, field)
        kind = _CANONICAL_KIND.get(field)
        ca = canonical(va, kind) if kind else (va or "").strip().lower() or None
        cb = canonical(vb, kind) if kind else (vb or "").strip().lower() or None
        if not ca or not cb:
            severity, reason = "unknown", "至少一方原文没有写明这一项，无法确认是否一致。"
        elif ca == cb:
            severity, reason = "same", "两边一致。"
        else:
            severity, reason = spec["differ"], spec["reason"]
        fields_out.append({
            "field": field,
            "label": spec["label"],
            "a": va, "a_quote": _quote(a, field), "a_page": _page(a, field),
            "b": vb, "b_quote": _quote(b, field), "b_page": _page(b, field),
            "severity": severity,
            "reason": reason,
            "markers": [],
        })

    # 关键差异标记：在相关字段的值和原句里找关键词，两边落在不同类别时提级
    by_field = {f["field"]: f for f in fields_out}
    for marker in rules.get("markers") or []:
        cat_a = _marker_category(marker, " ".join(_field_text(a, f) for f in marker["fields"]))
        cat_b = _marker_category(marker, " ".join(_field_text(b, f) for f in marker["fields"]))
        if not (cat_a and cat_b and cat_a != cat_b):
            continue
        # 记在第一个命中关键词的字段上
        target = next((by_field[f] for f in marker["fields"]
                       if _marker_category(marker, _field_text(a, f) + " " + _field_text(b, f))), by_field[marker["fields"][0]])
        target["markers"].append({"name": marker["name"], "a": cat_a, "b": cat_b, "reason": marker["reason"]})
        if target["severity"] in ("same", "unknown") or SEVERITY_ORDER[marker["severity"]] > SEVERITY_ORDER[target["severity"]]:
            target["severity"] = marker["severity"]
            target["reason"] = marker["reason"]

    return {"fields": fields_out, "level": overall_level(fields_out)}


def overall_level(fields_out: list[dict]) -> str:
    worst = max((SEVERITY_ORDER[f["severity"]] for f in fields_out), default=0)
    if worst == SEVERITY_ORDER["major"]:
        return "major"
    if worst == SEVERITY_ORDER["minor"]:
        return "minor"
    if worst == SEVERITY_ORDER["unknown"]:
        return "insufficient"
    return "consistent"


def check_sentence(results: list[dict]) -> dict:
    """results: 同一句里被比较的结果 [{claim_id, subject, paper_id, conditions}]。两两对照。"""
    pairs = []
    for ra, rb in combinations(results, 2):
        cmp = compare_conditions(ra["conditions"], rb["conditions"])
        pairs.append({
            "a": {"claim_id": ra["claim_id"], "subject": ra.get("subject"), "paper_id": ra.get("paper_id")},
            "b": {"claim_id": rb["claim_id"], "subject": rb.get("subject"), "paper_id": rb.get("paper_id")},
            **cmp,
        })
    if not pairs:
        return {"level": "na", "label": LEVEL_LABELS["na"], "pairs": []}
    level_rank = {"consistent": 0, "insufficient": 1, "minor": 2, "major": 3}
    level = max((p["level"] for p in pairs), key=level_rank.__getitem__)
    return {"level": level, "label": LEVEL_LABELS[level], "pairs": pairs}
