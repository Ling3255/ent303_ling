"""第 1 步：读取论文。找开放全文 → GROBID 解析成带页码和坐标的段落；没有 GROBID 时退回 pypdf 按页抽文字。"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from .sources import ARXIV_NEW, DOI_RE, _client, unpaywall_pdf

log = logging.getLogger(__name__)
TEI = {"t": "http://www.tei-c.org/ns/1.0"}


class FullTextUnavailable(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_pdf(data: bytes) -> Path:
    path = settings.upload_dir / f"{sha256(data)}.pdf"
    if not path.exists():
        path.write_bytes(data)
    return path


def download_pdf(url: str) -> bytes:
    if not settings.network_enabled:
        raise FullTextUnavailable("网络已关闭")
    try:
        with _client() as client:
            r = client.get(url, timeout=60)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise FullTextUnavailable(f"下载失败：{exc}") from exc
    if not r.content.startswith(b"%PDF"):
        raise FullTextUnavailable("链接返回的不是 PDF")
    return r.content


def find_open_fulltext(*, doi: Optional[str], arxiv_id: Optional[str], pdf_url: Optional[str]) -> bytes:
    """按 arXiv → OpenAlex 给的开放链接 → Unpaywall 的顺序找全文。"""
    candidates = []
    if arxiv_id:
        candidates.append(f"https://arxiv.org/pdf/{arxiv_id}")
    if pdf_url:
        candidates.append(pdf_url)
    if doi:
        oa = unpaywall_pdf(doi)
        if oa:
            candidates.append(oa)
    errors = []
    for url in dict.fromkeys(candidates):
        try:
            return download_pdf(url)
        except FullTextUnavailable as exc:
            errors.append(str(exc))
    raise FullTextUnavailable("；".join(errors) or "没有找到开放获取的全文")


# ---------------- 解析 ----------------
def _clean(text: str) -> str:
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # 行尾连字符
    return re.sub(r"\s+", " ", text).strip()


def _boxes(coords: Optional[str]) -> list[dict]:
    boxes = []
    for part in (coords or "").split(";"):
        bits = part.split(",")
        if len(bits) >= 5:
            try:
                page, x, y, w, h = int(float(bits[0])), *(float(b) for b in bits[1:5])
            except ValueError:
                continue
            boxes.append({"page": page, "x": x, "y": y, "w": w, "h": h})
    return boxes


def _first_page(boxes: list[dict]) -> Optional[int]:
    return boxes[0]["page"] if boxes else None


def _itertext(el: ET.Element) -> str:
    return _clean("".join(el.itertext()))


def parse_tei(tei_xml: str) -> tuple[dict, list[dict]]:
    root = ET.fromstring(tei_xml)
    header: dict = {}
    title = root.find(".//t:teiHeader//t:titleStmt/t:title", TEI)
    if title is not None:
        header["title"] = _itertext(title)
    authors = []
    for pers in root.findall(".//t:teiHeader//t:sourceDesc//t:author/t:persName", TEI):
        name = " ".join(x for x in (
            " ".join(_itertext(f) for f in pers.findall("t:forename", TEI)),
            _itertext(pers.find("t:surname", TEI)) if pers.find("t:surname", TEI) is not None else "",
        ) if x)
        if name:
            authors.append(name)
    header["authors"] = authors
    date = root.find(".//t:teiHeader//t:publicationStmt/t:date", TEI)
    if date is not None and (date.get("when") or "")[:4].isdigit():
        header["year"] = int(date.get("when")[:4])
    idno = root.find(".//t:teiHeader//t:idno[@type='DOI']", TEI)
    if idno is not None and idno.text:
        header["doi"] = idno.text.strip().lower()
    arx = root.find(".//t:teiHeader//t:idno[@type='arXiv']", TEI)
    if arx is not None and arx.text:
        m = ARXIV_NEW.search(arx.text)
        if m:
            header["arxiv_id"] = m.group(1)

    paragraphs: list[dict] = []

    def add(kind: str, section: str, text: str, coords: Optional[str]) -> None:
        if len(text) < 3:
            return
        boxes = _boxes(coords)
        paragraphs.append({
            "id": f"p{len(paragraphs) + 1}",
            "kind": kind,
            "section": section,
            "text": text,
            "page": _first_page(boxes),
            "boxes": boxes,
        })

    for p in root.findall(".//t:profileDesc/t:abstract//t:p", TEI):
        add("text", "Abstract", _itertext(p), p.get("coords"))

    body = root.find(".//t:text/t:body", TEI)
    if body is not None:
        for div in body.iter(f"{{{TEI['t']}}}div"):
            head = div.find("t:head", TEI)
            section = _itertext(head) if head is not None else ""
            if head is not None and head.get("n"):
                section = f"{head.get('n')} {section}"
            for p in div.findall("t:p", TEI):
                add("text", section, _itertext(p), p.get("coords"))
        for fig in body.iter(f"{{{TEI['t']}}}figure"):
            caption = " ".join(_itertext(x) for x in fig.findall("t:head", TEI) + fig.findall("t:figDesc", TEI))
            if fig.get("type") == "table":
                rows = [" | ".join(_itertext(c) for c in row.findall("t:cell", TEI)) for row in fig.findall(".//t:row", TEI)]
                text = (caption + "\n" if caption else "") + "\n".join(r for r in rows if r.strip())
                add("table", caption[:80] or "Table", text.strip(), fig.get("coords"))
            elif caption:
                add("caption", "Figure", caption, fig.get("coords"))

    # 没有页码的段落（GROBID 偶尔漏坐标）沿用前一段的页码
    last = None
    for p in paragraphs:
        if p["page"] is None:
            p["page"] = last
        last = p["page"] or last
    return header, paragraphs


# httpx 带文件上传时 data 必须是 dict；同名字段（teiCoordinates）用列表表示多个值
GROBID_FORM = {
    "teiCoordinates": ["p", "head", "figure"],
    "consolidateHeader": "0",
    "consolidateCitations": "0",
}


def grobid_request(data: bytes) -> httpx.Request:
    files = {"input": ("paper.pdf", data, "application/pdf")}
    return httpx.Request("POST", f"{settings.grobid_url}/api/processFulltextDocument", files=files, data=GROBID_FORM)


def parse_with_grobid(data: bytes) -> tuple[dict, list[dict]]:
    with httpx.Client(timeout=180) as client:
        r = client.send(grobid_request(data))
    r.raise_for_status()
    return parse_tei(r.text)


def parse_with_pypdf(data: bytes) -> tuple[dict, list[dict]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    header: dict = {}
    meta = reader.metadata or {}
    if getattr(meta, "title", None) and len(meta.title) > 8:
        header["title"] = meta.title.strip()
    paragraphs: list[dict] = []
    for page_no, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        if page_no == 1 and "title" not in header:
            lines = [ln.strip() for ln in raw.splitlines() if len(ln.strip()) > 15]
            if lines:
                header["title"] = lines[0]
        blocks = [b for b in re.split(r"\n\s*\n", raw) if b.strip()]
        if len(blocks) <= 1:
            # pypdf 通常不给空行，按句子拼成约 600 字符的块
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", _clean(raw))
            blocks, buf = [], ""
            for s in sentences:
                if len(buf) + len(s) > 600 and buf:
                    blocks.append(buf)
                    buf = ""
                buf = f"{buf} {s}".strip()
            if buf:
                blocks.append(buf)
        for b in blocks:
            text = _clean(b)
            if len(text) < 3:
                continue
            kind = "table" if re.match(r"^table\s+\d", text, re.I) else "text"
            paragraphs.append({"id": f"p{len(paragraphs) + 1}", "kind": kind, "section": "",
                               "text": text, "page": page_no, "boxes": []})
    first_text = " ".join(p["text"] for p in paragraphs[:8])
    m = DOI_RE.search(first_text)
    if m:
        header["doi"] = m.group(1).rstrip(".,;)").lower()
    m = re.search(r"arXiv:(\d{4}\.\d{4,5})", first_text)
    if m:
        header["arxiv_id"] = m.group(1)
    return header, paragraphs


def parse_pdf(data: bytes) -> tuple[dict, list[dict], str, Optional[str]]:
    """返回 (header, paragraphs, parser, warning)。"""
    warning = None
    if settings.grobid_url:
        try:
            header, paragraphs = parse_with_grobid(data)
            if paragraphs:
                if not any(p["kind"] == "table" for p in paragraphs):
                    warning = "没有从这篇论文中解析出表格，表格里的数字可能无法核对。"
                return header, paragraphs, "grobid", warning
        except Exception as exc:  # GROBID 任何问题都不应让整篇论文读取失败，退回简易解析
            log.warning("GROBID 解析失败，改用 pypdf：%r", exc)
    header, paragraphs = parse_with_pypdf(data)
    warning = "使用简易解析（未连接 GROBID），表格结构和段落边界可能不准确，也无法在 PDF 中高亮段落。"
    if not paragraphs:
        warning = "PDF 中没有可读取的文字（可能是扫描件），无法核对。"
    return header, paragraphs, "pypdf", warning
