"""CiteCheck 后端接口。启动：uvicorn app.main:app --reload；接口文档见 /docs。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, services
from .config import settings
from .db import Check, Feedback, Paper, User, get_session, init_db
from .pipeline.runner import paper_summary, run_check, stage_list
from .pipeline.sentences import split_and_flag

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
check_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="check")
MAX_PDF_BYTES = 40 * 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    services.start_cleanup_thread()
    yield


app = FastAPI(title="CiteCheck API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


# ---------------- 请求体 ----------------
class SplitIn(BaseModel):
    text: str


class IdentifierIn(BaseModel):
    identifier: str = Field(..., description="DOI、arXiv 编号或论文标题")


class EmailIn(BaseModel):
    email: str


class VerifyIn(BaseModel):
    email: str
    code: str


class SentenceChoice(BaseModel):
    idx: int
    selected: bool


class CheckIn(BaseModel):
    text: str
    paper_ids: list[str]
    sentences: Optional[list[SentenceChoice]] = None


class FeedbackIn(BaseModel):
    sentence_idx: int
    layer: Literal["source", "support", "comparability"]
    system_label: Optional[str] = None
    reason: str = Field(..., min_length=2, max_length=2000)


def _check_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise HTTPException(400, "请先粘贴要检查的文字。")
    if len(text) > settings.max_text_chars:
        raise HTTPException(400, f"文字最多 {settings.max_text_chars} 字，当前 {len(text)} 字。")
    return text


# ---------------- 接口 ----------------
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm": settings.llm_model if settings.llm_enabled else None,
        "grobid": bool(settings.grobid_url),
        "embedding": settings.embedding_backend,
        "limits": {"max_text_chars": settings.max_text_chars, "max_papers": settings.max_papers},
        "auth": {"required": settings.auth_required, "domains": settings.allowed_email_domains,
                 "monthly_quota": settings.monthly_quota},
        "stages": stage_list(),
    }


@app.post("/api/auth/request-code")
def auth_request_code(body: EmailIn, session: Session = Depends(get_session)):
    return auth.request_code(session, body.email)


@app.post("/api/auth/verify")
def auth_verify(body: VerifyIn, session: Session = Depends(get_session)):
    return auth.verify_code(session, body.email, body.code)


@app.post("/api/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None), session: Session = Depends(get_session)):
    auth.logout(session, auth._token(authorization))
    return {"ok": True}


@app.get("/api/me")
def me(user: Optional[User] = Depends(auth.current_user), session: Session = Depends(get_session)):
    if not user:
        raise HTTPException(401, "未登录。")
    return auth.user_info(session, user)


@app.get("/api/me/checks")
def my_checks(user: Optional[User] = Depends(auth.current_user), session: Session = Depends(get_session)):
    if not user:
        raise HTTPException(401, "未登录。")
    rows = session.scalars(select(Check).where(Check.user_id == user.id).order_by(Check.created_at.desc()).limit(50)).all()
    return [{"id": c.id, "status": c.status, "created_at": c.created_at.isoformat(), "preview": c.text[:80],
             "summary": (c.report or {}).get("summary")} for c in rows]


@app.post("/api/split")
def split(body: SplitIn):
    return {"sentences": split_and_flag(_check_text(body.text))}


@app.post("/api/papers/identifier")
def add_paper_identifier(body: IdentifierIn, session: Session = Depends(get_session)):
    if not body.identifier.strip():
        raise HTTPException(400, "请填写 DOI、arXiv 编号或论文标题。")
    return paper_summary(services.add_by_identifier(session, body.identifier))


@app.post("/api/papers/upload")
async def add_paper_upload(file: UploadFile = File(...), session: Session = Depends(get_session)):
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(400, "PDF 不能超过 40 MB。")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "上传的文件不是 PDF。")
    return paper_summary(services.add_by_upload(session, data))


@app.get("/api/papers/{paper_id}")
def get_paper(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "找不到这篇论文。")
    return paper_summary(paper)


@app.get("/api/papers/{paper_id}/pdf")
def get_paper_pdf(paper_id: str, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper or not paper.pdf_path or not Path(paper.pdf_path).exists():
        raise HTTPException(404, "这篇论文的 PDF 已删除或不存在（上传的文件保留 7 天）。")
    return FileResponse(paper.pdf_path, media_type="application/pdf")


@app.post("/api/checks")
def create_check(body: CheckIn, session: Session = Depends(get_session),
                 user: Optional[User] = Depends(auth.current_user)):
    text = _check_text(body.text)
    auth.require_quota(session, user)
    if not body.paper_ids:
        raise HTTPException(400, "请至少添加一篇论文。")
    if len(body.paper_ids) > settings.max_papers:
        raise HTTPException(400, f"每次最多 {settings.max_papers} 篇论文。")
    for pid in body.paper_ids:
        if not session.get(Paper, pid):
            raise HTTPException(400, f"论文 {pid} 不存在。")

    sentences = split_and_flag(text)
    if body.sentences is not None:
        chosen = {c.idx: c.selected for c in body.sentences}
        for s in sentences:
            s["selected"] = chosen.get(s["idx"], s["suggested"])
    else:
        for s in sentences:
            s["selected"] = s["suggested"]

    check = Check(text=text, sentences=sentences, paper_ids=list(dict.fromkeys(body.paper_ids)), status="queued",
                  user_id=user.id if user else None)
    session.add(check)
    session.commit()
    check_executor.submit(run_check, check.id)
    return {"id": check.id}


@app.get("/api/checks/{check_id}")
def get_check(check_id: str, session: Session = Depends(get_session)):
    check = session.get(Check, check_id)
    if not check:
        raise HTTPException(404, "找不到这次检查。")
    return {
        "id": check.id,
        "status": check.status,
        "stage": check.stage,
        "stages": stage_list(),
        "error": check.error,
        "text": check.text,
        "created_at": check.created_at.isoformat() if check.created_at else None,
        "duration_s": check.duration_s,
        "report": check.report,
    }


@app.post("/api/checks/{check_id}/feedback")
def add_feedback(check_id: str, body: FeedbackIn, session: Session = Depends(get_session),
                 user: Optional[User] = Depends(auth.current_user)):
    if not session.get(Check, check_id):
        raise HTTPException(404, "找不到这次检查。")
    fb = Feedback(check_id=check_id, user_id=user.id if user else None, sentence_idx=body.sentence_idx, layer=body.layer,
                  system_label=body.system_label, reason=body.reason.strip())
    session.add(fb)
    session.commit()
    return {"ok": True, "id": fb.id}
