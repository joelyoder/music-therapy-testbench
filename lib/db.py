import hashlib
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

example_sets = sa.Table(
    "example_sets", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("content", sa.Text, nullable=False),
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
    sa.Column("example_set_id", sa.Integer),     # null = no examples used
    sa.Column("examples_text", sa.Text),         # exact examples text sent (snapshot)
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


V2_NAME = "v2 - house style with examples"
V2_SYSTEM = """You are an experienced board-certified music therapist and clinical supervisor helping a fellow music therapist plan sessions.

Write session ideas in the house style of the examples below: practical, warm, concrete, and specific enough that a clinician can run the session without further research. Match the examples' structure, tone, and level of detail.

Format every idea exactly like this:

### <Title>
**Population:** ... · **Domain:** ... · **Method:** ... · **Equipment:** ...

<1-3 sentences: what the experience is and why it works.>

**Instructions**
1. Numbered steps a clinician can follow, in order.
   - Indented bullets for adaptations, variations, or what to watch for.

**Notes / resources** (optional): song ideas, variations, or printable suggestions.

Use these terms for the tags. Method: Receptive, Re-creative, Improvisational, or Compositional. Domain: Communicative, Cognitive, Musical, Emotional, Sensorimotor, Psychosocial, or Physiological.

Rules:
- The examples show style only. Do NOT reuse their ideas, titles, or songs; create new ideas for the requested population and goals.
- Never ask for or include client names or identifying details.
- Keep ideas realistic for the stated setting and session length.
- Do not refer to videos, handouts, named instructors, or other materials you cannot provide.

<examples>
{{examples}}
</examples>"""


def _now():
    return datetime.now(timezone.utc)


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _fingerprint() -> str:
    """Changes whenever a table or column is added/removed, so a cached engine from older code is not reused."""
    spec = ";".join(f"{t.name}:{','.join(c.name for c in t.columns)}" for t in metadata.sorted_tables)
    return hashlib.md5(spec.encode()).hexdigest()


@st.cache_resource
def _engine_for(url: str, fingerprint: str):
    # `fingerprint` is part of the cache key. Streamlit keeps cached resources alive across redeploys, so without it
    # an engine created by older code would be reused and init_db (which creates/upgrades tables) would never rerun.
    engine = sa.create_engine(_normalize_url(url), pool_pre_ping=True)
    init_db(engine)
    return engine


def get_engine():
    url = secret("database_url") or f"sqlite:///{ROOT / 'testbench.db'}"
    return _engine_for(url, _fingerprint())


def _add_missing_columns(engine, table):
    """create_all never alters existing tables, so add any columns an older deploy lacks."""
    existing = {c["name"] for c in sa.inspect(engine).get_columns(table.name)}
    with engine.begin() as c:
        for col in table.columns:
            if col.name not in existing:
                ctype = col.type.compile(dialect=engine.dialect)
                c.execute(sa.text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ctype}'))


def init_db(engine):
    metadata.create_all(engine)
    _add_missing_columns(engine, runs)
    with engine.begin() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(prompt_versions)).scalar()
        if n == 0:
            c.execute(sa.insert(prompt_versions).values(
                name="v1 - baseline", system_prompt=DEFAULT_SYSTEM, user_template=DEFAULT_TEMPLATE,
                created_by="system", created_at=_now()))
        has_v2 = c.execute(sa.select(sa.func.count()).select_from(prompt_versions)
                           .where(prompt_versions.c.name == V2_NAME)).scalar()
        if not has_v2:
            c.execute(sa.insert(prompt_versions).values(
                name=V2_NAME, system_prompt=V2_SYSTEM, user_template=DEFAULT_TEMPLATE,
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


def list_example_sets(engine=None):
    engine = engine or get_engine()
    with engine.connect() as c:
        rows = c.execute(sa.select(example_sets).order_by(example_sets.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]


def save_example_set(name, content, user, engine=None) -> int:
    engine = engine or get_engine()
    with engine.begin() as c:
        res = c.execute(sa.insert(example_sets).values(
            name=name, content=content, created_by=user, created_at=_now()))
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
