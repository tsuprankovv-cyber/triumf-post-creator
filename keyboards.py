# -*- coding: utf-8 -*-
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

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
    if has_media:
        builder.button(text="🔄 Заменить")
        builder.button(text="🗑️ Удалить")
        builder.button(text="⏭️ Пропустить")
        builder.button(text="✏️ Редактировать")
        builder.button(text="➡️ Далее: Текст")
    else:
        builder.button(text="⏭️ Пропустить")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def text_keyboard(has_text=False, has_original=False):
    builder = ReplyKeyboardBuilder()
    builder.button(text="✏️ Редактировать")
    builder.button(text="🤖 ИИ: Новый")
    if has_text:
        builder.button(text="🤖 ИИ: Обновить")
        builder.button(text="🪄 Красиво")
        builder.button(text="🔄 Эмодзи")
        builder.button(text="🧹 Без эмодзи")
        builder.button(text="📄 Без формата")
    builder.button(text="🔗 Ссылка в текст")
    builder.button(text="⬅️ Назад")
    builder.button(text="➡️ Далее: Кнопки")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def buttons_keyboard(has_buttons=False):
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Добавить кнопку")
    builder.button(text="📚 Библиотека")
    builder.button(text="⬅️ Назад: Текст")
    builder.button(text="✅ ФИНИШ")
    builder.button(text="❓ Помощь")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)

def library_keyboard(items, selected: set, lib_type: str):
    builder = InlineKeyboardBuilder()
    for item in items:
        item_id = item['id']
        item_text = item['text']
        prefix = '✅ ' if item_id in selected else ''
        if lib_type == 'button':
            builder.button(text=f"{prefix}{item_text}", callback_data=f"lib:toggle:{item_id}")
        else:
            builder.button(text=f"{prefix}{item_text}", callback_data=f"link_lib:toggle:{item_id}")
    builder.adjust(2)
    if selected:
        builder.button(text="✅ Применить", callback_data=f"{'lib' if lib_type == 'button' else 'link_lib'}:apply")
    builder.button(text="🔙 Назад", callback_data=f"{'lib' if lib_type == 'button' else 'link_lib'}:back")
    builder.adjust(1, 1)
    return builder.as_markup()

def posts_keyboard(posts):
    builder = InlineKeyboardBuilder()
    for i, post in enumerate(posts[:50]):
        post_id = post.get('id', i)
        builder.button(text=f"📄 Пост #{post_id}", callback_data=f"post:view:{post_id}")
    builder.adjust(2)
    builder.button(text="🔙 Назад", callback_data="posts:back")
    builder.adjust(1)
    return builder.as_markup()

def help_keyboard(step: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="help:back")
    builder.adjust(1)
    return builder.as_markup()

def finish_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📋 Мои посты")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True)
