# -*- coding: utf-8 -*-
import os, logging, json, re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from states import PostWorkflow
from keyboards import (
    main_keyboard, cancel_keyboard, post_creation_keyboard,
    navigation_keyboard, media_navigation_keyboard, text_navigation_keyboard,
    library_keyboard, final_keyboard
)
from database import init_db, save_button, get_saved_buttons, delete_button, save_draft, get_draft, delete_draft

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')]
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
logger.info("="*60)

# ==================== ГЛАВНОЕ МЕНЮ ====================

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    logger.info(f"👤 User {message.from_user.id} вызвал /start")
    await message.answer("🤖 **Пост-Триумф**\n\n➕ Новый пост | 📚 Мои кнопки | ❓ Помощь",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    await message.answer("**📖 Помощь**\n\n1. ➕ Новый пост → создать пост\n2. 📚 Мои кнопки → библиотека кнопок",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

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
    await message.answer("📝 **Шаг 1: Медиа**\n\nОтправь фото/видео или нажми ⏭️ Пропустить",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=media_navigation_keyboard())

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    media_id = message.photo[-1].file_id
    logger.info(f"👤 User {message.from_user.id} отправил фото")
    await state.update_data(media_type='photo', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': media_id}, 'selecting_media')
    await message.answer("📸 Фото! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    media_id = message.video.file_id
    logger.info(f"👤 User {message.from_user.id} отправил видео")
    await state.update_data(media_type='video', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': media_id}, 'selecting_media')
    await message.answer("🎬 Видео! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.text)
async def skip_media(message: types.Message, state: FSMContext):
    if message.text in ["⏭️ Пропустить", "✅ Готово"]:
        logger.info(f"👤 User {message.from_user.id} пропустил медиа")
        await state.update_data(media_type=None, media_id=None)
        save_draft(message.from_user.id, {}, 'selecting_media')
        await message.answer("⏭️ Пропущено! Напиши текст:", reply_markup=text_navigation_keyboard())
        await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    if message.text in ["◀️ Назад к медиа", "Вперёд к кнопкам ▶️"]:
        return
    text_len = len(message.text)
    logger.info(f"👤 User {message.from_user.id} отправил текст ({text_len} симв.)")
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')
    await message.answer(f"✍️ Текст сохранён! ({text_len} симв.)\n\nНажми Вперёд к кнопкам ▶️",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard())

# ==================== БИБЛИОТЕКА КНОПОК ====================

@dp.message(F.text == "📚 Мои кнопки")
async def cmd_my_buttons(message: types.Message):
    logger.info(f"👤 User {message.from_user.id} открыл библиотеку кнопок")
    buttons = get_saved_buttons(message.from_user.id)
    
    if not buttons:
        await message.answer("📚 У тебя пока нет сохранённых кнопок.\n\nСоздай пост и добавь первую кнопку!",
                           reply_markup=main_keyboard())
        return
    
    await message.answer("**📚 Твои кнопки:**\n\nНажимай на кнопки ниже, чтобы выбрать:",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=library_keyboard(buttons))

@dp.message(PostWorkflow.writing_text, F.text == "Вперёд к кнопкам ▶️")
@dp.message(F.text == "📚 Выбрать из библиотеки")
async def open_library(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} открыл библиотеку для выбора")
    buttons = get_saved_buttons(message.from_user.id)
    
    if not buttons:
        await message.answer("📚 Пока нет кнопок. Добавь новую или нажми ✅ Готово",
                           reply_markup=post_creation_keyboard())
        return
    
    # Получаем уже выбранные кнопки из черновика
    data = await state.get_data()
    existing = data.get('buttons', [])
    selected_ids = {btn['id'] for btn in existing}
    
    await message.answer("**📚 Выбери кнопки для поста:**\n\n✅ — выбрана, 🔘 — нет",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=library_keyboard(buttons, selected_ids))

@dp.callback_query(lambda c: c.data.startswith('lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    action = parts[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал callback: {callback.data}")
    
    if action == 'toggle':
        button_id = int(parts[2])
        buttons = get_saved_buttons(user_id)
        btn = next((b for b in buttons if b['id'] == button_id), None)
        
        if not btn:
            await callback.answer("❌ Кнопка не найдена", show_alert=True)
            return
        
        # Получаем текущий выбор
        data = await state.get_data()
        selected = set(data.get('temp_selected', []))
        
        if button_id in selected:
            selected.remove(button_id)
            await callback.answer(f"❌ Убрано: {btn['text'][:20]}")
        else:
            selected.add(button_id)
            await callback.answer(f"✅ Выбрано: {btn['text'][:20]}")
        
        await state.update_data(temp_selected=list(selected))
        
        # Обновляем отображение
        all_buttons = get_saved_buttons(user_id)
        existing = data.get('buttons', [])
        existing_ids = {b['id'] for b in existing}
        combined_selected = existing_ids | selected
        
        await callback.message.edit_reply_markup(
            reply_markup=library_keyboard(all_buttons, combined_selected)
        )
    
    elif action == 'apply':
        data = await state.get_data()
        selected_ids = data.get('temp_selected', [])
        all_buttons = get_saved_buttons(user_id)
        
        selected_buttons = [b for b in all_buttons if b['id'] in selected_ids]
        
        # Добавляем к существующим
        existing = data.get('buttons', [])
        existing.extend([[btn] for btn in selected_buttons])
        
        await state.update_data(buttons=existing, temp_selected=[])
        await callback.message.delete()
        
        # Показываем предпросмотр
        await show_preview(callback.message, state)
        
        await callback.message.answer(f"✅ Добавлено {len(selected_buttons)} кнопок!",
                                     reply_markup=post_creation_keyboard())
        await callback.answer()
    
    elif action == 'clear':
        await state.update_data(temp_selected=[])
        buttons = get_saved_buttons(user_id)
        data = await state.get_data()
        existing = data.get('buttons', [])
        existing_ids = {b['id'] for b in existing}
        await callback.message.edit_reply_markup(
            reply_markup=library_keyboard(buttons, existing_ids)
        )
        await callback.answer("🔄 Выбор сброшен")
    
    elif action == 'back':
        await callback.message.delete()
        await callback.message.answer("Продолжай добавление кнопок или нажми ✅ Готово",
                                     reply_markup=post_creation_keyboard())
        await callback.answer()

# ==================== ПРЕДПРОСМОТР ====================

async def show_preview(message: types.Message, state: FSMContext):
    """Показывает предпросмотр поста с кнопками"""
    data = await state.get_data()
    text = data.get('text', '')
    buttons = data.get('buttons', [])
    
    if not buttons:
        return
    
    builder = InlineKeyboardBuilder()
    for row in buttons:
        for btn in row:
            builder.button(text=btn['text'], url=btn['url'])
    builder.adjust(1)
    
    if text:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(" ", reply_markup=builder.as_markup())

# ==================== ЗАВЕРШЕНИЕ ====================

@dp.message(PostWorkflow.writing_text, F.text == "✅ Готово с кнопками")
@dp.message(F.text == "✅ Готово")
async def finish_post(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} завершил создание поста")
    
    data = await state.get_data()
    text = data.get('text', '')
    buttons = data.get('buttons', [])
    
    # Показываем финальный пост
    if buttons:
        builder = InlineKeyboardBuilder()
        for row in buttons:
            for btn in row:
                builder.button(text=btn['text'], url=btn['url'])
        builder.adjust(1)
        kb = builder.as_markup()
    else:
        kb = None
    
    if text:
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif kb:
        await message.answer(" ", reply_markup=kb)
    
    await message.answer("✅ **Пост готов!**\n\n📤 Переслать вручную: нажмите на сообщение → Переслать",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard())
    
    await state.clear()
    delete_draft(message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'manual':
        await callback.message.answer("📤 **Переслать вручную**\n\n1. Нажмите на сообщение выше\n2. Выберите «Переслать»\n3. Выберите чат")
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 В разработке", show_alert=True)

# ==================== ЗАПУСК ====================

async def main():
    logger.info("="*60)
    logger.info("🚀 ПОСТ-ТРИУМФ ЗАПУСКАЕТСЯ")
    logger.info(f"🤖 Bot ID: {bot.id}")
    logger.info("="*60)
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
