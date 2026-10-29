import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from lib.models import parse_models, under_ceiling


def test_parse_models_filters_and_converts_prices():
    payload = {"data": [
        {"id": "a/ok", "name": "OK", "pricing": {"prompt": "0.000001", "completion": "0.000005"},
         "architecture": {"output_modalities": ["text"]}, "context_length": 1000},
        {"id": "a/image-out", "pricing": {"prompt": "0.1", "completion": "0.1"},
         "architecture": {"output_modalities": ["image"]}},
        {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
        {"id": "a/no-price"},
        {"id": "a/free", "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    got = {m["id"]: m for m in parse_models(payload)}
    assert set(got) == {"a/ok", "a/free"}
    assert abs(got["a/ok"]["in"] - 1.0) < 1e-9 and abs(got["a/ok"]["out"] - 5.0) < 1e-9


def test_under_ceiling():
    ms = [{"id": "x", "out": 5}, {"id": "y", "out": 50}]
    assert [m["id"] for m in under_ceiling(ms, 20)] == ["x"]
    assert len(under_ceiling(ms, None)) == 2


def _fake_run(model, system, user, temperature, max_tokens, client=None):
    return {"output": f"IDEAS from {model['id']}", "error": None, "tokens_in": 1, "tokens_out": 2,
            "cost_usd": 0.0, "latency_ms": 1}


def test_extra_model_picker_respects_price_ceiling_and_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    with patch("lib.llm.run_model", _fake_run):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        assert not at.exception, at.exception
        more = next(m for m in at.multiselect if m.label.startswith("More models"))
        opts = " | ".join(more.options)
        assert "acme/cheap-1" in opts
        assert "acme/pricey-1" not in opts                # above $20/M output: hidden by default
        assert "anthropic/claude-haiku-4.5" not in opts   # already starred: not duplicated
        more.select("acme/cheap-1").run()
        at.button[[b.label for b in at.button].index("Generate")].click().run()
        assert not at.exception, at.exception
        text = " ".join(m.value for m in at.markdown)
        assert "IDEAS from acme/cheap-1" in text and "IDEAS from anthropic/claude-haiku-4.5" in text

        at.checkbox[0].check().run()                               # opt in to expensive models
        more = next(m for m in at.multiselect if m.label.startswith("More models"))
        assert "acme/pricey-1" in " | ".join(more.options)
