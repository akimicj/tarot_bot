import hashlib
import re
from datetime import date, datetime

TAROT_CARDS = [
    "Шут", "Маг", "Жрица", "Императрица", "Император", "Иерофант",
    "Влюблённые", "Колесница", "Сила", "Отшельник", "Колесо Фортуны", "Справедливость",
    "Повешенный", "Смерть", "Умеренность", "Дьявол", "Башня", "Звезда",
    "Луна", "Солнце", "Суд", "Мир"
]

DAY_THEMES = [
    "собрать энергию и не расплескать её",
    "сделать один важный шаг без суеты",
    "разобраться в чувствах и расставить акценты",
    "не спорить с хаосом, а использовать его",
    "навести порядок в делах и мыслях",
    "поймать удачный момент и не упустить его",
    "укрепить позиции и не спешить",
    "почувствовать людей вокруг и выбрать точный тон",
    "закрыть старый вопрос и освободить место новому",
    "не торопить события и дать форме созреть",
]

ENERGY_STATES = [
    "энергия ровная, без резких провалов",
    "энергия на подъёме, особенно в первой половине дня",
    "энергия волнами, лучше работать короткими рывками",
    "энергия тихая, но очень точная",
    "энергия сильная, но требует дисциплины",
    "энергия нестабильная, зато творческая",
    "энергия собранная и практичная",
    "энергия мягкая, но с хорошим внутренним импульсом",
]

CHALLENGES = [
    "главная ловушка дня — лишняя спешка",
    "осторожнее с недосказанностью",
    "не провоцируй лишние конфликты",
    "не бери на себя больше, чем реально потянешь",
    "не позволяй чужому настроению сбить твой ритм",
    "риск дня — распыление внимания",
    "не делай выводов на эмоциях",
    "слишком резкий тон может испортить полезный контакт",
]

OPPORTUNITIES = [
    "лучший шанс дня — один честный разговор",
    "сильная точка дня — завершить старое дело",
    "полезно закрепить договорённость",
    "можно получить маленькую, но важную победу",
    "удачно зайдёт обучение или сбор информации",
    "хороший момент для примирения",
    "день подходит для аккуратного прорыва",
    "может открыться путь, который раньше был незаметен",
]

LOVE = [
    "в отношениях важны мягкость и честность",
    "симпатия проявится через внимание к деталям",
    "не дави на чувства — сегодня работает деликатность",
    "в личном лучше меньше загадок и больше ясности",
    "день подходит для тёплого контакта и примирения",
    "в любви важнее слушать, чем доказывать",
    "может проявиться скрытый интерес или знак внимания",
    "лучше говорить о конкретике, а не о догадках",
]

WORK = [
    "в работе лучше двигаться по одному приоритету",
    "день хорош для задач, где нужна точность",
    "подходит для переговоров и согласований",
    "можно закрыть зависший рабочий вопрос",
    "не распыляйся на лишние переписки",
    "хорошо идут планирование и аналитика",
    "день помогает тем, кто действует спокойно и последовательно",
    "полезно проверить детали перед отправкой результата",
]

MONEY = [
    "по деньгам лучше без импульсивных трат",
    "денежный поток стабилен, если не торопиться",
    "сегодня полезно пересмотреть расходы",
    "неплохой день для практичной покупки",
    "может прийти небольшая выгода из старой идеи",
    "день не про риск, а про сохранение",
    "финансовый шанс связан с дисциплиной",
    "лучше опираться на проверенные решения",
]

ADVICE = [
    "выбери одну цель и держи курс до вечера",
    "не спорь с тем, что уже идёт своим путём",
    "сделай паузу перед важным ответом",
    "проверяй факты, а не только ощущения",
    "действуй спокойно, но не откладывай главное",
    "сегодня побеждает не скорость, а точность",
    "береги внимание — это твой главный ресурс дня",
    "сначала порядок, потом импульс",
]

RITUALS = [
    "утром выпей воды и сформулируй один главный запрос дня",
    "на 5 минут убери лишнее со стола и почувствуй, как меняется настрой",
    "запиши 3 задачи, но выполни сначала одну",
    "перед важным делом сделай 7 спокойных вдохов",
    "отметь один завершённый шаг, даже если он маленький",
    "в середине дня выйди на короткую прогулку и сбрось шум",
    "перед началом работы открой план и выдели главное",
    "вечером запиши, что сегодня действительно сработало",
]

MANTRAS = [
    "Я выбираю ясность.",
    "Я двигаюсь спокойно и точно.",
    "Я слышу свой ритм.",
    "Я не теряю силу в суете.",
    "Я замечаю шанс и беру его вовремя.",
    "Я остаюсь собранным и внимательным.",
    "Я доверяю точному шагу.",
    "Я удерживаю фокус.",
]

COLORS = [
    "синий", "зелёный", "чёрный", "белый", "фиолетовый",
    "золотой", "серый", "бордовый", "лазурный", "песочный"
]

TIMINGS = [
    "утро", "первая половина дня", "день", "после обеда",
    "вечер", "поздний вечер"
]

PLACE_HINTS = [
    "место рождения усиливает практичность и умение собирать детали",
    "место рождения даёт сильную интуитивную реакцию на людей",
    "место рождения помогает быстро чувствовать перемены в атмосфере",
    "место рождения добавляет внутреннюю выносливость и терпение",
    "место рождения делает заметной тягу к точным решениям",
    "место рождения усиливает способность подмечать скрытое",
]

ZODIAC_ELEMENTS = {
    "Овен": "Огонь",
    "Телец": "Земля",
    "Близнецы": "Воздух",
    "Рак": "Вода",
    "Лев": "Огонь",
    "Дева": "Земля",
    "Весы": "Воздух",
    "Скорпион": "Вода",
    "Стрелец": "Огонь",
    "Козерог": "Земля",
    "Водолей": "Воздух",
    "Рыбы": "Вода",
}


def normalize_text(value: str) -> str:
    value = value or ""
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def zodiac_sign(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    md = d.month * 100 + d.day

    boundaries = [
        (119, "Козерог"),
        (218, "Водолей"),
        (320, "Рыбы"),
        (419, "Овен"),
        (520, "Телец"),
        (620, "Близнецы"),
        (722, "Рак"),
        (822, "Лев"),
        (922, "Дева"),
        (1022, "Весы"),
        (1121, "Скорпион"),
        (1221, "Стрелец"),
        (1231, "Козерог"),
    ]

    for limit, sign in boundaries:
        if md <= limit:
            return sign
    return "Козерог"


def zodiac_element(sign: str) -> str:
    return ZODIAC_ELEMENTS.get(sign, "—")


def _reduce_number(n: int) -> int:
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(ch) for ch in str(n))
    return n


def life_path_number(date_str: str) -> int:
    digits = [int(ch) for ch in date_str if ch.isdigit()]
    total = sum(digits)
    return _reduce_number(total)


def day_code(reading_date: date) -> int:
    return sum(int(ch) for ch in reading_date.strftime("%d%m%Y") if ch.isdigit())


def day_arcana(reading_date: date) -> int:
    code = day_code(reading_date)
    return code % 22 or 22


def profile_signature(user) -> str:
    parts = [
        normalize_text(user["birth_date"] or ""),
        normalize_text(user["birth_time"] or ""),
        normalize_text(user["birth_place"] or ""),
    ]
    return "|".join(parts)


def _digest_for(user, reading_date: date) -> str:
    payload = f"{profile_signature(user)}|{reading_date.isoformat()}|{day_code(reading_date)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() * 4


def _pair_digest(user_a, user_b, reading_date: date) -> str:
    sigs = sorted([profile_signature(user_a), profile_signature(user_b)])
    payload = f"{sigs[0]}||{sigs[1]}|{reading_date.isoformat()}|{day_code(reading_date)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() * 4


def _pick(pool: str, offset: int, options: list[str]) -> str:
    chunk = pool[offset:offset + 8]
    if not chunk:
        chunk = pool[:8]
    idx = int(chunk, 16) % len(options)
    return options[idx]


def _pick_number(pool: str, offset: int, minimum: int, maximum: int) -> int:
    span = maximum - minimum + 1
    chunk = pool[offset:offset + 8]
    if not chunk:
        chunk = pool[:8]
    return minimum + (int(chunk, 16) % span)


def generate_daily_reading(user, reading_date: date) -> dict:
    pool = _digest_for(user, reading_date)

    zodiac = zodiac_sign(user["birth_date"]) if user["birth_date"] else "—"
    life_number = life_path_number(user["birth_date"]) if user["birth_date"] else None
    element = zodiac_element(zodiac) if zodiac != "—" else "—"

    return {
        "card": _pick(pool, 0, TAROT_CARDS),
        "theme": _pick(pool, 8, DAY_THEMES),
        "energy": _pick(pool, 16, ENERGY_STATES),
        "challenge": _pick(pool, 24, CHALLENGES),
        "opportunity": _pick(pool, 32, OPPORTUNITIES),
        "love": _pick(pool, 40, LOVE),
        "work": _pick(pool, 48, WORK),
        "money": _pick(pool, 56, MONEY),
        "advice": _pick(pool, 64, ADVICE),
        "ritual": _pick(pool, 72, RITUALS),
        "mantra": _pick(pool, 80, MANTRAS),
        "color": _pick(pool, 88, COLORS),
        "timing": _pick(pool, 96, TIMINGS),
        "luck": _pick_number(pool, 104, 45, 99),
        "focus": _pick_number(pool, 112, 40, 99),
        "social": _pick_number(pool, 120, 35, 99),
        "intuition": _pick_number(pool, 128, 45, 99),
        "birth_place_hint": _pick(pool, 136, PLACE_HINTS),
        "day_code": day_code(reading_date),
        "day_arcana": day_arcana(reading_date),
        "zodiac": zodiac,
        "zodiac_element": element,
        "life_path_number": life_number,
        "personal_arcana": int(user["personal_arcana"] or 0),
    }


def generate_pair_reading(user_a, user_b, reading_date: date) -> dict:
    pool = _pair_digest(user_a, user_b, reading_date)

    sign_a = zodiac_sign(user_a["birth_date"]) if user_a["birth_date"] else "—"
    sign_b = zodiac_sign(user_b["birth_date"]) if user_b["birth_date"] else "—"
    element_a = zodiac_element(sign_a) if sign_a != "—" else "—"
    element_b = zodiac_element(sign_b) if sign_b != "—" else "—"

    score = 50 + (int(pool[:4], 16) % 41)
    if sign_a != "—" and sign_a == sign_b:
        score += 5
    if element_a != "—" and element_a == element_b:
        score += 3
    score = min(score, 99)

    return {
        "score": score,
        "theme": _pick(pool, 0, [
            "лёгкий контакт и важный внутренний отклик",
            "совместное движение к общему результату",
            "разговор, который многое прояснит",
            "проверка на терпение и взаимное уважение",
            "день, где важны ясные роли и мягкость",
            "сильный шанс услышать друг друга точнее",
        ]),
        "strength": _pick(pool, 8, [
            "общая цель",
            "умение договориться",
            "эмоциональная поддержка",
            "быстрый обмен идеями",
            "взаимная интуиция",
            "практичная помощь",
        ]),
        "risk": _pick(pool, 16, [
            "спешные выводы",
            "резкий тон",
            "недосказанность",
            "разные ожидания",
            "лишняя гордость",
            "перетягивание внимания на себя",
        ]),
        "advice": _pick(pool, 24, [
            "говорить прямо, но мягко",
            "не спорить о мелочах",
            "оставить место тишине и наблюдению",
            "действовать как команда, а не как соперники",
            "проверять не эмоцию, а факт",
            "сразу уточнять намерения",
        ]),
        "timing": _pick(pool, 32, TIMINGS),
        "chemistry": _pick_number(pool, 40, 40, 99),
        "communication": _pick_number(pool, 48, 40, 99),
        "support": _pick_number(pool, 56, 40, 99),
        "stability": _pick_number(pool, 64, 40, 99),
        "result": _pick(pool, 72, [
            "контакт укрепляется",
            "нужно немного больше ясности",
            "есть потенциал для тёплого сближения",
            "лучше не торопить развитие",
            "связь может дать полезный поворот",
            "день подходит для честного шага навстречу",
        ]),
        "day_code": day_code(reading_date),
        "day_arcana": day_arcana(reading_date),
        "sign_a": sign_a,
        "sign_b": sign_b,
        "element_a": element_a,
        "element_b": element_b,
    }