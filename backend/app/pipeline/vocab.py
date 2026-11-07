"""基准词表（rules/benchmarks.yaml）：把不同写法归一成同一个名字。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
_CJK = re.compile(r"[一-鿿]")


@dataclass(frozen=True)
class Term:
    kind: str  # dataset / split / metric
    canonical: str
    alias: str
    pattern: re.Pattern


@dataclass(frozen=True)
class Match:
    kind: str
    canonical: str
    start: int
    end: int
    text: str


def _compile(alias: str) -> re.Pattern:
    escaped = re.escape(alias.lower())
    if _CJK.search(alias):
        return re.compile(escaped)
    # 英文别名要求两侧不是字母数字，避免 "em" 匹配到 "system"
    left = r"(?<![a-z0-9])"
    right = "" if alias.endswith(("@", "-")) else r"(?![a-z0-9])"
    return re.compile(left + escaped + right)


@lru_cache(maxsize=1)
def load_vocab(path: Optional[str] = None) -> dict:
    data = yaml.safe_load(Path(path or RULES_DIR / "benchmarks.yaml").read_text(encoding="utf-8"))
    terms: list[Term] = []
    for name, spec in (data.get("datasets") or {}).items():
        for alias in {name, *spec.get("aliases", [])}:
            terms.append(Term("dataset", name, alias, _compile(alias)))
    for kind in ("splits", "metrics"):
        for name, aliases in (data.get(kind) or {}).items():
            for alias in {name, *aliases}:
                terms.append(Term(kind[:-1], name, alias, _compile(alias)))
    # 长的别名先匹配，"top-1 accuracy" 优先于 "top-1"，"test-clean" 优先于 "test"
    terms.sort(key=lambda t: len(t.alias), reverse=True)
    return {"raw": data, "terms": terms}


def find_terms(text: str, kinds: tuple[str, ...] = ("dataset", "split", "metric")) -> list[Match]:
    lowered = text.lower()
    # 每类分别记录已匹配的位置：同类里长别名优先，不同类可以重叠（"LibriSpeech Clean" 同时是数据集和划分）
    taken = {kind: [False] * len(lowered) for kind in kinds}
    found: list[Match] = []
    for term in load_vocab()["terms"]:
        if term.kind not in kinds:
            continue
        taken_kind = taken[term.kind]
        for m in term.pattern.finditer(lowered):
            if any(taken_kind[m.start() : m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken_kind[i] = True
            found.append(Match(term.kind, term.canonical, m.start(), m.end(), text[m.start() : m.end()]))
    found.sort(key=lambda m: m.start)
    return found


def canonical(value: Optional[str], kind: str) -> Optional[str]:
    """把一个字段值归一化；词表里没有就返回小写去空白后的原值。"""
    if not value:
        return None
    key = re.sub(r"\s+", " ", value.strip().lower())
    alias = ((load_vocab()["raw"].get("value_aliases") or {}).get(kind) or {}).get(key)
    if alias:
        return alias
    hits = sorted({m.canonical for m in find_terms(value, (kind,))})
    if hits:
        return " + ".join(hits)
    return re.sub(r"\s+", " ", value.strip().lower())


def dataset_domain(name: str) -> Optional[str]:
    spec = (load_vocab()["raw"].get("datasets") or {}).get(name)
    return spec.get("domain") if spec else None
