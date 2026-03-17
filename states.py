# states.py
from aiogram.fsm.state import State, StatesGroup

class PostWorkflow(StatesGroup):
    selecting_media = State()
    configuring_media = State()
    writing_text = State()
    adding_inline_links = State()
    adding_buttons = State()
    preview = State()
    editing_step = State()
    confirming = State()
