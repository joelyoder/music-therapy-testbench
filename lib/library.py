"""Turn entries from the cleaned library (library.json) into example text for prompts."""
import json
import re

# Default starter set: covers all four methods and most populations.
DEFAULT_EXAMPLE_IDS = [37023, 36826, 37019, 36701, 30396, 37121]

TAG_FIELDS = (("Population", "population"), ("Domain", "domain"), ("Method", "method"), ("Equipment", "equipment"))


def load_library(raw: bytes | str) -> list[dict]:
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(r, dict) and "title" in r and "id" in r for r in data):
        raise ValueError("This doesn't look like library.json (expected a list of entries with id and title).")
    return data


def format_example(r: dict) -> str:
    """One library entry in the same shape we ask the model to produce."""
    lines = [f"### {r['title']}"]
    tags = [f"**{label}:** {', '.join(r[key])}" for label, key in TAG_FIELDS if r.get(key)]
    if tags:
        lines.append(" · ".join(tags))
    if r.get("description"):
        lines += ["", r["description"]]
    if r.get("instructions"):
        lines += ["", "**Instructions**", r["instructions"]]
    # Resource notes are often just "Click here for ..." with the link stripped; drop those lines.
    notes = [l for l in (r.get("resources") or "").splitlines() if l.strip() and not re.search(r"click here|click on", l, re.I)]
    if notes:
        lines += ["", "**Notes / resources**", *notes]
    return "\n".join(lines)


def build_examples_text(entries: list[dict]) -> str:
    return "\n\n---\n\n".join(format_example(r) for r in entries)


def describe(text: str) -> str:
    """Rough size summary for the UI: number of examples and approximate tokens."""
    n = len(re.findall(r"^### ", text, re.M))
    return f"{n} example{'s' if n != 1 else ''} · about {len(text) // 4:,} tokens"
