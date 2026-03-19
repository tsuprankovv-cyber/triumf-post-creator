# database.py
import sqlite3, json, logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_NAME = 'templates.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Таблица кнопок
    c.execute('''CREATE TABLE IF NOT EXISTS saved_buttons
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  button_text TEXT, button_url TEXT, created_at TIMESTAMP)''')
    
    # Таблица ссылок (для слов-ссылок)
    c.execute('''CREATE TABLE IF NOT EXISTS saved_links
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  link_text TEXT, link_url TEXT, created_at TIMESTAMP)''')
    
    # Таблица опубликованных постов (для редактирования)
    c.execute('''CREATE TABLE IF NOT EXISTS published_posts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                  media_type TEXT, media_id TEXT, text_content TEXT, 
                  buttons_json TEXT, created_at TIMESTAMP)''')
    
    # Таблица черновиков
    c.execute('''CREATE TABLE IF NOT EXISTS post_drafts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  media_type TEXT, media_id TEXT, text_content TEXT, 
                  buttons_json TEXT, current_step TEXT, 
                  created_at TIMESTAMP, updated_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def save_button(user_id, text, url, limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Проверка на дубликат
    c.execute('SELECT id FROM saved_buttons WHERE user_id=? AND button_text=? AND button_url=?', 
              (user_id, text, url))
    if c.fetchone():
        conn.close()
        return False, 'duplicate'
    
    # Проверка лимита
    c.execute('SELECT COUNT(*) FROM saved_buttons WHERE user_id=?', (user_id,))
    count = c.fetchone()[0]
    
    if count >= limit:
        # Удаляем самую старую
        c.execute('SELECT id FROM saved_buttons WHERE user_id=? ORDER BY created_at ASC LIMIT 1', (user_id,))
        old = c.fetchone()
        if old:
            c.execute('DELETE FROM saved_buttons WHERE id=?', (old[0],))
            conn.commit()
    
    c.execute('INSERT INTO saved_buttons (user_id, button_text, button_url, created_at) VALUES (?, ?, ?, ?)', 
              (user_id, text, url, datetime.now()))
    conn.commit()
    conn.close()
    return True, 'saved'

def get_saved_buttons(user_id, limit=50):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, button_text, button_url FROM saved_buttons WHERE user_id=? ORDER BY created_at DESC LIMIT ?', 
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'text': r[1], 'url': r[2]} for r in rows]

def delete_button(button_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM saved_buttons WHERE id=? AND user_id=?', (button_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_button(button_id, user_id, new_text, new_url):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE saved_buttons SET button_text=?, button_url=? WHERE id=? AND user_id=?', 
              (new_text, new_url, button_id, user_id))
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def save_link(user_id, text, url, limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('SELECT id FROM saved_links WHERE user_id=? AND link_text=? AND link_url=?', 
              (user_id, text, url))
    if c.fetchone():
        conn.close()
        return False, 'duplicate'
    
    c.execute('SELECT COUNT(*) FROM saved_links WHERE user_id=?', (user_id,))
    count = c.fetchone()[0]
    
    if count >= limit:
        c.execute('SELECT id FROM saved_links WHERE user_id=? ORDER BY created_at ASC LIMIT 1', (user_id,))
        old = c.fetchone()
        if old:
            c.execute('DELETE FROM saved_links WHERE id=?', (old[0],))
            conn.commit()
    
    c.execute('INSERT INTO saved_links (user_id, link_text, link_url, created_at) VALUES (?, ?, ?, ?)', 
              (user_id, text, url, datetime.now()))
    conn.commit()
    conn.close()
    return True, 'saved'

def get_saved_links(user_id, limit=50):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, link_text, link_url FROM saved_links WHERE user_id=? ORDER BY created_at DESC LIMIT ?', 
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'text': r[1], 'url': r[2]} for r in rows]

def delete_link(link_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM saved_links WHERE id=? AND user_id=?', (link_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_link(link_id, user_id, new_text, new_url):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE saved_links SET link_text=?, link_url=? WHERE id=? AND user_id=?', 
              (new_text, new_url, link_id, user_id))
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def save_published_post(user_id, media_type, media_id, text, buttons, limit=50):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Проверка лимита
    c.execute('SELECT COUNT(*) FROM published_posts WHERE user_id=?', (user_id,))
    count = c.fetchone()[0]
    
    if count >= limit:
        c.execute('SELECT id FROM published_posts WHERE user_id=? ORDER BY created_at ASC LIMIT 1', (user_id,))
        old = c.fetchone()
        if old:
            c.execute('DELETE FROM published_posts WHERE id=?', (old[0],))
            conn.commit()
    
    buttons_json = json.dumps(buttons) if buttons else None
    c.execute('''INSERT INTO published_posts 
                 (user_id, media_type, media_id, text_content, buttons_json, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?)''', 
              (user_id, media_type, media_id, text, buttons_json, datetime.now()))
    conn.commit()
    post_id = c.lastrowid
    conn.close()
    return post_id

def get_published_posts(user_id, limit=50):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT id, media_type, media_id, text_content, buttons_json, created_at 
                 FROM published_posts WHERE user_id=? ORDER BY created_at DESC LIMIT ?''', 
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 
        'media_type': r[1], 
        'media_id': r[2], 
        'text': r[3], 
        'buttons': json.loads(r[4]) if r[4] else [],
        'created_at': r[5]
    } for r in rows]

def get_published_post(post_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT media_type, media_id, text_content, buttons_json 
                 FROM published_posts WHERE id=? AND user_id=?''', (post_id, user_id))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'media_type': row[0],
            'media_id': row[1],
            'text': row[2],
            'buttons': json.loads(row[3]) if row[3] else []
        }
    return None

def delete_published_post(post_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM published_posts WHERE id=? AND user_id=?', (post_id, user_id))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def save_draft(user_id, data, step):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id FROM post_drafts WHERE user_id=?', (user_id,))
    exists = c.fetchone()
    now = datetime.now()
    btn_json = json.dumps(data.get('buttons', [])) if data.get('buttons') else None
    if exists:
        c.execute('''UPDATE post_drafts SET media_type=?, media_id=?, text_content=?, 
                     buttons_json=?, current_step=?, updated_at=? WHERE user_id=?''',
                  (data.get('media_type'), data.get('media_id'), data.get('text'), 
                   btn_json, step, now, user_id))
    else:
        c.execute('''INSERT INTO post_drafts 
                     (user_id, media_type, media_id, text_content, buttons_json, current_step, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, data.get('media_type'), data.get('media_id'), data.get('text'), 
                   btn_json, step, now, now))
    conn.commit()
    conn.close()
    return True

def get_draft(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT media_type, media_id, text_content, buttons_json, current_step FROM post_drafts WHERE user_id=?', 
              (user_id,))
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

def delete_draft(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM post_drafts WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    return True
