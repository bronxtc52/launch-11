from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def nav_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Прогресс", callback_data="progress"),
                InlineKeyboardButton(text="♻️ Начать заново", callback_data="reset"),
            ]
        ]
    )
