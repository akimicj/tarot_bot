import datetime
import random

def zodiac_sign(date_str):
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d")

    day = d.day
    month = d.month

    signs = [
        (120, "Козерог"), (218, "Водолей"), (320, "Рыбы"),
        (420, "Овен"), (521, "Телец"), (621, "Близнецы"),
        (723, "Рак"), (823, "Лев"), (923, "Дева"),
        (1023, "Весы"), (1122, "Скорпион"), (1222, "Стрелец"),
        (1231, "Козерог")
    ]

    num = month * 100 + day
    for s in signs:
        if num <= s[0]:
            return s[1]

def day_code():
    today = datetime.datetime.now()
    digits = list(map(int, today.strftime("%d%m%Y")))
    return sum(digits)

def day_arcana():
    return day_code() % 22 or 22

def compatibility(user1, user2):
    return (user1[6] + user2[6]) % 100

def generate_extended_reading(user):
    return {
        "text": f"""
🔮 Расширенный расклад

Твой знак: {user[5]}
Твой личный аркан: {user[6]}

Код дня: {day_code()}
Аркан дня: {day_arcana()}

Сегодня энергия требует сосредоточенности.
Избегай конфликтов и не принимай решения на эмоциях.
"""
    }
