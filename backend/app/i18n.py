"""界面文字的中英文。后端返回给前端的提示一律用 L(中文, 英文) 包成 {"zh", "en"}，前端按当前语言显示。"""
from __future__ import annotations

import json
from typing import Optional, Union

Text = Union[str, dict]


def L(zh: str, en: str) -> dict:
    return {"zh": zh, "en": en}


def dumps(text: Optional[Text]) -> Optional[str]:
    """存进数据库的文本字段（如论文的解析提示）序列化成 JSON 字符串。"""
    if text is None:
        return None
    return json.dumps(text, ensure_ascii=False) if isinstance(text, dict) else text


def loads(raw: Optional[str]) -> Optional[Text]:
    """读回 dumps 存的字段；旧数据是纯文本，原样返回。"""
    if not raw:
        return raw
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
            if isinstance(value, dict) and "zh" in value:
                return value
        except ValueError:
            pass
    return raw
