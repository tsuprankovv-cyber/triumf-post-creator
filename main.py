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
from aiohttp import web

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
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

if not BOT_TOKEN:
    logger.error("❌ НЕТ ТОКЕНА!")
    raise ValueError("❌ Нет токена!")

logger.info(f"🔧 DEBUG режим: {DEBUG}")
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
        logger.debug(f"🗑️ Удалено сообщение {message_id} в чате {chat_id}")
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e):
            logger.debug(f"⚠️ Сообщение {message_id} уже удалено")
        else:
            logger.warning(f"⚠️ Не удалил {message_id}: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка удаления {message_id}: {type(e).__name__}: {e}")

async def cleanup_chat(chat_id: int, keep_preview=False):
    """Удалить ВСЕ временные сообщения в чате"""
    logger.debug(f"🧹 Очистка чата {chat_id} (keep_preview={keep_preview})")
    
    # Удаляем временные сообщения
    if chat_id in temp_messages:
        count = len(temp_messages[chat_id])
        for msg_id in temp_messages[chat_id][:]:
            await delete_message_safe(chat_id, msg_id)
        temp_messages[chat_id] = []
        logger.debug(f"✅ Очищено {count} временных сообщений")
    
    # Удаляем меню (если не сохраняем)
    if chat_id in menu_messages and not keep_preview:
        await delete_message_safe(chat_id, menu_messages[chat_id])
        del menu_messages[chat_id]
        logger.debug(f"✅ Меню удалено")

def add_temp(chat_id: int, message_id: int):
    """Добавить сообщение в список на удаление"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)
    logger.debug(f"📝 Добавлено сообщение {message_id} в temp для чата {chat_id}")

async def send_step_message(chat_id: int, text: str, step: str, reply_markup=None):
    """Отправить сообщение с шагом и сохранить ID для очистки"""
    full_text = f"<b>{step}</b>\n\n{text}"
    msg = await bot.send_message(chat_id, text=full_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    add_temp(chat_id, msg.message_id)
    logger.info(f"📤 Отправлено сообщение шага '{step}' в чат {chat_id}, msg_id={msg.message_id}")
    return msg

async def update_preview(state: FSMContext, chat_id: int):
    """Обновить превью поста"""
    logger.debug(f"🔄 update_preview: chat_id={chat_id}")
    
    try:
        data = await state.get_data()
        text_content = data.get('text', '')
        media_id = data.get('media_id')
        media_type = data.get('media_type')
        buttons_data = data.get('buttons', [])
        step = data.get('step', 'unknown')
        preview_message_id = data.get('preview_message_id')
        
        logger.debug(f"💾 STATE: media_type={media_type}, media_id={media_id[:20] if media_id else None}, text_len={len(text_content)}, buttons={len(buttons_data)}, preview_id={preview_message_id}")
        
        # Формируем текст превью
        if not text_content and not media_id:
            if step == 'media':
                caption = "<i>📷 Ожидание медиа...</i>"
            elif step == 'text':
                caption = "<i>✏️ Ожидание текста...</i>"
            elif step == 'buttons':
                caption = "<i>🔘 Ожидание кнопок...</i>"
            else:
                caption = "<i>📝 ПРЕВЬЮ ПОСТА</i>"
        elif not text_content:
            caption = "<i>📝 Добавьте текст или используйте ИИ</i>"
        else:
            caption = text_content
        
        # Добавляем кнопки в превью
        if buttons_data:
            btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
            caption += f"\n\n━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
        
        # Добавляем метку превью
        caption = f"<b>👁️ ПРЕВЬЮ ПОСТА</b>\n\n{caption}"
        
        # Добавляем подсказку по шагу
        step_hints = {
            'media': '\n\n<i>📷 Шаг 1/3: Медиа</i>',
            'text': '\n\n<i>✏️ Шаг 2/3: Текст</i>',
            'buttons': '\n\n<i>🔘 Шаг 3/3: Кнопки</i>'
        }
        caption += step_hints.get(step, '')
        
        # Определяем текущий тип превью из state
        current_preview_type = data.get('_preview_type', 'text')
        logger.debug(f"📍 Тип превью: текущий={current_preview_type}, новый={media_type or 'text'}")
        
        if preview_message_id:
            # Пытаемся отредактировать существующее превью
            try:
                # Проверяем совместимость типов
                if current_preview_type == 'text' and media_type in ['photo', 'video']:
                    # Нельзя редактировать текст в фото/видео — создаём новое
                    logger.warning(f"⚠️ Смена типа превью {current_preview_type} → {media_type}, создаём новое")
                    await delete_message_safe(chat_id, preview_message_id)
                    preview_message_id = None
                    await state.update_data(preview_message_id=None, _preview_type=None)
                elif current_preview_type in ['photo', 'video'] and media_type is None:
                    # Нельзя редактировать фото/видео в текст — создаём новое
                    logger.warning(f"⚠️ Смена типа превью {current_preview_type} → text, создаём новое")
                    await delete_message_safe(chat_id, preview_message_id)
                    preview_message_id = None
                    await state.update_data(preview_message_id=None, _preview_type=None)
                else:
                    # Типы совместимы — редактируем
                    if media_type == 'photo' and media_id:
                        await bot.edit_message_caption(chat_id=chat_id, message_id=preview_message_id, caption=caption, parse_mode=ParseMode.HTML)
                    elif media_type == 'video' and media_id:
                        await bot.edit_message_caption(chat_id=chat_id, message_id=preview_message_id, caption=caption, parse_mode=ParseMode.HTML)
                    else:
                        await bot.edit_message_text(chat_id=chat_id, message_id=preview_message_id, text=caption, parse_mode=ParseMode.HTML)
                    
                    logger.info(f"✅ Превью обновлено (msg_id={preview_message_id})")
                    return
                    
            except TelegramBadRequest as e:
                error_str = str(e)
                logger.warning(f"⚠️ Ошибка редактирования превью: {e}")
                
                if "message to edit not found" in error_str or "message can't be edited" in error_str:
                    logger.warning(f"⚠️ Превью недоступно, создаём новое")
                    preview_message_id = None
                    await state.update_data(preview_message_id=None, _preview_type=None)
                elif "message is not modified" in error_str:
                    logger.debug("ℹ️ Контент превью не изменился")
                    return
                elif "there is no caption" in error_str:
                    logger.warning(f"⚠️ Попытка edit_caption на текстовом сообщении, создаём новое")
                    await delete_message_safe(chat_id, preview_message_id)
                    preview_message_id = None
                    await state.update_data(preview_message_id=None, _preview_type=None)
                else:
                    raise
        
        # Создаём новое превью
        logger.info(f"🆕 Создание нового превью: type={media_type or 'text'}")
        new_msg = None
        
        if media_type == 'photo' and media_id:
            new_msg = await bot.send_photo(chat_id=chat_id, photo=media_id, caption=caption, parse_mode=ParseMode.HTML)
            await state.update_data(_preview_type='photo')
        elif media_type == 'video' and media_id:
            new_msg = await bot.send_video(chat_id=chat_id, video=media_id, caption=caption, parse_mode=ParseMode.HTML)
            await state.update_data(_preview_type='video')
        else:
            new_msg = await bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML)
            await state.update_data(_preview_type='text')
        
        if new_msg:
            await state.update_data(preview_message_id=new_msg.message_id)
            logger.info(f"✅ Превью создано (msg_id={new_msg.message_id}, type={media_type or 'text'})")
                
    except Exception as e:
        logger.error(f"❌ ОШИБКА update_preview: {type(e).__name__}: {e}", exc_info=True)
        raise

# === ГЛАВНОЕ МЕНЮ ===
@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    cid = message.chat.id
    logger.info(f"👤 START: {cid}")
    
    await cleanup_chat(cid, keep_preview=False)
    
    text = (
        "🤖 <b>Пост-Триумф Live</b>\n\n"
        "➕ <b>Новый пост</b> — создать пост с медиа, текстом и кнопками\n"
        "📚 <b>Кнопки</b> — библиотека готовых кнопок\n"
        "🔗 <b>Ссылки</b> — библиотека ссылок для вставки в текст\n"
        "📋 <b>Посты</b> — история опубликованных постов\n"
        "❓ <b>Помощь</b> — подробная инструкция"
    )
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
    menu_messages[cid] = msg.message_id
    logger.info(f"✅ Меню отправлено (msg_id={msg.message_id})")

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"❌ ОТМЕНА: {cid}")
    
    # Получаем preview_message_id из state перед очисткой
    data = await state.get_data()
    preview_id = data.get('preview_message_id')
    
    await state.clear()
    await cleanup_chat(cid, keep_preview=False)
    
    if preview_id:
        await delete_message_safe(cid, preview_id)
        logger.info(f"🗑️ Превью удалено при отмене (msg_id={preview_id})")
    
    await message.answer("❌ Отменено. Возврат в главное меню.", reply_markup=main_keyboard())
    logger.info("✅ Отмена выполнена")

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🆕 НОВЫЙ ПОСТ: {cid}")
    
    # Очищаем чат, но НЕ удаляем превью (его ещё нет)
    await cleanup_chat(cid, keep_preview=False)
    
    # Сбрасываем состояние и инициализируем данные
    await state.clear()
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
        preview_message_id=None,
        _preview_type='text'
    )
    
    logger.info(f"💾 STATE инициализирован: step=media")
    
    # Создаём пустое превью
    await update_preview(state, cid)
    
    # Отправляем инструкцию по шагу 1/3
    text = (
        "📎 <b>Добавить медиа:</b>\n"
        "• Отправьте фото или видео прямо в чат\n"
        "• Или нажмите «⏭️ Пропустить медиа»\n"
        "• Нажмите «❓ Помощь» для подробной инструкции"
    )
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard())
    logger.info("✅ Начат новый пост, шаг 1/3")

@dp.message(F.text == "📋 Мои посты")
async def my_posts(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📋 МОИ ПОСТЫ: {cid}")
    await cleanup_chat(cid, keep_preview=False)
    
    posts = get_published_posts(cid, limit=50)
    if not posts:
        await message.answer("📋 У вас пока нет опубликованных постов.", reply_markup=main_keyboard())
        return
    
    await message.answer(f"📋 <b>Ваши посты</b> ({len(posts)}):", parse_mode=ParseMode.HTML, reply_markup=posts_keyboard(posts))

@dp.message(F.text == "📚 Библиотека кнопок")
async def open_button_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📚 БИБЛИОТЕКА КНОПОК: {cid}")
    await cleanup_chat(cid, keep_preview=False)
    
    data = await state.get_data()
    help_context[cid] = data.get('step', 'main')
    
    buttons = get_saved_buttons(cid)
    await message.answer(f"📚 <b>Библиотека кнопок</b>\n\nНажмите на кнопку, чтобы добавить её в пост:", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(buttons, set(), 'button'))

@dp.message(F.text == "🔗 Библиотека ссылок")
async def open_link_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔗 БИБЛИОТЕКА ССЫЛОК: {cid}")
    await cleanup_chat(cid, keep_preview=False)
    
    data = await state.get_data()
    help_context[cid] = data.get('step', 'main')
    
    links = get_saved_links(cid)
    await message.answer(f"🔗 <b>Библиотека ссылок</b>\n\nНажмите на ссылку, чтобы добавить её в текст:", parse_mode=ParseMode.HTML, reply_markup=library_keyboard(links, set(), 'link'))

# === ПОМОЩЬ ===
@dp.callback_query(lambda c: c.data.startswith('help:'))
async def help_callback(callback: types.CallbackQuery, state: FSMContext):
    cid = callback.message.chat.id
    parts = callback.data.split(':')
    step = parts[1] if len(parts) > 1 else 'main'
    
    logger.info(f"❓ ПОМОЩЬ: chat_id={cid}, step={step}")
    
    # Получаем текущий шаг из state для контекстной помощи
    if step == 'current':
        data = await state.get_data()
        step = data.get('step', 'main')
        logger.info(f"📍 Контекстная помощь для шага: {step}")
    
    help_text = get_help_text(step)
    await callback.message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard(step))
    await callback.answer()

# === ШАГ 1: МЕДИА ===
@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📸 ФОТО: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    current_step = data.get('step')
    logger.info(f"💾 STATE до: step={current_step}, media_id={data.get('media_id')}")
    
    # Сохраняем фото
    media_id = message.photo[-1].file_id
    await state.update_data(media_type='photo', media_id=media_id)
    
    logger.info(f"💾 STATE после: media_type=photo, media_id={media_id[:20]}...")
    
    # Обновляем превью
    await update_preview(state, cid)
    
    # Удаляем сообщение с фото (оно уже в превью)
    await delete_message_safe(cid, message.message_id)
    
    # Показываем следующий шаг
    text = (
        "✅ <b>Фото добавлено в превью!</b>\n\n"
        "➡️ Нажмите «Далее: Текст» для продолжения\n"
        "✏️ Или «Редактировать текст» чтобы добавить описание\n"
        "🔄 Или «Заменить медиа» для другого фото"
    )
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard(has_media=True))
    logger.info("✅ Фото обработано, показан переход к тексту")

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🎬 ВИДЕО: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    
    data = await state.get_data()
    logger.info(f"💾 STATE до: step={data.get('step')}")
    
    media_id = message.video.file_id
    await state.update_data(media_type='video', media_id=media_id)
    await update_preview(state, cid)
    await delete_message_safe(cid, message.message_id)
    
    text = "✅ <b>Видео добавлено в превью!</b>\n\n➡️ Нажмите «Далее: Текст» для продолжения"
    await send_step_message(cid, text, "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard(has_media=True))

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⏭️ ПРОПУСК МЕДИА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None, step='text')
    await update_preview(state, cid)
    
    text = (
        "✏️ <b>ШАГ 2/3: Текст</b>\n\n"
        "• Напишите текст вручную\n"
        "• Или используйте «🤖 ИИ: Новый запрос» для генерации\n"
        "• Нажмите «🪄 Сделать красиво» для авто-форматирования"
    )
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(False, False))

@dp.message(F.text == "🔄 Заменить медиа")
async def replace_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔄 ЗАМЕНИТЬ МЕДИА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    
    await send_step_message(cid, "📎 Отправьте новое фото или видео:", "📷 ШАГ 1/3: Медиа", reply_markup=cancel_keyboard())

@dp.message(F.text == "🗑️ Удалить медиа")
async def delete_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🗑️ УДАЛИТЬ МЕДИА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(media_type=None, media_id=None)
    await update_preview(state, cid)
    
    await message.answer("🗑️ Медиа удалено из превью.", reply_markup=media_keyboard())

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➡️ ПЕРЕХОД К ТЕКСТУ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='text')
    await update_preview(state, cid)
    
    data = await state.get_data()
    has_text = bool(data.get('text'))
    has_original = bool(data.get('original_text'))
    
    logger.info(f"💾 STATE: step=text, has_text={has_text}, has_original={has_original}")
    
    text = (
        "✏️ <b>ШАГ 2/3: Текст</b>\n\n"
        "• Напишите текст или отредактируйте существующий\n"
        "• Используйте ИИ для генерации или улучшения текста\n"
        "• ⬅️ Назад: Медиа — вернуться к работе с фото"
    )
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(has_text, has_original))

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⬅️ НАЗАД К МЕДИА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='media')
    await update_preview(state, cid)
    
    data = await state.get_data()
    await send_step_message(cid, "📷 Выберите действие с медиа:", "📷 ШАГ 1/3: Медиа", reply_markup=media_keyboard(bool(data.get('media_id'))))

# === ШАГ 2: ТЕКСТ ===
@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"✏️ РЕДАКТИРОВАТЬ ТЕКСТ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    raw = data.get('text', '')
    
    if not raw:
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer("✏️ <b>Введите текст:</b>\n\nОтправьте текст, который хотите использовать в посте.", parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
        add_temp(cid, msg.message_id)
        return
    
    # Показываем текущий текст для редактирования
    clean = remove_emojis(remove_formatting(raw))
    await state.set_state(PostWorkflow.writing_text)
    
    if len(clean) > 4000:
        for i in range(0, len(clean), 4000):
            chunk = clean[i:i+4000]
            msg = await message.answer(f"✏️ Часть {i//4000 + 1}:\n\n<code>{chunk}</code>", parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
            add_temp(cid, msg.message_id)
        msg = await message.answer("📝 <b>Отправьте исправленный текст целиком:</b>", parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
        add_temp(cid, msg.message_id)
    else:
        msg = await message.answer(f"✏️ <b>Исправьте и отправьте:</b>\n\n<code>{clean}</code>", parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
        add_temp(cid, msg.message_id)

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"✍️ ВВОД ТЕКСТА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    txt = message.text
    
    # Сохраняем текст
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    
    # Обновляем превью
    await update_preview(state, cid)
    
    # Показываем следующие опции
    data = await state.get_data()
    has_text = bool(data.get('text'))
    has_original = bool(data.get('original_text'))
    
    logger.info(f"💾 STATE: text_len={len(txt)}, has_original={has_original}")
    
    text = "✅ <b>Текст сохранён!</b>\n\nВыберите следующее действие:"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(has_text, has_original))
    logger.info("✅ Текст сохранён, превью обновлено")

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🤖 ИИ НОВЫЙ ЗАПРОС: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    hint = f"\n\n<i>Прошлый запрос: {kws}</i>" if kws else ""
    
    await state.set_state(PostWorkflow.ai_input)
    text = f"🤖 <b>Опишите, о чём написать:</b>{hint}\n\nПример: «туризм на Байкале, зимние развлечения, омуль»"
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🤖 ИИ ОБРАБОТКА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    kws = message.text.strip()
    await state.update_data(ai_keywords=kws)
    
    # Генерируем текст (каждый раз новый!)
    selected_style = random.choice(get_available_styles())
    txt = generate_ai_text(kws, style=selected_style)
    
    # СНАЧАЛА сохраняем в state, ПОТОМ обновляем превью
    await state.update_data(text=txt, original_text=txt, smart_variant=-1, ai_style=selected_style)
    save_draft(cid, {'text': txt}, 'text')
    await state.set_state(None)
    
    # Обновляем превью (теперь текст будет виден!)
    await update_preview(state, cid)
    
    text = f"✅ <b>Текст сгенерирован!</b>\n\n<i>Стиль: {selected_style}</i>\n\nВыберите действие:"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(True, True))
    logger.info(f"✅ ИИ текст сгенерирован, стиль: {selected_style}")

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🤖 ИИ ОБНОВЛЕНИЕ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    kws = data.get('ai_keywords', '')
    
    if not kws:
        await message.answer("⚠️ Сначала создайте запрос через «🤖 ИИ: Новый запрос»", reply_markup=text_keyboard(True, True))
        return
    
    # Генерируем НОВЫЙ текст (не тот же самый!)
    selected_style = random.choice(get_available_styles())
    txt = generate_ai_text(kws, style=selected_style)
    
    await state.update_data(text=txt, original_text=txt, ai_style=selected_style)
    await update_preview(state, cid)
    
    await message.answer("✅ Текст обновлён!", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🪄 СДЕЛАТЬ КРАСИВО: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Сначала введите текст!", reply_markup=text_keyboard(False, False))
        return
    
    clean_txt = remove_emojis(remove_formatting(txt))
    res = smart_format_text(clean_txt, 0, 0)
    
    await state.update_data(text=res['text'], original_text=txt, smart_variant=0, emoji_variant=0)
    await update_preview(state, cid)
    
    await message.answer("✅ Текст отформатирован!", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔄 ЭМОДЗИ (СМЕНИТЬ): {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста для форматирования")
        return
    
    # Генерируем НОВЫЙ вариант эмодзи через ИИ
    variant = data.get('emoji_variant', 0) + 1
    clean_orig = remove_emojis(remove_formatting(data.get('original_text', txt)))
    res = smart_format_text(clean_orig, data.get('smart_variant', 0), variant)
    
    await state.update_data(text=res['text'], emoji_variant=variant)
    await update_preview(state, cid)
    
    await message.answer(f"✅ Вариант эмодзи #{variant}", reply_markup=text_keyboard(True, True))

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🧹 БЕЗ ЭМОДЗИ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста для форматирования")
        return
    
    cleaned = remove_emojis(txt)
    if cleaned == txt:
        await message.answer("ℹ️ Эмодзи уже нет")
        return
    
    await state.update_data(text=cleaned)
    await update_preview(state, cid)
    
    await message.answer("✅ Эмодзи удалены", reply_markup=text_keyboard(True, False))

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📄 БЕЗ ФОРМАТА: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    txt = data.get('text', '')
    
    if not txt:
        await message.answer("⚠️ Нет текста для форматирования")
        return
    
    cleaned = remove_formatting(txt)
    if cleaned == txt:
        await message.answer("ℹ️ Форматирование уже снято")
        return
    
    await state.update_data(text=cleaned, original_text=None, smart_variant=-1)
    await update_preview(state, cid)
    
    await message.answer("✅ Форматирование снято", reply_markup=text_keyboard(True, False))

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➡️ ПЕРЕХОД К КНОПКАМ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    data = await state.get_data()
    
    if not data.get('text'):
        await message.answer("⚠️ Сначала добавьте текст!", reply_markup=text_keyboard(False, False))
        return
    
    await state.update_data(step='buttons')
    await update_preview(state, cid)
    
    text = (
        "🔘 <b>ШАГ 3/3: Кнопки</b>\n\n"
        "• «➕ Добавить кнопку» — создать новую\n"
        "• «📚 Библиотека кнопок» — выбрать из сохранённых\n"
        "• «✅ ФИНИШ» — опубликовать пост\n"
        "• ⬅️ Назад: Текст — вернуться к редактированию"
    )
    await send_step_message(cid, text, "🔘 ШАГ 3/3: Кнопки", reply_markup=buttons_keyboard(bool(data.get('buttons'))))

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⬅️ НАЗАД К ТЕКСТУ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.update_data(step='text')
    await update_preview(state, cid)
    
    data = await state.get_data()
    text = "✏️ <b>ШАГ 2/3: Текст</b>\n\nВыберите действие:"
    await send_step_message(cid, text, "✏️ ШАГ 2/3: Текст", reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))

# === ШАГ 3: КНОПКИ ===
@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➕ ДОБАВИТЬ КНОПКУ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    await state.set_state(AddButtonSteps.waiting_for_text)
    
    text = "➕ <b>Текст кнопки:</b>\n\nОтправьте текст, который будет на кнопке.\n\n<i>Совет: можно сразу в формате «Текст - ссылка»</i>"
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔤 ТЕКСТ КНОПКИ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    text = message.text.strip()
    
    # Если сразу со ссылкой
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
                    await message.answer(f"✅ Кнопка «{btn_text}» добавлена!", reply_markup=buttons_keyboard(True))
                    await state.set_state(None)
                    return
    
    # Сохраняем текст и ждём ссылку
    await state.update_data(new_btn_text=text)
    await state.set_state(AddButtonSteps.waiting_for_url)
    
    text = "🔗 <b>Ссылка для кнопки:</b>\n\nОтправьте URL (начинается с http://, https://, t.me/ или tg://)"
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔗 ССЫЛКА КНОПКИ: {cid}")
    
    await cleanup_chat(cid, keep_preview=True)
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        msg = await message.answer("❌ <b>Неверный формат ссылки</b>\n\nСсылка должна начинаться с:\n• http://\n• https://\n• t.me/\n• tg://", parse_mode=ParseMode.HTML, reply_markup=cancel_keyboard())
        add_temp(cid, msg.message_id)
        return
    
    data = await state.get_data()
    btn_text = data.get('new_btn_text', '')
    success, _ = save_button(cid, btn_text, url)
    
    if success:
        buttons = data.get('buttons', [])
        buttons.append([{'text': btn_text, 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None)
        await state.set_state(None)
        await update_preview(state, cid)
        await message.answer(f"✅ Кнопка «{btn_text}» добавлена!", reply_markup=buttons_keyboard(True))
    else:
        await message.answer(f"⚠️ Кнопка «{btn_text}» уже существует", reply_markup=buttons_keyboard(True))

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"✅ ФИНИШ: публикация поста в чате {cid}")
    
    # Получаем preview_message_id перед очисткой state
    data = await state.get_data()
    preview_id = data.get('preview_message_id')
    
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    if not txt and not media_id:
        await message.answer("⚠️ <b>Пост пустой!</b>\n\nДобавьте текст или медиа перед публикацией.", parse_mode=ParseMode.HTML)
        return
    
    # Создаём клавиатуру
    final_kb = InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data:
        final_kb.adjust(1)
    
    # Публикуем
    try:
        if media_type == 'photo' and media_id:
            await bot.send_photo(chat_id=cid, photo=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        elif media_type == 'video' and media_id:
            await bot.send_video(chat_id=cid, video=media_id, caption=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        else:
            await bot.send_message(chat_id=cid, text=txt, parse_mode=ParseMode.HTML, reply_markup=final_kb.as_markup())
        
        # Сохраняем в историю
        save_published_post(cid, media_type, media_id, txt, buttons_data)
        logger.info(f"✅ Пост опубликован в чате {cid}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {type(e).__name__}: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка публикации: {e}")
        return
    
    # Очищаем состояние и чат
    await state.clear()
    await cleanup_chat(cid, keep_preview=False)
    
    # Удаляем превью
    if preview_id:
        await delete_message_safe(cid, preview_id)
        logger.info(f"🗑️ Превью удалено после публикации (msg_id={preview_id})")
    
    if cid in menu_messages:
        await delete_message_safe(cid, menu_messages[cid])
        del menu_messages[cid]
    
    await message.answer("🎉 <b>ПОСТ ОПУБЛИКОВАН!</b>\n\nЧто дальше?", reply_markup=finish_keyboard())
    logger.info("✅ Публикация завершена, состояние очищено")

# === БИБЛИОТЕКИ (кнопки/ссылки) ===
@dp.callback_query(lambda c: c.data.startswith('lib:') or c.data.startswith('link_lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    lib_type = 'button' if parts[0] == 'lib' else 'link'
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    logger.debug(f"📚 LIB CALLBACK: type={lib_type}, act={act}, chat_id={cid}")
    
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
        
        logger.info(f"💾 Применено {len(chosen)} элементов из библиотеки")
        
        if not chosen:
            await callback.answer("⚠️ Ничего не выбрано", show_alert=True)
            return
        
        if lib_type == 'button':
            buttons = data.get('buttons', [])
            buttons.extend([[{'text': b['text'], 'url': b['url']}] for b in chosen])
            await state.update_data(buttons=buttons, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            
            rp = help_context.get(cid, 'buttons')
            if rp == 'media':
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=media_keyboard(True))
            elif rp == 'text':
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=text_keyboard(True, True))
            else:
                await callback.message.answer("✅ Кнопки добавлены!", reply_markup=buttons_keyboard(True))
        else:
            current_text = data.get('text', '')
            for link in chosen:
                current_text += f'\n<a href="{link["url"]}">{link["text"]}</a>'
            await state.update_data(text=current_text, temp_selected=[])
            await update_preview(state, cid)
            await callback.message.delete()
            await callback.message.answer("✅ Ссылки добавлены!", reply_markup=text_keyboard(True, True))
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        rp = help_context.get(cid, 'main')
        
        if rp == 'media':
            data = await state.get_data()
            await callback.message.answer("<b>📷 ШАГ 1/3: Медиа</b>", parse_mode=ParseMode.HTML, reply_markup=media_keyboard(bool(data.get('media_id'))))
        elif rp == 'text':
            data = await state.get_data()
            await callback.message.answer("<b>✏️ ШАГ 2/3: Текст</b>", parse_mode=ParseMode.HTML, reply_markup=text_keyboard(bool(data.get('text')), bool(data.get('original_text'))))
        elif rp == 'buttons':
            data = await state.get_data()
            await callback.message.answer("<b>🔘 ШАГ 3/3: Кнопки</b>", parse_mode=ParseMode.HTML, reply_markup=buttons_keyboard(bool(data.get('buttons'))))
        else:
            await callback.message.answer("🤖 <b>Пост-Триумф Live</b>", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        await callback.answer()

# === НЕВЕРНЫЙ ШАГ (В САМОМ КОНЦЕ ФАЙЛА!) ===
@dp.message()
async def handle_unknown(message: types.Message, state: FSMContext):
    """Обработчик неизвестных сообщений — ДОЛЖЕН БЫТЬ В КОНЦЕ"""
    cid = message.chat.id
    data = await state.get_data()
    step = data.get('step')
    current_state = await state.get_state()
    text = message.text
    
    # Игнорируем системные команды и кнопки меню
    if text in ["➕ Новый пост", "📚 Библиотека кнопок", "🔗 Библиотека ссылок", "📋 Мои посты", "❓ Помощь", "❌ Отмена"]:
        logger.debug(f"⚙️ Игнорируем команду меню: {text}")
        return
    if text in ["⬅️ Назад: Медиа", "⬅️ Назад: Текст", "➡️ Далее: Текст", "➡️ Далее: Кнопки", "✅ ФИНИШ: Опубликовать"]:
        logger.debug(f"⚙️ Игнорируем кнопку навигации: {text}")
        return
    if text in ["⏭️ Пропустить медиа", "🔄 Заменить медиа", "🗑️ Удалить медиа", "➡️ Далее: Текст"]:
        logger.debug(f"⚙️ Игнорируем кнопку шага: {text}")
        return
    if text in ["✏️ Редактировать текст", "🤖 ИИ: Новый запрос", "🤖 ИИ: Обновить", "🪄 Сделать красиво", "🔄 Эмодзи (сменить)", "🧹 Без эмодзи", "📄 Без формата", "🔗 Добавить ссылку в текст", "➕ Добавить кнопку", "📚 Библиотека кнопок", "🔗 Библиотека ссылок", "✅ ФИНИШ: Опубликовать"]:
        logger.debug(f"⚙️ Игнорируем кнопку действия: {text}")
        return
    
    # Если бот ждёт ввода текста (состояние активно) — НЕ перехватываем!
    if current_state and current_state != '*':
        logger.debug(f"⚙️ Активное состояние {current_state}, игнорируем: {text[:50]}")
        return
    
    if not step:
        logger.debug(f"⚙️ Нет активного шага, игнорируем: {text[:50]}")
        return
    
    logger.warning(f"⚠️ Неверное сообщение на шаге {step}: '{text[:50]}...'")
    
    # Не удаляем сообщение пользователя — даём возможность исправить
    hint = {
        'media': "📷 Сейчас шаг: Медиа. Отправьте фото/видео или нажмите кнопку.",
        'text': "✏️ Сейчас шаг: Текст. Введите текст или используйте кнопку.",
        'buttons': "🔘 Сейчас шаг: Кнопки. Добавьте кнопку или завершите пост."
    }
    
    msg = await message.answer(f"⚠️ {hint.get(step, 'Неверное действие')}", reply_markup=cancel_keyboard())
    add_temp(cid, msg.message_id)

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
async def handle_health(request):
    """Health check endpoint"""
    return web.Response(text="OK")

async def start_web_server():
    """Запуск мини-веб-сервера для Render"""
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")

# === ЗАПУСК ===
async def main():
    logger.info("🔧 Запуск инициализации...")
    
    # Запускаем веб-сервер (для Render free tier)
    await start_web_server()
    
    # Запускаем бота
    await bot.delete_webhook()
    logger.info("🚀 ЗАПУСК БОТА...")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка polling: {type(e).__name__}: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    logger.info("📦 Запуск main.py")
    asyncio.run(main())
