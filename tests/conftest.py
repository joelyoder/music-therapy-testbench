import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def fresh_engine_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


FAKE_ALL = [
    {"id": "acme/cheap-1", "label": "Acme Cheap", "in": 0.1, "out": 0.4, "context": 8000},
    {"id": "acme/pricey-1", "label": "Acme Pricey", "in": 15.0, "out": 75.0, "context": 8000},
    {"id": "anthropic/claude-haiku-4.5", "label": "dup of starred", "in": 1.0, "out": 5.0, "context": 8000},
]


@pytest.fixture(autouse=True)
def fake_openrouter_list(monkeypatch):
    """Never hit the network in tests."""
    import lib.models
    monkeypatch.setattr(lib.models, "fetch_all_models", lambda: (FAKE_ALL, None))
