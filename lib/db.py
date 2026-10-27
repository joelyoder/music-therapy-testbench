import json
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
import streamlit as st

from lib.config import ROOT, secret

metadata = sa.MetaData()

prompt_versions = sa.Table(
    "prompt_versions", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("system_prompt", sa.Text, nullable=False),
    sa.Column("user_template", sa.Text, nullable=False),
    sa.Column("created_by", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

runs = sa.Table(
    "runs", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("user_email", sa.String(200)),
    sa.Column("compare_group", sa.String(40)),
    sa.Column("prompt_version_id", sa.Integer),  # null if the prompt was edited and not saved
    sa.Column("system_prompt", sa.Text),         # exact snapshot used
    sa.Column("user_template", sa.Text),
    sa.Column("inputs_json", sa.Text),
    sa.Column("rendered_user_prompt", sa.Text),
    sa.Column("model", sa.String(200)),
    sa.Column("temperature", sa.Float),
    sa.Column("max_tokens", sa.Integer),
    sa.Column("output", sa.Text),
    sa.Column("error", sa.Text),
    sa.Column("tokens_in", sa.Integer),
    sa.Column("tokens_out", sa.Integer),
    sa.Column("cost_usd", sa.Float),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("rating", sa.Integer),
    sa.Column("notes", sa.Text),
)

DEFAULT_SYSTEM = """You are an experienced board-certified music therapist and clinical supervisor helping a fellow music therapist plan sessions.

Generate practical, evidence-informed session ideas. For each idea include: a title, therapeutic goals, materials, step-by-step procedure with approximate timing, adaptations for different ability levels, and how to observe/measure progress.

Rules:
- Never ask for or include client names or identifying details.
- Keep ideas realistic for the stated setting and time.
- Prefer clear, scannable formatting (headings and short lists)."""

DEFAULT_TEMPLATE = """Please suggest {{num_ideas}} session ideas.

Population / client group: {{population}}
Goals: {{goals}}
Session length: {{session_length}}
Setting: {{setting}}
Additional notes: {{notes}}"""


def _now():
    return datetime.now(timezone.utc)


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@st.cache_resource
def get_engine():
    url = secret("database_url") or f"sqlite:///{ROOT / 'testbench.db'}"
    engine = sa.create_engine(_normalize_url(url), pool_pre_ping=True)
    init_db(engine)
    return engine


def init_db(engine):
    metadata.create_all(engine)
    with engine.begin() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(prompt_versions)).scalar()
        if n == 0:
            c.execute(sa.insert(prompt_versions).values(
                name="v1 - baseline", system_prompt=DEFAULT_SYSTEM, user_template=DEFAULT_TEMPLATE,
                created_by="system", created_at=_now()))


def list_prompt_versions(engine=None):
    engine = engine or get_engine()
    with engine.connect() as c:
        rows = c.execute(sa.select(prompt_versions).order_by(prompt_versions.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]


def save_prompt_version(name, system_prompt, user_template, user, engine=None) -> int:
    engine = engine or get_engine()
    with engine.begin() as c:
        res = c.execute(sa.insert(prompt_versions).values(
            name=name, system_prompt=system_prompt, user_template=user_template,
            created_by=user, created_at=_now()))
        return res.inserted_primary_key[0]


def insert_run(data: dict, engine=None) -> int:
    engine = engine or get_engine()
    data = {**data, "created_at": _now()}
    if isinstance(data.get("inputs_json"), dict):
        data["inputs_json"] = json.dumps(data["inputs_json"])
    with engine.begin() as c:
        return c.execute(sa.insert(runs).values(**data)).inserted_primary_key[0]


def update_feedback(run_id: int, rating, notes, engine=None):
    engine = engine or get_engine()
    with engine.begin() as c:
        c.execute(sa.update(runs).where(runs.c.id == run_id).values(rating=rating, notes=notes))


def count_runs_today(user, engine=None) -> int:
    engine = engine or get_engine()
    since = _now() - timedelta(hours=24)
    with engine.connect() as c:
        return c.execute(
            sa.select(sa.func.count()).select_from(runs)
            .where(runs.c.user_email == user, runs.c.created_at >= since)).scalar()


def fetch_runs(engine=None):
    engine = engine or get_engine()
    with engine.connect() as c:
        rows = c.execute(sa.select(runs).order_by(runs.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]
