# smart_text.py
import re
import random

# === БАЗЫ ЭМОДЗИ ===
EMOJI_THEMES = {
    'thailand': ['🇹🇭', '🌴', '🏖️', '🛺', '🍜', '🥥', '🐘', '🌊', '☀️', '🍹', '🔫', '🎉'],
    'vietnam': ['🇻🇳', '🛶', '🎋', '🍚', '☕', '🏍️', '🌾', '🏖️', '🦞'],
    'china': ['🇨🇳', '🏮', '🐉', '🥟', '🍜', '🍵', '🏯', '🧧', '🛍️', '🚄'],
    'dubai_uae': ['🇦🇪', '🏙️', '🏜️', '🐫', '🛍️', '💎', '🏨', '🚁', '🥂'],
    'egypt': ['🇪🇬', '🔺', '🐪', '🌊', '🤿', '🐠', '☀️', '🕌', '🏛️'],
    'turkey': ['🇹🇷', '🏨', '🍽️', '🍷', '🏖️', '🧖', '🛍️', '🥐', '🌅'],
    'baikal_siberia': ['🏔️', '🌊', '🧊', '❄️', '🐟', '🛶', '🏕️', '🌲', '🦭', '🔥'],
    'sochi_sea': ['🌊', '🏖️', '🏔️', '🌴', '🏨', '🚠', '🎢', '🍷', '🍇'],
    'general': ['✨', '⭐', '❤️', '👏', '🎉', '🌟', '🔹', '💫']
}

KEYWORDS = {
    'thailand': ['тайланд', 'пхукет', 'самуи', 'паттайя', 'краби', 'сиам', 'сонгкран'],
    'vietnam': ['вьетнам', 'нячанг', 'фукуок', 'дананг', 'халонг'],
    'china': ['китай', 'ханькоу', 'хэйхэ', 'хайлар', 'пекин', 'шанхай', 'виза', 'безвиз'],
    'dubai_uae': ['дубай', 'оаэ', 'абудаби', 'эмираты', 'бурдж', 'сафари'],
    'egypt': ['египет', 'шарм', 'хургада', 'каир', 'пирамида', 'красное море'],
    'turkey': ['турция', 'анталья', 'стамбул', 'кемер', 'алания', 'все включено', 'all inclusive'],
    'baikal_siberia': ['байкал', 'ольхон', 'листвянка', 'иркутск', 'бурятия', 'омпуль', 'лед', 'круиз'],
    'sochi_sea': ['сочи', 'адлер', 'абхазия', 'красная поляна', 'море', 'горы']
}

# === ПРОДВИНУТЫЕ ШАБЛОНЫ КОПИРАЙТИНГА ===
COPYWRITING_TEMPLATES = {
    'sale': {
        'headline': [
            "🔥 {destination}: ЭТО НЕ ПРОСТО ТУР, ЭТО {emotion}!",
            "⚡ ГОРЯЩЕЕ ПРЕДЛОЖЕНИЕ: {destination} по цене МЕЧТЫ!",
            "💣 БОМБА! {destination} за {price} — вы НЕ поверите!",
            "🚨 СРОЧНО: {destination} ждёт ВАС, но мест осталось {count}!"
        ],
        'body': [
            "Друзья, это не просто отпуск. Это {experience}.\n\n"
            "Мы нашли варианты, которые другие турагенты даже не показывают — потому что не верят, что такое возможно.\n\n"
            "👇 ЧТО ВЫ ПОЛУЧАЕТЕ:",
            "Внимание! Это предложение исчезнет быстрее, чем вы скажете «чемодан».\n\n"
            "Почему? Потому что мы договорились с отелем о спеццене ТОЛЬКО для наших клиентов.\n\n"
            "👇 ВАШИ ВЫГОДЫ:",
            "Если вы искали идеальный момент — ЭТО ОН.\n\n"
            "{destination} в {month} — это магия, которую нельзя описать словами. Нужно видеть.\n\n"
            "👇 ЧТО ВКЛЮЧЕНО:"
        ],
        'benefits': [
            "✈️ Перелёт (туда-обратно) — без доплат и скрытых сборов",
            "🏨 Проживание в отеле {stars} — утром море, вечером закаты",
            "🍽️ Питание {food} — забудьте о готовке, вы в отпуске",
            "🚐 Трансфер из аэропорта — вас встретят как VIP",
            "📄 Страховка — отдыхайте без тревог",
            "🎁 БОНУС: {bonus} — только при бронировании до {date}"
        ],
        'cta': [
            "💰 <b>Цена: {price} рублей на человека</b>\n\n"
            "🔥 Мест осталось: {count}. Когда они закончатся — цена вырастет на 30%.\n\n"
            "📞 <b>ЗВОНИТЕ ПРЯМО СЕЙЧАС:</b> {phone}\n"
            "💬 <b>ИЛИ ПИШИТЕ:</b> @{username}\n\n"
            "⏰ <b>Предложение действует до {date}!</b>",
            "💰 <b>Всего {price} рублей!</b>\n\n"
            "Да, вы не ослышались. Это реальная цена, а не «от» с кучей доплат.\n\n"
            "📲 <b>Бронируйте сейчас:</b>\n"
            "Телефон: {phone}\n"
            "Telegram: @{username}\n\n"
            "⚡ <b>Успейте!</b> Через 24 часа цена изменится.",
            "💵 <b>{price} рублей — и всё включено!</b>\n\n"
            "Никаких «доплат на месте». Никаких сюрпризов. Только отдых.\n\n"
            "📞 <b>Забронировать:</b> {phone}\n"
            "💬 <b>Консультация:</b> @{username}\n\n"
            "🎯 <b>Внимание:</b> группа формируется до {date}. Потом — только по полной цене."
        ]
    },
    'standard': {
        'headline': [
            "✨ {destination}: Путешествие, о котором вы мечтаете",
            "🌴 Откройте для себя {destination} — рай на земле",
            "💎 Эксклюзивный тур в {destination} — только для избранных"
        ],
        'body': [
            "Приглашаем вас в незабываемое путешествие!\n\n"
            "{destination} — это место, где мечты становятся реальностью.\n\n"
            "👇 ЧТО ВАС ЖДЁТ:",
            "Вы заслужили лучший отдых. И мы знаем, как его организовать.\n\n"
            "{destination} встретит вас теплом, солнцем и невероятными впечатлениями.\n\n"
            "👇 ПРОГРАММА ТУРА:",
            "Готовы к приключениям? {destination} ждёт!\n\n"
            "Мы продумали каждую деталь, чтобы вы наслаждались каждым моментом.\n\n"
            "👇 ВАШИ ПРЕИМУЩЕСТВА:"
        ],
        'benefits': [
            "✈️ Комфортный перелёт без пересадок",
            "🏨 Отель {stars} с лучшим видом",
            "🍽️ Питание {food} — местная кухня и европейский комфорт",
            "🌊 Первая линия — море в 50 метрах от номера",
            "🎯 Индивидуальная программа экскурсий"
        ],
        'cta': [
            "💰 <b>Стоимость: {price} рублей</b>\n\n"
            "📞 <b>Забронировать:</b> {phone}\n"
            "💬 <b>Узнать детали:</b> @{username}\n\n"
            "✨ <b>Ждём вас в путешествии мечты!</b>",
            "💵 <b>Цена: {price} рублей на человека</b>\n\n"
            "📲 <b>Свяжитесь с нами:</b>\n"
            "Телефон: {phone}\n"
            "Telegram: @{username}\n\n"
            "🌟 <b>Подарите себе незабываемый отдых!</b>"
        ]
    }
}

def detect_theme(text):
    text_lower = text.lower()
    scores = {}
    for theme, words in KEYWORDS.items():
        count = sum(1 for word in words if word in text_lower)
        if count > 0:
            scores[theme] = count
    return max(scores, key=scores.get) if scores else 'general'

def detect_intent(kws):
    """Определяет намерение: продажа, информация, срочность"""
    if any(w in kws for w in ['горящий', 'акция', 'скидка', 'спеццена', 'вау', 'бомба']):
        return 'sale'
    return 'standard'

def get_emoji_pool(theme):
    pool = list(EMOJI_THEMES.get(theme, EMOJI_THEMES['general']))
    pool.extend(EMOJI_THEMES['general'])
    return list(set(pool))

def remove_emojis(text):
    """Полностью удаляет все эмодзи из текста"""
    if not text:
        return ""
    emoji_pattern = re.compile(
        "[" 
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", 
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub('', text)
    # Удаляем лишние пробелы после очистки
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def remove_formatting(text):
    """Удаляет HTML и Markdown форматирование"""
    if not text:
        return ""
    # HTML
    text = re.sub(r'<b>(.*?)</b>', r'\1', text)
    text = re.sub(r'<i>(.*?)</i>', r'\1', text)
    text = re.sub(r'<u>(.*?)</u>', r'\1', text)
    text = re.sub(r'<s>(.*?)</s>', r'\1', text)
    # Markdown
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    # Чистим звёздочки которые могли остаться
    text = text.replace('**', '').replace('__', '')
    return text.strip()

def generate_ai_text(keywords: str) -> str:
    """ПРОДВИНУТЫЙ ГЕНЕРАТОР ТЕКСТОВ С КОПИРАЙТИНГОМ"""
    kws = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    
    if not kws:
        return "<b>⚠️ Введите ключевые слова!</b>\n\nПример: <code>Паттайя, апрель, 50000 руб, вау цены</code>"
    
    # Определяем тему и намерение
    theme = detect_theme(keywords)
    intent = detect_intent(kws)
    template = COPYWRITING_TEMPLATES.get(intent, COPYWRITING_TEMPLATES['standard'])
    
    # Извлекаем данные из ключевых слов
    destination = next((w.title() for w in kws if w in ['паттайя', 'пхукет', 'тайланд', 'вьетнам', 'нячанг', 'китай', 'дубай', 'египет', 'турция', 'байкал', 'сочи']), 'Экзотическое направление')
    
    # Месяц
    month_map = {'апрель': 'апреле', 'май': 'мае', 'июнь': 'июне', 'июль': 'июле', 'август': 'августе'}
    month = next((m for k, m in month_map.items() if k in kws), 'этом сезоне')
    
    # Цена
    price = next((w for w in kws if w.isdigit() and int(w) > 1000), '50 000')
    if price.isdigit():
        price = f"{int(price):,}".replace(',', ' ')
    
    # Эмоция
    emotion_map = {'вау': 'НАСТОЯЩЕЕ ПРИКЛЮЧЕНИЕ', 'горящий': 'ШОК-ПРЕДЛОЖЕНИЕ', 'акция': 'ВЫГОДНЫЙ МОМЕНТ'}
    emotion = next((e for k, e in emotion_map.items() if k in kws), 'НЕЗАБЫВАЕМОЕ ПРИКЛЮЧЕНИЕ')
    
    # Отель
    stars = next((w for w in kws if w in ['5*', '4*', '3*']), '4*')
    food = 'Все включено' if 'все включено' in kws or 'all inclusive' in kws else 'Завтраки'
    
    # Генерируем текст
    headline = random.choice(template['headline']).format(
        destination=destination, 
        emotion=emotion,
        price=price
    )
    
    body = random.choice(template['body']).format(
        destination=destination,
        experience=emotion.lower(),
        month=month
    )
    
    benefits = "\n".join([
        b.format(stars=stars, food=food, bonus='экспресс-оформление', date='конца недели')
        for b in template['benefits'][:4]
    ])
    
    cta = random.choice(template['cta']).format(
        price=price,
        phone='+7 (XXX) XXX-XX-XX',
        username='triumf_irkutsk',
        date='3 дней',
        count='3',
        destination=destination
    )
    
    # Собираем финальный текст (HTML форматирование)
    result = f"{headline}\n\n{body}\n\n{benefits}\n\n{cta}"
    
    return result

def add_smart_emojis(text, theme, density):
    """Добавляет эмодзи ТОЛЬКО в начало строк, не заменяя слова"""
    if not text:
        return ""
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
            result.append(line)
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
    if not text:
        return ""
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
    if not do_highlight or not text:
        return text
    words = ['важно', 'срочно', 'бесплатно', 'акция', 'скидка', 'горящий', 'только сейчас', 'успейте', 'цена', 'руб', 'вылет', 'дата', 'места', 'осталось', 'новинка', 'хит', 'подарок', 'бонус', 'все включено', 'завтраки', 'перелет', 'трансфер', 'виза']
    for word in words:
        # HTML форматирование
        text = re.sub(r'\b(' + re.escape(word) + r')\b', r'<b>\1</b>', text, flags=re.IGNORECASE)
    return text

def smart_format_text(original_text, variant_index):
    if not original_text:
        return {"text": "", "style_name": "None", "detected_theme": "None"}
    
    # 🔹 ВАЖНО: Сначала чистим старые эмодзи!
    clean_text = remove_emojis(original_text)
    # Также чистим возможное форматирование
    clean_text = remove_formatting(clean_text)
    
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
            # Заголовок жирным (HTML)
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
