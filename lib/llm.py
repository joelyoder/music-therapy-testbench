import re
import time

from openai import OpenAI

from lib.config import secret

OPENROUTER_URL = "https://openrouter.ai/api/v1"
VARIABLE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_template(template: str, values: dict, allow_empty=()) -> tuple[str, list[str]]:
    """Fill {{var}} placeholders. Returns (text, unknown_variable_names).

    Blank values become "(not specified)" unless the variable is listed in allow_empty."""
    unknown = []

    def sub(m):
        key = m.group(1)
        if key in values:
            val = str(values[key]).strip()
            return val if (val or key in allow_empty) else "(not specified)"
        unknown.append(key)
        return m.group(0)

    return VARIABLE_RE.sub(sub, template), unknown


def estimate_cost(tokens_in, tokens_out, price_in, price_out):
    if tokens_in is None or tokens_out is None or price_in is None or price_out is None:
        return None
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def run_model(model: dict, system: str, user: str, temperature: float, max_tokens: int, client=None) -> dict:
    """Call one model via OpenRouter. Never raises; errors come back in 'error'."""
    start = time.perf_counter()
    try:
        client = client or OpenAI(
            base_url=OPENROUTER_URL, api_key=secret("openrouter_api_key"), timeout=120,
            default_headers={"X-Title": "Music Therapy Test Bench"})
        resp = client.chat.completions.create(
            model=model["id"],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens,
            extra_body={"usage": {"include": True}},  # asks OpenRouter to report actual cost
        )
        latency = int((time.perf_counter() - start) * 1000)
        usage = resp.usage
        tin = getattr(usage, "prompt_tokens", None)
        tout = getattr(usage, "completion_tokens", None)
        cost = getattr(usage, "cost", None)
        if cost is None and getattr(usage, "model_extra", None):
            cost = usage.model_extra.get("cost")
        if cost is None:
            cost = estimate_cost(tin, tout, model.get("in"), model.get("out"))
        return {"output": resp.choices[0].message.content or "", "error": None,
                "tokens_in": tin, "tokens_out": tout, "cost_usd": cost, "latency_ms": latency}
    except Exception as e:  # noqa: BLE001 - surface any provider error to the UI
        return {"output": "", "error": f"{type(e).__name__}: {e}", "tokens_in": None,
                "tokens_out": None, "cost_usd": None,
                "latency_ms": int((time.perf_counter() - start) * 1000)}
