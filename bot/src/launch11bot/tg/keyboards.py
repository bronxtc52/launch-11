from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def version_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Full — все 11 шагов", callback_data="ver:full")],
            [InlineKeyboardButton(text="⚡ Lite — сжато", callback_data="ver:lite")],
            [InlineKeyboardButton(text="🔧 Spec-only — только техчасть", callback_data="ver:spec_only")],
        ]
    )


def nav_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Прогресс", callback_data="progress"),
                InlineKeyboardButton(text="♻️ Начать заново", callback_data="reset"),
            ]
        ]
    )
