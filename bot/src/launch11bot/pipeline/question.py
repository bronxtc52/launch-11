"""Deterministic validation of everything the bot is about to SAY as a question.

Enforcing the *channel* (ask_question) is not enough — the model will put the dump inside
the tool arguments. Acceptance testing proved two escapes:
  * the whole list in `preamble` with a harmless "Начнём?" in `question`;
  * imperative dumps with no '?' at all ("Расскажи про X. Опиши Y. Дай Z.").
So we validate the *rendered user-facing text* as the single choke point, and require a
question to actually BE one question.
"""
from __future__ import annotations

import re

MAX_QUESTION_LEN = 400
MAX_PREAMBLE_LEN = 1200     # live: the model kept hitting 600 while presenting real content
MAX_RENDERED_LEN = 1800
MAX_PREAMBLE_SENTENCES = 12 # context is legitimate; the one-question rule is what we enforce
MAX_QUESTION_SENTENCES = 3

# list markers: at line start OR inline ("… ответь: 1) кто клиент; 2) какая боль")
_LIST_MARKER = re.compile(r"(?m)(?:^\s*|\s)(\d+[.)]|[-*•])\s+")
_SENTENCE_SPLIT = re.compile(r"[.!?]+(?:\s|$)")
_FIRST_QUESTION = re.compile(r"([^.!?\n]{3,}\?)")
# fullwidth/arabic/double question marks slip past a naive count("?")
_UNICODE_Q = re.compile(r"[？؟⁇︖﹖]")


def normalize_marks(text: str | None) -> str:
    return _UNICODE_Q.sub("?", text or "")


def _sentences(text: str) -> int:
    return len([p for p in _SENTENCE_SPLIT.split(text) if p.strip()])


def _list_like(text: str) -> bool:
    return bool(_LIST_MARKER.search(text)) or text.count(";") >= 2


# Asking without a question mark is still asking. These are the imperatives the model reaches
# for when it dumps requests as prose ("Теперь: 1. Расскажи… 2. Опиши…").
_IMPERATIVE = re.compile(
    r"(?im)(?:^|[\n;]|\d+[.)]\s*|[-*•]\s*)\s*"
    r"(расскажи|опиши|назови|перечисли|укажи|уточни|дай|напиши|поясни|объясни|сформулируй|ответь)\b"
)


def _request_dump(text: str) -> bool:
    """Two or more imperative requests = a dump wearing a statement's clothes.
    A list of STATEMENTS ('- поток предсказуем') is content and must survive."""
    return len(_IMPERATIVE.findall(text)) >= 2


def validate_prose(text: str | None) -> str | None:
    """Free-text the bot forwards. It must carry NO question — questions go through
    ask_question only.

    Lists are NOT banned here. Banning them was over-broad: it was aimed at question-dumps
    but it shredded legitimate content — a Northern Star formulation with an explanatory
    bullet list got rejected, the model then dropped it, and the user was asked to confirm
    a formulation they never saw. A list of STATEMENTS is content; only a dump of QUESTIONS
    is the thing we ban, and the '?' rule already catches that."""
    t = normalize_marks(text).strip()
    if not t:
        return None
    if "?" in t:
        return "вопрос в свободном тексте — задавай только через ask_question"
    if _request_dump(t):
        return "несколько требований подряд — это та же свалка вопросов, только без «?»"
    return None


def validate_question(text: str | None) -> str | None:
    """The single question itself. Must be exactly ONE question — not zero, not many."""
    if not text or not text.strip():
        return "пустой вопрос"
    t = normalize_marks(text).strip()
    if len(t) > MAX_QUESTION_LEN:
        return f"вопрос длиннее {MAX_QUESTION_LEN} символов"
    n = t.count("?")
    if n == 0:
        return "это не вопрос (нет '?') — задай именно вопрос, а не перечень указаний"
    if n > 1:
        return "больше одного вопроса в сообщении"
    if _list_like(t):
        return "список вопросов вместо одного"
    if _sentences(t) > MAX_QUESTION_SENTENCES:
        return "слишком много предложений — оставь один короткий вопрос"
    return None


def validate_preamble(text: str | None) -> str | None:
    """Optional 1-2 sentence lead-in. Must contain NO questions and no lists."""
    if text is None or not text.strip():
        return None
    t = normalize_marks(text).strip()
    if len(t) > MAX_PREAMBLE_LEN:
        return f"преамбула длиннее {MAX_PREAMBLE_LEN} символов"
    if "?" in t:
        return "вопрос в преамбуле — задавай вопрос только через поле question"
    if _sentences(t) > MAX_PREAMBLE_SENTENCES:
        return "преамбула длиннее двух предложений"
    return None


def validate_rendered(text: str | None) -> str | None:
    """Choke point: the FULL text about to reach the user must be exactly one question."""
    if not text or not text.strip():
        return "пустое сообщение"
    t = normalize_marks(text).strip()
    if len(t) > MAX_RENDERED_LEN:
        return f"сообщение длиннее {MAX_RENDERED_LEN} символов"
    if t.count("?") != 1:
        return "в сообщении должен быть ровно один вопрос"
    return None


def extract_first_question(text: str | None) -> str | None:
    """Fail-closed fallback: pull the FIRST single question out of a violating dump,
    so the user still gets a usable question instead of the wall of text."""
    if not text:
        return None
    m = _FIRST_QUESTION.search(text)
    if not m:
        return None
    q = re.sub(r"\s+", " ", m.group(1)).strip()
    q = re.sub(r"^(\d+[.)]|[-*•])\s*", "", q)          # drop a leading list marker
    q = re.sub(r"\*\*(.+?)\*\*", r"\1", q)             # drop markdown bold
    return q or None
