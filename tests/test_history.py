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
    assert not at.error, [e.value for e in at.error]

    views = [b for b in at.button if b.label == "View"]
    assert len(views) == 3                       # one View button per run
    for i in range(3):                           # open each run in turn (newest first); only the failed one shows an error
        at.run()
        [b for b in at.button if b.label == "View"][i].click().run()
        assert not at.exception, at.exception
        text = " ".join(m.value for m in at.markdown).lower().replace("financ", "")
        assert "nan" not in text
        assert all("boom" in e.value for e in at.error), [e.value for e in at.error]


def test_pagination(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'p.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = sa.create_engine(url)
    db.init_db(eng)
    for i in range(23):
        db.insert_run(dict(user_email="a@b.c", model="x/y", output=f"out {i}", prompt_version_id=1), eng)

    at = AppTest.from_file(str(ROOT / "views/history.py"), default_timeout=30)
    at.session_state["user"] = "a@b.c"
    at.run()
    assert not at.exception, at.exception
    assert len([b for b in at.button if b.label == "View"]) == 10
    assert any("Page 1 of 3" in m.value for m in at.markdown)
    [b for b in at.button if b.label == "Next ▶"][0].click().run()
    assert any("Page 2 of 3" in m.value for m in at.markdown)
    [b for b in at.button if b.label == "Next ▶"][0].click().run()
    assert len([b for b in at.button if b.label == "View"]) == 3       # 23 runs: last page has 3
    assert [b for b in at.button if b.label == "Next ▶"][0].disabled
    at.selectbox[-1].select(25).run()                                   # changing page size returns to page 1
    assert any("Page 1 of 1" in m.value for m in at.markdown)
