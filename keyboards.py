# keyboards.py
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📚 Мои кнопки")
    builder.button(text="❓ Помощь")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

def post_creation_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 Выбрать из библиотеки")
    builder.button(text="➕ Добавить новую")
    builder.button(text="✅ Готово с кнопками")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

def add_button_mode_keyboard():
    """Выбор способа добавления кнопки"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ По шагам (текст → ссылка)")
    builder.button(text="⚡ Быстро (текст - ссылка)")
    builder.button(text="◀️ Назад")
    builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True)

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
        InlineKeyboardButton(text="Вперёд к кнопкам ▶️", callback_data="text:next_to_buttons")
    )
    return builder.as_markup()

def library_keyboard(buttons: list, selected_ids: set = None):
    if selected_ids is None:
        selected_ids = set()
    
    builder = InlineKeyboardBuilder()
    for btn in buttons:
        is_selected = btn['id'] in selected_ids
        icon = "✅" if is_selected else "🔘"
        display_text = btn['text'][:25] + "..." if len(btn['text']) > 25 else btn['text']
        builder.button(
            text=f"{icon} {display_text}",
            callback_data=f"lib:toggle:{btn['id']}"
        )
    
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="✅ Применить", callback_data="lib:apply"),
        InlineKeyboardButton(text="🔄 Сбросить", callback_data="lib:clear")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="lib:back")
    )
    return builder.as_markup()

def final_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Переслать вручную", callback_data="send:manual"),
        InlineKeyboardButton(text="👻 Отправить анонимно", callback_data="send:anonymous")
    )
    return builder.as_markup()
