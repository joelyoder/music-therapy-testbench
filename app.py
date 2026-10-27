import streamlit as st

from lib.auth import require_login

st.set_page_config(page_title="Music Therapy Test Bench", page_icon="🎵", layout="wide")

user = require_login()
st.session_state["user"] = user

with st.sidebar:
    st.caption(f"Signed in as {user}")
    if user not in ("dev@local", "shared-password-user"):
        st.button("Sign out", on_click=st.logout)

pg = st.navigation([
    st.Page("views/playground.py", title="Playground", icon="🧪", default=True),
    st.Page("views/history.py", title="History", icon="📜"),
])
pg.run()
