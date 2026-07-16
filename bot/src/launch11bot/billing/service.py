"""Billing service — entitlement + Telegram Stars payments.

All money logic is server-side and transactional (KB lessons): entitlement is
consumed atomically on session creation; crediting is idempotent by charge_id;
payments are validated (currency/amount/payload) before crediting.
"""
from __future__ import annotations

from ..pipeline.slug import slugify

NEEDS_PAYMENT = object()  # sentinel returned when the user must pay to start a new run


class BillingService:
    def __init__(self, repo, free_runs: int, stars_price: int, stars_label: str,
                 owners: set[int] | None = None):
        self.repo = repo
        self.free_runs = free_runs
        self.stars_price = stars_price
        self.stars_label = stars_label
        self.owners = owners or set()

    def is_owner(self, user_id: int) -> bool:
        return user_id in self.owners

    async def start_session(self, user_id: int, slug: str, version: str):
        """Consume one entitlement and create the session, or return NEEDS_PAYMENT.
        Resuming an existing active session consumes nothing.
        Owners run unlimited and are never billed."""
        if self.is_owner(user_id):
            # no entitlement touched at all — never consumed, never invoiced
            return await self.repo.start_session(user_id, slugify(slug), version)
        session = await self.repo.start_session_with_entitlement(
            user_id, slugify(slug), version, self.free_runs)
        return session if session is not None else NEEDS_PAYMENT

    def validate_payment(self, user_id: int, currency: str, total_amount: int,
                         invoice_payload: str) -> bool:
        """Only our XTR invoice, at our price, bound to THIS user (council security-1, crit 11/12).
        Used both in pre_checkout (fail-closed BEFORE payment) and before crediting."""
        return (currency == "XTR"
                and total_amount == self.stars_price
                and invoice_payload == self.payload_for(user_id))

    async def on_successful_payment(self, user_id: int, charge_id: str, currency: str,
                                    total_amount: int, invoice_payload: str) -> bool:
        if not self.validate_payment(user_id, currency, total_amount, invoice_payload):
            return False
        return await self.repo.grant_paid_credit(charge_id, user_id, total_amount)

    def payload_for(self, user_id: int) -> str:
        return f"run:{user_id}"

    def invoice_params(self, user_id: int) -> dict:
        from aiogram.types import LabeledPrice
        return {
            "title": self.stars_label,
            "description": "Один прогон пайплайна launch-11 (идея → spec.md)",
            "payload": self.payload_for(user_id),
            "provider_token": "",           # empty for Telegram Stars
            "currency": "XTR",
            "prices": [LabeledPrice(label=self.stars_label, amount=self.stars_price)],
        }
