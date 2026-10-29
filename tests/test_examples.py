import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from lib import db
from lib.library import build_examples_text, describe, format_example, load_library
from lib.llm import render_template

ENTRY = {"id": 1, "title": "Rhythm Circle", "population": ["Older Adults"], "domain": ["Musical", "Emotional"],
         "method": ["Improvisational"], "equipment": ["Drums"], "description": "Pass the beat around.",
         "instructions": "1. Warm up\n  - slow tempo\n2. Pass the beat",
         "resources": "- Click here for the lead sheet\n- Try with shakers too"}


def test_format_example_uses_house_structure_and_drops_dead_link_lines():
    t = format_example(ENTRY)
    assert t.startswith("### Rhythm Circle\n**Population:** Older Adults · **Domain:** Musical, Emotional · "
                        "**Method:** Improvisational · **Equipment:** Drums")
    assert "**Instructions**\n1. Warm up" in t
    assert "Try with shakers too" in t and "lead sheet" not in t     # "Click here" lines removed
    two = build_examples_text([ENTRY, {**ENTRY, "id": 2, "title": "Other"}])
    assert "\n\n---\n\n" in two and describe(two).startswith("2 examples")


def test_load_library_rejects_wrong_files():
    assert load_library('[{"id": 1, "title": "x"}]')[0]["id"] == 1
    for bad in ('{"a": 1}', '[1, 2]', "not json"):
        try:
            load_library(bad)
            assert False, bad
        except ValueError:
            pass


def test_render_template_allows_empty_examples_but_not_other_blanks():
    text, unk = render_template("A {{examples}} B {{notes}}", {"examples": "", "notes": ""}, allow_empty=("examples",))
    assert text == "A  B (not specified)" and unk == []


def test_existing_database_is_upgraded_in_place(tmp_path):
    """Simulates the deployed DB: a runs table from before example sets existed, with data in it."""
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at DATETIME NOT NULL, "
                          "user_email VARCHAR(200), model VARCHAR(200), output TEXT)"))
        c.execute(sa.text("INSERT INTO runs (created_at, user_email, model, output) "
                          "VALUES ('2026-10-28 12:00:00', 'a@b.c', 'x/y', 'old output')"))
    db.init_db(eng)
    cols = {c["name"] for c in sa.inspect(eng).get_columns("runs")}
    assert {"example_set_id", "examples_text", "rating", "cost_usd"} <= cols
    old = db.fetch_runs(eng)[0]
    assert old["output"] == "old output" and old["example_set_id"] is None
    db.init_db(eng)                                              # idempotent
    set_id = db.save_example_set("s", "### T\nbody", "a@b.c", eng)
    assert db.list_example_sets(eng)[0]["id"] == set_id


def _fake_factory(calls):
    def fake(model, system, user, temperature, max_tokens, client=None):
        calls.append({"system": system, "user": user})
        return {"output": "ok", "error": None, "tokens_in": 1, "tokens_out": 1, "cost_usd": 0.0, "latency_ms": 1}
    return fake


def test_playground_sends_selected_examples_and_logs_them(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'p.db'}"
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("DATABASE_URL", url)
    eng = sa.create_engine(url)
    db.init_db(eng)
    set_id = db.save_example_set("Default 6", "### UNIQUE-EXAMPLE-MARKER\nbody", "a@b.c", eng)

    calls = []
    with patch("lib.llm.run_model", _fake_factory(calls)):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        assert not at.exception, at.exception
        at.button[[b.label for b in at.button].index("Generate")].click().run()
        assert not at.exception, at.exception
    assert "UNIQUE-EXAMPLE-MARKER" in calls[0]["system"]          # filled into the system prompt slot
    assert "{{examples}}" not in calls[0]["system"]
    run = db.fetch_runs(sa.create_engine(url))[0]
    assert run["example_set_id"] == set_id and "UNIQUE-EXAMPLE-MARKER" in run["examples_text"]
    assert "{{examples}}" in run["system_prompt"]                  # prompt logged as the template, not expanded


def test_playground_warns_when_prompt_has_no_examples_slot(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'w.db'}"
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("DATABASE_URL", url)
    eng = sa.create_engine(url)
    db.init_db(eng)
    db.save_example_set("S", "### T\nbody", "a@b.c", eng)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    prompt_select = next(s for s in at.selectbox if s.label == "Prompt version")
    baseline = next(v["id"] for v in db.list_prompt_versions(eng) if v["name"] == "v1 - baseline")
    prompt_select.select(baseline).run()
    assert any("no {{examples}} placeholder" in w.value for w in at.warning)


def test_examples_page_saves_a_new_set(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'e.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = sa.create_engine(url)
    db.init_db(eng)
    at = AppTest.from_file(str(ROOT / "views/examples.py"), default_timeout=30)
    at.session_state["user"] = "a@b.c"
    at.run()
    assert not at.exception, at.exception
    next(t for t in at.text_area if t.key.startswith("edit_text_")).input("### My example\nsteps").run()
    at.text_input(key="edit_name").input("My set").run()
    at.button(key="edit_save").click().run()
    assert not at.exception, at.exception
    saved = db.list_example_sets(eng)
    assert saved[0]["name"] == "My set" and saved[0]["content"].startswith("### My example")


def test_library_cleaner_keeps_nested_list_indentation():
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_library import convert
    text, links = convert('<ol>\n \t<li>Warm up\n<ul>\n \t<li>slow tempo</li>\n</ul>\n</li>\n \t<li>Pass the <a href="https://x.y">beat</a></li>\n</ol>')
    assert text == "1. Warm up\n  - slow tempo\n2. Pass the beat"
    assert links == [{"text": "beat", "url": "https://x.y"}]
