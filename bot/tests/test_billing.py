"""Phase 3 — billing entitlement + payment idempotency (criteria 1-5, 11-12)."""
import pytest
from launch11bot.billing.service import BillingService, NEEDS_PAYMENT


@pytest.fixture
def billing(repo):
    return BillingService(repo, free_runs=1, stars_price=100, stars_label="Прогон")


async def test_new_user_gets_free_run(billing, repo):
    session = await billing.start_session(1, slug="idea", version="lite")
    assert session is not NEEDS_PAYMENT
    b = await repo.get_billing(1)
    assert b["free_used"] == 1 and b["paid_credits"] == 0


async def test_second_run_without_credit_needs_payment(billing, repo):
    await billing.start_session(1, slug="idea", version="lite")
    # abandon (delete session) so resume won't return it, then try a new run
    await repo.delete_session(1)
    result = await billing.start_session(1, slug="idea2", version="lite")
    assert result is NEEDS_PAYMENT
    b = await repo.get_billing(1)
    assert b["free_used"] == 1  # unchanged, not 2


async def test_paid_credit_grants_and_is_consumed(billing, repo):
    await billing.start_session(1, slug="a", version="lite")
    await repo.delete_session(1)
    granted = await billing.on_successful_payment(1, charge_id="ch1", currency="XTR",
                                                  total_amount=100)
    assert granted is True
    assert (await repo.get_billing(1))["paid_credits"] == 1
    session = await billing.start_session(1, slug="b", version="lite")
    assert session is not NEEDS_PAYMENT
    assert (await repo.get_billing(1))["paid_credits"] == 0


async def test_duplicate_payment_not_credited_twice(billing, repo):
    g1 = await billing.on_successful_payment(1, charge_id="ch1", currency="XTR", total_amount=100)
    g2 = await billing.on_successful_payment(1, charge_id="ch1", currency="XTR", total_amount=100)
    assert g1 is True and g2 is False
    assert (await repo.get_billing(1))["paid_credits"] == 1  # not 2


async def test_wrong_currency_or_amount_not_credited(billing, repo):
    bad_cur = await billing.on_successful_payment(1, charge_id="c2", currency="USD", total_amount=100)
    bad_amt = await billing.on_successful_payment(1, charge_id="c3", currency="XTR", total_amount=5)
    assert bad_cur is False and bad_amt is False
    assert (await repo.get_billing(1))["paid_credits"] == 0


async def test_wrong_payload_not_credited(billing, repo):
    # payload bound to a different user must not credit (criterion 12)
    g = await billing.on_successful_payment(1, charge_id="cx", currency="XTR",
                                            total_amount=100, invoice_payload="run:999")
    assert g is False
    assert (await repo.get_billing(1))["paid_credits"] == 0


async def test_resume_does_not_consume(billing, repo):
    await billing.start_session(1, slug="a", version="lite")
    # starting again while an active session exists must return it WITHOUT consuming
    again = await billing.start_session(1, slug="a", version="lite")
    assert again is not NEEDS_PAYMENT
    assert (await repo.get_billing(1))["free_used"] == 1  # still 1, not 2


def test_invoice_params_xtr(billing):
    inv = billing.invoice_params(user_id=7)
    assert inv["currency"] == "XTR"
    assert inv["provider_token"] == ""
    assert inv["prices"][0].amount == 100
    assert "7" in inv["payload"]  # payload bound to the user
