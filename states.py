# states.py
from aiogram.fsm.state import State, StatesGroup

class PostWorkflow(StatesGroup):
    """Основные состояния workflow создания поста"""
    selecting_media = State()       # Выбор медиа (фото/видео)
    writing_text = State()          # Написание или редактирование текста
    adding_buttons = State()        # Добавление кнопок
    ai_input = State()              # Ввод ключевых слов для ИИ-генератора

class AddButtonSteps(StatesGroup):
    """Состояния для пошагового добавления одной кнопки"""
    waiting_for_text = State()      # Ожидание текста кнопки
    waiting_for_url = State()       # Ожидание ссылки кнопки
