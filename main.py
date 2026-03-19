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
from keyboards import main_keyboard, cancel_keyboard, get_preview_keyboard, library_keyboard
from database import init_db, save_button, get_saved_buttons, save_draft
from smart_text import smart_format_text, remove_emojis, remove_formatting, generate_ai_text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

# Хранилище: {chat_id: message_id}
preview_messages = {}
# Хранилище для временных сообщений (которые нужно удалять)
temp_messages = {}

STEP_CONFIG = {
    'media': {'num': 1, 'total': 3, 'name': 'Медиа'},
    'text': {'num': 2, 'total': 3, 'name': 'Текст'},
    'buttons': {'num': 3, 'total': 3, 'name': 'Кнопки'}
}

async def cleanup_temp_messages(chat_id: int):
    """Удаляет все временные сообщения (запросы ИИ, ввод кнопок и т.д.)"""
    if chat_id in temp_messages:
        for msg_id in temp_messages[chat_id]:
            try:
                await bot.delete_message(chat_id, msg_id)
            except:
                pass
        temp_messages[chat_id] = []

async def add_temp_message(chat_id: int, message_id: int):
    """Добавляет сообщение в список на удаление"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)

async def update_preview(state: FSMContext, chat_id: int):
    """Обновляет ОДНО сообщение превью. Всё остальное удаляет."""
    data = await state.get_data()
    
    step = data.get('step', 'media')
    text_content = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    # Формируем caption с отображением кнопок
    caption = text_content if text_content else "<i>_(Нажмите ✏️ Править текст)_</i>\n\n<i>Здесь будет ваш пост.</i>"
    
    # Добавляем информацию о кнопках в превью
    if buttons_data:
        btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
        caption += f"\n\n━━━━━━━━━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
    
    # Прогресс
    step_info = STEP_CONFIG.get(step, {'num': 1, 'total': 3})
    
    # Клавиатура
    has_formatted = bool(data.get('original_text') and data.get('original_text') != text_content)
    control_kb = get_preview_keyboard(step, step_info['num'], step_info['total'], bool(text_content), has_formatted)
    
    stored_msg_id = preview_messages.get(chat_id)
    
    try:
        # Сначала удаляем временные сообщения
        await cleanup_temp_messages(chat_id)
        
        if stored_msg_id:
            # РЕДАКТИРУЕМ существующее
            if media_type == 'photo' and media_id:
                await bot.edit_message_caption(
                    chat_id=chat_id, 
                    message_id=stored_msg_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
            elif media_type == 'video' and media_id:
                await bot.edit_message_caption(
                    chat_id=chat_id, 
                    message_id=stored_msg_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=stored_msg_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML,
                    reply_markup=control_kb
                )
            
            # Обновляем клавиатуру
            await bot.edit_message_reply_markup(
                chat_id=chat_id, 
                message_id=stored_msg_id, 
                reply_markup=control_kb
            )
            logger.info(f"✅ Обновлено превью chat_id={chat_id}")
        else:
            # СОЗДАЁМ новое
            new_msg = None
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(
                    chat_id=chat_id, 
                    photo=media_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=control_kb
                )
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(
                    chat_id=chat_id, 
                    video=media_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=control_kb
                )
            else:
                new_msg = await bot.send_message(
                    chat_id=chat_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=control_kb
                )
            
            if new_msg:
                preview_messages[chat_id] = new_msg.message_id
                logger.info(f"✅ Создано превью chat_id={chat_id}, msg_id={new_msg.message_id}")
                
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug(f"Контент не изменился chat_id={chat_id}")
        elif "message can't be edited" in str(e):
            # Сообщение удалено — создаём новое
            if chat_id in preview_messages:
                del preview_messages[chat_id]
            await update_preview(state, chat_id)
        elif "bot can't send messages to bots" in str(e):
            logger.critical(f"🚫 Бот не может писать chat_id={chat_id}")
        else:
            logger.error(f"Ошибка Telegram: {e}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}", exc_info=True)

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    is_bot = message.from_user.is_bot
    logger.info(f"Start от UID={uid}, is_bot={is_bot}")
    
    if is_bot:
        await message.answer("❌ Вы тестируете из аккаунта БОТА. Откройте из личного аккаунта!")
        return
    
    await message.answer("🤖 <b>Пост-Триумф Live</b>\n\nЖмите '➕ Новый пост'", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await state.clear()
    await cleanup_temp_messages(cid)
    if cid in preview_messages:
        try: 
            await bot.delete_message(cid, preview_messages[cid])
        except: 
            pass
        del preview_messages[cid]
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"Новый пост от chat_id={cid}")
    
    await state.set_state(None)
    await state.update_data(
        step='media', 
        text='', 
        media_id=None, 
        media_type=None, 
        buttons=[], 
        original_text=None, 
        ai_keywords=None,
        smart_variant=-1
    )
    
    await cleanup_temp_messages(cid)
    if cid in preview_messages:
        try: 
            await bot.delete_message(cid, preview_messages[cid])
        except: 
            pass
    
    await update_preview(state, cid)
    msg = await message.answer("<i>ℹ️ Используйте кнопки под сообщением выше.</i>", parse_mode=ParseMode.HTML)
    await add_temp_message(cid, msg.message_id)

@dp.callback_query(lambda c: c.data.startswith('prev:'))
async def preview_controller(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    cid = callback.message.chat.id
    uid = callback.from_user.id
    data = await state.get_data()
    
    logger.info(f"UID={uid}, CID={cid} нажал: {action}")

    if action == 'cancel':
        await cmd_cancel(callback.message, state)
        await callback.answer()
        return

    if action == 'skip_media':
        await state.update_data(media_type=None, media_id=None, step='text')
        await update_preview(state, cid)
        await callback.answer("Пропущено")
    elif action == 'to_text':
        await state.update_data(step='text')
        await update_preview(state, cid)
        await callback.answer("К тексту")
    elif action == 'back_media':
        await state.update_data(step='media')
        await update_preview(state, cid)
        await callback.answer()
    elif action == 'back_text':
        await state.update_data(step='text')
        await update_preview(state, cid)
        await callback.answer()
        
    elif action == 'edit_text':
        raw = data.get('text', '')
        if not raw:
            await state.set_state(PostWorkflow.writing_text)
            msg = await callback.message.answer("<b>✏️ Введите текст:</b>", parse_mode=ParseMode.HTML)
            await add_temp_message(cid, msg.message_id)
            await callback.answer()
            return
        clean = remove_emojis(remove_formatting(raw))
        await state.set_state(PostWorkflow.writing_text)
        msg = await callback.message.answer(f"<b>✏️ Исправьте и отправьте:</b>\n\n<code>{clean[:400]}</code>", parse_mode=ParseMode.HTML)
        await add_temp_message(cid, msg.message_id)
        await callback.answer()
        
    elif action == 'ai_generate':
        await state.set_state(PostWorkflow.ai_input)
        kws = data.get('ai_keywords', '')
        hint = f"\n\nПрошлые ключи: <code>{kws}</code>\nИзмените или напишите новые:" if kws else "\nНапишите ключевые слова через запятую:"
        msg = await callback.message.answer(f"<b>🤖 Генератор текста</b>{hint}", parse_mode=ParseMode.HTML)
        await add_temp_message(cid, msg.message_id)
        await callback.answer()
        
    elif action == 'smart_format':
        txt = data.get('text', '')
        if not txt: 
            await callback.answer("⚠️ Нет текста", show_alert=True)
            return
        clean_txt = remove_emojis(remove_formatting(txt))
        res = smart_format_text(clean_txt, 0)
        await state.update_data(text=res['text'], original_text=txt, smart_variant=0)
        await update_preview(state, cid)
        await callback.answer("✨ Отформатировано!")
        
    elif action == 'smart_next':
        v = data.get('smart_variant', 0) + 1
        orig = data.get('original_text', data.get('text'))
        clean_orig = remove_emojis(remove_formatting(orig))
        res = smart_format_text(clean_orig, v)
        await state.update_data(text=res['text'], smart_variant=v)
        await update_preview(state, cid)
        await callback.answer("🔄 Вариант изменен")
        
    elif action == 'smart_reset':
        orig = data.get('original_text', '')
        if not orig: 
            await callback.answer("Нет исходника", show_alert=True)
            return
        await state.update_data(text=orig, smart_variant=-1)
        await update_preview(state, cid)
        await callback.answer("↩️ Сброшено")
        
    elif action == 'remove_emojis':
        txt = data.get('text', '')
        if not txt: return
        cleaned = remove_emojis(txt)
        if cleaned == txt:
            await callback.answer("ℹ️ Эмодзи уже нет", show_alert=True)
            return
        await state.update_data(text=cleaned)
        await update_preview(state, cid)
        await callback.answer("🧹 Эмодзи удалены")
        
    elif action == 'remove_format':
        txt = data.get('text', '')
        if not txt: return
        cleaned = remove_formatting(txt)
        if cleaned == txt:
            await callback.answer("ℹ️ Формата уже нет", show_alert=True)
            return
        await state.update_data(text=cleaned)
        await update_preview(state, cid)
        await callback.answer("📄 Формат снят")
        
    elif action == 'to_buttons':
        if not data.get('text'): 
            await callback.answer("⚠️ Введите текст", show_alert=True)
            return
        await state.update_data(step='buttons')
        await update_preview(state, cid)
        await callback.answer("К кнопкам")
        
    elif action == 'add_btn':
        await state.set_state(AddButtonSteps.waiting_for_text)
        msg = await callback.message.answer("<b>➕ Текст кнопки:</b>", parse_mode=ParseMode.HTML)
        await add_temp_message(cid, msg.message_id)
        await callback.answer()
        
    elif action == 'lib_btn':
        btns = get_saved_buttons(uid)
        if not btns: 
            await callback.answer("📚 Пусто", show_alert=True)
            return
        sel = set(data.get('temp_selected', []))
        msg = await callback.message.answer("<b>📚 Выберите кнопки:</b>", reply_markup=library_keyboard(btns, sel), parse_mode=ParseMode.HTML)
        await add_temp_message(cid, msg.message_id)
        await callback.answer()
        
    elif action == 'finish':
        await finish_post(callback.message, state, cid)
        await callback.answer("Опубликовано")

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    cid = message.chat.id
    txt = message.text
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    await message.delete()

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    kws = message.text.strip()
    await state.update_data(ai_keywords=kws)
    
    txt = generate_ai_text(kws)
    
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer(f"<b>2️⃣ Ссылка для «{message.text}»:</b>", parse_mode=ParseMode.HTML)
    await add_temp_message(cid, msg.message_id)
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer("❌ Неверная ссылка.")
        await add_temp_message(cid, msg.message_id)
        return
    data = await state.get_data()
    if save_button(message.from_user.id, data['new_btn_text'], url):
        buttons = data.get('buttons', [])
        buttons.append([{'text': data['new_btn_text'], 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(state, cid)
        await message.delete()
    else:
        msg = await message.answer("⚠️ Уже есть.")
        await add_temp_message(cid, msg.message_id)

@dp.callback_query(lambda c: c.data.startswith('lib:'))
async def lib_cb(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    data = await state.get_data()
    
    if act == 'toggle':
        bid = int(parts[2])
        btns = get_saved_buttons(uid)
        btn = next((b for b in btns if b['id'] == bid), None)
        if not btn: return
        sel = set(data.get('temp_selected', []))
        if bid in sel: 
            sel.remove(bid)
        else: 
            sel.add(bid)
        await state.update_data(temp_selected=list(sel))
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(get_saved_buttons(uid), sel))
        await callback.answer()
    elif act == 'apply':
        sels = data.get('temp_selected', [])
        all_b = get_saved_buttons(uid)
        chosen = [b for b in all_b if b['id'] in sels]
        if not chosen: 
            await callback.answer("⚠️ Пусто", show_alert=True)
            return
        buttons = data.get('buttons', [])
        buttons.extend([[b] for b in chosen])
        await state.update_data(buttons=buttons, temp_selected=[])
        await callback.message.delete()
        await update_preview(state, cid)
        msg = await callback.message.answer("✅ Добавлено")
        await add_temp_message(cid, msg.message_id)
        await callback.answer()
    elif act == 'back':
        await callback.message.delete()
        await callback.answer()

async def finish_post(message: types.Message, state: FSMContext, cid: int):
    data = await state.get_data()
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    final_kb = types.InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data: 
        final_kb.adjust(1)
    
    try:
        if media_type == 'photo' and media_id:
            await bot.send_photo(
                chat_id=cid, 
                photo=media_id, 
                caption=txt, 
                parse_mode=ParseMode.HTML, 
                reply_markup=final_kb.as_markup()
            )
        elif media_type == 'video' and media_id:
            await bot.send_video(
                chat_id=cid, 
                video=media_id, 
                caption=txt, 
                parse_mode=ParseMode.HTML, 
                reply_markup=final_kb.as_markup()
            )
        else:
            await bot.send_message(
                chat_id=cid, 
                text=txt, 
                parse_mode=ParseMode.HTML, 
                reply_markup=final_kb.as_markup()
            )
        
        kb = types.InlineKeyboardBuilder()
        kb.button(text="📤 Как переслать", callback_data="final:info")
        msg = await message.answer("<b>✅ Готово!</b>", parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
        await add_temp_message(cid, msg.message_id)
        
        if cid in preview_messages:
            try: 
                await bot.delete_message(cid, preview_messages[cid])
            except: 
                pass
            del preview_messages[cid]
        await cleanup_temp_messages(cid)
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith('final:'))
async def final_actions(callback: types.CallbackQuery):
    if callback.data.split(':')[1] == 'info':
        await callback.answer("Нажмите на пост → Переслать", show_alert=True)

async def main():
    await bot.delete_webhook()
    logger.info("🚀 Запуск...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
