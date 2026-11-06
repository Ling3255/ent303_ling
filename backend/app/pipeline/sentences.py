"""第 3 步前半：拆句，并标出含数字、比较或引用的句子（规则，不用大模型）。"""
from __future__ import annotations

import re

_ABBREVIATIONS = ("et al.", "e.g.", "i.e.", "fig.", "figs.", "eq.", "tab.", "sec.", "vs.", "cf.", "approx.", "no.", "ref.")

_NUMBER = re.compile(r"(?<![A-Za-z\-/_.\d])\d+(?:\.\d+)?(?:\s*%)?(?![A-Za-z\d]|\.\d)")
# 型号里的版本号不算数字，例如 "wav2vec 2.0"
_MODEL_TOKEN = re.compile(r"(?:[A-Za-z]+\d[\w-]*|[vV])\s$")
_COMPARISON = re.compile(
    r"(比|优于|高于|低于|超过|领先|落后|胜过|不如|差不多|相当|持平|接近|相同|一样|都是|都达到|提升|降低|下降|减少|"
    r"better|worse|outperform|surpass|exceed|higher|lower|than|compared|comparable|similar|same|match(?:es)?|"
    r"vs\.?|versus|improve|reduc|beat|state[- ]of[- ]the[- ]art|sota)",
    re.I,
)
_CITATION = re.compile(
    r"(论文|文章|研究|报告|表明|指出|提出|发现|显示|证明|据|"
    r"et al\.|\[\d+(?:[,\-–]\s*\d+)*\]|\(\w[^()]*\d{4}\w?\)|arxiv|paper|study|show(?:s|ed)?|report(?:s|ed)?|"
    r"propose[sd]?|demonstrate[sd]?|according to)",
    re.I,
)


def split_sentences(text: str) -> list[dict]:
    """返回 [{idx, text, start, end}]。中文按 。！？；切，英文按句点 + 空格切，不切小数和常见缩写。"""
    sentences: list[dict] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        cut = False
        if ch in "。！？；!?\n":
            cut = True
        elif ch == ".":
            nxt = text[i + 1] if i + 1 < n else ""
            prev = text[i - 1] if i > 0 else ""
            if prev.isdigit() and nxt.isdigit():
                cut = False  # 小数
            elif nxt == "" or nxt.isspace():
                tail = text[max(start, i - 8) : i + 1].lower()
                cut = not any(tail.endswith(a) for a in _ABBREVIATIONS)
        if cut:
            end = i + 1
            # 把紧跟的引号和括号并入本句
            while end < n and text[end] in "”’\"')）】":
                end += 1
            _push(sentences, text, start, end)
            start = end
            i = end
            continue
        i += 1
    _push(sentences, text, start, n)
    for idx, s in enumerate(sentences):
        s["idx"] = idx
    return sentences


def _push(out: list[dict], text: str, start: int, end: int) -> None:
    chunk = text[start:end]
    stripped = chunk.strip()
    if not stripped:
        return
    lead = len(chunk) - len(chunk.lstrip())
    s = start + lead
    out.append({"text": stripped, "start": s, "end": s + len(stripped)})


def numbers_in(text: str) -> list[str]:
    """抽取句子里的数字，统一成不带空格的写法（"2.7 %" → "2.7%"）。年份和引用编号不算。"""
    results = []
    for m in _NUMBER.finditer(text):
        token = re.sub(r"\s+", "", m.group())
        bare = token.rstrip("%")
        before = text[max(0, m.start() - 1) : m.start()]
        after = text[m.end() : m.end() + 1]
        if before == "[" or after == "]":
            continue  # [12]
        if "%" not in token and _MODEL_TOKEN.search(text[max(0, m.start() - 20) : m.start()]):
            continue
        if re.fullmatch(r"(19|20)\d{2}", bare) and "%" not in token:
            continue  # 年份
        results.append(token)
    return results


def flag_sentence(text: str) -> dict:
    has_number = bool(numbers_in(text))
    has_comparison = bool(_COMPARISON.search(text))
    has_citation = bool(_CITATION.search(text))
    return {
        "has_number": has_number,
        "has_comparison": has_comparison,
        "has_citation": has_citation,
        "suggested": has_number or has_comparison or has_citation,
    }


def split_and_flag(text: str) -> list[dict]:
    sentences = split_sentences(text)
    for s in sentences:
        s.update(flag_sentence(s["text"]))
    return sentences
