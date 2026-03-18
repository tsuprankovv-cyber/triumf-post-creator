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

# ==================== ШАГ 1: МЕДИА ====================

@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    logger.info(f"👤 User {message.from_user.id} начал создание поста")
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer("📝 **Шаг 1: Медиа**\n\nОтправь фото/видео или нажми ⏭️ Пропустить",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=media_navigation_keyboard())

@dp.callback_query(lambda c: c.data.startswith('media:'))
async def media_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    logger.info(f"👤 User {user_id} нажал кнопку медиа: {action}")
    
    if action == 'skip':
        await state.update_data(media_type=None, media_id=None)
        save_draft(user_id, {}, 'selecting_media')
        await goto_text_step(callback.message, state, user_id)
        await callback.answer("⏭️ Пропущено")
        
    elif action == 'done':
        data = await state.get_data()
        if data.get('media_id'):
            await goto_text_step(callback.message, state, user_id)
            await callback.answer("✅ Готово! Переход к тексту.")
        else:
            await callback.answer("⚠️ Сначала отправь фото или нажми 'Пропустить'", show_alert=True)

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

# Вспомогательная функция перехода к тексту (с показом черновика!)
async def goto_text_step(target_message, state: FSMContext, user_id: int):
    await state.set_state(PostWorkflow.writing_text)
    data = await state.get_data()
    current_text = data.get('text', "")
    
    if current_text:
        txt = f"✍️ **Шаг 2: Текст**\n\n📝 *Текущий текст:*\n_{current_text[:100]}{'...' if len(current_text)>100 else ''}_\n\nОтправь **новый текст**, чтобы заменить, или нажми **Вперёд к кнопкам ▶️**"
    else:
        txt = "✍️ **Шаг 2: Текст**\n\nНапиши текст поста:\n(поддерживается **жирный**, *курсив*)\n\nИли нажми **Вперёд к кнопкам ▶️**"
    
    await target_message.answer(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard())

# ==================== ШАГ 2: ТЕКСТ (С УЧЕТОМ ЧЕРНОВИКА) ====================

@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    user_id = callback.from_user.id
    
    if action == 'back_to_media':
        await state.set_state(PostWorkflow.selecting_media)
        data = await state.get_data()
        has_media = bool(data.get('media_id'))
        
        txt = "📎 **Редактирование медиа**\n\n"
        if has_media:
            txt += "📸 Фото/видео уже загружено.\nОтправь новое, чтобы заменить, или нажми ⏭️ Пропустить."
        else:
            txt += "Медиа не выбрано.\nОтправь фото/видео или нажми ⏭️ Пропустить."
            
        await callback.message.edit_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=media_navigation_keyboard())
        await callback.answer()
        
    elif action == 'next_to_buttons':
        # Переход к меню кнопок
        await callback.message.answer("📚 **Шаг 3: Кнопки**\n\nВыберите действие:",
                                     reply_markup=post_creation_keyboard())
        await callback.answer()

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text(message: types.Message, state: FSMContext):
    # Игнорируем нажатия кнопок навигации (они обрабатываются в callback)
    if message.text in ["◀️ Назад к медиа", "Вперёд к кнопкам ▶️"]:
        return
    
    text_len = len(message.text)
    logger.info(f"👤 User {message.from_user.id} обновил текст ({text_len} симв.)")
    
    # Сохраняем новый текст
    await state.update_data(text=message.text)
    save_draft(message.from_user.id, {'text': message.text}, 'writing_text')
    
    await message.answer(f"✅ **Текст обновлён!** ({text_len} симв.)\n\nНажми **Вперёд к кнопкам ▶️**",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard())

# ==================== ШАГ 3: КНОПКИ (ПОШАГОВО) ====================

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
    # Сбрасываем временные данные кнопки
    await state.set_state(AddButtonSteps.waiting_for_text)
    await state.update_data(new_btn_text=None, new_btn_url=None)
    await message.answer("🔘 **Создание кнопки**\n\nВыберите режим:",
                        reply_markup=add_button_mode_keyboard())

# --- Режим: По шагам ---
@dp.message(F.text == "➕ По шагам (текст → ссылка)")
async def start_step_by_step(message: types.Message, state: FSMContext):
    await state.set_state(AddButtonSteps.waiting_for_text)
    await message.answer("1️⃣ **Введи ТЕКСТ кнопки**\n\n(Например: `Наш сайт`, `Заказать`)\n\n❌ Отмена — выйти",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def process_button_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    # Сохраняем текст во временное хранилище
    await state.update_data(new_btn_text=message.text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    
    await message.answer(f"2️⃣ **Введи ССЫЛКУ** для кнопки «{message.text}»\n\n(Например: `https://mysite.ru`)\n\n❌ Отмена — выйти",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def process_button_url(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cmd_cancel(message, state)
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text')
    btn_url = message.text.strip()
    
    # Валидация URL
    if not btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Ошибка: Ссылка должна начинаться с `http://`, `https://` или `t.me/`.\n\nПопробуй ещё раз:",
                            reply_markup=cancel_keyboard())
        return
    
    # Сохраняем в БД
    if save_button(message.from_user.id, btn_text, btn_url):
        await message.answer(f"✅ **Кнопка сохранена в библиотеку!**\n\n📝 Текст: `{btn_text}`\n🔗 Ссылка: `{btn_url}`",
                            parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("⚠️ Такая кнопка уже есть в библиотеке.", parse_mode=ParseMode.MARKDOWN)
    
    # Очищаем состояние создания кнопки
    await state.set_state(None) 
    await state.update_data(new_btn_text=None, new_btn_url=None)
    
    # Возвращаем в меню добавления кнопок поста
    await message.answer("📚 **Добавление кнопок к посту**\n\nВыберите действие:",
                        reply_markup=post_creation_keyboard())

# --- Режим: Быстро (заглушка) ---
@dp.message(F.text == "⚡ Быстро (текст - ссылка)")
async def start_fast_add(message: types.Message, state: FSMContext):
    await message.answer("⚡ **Быстрое добавление**\n\nПока доступен только режим **'По шагам'**. Выберите его выше.",
                        reply_markup=add_button_mode_keyboard())

# --- Выбор из библиотеки ---
@dp.message(F.text == "📚 Выбрать из библиотеки")
async def open_library_for_post(message: types.Message, state: FSMContext):
    buttons = get_saved_buttons(message.from_user.id)
    if not buttons:
        await message.answer("📚 Библиотека пуста. Сначала создайте кнопки через '➕ Добавить новую'.", 
                             reply_markup=post_creation_keyboard())
        return
    
    data = await state.get_data()
    temp_selected = set(data.get('temp_selected', []))
    
    await message.answer("**📚 Выбери кнопки из библиотеки:**\n✅ — выбрана, 🔘 — нет",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=library_keyboard(buttons, temp_selected))

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
        
        # Предпросмотр
        builder = types.InlineKeyboardBuilder()
        for row in existing:
            for b in row:
                builder.button(text=b['text'], url=b['url'])
        builder.adjust(1)
        
        await callback.message.answer("✅ Кнопки добавлены к посту!", reply_markup=builder.as_markup())
        await callback.message.answer("Продолжайте добавлять или нажмите **✅ Готово с кнопками**", 
                                      reply_markup=post_creation_keyboard())
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
    
    # Показываем финальный пост
    if text:
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif kb:
        await message.answer(" ", reply_markup=kb)
        
    await message.answer("✅ **Пост готов к публикации!**\n\n📤 **Как отправить:**\n1. Нажми на сообщение с постом выше\n2. Выбери «Переслать»\n3. Выбери нужный чат",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard())
    
    # Очищаем состояние
    await state.clear()
    delete_draft(message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_callback(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'manual':
        await callback.message.answer("📤 **Инструкция:**\n1. Найди сообщение с постом выше 👆\n2. Нажми на него (или ПКМ)\n3. Выбери «Переслать»\n4. Выбери чат назначения")
        await callback.answer()
    elif action == 'anonymous':
        await callback.answer("👻 Анонимная отправка будет доступна после настройки прав администратора в группе.", show_alert=True)

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
