"""论文入库（第 1、2 步）和上传文件的定期清理。论文在后台线程里处理，前端轮询状态。"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from .config import settings
from .db import Paper, SessionLocal, utcnow
from .pipeline import papers as paper_io
from .pipeline.sources import check_source, parse_identifier

log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="paper")


def _existing(session, cache_key: str) -> Optional[Paper]:
    return session.scalars(
        select(Paper).where(Paper.cache_key == cache_key, Paper.fulltext_status == "ok").order_by(Paper.created_at.desc())
    ).first()


def add_by_identifier(session, raw: str, *, run_async: bool = True) -> Paper:
    ident = parse_identifier(raw)
    if "doi" in ident:
        key = f"doi:{ident['doi']}"
    elif "arxiv_id" in ident:
        key = f"arxiv:{ident['arxiv_id']}"
    else:
        key = f"title:{ident['title'].lower()}"
    cached = _existing(session, key)
    if cached:
        return cached
    paper = Paper(cache_key=key, doi=ident.get("doi"), arxiv_id=ident.get("arxiv_id"), title=ident.get("title"),
                  fulltext_status="processing")
    session.add(paper)
    session.commit()
    _submit(_process_identifier, paper.id, run_async)
    return paper


def add_by_upload(session, data: bytes, *, run_async: bool = True) -> Paper:
    digest = paper_io.sha256(data)
    path = paper_io.save_pdf(data)
    key = f"sha256:{digest}"
    cached = _existing(session, key)
    if cached:
        cached.pdf_path = str(path)
        cached.pdf_uploaded_at = utcnow()
        session.commit()
        return cached
    paper = Paper(cache_key=key, pdf_path=str(path), pdf_uploaded_at=utcnow(), fulltext_status="processing")
    session.add(paper)
    session.commit()
    _submit(_process_upload, paper.id, run_async)
    return paper


def _submit(fn, paper_id: str, run_async: bool) -> None:
    if run_async:
        executor.submit(_safe, fn, paper_id)
    else:
        _safe(fn, paper_id)


def _safe(fn, paper_id: str) -> None:
    try:
        fn(paper_id)
    except Exception as exc:  # 后台任务出错也要把状态写回去，前端才不会一直转圈
        log.exception("处理论文 %s 失败", paper_id)
        with SessionLocal() as session:
            paper = session.get(Paper, paper_id)
            if paper:
                paper.fulltext_status = "failed"
                paper.parse_warning = f"处理失败：{exc}"
                session.commit()


def _apply_source(paper: Paper, result) -> None:
    meta = result.metadata
    paper.source_status = result.status
    paper.source_detail = {"checked": result.checked, "found_in": meta.found_in}
    paper.title = meta.title or paper.title
    paper.authors = meta.authors or paper.authors or []
    paper.year = meta.year or paper.year
    paper.venue = meta.venue or paper.venue
    paper.doi = paper.doi or meta.doi
    paper.arxiv_id = paper.arxiv_id or meta.arxiv_id
    paper.pdf_url = paper.pdf_url or meta.pdf_url


def _process_identifier(paper_id: str) -> None:
    with SessionLocal() as session:
        paper = session.get(Paper, paper_id)
        title = paper.title if not (paper.doi or paper.arxiv_id) else None
        _apply_source(paper, check_source(doi=paper.doi, arxiv_id=paper.arxiv_id, title=title))
        session.commit()

        if paper.source_status == "not_found":
            paper.fulltext_status = "need_upload"
            paper.parse_warning = "没有找到这篇论文；如果确实存在，请直接上传 PDF。"
            session.commit()
            return
        try:
            data = paper_io.find_open_fulltext(doi=paper.doi, arxiv_id=paper.arxiv_id, pdf_url=paper.pdf_url)
        except paper_io.FullTextUnavailable as exc:
            paper.fulltext_status = "need_upload"
            paper.parse_warning = f"没有找到开放获取的全文，请上传 PDF。（{exc}）"
            session.commit()
            return
        paper.pdf_path = str(paper_io.save_pdf(data))
        _parse_into(paper, data)
        session.commit()


def _process_upload(paper_id: str) -> None:
    with SessionLocal() as session:
        paper = session.get(Paper, paper_id)
        data = Path(paper.pdf_path).read_bytes()
        header = _parse_into(paper, data)
        paper.title = header.get("title")
        paper.authors = header.get("authors") or []
        paper.year = header.get("year")
        paper.doi = header.get("doi")
        paper.arxiv_id = header.get("arxiv_id")
        session.commit()
        if paper.doi or paper.arxiv_id or paper.title:
            _apply_source(paper, check_source(doi=paper.doi, arxiv_id=paper.arxiv_id, title=paper.title))
        else:
            paper.source_status = "unknown"
        session.commit()


def _parse_into(paper: Paper, data: bytes) -> dict:
    header, paragraphs, parser, warning = paper_io.parse_pdf(data)
    paper.paragraphs = paragraphs
    paper.parser = parser
    paper.parse_warning = warning
    paper.fulltext_status = "ok" if paragraphs else "failed"
    return header


# ---------------- 清理：上传的 PDF 7 天后删除 ----------------
def cleanup_uploads() -> int:
    cutoff = utcnow() - timedelta(days=settings.upload_retention_days)
    removed = 0
    with SessionLocal() as session:
        old = session.scalars(select(Paper).where(Paper.pdf_uploaded_at.is_not(None), Paper.pdf_uploaded_at < cutoff)).all()
        for paper in old:
            if paper.pdf_path:
                Path(paper.pdf_path).unlink(missing_ok=True)
            # 用户上传的全文一并删除，只保留元数据和已抽取的条件缓存
            paper.pdf_path = None
            paper.paragraphs = None
            paper.pdf_uploaded_at = None
            paper.fulltext_status = "need_upload"
            removed += 1
        session.commit()
    return removed


def start_cleanup_thread(interval_hours: float = 6) -> None:
    def loop() -> None:
        while True:
            try:
                n = cleanup_uploads()
                if n:
                    log.info("已删除 %d 个过期的上传文件", n)
            except Exception:
                log.exception("清理上传文件失败")
            time.sleep(interval_hours * 3600)

    threading.Thread(target=loop, daemon=True, name="cleanup").start()
