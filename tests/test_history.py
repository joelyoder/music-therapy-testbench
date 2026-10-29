import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from lib import db


def test_history_shows_clean_run_without_nan(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'h.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = sa.create_engine(url)
    db.init_db(eng)
    # a successful, unrated run (error / rating / notes all empty), plus a rated one
    db.insert_run(dict(user_email="a@b.c", model="x/y", output="GOOD OUTPUT", prompt_version_id=1,
                       tokens_in=1, tokens_out=2, cost_usd=0.1, latency_ms=5), eng)
    db.insert_run(dict(user_email="a@b.c", model="x/y", output="OTHER", prompt_version_id=1, rating=4,
                       notes="nice"), eng)

    # a failed run, so the error column mixes text and empty values (this is what triggered the bug)
    db.insert_run(dict(user_email="a@b.c", model="x/z", output="", error="RuntimeError: boom",
                       prompt_version_id=1), eng)

    at = AppTest.from_file(str(ROOT / "views/history.py"), default_timeout=30)
    at.session_state["user"] = "a@b.c"
    at.run()
    assert not at.exception, at.exception
    # inspect each run in turn; only the failed one may show an error box
    ids = at.selectbox[-1].options
    for rid in ids:
        at.selectbox[-1].select(rid).run()
        assert not at.exception, at.exception
        errs = [e.value for e in at.error]
        assert all("boom" in e for e in errs), errs
        assert "nan" not in " ".join(m.value for m in at.markdown).lower().replace("financ", "")
    shown = " ".join(m.value for m in at.markdown)
    assert "nan" not in shown.lower().replace("financ", "")
    assert "unrated" in shown or "rating: 4" in shown
