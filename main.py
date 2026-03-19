# -*- coding: utf-8 -*-
import os, logging, json, re, random, asyncio
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
    text_keyboard, buttons_keyboard, library_keyboard, 
    library_edit_keyboard, posts_keyboard, post_actions_keyboard,
    help_keyboard, finish_keyboard
)
from database import (
    init_db, save_button, get_saved_buttons, delete_button, update_button,
    save_link, get_saved_links, delete_link, update_link,
    save_published_post, get_published_posts, get_published_post, delete_published_post,
    save_draft, get_draft, delete_draft
)
from smart_text import smart_format_text, remove_emojis, remove_formatting, generate_ai_text, get_available_styles
from help_text import get_help_text

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ Нет токена!")
    raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

# === ХРАНИЛИЩА СОСТОЯНИЙ ===
preview_messages = {}  # {chat_id: message_id}
emoji_variants = {}  # {chat_id: variant}
style_variants = {}  # {chat_id: style}
temp_messages = {}  # {chat_id: [message_ids]}
library_return_points = {}  # {chat_id: 'media'|'text'|'buttons'}

STEP_CONFIG = {
    'media': {'num': 1, 'total': 3, 'name': 'Медиа'},
    'text': {'num': 2, 'total': 3, 'name': 'Текст'},
    'buttons': {'num': 3, 'total': 3, 'name': 'Кнопки'}
}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def delete_message_safe(chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id, message_id)
        logger.debug(f"🗑️ Удалено сообщение {message_id} в чате {chat_id}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалось удалить сообщение {message_id}: {e}")

async def add_temp_message(chat_id: int, message_id: int, delete_after: int = 10):
    """Добавить временное сообщение (удалить через N секунд)"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)
    
    async def delete_later():
        await asyncio.sleep(delete_after)
        await delete_message_safe(chat_id, message_id)
    
    asyncio.create_task(delete_later())

async def cleanup_temp_messages(chat_id: int):
    """Удалить все временные сообщения"""
    if chat_id in temp_messages:
        for msg_id in temp_messages[chat_id]:
            await delete_message_safe(chat_id, msg_id)
        temp_messages[chat_id] = []

async def update_preview(state: FSMContext, chat_id: int):
    """Обновить превью. ТОЛЬКО ОДНО сообщение."""
    data = await state.get_data()
    logger.debug(f"🔄 Обновление превью для chat_id={chat_id}")
    
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
            old_media_type = data.get('_preview_media_type', 'text')
            
            if media_type == 'photo' and media_id:
                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id, message_id=stored_msg_id,
                        caption=caption, parse_mode=ParseMode.HTML
                    )
                except TelegramBadRequest as e:
                    if "message to edit not found" in str(e):
                        del preview_messages[chat_id]
                        return await update_preview(state, chat_id)
                    elif "there is no caption" in str(e):
                        await bot.edit_message_text(
                            chat_id=chat_id, message_id=stored_msg_id,
                            text=caption, parse_mode=ParseMode.HTML
                        )
            elif media_type == 'video' and media_id:
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=stored_msg_id,
                    caption=caption, parse_mode=ParseMode.HTML
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=stored_msg_id,
                    text=caption, parse_mode=ParseMode.HTML
                )
            
            await state.update_data(_preview_media_type=media_type)
            
        else:
            new_msg = None
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(
                    chat_id=chat_id, photo=media_id,
                    caption=caption, parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='photo')
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(
                    chat_id=chat_id, video=media_id,
                    caption=caption, parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='video')
            else:
                new_msg = await bot.send_message(
                    chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='text')
            
            if new_msg:
                preview_messages[chat_id] = new_msg.message_id
                logger.info(f"✅ Превью создано chat_id={chat_id}, msg_id={new_msg.message_id}")
                
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e) or "message can't be edited" in str(e):
            if chat_id in preview_messages:
                del preview_messages[chat_id]
            await state.update_data(_preview_media_type=None)
            await update_preview(state, chat_id)
        else:
            logger.error(f"❌ Ошибка Telegram: {e}")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}", exc_info=True)

async def send_step_hint(chat_id: int, step: str):
    """Отправить подсказку по шагу"""
    help_text = get_help_text(step)
    msg = await bot.send_message(
        chat_id=chat_id,
        text=help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=help_keyboard(step)
    )
    await add_temp_message(chat_id, msg.message_id, delete_after=30)

# === ОБРАБОТЧИКИ: ГЛАВНОЕ МЕНЮ ===

@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    logger.info(f"👤 User {message.from_user.id} вызвал /start")
    await message.answer(
        "🤖 <b>Пост-Триумф Live</b>\n\n"
        "📝 <b>Как создать пост:</b>\n"
        "1️⃣ Нажмите ➕ Новый пост\n"
        "2️⃣ Прикрепите фото (скрепка 📎) или пропустите\n"
        "3️⃣ Напишите или сгенерируйте текст\n"
        "4️⃣ Добавьте кнопки-ссылки\n"
        "5️⃣ Опубликуйте и перешлите в группу\n\n"
        "Все кнопки навигации — внизу под полем ввода!",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"👤 User {cid} отменил действие")
    await state.clear()
    await cleanup_temp_messages(cid)
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
        del preview_messages[cid]
    if cid in emoji_variants:
        del emoji_variants[cid]
    if cid in style_variants:
        del style_variants[cid]
    if cid in library_return_points:
        del library_return_points[cid]
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"👤 User {cid} начал новый пост")
    
    await state.set_state(None)
    await state.update_data(
        step='media', text='', media_id=None, media_type=None,
        buttons=[], original_text=None, ai_keywords=None,
        smart_variant=-1, emoji_variant=0, ai_style=None,
        _preview_media_type=None
    )
    emoji_variants[cid] = 0
    style_variants[cid] = None
    library_return_points[cid] = None
    
    await cleanup_temp_messages(cid)
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
    
    await update_preview(state, cid)
    await send_step_hint(cid, 'media')
    
    await message.answer(
        "<b>📷 ШАГ 1/3: Медиа</b>\n\n"
        "📎 <b>Нажмите на скрепку</b> в поле ввода и прикрепите фото или видео.\n\n"
        "Или нажмите «⏭️ Пропустить медиа»",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard()
    )

@dp.message(F.text == "📋 Мои посты")
async def my_posts(message: types.Message, state: FSMContext):
    cid = message.chat.id
    posts = get_published_posts(cid, limit=50)
    
    if not posts:
        await message.answer("📋 <b>У вас пока нет опубликованных постов.</b>\n\nСоздайте первый пост через «➕ Новый пост»", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        return
    
    await message.answer(
        f"📋 <b>ВАШИ ПОСТЫ</b> (всего: {len(posts)})\n\n"
        f"Выберите пост для редактирования или копирования:",
        parse_mode=ParseMode.HTML,
        reply_markup=posts_keyboard(posts)
    )

@dp.message(F.text == "📚 Библиотека кнопок")
async def open_button_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    data = await state.get_data()
    current_step = data.get('step', 'main')
    library_return_points[cid] = current_step if current_step else 'main'
    
    buttons = get_saved_buttons(cid)
    await message.answer(
        f"📚 <b>БИБЛИОТЕКА КНОПОК</b> (макс. 10)\n\n"
        f"Отметьте ✅ нужные кнопки и нажмите «✅ Применить»",
        parse_mode=ParseMode.HTML,
        reply_markup=library_keyboard(buttons, set(), 'button')
    )

@dp.message(F.text == "🔗 Библиотека ссылок")
async def open_link_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    data = await state.get_data()
    current_step = data.get('step', 'main')
    library_return_points[cid] = current_step if current_step else 'main'
    
    links = get_saved_links(cid)
    await message.answer(
        f"🔗 <b>БИБЛИОТЕКА ССЫЛОК</b> (макс. 10)\n\n"
        f"Выберите ссылку для вставки в текст",
        parse_mode=ParseMode.HTML,
        reply_markup=library_keyboard(links, set(), 'link')
    )

# === ОБРАБОТЧИКИ: ШАГ 1 (МЕДИА) ===

@dp.message(F.text == "📎 Прикрепить фото/видео")
async def media_hint(message: types.Message):
    await delete_message_safe(message.chat.id, message.message_id)
    msg = await message.answer("ℹ️ Нажмите на значок скрепки 📎 в поле ввода и выберите фото/видео", reply_markup=media_keyboard())
    await add_temp_message(message.chat.id, msg.message_id, delete_after=5)

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
    await delete_message_safe(cid, message.message_id)
    
    await message.answer(
        "<b>✅ Фото добавлено в превью!</b>\n\n"
        "Теперь нажмите «➡️ Далее: Текст» или загрузите ещё фото для замены",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard(has_media=True)
    )

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
    await delete_message_safe(cid, message.message_id)
    
    await message.answer(
        "<b>✅ Видео добавлено в превью!</b>\n\n"
        "Теперь нажмите «➡️ Далее: Текст»",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard(has_media=True)
    )

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None, step='text')
    await update_preview(state, cid)
    
    await message.answer(
        "<b>✏️ ШАГ 2/3: Текст</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=text_keyboard(False, False)
    )
    await send_step_hint(cid, 'text')

@dp.message(F.text == "🔄 Заменить медиа")
async def replace_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    
    msg = await message.answer("📎 Теперь загрузите НОВОЕ фото/видео (оно заменит старое):", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🗑️ Удалить медиа")
async def delete_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    
    await message.answer("🗑️ Медиа удалено из превью", reply_markup=media_keyboard())

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    await state.update_data(step='text')
    await update_preview(state, cid)
    has_text = bool(data.get('text'))
    has_formatted = bool(data.get('original_text') and data.get('original_text') != data.get('text'))
    
    await message.answer(
        "<b>✏️ ШАГ 2/3: Текст</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=text_keyboard(has_text, has_formatted)
    )

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='media')
    await update_preview(state, cid)
    data = await state.get_data()
    has_media = bool(data.get('media_id'))
    
    await message.answer(
        "<b>📷 ШАГ 1/3: Медиа</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard(has_media)
    )

# === ОБРАБОТЧИКИ: ШАГ 2 (ТЕКСТ) ===

@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    raw = data.get('text', '')
    
    if not raw:
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer("✏️ Введите текст поста:", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
        return
    
    clean = remove_emojis(remove_formatting(raw))
    await state.set_state(PostWorkflow.writing_text)
    msg = await message.answer(f"✏️ Исправьте текст и отправьте:\n\n{clean[:400]}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    
    if not kws:
        msg = await message.answer("⚠️ Сначала используйте «🤖 ИИ: Новый запрос»", reply_markup=text_keyboard(False, False))
        await add_temp_message(cid, msg.message_id)
        return
    
    style = data.get('ai_style')
    txt = generate_ai_text(kws, style=style)
    await state.update_data(text=txt, original_text=txt)
    await update_preview(state, cid)

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    hint = f"\n\nПрошлые ключи: {kws}\nИзмените или напишите новые:" if kws else "\nНапишите ключевые слова через запятую:"
    
    await state.set_state(PostWorkflow.ai_input)
    msg = await message.answer(f"🤖 Генератор текста{hint}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        msg = await message.answer("⚠️ Сначала введите текст!")
        await add_temp_message(cid, msg.message_id)
        return
    
    clean_txt = remove_emojis(remove_formatting(txt))
    res = smart_format_text(clean_txt, 0, 0)
    await state.update_data(text=res['text'], original_text=txt, smart_variant=0, emoji_variant=0)
    emoji_variants[cid] = 0
    await update_preview(state, cid)

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    orig = data.get('original_text', data.get('text', ''))
    
    if not orig:
        msg = await message.answer("⚠️ Нет текста")
        await add_temp_message(cid, msg.message_id)
        return
    
    variant = emoji_variants.get(cid, 0) + 1
    emoji_variants[cid] = variant
    
    clean_orig = remove_emojis(remove_formatting(orig))
    res = smart_format_text(clean_orig, data.get('smart_variant', 0), variant)
    await state.update_data(text=res['text'], emoji_variant=variant)
    await update_preview(state, cid)

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        return
    
    cleaned = remove_emojis(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Эмодзи уже нет")
        await add_temp_message(cid, msg.message_id)
        return
    
    await state.update_data(text=cleaned)
    await update_preview(state, cid)

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        return
    
    cleaned = remove_formatting(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Формата уже нет")
        await add_temp_message(cid, msg.message_id)
        return
    
    await state.update_data(text=cleaned, original_text=None, smart_variant=-1)
    await update_preview(state, cid)

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    
    if not data.get('text'):
        msg = await message.answer("⚠️ Сначала введите текст!")
        await add_temp_message(cid, msg.message_id)
        return
    
    await state.update_data(step='buttons')
    await update_preview(state, cid)
    has_buttons = bool(data.get('buttons'))
    
    await message.answer(
        "<b>🔘 ШАГ 3/3: Кнопки</b>\n\n"
        "Добавьте кнопки-ссылки под пост",
        parse_mode=ParseMode.HTML,
        reply_markup=buttons_keyboard(has_buttons)
    )
    await send_step_hint(cid, 'buttons')

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='text')
    await update_preview(state, cid)
    data = await state.get_data()
    has_text = bool(data.get('text'))
    has_formatted = bool(data.get('original_text'))
    
    await message.answer(
        "<b>✏️ ШАГ 2/3: Текст</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=text_keyboard(has_text, has_formatted)
    )

@dp.message(F.text == "🔗 Добавить ссылку в текст")
async def add_text_link(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    links = get_saved_links(cid)
    
    if not links:
        msg = await message.answer("📚 У вас пока нет сохранённых ссылок.\n\nСначала создайте через «➕ Добавить» в библиотеке", reply_markup=library_keyboard([], set(), 'link'))
        await add_temp_message(cid, msg.message_id)
        return
    
    await state.set_state(PostWorkflow.selecting_link)
    msg = await message.answer("🔗 Выберите ссылку для вставки в текст:", reply_markup=library_keyboard(links, set(), 'link'))
    await add_temp_message(cid, msg.message_id)

# === ОБРАБОТЧИКИ: ШАГ 3 (КНОПКИ) ===

@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    await delete_message_safe(message.chat.id, message.message_id)
    await state.set_state(AddButtonSteps.waiting_for_text)
    msg = await message.answer(
        "➕ <b>ДОБАВЛЕНИЕ КНОПКИ</b>\n\n"
        "Введите текст кнопки (например: Подобрать тур):\n\n"
        "<i>Или в формате: Текст - Ссылка</i>\n"
        "<i>Пример: Подобрать тур - https://vCard.guru/...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard()
    )
    await add_temp_message(message.chat.id, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    text = message.text.strip()
    
    # Проверяем формат "Текст - Ссылка"
    if ' - ' in text and ('http://' in text or 'https://' in text):
        parts = text.split(' - ', 1)
        if len(parts) == 2:
            btn_text = parts[0].strip()
            btn_url = parts[1].strip()
            
            if btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
                # Сохраняем кнопку
                success, status = save_button(cid, btn_text, btn_url)
                if success:
                    # Добавляем в текущий пост
                    data = await state.get_data()
                    buttons = data.get('buttons', [])
                    buttons.append([{'text': btn_text, 'url': btn_url}])
                    await state.update_data(buttons=buttons)
                    await update_preview(state, cid)
                    
                    msg = await message.answer(f"✅ Кнопка «{btn_text}» добавлена!", reply_markup=buttons_keyboard(True))
                    await add_temp_message(cid, msg.message_id)
                    await state.set_state(None)
                    return
    
    # Обычный режим (текст → потом ссылка)
    await state.update_data(new_btn_text=text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer(
        f"2️⃣ <b>Введите ссылку для «{text}»:</b>\n\n"
        f"<i>Пример: https://vCard.guru/olga.tsuprankova</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard()
    )
    await add_temp_message(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer(
            "❌ <b>Неверная ссылка!</b>\n\n"
            "Ссылка должна начинаться с:\n"
            "• http://\n"
            "• https://\n"
            "• t.me/\n"
            "• tg://\n\n"
            "Попробуйте ещё раз:",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard()
        )
        await add_temp_message(cid, msg.message_id)
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text', '')
    
    success, status = save_button(cid, btn_text, url)
    
    if success:
        buttons = data.get('buttons', [])
        buttons.append([{'text': btn_text, 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(state, cid)
        
        msg = await message.answer(f"✅ Кнопка «{btn_text}» добавлена!", reply_markup=buttons_keyboard(True))
        await add_temp_message(cid, msg.message_id)
    elif status == 'duplicate':
        msg = await message.answer("⚠️ Такая кнопка уже есть в библиотеке", reply_markup=buttons_keyboard(True))
        await add_temp_message(cid, msg.message_id)
        await state.set_state(None)

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    if not txt and not media_id:
        msg = await message.answer("⚠️ Нельзя опубликовать пустой пост!\n\nДобавьте текст или медиа.", reply_markup=buttons_keyboard(bool(buttons_data)))
        await add_temp_message(cid, msg.message_id)
        return
    
    final_kb = InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data:
        final_kb.adjust(1)
    
    try:
        # Публикуем пост (остаётся в чате)
        if media_type == 'photo' and media_id:
            await bot.send_photo(
                chat_id=cid, photo=media_id,
                caption=txt, parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        elif media_type == 'video' and media_id:
            await bot.send_video(
                chat_id=cid, video=media_id,
                caption=txt, parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        else:
            await bot.send_message(
                chat_id=cid, text=txt,
                parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        
        # Сохраняем в историю опубликованных постов
        post_id = save_published_post(cid, media_type, media_id, txt, buttons_data)
        
        # Показываем меню после публикации
        await message.answer(
            "✅ <b>ПОСТ ОПУБЛИКОВАН!</b>\n\n"
            "📤 <b>Что дальше:</b>\n"
            "1. Нажмите на пост выше 👆\n"
            "2. Выберите «Переслать»\n"
            "3. Выберите группу/чат\n\n"
            "⚠️ <b>Важно:</b> При пересылке может быть «via @bot».\n"
            "Чтобы убрать: копируйте текст+медиа вручную или используйте «Скрыть имя».",
            parse_mode=ParseMode.HTML,
            reply_markup=finish_keyboard()
        )
        
        # Очищаем состояние но НЕ удаляем превью
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# === ОБРАБОТЧИКИ: БИБЛИОТЕКИ ===

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
        item = next((i for i in items if i['id'] == item_id), None)
        if not item:
            return
        
        data = await state.get_data()
        sel = set(data.get('temp_selected', []))
        
        if item_id in sel:
            sel.remove(item_id)
        else:
            sel.add(item_id)
        
        await state.update_data(temp_selected=list(sel))
        await callback.message.edit_reply_markup(
            reply_markup=library_keyboard(items, sel, lib_type)
        )
        await callback.answer()
        
    elif act == 'apply':
        data = await state.get_data()
        sels = data.get('temp_selected', [])
        all_items = get_saved_buttons(uid) if lib_type == 'button' else get_saved_links(uid)
        chosen = [i for i in all_items if i['id'] in sels]
        
        if not chosen:
            await callback.answer("⚠️ Ничего не выбрано", show_alert=True)
            return
        
        if lib_type == 'button':
            # Добавляем кнопки под пост
            buttons = data.get('buttons', [])
            buttons.extend([[{'text': b['text'], 'url': b['url']}] for b in chosen])
            await state.update_data(buttons=buttons, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            
            return_point = library_return_points.get(cid, 'buttons')
            if return_point == 'media':
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=media_keyboard(bool(data.get('media_id'))))
            elif return_point == 'text':
                has_text = bool(data.get('text'))
                has_fmt = bool(data.get('original_text'))
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=text_keyboard(has_text, has_fmt))
            else:
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=buttons_keyboard(True))
        else:
            # Вставляем ссылки в текст
            current_text = data.get('text', '')
            for link in chosen:
                current_text += f'\n<a href="{link["url"]}">{link["text"]}</a>'
            
            await state.update_data(text=current_text, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            
            await callback.message.answer("✅ Ссылки вставлены в текст!", reply_markup=text_keyboard(True, bool(data.get('original_text'))))
        
        await callback.answer()
        
    elif act == 'create':
        await state.set_state(AddButtonSteps.waiting_for_text if lib_type == 'button' else AddLinkSteps.waiting_for_text)
        prompt = "➕ Введите текст кнопки:" if lib_type == 'button' else "➕ Введите текст ссылки:"
        await callback.message.answer(prompt, reply_markup=cancel_keyboard())
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        return_point = library_return_points.get(cid, 'main')
        
        if return_point == 'media':
            data = await state.get_data()
            await callback.message.answer("<b>📷 ШАГ 1/3: Медиа</b>", parse_mode=ParseMode.HTML, reply_markup=media_keyboard(bool(data.get('media_id'))))
        elif return_point == 'text':
            data = await state.get_data()
            has_text = bool(data.get('text'))
            has_fmt = bool(data.get('original_text'))
            await callback.message.answer("<b>✏️ ШАГ 2/3: Текст</b>", parse_mode=ParseMode.HTML, reply_markup=text_keyboard(has_text, has_fmt))
        elif return_point == 'buttons':
            data = await state.get_data()
            await callback.message.answer("<b>🔘 ШАГ 3/3: Кнопки</b>", parse_mode=ParseMode.HTML, reply_markup=buttons_keyboard(bool(data.get('buttons'))))
        else:
            await callback.message.answer("🤖 <b>Пост-Триумф Live</b>", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('post:'))
async def post_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    if act == 'select':
        post_id = int(parts[2])
        post = get_published_post(post_id, uid)
        
        if not post:
            await callback.answer("⚠️ Пост не найден", show_alert=True)
            return
        
        await callback.message.edit_reply_markup(
            reply_markup=post_actions_keyboard(post_id)
        )
        await callback.answer()
        
    elif act == 'edit':
        post_id = int(parts[2])
        post = get_published_post(post_id, uid)
        
        if not post:
            await callback.answer("⚠️ Пост не найден", show_alert=True)
            return
        
        # Загружаем пост в превью для редактирования
        await state.set_state(None)
        await state.update_data(
            step='media',
            text=post['text'],
            original_text=post['text'],
            media_id=post['media_id'],
            media_type=post['media_type'],
            buttons=post['buttons'],
            smart_variant=0,
            emoji_variant=0,
            _preview_media_type=post['media_type']
        )
        
        # Удаляем старый пост из истории
        delete_published_post(post_id, uid)
        
        # Обновляем превью
        await update_preview(state, cid)
        await callback.message.delete()
        
        await callback.message.answer(
            "✏️ <b>ПОСТ ЗАГРУЖЕН В РЕДАКТОР</b>\n\n"
            "Старый пост удалён из истории.\n"
            "Пройдите все шаги и опубликуйте новую версию.",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard(bool(post['media_id']))
        )
        await callback.answer()
        
    elif act == 'copy':
        post_id = int(parts[2])
        post = get_published_post(post_id, uid)
        
        if not post:
            await callback.answer("⚠️ Пост не найден", show_alert=True)
            return
        
        # Копируем пост в превью (оригинал остаётся)
        await state.set_state(None)
        await state.update_data(
            step='media',
            text=post['text'],
            original_text=post['text'],
            media_id=post['media_id'],
            media_type=post['media_type'],
            buttons=post['buttons'],
            smart_variant=0,
            emoji_variant=0,
            _preview_media_type=post['media_type']
        )
        
        await update_preview(state, cid)
        await callback.message.delete()
        
        await callback.message.answer(
            "📋 <b>ПОСТ СКОПИРОВАН</b>\n\n"
            "Оригинальный пост остался в истории.\n"
            "Отредактируйте и опубликуйте копию.",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard(bool(post['media_id']))
        )
        await callback.answer()
        
    elif act == 'delete':
        post_id = int(parts[2])
        delete_published_post(post_id, uid)
        await callback.message.delete()
        await callback.message.answer("🗑️ Пост удалён из истории", reply_markup=main_keyboard())
        await callback.answer()
        
    elif act == 'forward_me':
        await callback.answer(
            "📤 Нажмите на пост → Переслать → Выберите чат\n\n"
            "Пост отправится ОТ ВАШЕГО ИМЕНИ",
            show_alert=True
        )
        
    elif act == 'forward_anon':
        await callback.answer(
            "👻 Для анонимной пересылки:\n"
            "1. Вы должны быть АДМИНОМ в группе\n"
            "2. Включите «Анонимная публикация»\n"
            "3. При пересылке выберите «Скрыть имя»",
            show_alert=True
        )
        
    elif act == 'back':
        posts = get_published_posts(uid, limit=50)
        await callback.message.edit_reply_markup(reply_markup=posts_keyboard(posts))
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('help:'))
async def help_callback(callback: types.CallbackQuery):
    parts = callback.data.split(':')
    step = parts[2] if len(parts) > 2 else 'main'
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('finish:'))
async def finish_callback(callback: types.CallbackQuery, state: FSMContext):
    act = callback.data.split(':')[1]
    cid = callback.message.chat.id
    
    if act == 'forward_me':
        await callback.answer(
            "📤 Нажмите на пост выше → Переслать → Выберите чат\n\n"
            "Пост отправится ОТ ВАШЕГО ИМЕНИ",
            show_alert=True
        )
    elif act == 'forward_anon':
        await callback.answer(
            "👻 Для анонимной пересылки:\n"
            "1. Вы должны быть АДМИНОМ в группе\n"
            "2. Включите «Анонимная публикация»\n"
            "3. При пересылке выберите «Скрыть имя»",
            show_alert=True
        )
    elif act == 'copy':
        await callback.answer("📋 Функция в разработке", show_alert=True)
    elif act == 'edit':
        await callback.answer("✏️ Функция в разработке", show_alert=True)
    elif act == 'done':
        await callback.message.delete()
        await callback.message.answer("✅ Готово! Главное меню:", reply_markup=main_keyboard())
        await callback.answer()

# === ОБРАБОТКА СООБЩЕНИЙ НЕ ПО ШАГУ ===

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    cid = message.chat.id
    txt = message.text
    await delete_message_safe(cid, message.message_id)
    
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    
    data = await state.get_data()
    has_text = bool(data.get('text'))
    has_formatted = bool(data.get('original_text'))
    
    await message.answer(
        "✅ Текст обновлён!",
        reply_markup=text_keyboard(has_text, has_formatted)
    )

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    kws = message.text.strip()
    await delete_message_safe(cid, message.message_id)
    
    await state.update_data(ai_keywords=kws)
    
    available_styles = get_available_styles()
    selected_style = random.choice(available_styles)
    style_variants[cid] = selected_style
    
    txt = generate_ai_text(kws, style=selected_style)
    await state.update_data(text=txt, original_text=txt, smart_variant=-1, ai_style=selected_style)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)
    
    await message.answer(
        f"✅ Текст сгенерирован (стиль: {selected_style})!",
        reply_markup=text_keyboard(True, True)
    )

@dp.message(PostWorkflow.selecting_link, F.text)
async def handle_link_selection(message: types.Message, state: FSMContext):
    # Обработка выбора ссылки
    await message.answer("⚠️ Используйте кнопки для выбора ссылок", reply_markup=cancel_keyboard())

# === ОБРАБОТКА СООБЩЕНИЙ НЕ ПО ШАГУ (УДАЛЕНИЕ) ===

@dp.message()
async def handle_wrong_step(message: types.Message, state: FSMContext):
    """Удалять сообщения если они не по текущему шагу"""
    cid = message.chat.id
    data = await state.get_data()
    current_step = data.get('step')
    
    # Игнорируем команды главного меню
    if message.text in ["➕ Новый пост", "📚 Библиотека кнопок", "🔗 Библиотека ссылок", "📋 Мои посты", "❓ Помощь"]:
        return
    
    # Игнорируем кнопки навигации
    if message.text in ["⬅️ Назад: Медиа", "⬅️ Назад: Текст", "➡️ Далее: Текст", "➡️ Далее: Кнопки", "✅ ФИНИШ: Опубликовать", "❌ Отмена"]:
        return
    
    # Если не в процессе создания поста — игнорируем
    if not current_step:
        return
    
    # Удаляем сообщение не по шагу
    await delete_message_safe(cid, message.message_id)
    
    # Отправляем подсказку
    step_hints = {
        'media': "📷 Сейчас шаг МЕДИА. Загрузите фото или нажмите «⏭️ Пропустить»",
        'text': "✏️ Сейчас шаг ТЕКСТ. Напишите текст или используйте ИИ",
        'buttons': "🔘 Сейчас шаг КНОПКИ. Добавьте кнопки или нажмите «✅ ФИНИШ»"
    }
    
    hint = step_hints.get(current_step, "Следуйте инструкциям на экране")
    msg = await message.answer(f"⚠️ {hint}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id, delete_after=5)

# === ЗАПУСК ===

async def main():
    await bot.delete_webhook()
    logger.info("🚀 Запуск...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
