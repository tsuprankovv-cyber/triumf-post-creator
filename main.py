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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

# Хранилище ID сообщения с предпросмотром: {user_id: message_id}
preview_messages = {} 

async def update_preview(message: types.Message, state: FSMContext, force_new: bool = False):
    """Обновляет или создает сообщение предпросмотра"""
    user_id = message.from_user.id
    data = await state.get_data()
    
    step = data.get('step', 'media')
    text_content = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    # Формируем текст превью
    if not text_content:
        caption = "_(Нажмите ✏️ Править текст, чтобы добавить описание)_\n\nЗдесь будет ваш продающий пост."
    else:
        caption = text_content
        
    # Клавиатура управления (кнопки под постом)
    has_formatted = data.get('original_text') and data.get('original_text') != text_content
    control_kb = get_preview_keyboard(step, bool(text_content), has_formatted)
    
    try:
        msg_id = preview_messages.get(user_id)
        
        if msg_id and not force_new:
            # РЕДАКТИРУЕМ СУЩЕСТВУЮЩЕЕ СООБЩЕНИЕ
            if media_type == 'photo' and media_id:
                # Нельзя менять клавиатуру через edit_caption, поэтому делаем два вызова или игнорируем смену кнопок если тип не меняется
                try:
                    await bot.edit_message_caption(chat_id=user_id, message_id=msg_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                except: pass
                # Обновляем кнопки отдельно
                await bot.edit_message_reply_markup(chat_id=user_id, message_id=msg_id, reply_markup=control_kb)
                
            elif media_type == 'video' and media_id:
                try:
                    await bot.edit_message_caption(chat_id=user_id, message_id=msg_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                except: pass
                await bot.edit_message_reply_markup(chat_id=user_id, message_id=msg_id, reply_markup=control_kb)
            else:
                # Текст
                await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
        else:
            # СОЗДАЕМ НОВОЕ СООБЩЕНИЕ
            new_msg = None
            if media_type == 'photo' and media_id:
                new_msg = await bot.send_photo(chat_id=user_id, photo=media_id, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            elif media_type == 'video' and media_id:
                new_msg = await bot.send_video(chat_id=user_id, video=media_id, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            else:
                new_msg = await bot.send_message(chat_id=user_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=control_kb)
            
            if new_msg:
                preview_messages[user_id] = new_msg.message_id
                
    except TelegramBadRequest as e:
        logger.warning(f"Ошибка обновления превью (возможно, текст не изменился): {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка превью: {e}")

# ==================== СТАРТ И МЕНЮ ====================
@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    await message.answer("🤖 **Пост-Триумф Live**\n\nСоздавайте посты в реальном времени!", reply_markup=main_keyboard())

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
    await state.set_state(PostWorkflow.selecting_media)
    await state.update_data(step='media', text='', media_id=None, media_type=None, buttons=[], original_text=None, ai_keywords=None)
    
    # Удаляем старое превью если было
    if uid in preview_messages:
        try: await bot.delete_message(uid, preview_messages[uid])
        except: pass
    
    await update_preview(message, state, force_new=True)
    await message.answer("ℹ️ **Редактор открыт!**\nВсе изменения будут появляться в сообщении выше.", reply_markup=cancel_keyboard())

# ==================== КОНТРОЛЛЕР ПРЕВЬЮ (ГЛАВНЫЙ МОЗГ) ====================
@dp.callback_query(lambda c: c.data.startswith('prev:'))
async def preview_controller(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    uid = callback.from_user.id
    data = await state.get_data()
    
    # --- ОТМЕНА ---
    if action == 'cancel':
        await cmd_cancel(callback.message, state)
        await callback.answer()
        return

    # --- ШАГ 1: МЕДИА ---
    if action == 'skip_media':
        await state.update_data(media_type=None, media_id=None, step='text')
        await update_preview(callback.message, state)
        await callback.answer("Фото пропущено")
        
    elif action == 'to_text':
        if data.get('media_id') or data.get('media_type') is None:
             await state.update_data(step='text')
             await update_preview(callback.message, state)
             await callback.answer("Переход к тексту")
        else:
             await callback.answer("⚠️ Загрузите фото или нажмите 'Пропустить'", show_alert=True)

    # --- ШАГ 2: ТЕКСТ И ИИ ---
    elif action == 'back_media':
        await state.update_data(step='media')
        await update_preview(callback.message, state)
        await callback.answer()

    elif action == 'edit_text':
        # Извлекаем текст, чистим его и просим пользователя отредактировать
        raw_text = data.get('text', '')
        if not raw_text:
            await callback.answer("Введите текст первым сообщением!", show_alert=True)
            return
        
        # Очищаем от формата и эмодзи для удобного редактирования
        clean_text = remove_emojis(remove_formatting(raw_text))
        
        await state.set_state(PostWorkflow.writing_text)
        await callback.message.answer(f"✏️ **Редактирование текста**\n\nНиже ваш текст без форматирования. Исправьте его и отправьте обратно:\n\n_{clean_text[:500]}_", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif action == 'ai_generate':
        # Запрос ключевых слов для ИИ
        await state.set_state(PostWorkflow.ai_input)
        kws = data.get('ai_keywords', '')
        hint = f"\n\nПрошлые ключи: `{kws}`\nИзмените их или напишите новые:" if kws else ""
        await callback.message.answer(f"🤖 **Генератор текста**\n\nНапишите ключевые слова (через запятую):{hint}", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif action == 'smart_format':
        if not data.get('text'):
            await callback.answer("⚠️ Сначала введите текст!", show_alert=True)
            return
        await state.update_data(smart_variant=0)
        res = smart_format_text(data['text'], 0)
        await state.update_data(text=res['text'], original_text=data.get('text', ''), smart_variant=0)
        save_draft(uid, {'text': res['text']}, 'text')
        await update_preview(callback.message, state)
        await callback.answer("✨ Отформатировано!")

    elif action == 'smart_next':
        v = data.get('smart_variant', 0) + 1
        orig = data.get('original_text', data.get('text'))
        res = smart_format_text(orig, v)
        await state.update_data(text=res['text'], smart_variant=v)
        await update_preview(callback.message, state)
        await callback.answer("🔄 Вариант изменен")
        
    elif action == 'smart_reset':
        orig = data.get('original_text', '')
        await state.update_data(text=orig, smart_variant=-1)
        await update_preview(callback.message, state)
        await callback.answer("↩️ Сброшено")

    elif action == 'remove_emojis':
        if not data.get('text'): return
        cleaned = remove_emojis(data['text'])
        await state.update_data(text=cleaned)
        await update_preview(callback.message, state)
        await callback.answer("🧹 Эмодзи удалены")

    elif action == 'remove_format':
        if not data.get('text'): return
        cleaned = remove_formatting(data['text'])
        await state.update_data(text=cleaned)
        await update_preview(callback.message, state)
        await callback.answer("📄 Форматирование снято")

    elif action == 'to_buttons':
        if not data.get('text'):
            await callback.answer("⚠️ Введите текст!", show_alert=True)
            return
        await state.update_data(step='buttons')
        await update_preview(callback.message, state)
        await callback.answer("Переход к кнопкам")
        
    # --- ШАГ 3: КНОПКИ ---
    elif action == 'back_text':
        await state.update_data(step='text')
        await update_preview(callback.message, state)
        await callback.answer()

    elif action == 'add_btn':
        await state.set_state(AddButtonSteps.waiting_for_text)
        await callback.message.answer("➕ **Новая кнопка**\n\nВведите текст кнопки (например: *Забронировать*):")
        await callback.answer()
        
    elif action == 'lib_btn':
        btns = get_saved_buttons(uid)
        if not btns:
            await callback.answer("📚 Библиотека пуста!", show_alert=True)
            return
        # Показываем библиотеку отдельным сообщением для выбора
        sel = set(data.get('temp_selected', []))
        await callback.message.answer("**📚 Выберите кнопки:**", reply_markup=library_keyboard(btns, sel))
        await callback.answer()

    elif action == 'finish':
        # ФИНАЛ: Создаем чистый пост в ленте
        await finish_post_process(callback.message, state)
        await callback.answer("✅ Пост опубликован!")

# ==================== ОБРАБОТКА ВВОДА ПОЛЬЗОВАТЕЛЯ ====================

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_edit(message: types.Message, state: FSMContext):
    txt = message.text
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt, 'original_text': txt}, 'text')
    await state.set_state(None) # Сброс состояния ввода
    await update_preview(message, state)
    await message.delete() # Удаляем сообщение с текстом, чтобы не мусорить
    await message.answer("✅ Текст обновлен в превью выше!", delete_after=3)

@dp.message(PostWorkflow.ai_input, F.text)
async def handle_ai_input(message: types.Message, state: FSMContext):
    keywords = message.text.strip()
    await state.update_data(ai_keywords=keywords)
    
    # ЭМУЛЯЦИЯ ИИ (Шаблоны)
    generated_text = generate_ai_text(keywords)
    
    await state.update_data(text=generated_text, original_text=generated_text, smart_variant=-1)
    save_draft(message.from_user.id, {'text': generated_text}, 'text')
    await state.set_state(None)
    await update_preview(message, state)
    await message.delete()
    await message.answer("🤖 Текст сгенерирован! Смотрите превью выше.", delete_after=3)

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    await message.answer(f"2️⃣ Введите ссылку для «{message.text}»:")
    await message.delete()

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Неверная ссылка."); return
    
    data = await state.get_data()
    if save_button(message.from_user.id, data['new_btn_text'], url):
        # Добавляем кнопку в текущий черновик
        buttons = data.get('buttons', [])
        buttons.append([{'text': data['new_btn_text'], 'url': url}])
        await state.update_data(buttons=buttons, new_btn_text=None, new_btn_url=None)
        await state.set_state(None)
        await update_preview(message, state)
        await message.answer("✅ Кнопка добавлена!", delete_after=3)
    else:
        await message.answer("⚠️ Такая кнопка уже есть.")
    await message.delete()

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
        if not chosen: await callback.answer("⚠️ Ничего не выбрано", show_alert=True); return
        
        buttons = data.get('buttons', [])
        buttons.extend([[b] for b in chosen])
        await state.update_data(buttons=buttons, temp_selected=[])
        await callback.message.delete()
        await update_preview(callback.message, state) # Обновляем превью с новыми кнопками
        await callback.message.answer("✅ Кнопки добавлены в превью!", delete_after=3)
        await callback.answer()
        
    elif act == 'back':
        await callback.message.delete()
        await callback.answer()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def generate_ai_text(keywords: str) -> str:
    """Эмулятор ИИ на основе шаблонов"""
    kws = [k.strip().lower() for k in keywords.split(',')]
    text_parts = []
    
    # Определение темы
    theme = "travel"
    if any(k in kws for k in ['тайланд', 'пхукет', 'вьетнам', 'китай']): theme = "asia"
    elif any(k in kws for k in ['байкал', 'иркутск', 'алтай']): theme = "russia"
    elif any(k in kws for k in ['дубай', 'египет', 'турция']): theme = "hot"
    
    # Заголовок
    if 'горящий' in kws or 'акция' in kws:
        title = f"🔥 ГОРЯЩЕЕ ПРЕДЛОЖЕНИЕ: {', '.join(kws[:3]).title()}!"
    else:
        title = f"✨ Эксклюзивный тур: {', '.join(kws[:3]).title()}"
    text_parts.append(title)
    text_parts.append("")
    
    # Тело
    text_parts.append("Приглашаем вас в незабываемое путешествие!")
    if 'отель' in kws or '5*' in kws:
        text_parts.append("🏨 Вас ждет комфортабельный отель высокого уровня.")
    if 'море' in kws or 'пляж' in kws:
        text_parts.append("🌊 Кристально чистое море и золотые пляжи.")
    elif 'лед' in kws or 'байкал' in kws:
        text_parts.append("🧊 Величие природы и чистейший воздух.")
        
    text_parts.append("✈️ Удобный перелет и трансфер включены.")
    
    # Цена и призыв
    if 'цена' in kws or 'скидка' in kws:
        text_parts.append("")
        text_parts.append("💰 **Специальная цена** только на этой неделе!")
    
    text_parts.append("")
    text_parts.append("📞 Звоните нам для бронирования!")
    
    return "\n".join(text_parts)

async def finish_post_process(message: types.Message, state: FSMContext):
    """Создает чистый пост в ленте"""
    data = await state.get_data()
    txt = data.get('text', '')
    media_id = data.get('media_id')
    media_type = data.get('media_type')
    buttons_data = data.get('buttons', [])
    
    # Создаем клавиатуру для готового поста (только ссылки)
    final_kb = types.InlineKeyboardBuilder()
    for row in buttons_data:
        for btn in row:
            final_kb.button(text=btn['text'], url=btn['url'])
    if buttons_data: final_kb.adjust(1)
    
    # Кнопки управления готовым постом
    manage_kb = types.InlineKeyboardBuilder()
    manage_kb.button(text="📤 Инструкция по пересылке", callback_data="final:forward_info")
    manage_kb.button(text="✏️ Редактировать этот пост", callback_data=f"final:edit:{message.message_id}") # ID пока фейковый, нужна логика сохранения ID поста
    # УПРОЩЕНИЕ: Кнопка редактировать просто вернет нас в режим создания с текущими данными
    manage_kb.adjust(2)
    
    # Отправляем чистый пост
    try:
        if media_type == 'photo' and media_id:
            await bot.send_photo(chat_id=message.chat.id, photo=media_id, caption=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
        elif media_type == 'video' and media_id:
            await bot.send_video(chat_id=message.chat.id, video=media_id, caption=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
        else:
            await bot.send_message(chat_id=message.chat.id, text=txt, parse_mode=ParseMode.MARKDOWN, reply_markup=final_kb.as_markup())
            
        # Под постом добавляем блок управления (отдельным сообщением или прикрепленным? Лучше отдельным для чистоты)
        await message.answer("✅ **Пост готов!**\nВыберите действие:", reply_markup=manage_kb)
        
        # Очищаем состояние и превью
        uid = message.from_user.id
        await state.clear()
        if uid in preview_messages:
            try: await bot.delete_message(uid, preview_messages[uid])
            except: pass
            del preview_messages[uid]
            
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await message.answer("❌ Ошибка при публикации поста.")

@dp.callback_query(lambda c: c.data.startswith('final:'))
async def final_actions(callback: types.CallbackQuery):
    action = callback.data.split(':')[1]
    if action == 'forward_info':
        await callback.answer("Нажмите на пост выше → Переслать → Выберите чат", show_alert=True)
    elif action == 'edit':
        # Логика возврата к редактированию (нужно сохранять данные поста в БД по ID)
        await callback.answer("Функция восстановления данных в разработке. Пока создайте новый пост.", show_alert=True)

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
