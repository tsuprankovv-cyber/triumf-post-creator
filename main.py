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
from smart_text import smart_format_text, remove_emojis, remove_formatting

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

async def update_preview(state: FSMContext, chat_id: int):
    """Обновляет ОДНО сообщение превью. Никогда не создаёт новые."""
    data = await state.get_data()
    
    step = data.get('step', 'media')
    text_content = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    # Формируем caption
    if not text_content:
        caption = "_(Нажмите ✏️ Править текст)_\n\nЗдесь будет ваш пост."
    else:
        caption = text_content
    
    # Проверяем, есть ли сохранённое сообщение
    stored_msg_id = preview_messages.get(chat_id)
    
    try:
        if stored_msg_id:
            # РЕДАКТИРУЕМ существующее
            if media_type == 'photo' and media_id:
                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id, 
                        message_id=stored_msg_id, 
                        caption=caption, 
                        parse_mode=ParseMode.HTML
                    )
                except TelegramBadRequest as e:
                    if "message can't be edited" in str(e):
                        # Сообщение удалено пользователем — создаём новое
                        del preview_messages[chat_id]
                        return await update_preview(state, chat_id)
                    raise
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
                    parse_mode=ParseMode.HTML
                )
            
            # Обновляем клавиатуру ОТДЕЛЬНО (важно!)
            control_kb = get_preview_keyboard(step, bool(text_content), bool(data.get('original_text')))
            await bot.edit_message_reply_markup(
                chat_id=chat_id, 
                message_id=stored_msg_id, 
                reply_markup=control_kb
            )
            logger.info(f"✅ Обновлено превью chat_id={chat_id}")
        else:
            # СОЗДАЁМ новое (только если нет сохранённого)
            control_kb = get_preview_keyboard(step, bool(text_content), bool(data.get('original_text')))
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
            # Контент не изменился — игнорируем
            logger.debug(f"Контент не изменился для chat_id={chat_id}")
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
    
    await message.answer("🤖 **Пост-Триумф Live**\n\nЖмите '➕ Новый пост'", reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await state.clear()
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
    
    if cid in preview_messages:
        try: 
            await bot.delete_message(cid, preview_messages[cid])
        except: 
            pass
    
    await update_preview(state, cid)
    await message.answer("ℹ️ Используйте кнопки под сообщением выше.", delete_after=5)

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
        
    elif action == 'edit_text':
        raw = data.get('text', '')
        if not raw:
            await state.set_state(PostWorkflow.writing_text)
            await callback.message.answer("✏️ Введите текст:")
            await callback.answer()
            return
        # Очищаем от эмодзи И форматирования
        clean = remove_emojis(remove_formatting(raw))
        await state.set_state(PostWorkflow.writing_text)
        await callback.message.answer(f"✏️ Исправьте и отправьте:\n\n<code>{clean[:400]}</code>", parse_mode=ParseMode.HTML)
        await callback.answer()
        
    elif action == 'ai_generate':
        await state.set_state(PostWorkflow.ai_input)
        kws = data.get('ai_keywords', '')
        hint = f"\n\nПрошлые ключи: <code>{kws}</code>\nИзмените или напишите новые:" if kws else "\nНапишите ключевые слова через запятую:"
        await callback.message.answer(
            f"🤖 <b>Генератор текста</b>{hint}", 
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        
    elif action == 'smart_format':
        txt = data.get('text', '')
        if not txt: 
            await callback.answer("⚠️ Нет текста", show_alert=True)
            return
        # 🔹 ВАЖНО: Сначала чистим старые эмодзи, потом форматируем
        clean_txt = remove_emojis(txt)
        res = smart_format_text(clean_txt, 0)
        await state.update_data(text=res['text'], original_text=txt, smart_variant=0)
        await update_preview(state, cid)
        await callback.answer("✨ Отформатировано!")
        
    elif action == 'smart_next':
        v = data.get('smart_variant', 0) + 1
        orig = data.get('original_text', data.get('text'))
        # 🔹 Чистим эмодзи перед новой генерацией
        clean_orig = remove_emojis(orig)
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
        
    elif action == 'back_text':
        await state.update_data(step='text')
        await update_preview(state, cid)
        await callback.answer()
        
    elif action == 'add_btn':
        await state.set_state(AddButtonSteps.waiting_for_text)
        await callback.message.answer("➕ <b>Текст кнопки:</b>", parse_mode=ParseMode.HTML)
        await callback.answer()
        
    elif action == 'lib_btn':
        btns = get_saved_buttons(uid)
        if not btns: 
            await callback.answer("📚 Пусто", show_alert=True)
            return
        sel = set(data.get('temp_selected', []))
        await callback.message.answer("<b>📚 Выберите кнопки:</b>", reply_markup=library_keyboard(btns, sel), parse_mode=ParseMode.HTML)
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
    
    # 🔹 ПРОДВИНУТЫЙ ГЕНЕРАТОР
    txt = generate_ai_text(kws)
    
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer(f"2️⃣ <b>Ссылка для «{message.text}»:</b>", parse_mode=ParseMode.HTML)
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Неверная ссылка.")
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
        await message.answer("⚠️ Уже есть.")

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
        await callback.message.answer("✅ Добавлено", delete_after=3)
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
    
    # Создаём клавиатуру с кнопками-ссылками
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
        await message.answer("✅ <b>Готово!</b>", parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
        
        if cid in preview_messages:
            try: 
                await bot.delete_message(cid, preview_messages[cid])
            except: 
                pass
            del preview_messages[cid]
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.callback_query(lambda c: c.data.startswith('final:'))
async def final_actions(callback: types.CallbackQuery):
    if callback.data.split(':')[1] == 'info':
        await callback.answer("Нажмите на пост → Переслать", show_alert=True)

# ============================================================================
# 🔹 ПРОДВИНУТЫЙ ГЕНЕРАТОР ТЕКСТОВ (Маркетинговые формулы)
# ============================================================================

def generate_ai_text(keywords: str) -> str:
    """Генерирует продающий текст по ключевым словам"""
    kws = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    
    if not kws:
        return "<b>Введите ключевые слова!</b>\n\nНапример: Пхукет, отель 5*, горящий тур"
    
    # Определяем тему
    theme = detect_theme_advanced(kws)
    
    # Заголовок (по формуле AIDA - Attention)
    if any(w in kws for w in ['горящий', 'акция', 'скидка', 'спеццена']):
        title = f"🔥 <b>ГОРЯЩЕЕ ПРЕДЛОЖЕНИЕ!</b>"
    elif any(w in kws for w in ['новый', 'открытие', 'старт']):
        title = f"✨ <b>НОВИНКА!</b>"
    else:
        title = f"💎 <b>ЭКСКЛЮЗИВНЫЙ ТУР</b>"
    
    # Тело письма (по формуле AIDA - Interest & Desire)
    body_parts = []
    
    # Направление
    destinations = [k for k in kws if k in ['тайланд', 'пхукет', 'самуи', 'вьетнам', 'нячанг', 'китай', 'ханькоу', 'дубай', 'оаэ', 'египет', 'турция', 'байкал', 'иркутск', 'сочи', 'алтай']]
    if destinations:
        body_parts.append(f"📍 <b>Направление:</b> {', '.join(destinations).title()}")
    
    # Отель
    if any(w in kws for w in ['отель', 'гостиница', '5*', '4*', '3*', 'люкс']):
        stars = next((w for w in kws if w in ['5*', '4*', '3*']), 'высокого уровня')
        body_parts.append(f"🏨 <b>Отель:</b> {stars}")
    
    # Питание
    if any(w in kws for w in ['все включено', 'all inclusive', 'завтрак', 'ужин']):
        body_parts.append(f"🍽️ <b>Питание:</b> Все включено")
    
    # Перелёт
    if any(w in kws for w in ['вылет', 'перелет', 'авиа', 'билет']):
        body_parts.append(f"✈️ <b>Перелёт:</b> Включён")
    
    # Цена
    if any(w in kws for w in ['цена', 'стоимость', 'руб', 'доллар', 'скидка']):
        body_parts.append(f"💰 <b>Специальная цена!</b>")
    
    # Сроки
    if any(w in kws for w in ['завтра', 'срочно', 'дедлайн', 'дата']):
        body_parts.append(f"⏰ <b>Ограниченное предложение!</b>")
    
    # Призыв к действию (по формуле AIDA - Action)
    cta = [
        "📞 <b>Звоните прямо сейчас!</b>",
        "💬 <b>Пишите — подберём лучший вариант!</b>",
        "⚡ <b>Успейте забронировать!</b>"
    ]
    
    # Собираем текст
    result = [title, ""]
    result.extend(body_parts)
    result.append("")
    result.append("<b>Приглашаем вас в незабываемое путешествие!</b>")
    result.append("")
    result.append(random.choice(cta))
    
    return "\n".join(result)

def detect_theme_advanced(kws: list) -> str:
    """Определяет тему для подбора эмодзи"""
    asia = ['тайланд', 'пхукет', 'вьетнам', 'китай', 'ханькоу']
    arab = ['дубай', 'оаэ', 'египет', 'турция']
    russia = ['байкал', 'иркутск', 'сочи', 'алтай']
    
    if any(k in kws for k in asia): return 'asia'
    if any(k in kws for k in arab): return 'arab'
    if any(k in kws for k in russia): return 'russia'
    return 'general'

import random

async def main():
    await bot.delete_webhook()
    logger.info("🚀 Запуск...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
