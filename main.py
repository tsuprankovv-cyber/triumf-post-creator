# -*- coding: utf-8 -*-
import os, logging, json, re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from states import PostWorkflow
from keyboards import main_keyboard, cancel_keyboard, navigation_keyboard, media_navigation_keyboard, text_navigation_keyboard, final_keyboard
from database import init_db, save_button, get_saved_buttons, delete_button, save_draft, get_draft, delete_draft

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(), logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')])
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer("🤖 **Пост-Триумф**\n\n➕ Новый пост — создать пост\n📚 Мои кнопки — управление кнопками\n📚 Мои ссылки — управление ссылками\n❓ Помощь", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    await message.answer("**📖 Помощь**\n\n1. Нажми ➕ Новый пост\n2. Загрузи фото/видео или пропусти\n3. Напиши текст\n4. Добавь кнопки\n5. Отправь в группу", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    delete_draft(message.from_user.id)  # ✅ Убран await
    await message.answer("❌ Отменено", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer("📝 **Шаг 1: Медиа**\n\nОтправь фото/видео или нажми ⏭️ Пропустить", parse_mode=ParseMode.MARKDOWN, reply_markup=media_navigation_keyboard())

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    await state.update_data(media_type='photo', media_id=message.photo[-1].file_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': message.photo[-1].file_id}, 'selecting_media')  # ✅ Убран await
    await message.answer("📸 Фото! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    await state.update_data(media_type='video', media_id=message.video.file_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': message.video.file_id}, 'selecting_media')  # ✅ Убран await
    await message.answer("🎬 Видео! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.text)
async def skip_media(message: types.Message, state: FSMContext):
    if message.text in ["⏭️ Пропустить", "✅ Готово"]:
        await state.update_data(media_type=None, media_id=None)
        save_draft(message.from_user.id, {}, 'selecting_media')  # ✅ Убран await
        await message.answer("⏭️ Пропущено! Напиши текст:", reply_markup=text_navigation_keyboard())
        await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    if message.text in ["◀️ Назад к медиа", "Вперёд к ссылкам ▶️"]:
        return
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')  # ✅ Убран await
    await message.answer(f"✍️ Текст сохранён! ({len(message.text)} симв.)\n\nНажми Вперёд к ссылкам ▶️", reply_markup=text_navigation_keyboard())

@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    if action == 'back_to_media':
        await state.set_state(PostWorkflow.selecting_media)
        await callback.message.edit_text("📎 Редактирование медиа:", reply_markup=media_navigation_keyboard())
        await callback.answer()
    elif action == 'next_to_links':
        data = await state.get_data()
        if not data.get('text'):
            await callback.answer("❌ Сначала введи текст!", show_alert=True)
            return
        await callback.answer("▶️ Переход к ссылкам (в разработке)")

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    if action == 'manual':
        await callback.message.answer("📤 **Переслать вручную**\n\n1. Нажмите на сообщение\n2. Выберите «Переслать»\n3. Выберите чат")
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 В разработке", show_alert=True)

async def main():
    logger.info("🚀 Пост-Триумф запускается...")
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
