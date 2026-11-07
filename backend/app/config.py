"""运行配置，全部从环境变量读取（见仓库根目录 .env.example）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR.parent / 'citecheck.db'}")
    )
    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", str(BASE_DIR.parent / "uploads"))))
    upload_retention_days: int = field(default_factory=lambda: int(os.getenv("UPLOAD_RETENTION_DAYS", "7")))

    # 外部服务
    grobid_url: str = field(default_factory=lambda: os.getenv("GROBID_URL", "").rstrip("/"))
    contact_email: str = field(default_factory=lambda: os.getenv("CONTACT_EMAIL", "citecheck@example.com"))

    # 大模型：任何 OpenAI 兼容接口都可以（DeepSeek、通义千问 DashScope 兼容模式等）
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "60")))

    # 向量检索：bge-m3 需要额外安装 FlagEmbedding（requirements-embed.txt），否则退回关键词检索
    embedding_backend: str = field(default_factory=lambda: os.getenv("EMBEDDING_BACKEND", "lexical"))
    top_k_paragraphs: int = 5

    # 输入限制
    max_text_chars: int = 1500
    max_papers: int = 5

    # 外网开关：测试时关闭，所有学术接口返回“查询失败”
    network_enabled: bool = field(default_factory=lambda: _bool("NETWORK_ENABLED", True))

    # 学生账号：学校邮箱验证码登录，免费版每月 monthly_quota 次
    auth_required: bool = field(default_factory=lambda: _bool("AUTH_REQUIRED", False))
    allowed_email_domains: list[str] = field(default_factory=lambda: [
        d.strip().lower() for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "xjtlu.edu.cn,student.xjtlu.edu.cn").split(",") if d.strip()
    ])
    monthly_quota: int = field(default_factory=lambda: int(os.getenv("MONTHLY_QUOTA", "20")))
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "30")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "465")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")))
    # 没配 SMTP 时把验证码直接返回给前端，方便开发和内部测试；正式上线必须关掉
    dev_show_code: bool = field(default_factory=lambda: _bool("DEV_SHOW_CODE", True))

    cors_origins: list[str] = field(
        default_factory=lambda: [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
    )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
