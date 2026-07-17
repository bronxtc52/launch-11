"""The bot must never destroy the content it is asking about.

Live bug: the bot sent «Подтверждаешь такую формулировку Northern Star?» — WITHOUT the
formulation. Log evidence:

    contract violation: text='Хорошо, фокус — регулярность. Тогда путеводная звезда продукта:\\n\\n**'
    tool=ask_question ok=True  -> "Подтверждаешь такую формулировку?"

The model put the formulation in prose with an explanatory bullet list; validate_prose
rejected it as "список в свободном тексте"; the correction told the model to ask via the
tool — so it complied and DROPPED the formulation. The validator killed content instead of
repairing it.

One question per message is the invariant. A list of STATEMENTS is legitimate content —
only a dump of QUESTIONS is the thing we ban.
"""
from launch11bot.app.turn import CONTRACT_CORRECTION, run_user_turn
from launch11bot.llm.client import Turn
from launch11bot.pipeline.question import validate_preamble, validate_prose, validate_rendered
from launch11bot.pipeline.tool_dispatcher import dispatch

FORMULATION = ("Хорошо, фокус — регулярность. Тогда путеводная звезда продукта:\n\n"
               "**«Рекрутер стабильно получает 5 тёплых кандидатов в неделю»**\n\n"
               "Это значит:\n- поток предсказуем\n- рекрутер не ищет вручную")


def test_explanatory_list_in_prose_is_legitimate_content():
    assert validate_prose(FORMULATION) is None, \
        "список утверждений — это контент, а не свалка вопросов"


def test_prose_with_a_question_is_still_banned():
    assert validate_prose("Вот звезда: «X». А что думаешь?") is not None
    assert validate_prose("Кто пользователь?") is not None


def test_semicolons_are_not_a_list():
    assert validate_prose("Звезда: поток стабилен; поиск не ручной; сроки предсказуемы.") is None


def test_preamble_fits_a_real_formulation():
    pre = ("Northern Star: «Рекрутер стабильно получает 5 тёплых кандидатов в неделю "
           "без ручного поиска на джоб-сайтах». Это поведенческая метрика, не выручка. "
           "Она отражает регулярность, которую ты выбрал.")
    assert validate_preamble(pre) is None, "формулировка обязана помещаться в преамбулу"


def test_rendered_keeps_one_question_rule():
    assert validate_rendered("Контекст со списком:\n- раз\n- два\n\nПодтверждаешь?") is None
    assert validate_rendered("Первый? Второй?") is not None   # two questions -> still banned


async def test_contract_correction_tells_the_model_to_keep_the_context():
    assert "preamble" in CONTRACT_CORRECTION, \
        "коррекция обязана велеть ПЕРЕНЕСТИ контекст в preamble, а не выбросить его"


async def test_formulation_reaches_the_user_with_the_question(orch, repo):
    """The live scenario end-to-end: model states the formulation and asks to confirm."""
    s = await orch.start(1)
    sent_q, sent_t = [], []

    async def on_q(q):
        sent_q.append(q)

    async def on_t(t):
        sent_t.append(t)

    async def _noop(*a):
        pass

    claude = _Fake([Turn(text=FORMULATION, tool_calls=[
        ("t1", "ask_question", {"question": "Подтверждаешь такую формулировку?"})])])
    await run_user_turn(orch=orch, claude=claude, repo=repo, settings=orch.settings, session=s,
                        user_text="регулярность", on_text=on_t, on_document=_noop,
                        on_notice=_noop, on_question=on_q)

    everything = " ".join(sent_t + sent_q)
    assert "5 тёплых кандидатов" in everything, \
        "формулировку, которую просят подтвердить, нельзя терять"
    assert "Подтверждаешь такую формулировку?" in everything


class _Fake:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def turn(self, system, history, version, **_):
        self.calls += 1
        return self.script.pop(0) if self.script else Turn(text="")
