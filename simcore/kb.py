"""Penyaji dokumen SOP fiktif (folder kb/) untuk workflow ingest di n8n."""
from __future__ import annotations

import os
import re

KB_DIR = os.getenv("KB_DIR", os.path.join(os.path.dirname(__file__), "..", "kb"))


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.*)", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _doc_id(filename: str) -> str:
    """'SOP-OPS-01_trip-penghantar-150kv.md' -> 'SOP-OPS-01'"""
    return filename.rsplit(".", 1)[0].split("_", 1)[0]


def list_docs(with_content: bool = True) -> list[dict]:
    out = []
    if not os.path.isdir(KB_DIR):
        return out
    for fn in sorted(os.listdir(KB_DIR)):
        if not fn.lower().endswith(".md"):
            continue
        with open(os.path.join(KB_DIR, fn), encoding="utf-8") as f:
            text = f.read()
        item = {"doc_id": _doc_id(fn), "judul": _title(text, fn), "file": fn, "karakter": len(text)}
        if with_content:
            item["isi"] = text
        out.append(item)
    return out


def get_doc(doc_id: str) -> dict | None:
    for d in list_docs(True):
        if d["doc_id"].lower() == doc_id.lower():
            return d
    return None
