"""大模型接口封装。

只依赖 OpenAI 兼容的 /chat/completions 接口，换成通义千问等其他已备案模型时
只需改 LLM_BASE_URL 和 LLM_MODEL 两个环境变量。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _extract_json(content: str) -> Any:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if fenced:
        content = fenced.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise


def chat_json(system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 2000,
              client: Optional[httpx.Client] = None) -> Any:
    """发送一次对话并把回答解析成 JSON。失败时重试一次。"""
    if not settings.llm_enabled:
        raise LLMError("未配置 LLM_API_KEY")

    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    own_client = client is None
    client = client or httpx.Client(timeout=settings.llm_timeout)
    try:
        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                resp = client.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return _extract_json(content)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                log.warning("LLM 调用失败，重试：%s", exc)
        raise LLMError(str(last_error))
    finally:
        if own_client:
            client.close()
