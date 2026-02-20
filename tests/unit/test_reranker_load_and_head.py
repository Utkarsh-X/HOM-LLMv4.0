import os

import pytest
import torch

import homllm.ranking.reranker as reranker_mod
from homllm.ranking.reranker import QwenReranker


class _FakeConfig:
    def __init__(self):
        self.pad_token_id = None
        self.num_labels = 1


class _FakeModel:
    def __init__(self, state):
        self._state = state
        self.config = _FakeConfig()

    def state_dict(self):
        return self._state

    def to(self, _device):
        return self

    def eval(self):
        return self


class _FakeTokenizer:
    pad_token = "</s>"
    eos_token = "</s>"
    unk_token = "<unk>"
    pad_token_id = 0

    @classmethod
    def from_pretrained(cls, *_args, **_kwargs):
        return cls()

    def __call__(self, *_args, **_kwargs):
        return {"input_ids": [1, 2, 3]}


def test_reranker_fail_fast_when_head_missing(monkeypatch):
    class _FakeAutoModel:
        @classmethod
        def from_pretrained(cls, *_args, **_kwargs):
            model = _FakeModel(
                state={
                    "encoder.layer.weight": torch.ones((2, 2), dtype=torch.float32),
                }
            )
            loading_info = {"missing_keys": ["score.weight"], "unexpected_keys": []}
            return model, loading_info

    monkeypatch.setattr(reranker_mod, "AutoTokenizer", _FakeTokenizer)
    monkeypatch.setattr(reranker_mod, "AutoModelForSequenceClassification", _FakeAutoModel)

    rr = QwenReranker("fake/model-missing-head")
    assert rr.healthcheck() is False
    assert rr._available is False
    assert rr._head_validated is False
    assert rr._load_error is not None
    err = rr._load_error.lower()
    assert "head parameters" in err and (
        "missing" in err or "not found" in err
    )


def test_reranker_head_present_and_shaped_mock(monkeypatch):
    class _FakeAutoModel:
        @classmethod
        def from_pretrained(cls, *_args, **_kwargs):
            model = _FakeModel(
                state={
                    "encoder.layer.weight": torch.ones((2, 2), dtype=torch.float32),
                    "score.weight": torch.ones((1, 4), dtype=torch.float32),
                    "score.bias": torch.zeros((1,), dtype=torch.float32),
                }
            )
            loading_info = {"missing_keys": [], "unexpected_keys": []}
            return model, loading_info

    monkeypatch.setattr(reranker_mod, "AutoTokenizer", _FakeTokenizer)
    monkeypatch.setattr(reranker_mod, "AutoModelForSequenceClassification", _FakeAutoModel)

    rr = QwenReranker("fake/model-good-head")
    assert rr.healthcheck() is True
    assert rr._available is True
    assert rr._head_validated is True
    assert rr._model is not None
    state = rr._model.state_dict()
    assert "score.weight" in state
    assert "score.bias" in state
    assert tuple(state["score.weight"].shape) == (1, 4)


@pytest.mark.skipif(
    os.environ.get("HOMLLM_RUN_RERANKER_TESTS") != "1",
    reason="Set HOMLLM_RUN_RERANKER_TESTS=1 to run real-model reranker checks.",
)
def test_reranker_real_head_present_and_shaped():
    rr = QwenReranker("tomaarsen/Qwen3-Reranker-0.6B-seq-cls")
    assert rr.healthcheck() is True
    assert rr._model is not None
    state = rr._model.state_dict()
    assert "score.weight" in state
    score_weight = state["score.weight"]
    assert score_weight.ndim == 2
    assert int(score_weight.shape[0]) == 1
    assert float(score_weight.abs().sum().item()) > 0.0
    missing = [str(k) for k in rr._loading_info.get("missing_keys", [])]
    assert not any(k.endswith("score.weight") or k.endswith("classifier.weight") for k in missing)
