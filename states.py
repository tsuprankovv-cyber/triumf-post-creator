# states.py
from aiogram.fsm.state import State, StatesGroup

class PostWorkflow(StatesGroup):
    selecting_media = State()
    writing_text = State()
    adding_buttons = State()

# Состояния для пошагового создания кнопки
class AddButtonSteps(StatesGroup):
    waiting_for_text = State()
    waiting_for_url = State()

# Состояние для быстрого ввода кнопок (опционально, можно использовать и без него)
class QuickButtonInput(StatesGroup):
    waiting_for_input = State()State()
