"""原句核对：大模型给出的每一句“原文”，都要在论文里真的找得到，找不到就作废。"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from rapidfuzz import fuzz

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_DASHES)
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)  # 换行连字符
    text = re.sub(r"[|\s]+", " ", text)  # 表格分隔符和空白统一成一个空格
    return text.strip().lower()


def locate_quote(quote: Optional[str], paragraphs: list[dict], min_len: int = 6) -> Optional[dict]:
    """找到包含这句原文的段落；找不到返回 None。

    先做归一化后的精确匹配；不行再在段落里做高阈值的模糊匹配（容忍 PDF 解析造成的个别字符差异）。
    """
    q = normalize(quote or "")
    if len(q) < min_len:
        return None
    for p in paragraphs:
        if q in normalize(p["text"]):
            return p
    if len(q) < 20:
        return None
    best, best_score = None, 0.0
    for p in paragraphs:
        score = fuzz.partial_ratio(q, normalize(p["text"]))
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 95 else None


def window(text: str, start: int, end: int, radius: int = 70) -> str:
    """取 [start, end) 前后各约 radius 个字符，并对齐到空格，保证结果仍是原文的子串。"""
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    if lo > 0:
        space = text.find(" ", lo, start)
        lo = space + 1 if space != -1 else lo
    if hi < len(text):
        space = text.rfind(" ", end, hi)
        hi = space if space != -1 else hi
    return text[lo:hi].strip()


def shorten(text: str, needle: str, limit: int = 240) -> str:
    """太长的句子（PDF 解析出的整块表格）只保留 needle 附近的一段。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    at = text.lower().find(needle.lower())
    if at < 0:
        return text[:limit].rsplit(" ", 1)[0]
    return window(text, at, at + len(needle))


def sentence_containing(paragraph_text: str, needle: str) -> str:
    """从段落里取出包含 needle 的那句话（表格则取那一行），用作短句引文。"""
    lines = paragraph_text.split("\n")
    if len(lines) > 1:
        for line in lines:
            if needle.lower() in line.lower():
                return shorten(line, needle)
    parts = re.split(r"(?<=[.!?。])\s+", paragraph_text)
    for part in parts:
        if needle.lower() in part.lower():
            return shorten(part, needle)
    return shorten(paragraph_text, needle)
