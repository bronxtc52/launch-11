"""The spec filename must name the PRODUCT, not the first thing the human typed.

Live: the delivered file was «не-понял-spec.md» — the session slug was taken from the user's
first message, which happened to be «не понял». That utterance then named the product forever.

Fix: the first message never names anything. A neutral slug is used until the model, which
knows the product by then, sets a real name via set_product_name.
"""
from launch11bot.app.turn import handle_incoming
from launch11bot.billing.service import BillingService
from launch11bot.llm.client import Turn
from launch11bot.pipeline.tool_dispatcher import dispatch


class FakeClaude:
    def __init__(self, script=()):
        self.script = list(script)
        self.calls = 0

    async def turn(self, system, history, version, **_):
        self.calls += 1
        return self.script.pop(0) if self.script else Turn(text="ок")


async def _noop(*a):
    pass


async def test_first_message_never_becomes_the_product_name(orch, repo):
    billing = BillingService(repo, free_runs=1, stars_price=100, stars_label="x")
    await handle_incoming(
        user_id=77, text="не понял", version="lite", orch=orch, billing=billing,
        claude=FakeClaude(), repo=repo, settings=orch.settings, on_text=_noop,
        on_document=_noop, on_notice=_noop, on_question=_noop, on_needs_payment=_noop,
        on_denied=_noop,
    )
    s = await orch.resume(77)
    assert "не-понял" not in s.slug, "случайная реплика не может назвать продукт"


async def test_model_names_the_product(orch):
    s = await orch.start(1)
    res = await dispatch(orch, s, "set_product_name",
                         {"name": "AI-рекрутер для hh.kz"})
    assert res.ok is True
    assert s.slug == "ai-рекрутер-для-hh-kz"


async def test_product_name_is_validated(orch):
    s = await orch.start(1)
    before = s.slug
    for junk in ("", "   ", "?" * 5, "а" * 300):
        res = await dispatch(orch, s, "set_product_name", {"name": junk})
        assert res.ok is False, f"мусор не должен становиться именем файла: {junk!r}"
    assert s.slug == before


async def test_filename_uses_the_product_name(orch, repo):
    s = await orch.start(1)
    await dispatch(orch, s, "set_product_name", {"name": "AI рекрутер"})
    for sid in ("L1", "L2", "L3", "L4"):
        s = await orch.save_artifact(s, sid, f"# {sid}")
    spec = await orch.finish(s)
    assert "ai-рекрутер" in s.slug
    assert "ai-рекрутер" in spec.splitlines()[0].lower(), "заголовок spec.md несёт имя продукта"


async def test_neutral_fallback_when_never_named(orch):
    s = await orch.start(42)
    assert s.slug.startswith("product-"), "без имени — нейтральный slug, а не случайная фраза"


def test_tool_is_exposed_to_the_model():
    from launch11bot.llm import tools
    names = {t["name"] for t in tools.tool_defs("full")}
    assert "set_product_name" in names


def test_star_steps_tell_the_model_to_name_the_product():
    from launch11bot.pipeline import steps
    for plist in steps.PIPELINES.values():
        for st in plist:
            if st.id in ("L1", "F1"):
                assert "set_product_name" in st.instruction, \
                    f"{st.id}: модель должна знать, что продукт надо назвать"
