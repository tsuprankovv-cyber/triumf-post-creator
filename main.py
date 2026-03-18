# -*- coding: utf-8 -*-
import os, logging, json, re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from states import PostWorkflow, AddButtonSteps
from keyboards import (
    main_keyboard, cancel_keyboard, post_creation_keyboard,
    media_navigation_keyboard, text_navigation_keyboard, library_keyboard, final_keyboard
)
from database import init_db, save_button, get_saved_buttons, delete_button, save_draft, get_draft, delete_draft

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Нет токена! Добавьте BOT_TOKEN в переменные окружения.")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === ИНИЦИАЛИЗАЦИЯ ===
init_db()

logger.info("="*60)
logger.info("🚀 ПОСТ-ТРИУМФ ЗАПУСКАЕТСЯ")
logger.info(f"🤖 Bot ID: {bot.id}")
logger.info("="*60)

# ==================== СТАРТ И МЕНЮ ====================

@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 **Пост-Триумф** — Конструктор постов\n\n"
        "➕ **Новый пост** — создать пост по шагам\n"
        "📚 **Мои кнопки** — библиотека кнопок\n"
        "❓ **Помощь** — эта инструкция",
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} отменил действие")
    await state.clear()
    delete_draft(message.from_user.id)
    await message.answer("❌ Действие отменено.", reply_markup=main_keyboard())

# ==================== ШАГ 1: МЕДИА ====================

@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал создание поста")
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer(
        "📷 **ШАГ 1: Медиа**\n\n"
        "Отправьте фото или видео для поста.\n"
        "Если медиа не нужно, нажмите кнопку ниже ⬇️",
        reply_markup=media_navigation_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith('media:'))
async def media_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    
    if action == 'skip':
        logger.info(f"👤 User {user_id} пропустил медиа")
        await state.update_data(media_type=None, media_id=None)
        save_draft(user_id, {}, 'selecting_media')
        await goto_text_step(callback.message, state, user_id)
        await callback.answer("⏭️ Пропущено")
        
    elif action == 'done':
        data = await state.get_data()
        if data.get('media_id'):
            logger.info(f"👤 User {user_id} завершил шаг медиа")
            await goto_text_step(callback.message, state, user_id)
            await callback.answer("✅ Переход к тексту")
        else:
            await callback.answer("⚠️ Сначала отправьте фото/видео или нажмите 'Пропустить'", show_alert=True)

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': media_id}, 'selecting_media')
    await goto_text_step(message, state, message.from_user.id)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': media_id}, 'selecting_media')
    await goto_text_step(message, state, message.from_user.id)

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПЕРЕХОДА К ТЕКСТУ ---
async def goto_text_step(target_message, state: FSMContext, user_id: int):
    await state.set_state(PostWorkflow.writing_text)
    data = await state.get_data()
    current_text = data.get('text', "")
    
    if current_text:
        txt = (
            "✍️ **ШАГ 2: Текст поста**\n\n"
            "✅ Текст уже сохранён:\n"
            f"_{current_text[:200]}{'...' if len(current_text)>200 else ''}_\n\n"
            "🔹 Чтобы **изменить**: просто отправьте новый текст сообщением.\n"
            "🔹 Чтобы **оставить как есть**: нажмите «Вперёд к кнопкам ▶️».\n"
            "🔹 Чтобы **исправить ошибку**: нажмите «✏️ Изменить текст».",
            parse_mode=ParseMode.MARKDOWN
        )
        kb = text_navigation_keyboard()
    else:
        txt = (
            "✍️ **ШАГ 2: Текст поста**\n\n"
            "Напишите текст вашего поста.\n\n"
            "💡 **Поддерживается форматирование:**\n"
            "`**жирный**` → **жирный**\n"
            "`*курсив*` → *курсив*\n"
            "`__подчёркнутый__` → __подчёркнутый__\n\n"
            "📝 Пример:\n`Привет! Это **важный** пост.`",
            parse_mode=ParseMode.MARKDOWN
        )
        kb = text_navigation_keyboard()
    
    await target_message.answer(txt, reply_markup=kb)

# ==================== ШАГ 2: ТЕКСТ (НАВИГАЦИЯ) ====================

@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    
    if action == 'back_to_media':
        await state.set_state(PostWorkflow.selecting_media)
        data = await state.get_data()
        has_media = bool(data.get('media_id'))
        
        txt = "📷 **Редактирование медиа**\n\n"
        if has_media:
            txt += "✅ Фото/видео загружено.\nОтправьте новое, чтобы заменить, или нажмите «Пропустить»."
        else:
            txt += "Медиа не выбрано."
            
        await callback.message.edit_text(txt, reply_markup=media_navigation_keyboard())
        await callback.answer()
        
    elif action == 'next_to_buttons':
        await callback.message.answer(
            "🔘 **ШАГ 3: Кнопки**\n\n"
            "Добавьте кнопки под постом для переходов.\n"
            "Выберите удобный способ:",
            reply_markup=post_creation_keyboard()
        )
        await callback.answer()
        
    elif action == 'edit_mode':
        await callback.message.answer(
            "✏️ **Редактирование текста**\n\n"
            "Отправьте новый текст, чтобы заменить текущий.\n"
            "Или нажмите «Отмена», если передумали.",
            reply_markup=cancel_keyboard()
        )
        await callback.answer("Жду ваш текст...")

# ==================== ОБРАБОТКА ТЕКСТА И БЫСТРЫЙ ВВОД КНОПОК ====================
# 🔥 ЭТА ФУНКЦИЯ ЗАМЕНЯЕТ СТАРУЮ handle_text

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_and_quick_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # --- РЕЖИМ 1: БЫСТРЫЙ ВВОД КНОПОК (СПИСКОМ) ---
    if data.get('waiting_for_quick_buttons'):
        if message.text == "❌ Отмена":
            await state.update_data(waiting_for_quick_buttons=False)
            await cmd_cancel(message, state)
            return

        lines = message.text.strip().split('\n')
        created_count = 0
        
        logger.info(f"👤 User {message.from_user.id} пытается быстрый ввод кнопок: {len(lines)} строк")
        
        for line in lines:
            # Ищем разделитель " - " (пробел-тире-пробел) или просто "-"
            if ' - ' in line:
                parts = line.split(' - ', 1)
            elif '-' in line:
                parts = line.split('-', 1)
            else:
                continue # Пропускаем строки без разделителя
                
            if len(parts) == 2:
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                # Проверка URL
                if btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
                    if save_button(message.from_user.id, btn_text, btn_url):
                        created_count += 1
                        logger.info(f"✅ Кнопка создана: {btn_text}")
        
        await state.update_data(waiting_for_quick_buttons=False)
        
        if created_count > 0:
            await message.answer(f"✅ **Создано кнопок: {created_count}!**\nОни сохранены в библиотеку.", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer("⚠️ Не удалось распознать ни одной кнопки.\nПроверьте формат: `Текст - Ссылка`", parse_mode=ParseMode.MARKDOWN)
        
        await message.answer("🔘 **МЕНЮ КНОПОК**\nЧто делаем дальше?", reply_markup=post_creation_keyboard())
        return

    # --- РЕЖИМ 2: ОБЫЧНЫЙ ТЕКСТ ПОСТА ---
    
    # Игнорируем нажатия кнопок меню (если они вдруг пришли текстом)
    ignore_texts = [
        "◀️ Назад к медиа", "Вперёд к кнопкам ▶️", "✏️ Изменить текст", 
        "➕ Добавить новую (по шагам)", "⚡ Быстрый ввод (списком)", 
        "📚 Выбрать из библиотеки", "✅ Готово с кнопками"
    ]
    if message.text in ignore_texts:
        return
        
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    text_len = len(message.text)
    logger.info(f"👤 User {message.from_user.id} сохранил текст поста ({text_len} симв.)")
    
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')
    
    await message.answer(
        f"✅ **Текст сохранён!** ({text_len} симв.)\n\n"
        f"Теперь выберите действие с кнопками:",
        reply_markup=post_creation_keyboard()
    )

# ==================== ШАГ 3: КНОПКИ (ЛОГИКА) ====================

@dp.message(F.text == "📚 Мои кнопки")
async def cmd_my_buttons(message: types.Message):
    buttons = get_saved_buttons(message.from_user.id)
    if not buttons:
        await message.answer("📚 Ваша библиотека пуста.", reply_markup=main_keyboard())
        return
    await message.answer("**📚 Ваши сохранённые кнопки:**", parse_mode=ParseMode.MARKDOWN, reply_markup=library_keyboard(buttons))

# --- РЕЖИМ А: ПОШАГОВОЕ СОЗДАНИЕ ---
@dp.message(F.text == "➕ Добавить новую (по шагам)")
async def start_add_button_step(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал пошаговое добавление кнопки")
    await state.update_data(new_btn_text=None, new_btn_url=None)
    await state.set_state(AddButtonSteps.waiting_for_text)
    
    await message.answer(
        "🔘 **СОЗДАНИЕ КНОПКИ (ПО ШАГАМ)**\n\n"
        "1️⃣ Введите **название (текст)** кнопки.\n\n"
        "📝 *Пример:* `Наш сайт`, `Заказать`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def process_button_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    btn_text = message.text.strip()
    if len(btn_text) > 50:
        await message.answer("⚠️ Текст слишком длинный. Попробуйте короче.")
        return

    await state.update_data(new_btn_text=btn_text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    
    await message.answer(
        f"✅ Название принято: **«{btn_text}»**\n\n"
        "2️⃣ Теперь введите **ссылку**.\n\n"
        "🔗 *Пример:* `https://mysite.ru`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def process_button_url(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text')
    btn_url = message.text.strip()
    
    if not btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Ошибка: Ссылка должна начинаться с `http://`, `https://`, `t.me/`.\nПопробуйте ещё раз:", reply_markup=cancel_keyboard())
        return
    
    if save_button(message.from_user.id, btn_text, btn_url):
        await message.answer(f"🎉 **Кнопка создана!**\n📝 `{btn_text}`\n🔗 `{btn_url}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("⚠️ Такая кнопка уже есть.", parse_mode=ParseMode.MARKDOWN)
    
    await state.set_state(None) 
    await state.update_data(new_btn_text=None, new_btn_url=None)
    await message.answer("🔘 **МЕНЮ КНОПОК**\nЧто делаем дальше?", reply_markup=post_creation_keyboard())

# --- РЕЖИМ Б: БЫСТРЫЙ ВВОД ---
@dp.message(F.text == "⚡ Быстрый ввод (списком)")
async def start_quick_add(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал быстрый ввод кнопок")
    # Устанавливаем флаг, что ждем быстрый ввод
    await state.update_data(waiting_for_quick_buttons=True)
    
    await message.answer(
        "⚡ **БЫСТРЫЙ ВВОД КНОПОК**\n\n"
        "Отправьте список кнопок в формате:\n"
        "`Текст кнопки - Ссылка`\n\n"
        "Можно сразу несколько, каждая с новой строки:\n\n"
        "📝 *Пример:* \n"
        "`Подобрать тур - https://vCard.guru/olga.tsuprankova`\n"
        "`Оставить заявку - https://forms.yandex.ru/...`\n\n"
        "❌ Отмена — выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard()
    )

# --- ВЫБОР ИЗ БИБЛИОТЕКИ ---
@dp.message(F.text == "📚 Выбрать из библиотеки")
async def open_library_for_post(message: types.Message, state: FSMContext):
    buttons = get_saved_buttons(message.from_user.id)
    if not buttons:
        await message.answer("📚 Библиотека пуста. Создайте кнопки через «➕ Добавить новую» или «⚡ Быстрый ввод».", reply_markup=post_creation_keyboard())
        return
    
    data = await state.get_data()
    temp_selected = set(data.get('temp_selected', []))
    
    await message.answer(
        "**📚 ВЫБОР КНОПОК**\n\n"
        "Нажимайте на кнопки ниже, чтобы выбрать их (появится ✅).\n"
        "Когда выберете все нужные, нажмите «✅ Применить выбранные».",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=library_keyboard(buttons, temp_selected)
    )

@dp.callback_query(lambda c: c.data.startswith('lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    action = parts[1]
    user_id = callback.from_user.id
    
    if action == 'toggle':
        button_id = int(parts[2])
        buttons = get_saved_buttons(user_id)
        btn = next((b for b in buttons if b['id'] == button_id), None)
        if not btn: return
        
        data = await state.get_data()
        selected = set(data.get('temp_selected', []))
        
        if button_id in selected:
            selected.remove(button_id)
            msg = f"❌ Убрано: {btn['text']}"
        else:
            selected.add(button_id)
            msg = f"✅ Выбрано: {btn['text']}"
        
        await state.update_data(temp_selected=list(selected))
        all_buttons = get_saved_buttons(user_id)
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(all_buttons, selected))
        await callback.answer(msg)

    elif action == 'apply':
        data = await state.get_data()
        selected_ids = data.get('temp_selected', [])
        all_buttons = get_saved_buttons(user_id)
        selected_buttons = [b for b in all_buttons if b['id'] in selected_ids]
        
        if not selected_buttons:
            await callback.answer("⚠️ Вы не выбрали ни одной кнопки!", show_alert=True)
            return

        existing = data.get('buttons', [])
        existing.extend([[btn] for btn in selected_buttons])
        
        await state.update_data(buttons=existing, temp_selected=[])
        await callback.message.delete()
        
        builder = types.InlineKeyboardBuilder()
        for row in existing:
            for b in row:
                builder.button(text=b['text'], url=b['url'])
        builder.adjust(1)
        
        await callback.message.answer("✅ Кнопки добавлены к посту!", reply_markup=builder.as_markup())
        await callback.message.answer("Продолжайте или нажмите **✅ Готово с кнопками**", reply_markup=post_creation_keyboard())
        await callback.answer()
        
    elif action == 'back':
        await callback.message.delete()
        await callback.message.answer("🔘 **МЕНЮ КНОПОК**", reply_markup=post_creation_keyboard())
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
        
    await message.answer(
        "✅ **Пост готов к публикации!**\n\n"
        "📤 **Как отправить:**\n"
        "1. Нажмите на сообщение с постом выше 👆\n"
        "2. Выберите «Переслать»\n"
        "3. Выберите нужный чат",
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=final_keyboard()
    )
    
    await state.clear()
    delete_draft(message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'manual':
        await callback.message.answer("📤 **Инструкция:**\n1. Найди пост выше 👆\n2. Нажми «Переслать»\n3. Выбери чат")
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 В разработке", show_alert=True)

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
