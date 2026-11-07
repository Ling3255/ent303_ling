"""第 2 步：核对来源（①）。用 Crossref、OpenAlex、arXiv、DBLP 判断论文是否存在、是否正式发表。不用大模型。"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import httpx
from rapidfuzz import fuzz

from ..config import settings
from ..i18n import L

log = logging.getLogger(__name__)

ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_OLD = re.compile(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?")
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

SOURCE_LABELS = {
    "published": L("存在", "Exists"),
    "preprint": L("预印本", "Preprint"),
    "not_found": L("找不到", "Not found"),
    "unknown": L("查询失败", "Lookup failed"),
}


@dataclass
class Metadata:
    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pdf_url: Optional[str] = None
    is_published: Optional[bool] = None
    found_in: str = ""


@dataclass
class SourceResult:
    status: str  # published / preprint / not_found / unknown
    metadata: Metadata
    checked: dict = field(default_factory=dict)  # 每个接口：found / not_found / error

    @property
    def label(self) -> dict:
        return SOURCE_LABELS[self.status]


def parse_identifier(raw: str) -> dict:
    """把用户填的字符串识别成 {'doi': ...} 或 {'arxiv_id': ...}；都不是返回 {'title': raw}。"""
    s = raw.strip()
    lowered = s.lower()
    m = re.search(r"10\.48550/arxiv\.(\S+)", lowered)
    if m:
        return {"arxiv_id": m.group(1)}
    if "arxiv" in lowered or ARXIV_NEW.fullmatch(s) or ARXIV_NEW.fullmatch(lowered.replace("arxiv:", "")):
        m = ARXIV_NEW.search(s) or ARXIV_OLD.search(s)
        if m:
            return {"arxiv_id": m.group(1)}
    m = DOI_RE.search(s)
    if m:
        return {"doi": m.group(1).rstrip(".,;)").lower()}
    return {"title": s}


def norm_title(t: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def titles_match(a: Optional[str], b: Optional[str], threshold: int = 90) -> bool:
    if not a or not b:
        return False
    return fuzz.token_sort_ratio(norm_title(a), norm_title(b)) >= threshold


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": f"CiteCheck/0.1 (mailto:{settings.contact_email})"},
    )


class _Offline(Exception):
    pass


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response:
    if not settings.network_enabled:
        raise _Offline()
    return client.get(url, **kw)


# ---------------- Crossref ----------------
_PREPRINT_TYPES = {"posted-content"}


def _crossref_meta(item: dict) -> Metadata:
    parts = (item.get("issued") or item.get("published") or {}).get("date-parts") or [[None]]
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in item.get("author", [])]
    venue = (item.get("container-title") or [None])[0]
    return Metadata(
        title=(item.get("title") or [None])[0],
        authors=[a for a in authors if a],
        year=parts[0][0] if parts and parts[0] else None,
        venue=venue,
        doi=(item.get("DOI") or "").lower() or None,
        is_published=item.get("type") not in _PREPRINT_TYPES,
        found_in="crossref",
    )


def crossref_by_doi(client: httpx.Client, doi: str) -> Optional[Metadata]:
    r = _get(client, f"https://api.crossref.org/works/{doi}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return _crossref_meta(r.json()["message"])


def crossref_by_title(client: httpx.Client, title: str) -> Optional[Metadata]:
    r = _get(client, "https://api.crossref.org/works", params={"query.bibliographic": title, "rows": 5})
    r.raise_for_status()
    best = None
    for item in r.json()["message"].get("items", []):
        meta = _crossref_meta(item)
        if titles_match(meta.title, title):
            # 同名的正式版优先于预印本
            if best is None or (meta.is_published and not best.is_published):
                best = meta
    return best


# ---------------- OpenAlex ----------------
def _openalex_meta(w: dict) -> Metadata:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    published = w.get("type") != "preprint" and src.get("type") in {"journal", "conference", "book series", "ebook platform"}
    for other in w.get("locations") or []:
        s = other.get("source") or {}
        if s.get("type") in {"journal", "conference"}:
            published = True
            src = src if src.get("type") in {"journal", "conference"} else s
    oa = w.get("best_oa_location") or {}
    ids = w.get("ids") or {}
    doi = (ids.get("doi") or w.get("doi") or "").replace("https://doi.org/", "").lower() or None
    return Metadata(
        title=w.get("title") or w.get("display_name"),
        authors=[a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
        year=w.get("publication_year"),
        venue=src.get("display_name"),
        doi=doi,
        pdf_url=oa.get("pdf_url"),
        is_published=published,
        found_in="openalex",
    )


def openalex_by_doi(client: httpx.Client, doi: str) -> Optional[Metadata]:
    r = _get(client, f"https://api.openalex.org/works/doi:{doi}", params={"mailto": settings.contact_email})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return _openalex_meta(r.json())


def openalex_by_title(client: httpx.Client, title: str) -> Optional[Metadata]:
    r = _get(client, "https://api.openalex.org/works",
             params={"search": title, "per-page": 5, "mailto": settings.contact_email})
    r.raise_for_status()
    best = None
    for w in r.json().get("results", []):
        meta = _openalex_meta(w)
        if titles_match(meta.title, title) and (best is None or (meta.is_published and not best.is_published)):
            best = meta
    return best


# ---------------- arXiv ----------------
def arxiv_by_id(client: httpx.Client, arxiv_id: str) -> Optional[Metadata]:
    r = _get(client, "https://export.arxiv.org/api/query", params={"id_list": arxiv_id, "max_results": 1})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    entry = root.find("a:entry", ATOM)
    if entry is None or entry.find("a:title", ATOM) is None:
        return None
    entry_id = entry.findtext("a:id", default="", namespaces=ATOM)
    if "api/errors" in entry_id:
        return None
    title = re.sub(r"\s+", " ", entry.findtext("a:title", default="", namespaces=ATOM)).strip()
    published = entry.findtext("a:published", default="", namespaces=ATOM)
    journal_ref = entry.findtext("arxiv:journal_ref", default=None, namespaces=ATOM)
    doi = entry.findtext("arxiv:doi", default=None, namespaces=ATOM)
    return Metadata(
        title=title,
        authors=[a.findtext("a:name", default="", namespaces=ATOM) for a in entry.findall("a:author", ATOM)],
        year=int(published[:4]) if published[:4].isdigit() else None,
        venue=journal_ref,
        doi=doi.lower() if doi else None,
        arxiv_id=arxiv_id,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        is_published=bool(journal_ref or doi),
        found_in="arxiv",
    )


# ---------------- DBLP（ICML、NeurIPS 等没有 DOI 的会议论文） ----------------
def dblp_by_title(client: httpx.Client, title: str) -> Optional[Metadata]:
    r = _get(client, "https://dblp.org/search/publ/api", params={"q": title, "format": "json", "h": 10})
    r.raise_for_status()
    hits = ((r.json().get("result") or {}).get("hits") or {}).get("hit") or []
    best = None
    for hit in hits:
        info = hit.get("info") or {}
        if not titles_match(info.get("title", "").rstrip("."), title):
            continue
        authors = (info.get("authors") or {}).get("author") or []
        if isinstance(authors, dict):
            authors = [authors]
        is_published = info.get("type") in {"Conference and Workshop Papers", "Journal Articles"} and info.get("venue") != "CoRR"
        meta = Metadata(
            title=info.get("title", "").rstrip("."),
            authors=[re.sub(r"\s\d{4}$", "", a.get("text", "")) for a in authors],
            year=int(info["year"]) if str(info.get("year", "")).isdigit() else None,
            venue=info.get("venue") if isinstance(info.get("venue"), str) else None,
            doi=(info.get("doi") or "").lower() or None,
            is_published=is_published,
            found_in="dblp",
        )
        if best is None or (meta.is_published and not best.is_published):
            best = meta
    return best


# ---------------- 汇总 ----------------
def check_source(*, doi: Optional[str] = None, arxiv_id: Optional[str] = None, title: Optional[str] = None) -> SourceResult:
    """按 DOI → arXiv → 标题的顺序查询，汇总出发表状态。

    - 任一接口确认有正式发表版本 → published
    - 只在 arXiv / 预印本平台找到 → preprint
    - 所有接口都正常返回但找不到 → not_found
    - 所有接口都出错（断网等）→ unknown
    """
    checked: dict[str, str] = {}
    found: list[Metadata] = []

    def attempt(name: str, fn, *args) -> Optional[Metadata]:
        try:
            meta = fn(*args)
        except (_Offline, httpx.HTTPError, ET.ParseError, ValueError, KeyError) as exc:
            log.info("%s 查询失败：%s", name, exc)
            checked[name] = "error"
            return None
        checked[name] = "found" if meta else "not_found"
        if meta:
            found.append(meta)
        return meta

    with _client() as client:
        if arxiv_id:
            attempt("arxiv", arxiv_by_id, client, arxiv_id)
        if doi:
            attempt("crossref", crossref_by_doi, client, doi)
            attempt("openalex", openalex_by_doi, client, doi)
        lookup_title = title or next((m.title for m in found if m.title), None)
        # 预印本可能已经在会议或期刊正式发表，用标题再查一次正式版本
        if lookup_title and not any(m.is_published for m in found):
            attempt("crossref_title", crossref_by_title, client, lookup_title)
            attempt("openalex_title", openalex_by_title, client, lookup_title)
        if lookup_title and not any(m.is_published for m in found):
            attempt("dblp", dblp_by_title, client, lookup_title)

    if not found:
        status = "unknown" if checked and all(v == "error" for v in checked.values()) else "not_found"
        if not checked:
            status = "unknown"
        return SourceResult(status, Metadata(title=title, doi=doi, arxiv_id=arxiv_id), checked)

    merged = _merge(found, doi=doi, arxiv_id=arxiv_id)
    status = "published" if merged.is_published else "preprint"
    return SourceResult(status, merged, checked)


def _merge(found: list[Metadata], *, doi: Optional[str], arxiv_id: Optional[str]) -> Metadata:
    # 标题、作者以第一个来源（用户给的标识对应的记录）为准，发表信息取正式版本
    base = found[0]
    published = next((m for m in found if m.is_published), None)
    merged = Metadata(
        title=base.title,
        authors=base.authors or next((m.authors for m in found if m.authors), []),
        year=(published or base).year or base.year,
        venue=(published.venue if published else None) or base.venue,
        doi=doi or next((m.doi for m in found if m.doi and "arxiv" not in m.doi), None),
        arxiv_id=arxiv_id or next((m.arxiv_id for m in found if m.arxiv_id), None),
        pdf_url=next((m.pdf_url for m in found if m.pdf_url), None),
        is_published=published is not None,
        found_in=",".join(dict.fromkeys(m.found_in for m in found)),
    )
    return merged


def unpaywall_pdf(doi: str) -> Optional[str]:
    try:
        with _client() as client:
            r = _get(client, f"https://api.unpaywall.org/v2/{doi}", params={"email": settings.contact_email})
            if r.status_code != 200:
                return None
            loc = r.json().get("best_oa_location") or {}
            return loc.get("url_for_pdf")
    except (_Offline, httpx.HTTPError, ValueError):
        return None
