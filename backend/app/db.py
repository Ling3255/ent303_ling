"""数据库表：论文（含解析结果与来源检查）、条件缓存、检查记录、用户反馈。

开发时默认用 SQLite；部署时把 DATABASE_URL 指向 PostgreSQL 即可，表结构相同。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # 缓存键：doi:<doi> / arxiv:<id> / sha256:<pdf 哈希>
    cache_key: Mapped[str] = mapped_column(String(300), index=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    venue: Mapped[Optional[str]] = mapped_column(Text)

    # ① 来源检查结果：published / preprint / not_found / unknown
    source_status: Mapped[str] = mapped_column(String(20), default="unknown")
    source_detail: Mapped[dict] = mapped_column(JSON, default=dict)

    pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text)
    pdf_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # ok / need_upload / missing
    fulltext_status: Mapped[str] = mapped_column(String(20), default="missing")

    # 解析出的段落：[{id, kind, section, text, page, boxes}]
    paragraphs: Mapped[Optional[list]] = mapped_column(JSON)
    parser: Mapped[Optional[str]] = mapped_column(String(20))
    parse_warning: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConditionCache(Base):
    """第 5 步的结果按（论文, 论断）缓存，同一篇论文同一说法只问一次大模型。"""

    __tablename__ = "condition_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_key: Mapped[str] = mapped_column(String(300), index=True)
    claim_hash: Mapped[str] = mapped_column(String(64), index=True)
    engine: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    text: Mapped[str] = mapped_column(Text)
    sentences: Mapped[list] = mapped_column(JSON)
    paper_ids: Mapped[list] = mapped_column(JSON)
    # queued / running / done / failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[Optional[str]] = mapped_column(String(40))
    error: Mapped[Optional[str]] = mapped_column(Text)
    report: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[Optional[float]] = mapped_column(Float)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_id: Mapped[str] = mapped_column(ForeignKey("checks.id"), index=True)
    sentence_idx: Mapped[int] = mapped_column(Integer)
    # source / support / comparability
    layer: Mapped[str] = mapped_column(String(20))
    system_label: Mapped[Optional[str]] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
