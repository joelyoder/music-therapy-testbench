import uuid
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from lib import db
from lib.config import load_models, secret
from lib.llm import VARIABLE_RE, render_template, run_model

user = st.session_state["user"]
models = load_models()
model_by_id = {m["id"]: m for m in models}
MAX_TOKENS_CAP = int(secret("max_tokens_cap", 4000))
DAILY_LIMIT = int(secret("max_runs_per_user_per_day", 100))

st.title("Session Idea Playground")

# ---------------- Prompt ----------------
versions = db.list_prompt_versions()
labels = {v["id"]: f'#{v["id"]} {v["name"]}' for v in versions}
with st.expander("1. System prompt & template", expanded=True):
    sel_id = st.selectbox("Prompt version", [v["id"] for v in versions], format_func=labels.get)
    ver = next(v for v in versions if v["id"] == sel_id)
    system_prompt = st.text_area("System prompt", ver["system_prompt"], height=220, key=f"sys_{sel_id}")
    user_template = st.text_area(
        "User message template (use {{population}}, {{goals}}, {{session_length}}, {{setting}}, {{notes}}, {{num_ideas}})",
        ver["user_template"], height=160, key=f"tpl_{sel_id}")
    edited = (system_prompt != ver["system_prompt"]) or (user_template != ver["user_template"])
    if edited:
        st.info("You have unsaved edits. Runs will use your edited text, but save a version to keep it.")
    c1, c2 = st.columns([3, 1])
    new_name = c1.text_input("Name for new version", placeholder="e.g. v2 - shorter, more adaptations")
    if c2.button("Save as new version", disabled=not new_name.strip(), use_container_width=True):
        new_id = db.save_prompt_version(new_name.strip(), system_prompt, user_template, user)
        st.success(f"Saved as version #{new_id}. Select it in the dropdown above.")
        st.rerun()

# ---------------- Inputs ----------------
with st.expander("2. Session inputs", expanded=True):
    c1, c2 = st.columns(2)
    population = c1.text_input("Population / client group", "Adults with early-stage dementia")
    goals = c2.text_input("Goals", "Reminiscence, social engagement, mood")
    c3, c4, c5 = st.columns(3)
    session_length = c3.text_input("Session length", "45 minutes")
    setting = c4.text_input("Setting", "Group session, memory care unit")
    num_ideas = c5.number_input("Number of ideas", 1, 10, 3)
    notes = st.text_area("Additional notes (no client names or identifying details)", "", height=80)

# ---------------- Models ----------------
with st.expander("3. Models & settings", expanded=True):
    chosen = st.multiselect(
        "Models (pick 1-4; more than one = side-by-side compare)",
        [m["id"] for m in models], default=[models[0]["id"]], max_selections=4,
        format_func=lambda i: f'{model_by_id[i]["label"]}  [{i}]')
    c1, c2 = st.columns(2)
    temperature = c1.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
    max_tokens = c2.number_input("Max output tokens", 100, MAX_TOKENS_CAP, min(1500, MAX_TOKENS_CAP), 100)

# ---------------- Run ----------------
rendered, unknown = render_template(
    user_template, dict(population=population, goals=goals, session_length=session_length,
                        setting=setting, notes=notes, num_ideas=num_ideas))
if unknown:
    st.warning(f"Template uses unknown variables (sent as-is): {', '.join(sorted(set(unknown)))}")
with st.expander("Preview the exact message that will be sent"):
    st.code(rendered, language="markdown")

used = db.count_runs_today(user)
st.caption(f"Runs in the last 24h: {used}/{DAILY_LIMIT}")
go = st.button("Generate", type="primary", disabled=not chosen or used + len(chosen) > DAILY_LIMIT)
if used + len(chosen) > DAILY_LIMIT:
    st.error("Daily run limit reached for your account.")

if go:
    group = uuid.uuid4().hex[:12]
    with st.spinner(f"Running {len(chosen)} model(s)..."):
        with ThreadPoolExecutor(max_workers=len(chosen)) as ex:
            results = list(ex.map(
                lambda mid: run_model(model_by_id[mid], system_prompt, rendered, temperature, int(max_tokens)),
                chosen))
    ids = []
    for mid, res in zip(chosen, results):
        ids.append(db.insert_run(dict(
            user_email=user, compare_group=group,
            prompt_version_id=None if edited else sel_id,
            system_prompt=system_prompt, user_template=user_template,
            inputs_json=dict(population=population, goals=goals, session_length=session_length,
                             setting=setting, notes=notes, num_ideas=int(num_ideas)),
            rendered_user_prompt=rendered, model=mid, temperature=temperature, max_tokens=int(max_tokens),
            **res)))
    st.session_state["last_runs"] = list(zip(ids, chosen, results))

# ---------------- Results ----------------
last = st.session_state.get("last_runs")
if last:
    st.divider()
    st.subheader("Results")
    cols = st.columns(len(last))
    for col, (run_id, mid, res) in zip(cols, last):
        with col:
            st.markdown(f"**{model_by_id[mid]['label']}**")
            if res["error"]:
                st.error(res["error"])
            else:
                st.markdown(res["output"])
            cost = res["cost_usd"]
            st.caption(
                f'{res["tokens_in"] or "?"} in / {res["tokens_out"] or "?"} out tokens · '
                f'{res["latency_ms"] / 1000:.1f}s · ' + (f"${cost:.4f}" if cost is not None else "cost n/a"))
            rating = st.radio("Rating", ["-", 1, 2, 3, 4, 5], horizontal=True, key=f"rate_{run_id}")
            note = st.text_input("Notes", key=f"note_{run_id}")
            if st.button("Save feedback", key=f"save_{run_id}"):
                db.update_feedback(run_id, None if rating == "-" else int(rating), note)
                st.success("Saved")
