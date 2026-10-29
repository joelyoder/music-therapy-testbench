"""Turn a WordPress export (XML) of 'intervention' posts into a clean library.json.

Usage: python -I scripts/build_library.py EXPORT.xml [OUT_DIR]
Writes OUT_DIR/library.json (structured) and OUT_DIR/library_compact.txt (prompt-ready text).
Only published posts are kept. WordPress/plugin metadata and authors are dropped.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

NS = {"wp": "http://wordpress.org/export/1.2/"}
SONG_HOSTS = ("youtube.com", "youtu.be", "open.spotify.com", "spotify.com", "music.apple.com")


class HtmlToText(HTMLParser):
    """Small HTML -> plain-text converter that keeps list structure and collects links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.links = [], []
        self.stack = []        # list contexts: ["ol", counter] / ["ul", None]
        self.href = None
        self.href_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("ol", "ul"):
            self.stack.append([tag, 0])
        elif tag == "li":
            depth = max(len(self.stack) - 1, 0)
            if self.stack and self.stack[-1][0] == "ol":
                self.stack[-1][1] += 1
                marker = f"{self.stack[-1][1]}."
            else:
                marker = "-"
            self.out.append("\n" + "  " * depth + marker + " ")
        elif tag in ("br", "p", "div"):
            self.out.append("\n")
        elif tag == "a":
            self.href, self.href_text = dict(attrs).get("href"), []

    def handle_endtag(self, tag):
        if tag in ("ol", "ul") and self.stack:
            self.stack.pop()
            self.out.append("\n")
        elif tag == "a" and self.href:
            self.links.append({"text": re.sub(r"\s+", " ", "".join(self.href_text)).strip(), "url": self.href})
            self.href = None

    def handle_data(self, data):
        self.out.append(data)
        if self.href is not None:
            self.href_text.append(data)

    def result(self):
        text = "".join(self.out).replace("\xa0", " ")
        # collapse repeated spaces inside a line but keep its leading indentation (nested lists)
        lines = [" " * (len(l) - len(l.lstrip(" "))) + re.sub(r"[ \t]+", " ", l.strip()) for l in text.splitlines()]
        text = "\n".join(l for l in lines if l.strip())
        return text.strip()


def convert(html_text):
    p = HtmlToText()
    p.feed(html_text or "")
    return p.result(), p.links


def main(xml_path, out_dir="data"):
    items = ET.parse(xml_path).getroot().findall("./channel/item")
    records, skipped = [], {"not_published": 0}
    repeater_keys = set()
    for it in items:
        if it.findtext("wp:post_type", namespaces=NS) != "intervention":
            continue
        if it.findtext("wp:status", namespaces=NS) != "publish":
            skipped["not_published"] += 1
            continue
        meta = {}
        for m in it.findall("wp:postmeta", NS):
            k = m.findtext("wp:meta_key", namespaces=NS)
            meta[k] = m.findtext("wp:meta_value", namespaces=NS) or ""
            if k.startswith("video_repeater_") or k.startswith("_video_repeater_"):
                repeater_keys.add(k)
        tax = {"population": [], "domain": [], "method": [], "equipment": []}
        for c in it.findall("category"):
            if c.get("domain") in tax:
                tax[c.get("domain")].append((c.text or "").strip())
        desc, _ = convert(meta.get("description"))
        instr, _ = convert(meta.get("instructions"))
        res_text, res_links = convert(meta.get("resources"))

        urls = [u.strip() for u in [meta.get("video", "")] if u.strip()]
        for k, v in meta.items():  # repeater sub-fields, if the export has them
            if re.fullmatch(r"video_repeater_\d+_\w*(video|url|link)\w*", k) and v.strip().startswith("http"):
                urls.append(v.strip())
        videos = [{"url": u, "host": urlparse(u).netloc.removeprefix("www."),
                   "kind": "song_reference" if urlparse(u).netloc.removeprefix("www.").endswith(SONG_HOSTS) else "demo"}
                  for u in dict.fromkeys(urls)]

        records.append({
            "id": int(it.findtext("wp:post_id", namespaces=NS)),
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            **tax,
            "kind": meta.get("type", "").strip(),          # 'idea' / 'jam-along' / ''
            "description": desc,
            "instructions": instr,
            "resources": res_text,
            "resource_links": [l for l in res_links if l["url"].startswith("http")],
            "videos": videos,
        })
    records.sort(key=lambda r: r["id"])

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "library.json").write_text(json.dumps(records, ensure_ascii=False, indent=1))
    (out / "library_compact.txt").write_text("\n\n".join(compact(r) for r in records))
    print(f"kept {len(records)} interventions; skipped {skipped}; repeater keys seen: {sorted(repeater_keys)[:6]}")


def compact(r):
    tags = "; ".join(f"{k}: {', '.join(r[k])}" for k in ("population", "domain", "method", "equipment") if r[k])
    parts = [f"## [{r['id']}] {r['title']}", tags]
    if r["description"]:
        parts.append(r["description"])
    if r["instructions"]:
        parts.append("Instructions:\n" + r["instructions"])
    if r["resources"]:
        parts.append("Notes/resources:\n" + r["resources"])
    songs = [v["url"] for v in r["videos"] if v["kind"] == "song_reference"]
    if songs:
        parts.append("Song reference: " + ", ".join(songs))
    return "\n".join(parts)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data")
