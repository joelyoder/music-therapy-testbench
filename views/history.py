import json

import pandas as pd
import streamlit as st

from lib import db

st.title("Run History")
rows = db.fetch_runs()
if not rows:
    st.info("No runs yet. Generate something in the Playground.")
    st.stop()

versions = {v["id"]: f'#{v["id"]} {v["name"]}' for v in db.list_prompt_versions()}
df = pd.DataFrame(rows)
df["prompt"] = df["prompt_version_id"].map(versions).fillna("(edited, unsaved)")

c1, c2, c3, c4 = st.columns(4)
f_model = c1.multiselect("Model", sorted(df["model"].dropna().unique()))
f_prompt = c2.multiselect("Prompt version", sorted(df["prompt"].unique()))
f_user = c3.multiselect("User", sorted(df["user_email"].dropna().unique()))
f_rating = c4.selectbox("Rating", ["any", "rated only", "4+", "<= 2"])

if f_model: df = df[df["model"].isin(f_model)]
if f_prompt: df = df[df["prompt"].isin(f_prompt)]
if f_user: df = df[df["user_email"].isin(f_user)]
if f_rating == "rated only": df = df[df["rating"].notna()]
elif f_rating == "4+": df = df[df["rating"] >= 4]
elif f_rating == "<= 2": df = df[df["rating"] <= 2]

# Summary per model x prompt: this is the cost-vs-quality table
st.subheader("Summary by model and prompt")
if len(df):
    summary = (df.groupby(["model", "prompt"], dropna=False)
                 .agg(runs=("id", "count"), avg_rating=("rating", "mean"), rated=("rating", "count"),
                      avg_cost_usd=("cost_usd", "mean"), avg_latency_s=("latency_ms", lambda s: s.mean() / 1000))
                 .round(4).reset_index())
    st.dataframe(summary, use_container_width=True, hide_index=True)

st.subheader("All runs")
show = df[["id", "created_at", "user_email", "model", "prompt", "rating", "cost_usd", "latency_ms", "notes"]]
st.dataframe(show, use_container_width=True, hide_index=True)
st.download_button("Download filtered runs (CSV)", df.drop(columns=["prompt"]).to_csv(index=False),
                   "runs.csv", "text/csv")

if len(df):
    rid = st.selectbox("Inspect a run", df["id"].tolist())
    r = df[df["id"] == rid].iloc[0]
    st.markdown(f"**{r['model']}** · {r['prompt']} · rating: {r['rating']} · notes: {r['notes'] or '-'}")
    if r["error"]:
        st.error(r["error"])
    t1, t2, t3 = st.tabs(["Output", "Message sent", "System prompt"])
    t1.markdown(r["output"] or "")
    t2.code(r["rendered_user_prompt"] or "", language="markdown")
    t3.code(r["system_prompt"] or "", language="markdown")
