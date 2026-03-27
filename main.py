# -*- coding: utf-8 -*-
import os, logging, json, re, random, asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiohttp import web

from states import PostWorkflow, AddButtonSteps, AddLinkSteps
from keyboards import (
    main_keyboard, cancel_keyboard, media_keyboard,
    text_keyboard, buttons_keyboard, library_keyboard,
    posts_keyboard, help_keyboard, finish_keyboard
)
from database import (
    init_db, save_button, get_saved_buttons, delete_button,
    save_link, get_saved_links, delete_link,
    save_published_post, get_published_posts, get_published_post, delete_published_post,
    save_draft
)
from smart_text import smart_format_text, remove_emojis, remove_formatting, generate_ai_text, get_available_styles
from help_text import get_help_text

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
PORT = int(os.getenv('PORT', os.getenv('RENDER_EXTERNAL_PORT', 8080)))

if not BOT_TOKEN:
    logger.error("❌ НЕТ ТОКЕНА!")
    raise ValueError("❌ Нет токена!")

logger.info(f"🌐 Порт: {PORT}")

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()
logger.info("✅ База данных инициализирована")

# === ХРАНИЛИЩА ===
menu_messages = {}      # {chat_id: message_id}
temp_messages = {}      # {chat_id: [message_ids]}
help_context = {}       # {chat_id: current_step}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def delete_message_safe(chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id, message_id)
        logger.debug(f"🗑️ Удалено {message_id}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалил {message_id}: {e}")

async def cleanup_chat(chat_id: int, keep_preview=False):
    """Удалить ВСЕ временные сообщения"""
    logger.debug(f"🧹 Очистка чата {chat_id}")
    
    if chat_id in temp_messages:
        for msg_id in temp_messages[chat_id][:]:
            await delete_message_safe(chat_id, msg_id)
        temp_messages[chat_id] = []
    
    if chat_id in menu_messages and not keep_preview:
        await delete_message_safe(chat_id, menu_messages[chat_id])
        del menu_messages[chat_id]

def add_temp(chat_id: int, message_id: int):
    """Добавить сообщение на удаление"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)

async def send_step_message(chat_id: int, text: str, step: str, reply_markup=None):
    """Отправить сообщение шага"""
    full_text = f"<b>{step}</b>\n\n{text}"
    msg = await bot.send_message(chat_id, text=full_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    add_temp(chat_id, msg.message_id)
    logger.info(f"📤 {step} → msg_id={msg.message_id}")
    return msg

async def update_preview(state: FSMContext, chat_id: int):
    """Обновить превью поста"""
    try:
        data = await state.get_data()
        text_content = data.get('text', '')
        media_id = data.get('media_id')
        media_type = data.get('media_type')
        buttons_data = data.get('buttons', [])
        step = data.get('step', 'unknown')
        preview_id = data.get('preview_message_id')
        
        # Формируем текст
        if not text_content and not media_id:
            caption = f"<i>📷 Ожидание...</i>" if step == 'media' else f"<i>✏️ Ожидание...</i>" if step == 'text' else f"<i>🔘 Ожидание...</i>"
        elif not text_content:
            caption = "<i>📝 Добавьте текст</i>"
        else:
            caption = text_content
        
        if buttons_data:
            btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
            caption += f"\n\n━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
        
        caption = f"<b>👁️ ПРЕВЬЮ</b>\n\n{caption}"
        
        if preview_id:
            try:
                if media_type == 'photo' and media_id:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=preview_id, caption=caption, parse_mode=ParseMode.HTML)
                elif media_type == 'video' and media_id:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=preview_id, caption=caption, parse_mode=ParseMode.HTML)
                else:
                    await bot.edit_message_text(chat_id=chat_id, message_id=preview_id, text=caption, parse_mode=ParseMode.HTML)
                logger.info(f"✅ Превью обновлено")
                return
            except TelegramBadRequest as e:
                if "message to edit not found" in str(e):
                    await delete_message_safe(chat_id, preview_id)
                    await state.update_data(preview_message_id=None)
        
        # Создаём новое
        if media_type == 'photo' and media_id:
            new_msg = await bot.send_photo(chat_id=chat_id, photo=media_id, caption=caption, parse_mode=ParseMode.HTML)
        elif media_type == 'video' and media_id:
            new_msg = await bot.send_video(chat_id=chat_id, video=media_id, caption=caption, parse_mode=ParseMode.HTML)
        else:
            new_msg = await bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML)
        
        await state.update_data(preview_message_id=new_msg.message_id)
        logger.info(f"✅ Превью создано msg_id={new_msg.message_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка превью: {e}")

# === ГЛАВНОЕ МЕНЮ ===
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    cid = message.chat.id
    logger.info(f"👤 START: {cid}")
    
    await delete_message_safe(cid, message.message_id)  # Удаляем /start
    await cleanup_chat(cid, keep_preview=False)
    
    text = "🤖 <b>Пост-Триумф Live</b>\n\n➕ Новый пост | 📚 Кнопки | 🔗 Ссылки | 📋 Посты | ❓ Помощь"
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
    menu_messages[cid] = msg.message_id

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"❌ ОТМЕНА: {cid}")
    
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    preview_id = data.get('preview_message_id')
    
    await state.clear()
    await cleanup_chat(cid, keep_preview=False)
    
    if preview_id:
        await delete_message_safe(cid, preview_id)
    
    msg = await message.answer("❌ Отменено.", reply_markup=main_keyboard())
    menu_messages[cid] = msg.message_id

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🆕 НОВЫЙ ПОСТ: {cid}")
    
    await delete_message_safe(cid, message.message_id)  # Удаляем кнопку пользователя
    await cleanup_chat(cid, keep_preview=False)
    
    await state.clear()
    await state.update_data(
        step='media', text='', media_id=None, media_type=None,
        buttons=[], preview_message_id=None
    )
    
    await update_preview(state, cid)
    
    text = "📎 <b>Добавить медиа:</b>\n• Отправьте фото/видео\n• Или «⏭️ Пропустить медиа»\n• «❓ Помощь» — инструкция"
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard())

@dp.message(F.text == "📚 Библиотека кнопок")
async def open_button_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=False)
    buttons = get_saved_buttons(cid)
    await message.answer("📚 <b>Библиотека кнопок</b>", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(buttons, set(), 'button'))

@dp.message(F.text == "🔗 Библиотека ссылок")
async def open_link_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=False)
    links = get_saved_links(cid)
    await message.answer("🔗 <b>Библиотека ссылок</b>", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(links, set(), 'link'))

@dp.message(F.text == "📋 Мои посты")
async def my_posts(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=False)
    posts = get_published_posts(cid, limit=50)
    if not posts:
        await message.answer("📋 Нет постов.", reply_markup=main_keyboard())
        return
    await message.answer(f"📋 <b>Посты</b> ({len(posts)}):", parse_mode=ParseMode.HTML, reply_markup=posts_keyboard(posts))

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    step = data.get('step', 'main')
    help_text = get_help_text(step if step else 'main')
    await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard(step if step else 'main'))

# === ШАГ 1: МЕДИА ===
@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📸 ФОТО: {cid}")
    
    await delete_message_safe(cid, message.message_id)
    
    data = await state.get_data()
    if data.get('step') != 'media':
        return
    
    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    await update_preview(state, cid)
    
    text = "✅ <b>Фото в превью!</b>\n\n➡️ Далее: Текст | ✏️ Редактировать | 🔄 Заменить"
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard(has_media=True))

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    
    data = await state.get_data()
    if data.get('step') != 'media':
        return
    
    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    await update_preview(state, cid)
    
    text = "✅ <b>Видео в превью!</b>\n\n➡️ Далее: Текст"
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard(has_media=True))

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None, step='text')
    await update_preview(state, cid)
    text = "✏️ <b>ШАГ 2/3: Текст</b>\n\n🤖 ИИ: Новый запрос | ✏️ Редактировать | 🪄 Сделать красиво"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(False, False))

@dp.message(F.text == "🔄 Заменить медиа")
async def replace_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    await send_step_message(cid, "📎 Отправьте новое фото:", "📷 ШАГ 1/3: Медиа", reply_markup=cancel_keyboard())

@dp.message(F.text == "🗑️ Удалить медиа")
async def delete_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    await message.answer("🗑️ Удалено", reply_markup=media_keyboard())

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='text')
    await update_preview(state, cid)
    text = "✏️ <b>ШАГ 2/3: Текст</b>\n\n🤖 ИИ: Новый запрос | ✏️ Редактировать | 🪄 Сделать красиво"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(False, False))

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='media')
    await update_preview(state, cid)
    await send_step_message(cid, "📷 Медиа:", "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard())

# === ШАГ 2: ТЕКСТ ===
@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    raw = data.get('text', '')
    
    if not raw:
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer("✏️ Введите текст:", reply_markup=cancel_keyboard())
        add_temp(cid, msg.message_id)
        return
    
    clean = remove_emojis(remove_formatting(raw))
    await state.set_state(PostWorkflow.writing_text)
    msg = await message.answer(f"✏️ Исправьте:\n\n{clean}", reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    txt = message.text
    await state.update_data(text=txt, original_text=txt)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    
    text = "✅ Текст сохранён!\n\n🤖 ИИ: Обновить | 🪄 Сделать красиво | 🔄 Эмодзи"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.set_state(PostWorkflow.ai_input)
    msg = await message.answer("🤖 Опишите тему:", reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    kws = message.text.strip()
    await state.update_data(ai_keywords=kws)
    
    selected_style = random.choice(get_available_styles())
    txt = generate_ai_text(kws, style=selected_style)
    
    await state.update_data(text=txt, original_text=txt, ai_style=selected_style)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    
    text = f"✅ Текст сгенерирован!\n\n🤖 ИИ: Обновить | 🪄 Сделать красиво | 🔄 Эмодзи"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    
    if not kws:
        await message.answer("⚠️ Сначала «ИИ: Новый запрос»")
        return
    
    txt = generate_ai_text(kws, style=data.get('ai_style'))
    await state.update_data(text=txt, original_text=txt)
    await update_preview(state, cid)
    await message.answer("✅ Обновлён", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста")
        return
    
    res = smart_format_text(txt, 0, 0)
    await state.update_data(text=res['text'])
    await update_preview(state, cid)
    await message.answer("✅ Отформатировано", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста")
        return
    
    variant = data.get('emoji_variant', 0) + 1
    clean = remove_emojis(remove_formatting(data.get('original_text', txt)))
    res = smart_format_text(clean, 0, variant)
    
    await state.update_data(text=res['text'], emoji_variant=variant)
    await update_preview(state, cid)
    await message.answer(f"✅ Вариант #{variant}", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста")
        return
    
    cleaned = remove_emojis(txt)
    await state.update_data(text=cleaned)
    await update_preview(state, cid)
    await message.answer("✅ Эмодзи удалены", reply_markup=text_keyboard(True, False))

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста")
        return
    
    cleaned = remove_formatting(txt)
    await state.update_data(text=cleaned, original_text=None)
    await update_preview(state, cid)
    await message.answer("✅ Формат снят", reply_markup=text_keyboard(True, False))

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    if not data.get('text'):
        await message.answer("⚠️ Сначала текст")
        return
    
    await state.update_data(step='buttons')
    await update_preview(state, cid)
    text = "🔘 <b>ШАГ 3/3: Кнопки</b>\n\n➕ Добавить | 📚 Библиотека | ✅ ФИНИШ"
    await send_step_message(cid, text, "🔘 ШАГ 3/3: Кнопки", reply_markup=buttons_keyboard(bool(data.get('buttons'))))

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='text')
    await update_preview(state, cid)
    await send_step_message(cid, "✏️ Текст:", "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(True, True))

# === ШАГ 3: КНОПКИ ===
@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    await state.set_state(AddButtonSteps.waiting_for_text)
    msg = await message.answer("➕ Текст кнопки:", reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    text = message.text.strip()
    if ' - ' in text and 'http' in text:
        parts = text.split(' - ', 1)
        if len(parts) == 2:
            btn_text, btn_url = parts[0].strip(), parts[1].strip()
            if btn_url.startswith(('http', 't.me/', 'tg://')):
                save_button(cid, btn_text, btn_url)
                data = await state.get_data()
                buttons = data.get('buttons', [])
                buttons.append([{'text': btn_text, 'url': btn_url}])
                await state.update_data(buttons=buttons)
                await update_preview(state, cid)
                await state.set_state(None)
                await message.answer(f"✅ {btn_text}", reply_markup=buttons_keyboard(True))
                return
    
    await state.update_data(new_btn_text=text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer("🔗 Ссылка:", reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await cleanup_chat(cid, keep_preview=True)
    
    url = message.text.strip()
    if not url.startswith(('http', 't.me/', 'tg://')):
        await message.answer("❌ http:// или https://")
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text', '')
    save_button(cid, btn_text, url)
    
    buttons = data.get('buttons', [])
    buttons.append([{'text': btn_text, 'url': url}])
    await state.update_data(buttons=buttons, new_btn_text=None)
    await state.set_state(None)
    await update_preview(state, cid)
    await message.answer(f"✅ {btn_text}", reply_markup=buttons_keyboard(True))

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    
    data = await state.get_data()
    preview_id = data.get('preview_message_id')
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    if not txt and not media_id:
        await message.answer("⚠️ Пусто")
        return
    
    final_kb = InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data:
        final_kb.adjust(1)
    
    if media_type == 'photo' and media_id:
        await bot.send_photo(chat_id=cid, photo=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
    elif media_type == 'video' and media_id:
        await bot.send_video(chat_id=cid, video=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
    else:
        await bot.send_message(chat_id=cid, text=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
    
    save_published_post(cid, media_type, media_id, txt, buttons_data)
    
    await state.clear()
    await cleanup_chat(cid, keep_preview=False)
    if preview_id:
        await delete_message_safe(cid, preview_id)
    if cid in menu_messages:
        await delete_message_safe(cid, menu_messages[cid])
        del menu_messages[cid]
    
    await message.answer("🎉 ОПУБЛИКОВАНО!", reply_markup=finish_keyboard())

# === БИБЛИОТЕКИ ===
@dp.callback_query(lambda c: c.data.startswith('lib:') or c.data.startswith('link_lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    lib_type = 'button' if parts[0] == 'lib' else 'link'
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    if act == 'toggle':
        item_id = int(parts[2])
        items = get_saved_buttons(uid) if lib_type == 'button' else get_saved_links(uid)
        data = await state.get_data()
        sel = set(data.get('temp_selected', []))
        if item_id in sel:
            sel.remove(item_id)
        else:
            sel.add(item_id)
        await state.update_data(temp_selected=list(sel))
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(items, sel, lib_type))
        await callback.answer()
        
    elif act == 'apply':
        data = await state.get_data()
        sels = data.get('temp_selected', [])
        all_items = get_saved_buttons(uid) if lib_type == 'button' else get_saved_links(uid)
        chosen = [i for i in all_items if i['id'] in sels]
        
        if not chosen:
            await callback.answer("⚠️ Пусто", show_alert=True)
            return
        
        if lib_type == 'button':
            buttons = data.get('buttons', [])
            buttons.extend([[{'text': b['text'], 'url': b['url']}] for b in chosen])
            await state.update_data(buttons=buttons, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            await callback.message.answer("✅ Кнопки!", reply_markup=buttons_keyboard(True))
        else:
            current_text = data.get('text', '')
            for link in chosen:
                current_text += f'\n<a href="{link["url"]}">{link["text"]}</a>'
            await state.update_data(text=current_text, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            await callback.message.answer("✅ Ссылки!", reply_markup=text_keyboard(True, True))
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        await callback.message.answer("🤖 <b>Пост-Триумф</b>", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('help:'))
async def help_callback(callback: types.CallbackQuery, state: FSMContext):
    cid = callback.message.chat.id
    parts = callback.data.split(':')
    step = parts[1] if len(parts) > 1 else 'main'
    
    if step == 'back':
        await callback.message.delete()
        data = await state.get_data()
        step = data.get('step', 'main')
        help_text = get_help_text(step if step else 'main')
        await callback.message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard(step if step else 'main'))
        await callback.answer()
        return
    
    help_text = get_help_text(step)
    await callback.message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard(step))
    await callback.answer()

# === ВЕБ-СЕРВЕР ===
async def handle_health(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Порт {PORT}")

async def main():
    await start_web_server()
    await bot.delete_webhook()
    logger.info("🚀 ЗАПУСК")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
