# -*- coding: utf-8 -*-
import random
import re

EMOJI_POOLS = {
    'travel': ['✈️', '🌍', '🗺️', '🏖️', '🏔️', '🌅', '🧳', '📸'],
    'food': ['🍽️', '🥘', '🍜', '🍣', '🍕', '🍰', '☕', '🍷'],
    'nature': ['🌸', '🌺', '🌻', '🌿', '🌲', '🍀', '🦋', '🐝'],
    'tech': ['💻', '📱', '⌨️', '🖱️', '📷', '🎧', '🔋', '💾'],
    'art': ['🎨', '🖌️', '🎭', '🎬', '🎵', '📖', '🎪', '🎯'],
    'business': ['💼', '📊', '📈', '💰', '🏦', '📋', '📝', '🏢'],
    'sport': ['⚽', '🏀', '🎾', '🏊', '🚴', '🏋️', '🥇', '🏆'],
    'default': ['🌟', '✨', '💫', '⭐', '🔥', '💥', '💯', '🎯'],
}

TEXT_STYLES = ['informative', 'emotional', 'friendly', 'creative', 'energetic']

def get_available_styles():
    return TEXT_STYLES

def remove_emojis(text: str) -> str:
    emoji_pattern = re.compile("["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub('', text)

def remove_formatting(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()

def detect_topic(text: str) -> str:
    text_lower = text.lower()
    topics = {
        'travel': ['путешествие', 'тур', 'отель', 'страна', 'море', 'пляж', 'вьетнам', 'тайланд', 'турция'],
        'food': ['еда', 'ресторан', 'кафе', 'блюдо', 'кухня', 'вкус', 'завтрак', 'обед'],
        'nature': ['природа', 'лес', 'горы', 'река', 'парк', 'цветы', 'животные'],
        'tech': ['технологии', 'компьютер', 'телефон', 'интернет', 'сайт', 'приложение'],
        'art': ['искусство', 'музыка', 'кино', 'театр', 'выставка', 'концерт'],
        'business': ['бизнес', 'работа', 'офис', 'проект', 'клиент', 'услуга', 'компания'],
        'sport': ['спорт', 'фитнес', 'тренировка', 'бег', 'футбол', 'йога'],
    }
    for topic, keywords in topics.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return 'default'

def smart_format_text(text: str, variant: int = 0, emoji_variant: int = 0):
    if not text:
        return {'text': '', 'emoji_variant': emoji_variant}
    
    topic = detect_topic(text)
    pool_keys = list(EMOJI_POOLS.keys())
    
    if emoji_variant > 0:
        pool_index = (emoji_variant - 1) % len(pool_keys)
        emojis = EMOJI_POOLS[pool_keys[pool_index]]
    else:
        emojis = EMOJI_POOLS.get(topic, EMOJI_POOLS['default'])
    
    paragraphs = text.split('\n\n')
    formatted = []
    
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        
        emoji = random.choice(emojis[:4])
        
        # Выделяем ключевые слова жирным
        important = ['важно', 'внимание', 'акция', 'скидка', 'новый', 'лучший', 'топ', 'бесплатно']
        for word in important:
            para = re.sub(rf'\b({word})\b', r'<b>\1</b>', para, flags=re.IGNORECASE)
        
        formatted.append(f"{emoji} {para}")
    
    return {'text': '\n\n'.join(formatted), 'emoji_variant': emoji_variant}

def generate_ai_text(keywords: str, style: str = 'informative'):
    """Генерирует ИНФОРМАТИВНЫЙ текст по ключевым словам"""
    
    # Разбиваем ключевые слова на темы
    kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
    main_topic = kw_list[0] if kw_list else keywords
    
    templates = {
        'informative': f"""📋 **Всё о {main_topic}**

{main_topic} — важная тема, которая требует внимания.

🔹 **Ключевые аспекты:**
• {', '.join(kw_list[:3]) if len(kw_list) > 1 else 'Детальное рассмотрение'}
• Практическое применение
• Рекомендации экспертов

📌 **Важно знать:**
Информация актуальна и проверена. Сохраняйте для использования!

💡 Подробнее изучайте тему через дополнительные источники.""",

        'emotional': f"""🔥 **{main_topic} — это потрясающе!**

Вы только представьте: {main_topic} может изменить всё!

💖 **Почему это важно:**
• Эмоции зашкаливают
• Впечатления на всю жизнь
• Момент, который нельзя пропустить

✨ {', '.join(kw_list[1:3]) if len(kw_list) > 1 else 'Не упустите шанс!'}

🎉 Действуйте сейчас!""",

        'friendly': f"""👋 **Привет! Поговорим про {main_topic}?**

Друзья, сегодня у нас интересная тема — {main_topic}.

😊 **Что интересного:**
• {', '.join(kw_list[:2]) if len(kw_list) > 1 else 'Много полезного'}
• Личный опыт и советы
• Ответы на вопросы

💬 Пишите в комментариях своё мнение!

📝 Ждём ваши истории!""",

        'creative': f"""🎨 **{main_topic} в новом свете!**

А что если посмотреть на {main_topic} иначе?

✨ **Неожиданные грани:**
• Творческий подход
• Нестандартные решения
• Креативные идеи

🌈 {', '.join(kw_list[1:3]) if len(kw_list) > 1 else 'Вдохновляйтесь!'}

🎭 Будьте креативными!""",

        'energetic': f"""⚡ **{main_topic} — ПОЕХАЛИ!**

Врываемся в тему {main_topic}!

🔥 **Что будет:**
• Драйв и энергия
• Максимум пользы
• Только вперёд

🎯 {', '.join(kw_list[:2]) if len(kw_list) > 1 else 'Результат гарантирован!'}

🚀 Погнали!""",
    }
    
    return templates.get(style, templates['informative'])
