import math
import re

import pandas as pd
import streamlit as st

from lib import db
from lib.config import secret

TZ = secret("display_timezone", "America/New_York")
PAGE_SIZES = [10, 25, 50]
COLS = [0.7, 1.3, 1.4, 2.0, 2.1, 0.9, 1.0, 0.9, 1.8, 1.1]  # id, when, user, model, prompt+examples, rating, cost, time, preview, button  # id, when, user, model, prompt, rating, cost, time, preview, button

st.title("Run History")
rows = db.fetch_runs()
if not rows:
    st.info("No runs yet. Generate something in the Playground.")
    st.stop()


def preview(text: str, n: int = 70) -> str:
    """One plain line from model output: no markdown headings/emphasis, and $ escaped so it isn't read as math."""
    flat = re.sub(r"[#*_`>\[\]]", "", text).replace("$", r"\$")
    flat = re.sub(r"\s+", " ", flat).strip()
    return flat[:n] + ("…" if len(flat) > n else "")


def clean(v):
    """pandas turns missing values into NaN; treat them as empty."""
    return None if pd.isna(v) else v


versions = {v["id"]: f'#{v["id"]} {v["name"]}' for v in db.list_prompt_versions()}
df = pd.DataFrame(rows)
df["prompt"] = df["prompt_version_id"].map(versions).fillna("(edited, unsaved)")
set_names = {x["id"]: f'#{x["id"]} {x["name"]}' for x in db.list_example_sets()}
df["examples"] = df["example_set_id"].map(set_names).fillna("none")

# ---------------- Filters ----------------
c1, c2, c3, c4, c5 = st.columns(5)
f_model = c1.multiselect("Model", sorted(df["model"].dropna().unique()))
f_prompt = c2.multiselect("Prompt version", sorted(df["prompt"].unique()))
f_examples = c3.multiselect("Example set", sorted(df["examples"].unique()))
f_user = c4.multiselect("User", sorted(df["user_email"].dropna().unique()))
f_rating = c5.selectbox("Rating", ["any", "rated only", "4+", "<= 2"])

if f_model: df = df[df["model"].isin(f_model)]
if f_prompt: df = df[df["prompt"].isin(f_prompt)]
if f_examples: df = df[df["examples"].isin(f_examples)]
if f_user: df = df[df["user_email"].isin(f_user)]
if f_rating == "rated only": df = df[df["rating"].notna()]
elif f_rating == "4+": df = df[df["rating"] >= 4]
elif f_rating == "<= 2": df = df[df["rating"] <= 2]

tab_runs, tab_summary = st.tabs(["Runs", "Model comparison"])

# ---------------- Model comparison (cost vs quality) ----------------
with tab_summary:
    st.caption("Averages over the runs that match the filters above. Rate runs in the Playground to fill in the rating columns.")
    if df.empty:
        st.info("No runs match these filters.")
    else:
        summary = (df.groupby(["model", "prompt", "examples"], dropna=False)
                     .agg(runs=("id", "count"), rated=("rating", "count"), avg_rating=("rating", "mean"),
                          avg_cost=("cost_usd", "mean"), avg_time=("latency_ms", lambda s: s.mean() / 1000))
                     .reset_index()
                     .sort_values(["avg_rating", "runs"], ascending=[False, False], na_position="last"))
        st.dataframe(
            summary, width="stretch", hide_index=True,
            column_order=["model", "prompt", "examples", "runs", "rated", "avg_rating", "avg_cost", "avg_time"],
            column_config={
                "model": st.column_config.TextColumn("Model"),
                "prompt": st.column_config.TextColumn("Prompt version"),
                "examples": st.column_config.TextColumn("Example set"),
                "runs": st.column_config.NumberColumn("Runs", format="%d"),
                "rated": st.column_config.NumberColumn("Rated runs", format="%d",
                                                       help="How many of these runs have a rating"),
                "avg_rating": st.column_config.NumberColumn("Avg rating", format="%.1f ★",
                                                            help="Average of the 1-5 ratings, rated runs only"),
                "avg_cost": st.column_config.NumberColumn("Avg cost / run", format="$%.4f"),
                "avg_time": st.column_config.NumberColumn("Avg response time", format="%.1f s"),
            })


# ---------------- Run preview (pop-up) ----------------
@st.dialog("Run details", width="large")
def show_run(r: dict):
    rating = clean(r["rating"])
    st.markdown(f"**{r['model']}** · {r['prompt']} · rating: {int(rating) if rating is not None else 'unrated'}"
                f" · notes: {clean(r['notes']) or '-'}")
    cost, tin, tout, ms = clean(r["cost_usd"]), clean(r["tokens_in"]), clean(r["tokens_out"]), clean(r["latency_ms"])
    st.caption(f"Run #{r['id']} · {r['when']} · `{r['user_email'] or 'unknown user'}` · "
               f"{int(tin) if tin is not None else '?'} in / {int(tout) if tout is not None else '?'} out tokens · "
               f"{f'{ms / 1000:.1f}s' if ms is not None else 'time n/a'} · "
               + (f"${cost:.4f}" if cost is not None else "cost n/a"))
    if clean(r["error"]):
        st.error(clean(r["error"]))
    t1, t2, t3, t4 = st.tabs(["Output", "Message sent", "System prompt", f"Examples ({r['examples']})"])
    t1.markdown(clean(r["output"]) or "")
    t2.code(clean(r["rendered_user_prompt"]) or "", language="markdown")
    t3.code(clean(r["system_prompt"]) or "", language="markdown")
    t4.code(clean(r["examples_text"]) or "(no examples were sent)", language="markdown")


with tab_runs:
    # ---------------- Table with pagination ----------------
    st.download_button("Download filtered runs (CSV)", df.drop(columns=["prompt"]).to_csv(index=False),
                       "runs.csv", "text/csv")
    if df.empty:
        st.info("No runs match these filters.")
        st.stop()

    df = df.copy()
    df["when"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(TZ).dt.strftime("%b %d, %H:%M")

    pc1, pc2, pc3, pc4 = st.columns([1.2, 1, 3, 1], vertical_alignment="center")
    page_size = pc1.selectbox("Rows per page", PAGE_SIZES, key="hist_page_size")
    total = len(df)
    pages = max(1, math.ceil(total / page_size))

    # go back to page 1 whenever the filters or page size change
    sig = (tuple(f_model), tuple(f_prompt), tuple(f_examples), tuple(f_user), f_rating, page_size)
    if st.session_state.get("hist_sig") != sig:
        st.session_state["hist_sig"] = sig
        st.session_state["hist_page"] = 0
    page = min(st.session_state.get("hist_page", 0), pages - 1)


    def go(delta):
        st.session_state["hist_page"] = min(max(page + delta, 0), pages - 1)


    pc2.button("◀ Prev", on_click=go, args=(-1,), disabled=page == 0, width="stretch")
    pc3.markdown(f"<div style='text-align:center'>Page {page + 1} of {pages} · {total} runs</div>", unsafe_allow_html=True)
    pc4.button("Next ▶", on_click=go, args=(1,), disabled=page >= pages - 1, width="stretch")

    header = st.columns(COLS)
    for col, name in zip(header, ["ID", "When (ET)" if TZ == "America/New_York" else "When", "User", "Model", "Prompt / examples",
                                  "Rating", "Cost", "Time", "Output preview", ""]):
        col.markdown(f"**{name}**")

    for r in df.iloc[page * page_size:(page + 1) * page_size].to_dict("records"):
        c = st.columns(COLS, vertical_alignment="center")
        rating, cost, ms = clean(r["rating"]), clean(r["cost_usd"]), clean(r["latency_ms"])
        out, err = clean(r["output"]) or "", clean(r["error"])
        c[0].write(r["id"])
        c[1].write(r["when"])
        c[2].write((r["user_email"] or "?").split("@")[0])
        c[3].write(r["model"])
        c[4].write(r["prompt"])
        c[4].caption(f'Examples: {r["examples"]}')
        c[5].write(f"{int(rating)} ★" if rating is not None else "—")
        c[6].write(f"${cost:.4f}" if cost is not None else "—")
        c[7].write(f"{ms / 1000:.1f}s" if ms is not None else "—")
        c[8].caption("⚠ error" if err and not out else preview(out))
        if c[9].button("View", key=f"view_{r['id']}", width="stretch"):
            show_run(r)
        st.divider()
