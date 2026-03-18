# -*- coding: utf-8 -*-
import os, logging, json, re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

# ИМПОРТЫ НАШИХ МОДУЛЕЙ
from states import PostWorkflow, AddButtonSteps
from keyboards import main_keyboard, cancel_keyboard, post_creation_keyboard, media_navigation_keyboard, text_navigation_keyboard, library_keyboard, final_keyboard
from database import init_db, save_button, get_saved_buttons, delete_button, save_draft, get_draft, delete_draft
from smart_text import smart_format_text  # <-- ВАЖНО: Импорт нового модуля

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(), logging.FileHandler('bot_debug.log', encoding='utf-8', mode='a')])
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN: raise ValueError("❌ Нет токена!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
init_db()

logger.info("="*60 + "\n🚀 ПОСТ-ТРИУМФ ЗАПУСКАЕТСЯ\n" + "="*60)

# ==================== СТАРТ ====================
@dp.message(Command('start'))
@dp.message(F.text == "❓ Помощь")
async def cmd_start(message: types.Message):
    await message.answer("🤖 **Пост-Триумф**\n\n➕ Новый пост | 📚 Мои кнопки | ❓ Помощь", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear(); delete_draft(message.from_user.id)
    await message.answer("❌ Отменено.", reply_markup=main_keyboard())

# ==================== ШАГ 1: МЕДИА ====================
@dp.message(F.text == "➕ Новый пост")
@dp.message(Command('new'))
async def cmd_new(message: types.Message, state: FSMContext):
    await state.set_state(PostWorkflow.selecting_media)
    await message.answer("📷 **ШАГ 1: Медиа**\n\nОтправьте фото/видео или нажмите ⏭️ Пропустить", reply_markup=media_navigation_keyboard())

@dp.callback_query(lambda c: c.data.startswith('media:'))
async def media_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    uid = callback.from_user.id
    if action == 'skip':
        await state.update_data(media_type=None, media_id=None)
        save_draft(uid, {}, 'selecting_media')
        await goto_text_step(callback.message, state, uid)
        await callback.answer("⏭️ Пропущено")
    elif action == 'done':
        data = await state.get_data()
        if data.get('media_id'):
            await goto_text_step(callback.message, state, uid)
            await callback.answer("✅ Переход к тексту")
        else:
            await callback.answer("⚠️ Сначала отправьте медиа или нажмите 'Пропустить'", show_alert=True)

@dp.message(PostWorkflow.selecting_media, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    await state.update_data(media_type='photo', media_id=message.photo[-1].file_id)
    save_draft(message.from_user.id, {'media_type': 'photo', 'media_id': message.photo[-1].file_id}, 'selecting_media')
    await goto_text_step(message, state, message.from_user.id)

@dp.message(PostWorkflow.selecting_media, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    await state.update_data(media_type='video', media_id=message.video.file_id)
    save_draft(message.from_user.id, {'media_type': 'video', 'media_id': message.video.file_id}, 'selecting_media')
    await goto_text_step(message, state, message.from_user.id)

async def goto_text_step(target_message, state: FSMContext, uid: int):
    await state.set_state(PostWorkflow.writing_text)
    data = await state.get_data()
    curr = data.get('text', "")
    orig = data.get('original_text', "")
    
    # Сохраняем оригинал при первом входе
    if curr and not orig:
        await state.update_data(original_text=curr)
        save_draft(uid, {'text': curr, 'original_text': curr}, 'writing_text')
        
    has_fmt = bool(orig and curr != orig)
    txt = "✍️ **ШАГ 2: Текст поста**\n\n"
    if curr:
        prev = curr[:150] + "..." if len(curr) > 150 else curr
        txt += f"📝 *Текущий:* _{prev}_\n\n"
    txt += "💡 Поддерживается: `**жирный**`, `*курсив*`\n\n🤖 Нажмите «🪄 Сделать красиво» для авто-оформления."
    await target_message.answer(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard(show_reset=has_fmt))

# ==================== ШАГ 2: ТЕКСТ И ФОРМАТИРОВАНИЕ ====================
@dp.callback_query(lambda c: c.data.startswith('text:'))
async def text_callback(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    uid = callback.from_user.id
    data = await state.get_data()
    curr = data.get('text', "")
    orig = data.get('original_text', "")

    if not curr and action.startswith('smart'):
        await callback.answer("⚠️ Сначала введите текст!", show_alert=True); return

    if action == 'back_to_media':
        await state.set_state(PostWorkflow.selecting_media)
        has_m = bool(data.get('media_id'))
        await callback.message.edit_text(f"📷 **Медиа**\n\n{'✅ Загружено.' if has_m else 'Не выбрано.'}", reply_markup=media_navigation_keyboard())
        await callback.answer()
    elif action == 'next_to_buttons':
        await callback.message.answer("🔘 **ШАГ 3: Кнопки**\n\nВыберите способ:", reply_markup=post_creation_keyboard())
        await callback.answer()
    elif action == 'edit_mode':
        await callback.message.answer("✏️ **Отправьте новый текст:**", reply_markup=cancel_keyboard())
        await callback.answer()
    elif action == 'smart_format':
        await state.update_data(smart_variant=0)
        res = smart_format_text(curr, 0)
        await apply_smart(state, callback, uid, res['text'], res['style_name'])
    elif action == 'smart_format_next':
        v = data.get('smart_variant', 0) + 1
        await state.update_data(smart_variant=v)
        res = smart_format_text(curr, v)
        await apply_smart(state, callback, uid, res['text'], res['style_name'])
    elif action == 'smart_reset':
        if orig:
            await state.update_data(text=orig, smart_variant=-1)
            save_draft(uid, {'text': orig}, 'writing_text')
            await callback.message.answer("↩️ **Текст сброшен к исходнику.**", reply_markup=text_navigation_keyboard(show_reset=False))
            await callback.answer("Сброшено")
        else:
            await callback.answer("Нет исходника", show_alert=True)

async def apply_smart(state, callback, uid, text, style):
    await state.update_data(text=text)
    save_draft(uid, {'text': text}, 'writing_text')
    prev = text[:200] + "..." if len(text) > 200 else text
    await callback.message.answer(f"🪄 **Стиль: {style}**\n\n{prev}\n\nЖмите «🔄 Ещё» или «↩️ Исходник».", parse_mode=ParseMode.MARKDOWN, reply_markup=text_navigation_keyboard(show_reset=True))
    await callback.answer("Готово!")

@dp.message(PostWorkflow.writing_text, F.text)
async def handle_text_logic(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Быстрый ввод кнопок (если активен флаг)
    if data.get('waiting_for_quick_buttons'):
        if message.text == "❌ Отмена":
            await state.update_data(waiting_for_quick_buttons=False)
            await cmd_cancel(message, state); return
        
        lines = message.text.strip().split('\n')
        count = 0
        for line in lines:
            parts = line.split(' - ', 1) if ' - ' in line else line.split('-', 1)
            if len(parts) == 2:
                t, u = parts[0].strip(), parts[1].strip()
                if u.startswith(('http://', 'https://', 't.me/', 'tg://')):
                    if save_button(message.from_user.id, t, u): count += 1
        
        await state.update_data(waiting_for_quick_buttons=False)
        msg = f"✅ Создано кнопок: {count}!" if count > 0 else "⚠️ Не распознано. Формат: `Текст - Ссылка`"
        await message.answer(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=post_creation_keyboard())
        return

    # Обычный текст
    ignore = ["◀️ Назад к медиа", "Вперёд к кнопкам ▶️", "✏️ Изменить текст", "➕ Добавить новую (по шагам)", "⚡ Быстрый ввод (списком)", "📚 Выбрать из библиотеки", "✅ Готово с кнопками"]
    if message.text in ignore: return
    if message.text == "❌ Отмена": await cmd_cancel(message, state); return
    
    txt = message.text
    # Обновляем и текст, и оригинал при ручном вводе
    await state.update_data(text=txt, original_text=txt, smart_variant=-1)
    save_draft(message.from_user.id, {'text': txt, 'original_text': txt}, 'writing_text')
    await message.answer(f"✅ **Текст сохранён!** ({len(txt)} симв.)", reply_markup=text_navigation_keyboard(show_reset=False))

# ==================== ШАГ 3: КНОПКИ ====================
@dp.message(F.text == "📚 Мои кнопки")
async def cmd_my_buttons(message: types.Message):
    btns = get_saved_buttons(message.from_user.id)
    if not btns: await message.answer("📚 Пусто.", reply_markup=main_keyboard()); return
    await message.answer("**📚 Кнопки:**", parse_mode=ParseMode.MARKDOWN, reply_markup=library_keyboard(btns))

@dp.message(F.text == "➕ Добавить новую (по шагам)")
async def start_add_step(message: types.Message, state: FSMContext):
    await state.update_data(new_btn_text=None, new_btn_url=None)
    await state.set_state(AddButtonSteps.waiting_for_text)
    await message.answer("1️⃣ **Введите текст кнопки:**", reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_text, F.text)
async def proc_btn_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": await cmd_cancel(message, state); return
    await state.update_data(new_btn_text=message.text.strip())
    await state.set_state(AddButtonSteps.waiting_for_url)
    await message.answer(f"2️⃣ **Введите ссылку для «{message.text}»:**", reply_markup=cancel_keyboard())

@dp.message(AddButtonSteps.waiting_for_url, F.text)
async def proc_btn_url(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена": await cmd_cancel(message, state); return
    data = await state.get_data()
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        await message.answer("❌ Неверная ссылка.", reply_markup=cancel_keyboard()); return
    if save_button(message.from_user.id, data['new_btn_text'], url):
        await message.answer(f"✅ Создана: `{data['new_btn_text']}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("⚠️ Уже есть.")
    await state.set_state(None)
    await message.answer("🔘 **Меню кнопок**", reply_markup=post_creation_keyboard())

@dp.message(F.text == "⚡ Быстрый ввод (списком)")
async def start_quick(message: types.Message, state: FSMContext):
    await state.update_data(waiting_for_quick_buttons=True)
    await message.answer("⚡ **Быстрый ввод**\nФормат: `Текст - Ссылка`\n(каждая с новой строки)\n\n❌ Отмена", reply_markup=cancel_keyboard())

@dp.message(F.text == "📚 Выбрать из библиотеки")
async def open_lib(message: types.Message, state: FSMContext):
    btns = get_saved_buttons(message.from_user.id)
    if not btns: await message.answer("📚 Пусто.", reply_markup=post_creation_keyboard()); return
    data = await state.get_data()
    sel = set(data.get('temp_selected', []))
    await message.answer("**📚 Выберите кнопки:**", parse_mode=ParseMode.MARKDOWN, reply_markup=library_keyboard(btns, sel))

@dp.callback_query(lambda c: c.data.startswith('lib:'))
async def lib_cb(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':'); act = parts[1]; uid = callback.from_user.id
    if act == 'toggle':
        bid = int(parts[2]); btns = get_saved_buttons(uid)
        btn = next((b for b in btns if b['id'] == bid), None)
        if not btn: return
        data = await state.get_data(); sel = set(data.get('temp_selected', []))
        if bid in sel: sel.remove(bid); msg=f"❌ {btn['text']}"
        else: sel.add(bid); msg=f"✅ {btn['text']}"
        await state.update_data(temp_selected=list(sel))
        await callback.message.edit_reply_markup(reply_markup=library_keyboard(get_saved_buttons(uid), sel))
        await callback.answer(msg)
    elif act == 'apply':
        data = await state.get_data(); sels = data.get('temp_selected', [])
        all_b = get_saved_buttons(uid); chosen = [b for b in all_b if b['id'] in sels]
        if not chosen: await callback.answer("⚠️ Ничего не выбрано", show_alert=True); return
        exist = data.get('buttons', []); exist.extend([[b] for b in chosen])
        await state.update_data(buttons=exist, temp_selected=[])
        await callback.message.delete()
        kb = types.InlineKeyboardBuilder()
        for row in exist:
            for b in row: kb.button(text=b['text'], url=b['url'])
        kb.adjust(1)
        await callback.message.answer("✅ Добавлено!", reply_markup=kb.as_markup())
        await callback.message.answer("Жмите **✅ Готово**", reply_markup=post_creation_keyboard())
        await callback.answer()
    elif act == 'back':
        await callback.message.delete()
        await callback.message.answer("🔘 **Меню**", reply_markup=post_creation_keyboard())
        await callback.answer()

# ==================== ФИНАЛ ====================
@dp.message(F.text == "✅ Готово с кнопками")
async def finish_post(message: types.Message, state: FSMContext):
    data = await state.get_data()
    txt = data.get('text', ''); btns = data.get('buttons', [])
    kb = None
    if btns:
        b = types.InlineKeyboardBuilder()
        for row in btns:
            for x in row: b.button(text=x['text'], url=x['url'])
        b.adjust(1); kb = b.as_markup()
    if txt: await message.answer(txt, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif kb: await message.answer(" ", reply_markup=kb)
    await message.answer("✅ **Пост готов!**\n\n1. Нажми на пост выше\n2. Выбери «Переслать»\n3. Выбери чат", parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard())
    await state.clear(); delete_draft(message.from_user.id)

@dp.callback_query(lambda c: c.data.startswith('send:'))
async def send_cb(callback: types.CallbackQuery):
    if callback.data.split(':')[1] == 'manual':
        await callback.message.answer("📤 Нажми на пост → Переслать → Чат")
        await callback.answer()
    else:
        await callback.answer("👻 В разработке", show_alert=True)

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
