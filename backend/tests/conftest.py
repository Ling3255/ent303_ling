import os
import sys
import tempfile
from pathlib import Path

# 测试一律离线、不调用大模型、用临时 SQLite
_tmp = tempfile.mkdtemp(prefix="citecheck-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["NETWORK_ENABLED"] = "0"
os.environ["LLM_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["GROBID_URL"] = ""
os.environ["EMBEDDING_BACKEND"] = "lexical"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402

init_db()


WHISPER_PARAGRAPHS = [
    {"id": "p1", "kind": "text", "section": "Abstract", "page": 1, "boxes": [],
     "text": "We study the capabilities of speech processing systems trained simply to predict large amounts of "
             "transcripts of audio on the internet. When scaled to 680,000 hours of multilingual and multitask "
             "supervision, the resulting models generalize well to standard benchmarks and are often competitive "
             "with prior fully supervised results but in a zero-shot transfer setting without the need for any fine-tuning."},
    {"id": "p2", "kind": "text", "section": "3.3 English Speech Recognition", "page": 6, "boxes": [],
     "text": "In 2015, Deep Speech 2 reported human-level performance on LibriSpeech test-clean. "
             "We compare Whisper with wav2vec 2.0 Large (no LM), a supervised model fine-tuned on the 960 hours of "
             "labeled LibriSpeech training data. Whisper models are evaluated zero-shot and never see LibriSpeech "
             "training data."},
    {"id": "p3", "kind": "table", "section": "Table 2", "page": 7,
     "boxes": [{"page": 7, "x": 54.0, "y": 80.0, "w": 240.0, "h": 160.0}],
     "text": "Table 2. Detailed comparison of effective robustness across various datasets. Although both models "
             "perform within 0.1% of each other on LibriSpeech, a zero-shot Whisper model performs much better on "
             "other datasets than expected for its LibriSpeech performance. Results reported in word error rate (WER).\n"
             "Dataset | wav2vec 2.0 Large (no LM) | Whisper Large V2 | RER (%)\n"
             "LibriSpeech Clean | 2.7 | 2.7 | 0.0\n"
             "Artie | 24.5 | 6.2 | 74.7\n"
             "Common Voice | 29.9 | 9.0 | 69.9\n"
             "TED-LIUM | 10.5 | 4.0 | 61.9"},
    {"id": "p4", "kind": "text", "section": "4 Analysis", "page": 9, "boxes": [],
     "text": "All experiments were run on NVIDIA V100 GPUs. Decoding uses beam search with temperature fallback."},
]


@pytest.fixture
def whisper_paragraphs():
    return [dict(p) for p in WHISPER_PARAGRAPHS]
