# -*- coding: utf-8 -*-
import os, logging, json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from states import PostWorkflow, AddButtonSteps
from keyboards import (
    main_keyboard, cancel_keyboard, post_creation_keyboard, add_button_mode_keyboard,
    media_navigation_keyboard, text_navigation_keyboard, library_keyboard, final_keyboard
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

# ==================== СТАРТ И МЕНЮ ====================

@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    await message.answer("🤖 **Пост-Триумф**\n\n➕ Новый пост | 📚 Мои кнопки | ❓ Помощь",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} отменил действие")
    await state.clear()
    delete_draft(message.from_user.id)
    await message.answer("❌ Отменено", reply_markup=main_keyboard())

# ==================== ШАГ 1: МЕДИА (ИСПРАВЛЕНО) ====================

@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал создание поста")
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer("📝 **Шаг 1: Медиа**\n\nОтправь фото/видео или нажми ⏭️ Пропустить",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=media_navigation_keyboard())

# 🔧 ОБРАБОТЧИК КНОПОК МЕДИА (ТЕПЕРЬ РАБОТАЕТ!)
@dp.callback_query(lambda c: c.data.startswith('media:'))
async def media_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал кнопку медиа: {action}")
    
    if action == 'skip':
        await state.update_data(media_type=None, media_id=None)
        save_draft(user_id, {}, 'selecting_media')
        await state.set_state(PostWorkflow.writing_text)
        await callback.message.edit_text("⏭️ **Пропущено!**\n\nНапиши текст:",
                                        parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=text_navigation_keyboard())
        await callback.answer("⏭️ Пропущено")
        
    elif action == 'done':
        data = await state.get_data()
        if data.get('media_id'):
            await state.set_state(PostWorkflow.writing_text)
            await callback.answer("✅ Готово! Пиши текст.")
        else:
            await callback.answer("⚠️ Сначала отправь фото или нажми 'Пропустить'", show_alert=True)

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': media_id}, 'selecting_media')
    await message.answer("📸 Фото! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': media_id}, 'selecting_media')
    await message.answer("🎬 Видео! Теперь напиши текст:", reply_markup=text_navigation_keyboard())
    await state.set_state(PostWorkflow.writing_text)

# ==================== ШАГ 2: ТЕКСТ ====================

@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    if action == 'back_to_media':
        await state.set_state(PostWorkflow.selecting_media)
        await callback.message.edit_text("📎 **Редактирование медиа:**",
                                        parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=media_navigation_keyboard())
        await callback.answer()
    elif action == 'next_to_buttons':
        data = await state.get_data()
        if not data.get('text'):
             await callback.answer("❌ Сначала введи текст!", show_alert=True)
             return
        await callback.message.answer("📚 **Добавление кнопок**\n\nВыберите действие:",
                                     reply_markup=post_creation_keyboard())
        await callback.answer()

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    # Игнорируем системные команды, если они вдруг пришли текстом
    if message.text in ["◀️ Назад к медиа", "Вперёд к кнопкам ▶️"]:
        return
    
    text_len = len(message.text)
    logger.info(f"👤 User {message.from_user.id} отправил текст ({text_len} симв.)")
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')
    await message.answer(f"✍️ Текст сохранён! ({text_len} симв.)\n\nНажми Вперёд к кнопкам ▶️",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard())

# ==================== ШАГ 3: КНОПКИ (НОВАЯ ЛОГИКА) ====================

@dp.message(F.text == "📚 Мои кнопки")
async def cmd_my_buttons(message: types.Message):
    buttons = get_saved_buttons(message.from_user.id)
    if not buttons:
        await message.answer("📚 Пока нет кнопок.", reply_markup=main_keyboard())
        return
    await message.answer("**📚 Твои кнопки:**", parse_mode=ParseMode.MARKDOWN,
                        reply_markup=library_keyboard(buttons))

@dp.message(F.text == "➕ Добавить новую")
async def start_add_button(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал добавление кнопки")
    await message.answer("🔘 **Создание кнопки**\n\nКак хочешь добавить?",
                        reply_markup=add_button_mode_keyboard())

# --- Режим: По шагам ---
@dp.message(F.text == "➕ По шагам (текст → ссылка)")
async def start_step_by_step(message: types.Message, state: FSMContext):
    await state.set_state(AddButtonSteps.waiting_for_text)
    await message.answer("1️⃣ **Введи ТЕКСТ кнопки**\n\n(Например: *Наш сайт*, *Заказать*)",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def process_button_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    await state.update_data(new_btn_text=message.text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    await message.answer(f"2️⃣ **Введи ССЫЛКУ** для кнопки «{message.text}»\n\n(Например: `https://mysite.ru`)",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def process_button_url(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text')
    btn_url = message.text.strip()
    
    if not btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Ссылка должна начинаться с `http://`, `https://` или `t.me/`.\nПопробуй ещё раз:",
                            reply_markup=cancel_keyboard())
        return
    
    if save_button(message.from_user.id, btn_text, btn_url):
        await message.answer(f"✅ **Кнопка сохранена!**\n\n📝 Текст: `{btn_text}`\n🔗 Ссылка: `{btn_url}`",
                            parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("⚠️ Такая кнопка уже есть.", parse_mode=ParseMode.MARKDOWN)
    
    await state.clear()
    await message.answer("📚 **Добавление кнопок**\n\nВыберите действие:",
                        reply_markup=post_creation_keyboard())

# --- Режим: Быстро (заготовка) ---
@dp.message(F.text == "⚡ Быстро (текст - ссылка)")
async def start_fast_add(message: types.Message, state: FSMContext):
    await message.answer("⚡ **Быстрое добавление**\n\nФормат: `Текст - Ссылка`\n\n(Пока работает только режим 'По шагам')",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=post_creation_keyboard())

# --- Выбор из библиотеки ---
@dp.message(F.text == "📚 Выбрать из библиотеки")
async def open_library_for_post(message: types.Message, state: FSMContext):
    buttons = get_saved_buttons(message.from_user.id)
    if not buttons:
        await message.answer("📚 Пока нет кнопок.", reply_markup=post_creation_keyboard())
        return
    
    data = await state.get_data()
    # Собираем уже выбранные ID
    existing_rows = data.get('buttons', [])
    selected_ids = set()
    for row in existing_rows:
        # Нам нужно найти ID кнопки по тексту/URL, так как в черновике хранятся только данные
        # Для упрощения пока просто показываем все, а выбор делаем заново или храним ID в temp_selected
        pass 
        
    # Берем временный выбор из состояния
    temp_selected = set(data.get('temp_selected', []))
    
    await message.answer("**📚 Выбери кнопки:**\n✅ — выбрана, 🔘 — нет",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=library_keyboard(buttons, temp_selected))

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
        if not btn: return
        
        data = await state.get_data()
        selected = set(data.get('temp_selected', []))
        
        if button_id in selected:
            selected.remove(button_id)
            await callback.answer(f"❌ Убрано: {btn['text']}")
        else:
            selected.add(button_id)
            await callback.answer(f"✅ Выбрано: {btn['text']}")
        
        await state.update_data(temp_selected=list(selected))
        
        all_buttons = get_saved_buttons(user_id)
        # Объединяем с уже примененными (для визуализации)
        existing_rows = data.get('buttons', [])
        existing_ids = set() 
        # (Упрощенная логика отображения)
        
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(all_buttons, selected))

    elif action == 'apply':
        data = await state.get_data()
        selected_ids = data.get('temp_selected', [])
        all_buttons = get_saved_buttons(user_id)
        selected_buttons = [b for b in all_buttons if b['id'] in selected_ids]
        
        existing = data.get('buttons', [])
        existing.extend([[btn] for btn in selected_buttons])
        
        await state.update_data(buttons=existing, temp_selected=[])
        await callback.message.delete()
        
        # Предпросмотр
        builder = types.InlineKeyboardBuilder()
        for row in existing:
            for b in row:
                builder.button(text=b['text'], url=b['url'])
        builder.adjust(1)
        await callback.message.answer("✅ Кнопки добавлены!", reply_markup=builder.as_markup())
        await callback.message.answer("Продолжайте или нажмите ✅ Готово", reply_markup=post_creation_keyboard())
        await callback.answer()
        
    elif action == 'back':
        await callback.message.delete()
        await callback.message.answer("📚 **Добавление кнопок**", reply_markup=post_creation_keyboard())
        await callback.answer()

# ==================== ФИНАЛ ====================

@dp.message(F.text == "✅ Готово с кнопками")
async def finish_post(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data.get('text', '')
    buttons = data.get('buttons', [])
    
    kb = None
    if buttons:
        builder = types.InlineKeyboardBuilder()
        for row in buttons:
            for btn in row:
                builder.button(text=btn['text'], url=btn['url'])
        builder.adjust(1)
        kb = builder.as_markup()
    
    if text:
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif kb:
        await message.answer(" ", reply_markup=kb)
        
    await message.answer("✅ **Пост готов!**\n\n📤 Переслать вручную: нажмите на сообщение выше → Переслать",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard())
    await state.clear()
    delete_draft(message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'manual':
        await callback.message.answer("📤 **Инструкция:**\n1. Нажми на пост выше\n2. Выбери 'Переслать'\n3. Выбери чат")
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 В разработке", show_alert=True)

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
