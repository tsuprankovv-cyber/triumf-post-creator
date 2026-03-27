# -*- coding: utf-8 -*-
from aiogram.utils.keyboard import InlineKeyboardBuilder

def help_keyboard(step: str):
    """Клавиатура для помощи"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="help:back")
    builder.adjust(1)
    return builder.as_markup()
