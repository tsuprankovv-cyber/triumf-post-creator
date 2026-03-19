# keyboards.py
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📚 Библиотека кнопок")
    builder.button(text="🔗 Библиотека ссылок")
    builder.button(text="📋 Мои посты")
    builder.button(text="❓ Помощь")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

def media_keyboard(has_media=False):
    builder = ReplyKeyboardBuilder()
    builder.button(text="📎 Прикрепить фото/видео")
    if has_media:
        builder.button(text="🔄 Заменить медиа")
        builder.button(text="🗑️ Удалить медиа")
    builder.button(text="⏭️ Пропустить медиа")
    builder.button(text="➡️ Далее: Текст")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(1, 2, 2)
    return builder.as_markup(resize_keyboard=True)

def text_keyboard(has_text=False, has_formatted=False):
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
    builder.button(text="🔗 Добавить ссылку в текст")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def buttons_keyboard(has_buttons=False):
    builder = ReplyKeyboardBuilder()
    builder.button(text="⬅️ Назад: Текст")
    builder.button(text="➕ Добавить кнопку")
    builder.button(text="📚 Из библиотеки кнопок")
    builder.button(text="🔗 Добавить ссылку в текст")
    builder.button(text="✅ ФИНИШ: Опубликовать")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def library_keyboard(items, selected_ids=None, item_type='button'):
    if selected_ids is None:
        selected_ids = set()
    builder = InlineKeyboardBuilder()
    for item in items:
        icon = "✅" if item['id'] in selected_ids else "🔘"
        txt = item['text'][:20] + ".." if len(item['text']) > 20 else item['text']
        callback_type = 'lib' if item_type == 'button' else 'link_lib'
        builder.button(text=f"{icon} {txt}", callback_data=f"{callback_type}:toggle:{item['id']}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="✅ Применить", callback_data=f"{item_type}:apply"),
        InlineKeyboardButton(text="➕ Добавить", callback_data=f"{item_type}:create")
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{item_type}:back"))
    return builder.as_markup()

def library_edit_keyboard(item_id, item_type='button'):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"{item_type}:edit:{item_id}"),
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"{item_type}:delete:{item_id}")
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{item_type}:back"))
    return builder.as_markup()

def posts_keyboard(posts):
    builder = InlineKeyboardBuilder()
    for post in posts:
        preview = post['text'][:50].replace('\n', ' ') + "..." if len(post['text']) > 50 else post['text']
        builder.button(text=f"📄 #{post['id']} - {preview}", callback_data=f"post:select:{post['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ В главное меню", callback_data="post:back"))
    return builder.as_markup()

def post_actions_keyboard(post_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post:edit:{post_id}"),
        InlineKeyboardButton(text="📋 Копировать", callback_data=f"post:copy:{post_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📤 Переслать как я", callback_data=f"post:forward_me:{post_id}"),
        InlineKeyboardButton(text="👻 Переслать анонимно", callback_data=f"post:forward_anon:{post_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить из истории", callback_data=f"post:delete:{post_id}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="post:back")
    )
    return builder.as_markup()

def help_keyboard(current_step='main'):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"help:back:{current_step}"))
    return builder.as_markup()

def finish_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Переслать как я", callback_data="finish:forward_me"),
        InlineKeyboardButton(text="👻 Переслать анонимно", callback_data="finish:forward_anon")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Копировать пост", callback_data="finish:copy"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="finish:edit")
    )
    builder.row(InlineKeyboardButton(text="✅ Готово", callback_data="finish:done"))
    return builder.as_markup()
