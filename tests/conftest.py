import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def fresh_engine_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()
