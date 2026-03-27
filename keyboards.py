# -*- coding: utf-8 -*-
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import KeyboardButton

# === ГЛАВНОЕ МЕНЮ ===
def main_keyboard():
    """Главное меню бота"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📚 Библиотека кнопок")
    builder.button(text="🔗 Библиотека ссылок")
    builder.button(text="📋 Мои посты")
    builder.button(text="❓ Помощь")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# === ОТМЕНА ===
def cancel_keyboard():
    """Клавиатура отмены"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

# === ШАГ 1: МЕДИА ===
def media_keyboard(has_media: bool = False):
    """Клавиатура для шага с медиа"""
    builder = ReplyKeyboardBuilder()
    
    if has_media:
        builder.button(text="🔄 Заменить медиа")
        builder.button(text="🗑️ Удалить медиа")
        builder.button(text="⏭️ Пропустить медиа")
        builder.button(text="✏️ Редактировать текст")
        builder.button(text="➡️ Далее: Текст")
    else:
        builder.button(text="⏭️ Пропустить медиа")
    
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# === ШАГ 2: ТЕКСТ ===
def text_keyboard(has_text: bool = False, has_original: bool = False):
    """Клавиатура для шага с текстом"""
    builder = ReplyKeyboardBuilder()
    
    # Первый ряд
    builder.button(text="✏️ Редактировать текст")
    builder.button(text="🤖 ИИ: Новый запрос")
    
    # Второй ряд (если есть текст)
    if has_text:
        builder.button(text="🤖 ИИ: Обновить")
        builder.button(text="🪄 Сделать красиво")
    
    # Третий ряд (если есть оригинал для эмодзи)
    if has_original:
        builder.button(text="🔄 Эмодзи (сменить)")
        builder.button(text="🧹 Без эмодзи")
        builder.button(text="📄 Без формата")
    
    # Навигация
    builder.button(text="🔗 Добавить ссылку в текст")
    builder.button(text="⬅️ Назад: Медиа")
    builder.button(text="➡️ Далее: Кнопки")
    
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# === ШАГ 3: КНОПКИ ===
def buttons_keyboard(has_buttons: bool = False):
    """Клавиатура для шага с кнопками"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="➕ Добавить кнопку")
    builder.button(text="📚 Библиотека кнопок")
    
    if has_buttons:
        builder.button(text="🗑️ Удалить кнопку")
    
    builder.button(text="⬅️ Назад: Текст")
    builder.button(text="✅ ФИНИШ: Опубликовать")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)

# === БИБЛИОТЕКА (КНОПКИ/ССЫЛКИ) ===
def library_keyboard(items, selected: set, lib_type: str):
    """Клавиатура библиотеки (кнопки ИЛИ ссылки)"""
    builder = InlineKeyboardBuilder()
    
    for item in items:
        item_id = item['id']
        item_text = item['text']
        
        # ✅ callback_data для выбора из библиотеки (НЕ url!)
        if lib_type == 'button':
            builder.button(
                text=f"{'✅ ' if item_id in selected else ''}{item_text}",
                callback_data=f"lib:toggle:{item_id}"
            )
        else:
            builder.button(
                text=f"{'✅ ' if item_id in selected else ''}{item_text}",
                callback_data=f"link_lib:toggle:{item_id}"
            )
    
    builder.adjust(2)
    
    # Кнопки управления
    if selected:
        builder.button(text="✅ Применить", callback_data=f"{'lib' if lib_type == 'button' else 'link_lib'}:apply")
    builder.button(text="🔙 Назад", callback_data=f"{'lib' if lib_type == 'button' else 'link_lib'}:back")
    
    builder.adjust(1, 1)
    return builder.as_markup()

# === ПОСТЫ ===
def posts_keyboard(posts):
    """Клавиатура списка постов"""
    builder = InlineKeyboardBuilder()
    
    for i, post in enumerate(posts[:50]):
        post_id = post.get('id', i)
        post_type = post.get('media_type', 'text')
        icon = {'photo': '📷', 'video': '🎬', 'text': '📝'}.get(post_type, '📄')
        builder.button(text=f"{icon} Пост #{post_id}", callback_data=f"post:view:{post_id}")
    
    builder.adjust(2)
    builder.button(text="🔙 Назад", callback_data="posts:back")
    builder.adjust(1)
    return builder.as_markup()

# === ДЕЙСТВИЯ С ПОСТОМ ===
def post_actions_keyboard():
    """Клавиатура действий с постом"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Удалить", callback_data="post:delete")
    builder.button(text="🔙 Назад", callback_data="posts:back")
    builder.adjust(1, 1)
    return builder.as_markup()

# === ПОМОЩЬ ===
def help_keyboard(step: str):
    """Клавиатура для помощи"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="help:back")
    builder.adjust(1)
    return builder.as_markup()

# === ФИНИШ ===
def finish_keyboard():
    """Клавиатура после публикации"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📋 Мои посты")
    builder.button(text="🔙 В главное меню")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)
