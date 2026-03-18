# keyboards.py
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ==================== REPLY КЛАВИАТУРЫ (нижнее меню) ====================

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

# ==================== INLINE КЛАВИАТУРЫ (под сообщением) ====================

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
        InlineKeyboardButton(text="Вперёд к кнопкам ▶️", callback_data="text:next_to_buttons")
    )
    return builder.as_markup()

def library_keyboard(buttons: list, selected_ids: set = None):
    """Клавиатура библиотеки кнопок с чекбоксами"""
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
    
    # Кнопки действий
    builder.row(
        InlineKeyboardButton(text="✅ Применить выбранные", callback_data="lib:apply"),
        InlineKeyboardButton(text="🔄 Сбросить выбор", callback_data="lib:clear")
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
