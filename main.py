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

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,  # ✅ Изменено на DEBUG для детальных логов
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

logger.info("="*60)
logger.info("🚀 ПОСТ-ТРИУМФ ЗАПУСКАЕТСЯ")
logger.info(f"🤖 Bot ID: {bot.id}")
logger.info(f"📛 Username: @{bot.username}")
logger.info("="*60)

# ==================== ГЛАВНОЕ МЕНЮ ====================

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    logger.info(f"👤 User {message.from_user.id} (@{message.from_user.username or 'anon'}) вызвал /start")
    await message.answer(
        "🤖 **Пост-Триумф**\n\n"
        "➕ Новый пост — создать пост\n"
        "📚 Мои кнопки — управление кнопками\n"
        "📚 Мои ссылки — управление ссылками\n"
        "❓ Помощь",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    logger.info(f"👤 User {message.from_user.id} запросил помощь")
    await message.answer(
        "**📖 Помощь**\n\n"
        "1. Нажми ➕ Новый пост\n"
        "2. Загрузи фото/видео или пропусти\n"
        "3. Напиши текст\n"
        "4. Добавь кнопки\n"
        "5. Отправь в группу",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} отменил действие")
    await state.clear()
    delete_draft(message.from_user.id)
    await message.answer("❌ Отменено", reply_markup=main_keyboard())

# ==================== СОЗДАНИЕ ПОСТА ====================

@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал создание поста")
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer(
        "📝 **Шаг 1: Медиа**\n\n"
        "Отправь фото/видео или нажми ⏭️ Пропустить",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=media_navigation_keyboard()
    )

# ==================== ШАГ 1: МЕДИА ====================

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    media_id = message.photo[-1].file_id
    logger.info(f"👤 User {message.from_user.id} отправил фото (ID: {media_id[:20]}...)")
    await state.update_data(media_type='photo', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': media_id}, 'selecting_media')
    await message.answer(
        "📸 **Фото получено!**\n\n"
        "Теперь напиши текст:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=text_navigation_keyboard()
    )
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    media_id = message.video.file_id
    logger.info(f"👤 User {message.from_user.id} отправил видео (ID: {media_id[:20]}...)")
    await state.update_data(media_type='video', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': media_id}, 'selecting_media')
    await message.answer(
        "🎬 **Видео получено!**\n\n"
        "Теперь напиши текст:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=text_navigation_keyboard()
    )
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.text)
async def skip_media(message: types.Message, state: FSMContext):
    if message.text in ["⏭️ Пропустить", "✅ Готово"]:
        logger.info(f"👤 User {message.from_user.id} пропустил медиа")
        await state.update_data(media_type=None, media_id=None)
        save_draft(message.from_user.id, {}, 'selecting_media')
        await message.answer(
            "⏭️ **Пропущено!**\n\n"
            "Напиши текст:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=text_navigation_keyboard()
        )
        await state.set_state(PostWorkflow.writing_text)
    else:
        logger.warning(f"👤 User {message.from_user.id} отправил неизвестный текст: {message.text}")

# ==================== ШАГ 2: ТЕКСТ ====================

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    if message.text in ["◀️ Назад к медиа", "Вперёд к ссылкам ▶️"]:
        logger.debug(f"👤 User {message.from_user.id} нажал кнопку навигации: {message.text}")
        return
    
    text_len = len(message.text)
    logger.info(f"👤 User {message.from_user.id} отправил текст ({text_len} симв.)")
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')
    await message.answer(
        f"✍️ **Текст сохранён!** ({text_len} симв.)\n\n"
        f"Нажми Вперёд к ссылкам ▶️",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=text_navigation_keyboard()
    )

# ==================== CALLBACK: НАВИГАЦИЯ ====================

@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал callback: text:{action}")
    
    if action == 'back_to_media':
        logger.info(f"👤 User {user_id} вернулся к шагу медиа")
        await state.set_state(PostWorkflow.selecting_media)
        await callback.message.edit_text(
            "📎 **Редактирование медиа:**\n\n"
            "Отправь новое фото/видео или нажми ⏭️ Пропустить",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=media_navigation_keyboard()
        )
        await callback.answer("◀️ Возврат к медиа")
        
    elif action == 'next_to_links':
        data = await state.get_data()
        if not data.get('text'):
            logger.warning(f"👤 User {user_id} попытался перейти к ссылкам без текста")
            await callback.answer("❌ Сначала введи текст!", show_alert=True)
            return
        logger.info(f"👤 User {user_id} перешёл к ссылкам (в разработке)")
        await callback.answer("▶️ Переход к ссылкам (в разработке)", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('media:'))
async def media_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал callback: media:{action}")
    
    if action == 'skip':
        await state.update_data(media_type=None, media_id=None)
        save_draft(user_id, {}, 'selecting_media')
        await state.set_state(PostWorkflow.writing_text)
        await callback.message.edit_text(
            "⏭️ **Пропущено!**\n\n"
            "Напиши текст:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=text_navigation_keyboard()
        )
        await callback.answer("⏭️ Пропущено")
    
    elif action == 'done':
        await callback.answer("✅ Готово (переход к тексту)", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал callback: send:{action}")
    
    if action == 'manual':
        await callback.message.answer(
            "📤 **Переслать вручную**\n\n"
            "1. Нажмите на сообщение\n"
            "2. Выберите «Переслать»\n"
            "3. Выберите чат"
        )
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 В разработке", show_alert=True)

# ==================== ЗАПУСК ====================

async def main():
    logger.info("="*60)
    logger.info("🚀 ПОСТ-ТРИУМФ ЗАПУСКАЕТСЯ")
    logger.info(f"🤖 Bot ID: {bot.id}")
    logger.info(f"📛 Username: @{bot.username}")
    logger.info("="*60)
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
