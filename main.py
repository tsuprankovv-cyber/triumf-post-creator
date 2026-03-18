# -*- coding: utf-8 -*-
import os, logging, json, re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from states import PostWorkflow, AddButtonSteps
from keyboards import main_keyboard, cancel_keyboard, post_creation_keyboard, get_preview_keyboard, library_keyboard
from database import init_db, save_button, get_saved_buttons, delete_button, save_draft, get_draft, delete_draft
from smart_text import smart_format_text, remove_emojis, remove_formatting

# Настройка логов
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

# Хранилище ID сообщения предпросмотра: {user_id: message_id}
preview_messages = {} 

async def update_preview(message: types.Message, state: FSMContext, force_new: bool = False):
    """Обновляет или создает сообщение предпросмотра"""
    user_id = message.from_user.id
    
    # Проверка: не бот ли это?
    if user_id < 0: # Это группа
        logger.warning("Попытка работы в группе. Live Preview работает только в ЛС.")
        return

    data = await state.get_data()
    
    step = data.get('step', 'media')
    text_content = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    
    # Формируем текст
    if not text_content:
        caption = "_(Нажмите ✏️ Править текст, чтобы добавить описание)_\n\nЗдесь будет ваш продающий пост."
    else:
        caption = text_content
        
    has_formatted = data.get('original_text') and data.get('original_text') != text_content
    control_kb = get_preview_keyboard(step, bool(text_content), has_formatted)
    
    try:
        msg_id = preview_messages.get(user_id)
        
        if msg_id and not force_new:
            # РЕДАКТИРУЕМ
            if media_type == 'photo' and media_id:
                try:
                    await bot.edit_message_caption(chat_id=user_id, message_id=msg_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                except Exception as e: logger.debug(f"Caption error: {e}")
                await bot.edit_message_reply_markup(chat_id=user_id, message_id=msg_id, reply_markup=control_kb)
            elif media_type == 'video' and media_id:
                try:
                    await bot.edit_message_caption(chat_id=user_id, message_id=msg_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                except Exception as e: logger.debug(f"Caption error: {e}")
                await bot.edit_message_reply_markup(chat_id=user_id, message_id=msg_id, reply_markup=control_kb)
            else:
                await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
        else:
            # СОЗДАЕМ НОВОЕ
            new_msg = None
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(chat_id=user_id, photo=media_id, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(chat_id=user_id, video=media_id, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            else:
                new_msg = await bot.send_message(chat_id=user_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            
            if new_msg:
                preview_messages[user_id] = new_msg.message_id
                logger.info(f"Создано превью для юзера {user_id}, msg_id: {new_msg.message_id}")
                
    except TelegramBadRequest as e:
        if "bot can't send messages to bots" in str(e):
            logger.error("Ошибка: Вы тестируете бота из чата с другим ботом! Откройте ЛС с человеком.")
        else:
            logger.warning(f"Telegram Error: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка превью: {e}", exc_info=True)

# ==================== СТАРТ ====================
@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    logger.info(f"User {message.from_user.id} вызвал старт")
    await message.answer("🤖 **Пост-Триумф Live**\n\nНажмите '➕ Новый пост' для начала.", reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    if uid in preview_messages:
        try: await bot.delete_message(uid, preview_messages[uid])
        except: pass
        del preview_messages[uid]
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    logger.info(f"User {uid} начал новый пост")
    
    # Сброс состояния
    await state.set_state(None) 
    await state.update_data(step='media', text='', media_id=None, media_type=None, buttons=[], original_text=None, ai_keywords=None)
    
    # Удаляем старое превью
    if uid in preview_messages:
        try: await bot.delete_message(uid, preview_messages[uid])
        except: pass
    
    # Создаем новое превью
    await update_preview(message, state, force_new=True)
    await message.answer("ℹ️ **Редактор открыт!**\nИспользуйте кнопки под сообщением выше.", reply_markup=cancel_keyboard())

# ==================== КОНТРОЛЛЕР КНОПОК ====================
@dp.callback_query(lambda c: c.data.startswith('prev:'))
async def preview_controller(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    uid = callback.from_user.id
    data = await state.get_data()
    
    logger.info(f"User {uid} нажал кнопку: {action}. Текущее состояние: {await state.get_state()}, Данные: {data}")

    if action == 'cancel':
        await cmd_cancel(callback.message, state)
        await callback.answer()
        return

    # --- МЕДИА ---
    if action == 'skip_media':
        await state.update_data(media_type=None, media_id=None, step='text')
        await update_preview(callback.message, state)
        await callback.answer("Фото пропущено")
        
    elif action == 'to_text':
        # Разрешаем переход, если медиа нет (пропустили) или есть
        await state.update_data(step='text')
        await update_preview(callback.message, state)
        await callback.answer("Переход к тексту")

    # --- ТЕКСТ ---
    elif action == 'back_media':
        await state.update_data(step='media')
        await update_preview(callback.message, state)
        await callback.answer()

    elif action == 'edit_text':
        raw_text = data.get('text', '')
        if not raw_text:
            # Если текста нет, просим ввести его первым делом
            await state.set_state(PostWorkflow.writing_text)
            await callback.message.answer("✏️ Введите текст поста первым сообщением:")
            await callback.answer()
            return
            
        clean_text = remove_emojis(remove_formatting(raw_text))
        await state.set_state(PostWorkflow.writing_text)
        await callback.message.answer(f"✏️ **Редактирование**\n\nИсправьте текст и отправьте обратно:\n\n_{clean_text[:400]}_", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif action == 'ai_generate':
        await state.set_state(PostWorkflow.ai_input)
        kws = data.get('ai_keywords', '')
        hint = f"\n\nПрошлые ключи: `{kws}`" if kws else ""
        await callback.message.answer(f"🤖 **Генератор**\nВведите ключевые слова через запятую:{hint}", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif action == 'smart_format':
        txt = data.get('text', '')
        if not txt:
            await callback.answer("⚠️ Сначала введите текст!", show_alert=True)
            return
        await state.update_data(smart_variant=0)
        res = smart_format_text(txt, 0)
        await state.update_data(text=res['text'], original_text=txt, smart_variant=0)
        await update_preview(callback.message, state)
        await callback.answer("✨ Готово!")

    elif action == 'smart_next':
        v = data.get('smart_variant', 0) + 1
        orig = data.get('original_text', data.get('text'))
        res = smart_format_text(orig, v)
        await state.update_data(text=res['text'], smart_variant=v)
        await update_preview(callback.message, state)
        await callback.answer("🔄 Вариант изменен")
        
    elif action == 'smart_reset':
        orig = data.get('original_text', '')
        if not orig:
             await callback.answer("Нет исходника", show_alert=True)
             return
        await state.update_data(text=orig, smart_variant=-1)
        await update_preview(callback.message, state)
        await callback.answer("↩️ Сброшено")

    elif action == 'remove_emojis':
        txt = data.get('text', '')
        if not txt: return
        cleaned = remove_emojis(txt)
        await state.update_data(text=cleaned)
        await update_preview(callback.message, state)
        await callback.answer("🧹 Эмодзи удалены")

    elif action == 'remove_format':
        txt = data.get('text', '')
        if not txt: return
        cleaned = remove_formatting(txt)
        await state.update_data(text=cleaned)
        await update_preview(callback.message, state)
        await callback.answer("📄 Формат снят")

    elif action == 'to_buttons':
        if not data.get('text'):
            await callback.answer("⚠️ Введите текст!", show_alert=True)
            return
        await state.update_data(step='buttons')
        await update_preview(callback.message, state)
        await callback.answer("Переход к кнопкам")
        
    # --- КНОПКИ ---
    elif action == 'back_text':
        await state.update_data(step='text')
        await update_preview(callback.message, state)
        await callback.answer()

    elif action == 'add_btn':
        await state.set_state(AddButtonSteps.waiting_for_text)
        await callback.message.answer("➕ **Новая кнопка**\nВведите текст:")
        await callback.answer()
        
    elif action == 'lib_btn':
        btns = get_saved_buttons(uid)
        if not btns:
            await callback.answer("📚 Пусто!", show_alert=True)
            return
        sel = set(data.get('temp_selected', []))
        await callback.message.answer("**📚 Выберите:**", reply_markup=library_keyboard(btns, sel))
        await callback.answer()

    elif action == 'finish':
        await finish_post_process(callback.message, state)
        await callback.answer("✅ Опубликовано!")

# ==================== ОБРАБОТКА ТЕКСТА ОТ ПОЛЬЗОВАТЕЛЯ ====================

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    txt = message.text
    logger.info(f"Получен текст от юзера {message.from_user.id}: {txt[:50]}...")
    
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt, 'original_text': txt}, 'text')
    await state.set_state(None)
    
    await update_preview(message, state)
    await message.delete()
    # Не спамим ответом, просто обновляем превью

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    keywords = message.text.strip()
    await state.update_data(ai_keywords=keywords)
    
    generated_text = generate_ai_text(keywords)
    
    await state.update_data(text=generated_text, original_text=generated_text, smart_variant=-1)
    save_draft(message.from_user.id, {'text': generated_text}, 'text')
    await state.set_state(None)
    
    await update_preview(message, state)
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    await message.answer(f"2️⃣ Ссылка для «{message.text}»:")
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        m = await message.answer("❌ Неверная ссылка.")
        return # Не удаляем, пусть видит ошибку
    
    data = await state.get_data()
    if save_button(message.from_user.id, data['new_btn_text'], url):
        buttons = data.get('buttons', [])
        buttons.append([{'text': data['new_btn_text'], 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(message, state)
        await message.delete()
    else:
        m = await message.answer("⚠️ Уже есть.")

@dp.callback_query(lambda c: c.data.startswith('lib:'))
async def lib_cb(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':'); act = parts[1]; uid = callback.from_user.id
    data = await state.get_data()
    
    if act == 'toggle':
        bid = int(parts[2]); btns = get_saved_buttons(uid)
        btn = next((b for b in btns if b['id'] == bid), None)
        if not btn: return
        sel = set(data.get('temp_selected', []))
        if bid in sel: sel.remove(bid)
        else: sel.add(bid)
        await state.update_data(temp_selected=list(sel))
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(get_saved_buttons(uid), sel))
        await callback.answer()
        
    elif act == 'apply':
        sels = data.get('temp_selected', [])
        all_b = get_saved_buttons(uid); chosen = [b for b in all_b if b['id'] in sels]
        if not chosen: await callback.answer("⚠️ Пусто", show_alert=True); return
        
        buttons = data.get('buttons', [])
        buttons.extend([[b] for b in chosen])
        await state.update_data(buttons=buttons, temp_selected=[])
        await callback.message.delete()
        await update_preview(callback.message, state)
        await callback.message.answer("✅ Добавлено!", delete_after=3)
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        await callback.answer()

# ==================== ФИНАЛ И УТИЛИТЫ ====================

def generate_ai_text(keywords: str) -> str:
    kws = [k.strip().lower() for k in keywords.split(',')]
    parts = []
    theme = "travel"
    if any(k in kws for k in ['тайланд', 'пхукет', 'вьетнам']): theme = "asia"
    elif any(k in kws for k in ['байкал', 'иркутск']): theme = "russia"
    
    if 'горящий' in kws: title = f"🔥 ГОРЯЩИЙ ТУР: {', '.join(kws[:2]).title()}!"
    else: title = f"✨ ТУР: {', '.join(kws[:2]).title()}"
    
    parts.append(title)
    parts.append("")
    parts.append("Приглашаем вас в незабываемое путешествие!")
    if 'отель' in kws: parts.append("🏨 Комфортабельный отель.")
    if 'море' in kws: parts.append("🌊 Чистейшее море.")
    parts.append("✈️ Перелет включен.")
    if 'цена' in kws or 'скидка' in kws:
        parts.append("")
        parts.append("💰 **Спеццена**!")
    parts.append("")
    parts.append("📞 Звоните!")
    return "\n".join(parts)

async def finish_post_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    final_kb = types.InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data: final_kb.adjust(1)
    
    try:
        if media_type == 'photo' and media_id:
            await bot.send_photo(chat_id=message.chat.id, photo=media_id, caption=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
        elif media_type == 'video' and media_id:
            await bot.send_video(chat_id=message.chat.id, video=media_id, caption=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
        else:
            await bot.send_message(chat_id=message.chat.id, text=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
            
        manage_kb = types.InlineKeyboardBuilder()
        manage_kb.button(text="📤 Как переслать", callback_data="final:forward_info")
        manage_kb.row(manage_kb.button(text="✏️ Редактировать", callback_data="final:edit")) # Упрощено
        # Примечание: кнопка редактировать пока просто заглушка, т.к. нужно хранить ID поста
        
        await message.answer("✅ **Пост готов!**", reply_markup=manage_kb)
        
        # Очистка
        uid = message.from_user.id
        await state.clear()
        if uid in preview_messages:
            try: await bot.delete_message(uid, preview_messages[uid])
            except: pass
            del preview_messages[uid]
            
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith('final:'))
async def final_actions(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'forward_info':
        await callback.answer("Нажмите на пост выше → Переслать", show_alert=True)
    elif action == 'edit':
        await callback.answer("Функция восстановления в разработке", show_alert=True)

async def main():
    await bot.delete_webhook()
    logger.info("Запуск polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
