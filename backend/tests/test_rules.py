from app.pipeline.claims import find_subjects
from app.pipeline.comparability import check_sentence, compare_conditions
from app.pipeline.evidence import locate_quote
from app.pipeline.sentences import numbers_in, split_and_flag, split_sentences
from app.pipeline.sources import parse_identifier
from app.pipeline.support import _finalize
from app.pipeline.vocab import canonical, find_terms


# ---------- 拆句 ----------
def test_split_chinese_and_english():
    text = "Whisper 在 LibriSpeech 上是 2.7%。Radford et al. reported a WER of 2.7 on test-clean. 这很好！"
    parts = [s["text"] for s in split_sentences(text)]
    assert parts == [
        "Whisper 在 LibriSpeech 上是 2.7%。",
        "Radford et al. reported a WER of 2.7 on test-clean.",
        "这很好！",
    ]


def test_flags():
    flags = {s["text"]: s for s in split_and_flag("Whisper 比 wav2vec 好。今天天气不错。")}
    assert flags["Whisper 比 wav2vec 好。"]["suggested"]
    assert not flags["今天天气不错。"]["suggested"]


def test_numbers_skip_versions_years_and_refs():
    assert numbers_in("wav2vec 2.0 在 2020 年 [12] 达到 1.8% 和 3.3") == ["1.8%", "3.3"]
    assert numbers_in("ResNet-50 gets 76.1 top-1") == ["76.1"]


# ---------- 词表 ----------
def test_vocab_normalizes_aliases():
    kinds = {(m.kind, m.canonical) for m in find_terms("LibriSpeech test clean, word error rate")}
    assert kinds == {("dataset", "LibriSpeech"), ("split", "test-clean"), ("metric", "WER")}
    assert canonical("ILSVRC-2012", "dataset") == "ImageNet-1k"
    assert canonical("Top-1 acc", "metric") == "top-1 accuracy"
    # 短别名不能匹配到单词内部
    assert not find_terms("the system was robust", ("metric",))


def test_subjects():
    assert find_subjects("Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%") == ["Whisper", "wav2vec 2.0"]
    # 英文句子：不能把 "reach 2"（来自 2.7%）当成模型名
    assert find_subjects("Whisper and wav2vec 2.0 both reach 2.7% on LibriSpeech") == ["Whisper", "wav2vec 2.0"]


def test_parse_identifier():
    assert parse_identifier("arXiv:2212.04356v1") == {"arxiv_id": "2212.04356"}
    assert parse_identifier("https://arxiv.org/abs/2006.11477") == {"arxiv_id": "2006.11477"}
    assert parse_identifier("2212.04356") == {"arxiv_id": "2212.04356"}
    assert parse_identifier("https://doi.org/10.1109/CVPR.2016.90") == {"doi": "10.1109/cvpr.2016.90"}
    assert parse_identifier("10.48550/arXiv.2212.04356") == {"arxiv_id": "2212.04356"}
    assert parse_identifier("Attention is all you need") == {"title": "Attention is all you need"}


# ---------- 可比规则 ----------
def _c(**fields):
    return {k: {"value": v, "quote": v} for k, v in fields.items()}


def test_different_split_is_major():
    out = compare_conditions(_c(dataset="LibriSpeech", split="test-clean", metric="WER"),
                             _c(dataset="LibriSpeech", split="test-other", metric="WER"))
    assert out["level"] == "major"
    assert {f["field"]: f["severity"] for f in out["fields"]}["split"] == "major"


def test_aliases_count_as_same():
    out = compare_conditions(
        _c(dataset="ILSVRC-2012", split="val", metric="top-1", baseline="ResNet-50", environment="A100"),
        _c(dataset="ImageNet", split="validation set", metric="Top-1 accuracy", baseline="resnet-50", environment="a100"),
    )
    assert out["level"] == "consistent"


def test_hardware_only_is_minor():
    out = compare_conditions(
        _c(dataset="ImageNet", split="val", metric="top-1", baseline="ResNet-50", environment="8x V100"),
        _c(dataset="ImageNet", split="val", metric="top-1", baseline="ResNet-50", environment="TPU v3"),
    )
    assert out["level"] == "minor"


def test_zero_shot_vs_finetuned_is_major_even_in_minor_field():
    out = compare_conditions(
        _c(dataset="LibriSpeech", split="test-clean", metric="WER", baseline="large-v2", environment="zero-shot"),
        _c(dataset="LibriSpeech", split="test-clean", metric="WER", baseline="Large (no LM)",
           environment="fine-tuned on 960h labeled LibriSpeech"),
    )
    env = {f["field"]: f for f in out["fields"]}["environment"]
    assert env["severity"] == "major" and env["markers"][0]["name"]["zh"] == "训练方式"
    assert out["level"] == "major"


def test_missing_field_is_never_consistent():
    out = compare_conditions(_c(dataset="CIFAR-10", metric="top-1"), _c(dataset="CIFAR-10", metric="top-1"))
    assert out["level"] == "insufficient"


def test_no_comparison():
    assert check_sentence([])["level"] == "na"


# ---------- 原句核对 ----------
def test_locate_quote(whisper_paragraphs):
    assert locate_quote("a zero-shot Whisper model performs much better", whisper_paragraphs)["id"] == "p3"
    assert locate_quote("LibriSpeech Clean | 2.7 | 2.7", whisper_paragraphs)["id"] == "p3"
    assert locate_quote("Whisper beats every model on every benchmark by 50%", whisper_paragraphs) is None


def test_fabricated_quotes_are_dropped(whisper_paragraphs):
    raw = {
        "verdict": "supported",
        "evidence": [{"paragraph_id": "p3", "quote": "Whisper achieves 1.5% WER on LibriSpeech test-clean"}],
        "conditions": {
            "dataset": {"value": "LibriSpeech", "quote": "LibriSpeech Clean | 2.7 | 2.7"},
            "environment": {"value": "fine-tuned", "quote": "Whisper was fine-tuned on LibriSpeech"},
        },
    }
    out = _finalize(raw, whisper_paragraphs[2:3], whisper_paragraphs)
    assert out["verdict"] == "not_found"  # 唯一的证据是编造的
    assert out["conditions"]["dataset"]["value"] == "LibriSpeech"
    assert out["conditions"]["environment"]["value"] is None  # 原句不存在 → 置空
    assert out["notes"]


def test_number_match_ignores_dataset_names():
    from app.pipeline.retrieval import number_hits

    assert number_hits("CommonVoice5.1 Fleurs.en_us", ["5.1%"]) == []
    assert number_hits("Common Voice | 29.9 | 5.1 | 69.9", ["5.1%"]) == ["5.1%"]


def test_every_rule_text_has_english():
    from app.pipeline.comparability import load_rules

    rules = load_rules()
    for name, spec in rules["fields"].items():
        assert spec.get("label_en") and spec.get("reason_en"), name
    for marker in rules["markers"]:
        assert marker.get("name_en") and marker.get("reason_en"), marker["name"]
        if marker.get("flag_if_one_sided"):
            assert "{known}" in marker["one_sided_reason_en"], marker["name"]
