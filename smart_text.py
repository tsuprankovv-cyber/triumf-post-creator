# smart_text.py
import re
import random

# === БАЗЫ ЭМОДЗИ (Только для усиления, не замены) ===
EMOJI_THEMES = {
    'thailand': ['🇹🇭', '🌴', '🏖️', '🛺', '🍜', '🥥', '🐘', '🌊', '☀️', '🍹'],
    'vietnam': ['🇻🇳', '🛶', '🎋', '🍚', '☕', '🏍️', '🌾', '🏖️', '🦞'],
    'china': ['🇨🇳', '🏮', '🐉', '🥟', '🍜', '🍵', '🏯', '🧧', '🛍️', '🚄'],
    'asia_general': ['🌏', '🥢', '🍤', '🌸', '⛩️'],
    'dubai_uae': ['🇦🇪', '🏙️', '🏜️', '🐫', '🛍️', '💎', '🏨', '🚁'],
    'egypt': ['🇪🇬', '🔺', '🐪', '🌊', '🤿', '🐠', '☀️', '🕌'],
    'turkey': ['🇹🇷', '🏨', '🍽️', '🍷', '🏖️', '🧖', '🛍️', '🥐'],
    'baikal_siberia': ['🏔️', '🌊', '🧊', '❄️', '🐟', '🛶', '🏕️', '🌲', '🦭'],
    'moscow_spb': ['🇷🇺', '🏛️', '🎭', '🖼️', '🚇', '🌉', '⛪', '🏰'],
    'sochi_sea': ['🌊', '🏖️', '🏔️', '🌴', '🏨', '🚠', '🎢'],
    'altay': ['⛰️', '🌲', '🏞️', '🚙', '🏕️', '🔥', '🌌', '🦌'],
    'karelia': ['🌲', '🌊', '🛶', '🍄', '🫐', '🪵', '🏕️'],
    'russia_general': ['🇷🇺', '🚆', '✈️', '🗺️', '📍', '🏨'],
    'sale': ['🔥', '⚡', '💸', '🏷️', '📢', '❗', '🚀', '🎁'],
    'hotel_service': ['🏨', '🛏️', '🍽️', '🍹', '🏊', '🧖', '🛎️'],
    'transport': ['✈️', '🚆', '🚌', '🚕', '🚢', '🧳', '🎫'],
    'general': ['✨', '⭐', '❤️', '👏', '🎉', '🌟', '🔹']
}

KEYWORDS = {
    'thailand': ['тайланд', 'пхукет', 'самуи', 'паттайя', 'краби', 'сиам'],
    'vietnam': ['вьетнам', 'нячанг', 'фукуок', 'дананг', 'халонг'],
    'china': ['китай', 'ханькоу', 'хэйхэ', 'хайлар', 'пекин', 'шанхай', 'виза', 'безвиз', 'шоппинг'],
    'dubai_uae': ['дубай', 'оаэ', 'абудаби', 'эмираты', 'бурдж', 'сафари'],
    'egypt': ['египет', 'шарм', 'хургада', 'каир', 'пирамида', 'красное море'],
    'turkey': ['турция', 'анталья', 'стамбул', 'кемер', 'алания', 'все включено', 'all inclusive'],
    'baikal_siberia': ['байкал', 'ольхон', 'листвянка', 'иркутск', 'бурятия', 'омпуль', 'лед', 'круиз'],
    'moscow_spb': ['москва', 'питер', 'санкт-петербург', 'кремль', 'эрмитаж'],
    'sochi_sea': ['сочи', 'адлер', 'абхазия', 'красная поляна', 'море', 'горы'],
    'altay': ['алтай', 'чемал', 'телецкое', 'катунь', 'белуха'],
    'karelia': ['карелия', 'петрозаводск', 'кижи', 'валаам', 'рускеала'],
    'hotel_service': ['отель', 'гостиница', 'номер', 'завтрак', 'ужин', 'бассейн', 'спа', 'ресторан'],
    'transport': ['вылет', 'перелет', 'авиа', 'билет', 'рейс', 'трансфер', 'встреча'],
    'sale': ['горящий', 'акция', 'скидка', 'спеццена', 'выгодно', 'распродажа', 'успейте', 'подарок', 'бесплатно']
}

STYLES = [
    {'name': 'Стандарт', 'list_marker': '▸', 'highlight': True, 'emoji_density': 1},
    {'name': 'Эмоциональный', 'list_marker': '🔹', 'highlight': True, 'emoji_density': 2},
    {'name': 'Минимализм', 'list_marker': '-', 'highlight': False, 'emoji_density': 0},
    {'name': 'Премиум', 'list_marker': '💎', 'highlight': True, 'emoji_density': 1},
    {'name': 'Срочно', 'list_marker': '❗', 'highlight': True, 'emoji_density': 2}
]

def detect_theme(text):
    text_lower = text.lower()
    scores = {}
    for theme, words in KEYWORDS.items():
        count = sum(1 for word in words if word in text_lower)
        if count > 0:
            weight = 3 if theme in ['thailand', 'vietnam', 'china', 'dubai_uae', 'egypt', 'turkey', 'baikal_siberia'] else 1
            if theme == 'sale': weight = 2
            scores[theme] = count * weight
    return max(scores, key=scores.get) if scores else 'general'

def get_emoji_pool(theme):
    pool = list(EMOJI_THEMES.get(theme, []))
    if theme in ['thailand', 'vietnam', 'china']: pool.extend(EMOJI_THEMES.get('asia_general', []))
    if theme in ['dubai_uae', 'egypt', 'turkey']: pool.extend(EMOJI_THEMES.get('hotel_service', []))
    if theme in ['baikal_siberia', 'altay', 'karelia']: pool.extend(EMOJI_THEMES.get('russia_general', []))
    pool.extend(EMOJI_THEMES.get('general', []))
    return list(set(pool))

def remove_emojis(text):
    """Удаляет все эмодзи из текста, оставляя форматирование"""
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text).strip()

def remove_formatting(text):
    """Удаляет Markdown форматирование (**, *, __), оставляя эмодзи"""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    return text

def add_smart_emojis(text, theme, density):
    """Добавляет эмодзи ТОЛЬКО рядом со словами или в начало строк, не заменяя их"""
    lines = text.split('\n')
    result = []
    pool = get_emoji_pool(theme)
    if not pool: pool = EMOJI_THEMES['general']
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
            
        # Проверка: есть ли уже эмодзи в начале?
        first_char = stripped[0] if stripped else ''
        code = ord(first_char) if first_char else 0
        has_emoji_start = 0x1F300 <= code <= 0x1F9FF or 0x2600 <= code <= 0x27BF or 0x1F1E0 <= code <= 0x1F1FF
        
        should_add = False
        if i == 0: should_add = True # Заголовок всегда
        elif density == 2 and len(stripped) < 100: should_add = True
        elif density == 1 and len(stripped) < 60: should_add = True
        
        if should_add and not has_emoji_start:
            emoji = random.choice(pool)
            # Добавляем ПЕРЕД строкой, не заменяя слова
            result.append(f"{emoji} {line}")
        else:
            result.append(line)
            
    return '\n'.join(result)

def format_lists(text, marker):
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        # Заменяем маркеры списков на красивые, но не трогаем текст
        if re.match(r'^[\-\*\•]\s', stripped):
            result.append(re.sub(r'^[\-\*\•]\s', f'{marker} ', stripped))
        else:
            result.append(line)
    return '\n'.join(result)

def highlight_keywords(text, do_highlight):
    if not do_highlight: return text
    words = ['важно', 'срочно', 'бесплатно', 'акция', 'скидка', 'горящий', 'только сейчас', 'успейте', 'цена', 'руб', 'вылет', 'дата', 'места', 'осталось', 'новинка', 'хит', 'подарок', 'бонус', 'все включено', 'завтраки', 'перелет', 'трансфер', 'виза']
    for word in words:
        text = re.sub(r'\b(' + re.escape(word) + r')\b', r'**\1**', text, flags=re.IGNORECASE)
    return text

def smart_format_text(original_text, variant_index):
    if not original_text: return {"text": "", "style_name": "None", "detected_theme": "None"}
    
    style = STYLES[variant_index % len(STYLES)]
    theme = detect_theme(original_text)
    
    lines = original_text.split('\n')
    formatted_lines = []
    header_done = False
    
    # 1. Обработка заголовка и структуры
    for line in lines:
        if not line.strip():
            formatted_lines.append(line)
            continue
        
        if not header_done:
            clean_line = line.strip()
            # Делаем заголовок жирным
            formatted_lines.append(f"**{clean_line}**")
            header_done = True
        else:
            formatted_lines.append(line)
    
    result = '\n'.join(formatted_lines)
    result = format_lists(result, style['list_marker'])
    result = highlight_keywords(result, style['highlight'])
    
    # 2. Добавление эмодзи (только рядом, не вместо)
    result = add_smart_emojis(result, theme, style['emoji_density'])
    
    return {
        "text": result, 
        "style_name": style['name'], 
        "detected_theme": theme.replace('_', ' ').title()
    }
