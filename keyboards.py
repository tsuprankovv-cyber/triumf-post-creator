# keyboards.py
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📚 Мои кнопки")
    builder.button(text="📚 Мои ссылки")
    builder.button(text="❓ Помощь")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

def cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

def navigation_keyboard(can_back=True, can_forward=True, can_save=True):
    builder = InlineKeyboardBuilder()
    buttons = []
    if can_back:
        buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data="nav:back"))
    if can_save:
        buttons.append(InlineKeyboardButton(text="💾 Сохранить", callback_data="nav:save"))
    if can_forward:
        buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data="nav:next"))
    if buttons:
        builder.row(*buttons)
    return builder.as_markup()

def media_navigation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data="media:skip"),
        InlineKeyboardButton(text="✅ Готово", callback_data="media:done")
    )
    return builder.as_markup()

def text_navigation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к медиа", callback_data="text:back_to_media"),
        InlineKeyboardButton(text="Вперёд к ссылкам ▶️", callback_data="text:next_to_links")
    )
    return builder.as_markup()

def final_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Переслать вручную", callback_data="send:manual"),
        InlineKeyboardButton(text="👻 Отправить анонимно", callback_data="send:anonymous")
    )
    return builder.as_markup()
