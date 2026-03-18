# states.py
from aiogram.fsm.state import State, StatesGroup

class PostWorkflow(StatesGroup):
    selecting_media = State()
    writing_text = State()
    adding_buttons = State()

class AddButtonSteps(StatesGroup):
    waiting_for_text = State()
    waiting_for_url = State()
