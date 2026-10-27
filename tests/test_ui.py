import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DEV_MODE"] = "1"

from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def fake_run(model, system, user, temperature, max_tokens, client=None):
    return {"output": f"IDEAS from {model['id']}", "error": None, "tokens_in": 10,
            "tokens_out": 20, "cost_usd": 0.001, "latency_ms": 500}


def test_generate_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui.db'}")
    with patch("lib.llm.run_model", fake_run):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        assert not at.exception, at.exception
        at.button[[b.label for b in at.button].index("Generate")].click().run()
        assert not at.exception, at.exception
        assert any("IDEAS from" in m.value for m in at.markdown), [m.value for m in at.markdown][:5]
