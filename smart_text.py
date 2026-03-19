# smart_text.py
import re
import random

EMOJI_THEMES = {
    'thailand': ['🇹🇭', '🌴', '🏖️', '🛺', '🍜', '🥥', '🐘', '🌊', '☀️', '🍹'],
    'vietnam': ['🇻🇳', '🛶', '🎋', '🍚', '☕', '🏍️', '🌾', '🏖️', '🦞'],
    'china': ['🇨🇳', '🏮', '🐉', '🥟', '🍜', '🍵', '🏯', '🧧', '🛍️', '🚄'],
    'dubai_uae': ['🇦🇪', '🏙️', '🏜️', '🐫', '🛍️', '💎', '🏨', '🚁'],
    'egypt': ['🇪🇬', '🔺', '🐪', '🌊', '🤿', '🐠', '☀️', '🕌'],
    'turkey': ['🇹🇷', '🏨', '🍽️', '🍷', '🏖️', '🧖', '🛍️', '🥐'],
    'baikal_siberia': ['🏔️', '🌊', '🧊', '❄️', '🐟', '🛶', '🏕️', '🌲', '🦭'],
    'sochi_sea': ['🌊', '🏖️', '🏔️', '🌴', '🏨', '🚠', '🎢'],
    'general': ['✨', '⭐', '❤️', '👏', '🎉', '🌟', '🔹']
}

KEYWORDS = {
    'thailand': ['тайланд', 'пхукет', 'самуи', 'паттайя'],
    'vietnam': ['вьетнам', 'нячанг', 'фукуок', 'дананг'],
    'china': ['китай', 'ханькоу', 'хэйхэ', 'пекин', 'шанхай'],
    'dubai_uae': ['дубай', 'оаэ', 'абудаби', 'эмираты'],
    'egypt': ['египет', 'шарм', 'хургада', 'каир'],
    'turkey': ['турция', 'анталья', 'стамбул', 'кемер'],
    'baikal_siberia': ['байкал', 'ольхон', 'листвянка', 'иркутск', 'бурятия'],
    'sochi_sea': ['сочи', 'адлер', 'абхазия', 'красная поляна']
}

STYLES = [
    {'name': 'Стандарт', 'list_marker': '▸', 'highlight': True, 'emoji_density': 1},
    {'name': 'Эмоциональный', 'list_marker': '🔹', 'highlight': True, 'emoji_density': 2},
    {'name': 'Минимализм', 'list_marker': '-', 'highlight': False, 'emoji_density': 0},
    {'name': 'Премиум', 'list_marker': '💎', 'highlight': True, 'emoji_density': 1}
]

def detect_theme(text):
    text_lower = text.lower()
    scores = {}
    for theme, words in KEYWORDS.items():
        count = sum(1 for word in words if word in text_lower)
        if count > 0:
            scores[theme] = count
    return max(scores, key=scores.get) if scores else 'general'

def get_emoji_pool(theme):
    pool = list(EMOJI_THEMES.get(theme, EMOJI_THEMES['general']))
    pool.extend(EMOJI_THEMES['general'])
    return list(set(pool))

def remove_emojis(text):
    emoji_pattern = re.compile("[" u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF" u"\U0001F1E0-\U0001F1FF" u"\U00002702-\U000027B0" "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def remove_formatting(text):
    text = re.sub(r'<b>(.*?)</b>', r'\1', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'<i>(.*?)</i>', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    return text

def add_smart_emojis(text, theme, density):
    """Добавляет эмодзи ТОЛЬКО в начало строк, не заменяя слова"""
    lines = text.split('\n')
    result = []
    pool = get_emoji_pool(theme)
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        
        # Проверяем, есть ли уже эмодзи в начале
        first_char = stripped[0] if stripped else ''
        code = ord(first_char) if first_char else 0
        has_emoji = 0x1F300 <= code <= 0x1F9FF or 0x2600 <= code <= 0x27BF or 0x1F1E0 <= code <= 0x1F1FF
        
        if has_emoji:
            result.append(line)  # Не добавляем второй эмодзи
            continue
        
        should_add = False
        if i == 0:  # Заголовок всегда
            should_add = True
        elif density == 2 and len(stripped) < 100:
            should_add = True
        elif density == 1 and len(stripped) < 60:
            should_add = True
        
        if should_add:
            emoji = random.choice(pool)
            result.append(f"{emoji} {line}")
        else:
            result.append(line)
    
    return '\n'.join(result)

def format_lists(text, marker):
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[\-\*\•]\s', stripped):
            result.append(re.sub(r'^[\-\*\•]\s', f'{marker} ', stripped))
        else:
            result.append(line)
    return '\n'.join(result)

def highlight_keywords(text, do_highlight):
    if not do_highlight: return text
    words = ['важно', 'срочно', 'бесплатно', 'акция', 'скидка', 'горящий', 'только сейчас', 'успейте', 'цена', 'руб', 'вылет', 'дата', 'места', 'осталось', 'новинка', 'хит', 'подарок', 'бонус', 'все включено', 'завтраки', 'перелет', 'трансфер', 'виза']
    for word in words:
        # Для HTML
        text = re.sub(r'\b(' + re.escape(word) + r')\b', r'<b>\1</b>', text, flags=re.IGNORECASE)
        # Для Markdown (на всякий случай)
        text = re.sub(r'\b(' + re.escape(word) + r')\b', r'**\1**', text, flags=re.IGNORECASE)
    return text

def smart_format_text(original_text, variant_index):
    if not original_text: 
        return {"text": "", "style_name": "None", "detected_theme": "None"}
    
    # 🔹 ВАЖНО: Сначала чистим старые эмодзи!
    clean_text = remove_emojis(original_text)
    
    style = STYLES[variant_index % len(STYLES)]
    theme = detect_theme(clean_text)
    lines = clean_text.split('\n')
    formatted_lines = []
    header_done = False
    
    for line in lines:
        if not line.strip():
            formatted_lines.append(line)
            continue
        if not header_done:
            clean_line = line.strip()
            # Делаем заголовок жирным (HTML)
            formatted_lines.append(f"<b>{clean_line}</b>")
            header_done = True
        else:
            formatted_lines.append(line)
    
    result = '\n'.join(formatted_lines)
    result = format_lists(result, style['list_marker'])
    result = highlight_keywords(result, style['highlight'])
    result = add_smart_emojis(result, theme, style['emoji_density'])
    
    return {
        "text": result, 
        "style_name": style['name'], 
        "detected_theme": theme.replace('_', ' ').title()
    }
