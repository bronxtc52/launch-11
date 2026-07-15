"""Sentry init + before_send scrubber (council S4).

Telegram message bodies, tool arguments, artifacts, tokens and API keys must
never leave the process inside error events.
"""
from __future__ import annotations

import re

SENSITIVE_KEY = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization|dsn)")
CONTENT_KEYS = {"text", "caption", "markdown", "artifact"}
REDACTED = "«REDACTED»"


def scrub_event(event: dict, hint) -> dict:
    # 1. collect sensitive string values so we can purge them wherever they appear
    secrets: set[str] = set()

    def collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and SENSITIVE_KEY.search(k):
                    secrets.add(v)
                collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)

    collect(event)

    # 2. redact by key name/content, then purge captured secret values from all strings
    def scrub(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if SENSITIVE_KEY.search(k) or k in CONTENT_KEYS:
                    out[k] = REDACTED
                else:
                    out[k] = scrub(v)
            return out
        if isinstance(o, list):
            return [scrub(v) for v in o]
        if isinstance(o, str):
            s = o
            for sec in secrets:
                if sec:
                    s = s.replace(sec, REDACTED)
            return s
        return o

    return scrub(event)


def init_sentry(dsn: str, release: str | None = None) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        release=release,
        send_default_pii=False,
        before_send=scrub_event,
        traces_sample_rate=0.0,
    )
