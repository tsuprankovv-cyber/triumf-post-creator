# database.py
import sqlite3
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)
DB_NAME = 'templates.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Таблица сохранённых кнопок
    c.execute('''CREATE TABLE IF NOT EXISTS saved_buttons
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  button_text TEXT,
                  button_url TEXT,
                  created_at TIMESTAMP)''')
    
    # Таблица черновиков постов
    c.execute('''CREATE TABLE IF NOT EXISTS post_drafts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  media_type TEXT,
                  media_id TEXT,
                  text_content TEXT,
                  buttons_json TEXT,
                  current_step TEXT,
                  created_at TIMESTAMP,
                  updated_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

# ==================== КНОПКИ ====================

def save_button(user_id: int, text: str, url: str) -> bool:
    """Сохраняет кнопку в библиотеку пользователя"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Проверяем на дубликат
    c.execute('SELECT id FROM saved_buttons WHERE user_id = ? AND button_text = ? AND button_url = ?',
              (user_id, text, url))
    if c.fetchone():
        conn.close()
        logger.info(f"⏭️ Кнопка уже существует: {text}")
        return False
    
    c.execute('INSERT INTO saved_buttons (user_id, button_text, button_url, created_at) VALUES (?, ?, ?, ?)',
              (user_id, text, url, datetime.now()))
    conn.commit()
    conn.close()
    logger.info(f"✅ Кнопка сохранена: {text} → {url[:30]}...")
    return True

def get_saved_buttons(user_id: int, limit: int = 20) -> list:
    """Получает сохранённые кнопки пользователя"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, button_text, button_url FROM saved_buttons WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'text': r[1], 'url': r[2]} for r in rows]

def delete_button(button_id: int, user_id: int) -> bool:
    """Удаляет кнопку из библиотеки"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM saved_buttons WHERE id = ? AND user_id = ?', (button_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# ==================== ЧЕРНОВИКИ ====================

def save_draft(user_id: int, data: dict, step: str) -> bool:
    """Сохраняет черновик поста"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('SELECT id FROM post_drafts WHERE user_id = ?', (user_id,))
    existing = c.fetchone()
    now = datetime.now()
    
    buttons_json = json.dumps(data.get('buttons', [])) if data.get('buttons') else None
    
    if existing:
        c.execute('''UPDATE post_drafts SET media_type = ?, media_id = ?, text_content = ?,
                     buttons_json = ?, current_step = ?, updated_at = ? WHERE user_id = ?''',
                  (data.get('media_type'), data.get('media_id'), data.get('text'),
                   buttons_json, step, now, user_id))
    else:
        c.execute('''INSERT INTO post_drafts (user_id, media_type, media_id, text_content,
                     buttons_json, current_step, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, data.get('media_type'), data.get('media_id'), data.get('text'),
                   buttons_json, step, now, now))
    
    conn.commit()
    conn.close()
    logger.info(f"💾 Черновик сохранён (шаг: {step}, кнопок: {len(data.get('buttons', []))})")
    return True

def get_draft(user_id: int) -> dict:
    """Получает черновик пользователя"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT media_type, media_id, text_content, buttons_json, current_step FROM post_drafts WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'media_type': row[0],
            'media_id': row[1],
            'text': row[2],
            'buttons': json.loads(row[3]) if row[3] else [],
            'current_step': row[4]
        }
    return {}

def delete_draft(user_id: int) -> bool:
    """Удаляет черновик"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM post_drafts WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True
