"""加入中英双语之前生成的报告：里面的标签、理由是纯中文。打开时按结果代码和规则文件补上英文，
保证英文界面看不到中文。用户自己的文字、论文标题和原文引文不翻译。"""
from __future__ import annotations

from typing import Any

from ..i18n import L, L_safe, has_cjk, legacy_text
from . import comparability as comp
from .runner import DISCLAIMER
from .sources import SOURCE_LABELS
from .support import SUPPORT_LABELS, VERDICT_EXPLANATION_EN

NO_CLAIM = L("这句话没有可以对照原文核对的论断。", "This sentence has no claim that can be checked against the papers.")
NOTE_EN = "Some quotes given by the model could not be verified in the paper and were removed."


def _old(value: Any) -> bool:
    return isinstance(value, str)


def upgrade_report(report: dict) -> dict:
    if not report:
        return report
    if _old(report.get("disclaimer")):
        report["disclaimer"] = DISCLAIMER
    for p in report.get("papers", []):
        src = p.get("source") or {}
        if _old(src.get("label")):
            src["label"] = SOURCE_LABELS.get(src.get("status"), SOURCE_LABELS["unknown"])
        if _old(p.get("warning")):
            p["warning"] = legacy_text(p["warning"])
    for s in report.get("sentences", []):
        _upgrade_sentence(s)
    return report


def _upgrade_sentence(s: dict) -> None:
    if _old(s.get("note")):
        s["note"] = NO_CLAIM
    for item in (s.get("source") or {}).get("items", []):
        if _old(item.get("label")):
            item["label"] = SOURCE_LABELS.get(item.get("status"), SOURCE_LABELS["unknown"])

    support = s.get("support") or {}
    if _old(support.get("label")):
        support["label"] = SUPPORT_LABELS.get(support.get("level"), SUPPORT_LABELS["not_found"])
    for r in support.get("results", []):
        verdict = r.get("verdict") if r.get("verdict") in SUPPORT_LABELS else "not_found"
        if _old(r.get("label")):
            r["label"] = SUPPORT_LABELS[verdict]
        if _old(r.get("explanation")):
            r["explanation"] = L_safe(r["explanation"], None if has_cjk(r["explanation"]) else r["explanation"],
                                      VERDICT_EXPLANATION_EN[verdict])
        r["notes"] = [L(n, NOTE_EN) if _old(n) else n for n in r.get("notes", [])]

    c = s.get("comparability") or {}
    if _old(c.get("label")):
        c["label"] = comp.LEVEL_LABELS.get(c.get("level"), comp.LEVEL_LABELS["na"])
    rules = comp.load_rules()
    markers_by_name = {m["name"]: m for m in rules.get("markers") or []}
    for pair in c.get("pairs", []):
        for f in pair.get("fields", []):
            spec = rules["fields"].get(f.get("field"))
            if _old(f.get("label")):
                f["label"] = comp._l(spec, "label") if spec else L_safe(f["label"], None, "Condition")
            for m in f.get("markers", []):
                rule = markers_by_name.get(m.get("name")) if _old(m.get("name")) else None
                if _old(m.get("name")):
                    m["name"] = comp._l(rule, "name") if rule else L_safe(m["name"], None, "Key difference")
                if _old(m.get("reason")):
                    if rule and m["reason"] == rule.get("reason"):
                        m["reason"] = comp._l(rule, "reason")
                    else:  # 一方未写明的提示，或规则已改过
                        m["reason"] = L_safe(m["reason"], None, comp._RULE_FALLBACK_EN["reason"])
                for side in ("a", "b"):
                    if _old(m.get(side)) and has_cjk(m[side]):
                        m[side] = comp.NOT_STATED
            if _old(f.get("reason")):
                if f.get("severity") == "same":
                    f["reason"] = comp.SAME_REASON
                elif f.get("severity") == "unknown" and f["reason"].startswith("至少一方"):
                    f["reason"] = comp.UNKNOWN_REASON
                elif f.get("markers"):
                    f["reason"] = f["markers"][0]["reason"]
                elif spec and f["reason"] == spec.get("reason"):
                    f["reason"] = comp._l(spec, "reason")
                else:
                    f["reason"] = L_safe(f["reason"], None, comp._RULE_FALLBACK_EN["reason"])
