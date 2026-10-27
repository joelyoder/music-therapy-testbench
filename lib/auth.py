import hmac
import os

import streamlit as st

from lib.config import secret


def _auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _allowed_emails() -> set[str]:
    raw = secret("allowed_emails", []) or []
    if isinstance(raw, str):
        raw = [e for e in raw.split(",")]
    return {e.strip().lower() for e in raw if e.strip()}


def require_login() -> str:
    """Gate the whole app. Returns the user's identifier, or stops the script.

    Fails closed: if nothing is configured, nobody gets in (except DEV_MODE=1 locally).
    """
    if os.getenv("DEV_MODE") == "1":
        return "dev@local"

    # Option 1: Google sign-in + email allowlist
    if _auth_configured():
        if not st.user.is_logged_in:
            st.title("Music Therapy Test Bench")
            st.write("Team members only. Sign in with your Google account.")
            st.button("Sign in with Google", on_click=st.login, type="primary")
            st.stop()
        email = (st.user.get("email") or "").lower()
        verified = st.user.get("email_verified", True)
        if not email or not verified or email not in _allowed_emails():
            st.error(f"{email or 'This account'} is not on the access list. Ask the admin to add it.")
            st.button("Sign out", on_click=st.logout)
            st.stop()
        return email

    # Option 2: shared password
    pw = secret("app_password")
    if pw:
        if st.session_state.get("_authed"):
            return "shared-password-user"
        st.title("Music Therapy Test Bench")
        entered = st.text_input("Password", type="password")
        if entered:
            if hmac.compare_digest(str(entered), str(pw)):
                st.session_state["_authed"] = True
                st.rerun()
            else:
                st.error("Wrong password.")
        st.stop()

    st.error("Login is not configured. Set up Google sign-in or app_password in secrets (see README).")
    st.stop()
