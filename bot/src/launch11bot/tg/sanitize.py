"""LLM markdown -> Telegram HTML, vendored from Avicenna (md_to_telegram_html).

Order is critical: html.escape FIRST (raw '<' breaks the Telegram HTML parser),
then markdown -> HTML. Never truncate HTML with a slice — split by lines.
Reference rule: ~/.claude/rules/llm-output-formatting.md
"""
from __future__ import annotations

import html
import re

TG_LIMIT = 4096


def md_to_telegram_html(text: str) -> str:
    text = html.escape(text)  # & < > (and quotes) — MUST be first
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # markdown headings -> bold line
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*(.+?)\s*$", r"<b>\1</b>", text)
    # list bullets - or * -> •
    text = re.sub(r"(?m)^(\s*)[-*]\s+", r"\1• ", text)
    # *italic* (single star, not part of **)
    text = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)\*(?!\*)", r"<i>\1</i>", text)
    # _italic_
    text = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)
    # `code`
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)
    return text


def _split_long_line(line: str, limit: int) -> list[str]:
    """Split a single over-limit line into <=limit pieces, avoiding cuts inside a <...> tag."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        end = min(i + limit, n)
        if end < n:
            lt = line.rfind("<", i, end)
            gt = line.rfind(">", i, end)
            if lt > gt and lt > i:  # window ends inside an unclosed tag -> back off
                end = lt
        out.append(line[i:end])
        i = end
    return out


def chunk_html(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Split HTML into <=limit chunks on line boundaries; never split a tag.

    Over-long single lines are split tag-safely at the character level.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        segments = _split_long_line(line, limit) if len(line) > limit else [line]
        for seg in segments:
            add = seg if not buf else "\n" + seg
            if len(buf) + len(add) <= limit:
                buf += add
            else:
                if buf:
                    chunks.append(buf)
                buf = seg
    if buf:
        chunks.append(buf)
    return chunks or [""]
