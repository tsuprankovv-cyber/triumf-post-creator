# keyboards.py
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_keyboard():
    """Главное меню бота"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Новый пост")
    builder.button(text="📚 Мои кнопки")
    builder.button(text="❓ Помощь")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def cancel_keyboard():
    """Клавиатура отмены"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)

def post_creation_keyboard():
    """Меню для быстрого добавления кнопок (вспомогательное)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Добавить кнопку")
    builder.button(text="📚 Из библиотеки")
    builder.button(text="✅ ФИНИШ: Готовый пост")
    builder.button(text="❌ Отмена")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

def get_preview_keyboard(step: str, has_text: bool, has_formatted: bool):
    """
    Генерирует клавиатуру управления ПОД сообщением предпросмотра.
    
    :param step: текущий шаг ('media', 'text', 'buttons')
    :param has_text: есть ли уже текст в посте
    :param has_formatted: был ли применен стиль (для показа кнопок сброса/вариантов)
    """
    builder = InlineKeyboardBuilder()
    
    if step == 'media':
        # Шаг 1: Медиа
        builder.row(
            InlineKeyboardButton(text="⏭️ Пропустить фото", callback_data="prev:skip_media"),
            InlineKeyboardButton(text="Далее: Текст ▶️", callback_data="prev:to_text")
        )
        
    elif step == 'text':
        # Шаг 2: Текст
        # Ряд 1: Навигация и ручное редактирование
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="prev:back_media"),
            InlineKeyboardButton(text="✏️ Править текст", callback_data="prev:edit_text")
        )
        
        # Ряд 2: ИИ и Форматирование
        row_format = [
            InlineKeyboardButton(text="🤖 Придумать текст", callback_data="prev:ai_generate"),
            InlineKeyboardButton(text="🪄 Красиво", callback_data="prev:smart_format")
        ]
        
        # Если текст уже отформатирован, добавляем кнопки управления стилем
        if has_formatted:
            row_format.append(InlineKeyboardButton(text="🔄 Ещё", callback_data="prev:smart_next"))
            row_format.append(InlineKeyboardButton(text="↩️ Сброс", callback_data="prev:smart_reset"))
            
        builder.row(*row_format)
        
        # Ряд 3: Очистка (отдельно эмодзи и формат)
        if has_text:
            builder.row(
                InlineKeyboardButton(text="🧹 Без эмодзи", callback_data="prev:remove_emojis"),
                InlineKeyboardButton(text="📄 Без формата", callback_data="prev:remove_format")
            )
        
        # Ряд 4: Переход дальше
        builder.row(InlineKeyboardButton(text="Далее: Кнопки ▶️", callback_data="prev:to_buttons"))
        
    elif step == 'buttons':
        # Шаг 3: Кнопки
        builder.row(
            InlineKeyboardButton(text="◀️ Назад к тексту", callback_data="prev:back_text"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="prev:add_btn")
        )
        builder.row(
            InlineKeyboardButton(text="📚 Выбрать из списка", callback_data="prev:lib_btn"),
            InlineKeyboardButton(text="✅ ФИНИШ: Готовый пост", callback_data="prev:finish")
        )
        
    # Общая кнопка отмены в самом низу
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="prev:cancel"))
    
    return builder.as_markup()

def library_keyboard(buttons: list, selected_ids: set = None):
    """Клавиатура выбора кнопок из библиотеки (с чекбоксами)"""
    if selected_ids is None:
        selected_ids = set()
    
    builder = InlineKeyboardBuilder()
    for btn in buttons:
        icon = "✅" if btn['id'] in selected_ids else "🔘"
        # Обрезаем длинный текст
        txt = btn['text'][:20] + ".." if len(btn['text']) > 20 else btn['text']
        builder.button(text=f"{icon} {txt}", callback_data=f"lib:toggle:{btn['id']}")
    
    builder.adjust(2) # 2 кнопки в ряд
    
    builder.row(
        InlineKeyboardButton(text="✅ Применить", callback_data="lib:apply"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="lib:back")
    )
    return builder.as_markup()
