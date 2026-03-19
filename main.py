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

# === НАСТРОЙКА ЛОГИРОВАНИЯ (МАКСИМАЛЬНЫЙ DEBUG) ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ НЕТ ТОКЕНА!")
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
library_return_points = {}  # {chat_id: 'media'|'text'|'buttons'|'main'}

STEP_CONFIG = {
    'media': {'num': 1, 'total': 3, 'name': 'Медиа'},
    'text': {'num': 2, 'total': 3, 'name': 'Текст'},
    'buttons': {'num': 3, 'total': 3, 'name': 'Кнопки'}
}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def delete_message_safe(chat_id: int, message_id: int, reason: str = ""):
    """Безопасное удаление сообщения с логированием"""
    try:
        logger.debug(f"🗑️ УДАЛЕНИЕ: msg_id={message_id}, chat_id={chat_id}, причина={reason}")
        await bot.delete_message(chat_id, message_id)
        logger.debug(f"✅ Успешно удалено {message_id}")
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ Не удалось удалить {message_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления {message_id}: {e}", exc_info=True)

async def add_temp_message(chat_id: int, message_id: int):
    """Добавить сообщение в список на удаление"""
    if chat_id not in temp_messages:
        temp_messages[chat_id] = []
    temp_messages[chat_id].append(message_id)
    logger.debug(f"📝 Добавлено временное сообщение {message_id} в чат {chat_id}. Всего: {len(temp_messages[chat_id])}")

async def cleanup_temp_messages(chat_id: int, reason: str = "cleanup"):
    """Удалить ВСЕ временные сообщения"""
    if chat_id in temp_messages:
        count = len(temp_messages[chat_id])
        logger.debug(f"🧹 ОЧИСТКА: {count} временных сообщений в чате {chat_id}, причина={reason}")
        for msg_id in temp_messages[chat_id][:]:  # Копия списка
            await delete_message_safe(chat_id, msg_id, reason)
        temp_messages[chat_id] = []
        logger.debug(f"✅ Очистка завершена")

async def update_preview(state: FSMContext, chat_id: int, force: bool = False):
    """Обновить превью с максимальным логированием"""
    logger.debug(f"🔄 UPDATE_PREVIEW: chat_id={chat_id}, force={force}")
    
    try:
        data = await state.get_data()
        logger.debug(f"💾 STATE DATA: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        step = data.get('step', 'media')
        text_content = data.get('text', '')
        media_id = data.get('media_id')
        media_type = data.get('media_type')
        buttons_data = data.get('buttons', [])
        
        logger.debug(f"📊 ПРЕВЬЮ ДАННЫЕ: step={step}, text_len={len(text_content) if text_content else 0}, media_type={media_type}, buttons={len(buttons_data)}")
        
        # Формируем caption
        if not text_content:
            caption = "<i>_(Нажмите ✏️ Редактировать текст)_</i>\n\n<i>Здесь будет ваш пост.</i>"
            logger.debug("📝 Caption: текст по умолчанию")
        else:
            caption = text_content
            logger.debug(f"📝 Caption: пользовательский текст ({len(text_content)} симв.)")
        
        # Добавляем кнопки в caption для просмотра
        if buttons_data:
            btn_list = "\n".join([f"🔘 {btn['text']}" for row in buttons_data for btn in row])
            caption += f"\n\n━━━━━━━━━━━━━━━━\n<b>📎 Кнопки:</b>\n{btn_list}"
            logger.debug(f"🔘 Добавлено {len(buttons_data)} кнопок в caption")
        
        stored_msg_id = preview_messages.get(chat_id)
        logger.debug(f"💾 Stored msg_id: {stored_msg_id}")
        
        if stored_msg_id and not force:
            # Пытаемся редактировать существующее
            old_media_type = data.get('_preview_media_type', 'text')
            logger.debug(f"📍 Старый тип: {old_media_type}, новый: {media_type}")
            
            try:
                if media_type == 'photo' and media_id:
                    logger.debug("📸 Редактируем фото caption")
                    await bot.edit_message_caption(
                        chat_id=chat_id, 
                        message_id=stored_msg_id,
                        caption=caption, 
                        parse_mode=ParseMode.HTML,
                        reply_markup=None  # Убираем клавиатуру у медиа
                    )
                    logger.debug("✅ Фото caption обновлён")
                    
                elif media_type == 'video' and media_id:
                    logger.debug("🎬 Редактируем видео caption")
                    await bot.edit_message_caption(
                        chat_id=chat_id, 
                        message_id=stored_msg_id,
                        caption=caption, 
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    )
                    logger.debug("✅ Видео caption обновлён")
                    
                else:
                    logger.debug("📝 Редактируем текст")
                    await bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=stored_msg_id,
                        text=caption, 
                        parse_mode=ParseMode.HTML
                    )
                    logger.debug("✅ Текст обновлён")
                
                await state.update_data(_preview_media_type=media_type)
                logger.info(f"✅ ПРЕВЬЮ ОБНОВЛЕНО chat_id={chat_id}")
                
            except TelegramBadRequest as e:
                error_str = str(e)
                logger.warning(f"⚠️ Ошибка редактирования: {e}")
                
                if "message to edit not found" in error_str or "message can't be edited" in error_str:
                    logger.warning(f"⚠️ Превью недоступно, создаём новое")
                    if chat_id in preview_messages:
                        del preview_messages[chat_id]
                    await state.update_data(_preview_media_type=None)
                    return await update_preview(state, chat_id, force=True)
                    
                elif "message is not modified" in error_str:
                    logger.debug("ℹ️ Контент не изменился, пропускаем")
                    return
                else:
                    logger.error(f"❌ Неизвестная ошибка: {e}")
                    raise
        else:
            # Создаём новое сообщение превью
            logger.info(f"🆕 СОЗДАНИЕ НОВОГО ПРЕВЬЮ chat_id={chat_id}")
            new_msg = None
            
            if media_type == 'photo' and media_id:
                logger.debug("📸 Отправляем новое фото")
                new_msg = await bot.send_photo(
                    chat_id=chat_id, 
                    photo=media_id,
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='photo')
                
            elif media_type == 'video' and media_id:
                logger.debug("🎬 Отправляем новое видео")
                new_msg = await bot.send_video(
                    chat_id=chat_id, 
                    video=media_id,
                    caption=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='video')
                
            else:
                logger.debug("📝 Отправляем текстовое сообщение")
                new_msg = await bot.send_message(
                    chat_id=chat_id, 
                    text=caption, 
                    parse_mode=ParseMode.HTML
                )
                await state.update_data(_preview_media_type='text')
            
            if new_msg:
                preview_messages[chat_id] = new_msg.message_id
                logger.info(f"✅ ПРЕВЬЮ СОЗДАНО chat_id={chat_id}, msg_id={new_msg.message_id}")
                
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА update_preview: {e}", exc_info=True)
        raise

async def send_step_hint(chat_id: int, step: str):
    """Отправить подсказку по шагу"""
    logger.debug(f"💡 Отправка подсказки для шага {step} в чат {chat_id}")
    try:
        help_text = get_help_text(step)
        msg = await bot.send_message(
            chat_id=chat_id,
            text=help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=help_keyboard(step)
        )
        await add_temp_message(chat_id, msg.message_id)
        logger.debug(f"✅ Подсказка отправлена msg_id={msg.message_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки подсказки: {e}")

def truncate_button_text(text: str, max_length: int = 18) -> str:
    """Обрезать текст кнопки чтобы поместился"""
    if len(text) <= max_length:
        return text
    # Умное сокращение с сохранением смысла
    words = text.split()
    result = []
    current_length = 0
    for word in words:
        if current_length + len(word) + 1 <= max_length - 2:
            result.append(word)
            current_length += len(word) + 1
        else:
            break
    if not result:
        return text[:max_length-2] + ".."
    return ' '.join(result) + ".."

# === ОБРАБОТЧИКИ: ГЛАВНОЕ МЕНЮ ===

@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    logger.info(f"👤 START: user_id={message.from_user.id}, username={message.from_user.username}")
    try:
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
        logger.info(f"✅ Главное меню отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка cmd_start: {e}", exc_info=True)

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"❌ ОТМЕНА: user_id={cid}")
    try:
        await state.clear()
        await cleanup_temp_messages(cid, "cancel")
        if cid in preview_messages:
            await delete_message_safe(cid, preview_messages[cid], "cancel")
            del preview_messages[cid]
        if cid in emoji_variants:
            del emoji_variants[cid]
        if cid in style_variants:
            del style_variants[cid]
        if cid in library_return_points:
            del library_return_points[cid]
        await message.answer("❌ Отменено.", reply_markup=main_keyboard())
        logger.info(f"✅ Отмена завершена")
    except Exception as e:
        logger.error(f"❌ Ошибка cmd_cancel: {e}", exc_info=True)

@dp.message(F.text == "➕ Новый пост")
async def start_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🆕 НОВЫЙ ПОСТ: user_id={cid}")
    try:
        await state.clear()
        await state.update_data(
            step='media', text='', media_id=None, media_type=None,
            buttons=[], original_text=None, ai_keywords=None,
            smart_variant=-1, emoji_variant=0, ai_style=None,
            _preview_media_type=None
        )
        emoji_variants[cid] = 0
        style_variants[cid] = None
        library_return_points[cid] = None
        
        await cleanup_temp_messages(cid, "new_post")
        if cid in preview_messages:
            await delete_message_safe(cid, preview_messages[cid], "new_post")
            del preview_messages[cid]
        
        await update_preview(state, cid, force=True)
        await send_step_hint(cid, 'media')
        
        await message.answer(
            "<b>📷 ШАГ 1/3: Медиа</b>\n\n"
            "📎 <b>Нажмите на скрепку</b> в поле ввода и прикрепите фото или видео.\n\n"
            "Или нажмите «⏭️ Пропустить медиа»",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard()
        )
        logger.info(f"✅ Новый пост инициирован")
    except Exception as e:
        logger.error(f"❌ Ошибка start_post: {e}", exc_info=True)

@dp.message(F.text == "📋 Мои посты")
async def my_posts(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📋 МОИ ПОСТЫ: user_id={cid}")
    try:
        posts = get_published_posts(cid, limit=50)
        logger.debug(f"💾 Найдено постов: {len(posts)}")
        
        if not posts:
            await message.answer(
                "📋 <b>У вас пока нет опубликованных постов.</b>\n\n"
                "Создайте первый пост через «➕ Новый пост»",
                parse_mode=ParseMode.HTML, 
                reply_markup=main_keyboard()
            )
            return
        
        await message.answer(
            f"📋 <b>ВАШИ ПОСТЫ</b> (всего: {len(posts)})\n\n"
            f"Выберите пост для редактирования или копирования:",
            parse_mode=ParseMode.HTML,
            reply_markup=posts_keyboard(posts)
        )
        logger.info(f"✅ Список постов отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка my_posts: {e}", exc_info=True)

@dp.message(F.text == "📚 Библиотека кнопок")
async def open_button_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📚 БИБЛИОТЕКА КНОПОК: user_id={cid}")
    try:
        data = await state.get_data()
        current_step = data.get('step', 'main')
        library_return_points[cid] = current_step if current_step else 'main'
        logger.debug(f"💾 Точка возврата: {library_return_points[cid]}")
        
        buttons = get_saved_buttons(cid)
        logger.debug(f"💾 Найдено кнопок: {len(buttons)}")
        
        await message.answer(
            f"📚 <b>БИБЛИОТЕКА КНОПОК</b> (макс. 10)\n\n"
            f"Отметьте ✅ нужные кнопки и нажмите «✅ Применить»",
            parse_mode=ParseMode.HTML,
            reply_markup=library_keyboard(buttons, set(), 'button')
        )
        logger.info(f"✅ Библиотека кнопок открыта")
    except Exception as e:
        logger.error(f"❌ Ошибка open_button_library: {e}", exc_info=True)

@dp.message(F.text == "🔗 Библиотека ссылок")
async def open_link_library(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔗 БИБЛИОТЕКА ССЫЛОК: user_id={cid}")
    try:
        data = await state.get_data()
        current_step = data.get('step', 'main')
        library_return_points[cid] = current_step if current_step else 'main'
        
        links = get_saved_links(cid)
        logger.debug(f"💾 Найдено ссылок: {len(links)}")
        
        await message.answer(
            f"🔗 <b>БИБЛИОТЕКА ССЫЛОК</b> (макс. 10)\n\n"
            f"Выберите ссылку для вставки в текст",
            parse_mode=ParseMode.HTML,
            reply_markup=library_keyboard(links, set(), 'link')
        )
        logger.info(f"✅ Библиотека ссылок открыта")
    except Exception as e:
        logger.error(f"❌ Ошибка open_link_library: {e}", exc_info=True)

# === ОБРАБОТЧИКИ: ШАГ 1 (МЕДИА) ===

@dp.message(F.text == "📎 Прикрепить фото/видео")
async def media_hint(message: types.Message):
    cid = message.chat.id
    logger.debug(f"📎 ПОДСКАЗКА МЕДИА: user_id={cid}")
    await delete_message_safe(cid, message.message_id, "media_hint")
    try:
        msg = await message.answer(
            "ℹ️ Нажмите на значок скрепки 📎 в поле ввода и выберите фото/видео",
            reply_markup=media_keyboard()
        )
        await add_temp_message(cid, msg.message_id)
        logger.debug(f"✅ Подсказка отправлена msg_id={msg.message_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка media_hint: {e}")

@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📸 ФОТО ЗАГРУЖЕНО: user_id={cid}, file_id={message.photo[-1].file_id[:20]}...")
    try:
        data = await state.get_data()
        logger.debug(f"💾 Текущий шаг: {data.get('step')}")
        
        if data.get('step') != 'media':
            logger.warning(f"⚠️ Фото загружено не в том шаге ({data.get('step')}), удаляем")
            await delete_message_safe(cid, message.message_id, "wrong_step")
            return
        
        media_id = message.photo[-1].file_id
        await state.update_data(media_type='photo', media_id=media_id)
        logger.debug(f"✅ Media_id сохранён в state")
        
        await update_preview(state, cid)
        await delete_message_safe(cid, message.message_id, "photo_uploaded")
        
        await message.answer(
            "<b>✅ Фото добавлено в превью!</b>\n\n"
            "Теперь нажмите «➡️ Далее: Текст» или загрузите ещё фото для замены",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard(has_media=True)
        )
        logger.info(f"✅ Фото обработано успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка handle_photo: {e}", exc_info=True)

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🎬 ВИДЕО ЗАГРУЖЕНО: user_id={cid}, file_id={message.video.file_id[:20]}...")
    try:
        data = await state.get_data()
        
        if data.get('step') != 'media':
            logger.warning(f"⚠️ Видео загружено не в том шаге, удаляем")
            await delete_message_safe(cid, message.message_id, "wrong_step")
            return
        
        media_id = message.video.file_id
        await state.update_data(media_type='video', media_id=media_id)
        
        await update_preview(state, cid)
        await delete_message_safe(cid, message.message_id, "video_uploaded")
        
        await message.answer(
            "<b>✅ Видео добавлено в превью!</b>\n\n"
            "Теперь нажмите «➡️ Далее: Текст»",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard(has_media=True)
        )
        logger.info(f"✅ Видео обработано успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка handle_video: {e}", exc_info=True)

@dp.message(F.text == "⏭️ Пропустить медиа")
async def skip_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⏭️ ПРОПУСК МЕДИА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "skip_media")
        await state.update_data(media_type=None, media_id=None, step='text')
        await update_preview(state, cid)
        
        await message.answer(
            "<b>✏️ ШАГ 2/3: Текст</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=text_keyboard(False, False)
        )
        await send_step_hint(cid, 'text')
        logger.info(f"✅ Медиа пропущено, переход к тексту")
    except Exception as e:
        logger.error(f"❌ Ошибка skip_media: {e}", exc_info=True)

@dp.message(F.text == "🔄 Заменить медиа")
async def replace_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔄 ЗАМЕНА МЕДИА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "replace_media")
        await state.update_data(media_type=None, media_id=None)
        await update_preview(state, cid)
        
        msg = await message.answer(
            "📎 Теперь загрузите НОВОЕ фото/видео (оно заменит старое):",
            reply_markup=cancel_keyboard()
        )
        await add_temp_message(cid, msg.message_id)
        logger.info(f"✅ Медиа готово к замене")
    except Exception as e:
        logger.error(f"❌ Ошибка replace_media: {e}", exc_info=True)

@dp.message(F.text == "🗑️ Удалить медиа")
async def delete_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🗑️ УДАЛЕНИЕ МЕДИА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "delete_media")
        await state.update_data(media_type=None, media_id=None)
        await update_preview(state, cid)
        
        await message.answer(
            "🗑️ Медиа удалено из превью",
            reply_markup=media_keyboard()
        )
        logger.info(f"✅ Медиа удалено")
    except Exception as e:
        logger.error(f"❌ Ошибка delete_media: {e}", exc_info=True)

@dp.message(F.text == "➡️ Далее: Текст")
async def to_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➡️ ПЕРЕХОД К ТЕКСТУ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "to_text")
        data = await state.get_data()
        await state.update_data(step='text')
        await update_preview(state, cid)
        has_text = bool(data.get('text'))
        has_formatted = bool(data.get('original_text') and data.get('original_text') != data.get('text'))
        
        logger.debug(f"💾 has_text={has_text}, has_formatted={has_formatted}")
        
        await message.answer(
            "<b>✏️ ШАГ 2/3: Текст</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=text_keyboard(has_text, has_formatted)
        )
        logger.info(f"✅ Переход к тексту выполнен")
    except Exception as e:
        logger.error(f"❌ Ошибка to_text: {e}", exc_info=True)

@dp.message(F.text == "⬅️ Назад: Медиа")
async def back_media(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⬅️ НАЗАД К МЕДИА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "back_media")
        await state.update_data(step='media')
        await update_preview(state, cid)
        data = await state.get_data()
        has_media = bool(data.get('media_id'))
        
        await message.answer(
            "<b>📷 ШАГ 1/3: Медиа</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=media_keyboard(has_media)
        )
        logger.info(f"✅ Возврат к медиа выполнен")
    except Exception as e:
        logger.error(f"❌ Ошибка back_media: {e}", exc_info=True)

# === ОБРАБОТЧИКИ: ШАГ 2 (ТЕКСТ) ===

@dp.message(F.text == "✏️ Редактировать текст")
async def edit_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"✏️ РЕДАКТИРОВАНИЕ ТЕКСТА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "edit_text")
        data = await state.get_data()
        raw = data.get('text', '')
        logger.debug(f"💾 Текущий текст: {raw[:50] if raw else 'пусто'}...")
        
        if not raw:
            await state.set_state(PostWorkflow.writing_text)
            msg = await message.answer("✏️ Введите текст поста:", reply_markup=cancel_keyboard())
            await add_temp_message(cid, msg.message_id)
            return
        
        clean = remove_emojis(remove_formatting(raw))
        await state.set_state(PostWorkflow.writing_text)
        msg = await message.answer(f"✏️ Исправьте текст и отправьте:\n\n{clean[:400]}", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
        logger.info(f"✅ Текст отправлен на редактирование")
    except Exception as e:
        logger.error(f"❌ Ошибка edit_text: {e}", exc_info=True)

@dp.message(F.text == "🤖 ИИ: Обновить")
async def ai_update(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🤖 ИИ ОБНОВЛЕНИЕ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "ai_update")
        data = await state.get_data()
        kws = data.get('ai_keywords', '')
        logger.debug(f"💾 Ключевые слова: {kws}")
        
        if not kws:
            msg = await message.answer(
                "⚠️ Сначала используйте «🤖 ИИ: Новый запрос»",
                reply_markup=text_keyboard(False, False)
            )
            await add_temp_message(cid, msg.message_id)
            return
        
        style = data.get('ai_style')
        txt = generate_ai_text(kws, style=style)
        await state.update_data(text=txt, original_text=txt)
        await update_preview(state, cid)
        logger.info(f"✅ ИИ текст обновлён")
    except Exception as e:
        logger.error(f"❌ Ошибка ai_update: {e}", exc_info=True)

@dp.message(F.text == "🤖 ИИ: Новый запрос")
async def ai_new(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🤖 ИИ НОВЫЙ ЗАПРОС: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "ai_new")
        data = await state.get_data()
        kws = data.get('ai_keywords', '')
        hint = f"\n\nПрошлые ключи: {kws}\nИзмените или напишите новые:" if kws else "\nНапишите ключевые слова через запятую:"
        
        await state.set_state(PostWorkflow.ai_input)
        msg = await message.answer(f"🤖 Генератор текста{hint}", reply_markup=cancel_keyboard())
        await add_temp_message(cid, msg.message_id)
        logger.info(f"✅ Ожидание ключевых слов ИИ")
    except Exception as e:
        logger.error(f"❌ Ошибка ai_new: {e}", exc_info=True)

@dp.message(F.text == "🪄 Сделать красиво")
async def make_beautiful(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🪄 СДЕЛАТЬ КРАСИВО: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "make_beautiful")
        data = await state.get_data()
        txt = data.get('text', '')
        logger.debug(f"💾 Текст до форматирования: {txt[:50] if txt else 'пусто'}...")
        
        if not txt:
            msg = await message.answer("⚠️ Сначала введите текст!")
            await add_temp_message(cid, msg.message_id)
            return
        
        clean_txt = remove_emojis(remove_formatting(txt))
        res = smart_format_text(clean_txt, 0, 0)
        await state.update_data(text=res['text'], original_text=txt, smart_variant=0, emoji_variant=0)
        emoji_variants[cid] = 0
        await update_preview(state, cid)
        logger.info(f"✅ Текст отформатирован")
    except Exception as e:
        logger.error(f"❌ Ошибка make_beautiful: {e}", exc_info=True)

@dp.message(F.text == "🔄 Эмодзи (сменить)")
async def change_emojis(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔄 СМЕНА ЭМОДЗИ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "change_emojis")
        data = await state.get_data()
        orig = data.get('original_text', data.get('text', ''))
        
        if not orig:
            msg = await message.answer("⚠️ Нет текста")
            await add_temp_message(cid, msg.message_id)
            return
        
        variant = emoji_variants.get(cid, 0) + 1
        emoji_variants[cid] = variant
        logger.debug(f"💾 Вариант эмодзи: {variant}")
        
        clean_orig = remove_emojis(remove_formatting(orig))
        res = smart_format_text(clean_orig, data.get('smart_variant', 0), variant)
        await state.update_data(text=res['text'], emoji_variant=variant)
        await update_preview(state, cid)
        logger.info(f"✅ Эмодзи обновлены (вариант {variant})")
    except Exception as e:
        logger.error(f"❌ Ошибка change_emojis: {e}", exc_info=True)

@dp.message(F.text == "🧹 Без эмодзи")
async def remove_emojis_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🧹 УДАЛЕНИЕ ЭМОДЗИ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "remove_emojis")
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
        logger.info(f"✅ Эмодзи удалены")
    except Exception as e:
        logger.error(f"❌ Ошибка remove_emojis_btn: {e}", exc_info=True)

@dp.message(F.text == "📄 Без формата")
async def remove_format_btn(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📄 УДАЛЕНИЕ ФОРМАТА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "remove_format")
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
        logger.info(f"✅ Формат удалён")
    except Exception as e:
        logger.error(f"❌ Ошибка remove_format_btn: {e}", exc_info=True)

@dp.message(F.text == "➡️ Далее: Кнопки")
async def to_buttons(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➡️ ПЕРЕХОД К КНОПКАМ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "to_buttons")
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
        logger.info(f"✅ Переход к кнопкам выполнен")
    except Exception as e:
        logger.error(f"❌ Ошибка to_buttons: {e}", exc_info=True)

@dp.message(F.text == "⬅️ Назад: Текст")
async def back_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"⬅️ НАЗАД К ТЕКСТУ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "back_text")
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
        logger.info(f"✅ Возврат к тексту выполнен")
    except Exception as e:
        logger.error(f"❌ Ошибка back_text: {e}", exc_info=True)

@dp.message(F.text == "🔗 Добавить ссылку в текст")
async def add_text_link(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔗 ДОБАВИТЬ ССЫЛКУ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "add_text_link")
        links = get_saved_links(cid)
        
        if not links:
            msg = await message.answer(
                "📚 У вас пока нет сохранённых ссылок.\n\n"
                "Сначала создайте через «➕ Добавить» в библиотеке",
                reply_markup=library_keyboard([], set(), 'link')
            )
            await add_temp_message(cid, msg.message_id)
            return
        
        await state.set_state(PostWorkflow.selecting_link)
        msg = await message.answer(
            "🔗 Выберите ссылку для вставки в текст:",
            reply_markup=library_keyboard(links, set(), 'link')
        )
        await add_temp_message(cid, msg.message_id)
        logger.info(f"✅ Библиотека ссылок открыта")
    except Exception as e:
        logger.error(f"❌ Ошибка add_text_link: {e}", exc_info=True)

# === ОБРАБОТЧИКИ: ШАГ 3 (КНОПКИ) ===

@dp.message(F.text == "➕ Добавить кнопку")
async def add_button(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"➕ ДОБАВИТЬ КНОПКУ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "add_button")
        await state.set_state(AddButtonSteps.waiting_for_text)
        msg = await message.answer(
            "➕ <b>ДОБАВЛЕНИЕ КНОПКИ</b>\n\n"
            "Введите текст кнопки (например: Подобрать тур):\n\n"
            "<i>Или в формате: Текст - Ссылка</i>\n"
            "<i>Пример: Подобрать тур - https://vCard.guru/...</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard()
        )
        await add_temp_message(cid, msg.message_id)
        logger.info(f"✅ Ожидание текста кнопки")
    except Exception as e:
        logger.error(f"❌ Ошибка add_button: {e}", exc_info=True)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"📝 ПОЛУЧЕН ТЕКСТ КНОПКИ: user_id={cid}, текст={message.text[:50]}...")
    try:
        await delete_message_safe(cid, message.message_id, "btn_text_received")
        text = message.text.strip()
        
        # Проверяем формат "Текст - Ссылка"
        if ' - ' in text and ('http://' in text or 'https://' in text):
            parts = text.split(' - ', 1)
            if len(parts) == 2:
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                if btn_url.startswith(('http://', 'https://', 't.me/', 'tg://')):
                    logger.debug(f"🔗 Распознан формат: текст={btn_text}, url={btn_url[:30]}...")
                    success, status = save_button(cid, btn_text, btn_url)
                    if success:
                        data = await state.get_data()
                        buttons = data.get('buttons', [])
                        buttons.append([{'text': btn_text, 'url': btn_url}])
                        await state.update_data(buttons=buttons)
                        await update_preview(state, cid)
                        
                        msg = await message.answer(
                            f"✅ Кнопка «{btn_text}» добавлена!",
                            reply_markup=buttons_keyboard(True)
                        )
                        await add_temp_message(cid, msg.message_id)
                        await state.set_state(None)
                        logger.info(f"✅ Кнопка добавлена через быстрый формат")
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
        logger.info(f"✅ Ожидание ссылки для кнопки")
    except Exception as e:
        logger.error(f"❌ Ошибка proc_btn_text: {e}", exc_info=True)

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"🔗 ПОЛУЧЕНА ССЫЛКА: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "btn_url_received")
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
            logger.warning(f"⚠️ Неверная ссылка: {url[:30]}...")
            return
        
        data = await state.get_data()
        btn_text = data.get('new_btn_text', '')
        logger.debug(f"💾 Текст кнопки: {btn_text}, URL: {url[:30]}...")
        
        success, status = save_button(cid, btn_text, url)
        
        if success:
            buttons = data.get('buttons', [])
            buttons.append([{'text': btn_text, 'url': url}])
            await state.update_data(buttons=buttons, new_btn_text=None)
            await state.set_state(None)
            await update_preview(state, cid)
            
            msg = await message.answer(
                f"✅ Кнопка «{btn_text}» добавлена!",
                reply_markup=buttons_keyboard(True)
            )
            await add_temp_message(cid, msg.message_id)
            logger.info(f"✅ Кнопка сохранена успешно")
        elif status == 'duplicate':
            msg = await message.answer(
                "⚠️ Такая кнопка уже есть в библиотеке",
                reply_markup=buttons_keyboard(True)
            )
            await add_temp_message(cid, msg.message_id)
            await state.set_state(None)
            logger.warning(f"⚠️ Дубликат кнопки: {btn_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка proc_btn_url: {e}", exc_info=True)

@dp.message(F.text == "✅ ФИНИШ: Опубликовать")
async def finish_post(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.info(f"✅ ФИНИШ: user_id={cid}")
    try:
        await delete_message_safe(cid, message.message_id, "finish")
        data = await state.get_data()
        
        txt = data.get('text', '')
        media_id = data.get('media_id')
        media_type = data.get('media_type')
        buttons_data = data.get('buttons', [])
        
        logger.debug(f"💾 ФИНИШ ДАННЫЕ: text_len={len(txt) if txt else 0}, media_type={media_type}, buttons={len(buttons_data)}")
        
        if not txt and not media_id:
            msg = await message.answer(
                "⚠️ Нельзя опубликовать пустой пост!\n\n"
                "Добавьте текст или медиа.",
                reply_markup=buttons_keyboard(bool(buttons_data))
            )
            await add_temp_message(cid, msg.message_id)
            return
        
        final_kb = InlineKeyboardBuilder()
        for row in buttons_data:
            for btn in row:
                final_kb.button(text=btn['text'], url=btn['url'])
        if buttons_data:
            final_kb.adjust(1)
        
        # Публикуем пост
        if media_type == 'photo' and media_id:
            logger.info(f"📸 Публикация фото поста")
            await bot.send_photo(
                chat_id=cid, photo=media_id,
                caption=txt, parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        elif media_type == 'video' and media_id:
            logger.info(f"🎬 Публикация видео поста")
            await bot.send_video(
                chat_id=cid, video=media_id,
                caption=txt, parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        else:
            logger.info(f"📝 Публикация текстового поста")
            await bot.send_message(
                chat_id=cid, text=txt,
                parse_mode=ParseMode.HTML,
                reply_markup=final_kb.as_markup()
            )
        
        # Сохраняем в историю
        post_id = save_published_post(cid, media_type, media_id, txt, buttons_data)
        logger.info(f"✅ Пост сохранён в историю под id={post_id}")
        
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
        logger.info(f"✅ ФИНИШ завершён успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка finish_post: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка публикации: {e}")

# === ОБРАБОТЧИКИ: БИБЛИОТЕКИ ===

@dp.callback_query(lambda c: c.data.startswith('lib:') or c.data.startswith('link_lib:'))
async def library_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    lib_type = 'button' if parts[0] == 'lib' else 'link'
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    logger.info(f"📚 БИБЛИОТЕКА CALLBACK: type={lib_type}, action={act}, user_id={uid}")
    
    try:
        if act == 'toggle':
            item_id = int(parts[2])
            items = get_saved_buttons(uid) if lib_type == 'button' else get_saved_links(uid)
            item = next((i for i in items if i['id'] == item_id), None)
            
            if not item:
                logger.warning(f"⚠️ Элемент не найден: id={item_id}")
                return
            
            data = await state.get_data()
            sel = set(data.get('temp_selected', []))
            
            if item_id in sel:
                sel.remove(item_id)
                logger.debug(f"🔘 Снято выделение с {item_id}")
            else:
                sel.add(item_id)
                logger.debug(f"✅ Выделено {item_id}")
            
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
            
            logger.debug(f"💾 Выбрано элементов: {len(chosen)}")
            
            if not chosen:
                await callback.answer("⚠️ Ничего не выбрано", show_alert=True)
                return
            
            if lib_type == 'button':
                buttons = data.get('buttons', [])
                buttons.extend([[{'text': b['text'], 'url': b['url']}] for b in chosen])
                await state.update_data(buttons=buttons, temp_selected=[])
                await update_preview(state, cid)
                await callback.message.delete()
                
                return_point = library_return_points.get(cid, 'buttons')
                logger.debug(f"💾 Точка возврата: {return_point}")
                
                if return_point == 'media':
                    await callback.message.answer(
                        "✅ Кнопки добавлены!",
                        reply_markup=media_keyboard(bool(data.get('media_id')))
                    )
                elif return_point == 'text':
                    has_text = bool(data.get('text'))
                    has_fmt = bool(data.get('original_text'))
                    await callback.message.answer(
                        "✅ Кнопки добавлены!",
                        reply_markup=text_keyboard(has_text, has_fmt)
                    )
                else:
                    await callback.message.answer(
                        "✅ Кнопки добавлены!",
                        reply_markup=buttons_keyboard(True)
                    )
            else:
                current_text = data.get('text', '')
                for link in chosen:
                    current_text += f'\n<a href="{link["url"]}">{link["text"]}</a>'
                
                await state.update_data(text=current_text, temp_selected=[])
                await update_preview(state, cid)
                await callback.message.delete()
                
                await callback.message.answer(
                    "✅ Ссылки вставлены в текст!",
                    reply_markup=text_keyboard(True, bool(data.get('original_text')))
                )
            
            await callback.answer()
            
        elif act == 'create':
            await state.set_state(AddButtonSteps.waiting_for_text if lib_type == 'button' else AddLinkSteps.waiting_for_text)
            prompt = "➕ Введите текст кнопки:" if lib_type == 'button' else "➕ Введите текст ссылки:"
            await callback.message.answer(prompt, reply_markup=cancel_keyboard())
            await callback.answer()
            
        elif act == 'back':
            await callback.message.delete()
            return_point = library_return_points.get(cid, 'main')
            logger.debug(f"💾 Возврат в: {return_point}")
            
            if return_point == 'media':
                data = await state.get_data()
                await callback.message.answer(
                    "<b>📷 ШАГ 1/3: Медиа</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=media_keyboard(bool(data.get('media_id')))
                )
            elif return_point == 'text':
                data = await state.get_data()
                has_text = bool(data.get('text'))
                has_fmt = bool(data.get('original_text'))
                await callback.message.answer(
                    "<b>✏️ ШАГ 2/3: Текст</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=text_keyboard(has_text, has_fmt)
                )
            elif return_point == 'buttons':
                data = await state.get_data()
                await callback.message.answer(
                    "<b>🔘 ШАГ 3/3: Кнопки</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=buttons_keyboard(bool(data.get('buttons')))
                )
            else:
                await callback.message.answer(
                    "🤖 <b>Пост-Триумф Live</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_keyboard()
                )
            
            await callback.answer()
            
    except Exception as e:
        logger.error(f"❌ Ошибка library_callback: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('post:'))
async def post_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    act = parts[1]
    uid = callback.from_user.id
    cid = callback.message.chat.id
    
    logger.info(f"📋 ПОСТ CALLBACK: action={act}, user_id={uid}")
    
    try:
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
            
            delete_published_post(post_id, uid)
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
            
    except Exception as e:
        logger.error(f"❌ Ошибка post_callback: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('help:'))
async def help_callback(callback: types.CallbackQuery):
    logger.debug(f"❓ ПОМОЩЬ CALLBACK: {callback.data}")
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('finish:'))
async def finish_callback(callback: types.CallbackQuery, state: FSMContext):
    act = callback.data.split(':')[1]
    cid = callback.message.chat.id
    logger.debug(f"✅ ФИНИШ CALLBACK: action={act}")
    
    try:
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
    except Exception as e:
        logger.error(f"❌ Ошибка finish_callback: {e}", exc_info=True)

# === ОБРАБОТКА ТЕКСТА (ШАГ 2) ===

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    cid = message.chat.id
    txt = message.text
    logger.info(f"✏️ ПОЛУЧЕН ТЕКСТ: user_id={cid}, len={len(txt)}")
    try:
        await delete_message_safe(cid, message.message_id, "text_received")
        
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
        logger.info(f"✅ Текст сохранён и превью обновлено")
    except Exception as e:
        logger.error(f"❌ Ошибка handle_text_edit: {e}", exc_info=True)

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    cid = message.chat.id
    kws = message.text.strip()
    logger.info(f"🤖 ПОЛУЧЕНЫ КЛЮЧИ ИИ: user_id={cid}, keywords={kws}")
    try:
        await delete_message_safe(cid, message.message_id, "ai_keywords_received")
        
        await state.update_data(ai_keywords=kws)
        
        available_styles = get_available_styles()
        selected_style = random.choice(available_styles)
        style_variants[cid] = selected_style
        logger.debug(f"💾 Выбран стиль ИИ: {selected_style}")
        
        txt = generate_ai_text(kws, style=selected_style)
        await state.update_data(text=txt, original_text=txt, smart_variant=-1, ai_style=selected_style)
        save_draft(cid, {'text': txt}, 'text')
        await state.set_state(None)
        await update_preview(state, cid)
        
        await message.answer(
            f"✅ Текст сгенерирован (стиль: {selected_style})!",
            reply_markup=text_keyboard(True, True)
        )
        logger.info(f"✅ ИИ текст сгенерирован")
    except Exception as e:
        logger.error(f"❌ Ошибка handle_ai_input: {e}", exc_info=True)

@dp.message(PostWorkflow.selecting_link, F.text)
async def handle_link_selection(message: types.Message, state: FSMContext):
    cid = message.chat.id
    logger.warning(f"⚠️ ПОЛУЧЕН ТЕКСТ ВМЕСТО КНОПКИ: user_id={cid}")
    await message.answer("⚠️ Используйте кнопки для выбора ссылок", reply_markup=cancel_keyboard())

# === ОБРАБОТКА СООБЩЕНИЙ НЕ ПО ШАГУ ===

@dp.message()
async def handle_wrong_step(message: types.Message, state: FSMContext):
    """Удалять сообщения если они не по текущему шагу"""
    cid = message.chat.id
    data = await state.get_data()
    current_step = data.get('step')
    
    # Игнорируем команды главного меню
    menu_commands = ["➕ Новый пост", "📚 Библиотека кнопок", "🔗 Библиотека ссылок", "📋 Мои посты", "❓ Помощь"]
    if message.text in menu_commands:
        logger.debug(f"ℹ️ Игнорируем команду меню: {message.text}")
        return
    
    # Игнорируем кнопки навигации
    nav_buttons = ["⬅️ Назад: Медиа", "⬅️ Назад: Текст", "➡️ Далее: Текст", "➡️ Далее: Кнопки", "✅ ФИНИШ: Опубликовать", "❌ Отмена"]
    if message.text in nav_buttons:
        logger.debug(f"ℹ️ Игнорируем кнопку навигации: {message.text}")
        return
    
    # Если не в процессе создания поста — игнорируем
    if not current_step:
        logger.debug(f"ℹ️ Нет активного шага, игнорируем сообщение")
        return
    
    # Удаляем сообщение не по шагу
    logger.warning(f"⚠️ Сообщение не по шагу (step={current_step}), удаляем: {message.text[:50]}...")
    await delete_message_safe(cid, message.message_id, "wrong_step")
    
    # Отправляем подсказку
    step_hints = {
        'media': "📷 Сейчас шаг МЕДИА. Загрузите фото или нажмите «⏭️ Пропустить»",
        'text': "✏️ Сейчас шаг ТЕКСТ. Напишите текст или используйте ИИ",
        'buttons': "🔘 Сейчас шаг КНОПКИ. Добавьте кнопки или нажмите «✅ ФИНИШ»"
    }
    
    hint = step_hints.get(current_step, "Следуйте инструкциям на экране")
    msg = await message.answer(f"⚠️ {hint}", reply_markup=cancel_keyboard())
    await add_temp_message(cid, msg.message_id)
    logger.debug(f"✅ Отправлена подсказка для шага {current_step}")

# === ЗАПУСК ===

async def main():
    logger.info("="*60)
    logger.info("🚀 ЗАПУСК БОТА ПОСТ-ТРИУМФ")
    logger.info(f"🤖 Bot ID: {bot.id}")
    logger.info("="*60)
    
    await bot.delete_webhook()
    logger.info("✅ Webhook удалён")
    
    await dp.start_polling(bot)
    logger.info("✅ Polling запущен")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
