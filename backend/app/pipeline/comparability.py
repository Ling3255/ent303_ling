"""第 6 步：判断是否可比（③）。逐字段对照两个结果的条件，按 rules/comparability.yaml 分级。不用大模型。"""
from __future__ import annotations

import re
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Optional

import yaml

from ..i18n import L
from .vocab import RULES_DIR, canonical

SEVERITY_ORDER = {"same": 0, "unknown": 1, "minor": 2, "major": 3}
LEVEL_LABELS = {
    "consistent": L("条件一致", "Conditions match"),
    "insufficient": L("原文未写明部分条件", "Some conditions not stated"),
    "minor": L("有差异但通常不影响", "Differs, usually minor"),
    "major": L("有差异且可能影响结论", "Differs, may affect the conclusion"),
    "na": L("不涉及比较", "No comparison"),
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


def _l(spec: dict, key: str) -> dict:
    """规则文件里的文字：key 是中文，key_en 是英文（没写英文就用中文）。"""
    return L(spec[key], spec.get(f"{key}_en") or spec[key])


def _page(cond: dict, field: str) -> Optional[int]:
    item = cond.get(field)
    return item.get("page") if isinstance(item, dict) else None


def _marker_category(marker: dict, text: str) -> Optional[str]:
    lowered = text.lower()
    for name, keywords in marker["categories"].items():
        if any(k.lower() in lowered for k in keywords):
            return name
    return None


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[一-鿿]", value.lower()))


def _compatible(ca: str, cb: str) -> bool:
    ta, tb = _tokens(ca), _tokens(cb)
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def _item_parts(cond: dict, field: str) -> tuple[str, str]:
    item = cond.get(field)
    if isinstance(item, dict):
        return item.get("value") or "", item.get("quote") or ""
    return item or "", ""


def _all_categories(marker: dict, text: str) -> set[str]:
    lowered = text.lower()
    return {name for name, kws in marker["categories"].items() if any(k.lower() in lowered for k in kws)}


def _side_category(marker: dict, cond: dict) -> Optional[str]:
    """这一方属于标记的哪一类。

    依次看：规则字段的值 → 规则字段的原句 → 其他字段的值 → 其他字段的原句。
    原句常常同时提到两边（"compares the zero-shot Whisper model with a supervised LibriSpeech model"），
    同一层同时命中两类时视为说不清，继续看下一层。
    """
    own = list(marker["fields"])
    others = [f for f in cond if f not in own]
    for fields, part in ((own, 0), (own, 1), (others, 0), (others, 1)):
        cats = _all_categories(marker, " ".join(_item_parts(cond, f)[part] for f in fields))
        if len(cats) == 1:
            return cats.pop()
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
            severity, reason = "unknown", L("至少一方原文没有写明这一项，无法确认是否一致。",
                                           "At least one paper does not state this, so it cannot be confirmed.")
        elif ca == cb:
            severity, reason = "same", L("两边一致。", "Same on both sides.")
        elif _compatible(ca, cb):
            # 例如 "clean" 和 "test-clean"：一方只是写得更简略，不能断定不同
            severity, reason = "unknown", L(f"两边写法不同（{va} / {vb}），可能是同一项，请核对原文。",
                                           f"Written differently ({va} / {vb}); possibly the same, please check the papers.")
        else:
            severity, reason = spec["differ"], _l(spec, "reason")
        fields_out.append({
            "field": field,
            "label": _l(spec, "label"),
            "a": va, "a_quote": _quote(a, field), "a_page": _page(a, field),
            "b": vb, "b_quote": _quote(b, field), "b_page": _page(b, field),
            "severity": severity,
            "reason": reason,
            "markers": [],
        })

    # 关键差异标记：在相关字段的值和原句里找关键词，两边落在不同类别时提级
    by_field = {f["field"]: f for f in fields_out}
    for marker in rules.get("markers") or []:
        cat_a, cat_b = _side_category(marker, a), _side_category(marker, b)
        if marker.get("flag_if_one_sided") and bool(cat_a) != bool(cat_b):
            # 一方明确是零样本 / oracle，另一方没写：不能当成一致，至少提示需要核对
            target = by_field[marker["fields"][0]]
            known = cat_a or cat_b
            not_stated = L("原文未写明", "not stated")
            reason = L(marker["one_sided_reason"].format(known=known),
                       marker.get("one_sided_reason_en", marker["one_sided_reason"]).format(known=known))
            target["markers"].append({"name": _l(marker, "name"), "a": cat_a or not_stated, "b": cat_b or not_stated,
                                      "reason": reason})
            if SEVERITY_ORDER[target["severity"]] < SEVERITY_ORDER["minor"]:
                target["severity"] = "minor"
                target["reason"] = reason
            continue
        if not (cat_a and cat_b and cat_a != cat_b):
            continue
        # 记在第一个命中关键词的字段上
        target = next((by_field[f] for f in marker["fields"]
                       if _marker_category(marker, _field_text(a, f) + " " + _field_text(b, f))), by_field[marker["fields"][0]])
        target["markers"].append({"name": _l(marker, "name"), "a": cat_a, "b": cat_b, "reason": _l(marker, "reason")})
        if target["severity"] in ("same", "unknown") or SEVERITY_ORDER[marker["severity"]] > SEVERITY_ORDER[target["severity"]]:
            target["severity"] = marker["severity"]
            target["reason"] = _l(marker, "reason")

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
