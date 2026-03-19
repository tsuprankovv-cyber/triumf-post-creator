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

def get_preview_keyboard(step: str, has_text: bool, has_formatted: bool):
    builder = InlineKeyboardBuilder()
    
    if step == 'media':
        builder.row(
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data="prev:skip_media"),
            InlineKeyboardButton(text="Далее: Текст ▶️", callback_data="prev:to_text")
        )
    elif step == 'text':
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="prev:back_media"),
            InlineKeyboardButton(text="✏️ Править", callback_data="prev:edit_text")
        )
        builder.row(
            InlineKeyboardButton(text="🤖 ИИ Текст", callback_data="prev:ai_generate"),
            InlineKeyboardButton(text="🪄 Красиво", callback_data="prev:smart_format")
        )
        if has_formatted:
            builder.row(
                InlineKeyboardButton(text="🔄 Ещё", callback_data="prev:smart_next"),
                InlineKeyboardButton(text="↩️ Сброс", callback_data="prev:smart_reset")
            )
        if has_text:
            builder.row(
                InlineKeyboardButton(text="🧹 Без эмодзи", callback_data="prev:remove_emojis"),
                InlineKeyboardButton(text="📄 Без формата", callback_data="prev:remove_format")
            )
        builder.row(InlineKeyboardButton(text="Далее: Кнопки ▶️", callback_data="prev:to_buttons"))
    elif step == 'buttons':
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="prev:back_text"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="prev:add_btn")
        )
        builder.row(
            InlineKeyboardButton(text="📚 Из библиотеки", callback_data="prev:lib_btn"),
            InlineKeyboardButton(text="✅ ФИНИШ", callback_data="prev:finish")
        )
    
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="prev:cancel"))
    return builder.as_markup()

def library_keyboard(buttons: list, selected_ids: set = None):
    if selected_ids is None: selected_ids = set()
    builder = InlineKeyboardBuilder()
    for btn in buttons:
        icon = "✅" if btn['id'] in selected_ids else "🔘"
        txt = btn['text'][:20] + ".." if len(btn['text']) > 20 else btn['text']
        builder.button(text=f"{icon} {txt}", callback_data=f"lib:toggle:{btn['id']}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="✅ Применить", callback_data="lib:apply"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="lib:back")
    )
    return builder.as_markup()
