import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa

from lib import db
from lib.llm import estimate_cost, render_template, run_model


def test_render_template_fills_and_flags_unknown():
    text, unknown = render_template("Pop: {{population}} / {{nope}} / {{notes}}",
                                    {"population": "kids", "notes": "  "})
    assert text == "Pop: kids / {{nope}} / (not specified)"
    assert unknown == ["nope"]


def test_estimate_cost():
    assert abs(estimate_cost(1000, 2000, 1.0, 5.0) - 0.011) < 1e-9
    assert estimate_cost(None, 1, 1, 1) is None


class FakeClient:
    def __init__(self, cost=None, fail=False):
        self.cost, self.fail = cost, fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        if self.fail:
            raise RuntimeError("boom")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=200, cost=self.cost, model_extra={})
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="idea"))])


MODEL = {"id": "x/y", "in": 1.0, "out": 2.0}


def test_run_model_uses_reported_cost():
    r = run_model(MODEL, "s", "u", 0.5, 100, client=FakeClient(cost=0.0123))
    assert r["output"] == "idea" and r["cost_usd"] == 0.0123 and r["tokens_in"] == 100


def test_run_model_falls_back_to_price_table():
    r = run_model(MODEL, "s", "u", 0.5, 100, client=FakeClient(cost=None))
    assert abs(r["cost_usd"] - (100 * 1 + 200 * 2) / 1e6) < 1e-12


def test_run_model_error_is_returned_not_raised():
    r = run_model(MODEL, "s", "u", 0.5, 100, client=FakeClient(fail=True))
    assert "boom" in r["error"] and r["output"] == ""


def test_db_roundtrip(tmp_path):
    eng = sa.create_engine(f"sqlite:///{tmp_path/'t.db'}")
    db.init_db(eng)
    vs = db.list_prompt_versions(eng)
    assert {v["name"] for v in vs} == {"v1 - baseline", db.V2_NAME}   # baseline + the house-style prompt
    db.init_db(eng)                                                   # re-running must not duplicate them
    assert len(db.list_prompt_versions(eng)) == 2
    vid = db.save_prompt_version("v2", "sys", "tpl", "a@b.c", eng)
    assert db.list_prompt_versions(eng)[0]["id"] == vid
    rid = db.insert_run(dict(user_email="a@b.c", model="x/y", output="o", inputs_json={"a": 1}), eng)
    db.update_feedback(rid, 4, "good", eng)
    run = db.fetch_runs(eng)[0]
    assert run["rating"] == 4 and run["notes"] == "good"
