# smart_text.py
import re
import random

# === ГЛОБАЛЬНАЯ БАЗА ЭМОДЗИ ПО НАПРАВЛЕНИЯМ (ТРИУМФ-ИРКУТСК) ===
EMOJI_THEMES = {
    # Азия
    'thailand': ['🇹🇭', '🌴', '🏖️', '🛺', '🍜', '🥥', '🐘', '🏯', '🌊', '☀️', '🍹', '👙', '🛵', '🥭'],
    'vietnam': ['🇻🇳', '🛶', '🎋', '🍚', '☕', '🏍️', '🌾', '🏖️', '🦞', '🌴', '🏯', '🌅'],
    'china': ['🇨🇳', '🏮', '🐉', '🥟', '🍜', '🍵', '🏯', '🧧', '🎋', '🐼', '🗼', '🛍️', '🚄', '🏙️'],
    'asia_general': ['🌏', '🥢', '🍤', '🍣', '🍱', '👘', '⛩️', '🏮', '🎎', '🌸'],
    
    # Ближний Восток и Африка
    'dubai_uae': ['🇦🇪', '🏙️', '🏜️', '🐫', '🛍️', '💎', '🏨', '✈️', '☀️', '🌊', '🏖️', '🚁', '🏎️'],
    'egypt': ['🇪🇬', '🔺', '🐪', '🌊', '🤿', '🐠', '☀️', '🏖️', '🏨', '🍹', '🕌', '👁️', '📜'],
    'turkey': ['🇹🇷', '🏨', '🍽️', '🍷', '🏖️', '🌊', '🧖', '🛍️', '🕌', '🥐', '🍉', '🍇', '🚐'],
    
    # Россия
    'baikal_siberia': ['🏔️', '🌊', '🧊', '❄️', '🐟', '🛶', '🏕️', '🌲', '🦭', '☃️', '🔥', '🚂', '🍯'],
    'moscow_spb': ['🇷🇺', '🏛️', '🎭', '🖼️', '🚇', '🌉', '⛪', '🏰', '🎡', '🚶', '📸', '🌧️', '🍂'],
    'sochi_sea': ['🌊', '🏖️', '🏔️', '🌴', '🏨', '🚠', '🎢', '🎿', '☀️', '🍷', '🍇', '🥝'],
    'altay': ['⛰️', '🌲', '🏞️', '🚙', '🏕️', '🔥', '🌌', '🦌', '🍯', '🧀', '🐎', '🌾'],
    'karelia': ['🌲', '🌊', '🛶', '🍄', '🫐', '🪵', '🏕️', '❄️', '🎣', '🚙', '🏰'],
    'russia_general': ['🇷🇺', '🚆', '✈️', '🗺️', '📍', '🏨', '🍽️', '🎒', '📸'],

    # Общее и Акции
    'sale': ['🔥', '⚡', '💸', '🏷️', '📢', '🆘', '❗', '💣', '🚀', '📉', '🤑', '🎁', '✅'],
    'hotel_service': ['🏨', '🛏️', '🍽️', '🍹', '🏊', '🧖', '🛎️', '🔑', '🧹', '📶', '🅿️', '👶'],
    'transport': ['✈️', '🚆', '🚌', '🚕', '🚢', '🚁', '🚙', '🚲', '🧳', '🎫', '🛂', '⏱️'],
    'general': ['✨', '⭐', '❤️', '😍', '👏', '🎉', '🌟', '💫', '🌈', '🦋', '🔹', '▫️']
}

# === КЛЮЧЕВЫЕ СЛОВА ДЛЯ РАСПОЗНАВАНИЯ ТЕМ ===
KEYWORDS = {
    # Азия
    'thailand': ['тайланд', 'пхукет', 'самуи', 'паттайя', 'краби', 'ханой', 'чиангмай', 'асия', 'сиам', 'тук-тук', 'манго', 'пад тай'],
    'vietnam': ['вьетнам', 'нячанг', 'фукуок', 'дананг', 'халонг', 'хошимин', 'ханой', 'фаго', 'лотос', 'кофе', 'рис'],
    'china': ['китай', 'ханькоу', 'хэйхэ', 'хайлар', 'пекин', 'шанхай', 'гуанчжоу', 'виза', 'безвиз', 'поднебесная', 'дракон', 'шоппинг', 'рынок', 'чай', 'лапша'],
    
    # Ближний Восток и Африка
    'dubai_uae': ['дубай', 'оаэ', 'абудаби', 'эмираты', 'бурдж', 'пустыня', 'сафари', 'молл', 'золото', 'роскошь', 'фонтан'],
    'egypt': ['египет', 'шарм', 'хургада', 'каир', 'пирамида', 'сфинкс', 'ниль', 'красное море', 'кораллы', 'дайвинг', 'снорклинг', 'ель гунна'],
    'turkey': ['турция', 'анталья', 'стамбул', 'кемер', 'alanya', 'bodrum', 'мармарис', 'все включено', 'all inclusive', 'улуд', 'каппадокия', 'падишах'],
    
    # Россия
    'baikal_siberia': ['байкал', 'ольхон', 'листвянка', 'иркутск', 'бурятия', 'омпуль', 'лед', 'круиз', 'теплоход', 'нерпа', 'кедр', 'тайга', 'саган-заба', 'котельниковский', 'аршан'],
    'moscow_spb': ['москва', 'питер', 'санкт-петербург', 'кремль', 'эрмитаж', 'невский', 'красная площадь', 'театр', 'музей', 'метро', 'нева', 'мойка'],
    'sochi_sea': ['сочи', 'адлер', 'абхазия', 'гагра', 'пицунда', 'красная поляна', 'роза хутор', 'море', 'горы', 'олимпиада', 'парк', 'дендрарий'],
    'altay': ['алтай', 'горно', 'чемал', 'телецкое', 'катунь', 'белуха', 'чуйский тракт', 'марс', 'гейзеры', 'кедровка', 'сыр', 'мед'],
    'karelia': ['карелия', 'петрозаводск', 'кижи', 'валаам', 'рускеала', 'горный парк', 'лес', 'озеро', 'грибы', 'ягоды', 'циклоп'],
    
    # Общие темы
    'hotel_service': ['отель', 'гостиница', 'номер', 'люкс', 'стандарт', 'завтрак', 'ужин', 'бассейн', 'спа', 'массаж', 'ресторан', 'бар', 'анимация', 'детский клуб', 'няня', 'трансфер'],
    'transport': ['вылет', 'перелет', 'авиа', 'билет', 'рейс', 'чартер', 'стыковка', 'багаж', 'ручная кладь', 'автобус', 'поезд', 'корабль', 'трансфер', 'встреча'],
    'sale': ['горящий', 'акция', 'скидка', 'спеццена', 'выгодно', 'дешево', 'распродажа', 'только сейчас', 'успейте', 'последние места', 'раннее бронирование', 'подарок', 'бесплатно', 'children free', 'промокод', 'черная пятница']
}

STYLES = [
    {'name': 'Стандарт Триумф', 'list_marker': '▸', 'highlight': True, 'emoji_density': 1},
    {'name': 'Эмоциональный 🔥', 'list_marker': '🔹', 'highlight': True, 'emoji_density': 2},
    {'name': 'Минимализм', 'list_marker': '-', 'highlight': False, 'emoji_density': 0},
    {'name': 'Премиум VIP', 'list_marker': '💎', 'highlight': True, 'emoji_density': 1},
    {'name': 'Срочно! Sale', 'list_marker': '❗', 'highlight': True, 'emoji_density': 2}
]

def detect_theme(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for theme, words in KEYWORDS.items():
        count = sum(1 for word in words if word in text_lower)
        if count > 0:
            weight = 3 if theme in ['thailand', 'vietnam', 'china', 'dubai_uae', 'egypt', 'turkey', 'baikal_siberia'] else 1
            if theme == 'sale': weight = 2
            scores[theme] = count * weight
    return max(scores, key=scores.get) if scores else 'general'

def has_emoji_at_start(line: str) -> bool:
    if not line.strip(): return True
    first_char = line.strip()[0]
    code = ord(first_char)
    return 0x1F300 <= code <= 0x1F9FF or 0x2600 <= code <= 0x27BF or 0x1F1E0 <= code <= 0x1F1FF

def get_emoji_pool(theme: str) -> list:
    pool = list(EMOJI_THEMES.get(theme, []))
    if theme in ['thailand', 'vietnam', 'china']: pool.extend(EMOJI_THEMES.get('asia_general', []))
    if theme in ['dubai_uae', 'egypt', 'turkey']: pool.extend(EMOJI_THEMES.get('hotel_service', []))
    if theme in ['baikal_siberia', 'altay', 'karelia']: pool.extend(EMOJI_THEMES.get('russia_general', []))
    pool.extend(EMOJI_THEMES.get('general', []))
    return list(set(pool))

def add_emojis_to_lines(text: str, theme: str, density: int) -> str:
    lines = text.split('\n')
    result = []
    pool = get_emoji_pool(theme)
    if not pool: pool = EMOJI_THEMES['general']
    
    for i, line in enumerate(lines):
        if not line.strip():
            result.append(line)
            continue
        if has_emoji_at_start(line):
            result.append(line)
            continue
        
        should_add = False
        if i == 0: should_add = True
        elif density == 2 and len(line.strip()) < 100 and not re.match(r'^[\-\*\•\▸❗]', line.strip()): should_add = True
        elif density == 1 and len(line.strip()) < 60 and not re.match(r'^[\-\*\•\▸❗]', line.strip()): should_add = True
            
        if should_add:
            result.append(f"{random.choice(pool)} {line}")
        else:
            result.append(line)
    return '\n'.join(result)

def format_lists(text: str, marker: str) -> str:
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[\-\*\•]\s', stripped):
            result.append(re.sub(r'^[\-\*\•]\s', f'{marker} ', stripped))
        else:
            result.append(line)
    return '\n'.join(result)

def highlight_keywords(text: str, do_highlight: bool) -> str:
    if not do_highlight: return text
    words = ['важно', 'срочно', 'бесплатно', 'акция', 'скидка', 'горящий', 'только сейчас', 'успейте', 'цена', 'руб', 'вылет', 'дата', 'места', 'осталось', 'новинка', 'хит', 'подарок', 'бонус', 'все включено', 'завтраки', 'перелет', 'трансфер', 'виза']
    for word in words:
        text = re.sub(r'\b(' + re.escape(word) + r')\b', r'**\1**', text, flags=re.IGNORECASE)
    return text

def smart_format_text(original_text: str, variant_index: int) -> dict:
    if not original_text: return {"text": "", "style_name": "None", "detected_theme": "None"}
    
    style = STYLES[variant_index % len(STYLES)]
    theme = detect_theme(original_text)
    theme_emojis = get_emoji_pool(theme)
    
    lines = original_text.split('\n')
    formatted_lines = []
    header_done = False
    
    for line in lines:
        if not line.strip():
            formatted_lines.append(line)
            continue
        if not header_done:
            emoji = random.choice(theme_emojis) if not has_emoji_at_start(line) else ""
            formatted_lines.append(f"**{emoji} {line.strip()}**".replace("  ", " "))
            header_done = True
        else:
            formatted_lines.append(line)
    
    result = '\n'.join(formatted_lines)
    result = format_lists(result, style['list_marker'])
    result = highlight_keywords(result, style['highlight'])
    result = add_emojis_to_lines(result, theme, style['emoji_density'])
    
    return {"text": result, "style_name": style['name'], "detected_theme": theme.replace('_', ' ').title()}
