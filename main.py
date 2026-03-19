# -*- coding: utf-8 -*-
import os, logging, json, re, random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states import PostWorkflow, AddButtonSteps, AddLinkSteps
from keyboards import (
    main_keyboard, cancel_keyboard, media_keyboard, 
    text_keyboard, buttons_keyboard, library_keyboard, saved_links_keyboard
)
from database import init_db, save_button, get_saved_buttons, save_draft, save_link, get_saved_links
from smart_text import smart_format_text, remove_emojis, remove_formatting, generate_ai_text, get_available_styles

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

preview_messages = {}
emoji_variants = {}
style_variants = {}

STEP_CONFIG = {
    'media': {'num': 1, 'total': 3, 'name': 'Медиа'},
    'text': {'num': 2, 'total': 3, 'name': 'Текст'},
    'buttons': {'num': 3, 'total': 3, 'name': 'Кнопки'}
}

async def delete_message_safe(chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def update_preview(state: FSMContext, chat_id: int):
    """Обновляет превью. ТОЛЬКО ОДНО сообщение. Всё остальное удаляется."""
    data = await state.get_data()
    
    step = data.get('step', 'media')
    text_content = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    # Формируем caption
    if not text_content:
        caption = "<i>_(Нажмите ✏️ Редактировать текст)_</i>\n\n<i>Здесь будет ваш пост.</i>"
    else:
        caption = text_content
    
    # Добавляем кнопки в caption для просмотра
    if buttons_data:
        btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
        caption += f"\n\n━━━━━━━━━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
    
    stored_msg_id = preview_messages.get(chat_id)
    
    try:
        if stored_msg_id:
            # Пытаемся узнать тип сообщения по кэшу или пробуем оба варианта
            old_media_type = data.get('_preview_media_type', 'text')
            
            if old_media_type in ['photo', 'video'] and media_id:
                # Было медиа, осталось медиа
                try:
                    if media_type == 'photo':
                        await bot.edit_message_caption(
                            chat_id=chat_id, 
                            message_id=stored_msg_id, 
                            caption=caption, 
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == 'video':
                        await bot.edit_message_caption(
                            chat_id=chat_id, 
                            message_id=stored_msg_id, 
                            caption=caption, 
                            parse_mode=ParseMode.HTML
                        )
                except TelegramBadRequest as e:
                    if "there is no caption" in str(e):
                        # Сообщение без медиа — используем edit_message_text
                        await bot.edit_message_text(
                            chat_id=chat_id, 
                            message_id=stored_msg_id, 
                            text=caption, 
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        raise
            else:
                # Текстовое сообщение или смена типа
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=stored_msg_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML
                )
            
            # Сохраняем текущий тип медиа для следующего раза
            await state.update_data(_preview_media_type=media_type)
            
        else:
            # Создаём новое сообщение превью
            new_msg = None
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(
                    chat_id=chat_id, 
                    photo=media_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='photo')
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(
                    chat_id=chat_id, 
                    video=media_id, 
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='video')
            else:
                new_msg = await bot.send_message(
                    chat_id=chat_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='text')
            
            if new_msg:
                preview_messages[chat_id] = new_msg.message_id
                logger.info(f"✅ Превью создано/обновлено chat_id={chat_id}")
                
    except TelegramBadRequest as e:
        if "message can't be edited" in str(e):
            # Сообщение удалено — создаём новое
            if chat_id in preview_messages:
                del preview_messages[chat_id]
            await state.update_data(_preview_media_type=None)
            await update_preview(state, chat_id)
        elif "there is no caption" in str(e):
            # Пытаемся как текст
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=stored_msg_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        else:
            logger.error(f"Ошибка Telegram: {e}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}", exc_info=True)

@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 <b>Пост-Триумф Live</b>\n\n"
        "📝 <b>Как создать пост:</b>\n"
        "1️⃣ Нажмите ➕ Новый пост\n"
        "2️⃣ Прикрепите фото (скрепка 📎) или пропустите\n"
        "3️⃣ Напишите или сгенерируйте текст\n"
        "4️⃣ Добавьте кнопки-ссылки\n"
        "5️⃣ Опубликуйте в группу\n\n"
        "Все кнопки навигации — внизу под полем ввода!",
        parse_mode=ParseMode.HTML, 
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await state.clear()
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
        del preview_messages[cid]
    if cid in emoji_variants:
        del emoji_variants[cid]
    if cid in style_variants:
        del style_variants[cid]
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await state.set_state(None)
    await state.update_data(
        step='media', 
        text='', 
        media_id=None, 
        media_type=None, 
        buttons=[], 
        original_text=None, 
        ai_keywords=None,
        smart_variant=-1,
        emoji_variant=0,
        ai_style=None,
        _preview_media_type=None
    )
    emoji_variants[cid] = 0
    style_variants[cid] = None
    
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
    
    await update_preview(state, cid)
    # НЕ отправляем служебное сообщение — всё в превью

@dp.message(F.text == "📷 Прикрепить фото/видео (скрепка 📎)")
async def media_hint(message: types.Message):
    await delete_message_safe(message.chat.id, message.message_id)
    await message.answer("ℹ️ Нажмите на значок скрепки 📎 в поле ввода и выберите фото/видео", reply_markup=media_keyboard(), delete_after=3)

@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    cid = message.chat.id
    data = await state.get_data()
    if data.get('step') != 'media':
        await delete_message_safe(cid, message.message_id)
        return
    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)  # Удаляем фото из чата
    # НЕ отправляем подтверждение

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    cid = message.chat.id
    data = await state.get_data()
    if data.get('step') != 'media':
        await delete_message_safe(cid, message.message_id)
        return
    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)  # Удаляем видео из чата
    # НЕ отправляем подтверждение

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None, step='text')
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    await state.update_data(step='text')
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='media')
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    raw = data.get('text', '')
    if not raw:
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer("✏️ Введите текст поста:", reply_markup=cancel_keyboard())
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    clean = remove_emojis(remove_formatting(raw))
    await state.set_state(PostWorkflow.writing_text)
    msg = await message.answer(f"✏️ Исправьте текст и отправьте:\n\n{clean[:400]}", reply_markup=cancel_keyboard())
    await add_temp_message_for_deletion(cid, msg.message_id)

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    if not kws:
        msg = await message.answer("⚠️ Сначала используйте «🤖 ИИ: Новый запрос»", reply_markup=text_keyboard(False, False), delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    
    style = data.get('ai_style')
    txt = generate_ai_text(kws, style=style)
    await state.update_data(text=txt, original_text=txt)
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    hint = f"\n\nПрошлые ключи: {kws}\nИзмените или напишите новые:" if kws else "\nНапишите ключевые слова через запятую:"
    await state.set_state(PostWorkflow.ai_input)
    msg = await message.answer(f"🤖 Генератор текста{hint}", reply_markup=cancel_keyboard())
    await add_temp_message_for_deletion(cid, msg.message_id)

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt:
        msg = await message.answer("⚠️ Сначала введите текст!", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    clean_txt = remove_emojis(remove_formatting(txt))
    res = smart_format_text(clean_txt, 0, 0)
    await state.update_data(text=res['text'], original_text=txt, smart_variant=0, emoji_variant=0)
    emoji_variants[cid] = 0
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    orig = data.get('original_text', data.get('text', ''))
    if not orig:
        msg = await message.answer("⚠️ Нет текста", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    
    variant = emoji_variants.get(cid, 0) + 1
    emoji_variants[cid] = variant
    
    clean_orig = remove_emojis(remove_formatting(orig))
    res = smart_format_text(clean_orig, data.get('smart_variant', 0), variant)
    await state.update_data(text=res['text'], emoji_variant=variant)
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt: return
    cleaned = remove_emojis(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Эмодзи уже нет", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    await state.update_data(text=cleaned)
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt: return
    cleaned = remove_formatting(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Формата уже нет", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    await state.update_data(text=cleaned, original_text=None, smart_variant=-1)
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    if not data.get('text'):
        msg = await message.answer("⚠️ Сначала введите текст!", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    await state.update_data(step='buttons')
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='text')
    await update_preview(state, cid)
    # НЕ отправляем подтверждение

@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    await delete_message_safe(message.chat.id, message.message_id)
    await state.set_state(AddButtonSteps.waiting_for_text)
    msg = await message.answer("➕ Введите текст кнопки:", reply_markup=cancel_keyboard())
    await add_temp_message_for_deletion(message.chat.id, msg.message_id)

@dp.message(F.text == "🔗 Добавить ссылку в текст")
async def add_text_link(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    links = get_saved_links(cid)
    if not links:
        msg = await message.answer("📚 У вас пока нет сохранённых ссылок.", reply_markup=saved_links_keyboard([]), delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    await state.set_state(PostWorkflow.selecting_link)
    msg = await message.answer("🔗 Выберите ссылку:", reply_markup=saved_links_keyboard(links))
    await add_temp_message_for_deletion(cid, msg.message_id)

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    final_kb = InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data:
        final_kb.adjust(1)
    
    try:
        if media_type == 'photo' and media_id:
            await bot.send_photo(chat_id=cid, photo=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        elif media_type == 'video' and media_id:
            await bot.send_video(chat_id=cid, video=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        else:
            await bot.send_message(chat_id=cid, text=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        
        # Очищаем превью
        if cid in preview_messages:
            await delete_message_safe(cid, preview_messages[cid])
            del preview_messages[cid]
        if cid in emoji_variants:
            del emoji_variants[cid]
        if cid in style_variants:
            del style_variants[cid]
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    cid = message.chat.id
    txt = message.text
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)  # Удаляем текст пользователя

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    kws = message.text.strip()
    await state.update_data(ai_keywords=kws)
    
    available_styles = get_available_styles()
    selected_style = random.choice(available_styles)
    style_variants[cid] = selected_style
    
    txt = generate_ai_text(kws, style=selected_style)
    await state.update_data(text=txt, original_text=txt, smart_variant=-1, ai_style=selected_style)
    save_draft(message.from_user.id, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)  # Удаляем ввод пользователя

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    await delete_message_safe(message.chat.id, message.message_id)
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer(f"2️⃣ Введите ссылку для «{message.text}»:", reply_markup=cancel_keyboard())
    await add_temp_message_for_deletion(message.chat.id, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer("❌ Ссылка должна начинаться с http://", reply_markup=cancel_keyboard(), delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)
        return
    data = await state.get_data()
    if save_button(message.from_user.id, data['new_btn_text'], url):
        buttons = data.get('buttons', [])
        buttons.append([{'text': data['new_btn_text'], 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(state, cid)
    else:
        msg = await message.answer("⚠️ Такая кнопка уже есть", delete_after=3)
        await add_temp_message_for_deletion(cid, msg.message_id)

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
        await callback.answer()
    elif act == 'back':
        await callback.message.delete()
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('link:'))
async def link_cb(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    if act == 'insert':
        link_id = int(parts[2])
        links = get_saved_links(uid)
        link = next((l for l in links if l['id'] == link_id), None)
        if link:
            await callback.answer(f"🔗 {link['text']}: {link['url']}", show_alert=True)
        await callback.answer()
    elif act == 'create':
        await state.set_state(AddLinkSteps.waiting_for_text)
        await callback.message.answer("➕ Введите текст для ссылки:")
        await callback.answer()
    elif act == 'back':
        await callback.message.delete()
        await callback.answer()

@dp.message(AddLinkSteps.waiting_for_text, F.text)
async def proc_link_text(message: types.Message, state: FSMContext):
    await delete_message_safe(message.chat.id, message.message_id)
    await state.update_data(new_link_text=message.text.strip())
    await state.set_state(AddLinkSteps.waiting_for_url)
    msg = await message.answer(f"2️⃣ Введите URL для «{message.text}»:", reply_markup=cancel_keyboard())
    await add_temp_message_for_deletion(message.chat.id, msg.message_id)

@dp.message(AddLinkSteps.waiting_for_url, F.text)
async def proc_link_url(message: types.Message, state: FSMContext):
    await delete_message_safe(message.chat.id, message.message_id)
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer("❌ Неверная ссылка", delete_after=3)
        await add_temp_message_for_deletion(message.chat.id, msg.message_id)
        return
    data = await state.get_data()
    save_link(message.from_user.id, data['new_link_text'], url)
    await state.set_state(None)
    msg = await message.answer("✅ Ссылка сохранена!", delete_after=3)
    await add_temp_message_for_deletion(message.chat.id, msg.message_id)

# Вспомогательная функция для временных сообщений
temp_messages_to_delete = {}

async def add_temp_message_for_deletion(chat_id: int, message_id: int):
    if chat_id not in temp_messages_to_delete:
        temp_messages_to_delete[chat_id] = []
    temp_messages_to_delete[chat_id].append(message_id)
    # Удаляем через 3 секунды
    import asyncio
    await asyncio.sleep(3)
    await delete_message_safe(chat_id, message_id)

async def main():
    await bot.delete_webhook()
    logger.info("🚀 Запуск...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
