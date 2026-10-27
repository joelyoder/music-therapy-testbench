import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest


def _clean_env(monkeypatch, tmp_path):
    for k in ("DEV_MODE", "APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'a.db'}")


def test_fails_closed_when_nothing_configured(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert any("not configured" in e.value for e in at.error)
    assert not [b for b in at.button if b.label == "Generate"]


def test_password_gate(monkeypatch, tmp_path):
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert at.text_input and not [b for b in at.button if b.label == "Generate"]
    at.text_input[0].input("wrong").run()
    assert any("Wrong password" in e.value for e in at.error)
    at.text_input[0].input("s3cret-pass").run()
    assert [b for b in at.button if b.label == "Generate"]
