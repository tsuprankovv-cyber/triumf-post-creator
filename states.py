# states.py
from aiogram.fsm.state import State, StatesGroup

class PostWorkflow(StatesGroup):
    selecting_media = State()
    writing_text = State()
    adding_buttons = State()
    ai_input = State()
    selecting_link = State()
    editing_post = State()  # Для редактирования старых постов

class AddButtonSteps(StatesGroup):
    waiting_for_text = State()
    waiting_for_url = State()

class AddLinkSteps(StatesGroup):
    waiting_for_text = State()
    waiting_for_url = State()
