import re
import uuid
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from lib import db
from lib.config import load_models, secret
from lib.library import describe
from lib.llm import VARIABLE_RE, render_template, run_model
from lib.models import fetch_all_models, under_ceiling

user = st.session_state["user"]
models = load_models()
model_by_id = {m["id"]: m for m in models}
MAX_TOKENS_CAP = int(secret("max_tokens_cap", 8000))
DAILY_LIMIT = int(secret("max_runs_per_user_per_day", 100))
PRICE_CEILING = float(secret("max_output_price_per_m", 20))  # USD per 1M output tokens

st.title("Session Idea Playground")

# ---------------- Prompt ----------------
versions = db.list_prompt_versions()
labels = {v["id"]: f'#{v["id"]} {v["name"]}' for v in versions}
with st.expander("1. System prompt & template", expanded=True):
    sel_id = st.selectbox("Prompt version", [v["id"] for v in versions], format_func=labels.get)
    ver = next(v for v in versions if v["id"] == sel_id)
    system_prompt = st.text_area("System prompt", ver["system_prompt"], height=220, key=f"sys_{sel_id}")
    user_template = st.text_area(
        "User message template (variables: {{population}}, {{goals}}, {{session_length}}, {{setting}}, {{notes}}, {{num_ideas}}; {{examples}} also works in the system prompt)",
        ver["user_template"], height=160, key=f"tpl_{sel_id}")
    edited = (system_prompt != ver["system_prompt"]) or (user_template != ver["user_template"])
    if edited:
        st.info("You have unsaved edits. Runs will use your edited text, but save a version to keep it.")
    c1, c2 = st.columns([3, 1])
    new_name = c1.text_input("Name for new version", placeholder="e.g. v2 - shorter, more adaptations")
    if c2.button("Save as new version", disabled=not new_name.strip(), width="stretch"):
        new_id = db.save_prompt_version(new_name.strip(), system_prompt, user_template, user)
        st.success(f"Saved as version #{new_id}. Select it in the dropdown above.")
        st.rerun()

# ---------------- Examples ----------------
example_sets = db.list_example_sets()
set_by_id = {x["id"]: x for x in example_sets}
SLOT_RE = re.compile(r"\{\{\s*examples\s*\}\}")
with st.expander("2. Examples", expanded=True):
    ex_id = st.selectbox(
        "Example set", [None] + [x["id"] for x in example_sets], index=1 if example_sets else 0,
        format_func=lambda i: "None (no examples)" if i is None
        else f'#{i} {set_by_id[i]["name"]}  ·  {describe(set_by_id[i]["content"])}')
    examples_text = set_by_id[ex_id]["content"] if ex_id else ""
    has_slot = bool(SLOT_RE.search(system_prompt + user_template))
    if not example_sets:
        st.caption("No example sets yet. Create one on the Example Sets page.")
    elif ex_id and not has_slot:
        st.warning("This prompt has no {{examples}} placeholder, so the selected examples will NOT be sent. "
                   "Add it to the system prompt, or pick a prompt version that has it.")
    elif has_slot and not ex_id:
        st.info("This prompt has an {{examples}} slot but no set is selected, so it will be empty.")

# ---------------- Inputs ----------------
with st.expander("3. Session inputs", expanded=True):
    c1, c2 = st.columns(2)
    population = c1.text_input("Population / client group", "Adults with early-stage dementia")
    goals = c2.text_input("Goals", "Reminiscence, social engagement, mood")
    c3, c4, c5 = st.columns(3)
    session_length = c3.text_input("Session length", "45 minutes")
    setting = c4.text_input("Setting", "Group session, memory care unit")
    num_ideas = c5.number_input("Number of ideas", 1, 10, 3)
    notes = st.text_area("Additional notes (no client names or identifying details)", "", height=80)

# ---------------- Models ----------------
with st.expander("4. Models & settings", expanded=True):
    chosen = st.multiselect(
        "Starred models (pick up to 4 in total, including any from the list below)",
        [m["id"] for m in models], default=[models[0]["id"]], max_selections=4,
        format_func=lambda i: f'{model_by_id[i]["label"]}  [{i}]')

    all_models, fetch_err = fetch_all_models()
    extra = []
    if fetch_err:
        st.caption(f"Couldn't load the full OpenRouter list ({fetch_err}). Starred models still work.")
    else:
        allow_pricey = st.checkbox(
            f"Include models priced above ${PRICE_CEILING:g} per 1M output tokens (can be expensive)", value=False)
        pool = all_models if allow_pricey else under_ceiling(all_models, PRICE_CEILING)
        pool = [m for m in pool if m["id"] not in model_by_id]
        pool_by_id = {m["id"]: m for m in pool}
        st.caption(f"{len(pool)} more models available. Type to search by name or provider.")
        extra = st.multiselect(
            "More models (all of OpenRouter)", list(pool_by_id), max_selections=max(4 - len(chosen), 0),
            format_func=lambda i: f'{pool_by_id[i]["label"]}  [{i}] - ${pool_by_id[i]["in"]:.2f} in / ${pool_by_id[i]["out"]:.2f} out per 1M')
        for i in extra:
            model_by_id[i] = pool_by_id[i]
        chosen = chosen + extra
    if len(chosen) > 4:
        st.error("Pick at most 4 models in total.")
        chosen = chosen[:4]
    c1, c2 = st.columns(2)
    temperature = c1.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
    max_tokens = c2.number_input("Max output tokens", 100, MAX_TOKENS_CAP, min(3000, MAX_TOKENS_CAP), 100,
                                 help="Upper limit on the response length. If a response ends abruptly, raise this. "
                                      "Thinking-style models also spend part of it on reasoning.")

# ---------------- Run ----------------
values = dict(population=population, goals=goals, session_length=session_length, setting=setting,
              notes=notes, num_ideas=num_ideas, examples=examples_text)
system_rendered, unknown_sys = render_template(system_prompt, values, allow_empty=("examples",))
rendered, unknown_user = render_template(user_template, values, allow_empty=("examples",))
unknown = unknown_sys + unknown_user
if unknown:
    st.warning(f"Prompt uses unknown variables (sent as-is): {', '.join(sorted(set(unknown)))}")
with st.expander("Preview the exact messages that will be sent"):
    t_user, t_sys = st.tabs(["User message", "System prompt (examples filled in)"])
    t_user.code(rendered, language="markdown")
    t_sys.code(system_rendered, language="markdown")

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
                lambda mid: run_model(model_by_id[mid], system_rendered, rendered, temperature, int(max_tokens)),
                chosen))
    ids = []
    for mid, res in zip(chosen, results):
        ids.append(db.insert_run(dict(
            user_email=user, compare_group=group,
            prompt_version_id=None if edited else sel_id,
            system_prompt=system_prompt, user_template=user_template,
            example_set_id=ex_id, examples_text=examples_text or None,
            inputs_json=dict(population=population, goals=goals, session_length=session_length,
                             setting=setting, notes=notes, num_ideas=int(num_ideas)),
            rendered_user_prompt=rendered, model=mid, temperature=temperature, max_tokens=int(max_tokens),
            **res)))
    st.session_state["last_runs"] = [
        {"run_id": i, "model": m, "res": r, "label": model_by_id[m]["label"]}
        for i, m, r in zip(ids, chosen, results)]

# ---------------- Results ----------------
last = st.session_state.get("last_runs")
if last and not all(isinstance(x, dict) for x in last):
    last = st.session_state["last_runs"] = None  # stale format from before a redeploy: drop it, don't crash
if last:
    st.divider()
    st.subheader("Results")
    cols = st.columns(len(last))
    for col, item in zip(cols, last):
        run_id, mid, res, label = item["run_id"], item["model"], item["res"], item["label"]
        with col:
            st.markdown(f"**{label}**  \n`{mid}`")
            if res["error"]:
                st.error(res["error"])
            else:
                if res.get("finish_reason") == "length":
                    st.warning("Cut off: this response hit the Max output tokens limit. "
                               "Raise it under \"4. Models & settings\" and run again.")
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
