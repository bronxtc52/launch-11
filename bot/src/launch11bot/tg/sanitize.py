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


_TAG_RE = re.compile(r"</?([a-zA-Z0-9]+)[^>]*>")
_BALANCE_RESERVE = 48  # headroom for reopened/closed tags added by _balance_tags


def _balance_tags(chunks: list[str]) -> list[str]:
    """Ensure each chunk is valid standalone HTML: close tags left open at a chunk
    boundary and reopen them at the next chunk (Telegram rejects unbalanced tags)."""
    out: list[str] = []
    carry: list[str] = []  # tags still open, carried from the previous chunk
    for ch in chunks:
        body = "".join(f"<{t}>" for t in carry) + ch
        stack: list[str] = []
        for m in _TAG_RE.finditer(body):
            tag = m.group(1).lower()
            if m.group(0).startswith("</"):
                if tag in stack:
                    stack.reverse()
                    stack.remove(tag)
                    stack.reverse()
            else:
                stack.append(tag)
        out.append(body + "".join(f"</{t}>" for t in reversed(stack)))
        carry = list(stack)
    return out


def chunk_html(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Split HTML into <=limit chunks on line boundaries; never split a tag, and
    keep paired tags (<b>…</b>) balanced within each chunk even across an
    over-long single line."""
    if len(text) <= limit:
        return [text]
    work = max(64, limit - _BALANCE_RESERVE)  # leave room for balancing tags
    chunks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        segments = _split_long_line(line, work) if len(line) > work else [line]
        for seg in segments:
            add = seg if not buf else "\n" + seg
            if len(buf) + len(add) <= work:
                buf += add
            else:
                if buf:
                    chunks.append(buf)
                buf = seg
    if buf:
        chunks.append(buf)
    return _balance_tags(chunks or [""])
