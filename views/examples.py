import streamlit as st

from lib import db
from lib.library import DEFAULT_EXAMPLE_IDS, build_examples_text, describe, load_library

user = st.session_state["user"]

st.title("Example Sets")
st.caption(
    "Examples teach the model your structure, tone, and level of detail. A prompt includes them wherever it "
    "contains the `{{examples}}` placeholder. Build a new set whenever you want to try different ones, then "
    "pick it in the Playground and compare results in History.")

sets = db.list_example_sets()

tab_view, tab_build, tab_edit = st.tabs(["Saved sets", "Build from library", "Paste or edit text"])

# ---------------- Saved sets ----------------
with tab_view:
    if not sets:
        st.info("No example sets yet. Use the \"Build from library\" tab to create your first one.")
    for s in sets:
        with st.expander(f'#{s["id"]} {s["name"]}  ·  {describe(s["content"])}'):
            st.caption(f'Created by {s["created_by"] or "unknown"}')
            st.text_area("Content", s["content"], height=300, disabled=True, key=f"view_{s['id']}",
                         label_visibility="collapsed")

# ---------------- Build from the library export ----------------
with tab_build:
    st.write("Upload the cleaned `library.json`, then choose which entries become examples. "
             "The file is read in your browser session only; it is not stored. Only the entries you choose are saved.")
    up = st.file_uploader("library.json", type=["json"])
    if up:
        try:
            library = load_library(up.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"Couldn't read that file: {e}")
            library = []
        if library:
            by_id = {r["id"]: r for r in library}
            label = lambda i: f'{by_id[i]["title"]}  ·  {", ".join(by_id[i]["population"][:2]) or "-"}  ·  {", ".join(by_id[i]["method"]) or "-"}'
            picked = st.multiselect(
                "Entries to include (type to search)", list(by_id),
                default=[i for i in DEFAULT_EXAMPLE_IDS if i in by_id], format_func=label)
            if picked:
                text = build_examples_text([by_id[i] for i in picked])
                st.caption(describe(text))
                with st.expander("Preview"):
                    st.code(text, language="markdown")
                name = st.text_input("Name for this set", placeholder="e.g. Default 6 - mixed methods", key="build_name")
                if st.button("Save example set", disabled=not name.strip(), type="primary", key="build_save"):
                    new_id = db.save_example_set(name.strip(), text, user)
                    st.success(f"Saved as set #{new_id}. Select it in the Playground.")
                    st.rerun()

# ---------------- Paste or edit ----------------
with tab_edit:
    st.write("Write or paste examples directly, or start from an existing set and edit it. "
             "Start each example with a `### Title` line so the size summary counts them.")
    base = st.selectbox("Start from", [None] + [s["id"] for s in sets], key="edit_base",
                        format_func=lambda i: "Blank" if i is None else next(f'#{s["id"]} {s["name"]}' for s in sets if s["id"] == i))
    initial = "" if base is None else next(s["content"] for s in sets if s["id"] == base)
    text = st.text_area("Examples text", initial, height=350, key=f"edit_text_{base}")
    if text.strip():
        st.caption(describe(text))
    name = st.text_input("Name for this set", key="edit_name", placeholder="e.g. Default 6, minus Cha Cha Cha")
    if st.button("Save as new example set", disabled=not (name.strip() and text.strip()), type="primary", key="edit_save"):
        new_id = db.save_example_set(name.strip(), text.strip(), user)
        st.success(f"Saved as set #{new_id}. Select it in the Playground.")
        st.rerun()
