"""第 4 步：查找原文段落。

- 向量检索：bge-m3（EMBEDDING_BACKEND=bge-m3，需安装 requirements-embed.txt），中英文跨语言都能检索；
- 关键词检索：BM25（默认），不需要下载模型，适合开发和测试；
- 含数字的论断，另外在表格和正文里按数字精确匹配，命中的段落排在前面。
"""
from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter, OrderedDict
from typing import Optional

from ..config import settings
from .sentences import numbers_in
from .vocab import find_terms

log = logging.getLogger(__name__)
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*|[一-鿿]")
_STOP = set("the a an of and or to in on for with by is are was were be this that we our as at from it its".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _number_pattern(num: str) -> re.Pattern:
    bare = num.rstrip("%")
    return re.compile(r"(?<![\w.])" + re.escape(bare) + r"(?![\w]|\.\d)")


def number_hits(paragraph: str, numbers: list[str]) -> list[str]:
    return [n for n in numbers if _number_pattern(n).search(paragraph)]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.tokens = [tokenize(d) for d in docs]
        self.k1, self.b = k1, b
        self.avgdl = sum(len(t) for t in self.tokens) / max(len(self.tokens), 1)
        df = Counter(term for toks in self.tokens for term in set(toks))
        n = len(self.tokens)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(t) for t in self.tokens]

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, toks in zip(self.tf, self.tokens):
            dl = len(toks) or 1
            s = 0.0
            for term in q:
                f = tf.get(term)
                if f:
                    s += self.idf[term] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


class _Embedder:
    """bge-m3 懒加载；同一篇论文的段落向量缓存在内存里。"""

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, object] = OrderedDict()

    def model(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                log.info("加载 bge-m3 …")
                self._model = SentenceTransformer("BAAI/bge-m3")
            return self._model

    def encode(self, texts: list[str]):
        return self.model().encode(texts, normalize_embeddings=True, batch_size=16)

    def paper_vectors(self, key: str, texts: list[str]):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        vecs = self.encode(texts)
        self._cache[key] = vecs
        if len(self._cache) > 50:
            self._cache.popitem(last=False)
        return vecs


_embedder = _Embedder()


def retrieve(paper_key: str, paragraphs: list[dict], query: str, numbers: Optional[list[str]] = None,
             top_k: Optional[int] = None) -> list[dict]:
    """返回最相关的段落（附 score、number_hits），数字命中的段落优先。"""
    if not paragraphs:
        return []
    top_k = top_k or settings.top_k_paragraphs
    numbers = numbers or []
    texts = [p["text"] for p in paragraphs]

    scores: list[float]
    if settings.embedding_backend == "bge-m3":
        try:
            vecs = _embedder.paper_vectors(paper_key, texts)
            qv = _embedder.encode([query])[0]
            scores = [float(v @ qv) for v in vecs]
        except Exception as exc:  # 模型缺失或显存不足时退回关键词检索
            log.warning("向量检索不可用，改用 BM25：%s", exc)
            scores = BM25(texts).scores(query)
    else:
        scores = BM25(texts).scores(query)

    # 关键词归一化到 0–1，便于和数字命中合并
    top = max(scores) if scores and max(scores) > 0 else 1.0
    terms = {m.canonical for m in find_terms(query)}
    ranked = []
    for p, s in zip(paragraphs, scores):
        hits = number_hits(p["text"], numbers)
        bonus = 0.0
        if hits:
            bonus += 0.6 * len(hits) / len(numbers)
            if p["kind"] == "table":
                bonus += 0.2
        if terms:
            para_terms = {m.canonical for m in find_terms(p["text"])}
            bonus += 0.2 * len(terms & para_terms) / len(terms)
        ranked.append({**p, "score": round(s / top + bonus, 4), "number_hits": hits})
    ranked.sort(key=lambda p: p["score"], reverse=True)
    return [p for p in ranked[:top_k] if p["score"] > 0]
