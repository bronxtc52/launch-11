"""Criteria 1, 2 — sanitizer and chunking."""
from launch11bot.tg.sanitize import md_to_telegram_html, chunk_html


def test_bold_becomes_b_tag():
    assert "<b>жирный</b>" in md_to_telegram_html("**жирный**")


def test_raw_lt_is_escaped():
    out = md_to_telegram_html("ЛПНП <3,0 это хорошо")
    assert "&lt;3,0" in out
    # no raw unescaped '<' that would break the Telegram HTML parser
    assert "<3" not in out


def test_heading_becomes_bold():
    out = md_to_telegram_html("## Заголовок")
    assert "<b>" in out and "Заголовок" in out


def test_bullets_normalized():
    out = md_to_telegram_html("- пункт один\n- пункт два")
    assert "•" in out


def test_order_escape_before_markdown():
    # ampersand from LLM must be escaped, not left raw
    out = md_to_telegram_html("A & B **bold**")
    assert "&amp;" in out
    assert "<b>bold</b>" in out


def test_chunk_respects_4096_limit():
    text = "\n".join("строка " + str(i) for i in range(2000))
    parts = chunk_html(text)
    assert all(len(p) <= 4096 for p in parts)
    # content round-trip (no tags here, so nothing is added by balancing)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_chunk_keeps_paired_tags_balanced_on_overlong_line():
    # a single markdown-bold line longer than the limit
    text = "<b>" + ("z" * 9000) + "</b>"
    parts = chunk_html(text)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 4096
        assert p.count("<b>") == p.count("</b>")  # each chunk is valid standalone HTML


def test_chunk_does_not_split_a_tag():
    line = "prefix <b>" + ("x" * 60) + "</b> suffix"
    text = "\n".join([line] * 300)  # forces multiple chunks
    parts = chunk_html(text)
    for p in parts:
        # every opening <b> in a chunk has a matching closing </b>
        assert p.count("<b>") == p.count("</b>")


def test_chunk_handles_overlong_single_line():
    # a single line longer than 4096 with no tags must still be split safely
    long_line = "y" * 10000
    parts = chunk_html(long_line)
    assert all(len(p) <= 4096 for p in parts)
    assert "".join(parts) == long_line
