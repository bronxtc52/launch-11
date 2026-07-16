"""Phase 4 — deterministic question validation (criterion 11) + fail-closed extraction (13)."""
from launch11bot.pipeline.question import extract_first_question, validate_question


def test_single_question_ok():
    assert validate_question("Кто конкретно страдает без продукта?") is None


def test_rejects_multiple_questions():
    assert validate_question("Кто пользователь? А какая боль?") is not None


def test_rejects_numbered_list():
    bad = "Несколько вопросов:\n1. Кто пользователь\n2. Какая боль"
    assert validate_question(bad) is not None


def test_rejects_bullet_list():
    assert validate_question("- Кто пользователь\n- Какая боль") is not None


def test_rejects_empty_and_overlong():
    assert validate_question("") is not None
    assert validate_question("   ") is not None
    assert validate_question("а" * 5000) is not None


def test_extract_first_question_from_dump():
    dump = ("Отлично! Несколько вопросов:\n\n1. **Кто именно пользователь?** Это бухгалтер?\n"
            "2. Какая боль? Что бесит?")
    q = extract_first_question(dump)
    assert q is not None
    assert q.count("?") == 1
    assert "пользователь" in q


def test_extract_returns_none_without_question():
    assert extract_first_question("Просто текст без вопросов.") is None
