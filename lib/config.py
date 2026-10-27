import json
import os
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent


def secret(name: str, default=None):
    """Read from st.secrets, falling back to environment variables."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name.upper(), default)


def load_models() -> list[dict]:
    data = json.loads((ROOT / "models.json").read_text())
    return data["models"]
