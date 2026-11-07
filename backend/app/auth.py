"""学生账号：学校邮箱 + 6 位验证码登录，免费版每月限定次数。只收集邮箱，不收集其他个人信息。"""
from __future__ import annotations

import hashlib
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .i18n import L
from .db import Check, LoginCode, User, UserSession, get_session, utcnow

log = logging.getLogger(__name__)
CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite 读回来的时间不带时区
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if email.count("@") != 1 or not email.split("@")[0]:
        raise HTTPException(400, L("邮箱格式不正确。", "Invalid email address."))
    domain = email.split("@")[1]
    if settings.allowed_email_domains and not any(
        domain == d or domain.endswith("." + d) for d in settings.allowed_email_domains
    ):
        raise HTTPException(400, L(f"请使用学校邮箱（{'、'.join(settings.allowed_email_domains)}）。",
                                  f"Please use your university email ({', '.join(settings.allowed_email_domains)})."))
    return email


def _send_email(to: str, code: str) -> bool:
    if not settings.smtp_host:
        return False
    msg = EmailMessage()
    msg["Subject"] = f"CiteCheck 登录验证码 / login code: {code}"
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(
        f"你的 CiteCheck 登录验证码是 {code}，{CODE_MINUTES} 分钟内有效。\n如果不是你本人操作，请忽略这封邮件。\n\n"
        f"Your CiteCheck login code is {code}. It expires in {CODE_MINUTES} minutes.\n"
        "If you did not request it, please ignore this email."
    )
    smtp_cls = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
    with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if smtp_cls is smtplib.SMTP:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    return True


def request_code(session: Session, email: str) -> dict:
    email = normalize_email(email)
    last = session.scalars(select(LoginCode).where(LoginCode.email == email).order_by(LoginCode.created_at.desc())).first()
    if last and (utcnow() - _aware(last.created_at)).total_seconds() < RESEND_SECONDS:
        raise HTTPException(429, L("验证码发送太频繁，请 1 分钟后再试。", "Too many requests. Please wait a minute and try again."))
    code = f"{secrets.randbelow(1_000_000):06d}"
    session.add(LoginCode(email=email, code_hash=_hash(code), expires_at=utcnow() + timedelta(minutes=CODE_MINUTES)))
    session.commit()
    try:
        sent = _send_email(email, code)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("验证码邮件发送失败：%s", exc)
        sent = False
    out: dict = {"ok": True, "sent": sent}
    if not sent:
        if not settings.dev_show_code:
            raise HTTPException(503, L("验证码邮件发送失败，请稍后再试。", "Could not send the verification email. Please try again later."))
        log.info("开发模式验证码 %s → %s", email, code)
        out["dev_code"] = code  # 只在未配置 SMTP 且 DEV_SHOW_CODE=1 时返回
    return out


def verify_code(session: Session, email: str, code: str) -> dict:
    email = normalize_email(email)
    row = session.scalars(
        select(LoginCode).where(LoginCode.email == email, LoginCode.used.is_(False)).order_by(LoginCode.created_at.desc())
    ).first()
    if not row or _aware(row.expires_at) < utcnow():
        raise HTTPException(400, L("验证码已过期，请重新获取。", "The code has expired. Please request a new one."))
    if row.attempts >= MAX_ATTEMPTS:
        raise HTTPException(400, L("尝试次数过多，请重新获取验证码。", "Too many attempts. Please request a new code."))
    if not secrets.compare_digest(row.code_hash, _hash(code.strip())):
        row.attempts += 1
        session.commit()
        raise HTTPException(400, L("验证码不正确。", "Incorrect code."))
    row.used = True
    user = session.scalars(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email)
        session.add(user)
        session.flush()
    token = secrets.token_urlsafe(32)
    session.add(UserSession(token_hash=_hash(token), user_id=user.id,
                            expires_at=utcnow() + timedelta(days=settings.session_days)))
    session.commit()
    return {"token": token, "user": user_info(session, user)}


def logout(session: Session, token: Optional[str]) -> None:
    if token:
        row = session.get(UserSession, _hash(token))
        if row:
            session.delete(row)
            session.commit()


def _month_start() -> datetime:
    now = utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def used_this_month(session: Session, user: User) -> int:
    return session.scalar(
        select(func.count()).select_from(Check).where(Check.user_id == user.id, Check.created_at >= _month_start())
    ) or 0


def user_info(session: Session, user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "plan": user.plan,
        "used": used_this_month(session, user),
        "quota": settings.monthly_quota if user.plan == "free" else None,
    }


def _token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: Optional[str] = Header(None), session: Session = Depends(get_session)) -> Optional[User]:
    token = _token(authorization)
    if not token:
        return None
    row = session.get(UserSession, _hash(token))
    if not row or _aware(row.expires_at) < utcnow():
        return None
    return session.get(User, row.user_id)


def require_quota(session: Session, user: Optional[User]) -> None:
    """AUTH_REQUIRED=1 时必须登录；登录用户的免费版每月有次数上限。"""
    if user is None:
        if settings.auth_required:
            raise HTTPException(401, L("请先用学校邮箱登录。", "Please log in with your university email first."))
        return
    if user.plan == "free" and used_this_month(session, user) >= settings.monthly_quota:
        raise HTTPException(429, L(f"免费版每月 {settings.monthly_quota} 次，本月已用完。",
                                  f"The free plan allows {settings.monthly_quota} checks per month. You have used them all."))
