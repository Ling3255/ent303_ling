"""界面文字的中英文。后端返回给前端的提示一律用 L(中文, 英文) 包成 {"zh", "en"}，前端按当前语言显示。"""
from __future__ import annotations

import json
import re
from typing import Optional, Union

Text = Union[str, dict]


_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")


def has_cjk(text: Optional[str]) -> bool:
    return bool(text and _CJK.search(text))


def L(zh: str, en: str) -> dict:
    return {"zh": zh, "en": en}


def L_safe(zh: str, en: Optional[str], fallback_en: str) -> dict:
    """英文缺失或混进了中文（比如大模型没按要求输出）时，用英文兜底句，保证英文界面看不到中文。"""
    return {"zh": zh, "en": en if en and not has_cjk(en) else fallback_en}


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
    return legacy_text(raw)


# 加入双语之前存进数据库的中文提示：按开头认出来补上英文
_LEGACY = [
    ("使用简易解析", "Using the basic parser (GROBID not connected): table structure and paragraph boundaries may be inaccurate, and paragraphs cannot be outlined in the PDF."),
    ("没有从这篇论文中解析出表格", "No tables were parsed from this paper; numbers in tables may not be verifiable."),
    ("PDF 中没有可读取的文字", "The PDF contains no readable text (possibly a scan), so it cannot be checked."),
    ("没有找到这篇论文", "Paper not found. If it does exist, please upload the PDF."),
    ("没有找到开放获取的全文", "No open-access full text found; please upload the PDF."),
    ("处理失败", "Processing failed. Please remove the paper and add it again."),
]


def legacy_text(raw: str, fallback_en: str = "See the Chinese interface for details.") -> Text:
    if not has_cjk(raw):
        return raw
    for prefix, en in _LEGACY:
        if raw.startswith(prefix):
            return L(raw, en)
    return L(raw, fallback_en)
