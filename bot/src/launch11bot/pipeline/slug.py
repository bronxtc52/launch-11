"""Shared slug helper (used by orchestrator and billing — no cross-module private imports)."""
from __future__ import annotations

import re


def slugify(text: str) -> str:
    # keep unicode letters/digits (Cyrillic included) so the idea survives in the filename
    s = re.sub(r"[^\w]+", "-", (text or "").lower().strip(), flags=re.UNICODE).strip("-_")
    return s[:40] or "product"
