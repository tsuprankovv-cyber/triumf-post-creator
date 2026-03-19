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

def media_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📷 Прикрепить фото/видео (скрепка 📎)")
    builder.button(text="⏭️ Пропустить медиа")
    builder.button(text="➡️ Далее: Текст")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True)

def text_keyboard(has_text: bool, has_formatted: bool):
    builder = ReplyKeyboardBuilder()
    builder.button(text="⬅️ Назад: Медиа")
    builder.button(text="➡️ Далее: Кнопки")
    builder.button(text="✏️ Редактировать текст")
    if has_formatted:
        builder.button(text="🔄 Эмодзи (сменить)")
        builder.button(text="📄 Без формата")
    else:
        if has_text:
            builder.button(text="🪄 Сделать красиво")
            builder.button(text="🧹 Без эмодзи")
    builder.button(text="🤖 ИИ: Обновить")
    builder.button(text="🤖 ИИ: Новый запрос")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup(resize_keyboard=True)

def buttons_keyboard(has_buttons: bool):
    builder = ReplyKeyboardBuilder()
    builder.button(text="⬅️ Назад: Текст")
    builder.button(text="➕ Добавить кнопку")
    builder.button(text="📚 Из библиотеки кнопок")
    builder.button(text="🔗 Добавить ссылку в текст")
    builder.button(text="✅ ФИНИШ: Опубликовать")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)

def library_keyboard(buttons: list, selected_ids: set = None):
    if selected_ids is None:
        selected_ids = set()
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

def saved_links_keyboard(links: list):
    builder = InlineKeyboardBuilder()
    for link in links:
        builder.button(text=f"🔗 {link['text']}", callback_data=f"link:insert:{link['id']}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="➕ Создать новую", callback_data="link:create"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="link:back")
    )
    return builder.as_markup()
