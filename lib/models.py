"""Live list of OpenRouter models (public endpoint, no API key needed)."""
import requests
import streamlit as st

URL = "https://openrouter.ai/api/v1/models"

# Variants (the part after ":" in an id) that exist on OpenRouter but can't be called through the
# chat/completions endpoint this app uses. Batch variants are asynchronous jobs, not chat models.
UNSUPPORTED_VARIANTS = {"batch"}


def parse_models(payload: dict) -> list[dict]:
    """Keep text-output models with a fixed price. Prices become USD per 1M tokens."""
    out = []
    for m in payload.get("data", []):
        if str(m.get("id", "")).rpartition(":")[2] in UNSUPPORTED_VARIANTS:
            continue
        try:
            arch = m.get("architecture") or {}
            if "text" not in (arch.get("output_modalities") or ["text"]):
                continue
            pricing = m.get("pricing") or {}
            p_in, p_out = float(pricing["prompt"]), float(pricing["completion"])
        except (KeyError, TypeError, ValueError):
            continue
        if p_in < 0 or p_out < 0:  # negative = variable pricing (auto-routers); skip, cost is unknowable
            continue
        out.append({"id": m["id"], "label": m.get("name") or m["id"],
                    "in": p_in * 1e6, "out": p_out * 1e6, "context": m.get("context_length")})
    return sorted(out, key=lambda x: x["id"])


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch() -> list[dict]:
    r = requests.get(URL, timeout=15)
    r.raise_for_status()
    return parse_models(r.json())  # exceptions are not cached, so a failure retries next time


def fetch_all_models() -> tuple[list[dict], str | None]:
    try:
        return _fetch(), None
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"


def under_ceiling(models: list[dict], max_out_per_m: float | None) -> list[dict]:
    if max_out_per_m is None:
        return models
    return [m for m in models if m["out"] <= max_out_per_m]
