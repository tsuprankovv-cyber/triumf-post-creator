# -*- coding: utf-8 -*-
import random
import re

# === ПУЛЫ ЭМОДЗИ ПО КАТЕГОРИЯМ ===
EMOJI_POOLS = {
    'stars': ['🌟', '✨', '💫', '⭐', '🌠', '💖', '🔮', '🎇'],
    'fire': ['🔥', '💥', '💯', '🎯', '⚡', '🚀', '💢', '🆔'],
    'pins': ['📍', '📌', '📎', '🏷️', '🔖', '📑', '🗂️', '📇'],
    'check': ['✅', '✔️', '☑️', '🆗', '👌', '👍', '🙆', '🆒'],
    'art': ['🎨', '🖌️', '🖍️', '✏️', '📝', '📖', '📚', '🎭'],
    'travel': ['✈️', '🌍', '🗺️', '🧭', '🏔️', '🏖️', '🌅', '🎒'],
    'food': ['🍽️', '🥘', '🍜', '🍱', '🍣', '🍙', '🍚', '🍢'],
    'nature': ['🌸', '🌺', '🌻', '🌼', '🌷', '🍀', '🌿', '🌲'],
    'animals': ['🐾', '🦋', '🐝', '🐞', '🐠', '🐬', '🦄', '🐲'],
    'tech': ['💻', '📱', '⌨️', '🖱️', '📷', '🎧', '🔋', '💾'],
}

# === СТИЛИ ТЕКСТА ===
TEXT_STYLES = [
    'informative',    # Информационный
    'emotional',      # Эмоциональный
    'friendly',       # Дружеский
    'official',       # Официальный
    'creative',       # Креативный
    'minimal',        # Минималистичный
    'energetic',      # Энергичный
    'calm',           # Спокойный
]

def get_available_styles():
    """Возвращает список доступных стилей"""
    return TEXT_STYLES

def remove_emojis(text: str) -> str:
    """Удаляет все эмодзи из текста"""
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
    return emoji_pattern.sub('', text)

def remove_formatting(text: str) -> str:
    """Удаляет HTML/Markdown форматирование"""
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    # Удаляем Markdown
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic*
    text = re.sub(r'__([^_]+)__', r'\1', text)      # __underline__
    text = re.sub(r'~~([^~]+)~~', r'\1', text)      # ~~strikethrough~~
    text = re.sub(r'`([^`]+)`', r'\1', text)        # `code`
    return text.strip()

def smart_format_text(text: str, variant: int = 0, emoji_variant: int = 0):
    """
    Форматирует текст с умным подбором эмодзи.
    
    Args:
        text: Исходный текст
        variant: Вариант форматирования (0 = авто)
        emoji_variant: Вариант подбора эмодзи (0 = авто, 1+ = конкретный пул)
    
    Returns:
        dict: {'text': formatted_text, 'emoji_variant': emoji_variant}
    """
    if not text:
        return {'text': '', 'emoji_variant': emoji_variant}
    
    # Разбиваем текст на абзацы
    paragraphs = text.split('\n\n')
    formatted_paragraphs = []
    
    # Определяем тему текста для подбора эмодзи
    topic = detect_topic(text)
    
    # Выбираем пул эмодзи
    if emoji_variant > 0:
        # Конкретный пул по номеру (по кругу)
        pool_keys = list(EMOJI_POOLS.keys())
        pool_index = (emoji_variant - 1) % len(pool_keys)
        emojis = EMOJI_POOLS[pool_keys[pool_index]]
    else:
        # Авто-подбор по теме
        emojis = EMOJI_POOLS.get(topic, EMOJI_POOLS['stars'])
    
    # Форматируем каждый абзац
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        
        # Добавляем эмодзи в начало абзаца
        if i == 0:
            # Первый абзац — заголовочный эмодзи
            emoji = random.choice(emojis[:3])
            para = f"{emoji} {para}"
        else:
            # Остальные абзацы — маркеры
            emoji = random.choice(emojis[3:6]) if len(emojis) > 3 else random.choice(emojis)
            para = f"{emoji} {para}"
        
        # Добавляем форматирование для ключевых слов
        para = format_keywords(para)
        
        formatted_paragraphs.append(para)
    
    # Собираем текст
    formatted_text = '\n\n'.join(formatted_paragraphs)
    
    return {'text': formatted_text, 'emoji_variant': emoji_variant}

def detect_topic(text: str) -> str:
    """
    Определяет тему текста для подбора эмодзи.
    
    Args:
        text: Текст для анализа
    
    Returns:
        str: Ключ темы (stars, travel, food, nature, etc.)
    """
    text_lower = text.lower()
    
    # Ключевые слова для каждой темы
    topic_keywords = {
        'travel': ['путешествие', 'тур', 'отель', 'билет', 'страна', 'город', 'море', 'пляж', 'экскурсия', 'турция', 'египет', 'тайланд', 'байкал', 'москва', 'питер'],
        'food': ['еда', 'ресторан', 'кафе', 'меню', 'блюдо', 'вкус', 'кухня', 'повар', 'завтрак', 'обед', 'ужин', 'пицца', 'суши', 'бургер'],
        'nature': ['природа', 'лес', 'горы', 'река', 'озеро', 'парк', 'сад', 'цветы', 'деревья', 'животные', 'птицы', 'рыбы'],
        'tech': ['технологии', 'компьютер', 'телефон', 'интернет', 'сайт', 'приложение', 'программа', 'код', 'данные', 'сервер'],
        'art': ['искусство', 'музыка', 'кино', 'театр', 'выставка', 'концерт', 'спектакль', 'фильм', 'книга', 'картина'],
        'sport': ['спорт', 'фитнес', 'тренировка', 'бег', 'плавание', 'футбол', 'баскетбол', 'йога', 'зал', 'турнир'],
        'business': ['бизнес', 'работа', 'офис', 'менеджер', 'проект', 'клиент', 'заказ', 'услуга', 'компания', 'продажи'],
        'education': ['обучение', 'курс', 'школа', 'университет', 'урок', 'знания', 'студент', 'преподаватель', 'экзамен'],
    }
    
    # Подсчитываем совпадения по темам
    topic_scores = {}
    for topic, keywords in topic_keywords.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            topic_scores[topic] = score
    
    # Возвращаем тему с наибольшим количеством совпадений
    if topic_scores:
        return max(topic_scores, key=topic_scores.get)
    
    # По умолчанию — звёзды
    return 'stars'

def format_keywords(text: str) -> str:
    """
    Добавляет форматирование для ключевых слов.
    
    Args:
        text: Текст для форматирования
    
    Returns:
        str: Текст с форматированием
    """
    # Ключевые слова для выделения жирным
    important_words = [
        'важно', 'внимание', 'акция', 'скидка', 'бесплатно', 'новый',
        'лучший', 'топ', 'хит', 'премиум', 'эксклюзив', 'ограничено'
    ]
    
    for word in important_words:
        # Выделяем жирным (независимо от регистра)
        pattern = re.compile(rf'\b({word})\b', re.IGNORECASE)
        text = pattern.sub(r'<b>\1</b>', text)
    
    return text

def generate_ai_text(keywords: str, style: str = 'informative'):
    """
    Генерирует текст на основе ключевых слов.
    Каждый вызов генерирует НОВЫЙ уникальный текст!
    
    Args:
        keywords: Ключевые слова/тема
        style: Стиль текста (informative, emotional, friendly, etc.)
    
    Returns:
        str: Сгенерированный текст
    """
    # Шаблоны для разных стилей
    templates = {
        'informative': [
            f"📋 **Информация по теме: {keywords}**\n\n"
            f"В этом материале мы рассмотрим ключевые аспекты темы «{keywords}».\n\n"
            f"🔹 Основные моменты:\n"
            f"• Детальное описание и характеристики\n"
            f"• Преимущества и особенности\n"
            f"• Рекомендации по использованию\n\n"
            f"📌 Подробнее в нашем материале!",
            
            f"📝 **Обзор: {keywords}**\n\n"
            f"Сегодня говорим о важной теме — {keywords}.\n\n"
            f"✅ Что нужно знать:\n"
            f"• Актуальная информация\n"
            f"• Практические советы\n"
            f"• Полезные рекомендации\n\n"
            f"💡 Сохраняйте себе!",
            
            f"📖 **Всё о {keywords}**\n\n"
            f"Полный гид по теме {keywords}.\n\n"
            f"📊 Содержание:\n"
            f"• Введение в тему\n"
            f"• Ключевые особенности\n"
            f"• Итоговые выводы\n\n"
            f"🔔 Читайте до конца!",
        ],
        
        'emotional': [
            f"🔥 **{keywords} — это невероятно!**\n\n"
            f"Вы только представьте: {keywords} может изменить всё!\n\n"
            f"💖 Почему это так важно:\n"
            f"• Эмоции зашкаливают\n"
            f"• Впечатления на всю жизнь\n"
            f"• Момент, который нельзя пропустить\n\n"
            f"✨ Не упустите свой шанс!",
            
            f"💫 **{keywords} — ваша мечта реальна!**\n\n"
            f"Мы знаем, как вы этого ждали! {keywords} уже здесь.\n\n"
            f"🌟 Что вас ждёт:\n"
            f"• Незабываемые ощущения\n"
            f"• Яркие моменты\n"
            f"• Положительные эмоции\n\n"
            f"🎉 Пора действовать!",
            
            f"🎯 **{keywords} — то, что вы искали!**\n\n"
            f"Именно это вы хотели узнать про {keywords}!\n\n"
            f"❤️ Почему стоит обратить внимание:\n"
            f"• Это именно то, что нужно\n"
            f"• Превосходит ожидания\n"
            f"• Стоит каждого момента\n\n"
            f"🚀 Вперёд к новому!",
        ],
        
        'friendly': [
            f"👋 **Привет! Поговорим про {keywords}?**\n\n"
            f"Друзья, сегодня у нас интересная тема — {keywords}.\n\n"
            f"😊 Что интересного:\n"
            f"• Простым языком о сложном\n"
            f"• Личный опыт и советы\n"
            f"• Ответы на ваши вопросы\n\n"
            f"💬 Пишите в комментариях!",
            
            f"🤗 **{keywords} — разбираемся вместе!**\n\n"
            f"Ребята, давайте обсудим {keywords}.\n\n"
            f"📌 План такой:\n"
            f"• Делимся опытом\n"
            f"• Задаём вопросы\n"
            f"• Помогаем друг другу\n\n"
            f"🙌 Присоединяйтесь к обсуждению!",
            
            f"☕ **{keywords} за чашечкой кофе**\n\n"
            f"Устроимся поуютнее и поговорим про {keywords}.\n\n"
            f"🍀 Что обсудим:\n"
            f"• Личные истории\n"
            f"• Полезные лайфхаки\n"
            f"• Дружеские советы\n\n"
            f"📝 Ждём ваши мнения!",
        ],
        
        'official': [
            f"📄 **Официальная информация: {keywords}**\n\n"
            f"Уважаемые пользователи, представляем информацию по теме {keywords}.\n\n"
            f"📋 Основные положения:\n"
            f"• Официальные данные\n"
            f"• Утверждённые рекомендации\n"
            f"• Действующие нормы\n\n"
            f"ℹ️ Для вопросов обращайтесь в поддержку.",
            
            f"🏢 **{keywords} — официальное сообщение**\n\n"
            f"Информируем вас о теме {keywords}.\n\n"
            f"📊 Содержание:\n"
            f"• Официальная позиция\n"
            f"• Установленные правила\n"
            f"• Контактная информация\n\n"
            f"📧 По вопросам: support@example.com",
        ],
        
        'creative': [
            f"🎨 **{keywords} в новом свете!**\n\n"
            f"А что если посмотреть на {keywords} иначе?\n\n"
            f"✨ Неожиданные грани:\n"
            f"• Творческий подход\n"
            f"• Нестандартные решения\n"
            f"• Креативные идеи\n\n"
            f"🌈 Вдохновляйтесь!",
            
            f"🚀 **{keywords} — за гранью возможного!**\n\n"
            f"{keywords} может быть совсем другим!\n\n"
            f"💡 Инновационный взгляд:\n"
            f"• Свежие идеи\n"
            f"• Уникальные решения\n"
            f"• Творческое мышление\n\n"
            f"🎭 Будьте креативными!",
        ],
        
        'minimal': [
            f"**{keywords}**\n\n"
            f"Кратко о главном.\n\n"
            f"• Суть\n"
            f"• Факты\n"
            f"• Итог\n\n"
            f"📌 Сохраните.",
            
            f"**{keywords}**\n\n"
            f"Только важное.\n\n"
            f"• Главное\n"
            f"• Детали\n"
            f"• Вывод\n\n"
            f"✓ Готово.",
        ],
        
        'energetic': [
            f"⚡ **{keywords} — ПОЕХАЛИ!**\n\n"
            f"Врываемся в тему {keywords}!\n\n"
            f"🔥 Что будет:\n"
            f"• Драйв и энергия\n"
            f"• Максимум пользы\n"
            f"• Только вперёд\n\n"
            f"🚀 Погнали!",
            
            f"💥 **{keywords} — ЗАЖИГАЕМ!**\n\n"
            f"{keywords} на полной мощности!\n\n"
            f"🎯 План действий:\n"
            f"• Быстро и чётко\n"
            f"• Эффективно\n"
            f"• Результативно\n\n"
            f"🏆 К победе!",
        ],
        
        'calm': [
            f"🌿 **{keywords} — спокойно о важном**\n\n"
            f"Не спеша разберём тему {keywords}.\n\n"
            f"☕ Что обсудим:\n"
            f"• Без суеты\n"
            f"• По делу\n"
            f"• С пониманием\n\n"
            f"🍃 Наслаждайтесь процессом.",
            
            f"🌸 **{keywords} — гармония и польза**\n\n"
            f"Мягко и подробно о {keywords}.\n\n"
            f"🕊️ В программе:\n"
            f"• Спокойный тон\n"
            f"• Полезная информация\n"
            f"• Приятное чтение\n\n"
            f"🌼 Отдыхайте с пользой.",
        ],
    }
    
    # Выбираем шаблоны для стиля
    style_templates = templates.get(style, templates['informative'])
    
    # Выбираем СЛУЧАЙНЫЙ шаблон (каждый раз новый!)
    selected_template = random.choice(style_templates)
    
    # Дополнительные вариации (рандомизация)
    variations = [
        # Добавляем случайные вставки
        lambda t: t.replace('📌', random.choice(['📌', '💡', '🔔', '⭐'])),
        lambda t: t.replace('✅', random.choice(['✅', '✔️', '👌', '🆗'])),
        lambda t: t.replace('🔥', random.choice(['🔥', '⚡', '💥', '🚀'])),
    ]
    
    # Применяем случайные вариации
    result = selected_template
    for variation in random.sample(variations, k=random.randint(1, len(variations))):
        result = variation(result)
    
    return result
