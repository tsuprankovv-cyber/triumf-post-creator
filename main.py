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
from aiogram.client.session.aiohttp import AiohttpSession
from states import PostWorkflow, AddButtonSteps, AddLinkSteps
from keyboards import (
    main_keyboard, cancel_keyboard, media_keyboard,
    text_keyboard, buttons_keyboard, library_keyboard,
    posts_keyboard, post_actions_keyboard,
    help_keyboard, finish_keyboard
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
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)  # ✅ ИСПРАВЛЕНО: было name → __name__

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
PROXY_URL = os.getenv('PROXY_URL', None)

if not BOT_TOKEN:
    logger.error("❌ НЕТ ТОКЕНА!")
    raise ValueError("❌ Нет токена!")

# === ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ ===
async def test_telegram_connection():
    """Проверка доступности Telegram API"""
    import aiohttp
    
    logger.info("🔍 === ПРОВЕРКА ПОДКЛЮЧЕНИЯ ===")
    
    # 1. Проверка токена
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        return False
    logger.info(f"✅ BOT_TOKEN: установлен (длина: {len(BOT_TOKEN)})")
    logger.info(f"🔑 Первые 10 символов: {BOT_TOKEN[:10]}...")
    
    # 2. Прямой тест соединения
    logger.info("🌐 Тестируем api.telegram.org...")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get('https://api.telegram.org', ssl=True) as resp:
                logger.info(f"✅ Telegram API доступен: {resp.status}")
                return True
    except aiohttp.ClientConnectorError as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        logger.error("💡 Вероятно: блокировка провайдером или фаервол")
        return False
    except aiohttp.ClientSSLError as e:
        logger.error(f"❌ SSL ошибка: {e}")
        logger.error("💡 Вероятно: проблема с сертификатами")
        return False
    except asyncio.TimeoutError:
        logger.error("❌ Тайм-аут подключения")
        logger.error("💡 Вероятно: блокировка или сеть не отвечает")
        return False
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка: {type(e).__name__}: {e}")
        return False

# 3. Информация о прокси
if PROXY_URL:
    logger.info(f"🔄 PROXY_URL: {PROXY_URL[:30]}...")
else:
    logger.info("⚠️ PROXY_URL не установлен (если нужно — добавьте в .env)")

# === ИНИЦИАЛИЗАЦИЯ ===
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

# === ХРАНИЛИЩА ===
preview_messages = {}  # {chat_id: message_id}
emoji_variants = {}
style_variants = {}
temp_messages = {}  # {chat_id: [message_ids]}
library_return_points = {}
menu_messages = {}  # {chat_id: message_id}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def delete_message_safe(chat_id: int, message_id: int):
    """Безопасное удаление"""
    try:
        await bot.delete_message(chat_id, message_id)
        logger.debug(f"🗑️ Удалено {message_id}")
    except Exception as e:
        logger.debug(f"⚠️ Не удалил {message_id}: {e}")

async def cleanup_all_temp_messages(chat_id: int):
    """Удалить ВСЕ временные сообщения"""
    if chat_id in temp_messages:
        for msg_id in temp_messages[chat_id][:]:
            await delete_message_safe(chat_id, msg_id)
        temp_messages[chat_id] = []
        logger.debug(f"🧹 Очистка temp завершена")
    
    # 🔹 УДАЛЯЕМ МЕНЮ
    if chat_id in menu_messages:
        await delete_message_safe(chat_id, menu_messages[chat_id])
        del menu_messages[chat_id]
        logger.debug(f"🧹 Меню удалено")

async def add_temp_message(chat_id: int, message_id: int):
    """Добавить в список на удаление"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)

async def update_preview(state: FSMContext, chat_id: int):
    """Обновить превью БЕЗ проверки типа (используем state)"""
    logger.debug(f"🔄 UPDATE_PREVIEW: chat_id={chat_id}")
    try:
        data = await state.get_data()
        logger.debug(f"💾 STATE: step={data.get('step')}, media_type={data.get('media_type')}")
        
        text_content = data.get('text', '')
        media_id = data.get('media_id')
        media_type = data.get('media_type')
        buttons_data = data.get('buttons', [])
        
        # Формируем caption
        if not text_content:
            caption = "<b>📝 ПРЕВЬЮ ПОСТА</b>\n\n<i>_(Нажмите ✏️ Редактировать текст или 🤖 ИИ)_</i>"
        else:
            caption = text_content
        
        if buttons_data:
            btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
            caption += f"\n\n━━━━━━━━━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
        
        stored_msg_id = preview_messages.get(chat_id)
        logger.debug(f"💾 Stored msg_id: {stored_msg_id}")
        
        if stored_msg_id:
            # 🔹 ИСПОЛЬЗУЕМ ТИП ИЗ STATE, НЕ ПРОВЕРЯЕМ
            old_type = data.get('_preview_media_type', 'text')
            logger.debug(f"📍 Старый тип (из state): {old_type}, новый: {media_type}")
            
            try:
                if media_type == 'photo' and media_id:
                    await bot.edit_message_caption(
                        chat_id=chat_id, message_id=stored_msg_id,
                        caption=caption, parse_mode=ParseMode.HTML
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
                logger.info(f"✅ ПРЕВЬЮ ОБНОВЛЕНО")
                
            except TelegramBadRequest as e:
                error_str = str(e)
                logger.warning(f"⚠️ Ошибка edit: {e}")
                
                if "message to edit not found" in error_str or "message can't be edited" in error_str:
                    logger.warning(f"⚠️ Превью недоступно, создаём новое")
                    if chat_id in preview_messages:
                        del preview_messages[chat_id]
                    await state.update_data(_preview_media_type=None)
                    return await update_preview(state, chat_id)
                elif "message is not modified" in error_str:
                    logger.debug("ℹ️ Контент не изменился")
                    return
                else:
                    raise
        else:
            logger.info(f"🆕 СОЗДАНИЕ ПРЕВЬЮ")
            new_msg = None
            
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(
                    chat_id=chat_id, photo=media_id,
                    caption=caption, parse_mode=ParseMode.HTML
                )
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(
                    chat_id=chat_id, video=media_id,
                    caption=caption, parse_mode=ParseMode.HTML
                )
            else:
                new_msg = await bot.send_message(
                    chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML
                )
            
            if new_msg:
                preview_messages[chat_id] = new_msg.message_id
                await state.update_data(_preview_media_type=media_type)
                logger.info(f"✅ ПРЕВЬЮ СОЗДАНО msg_id={new_msg.message_id}")
            
    except Exception as e:
        logger.error(f"❌ ОШИБКА update_preview: {e}", exc_info=True)
        raise

# === ГЛАВНОЕ МЕНЮ ===
@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    cid = message.chat.id
    logger.info(f"👤 START: {cid}")
    # 🔹 УДАЛЯЕМ ПРЕДЫДУЩЕЕ МЕНЮ
    await cleanup_all_temp_messages(cid)
    if cid in menu_messages:
        await delete_message_safe(cid, menu_messages[cid])

    msg = await message.answer(
        "🤖 <b>Пост-Триумф Live</b>\n\n"
        "➕ Новый пост | 📚 Кнопки | 🔗 Ссылки | 📋 Посты | ❓ Помощь",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard()
    )
    menu_messages[cid] = msg.message_id  # Сохраняем для удаления
    logger.info(f"✅ Меню отправлено")

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"❌ ОТМЕНА: {cid}")
    await state.clear()
    await cleanup_all_temp_messages(cid)
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
        del preview_messages[cid]
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🆕 НОВЫЙ ПОСТ: {cid}")
    # 🔹 УДАЛЯЕМ ВСЁ
    await cleanup_all_temp_messages(cid)
    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
        del preview_messages[cid]

    await state.clear()
    await state.update_data(
        step='media', text='', media_id=None, media_type=None,
        buttons=[], original_text=None, ai_keywords=None,
        smart_variant=-1, emoji_variant=0, ai_style=None,
        _preview_media_type=None
    )

    await update_preview(state, cid)

    # 🔹 КОРОТКАЯ ПОДСКАЗКА
    msg = await message.answer(
        "<b>📷 ШАГ 1/3: Медиа</b>\n\n"
        "📎 <b>Добавить фото:</b>\n"
        "1. Нажмите скрепку 📎 в поле ввода\n"
        "2. Выберите фото\n"
        "3. Отправьте\n\n"
        "⏭️ Или пропустите\n\n"
        "❓ Помощь для подробной инструкции",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard()
    )
    await add_temp_message(cid, msg.message_id)
    logger.info(f"✅ Новый пост начат")

@dp.message(F.text == "📋 Мои посты")
async def my_posts(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    posts = get_published_posts(cid, limit=50)
    if not posts:
        await message.answer("📋 Нет постов.", reply_markup=main_keyboard())
        return

    await message.answer(f"📋 <b>ПОСТЫ</b> ({len(posts)}):", parse_mode=ParseMode.HTML, reply_markup=posts_keyboard(posts))

@dp.message(F.text == "📚 Библиотека кнопок")
async def open_button_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    data = await state.get_data()
    library_return_points[cid] = data.get('step', 'main')
    buttons = get_saved_buttons(cid)
    await message.answer(f"📚 КНОПКИ", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(buttons, set(), 'button'))

@dp.message(F.text == "🔗 Библиотека ссылок")
async def open_link_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    data = await state.get_data()
    library_return_points[cid] = data.get('step', 'main')
    links = get_saved_links(cid)
    await message.answer(f"🔗 ССЫЛКИ", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(links, set(), 'link'))

# === ПОМОЩЬ ===
@dp.callback_query(lambda c: c.data.startswith('help:'))
async def help_callback(callback: types.CallbackQuery):
    parts = callback.data.split(':')
    step = parts[1] if len(parts) > 1 else 'main'
    logger.info(f"❓ ПОМОЩЬ: step={step}")
    help_text = get_help_text(step)
    await callback.message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard(step))
    await callback.answer()

# === ШАГ 1: МЕДИА ===
@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📸 ФОТО: {cid}")
    await cleanup_all_temp_messages(cid)
    data = await state.get_data()
    if data.get('step') != 'media':
        await delete_message_safe(cid, message.message_id)
        return

    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)

    msg = await message.answer(
        "<b>✅ Фото в превью!</b>\n\n"
        "➡️ Далее: Текст\n"
        "✏️ Или редактировать текст",
        parse_mode=ParseMode.HTML,
        reply_markup=media_keyboard(has_media=True)
    )
    await add_temp_message(cid, msg.message_id)

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🎬 ВИДЕО: {cid}")
    await cleanup_all_temp_messages(cid)
    data = await state.get_data()
    if data.get('step') != 'media':
        await delete_message_safe(cid, message.message_id)
        return

    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)

    msg = await message.answer("<b>✅ Видео в превью!</b>", parse_mode=ParseMode.HTML, reply_markup=media_keyboard(has_media=True))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⏭️ ПРОПУСК: {cid}")
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None, step='text')
    await update_preview(state, cid)

    msg = await message.answer(
        "<b>✏️ ШАГ 2/3: Текст</b>\n\n"
        "🤖 ИИ или вручную",
        parse_mode=ParseMode.HTML,
        reply_markup=text_keyboard(False, False)
    )
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🔄 Заменить медиа")
async def replace_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    msg = await message.answer("📎 Загрузите новое:", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🗑️ Удалить медиа")
async def delete_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    await message.answer("🗑️ Удалено", reply_markup=media_keyboard())

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➡️ К ТЕКСТУ: {cid}")
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='text')
    await update_preview(state, cid)
    data = await state.get_data()

    msg = await message.answer(
        "<b>✏️ ШАГ 2/3: Текст</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text')))
    )
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='media')
    await update_preview(state, cid)
    data = await state.get_data()
    await message.answer("📷 ШАГ 1/3: Медиа", parse_mode=ParseMode.HTML, reply_markup=media_keyboard(bool(data.get('media_id'))))

# === ШАГ 2: ТЕКСТ ===
@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    raw = data.get('text', '')
    if not raw:
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer("✏️ Введите текст:", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
        return

    # 🔹 ОТПРАВЛЯЕМ ТЕКСТ ПОЧАСТЯМ ЕСЛИ ДЛИННЫЙ
    clean = remove_emojis(remove_formatting(raw))
    await state.set_state(PostWorkflow.writing_text)

    if len(clean) > 4000:
        for i in range(0, len(clean), 4000):
            chunk = clean[i:i+4000]
            msg = await message.answer(f"✏️ Часть {i//4000 + 1}:\n\n{chunk}", reply_markup=cancel_keyboard())
            await add_temp_message(cid, msg.message_id)
        msg = await message.answer("📝 Отправьте исправленный текст целиком:", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
    else:
        msg = await message.answer(f"✏️ Исправьте и отправьте:\n\n{clean}", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    if not kws:
        msg = await message.answer("⚠️ Сначала «ИИ: Новый запрос»")
        await add_temp_message(cid, msg.message_id)
        return

    txt = generate_ai_text(kws, style=data.get('ai_style'))
    await state.update_data(text=txt, original_text=txt)
    await update_preview(state, cid)
    msg = await message.answer("✅ Обновлено", reply_markup=text_keyboard(True, True))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    hint = f"\nПрошлые: {kws}" if kws else ""
    await state.set_state(PostWorkflow.ai_input)
    msg = await message.answer(f"🤖 Ключевые слова:{hint}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt:
        msg = await message.answer("⚠️ Введите текст!")
        await add_temp_message(cid, msg.message_id)
        return

    clean_txt = remove_emojis(remove_formatting(txt))
    res = smart_format_text(clean_txt, 0, 0)
    await state.update_data(text=res['text'], original_text=txt, smart_variant=0, emoji_variant=0)
    emoji_variants[cid] = 0
    await update_preview(state, cid)
    msg = await message.answer("✅ Готово", reply_markup=text_keyboard(True, True))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
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
    msg = await message.answer(f"✅ Вариант {variant}", reply_markup=text_keyboard(True, True))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt:
        return
    cleaned = remove_emojis(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Уже нет")
        await add_temp_message(cid, msg.message_id)
        return

    await state.update_data(text=cleaned)
    await update_preview(state, cid)
    msg = await message.answer("✅ Удалено", reply_markup=text_keyboard(True, False))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    if not txt:
        return
    cleaned = remove_formatting(txt)
    if cleaned == txt:
        msg = await message.answer("ℹ️ Уже нет")
        await add_temp_message(cid, msg.message_id)
        return

    await state.update_data(text=cleaned, original_text=None, smart_variant=-1)
    await update_preview(state, cid)
    msg = await message.answer("✅ Снято", reply_markup=text_keyboard(True, False))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    if not data.get('text'):
        msg = await message.answer("⚠️ Введите текст!")
        await add_temp_message(cid, msg.message_id)
        return

    await state.update_data(step='buttons')
    await update_preview(state, cid)
    msg = await message.answer("<b>🔘 ШАГ 3/3: Кнопки</b>", parse_mode=ParseMode.HTML, reply_markup=buttons_keyboard(bool(data.get('buttons'))))
    await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.update_data(step='text')
    await update_preview(state, cid)
    data = await state.get_data()
    await message.answer("✏️ ШАГ 2/3: Текст", parse_mode=ParseMode.HTML, reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))

@dp.message(F.text == "🔗 Добавить ссылку в текст")
async def add_text_link(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    links = get_saved_links(cid)
    if not links:
        msg = await message.answer("📚 Нет ссылок.", reply_markup=library_keyboard([], set(), 'link'))
        await add_temp_message(cid, msg.message_id)
        return

    await state.set_state(PostWorkflow.selecting_link)
    msg = await message.answer("🔗 Выберите:", reply_markup=library_keyboard(links, set(), 'link'))
    await add_temp_message(cid, msg.message_id)

# === ШАГ 3: КНОПКИ ===
@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    await state.set_state(AddButtonSteps.waiting_for_text)
    msg = await message.answer("➕ Текст кнопки:", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    text = message.text.strip()
    if ' - ' in text and ('http://' in text or 'https://' in text):
        parts = text.split(' - ', 1)
        if len(parts) == 2:
            btn_text, btn_url = parts[0].strip(), parts[1].strip()
            if btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
                success, _ = save_button(cid, btn_text, btn_url)
                if success:
                    data = await state.get_data()
                    buttons = data.get('buttons', [])
                    buttons.append([{'text': btn_text, 'url': btn_url}])
                    await state.update_data(buttons=buttons)
                    await update_preview(state, cid)
                    msg = await message.answer(f"✅ {btn_text}", reply_markup=buttons_keyboard(True))
                    await add_temp_message(cid, msg.message_id)
                    await state.set_state(None)
                    return

    await state.update_data(new_btn_text=text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    msg = await message.answer("2️⃣ Ссылка:", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer("❌ http:// или https://", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
        return

    data = await state.get_data()
    success, _ = save_button(cid, data.get('new_btn_text', ''), url)

    if success:
        buttons = data.get('buttons', [])
        buttons.append([{'text': data['new_btn_text'], 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(state, cid)
        msg = await message.answer("✅ Добавлено", reply_markup=buttons_keyboard(True))
        await add_temp_message(cid, msg.message_id)
    else:
        msg = await message.answer("⚠️ Уже есть", reply_markup=buttons_keyboard(True))
        await add_temp_message(cid, msg.message_id)

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    data = await state.get_data()
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])

    if not txt and not media_id:
        msg = await message.answer("⚠️ Пустой пост!")
        await add_temp_message(cid, msg.message_id)
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

    if cid in preview_messages:
        await delete_message_safe(cid, preview_messages[cid])
        del preview_messages[cid]
    if cid in menu_messages:
        await delete_message_safe(cid, menu_messages[cid])
        del menu_messages[cid]
    await state.clear()

    await message.answer("✅ ОПУБЛИКОВАНО!", reply_markup=finish_keyboard())

# === БИБЛИОТЕКИ ===
@dp.callback_query(lambda c: c.data.startswith('lib:') or c.data.startswith('link_lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    lib_type = 'button' if parts[0] == 'lib' else 'link'
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    logger.debug(f"📚 LIB CALLBACK: type={lib_type}, act={act}")

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
        
        logger.debug(f"💾 Выбрано: {len(chosen)}")
        
        if not chosen:
            await callback.answer("⚠️ Пусто", show_alert=True)
            return
        
        if lib_type == 'button':
            buttons = data.get('buttons', [])
            buttons.extend([[{'text': b['text'], 'url': b['url']}] for b in chosen])
            await state.update_data(buttons=buttons, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            
            rp = library_return_points.get(cid, 'buttons')
            if rp == 'media':
                await callback.message.answer("✅ Кнопки!", reply_markup=media_keyboard(bool(data.get('media_id'))))
            elif rp == 'text':
                await callback.message.answer("✅ Кнопки!", reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))
            else:
                await callback.message.answer("✅ Кнопки!", reply_markup=buttons_keyboard(True))
        else:
            current_text = data.get('text', '')
            for link in chosen:
                current_text += f'\n<a href="{link["url"]}">{link["text"]}</a>'
            await state.update_data(text=current_text, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            await callback.message.answer("✅ Ссылки!", reply_markup=text_keyboard(True, bool(data.get('original_text'))))
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        rp = library_return_points.get(cid, 'main')
        if rp == 'media':
            data = await state.get_data()
            await callback.message.answer("<b>📷 Медиа</b>", parse_mode=ParseMode.HTML, reply_markup=media_keyboard(bool(data.get('media_id'))))
        elif rp == 'text':
            data = await state.get_data()
            await callback.message.answer("<b>✏️ Текст</b>", parse_mode=ParseMode.HTML, reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))
        elif rp == 'buttons':
            data = await state.get_data()
            await callback.message.answer("<b>🔘 Кнопки</b>", parse_mode=ParseMode.HTML, reply_markup=buttons_keyboard(bool(data.get('buttons'))))
        else:
            await callback.message.answer("🤖 <b>Пост-Триумф</b>", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        await callback.answer()

# === ТЕКСТ И ИИ ===
@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    txt = message.text
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)

    data = await state.get_data()
    await message.answer("✅ Текст!", reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    await cleanup_all_temp_messages(cid)
    await delete_message_safe(cid, message.message_id)
    kws = message.text.strip()
    await state.update_data(ai_keywords=kws)

    selected_style = random.choice(get_available_styles())
    txt = generate_ai_text(kws, style=selected_style)
    await state.update_data(text=txt, original_text=txt, smart_variant=-1, ai_style=selected_style)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    await update_preview(state, cid)

    await message.answer(f"✅ Стиль: {selected_style}", reply_markup=text_keyboard(True, True))

# === НЕ ПО ШАГУ ===
@dp.message()
async def handle_wrong_step(message: types.Message, state: FSMContext):
    cid = message.chat.id
    data = await state.get_data()
    current_step = data.get('step')
    if message.text in ["➕ Новый пост", "📚 Библиотека кнопок", "🔗 Библиотека ссылок", "📋 Мои посты", "❓ Помощь"]:
        return
    if message.text in ["⬅️ Назад: Медиа", "⬅️ Назад: Текст", "➡️ Далее: Текст", "➡️ Далее: Кнопки", "✅ ФИНИШ: Опубликовать", "❌ Отмена"]:
        return
    if not current_step:
        return

    await delete_message_safe(cid, message.message_id)
    msg = await message.answer(f"⚠️ Сейчас шаг {current_step.upper()}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)

# === ЗАПУСК ===
async def main():
    # 🔹 ПРОВЕРКА ПОДКЛЮЧЕНИЯ ПЕРЕД ЗАПУСКОМ
    connection_ok = await test_telegram_connection()
    
    if not connection_ok:
        logger.error("❌ ЗАПУСК ОТМЕНЁН: нет доступа к Telegram API")
        logger.error("💡 Решение:")
        logger.error("   1. Добавьте PROXY_URL в переменные окружения")
        logger.error("   2. Или используйте хостинг за пределами РФ")
        logger.error("   3. Или проверьте фаервол/сеть")
        return  # ⚠️ НЕ ЗАПУСКАТЬ БОТА БЕЗ СОЕДИНЕНИЯ
    
    # 🔹 СОЗДАНИЕ BOT С ПРОКСИ (ЕСЛИ НУЖЕН)
    if PROXY_URL:
        logger.info("🔄 Используем прокси...")
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        logger.info("🔌 Прямое подключение (без прокси)")
        bot = Bot(token=BOT_TOKEN)
    
    # 🔹 ДАЛЕЕ ОБЫЧНЫЙ ЗАПУСК
    try:
        await bot.delete_webhook()
        logger.info("🚀 ЗАПУСК БОТА...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}", exc_info=True)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
