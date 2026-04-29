import asyncio
import calendar
import html
import aiosqlite
import logging
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from db import (
    add_tokens,
    get_all_users_for_notifications,
    get_tokens,
    get_user,
    get_user_by_username,
    init_db,
    reset_profile,
    spend_tokens,
    set_birth_date,
    set_birth_place,
    set_birth_time,
    set_last_daily_sent_date,
    set_notify_time,
    set_paid_full_date,
    set_paid_match_date,
    set_subscription_until,
    set_zodiac,
    upsert_user,
)
from horoscope import (
    day_arcana,
    day_code,
    generate_daily_reading,
    generate_pair_reading,
    life_path_number,
    zodiac_element,
    zodiac_sign,
)

BOT_TOKEN = "8539615509:AAGmG2Nimijudxe_sZAW__84hXkpEuCndhk"
ADMIN_ID = 982023162
DEFAULT_TIMEZONE = "Europe/Moscow"
FULL_READING_PRICE = 10
MATCH_PRICE = 15
SUBSCRIPTION_PRICE = 199
SUBSCRIPTION_DAYS = 30
DEFAULT_NOTIFY_TIME = "09:00"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

BOT_USERNAME: str | None = None


class Onboarding(StatesGroup):
    birth_year = State()
    birth_month = State()
    birth_day = State()
    birth_hour = State()
    birth_minute = State()
    birth_place = State()
    match_username = State()


class ScheduleSetup(StatesGroup):
    hour = State()
    minute = State()


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_tokens = State()
    waiting_for_broadcast = State()


# ---------------------------
# Helpers
# ---------------------------

def e(value) -> str:
    return html.escape("" if value is None else str(value))


def is_admin(user_id: int | None) -> bool:
    return user_id == ADMIN_ID


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Меню")]],
        resize_keyboard=True,
    )


def main_menu_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔮 Расклад дня", callback_data="menu:readings"),
            InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton(text="💰 Токены", callback_data="menu:tokens"),
            InlineKeyboardButton(text="🎁 Подписка", callback_data="menu:subscription"),
        ],
        [
            InlineKeyboardButton(text="⏰ Расписание", callback_data="menu:schedule"),
            InlineKeyboardButton(text="👥 Совместимость", callback_data="menu:match"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="menu:about"),
        ],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
            [InlineKeyboardButton(text="💰 Выдать токены", callback_data="admin:give_tokens")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")],
        ]
    )


def back_button(back_cb: str, text: str = "⬅️ Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=back_cb)]
        ]
    )


def one_row_buttons(*buttons: tuple[str, str], back_cb: str | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=t, callback_data=cb) for t, cb in buttons]]
    if back_cb:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def readings_menu_keyboard(user) -> InlineKeyboardMarkup:
    full_free = subscription_active(user) or full_unlocked_today(user, current_local_date(user))
    full_label = "💎 Полный — открыт" if full_free else f"💎 Полный • {FULL_READING_PRICE}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌟 Краткий расклад", callback_data="reading:short"),
                InlineKeyboardButton(text=full_label, callback_data="reading:full"),
            ],
            [
                InlineKeyboardButton(text="🧿 Личная матрица", callback_data="reading:personal"),
                InlineKeyboardButton(text="📅 Код дня", callback_data="reading:daycode"),
            ],
            [
                InlineKeyboardButton(text="👥 Совместимость", callback_data="menu:match"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main"),
            ],
        ]
    )


def tokens_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ 50", callback_data="tokens:buy:50"),
                InlineKeyboardButton(text="➕ 100", callback_data="tokens:buy:100"),
            ],
            [
                InlineKeyboardButton(text="➕ 250", callback_data="tokens:buy:250"),
                InlineKeyboardButton(text="➕ 500", callback_data="tokens:buy:500"),
            ],
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="tokens:balance"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main"),
            ],
        ]
    )


def profile_menu_keyboard(has_profile: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👤 Показать профиль", callback_data="profile:show")],
    ]
    if not has_profile:
        rows.append([InlineKeyboardButton(text="▶️ Продолжить заполнение", callback_data="profile:continue")])
    rows.append([InlineKeyboardButton(text="✏️ Сбросить профиль", callback_data="profile:reset")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def schedule_menu_keyboard(user) -> InlineKeyboardMarkup:
    time_label = user["notify_time"] or "не задано"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Изменить время", callback_data="schedule:set_time")],
            [InlineKeyboardButton(text=f"📍 Время: {time_label}", callback_data="schedule:time_info")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")],
        ]
    )


def subscription_menu_keyboard(user) -> InlineKeyboardMarkup:
    active = subscription_active(user)
    if active:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="sub:cancel_prompt")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🎁 Оформить подписку • {SUBSCRIPTION_PRICE}", callback_data="sub:buy_prompt")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")],
        ]
    )


def confirm_keyboard(confirm_cb: str, back_cb: str, confirm_text: str = "✅ Подтвердить") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=confirm_cb)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)],
        ]
    )


def year_keyboard() -> InlineKeyboardMarkup:
    current_year = datetime.now().year
    years = [(str(y), str(y)) for y in range(current_year, current_year - 101, -1)]
    return make_grid_keyboard("birth_year", years, 3, back_cb="back:main")


def month_keyboard() -> InlineKeyboardMarkup:
    months = [
        ("Янв", "01"), ("Фев", "02"), ("Мар", "03"), ("Апр", "04"),
        ("Май", "05"), ("Июн", "06"), ("Июл", "07"), ("Авг", "08"),
        ("Сен", "09"), ("Окт", "10"), ("Ноя", "11"), ("Дек", "12"),
    ]
    return make_grid_keyboard("birth_month", months, 3, back_cb="back:birth_year")


def days_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    max_day = calendar.monthrange(year, month)[1]
    days = [(str(d).zfill(2), str(d).zfill(2)) for d in range(1, max_day + 1)]
    return make_grid_keyboard("birth_day", days, 7, back_cb="back:birth_month")


def hours_keyboard(prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    hours = [(str(h).zfill(2), str(h).zfill(2)) for h in range(24)]
    return make_grid_keyboard(prefix, hours, 6, back_cb=back_cb)


def minutes_keyboard(prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    minutes = [(str(m).zfill(2), str(m).zfill(2)) for m in range(0, 60, 5)]
    return make_grid_keyboard(prefix, minutes, 6, back_cb=back_cb)


def make_grid_keyboard(prefix: str, values: list[tuple[str, str]], columns: int, back_cb: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(values), columns):
        chunk = values[i:i + columns]
        row = [InlineKeyboardButton(text=text, callback_data=f"{prefix}:{value}") for text, value in chunk]
        rows.append(row)
    if back_cb:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tz_for_user(user) -> timezone:
    tz_name = user["timezone"] or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone(timedelta(hours=3))


def current_local_date(user) -> date_cls:
    return datetime.now(tz_for_user(user)).date()


def pretty_date(value: str | None) -> str:
    if not value:
        return "не задано"
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return d.strftime("%d.%m.%Y")
    except ValueError:
        return value


def pretty_time(value: str | None) -> str:
    return value if value else "не задано"


def pretty_iso_dt(value: str | None) -> str:
    if not value:
        return "не задано"
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.strftime("%d.%m.%Y %H:%M")
        local = dt.astimezone(timezone.utc)
        return local.strftime("%d.%m.%Y %H:%M UTC")
    except Exception:
        return value


def referral_link(user_id: int) -> str | None:
    if not BOT_USERNAME:
        return None
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"


def missing_profile_steps(user) -> list[str]:
    missing = []
    if not user["birth_date"]:
        missing.append("дата рождения")
    if not user["birth_time"]:
        missing.append("время рождения")
    if not user["birth_place"]:
        missing.append("место рождения")
    return missing


def profile_complete(user) -> bool:
    return len(missing_profile_steps(user)) == 0


def subscription_active(user) -> bool:
    if not user or not user["subscription_until"]:
        return False
    try:
        until = datetime.fromisoformat(user["subscription_until"])
        return until > datetime.now(timezone.utc)
    except Exception:
        return False


def full_unlocked_today(user, local_date: date_cls) -> bool:
    return bool(user and user["paid_full_date"] == local_date.isoformat())


def match_unlocked_today(user, local_date: date_cls) -> bool:
    return bool(user and user["paid_match_date"] == local_date.isoformat())


def format_profile(user) -> str:
    zodiac = user["zodiac"] or (zodiac_sign(user["birth_date"]) if user["birth_date"] else "не задан")
    element = zodiac_element(zodiac) if zodiac != "не задан" else "—"
    life_num = life_path_number(user["birth_date"]) if user["birth_date"] else None
    tokens = int(user["tokens"] or 0)
    username = f"@{user['username']}" if user["username"] else "не задан"
    personal_arcana = user["personal_arcana"] or "не задан"
    sub_text = "активна" if subscription_active(user) else "нет"

    text = (
        f"<b>👤 Профиль</b>\n\n"
        f"• <b>Имя:</b> {e(user['name'])}\n"
        f"• <b>Telegram:</b> {e(username)}\n"
        f"• <b>Дата рождения:</b> {pretty_date(user['birth_date'])}\n"
        f"• <b>Время рождения:</b> {pretty_time(user['birth_time'])}\n"
        f"• <b>Место рождения:</b> {e(user['birth_place'] or 'не задано')}\n"
        f"• <b>Знак зодиака:</b> {e(zodiac)}\n"
        f"• <b>Стихия:</b> {e(element)}\n"
        f"• <b>Число пути:</b> {life_num if life_num is not None else 'не задано'}\n"
        f"• <b>Личный аркан:</b> {personal_arcana}\n"
        f"• <b>Токены:</b> {tokens}\n"
        f"• <b>Подписка:</b> {sub_text}\n"
        f"• <b>Время рассылки:</b> {pretty_time(user['notify_time'])}\n"
        f"• <b>Часовой пояс:</b> {e(user['timezone'] or DEFAULT_TIMEZONE)}\n"
    )

    if not profile_complete(user):
        text += "\n<b>Осталось заполнить:</b>\n"
        for item in missing_profile_steps(user):
            text += f"• {e(item)}\n"

    link = referral_link(user["telegram_id"])
    if link:
        text += f"\n<b>Реферальная ссылка:</b>\n{e(link)}\n"

    return text


def format_short_reading(reading, local_date: date_cls) -> str:
    return (
        f"<b>🔮 Краткий расклад на {local_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"🃏 <b>Карта дня:</b> {e(reading['card'])}\n"
        f"🌙 <b>Тема:</b> {e(reading['theme'])}\n"
        f"💡 <b>Совет:</b> {e(reading['advice'])}\n\n"
        f"🔢 <b>Код дня:</b> {reading['day_code']}\n"
        f"🃏 <b>Аркан дня:</b> {reading['day_arcana']}\n"
        f"✨ <b>Личный аркан:</b> {reading['personal_arcana']}\n"
        f"♈ <b>Знак:</b> {e(reading['zodiac'])}\n"
    )


def format_full_reading(reading, local_date: date_cls) -> str:
    return (
        f"<b>🔮 Полный расклад на {local_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"🃏 <b>Карта дня:</b> {e(reading['card'])}\n"
        f"🌙 <b>Тема дня:</b> {e(reading['theme'])}\n"
        f"⚡ <b>Энергия:</b> {e(reading['energy'])}\n"
        f"🪞 <b>Тень:</b> {e(reading['challenge'])}\n"
        f"🌟 <b>Возможность:</b> {e(reading['opportunity'])}\n\n"
        f"💖 <b>Любовь:</b> {e(reading['love'])}\n"
        f"💼 <b>Работа:</b> {e(reading['work'])}\n"
        f"💰 <b>Деньги:</b> {e(reading['money'])}\n\n"
        f"🤝 <b>Контактность:</b> {reading['social']}%\n"
        f"🧠 <b>Интуиция:</b> {reading['intuition']}%\n"
        f"🎯 <b>Фокус:</b> {reading['focus']}%\n"
        f"🍀 <b>Удача:</b> {reading['luck']}%\n\n"
        f"🔢 <b>Код дня:</b> {reading['day_code']} (общий)\n"
        f"🃏 <b>Аркан дня:</b> {reading['day_arcana']} (общий)\n"
        f"✨ <b>Личный аркан:</b> {reading['personal_arcana']}\n"
        f"♈ <b>Знак:</b> {e(reading['zodiac'])}\n"
        f"🧭 <b>Стихия:</b> {e(reading['zodiac_element'])}\n"
        f"🔢 <b>Число пути:</b> {reading['life_path_number'] if reading['life_path_number'] is not None else 'не задано'}\n"
        f"🎨 <b>Цвет дня:</b> {e(reading['color'])}\n"
        f"⏳ <b>Лучшее время:</b> {e(reading['timing'])}\n"
        f"📍 <b>Место рождения:</b> {e(reading['birth_place_hint'])}\n\n"
        f"💬 <b>Совет:</b> {e(reading['advice'])}\n"
        f"🧿 <b>Ритуал:</b> {e(reading['ritual'])}\n"
        f"🗝 <b>Фраза дня:</b> {e(reading['mantra'])}\n"
    )


def format_personal_matrix(user) -> str:
    zodiac = user["zodiac"] or (zodiac_sign(user["birth_date"]) if user["birth_date"] else "не задан")
    element = zodiac_element(zodiac) if zodiac != "не задан" else "—"
    life_num = life_path_number(user["birth_date"]) if user["birth_date"] else None
    personal_arcana = user["personal_arcana"] or "не задан"

    return (
        "<b>🧿 Личная матрица</b>\n\n"
        f"• <b>Знак:</b> {e(zodiac)}\n"
        f"• <b>Стихия:</b> {e(element)}\n"
        f"• <b>Число пути:</b> {life_num if life_num is not None else 'не задано'}\n"
        f"• <b>Личный аркан:</b> {personal_arcana}\n"
        f"• <b>Место рождения:</b> {e(user['birth_place'] or 'не задано')}\n"
    )


def format_day_code_text(local_date: date_cls) -> str:
    code = day_code(local_date)
    arc = day_arcana(local_date)
    return (
        f"<b>📅 Код дня на {local_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"• <b>Код дня:</b> {code}\n"
        f"• <b>Аркан дня:</b> {arc}\n\n"
        f"Этот код одинаков для всех пользователей на эту дату."
    )


def format_match_result(user, other, pair, local_date: date_cls, target_username: str) -> str:
    return (
        f"<b>👥 Совместимость на {local_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"• <b>Ты:</b> {e(user['name'])}\n"
        f"• <b>Партнёр:</b> @{e(target_username)}\n\n"
        f"• <b>Совместимость:</b> {pair['score']}%\n"
        f"• <b>Энергия связки:</b> {e(pair['theme'])}\n"
        f"• <b>Сильная сторона:</b> {e(pair['strength'])}\n"
        f"• <b>Риск:</b> {e(pair['risk'])}\n"
        f"• <b>Лучшее окно:</b> {e(pair['timing'])}\n"
        f"• <b>Коммуникация:</b> {pair['communication']}%\n"
        f"• <b>Химия:</b> {pair['chemistry']}%\n"
        f"• <b>Поддержка:</b> {pair['support']}%\n"
        f"• <b>Стабильность:</b> {pair['stability']}%\n"
        f"• <b>Итог:</b> {e(pair['result'])}\n\n"
        f"• <b>Знак партнёра:</b> {e(pair['sign_b'])}\n"
        f"• <b>Стихия партнёра:</b> {e(pair['element_b'])}\n"
        f"• <b>Код дня:</b> {pair['day_code']}\n"
        f"• <b>Аркан дня:</b> {pair['day_arcana']}\n\n"
        f"• <b>Совет:</b> {e(pair['advice'])}\n"
    )


def format_full_pay_prompt(user, local_date: date_cls) -> str:
    tokens = int(user["tokens"] or 0)
    return (
        f"<b>💎 Полный расклад на сегодня</b>\n\n"
        "Это самый глубокий формат: он показывает не только общий вектор, но и риск, шанс, деньги, отношения и совет.\n\n"
        "Ты увидишь:\n"
        "• где скрыта возможность\n"
        "• что может помешать\n"
        "• на что сделать ставку сегодня\n\n"
        f"• <b>Разовый доступ:</b> {FULL_READING_PRICE} токенов\n"
        f"• <b>Подписка на 30 дней:</b> {SUBSCRIPTION_PRICE} токенов\n"
        f"• <b>Баланс:</b> {tokens}\n\n"
        "Если берёшь полный расклад регулярно, подписка выглядит заметно выгоднее уже в ближайшие дни."
    )


def format_match_pay_prompt(user, target_username: str) -> str:
    tokens = int(user["tokens"] or 0)
    return (
        f"<b>👥 Совместимость</b>\n\n"
        f"Партнёр: @{e(target_username)}\n\n"
        "Этот расчёт покажет, как складывается ваша связка сегодня: где притяжение, где риск и как лучше говорить друг с другом.\n\n"
        f"• <b>Стоимость:</b> {MATCH_PRICE} токенов\n"
        f"• <b>Баланс:</b> {tokens}\n\n"
        "После оплаты расчёт откроется сразу, а в течение этого дня повторно платить не придётся."
    )


def format_subscription_prompt(user) -> str:
    tokens = int(user["tokens"] or 0)
    return (
        f"<b>⭐ Подписка на ежедневный полный расклад</b>\n\n"
        "Каждый день ты получаешь полный разбор автоматически в выбранное время.\n"
        "Без доплат внутри срока, без лишних действий.\n\n"
        f"• <b>Стоимость:</b> {SUBSCRIPTION_PRICE} токенов\n"
        f"• <b>Срок:</b> {SUBSCRIPTION_DAYS} дней\n"
        f"• <b>Баланс:</b> {tokens}\n\n"
        "Подписка особенно выгодна, если ты берёшь полный расклад регулярно."
    )


def format_subscription_menu_text(user) -> str:
    active = subscription_active(user)
    if active:
        return (
            "<b>🎁 Подписка</b>\n\n"
            f"Статус: <b>активна</b>\n"
            f"До: <b>{pretty_iso_dt(user['subscription_until'])}</b>\n"
            f"Время рассылки: <b>{pretty_time(user['notify_time'])}</b>\n\n"
            "Ежедневный полный расклад приходит автоматически и открывает день без дополнительных действий."
        )
    return (
        "<b>🎁 Подписка</b>\n\n"
        "Ежедневный полный расклад в выбранное время.\n"
        f"Срок: <b>{SUBSCRIPTION_DAYS} дней</b>\n"
        f"Стоимость: <b>{SUBSCRIPTION_PRICE} токенов</b>\n\n"
        "Подписка делает ежедневный полный расклад выгоднее, чем разовые покупки."
    )


def admin_stats_text(users: list[dict]) -> str:
    total_users = len(users)
    total_tokens = sum(int(u.get("tokens") or 0) for u in users)
    active_subs = sum(1 for u in users if subscription_active(u))
    complete_profiles = sum(1 for u in users if profile_complete(u))

    return (
        "<b>📊 Статистика проекта</b>\n\n"
        f"• <b>Пользователей:</b> {total_users}\n"
        f"• <b>Всего токенов:</b> {total_tokens}\n"
        f"• <b>Активных подписок:</b> {active_subs}\n"
        f"• <b>Полных профилей:</b> {complete_profiles}\n"
    )


def admin_users_text(users: list[dict], limit: int = 20) -> str:
    active_subs = sum(1 for u in users if subscription_active(u))
    lines = [
        "<b>👥 Пользователи</b>",
        "",
        f"Всего: <b>{len(users)}</b>",
        f"Подписок: <b>{active_subs}</b>",
        "",
    ]

    for u in users[:limit]:
        uid = u.get("telegram_id", "—")
        name = u.get("name") or "не задано"
        username = f"@{u.get('username')}" if u.get("username") else "—"
        tokens = int(u.get("tokens") or 0)
        sub = "⭐" if subscription_active(u) else "—"
        lines.append(f"• <code>{e(uid)}</code> | {e(name)} | {e(username)} | 💰 {tokens} | {sub}")

    if len(users) > limit:
        lines.append("")
        lines.append(f"… и ещё {len(users) - limit}")

    return "\n".join(lines)


async def render(target: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            await target.message.answer(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)


async def safe_answer(message: Message, text: str, reply_markup=None) -> None:
    await message.answer(text, reply_markup=reply_markup)


def parse_ref_payload(message_text: str | None) -> int | None:
    if not message_text:
        return None
    parts = message_text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if not payload.startswith("ref_"):
        return None
    try:
        return int(payload[4:])
    except ValueError:
        return None


async def prepare_subscription_if_needed(user_id: int) -> None:
    user = await get_user(user_id)
    if user and not user["notify_time"]:
        await set_notify_time(user_id, DEFAULT_NOTIFY_TIME)


async def send_main_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    text = (
        "<b>🔮 Твой личный расклад на сегодня</b>\n\n"
        "Каждый день бот собирает новый сценарий на основе твоих данных и текущей даты.\n"
        "Выбирай краткий формат, если нужен быстрый ответ, или полный — если хочешь увидеть глубже.\n\n"
        "✨ Здесь тебя ждут:\n"
        "• настрой дня\n"
        "• сильная точка\n"
        "• зона риска\n"
        "• совет, который стоит взять с собой"
    )
    await render(target, text, main_menu_keyboard(target.from_user.id))


async def send_readings_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await get_user(target.from_user.id)
    text = (
        "<b>🔮 Выбери глубину анализа</b>\n\n"
        "🌟 <b>Краткий</b> — быстрый ориентир на день.\n"
        "💎 <b>Полный</b> — отношения, дела, деньги, риск и шанс.\n"
        "🧿 <b>Личная матрица</b> — твой знак, путь, стихия и аркан.\n"
        "📅 <b>Код дня</b> — общий ритм текущей даты.\n\n"
        "Выбирай то, что нужно прямо сейчас."
    )
    await render(target, text, readings_menu_keyboard(user))


async def send_profile_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await get_user(target.from_user.id)
    if not user:
        await render(target, "Сначала нажми /start.", main_menu_keyboard(target.from_user.id))
        return
    await render(target, format_profile(user), profile_menu_keyboard(profile_complete(user)))


async def send_tokens_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await get_user(target.from_user.id)
    tokens = int(user["tokens"] or 0) if user else 0
    link = referral_link(target.from_user.id)
    text = (
        "<b>💰 Токены</b>\n\n"
        f"Баланс: <b>{tokens}</b>\n\n"
        "Токены открывают полный расклад, совместимость и подписку.\n"
        "Чем выше баланс, тем свободнее можно брать глубину без пауз."
    )
    if link:
        text += f"\n<b>Реферальная ссылка:</b>\n{e(link)}\n"
        text += "Поделись ссылкой и получай бонус за каждого нового пользователя."
    await render(target, text, tokens_menu_keyboard())


async def send_schedule_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await get_user(target.from_user.id)
    if not user:
        await render(target, "Сначала нажми /start.", main_menu_keyboard(target.from_user.id))
        return
    text = (
        "<b>⏰ Расписание</b>\n\n"
        f"Время рассылки: <b>{pretty_time(user['notify_time'])}</b>\n"
        f"Часовой пояс: <b>{e(user['timezone'] or DEFAULT_TIMEZONE)}</b>\n\n"
        "Время можно изменить в любой момент."
    )
    await render(target, text, schedule_menu_keyboard(user))


async def send_subscription_menu(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = await get_user(target.from_user.id)
    if not user:
        await render(target, "Сначала нажми /start.", main_menu_keyboard(target.from_user.id))
        return
    await render(target, format_subscription_menu_text(user), subscription_menu_keyboard(user))


async def send_about(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    text = (
        "<b>ℹ️ О боте</b>\n\n"
        "Бот собирает дату, время и место рождения по согласию пользователя и строит дневные расклады.\n"
        "Есть короткий и полный расклад, личная матрица, код дня, совместимость, токены и подписка."
    )
    await render(target, text, main_menu_keyboard(target.from_user.id))


def birth_place_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:birth_minute")]
        ]
    )


def match_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")]
        ]
    )


# ---------------------------
# Admin helpers
# ---------------------------

async def send_admin_panel(target: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    if not is_admin(target.from_user.id):
        await render(target, "⛔ Доступ запрещён.", main_menu_keyboard(target.from_user.id))
        return
    await render(
        target,
        "<b>⚙️ Админ-панель</b>\n\nСтатистика, токены, пользователи и рассылка — всё здесь.",
        admin_menu_keyboard(),
    )


async def get_admin_users() -> list[dict]:
    async with aiosqlite.connect("users.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY telegram_id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ---------------------------
# Start / Commands
# ---------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    referrer_id = parse_ref_payload(message.text)
    if referrer_id == message.from_user.id:
        referrer_id = None

    created = await upsert_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
        referrer_id=referrer_id,
    )

    if created and referrer_id:
        referrer = await get_user(referrer_id)
        if referrer:
            await add_tokens(message.from_user.id, 10)
            await add_tokens(referrer_id, 5)

    user = await get_user(message.from_user.id)

    if not profile_complete(user):
        await safe_answer(
            message,
            "<b>Привет.</b>\n\nСначала заполним профиль, чтобы расклады были точнее и глубже.",
            main_reply_keyboard(),
        )
        await start_profile_flow(message, state, user)
        return

    await safe_answer(message, "<b>С возвращением.</b>\n\nТвой личный расклад готов к работе.", main_reply_keyboard())
    await send_main_menu(message, state)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_main_menu(message, state)


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_profile_menu(message, state)


@router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_tokens_menu(message, state)


@router.message(Command("tokens"))
async def cmd_tokens(message: Message, state: FSMContext):
    await cmd_balance(message, state)


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_schedule_menu(message, state)


@router.message(Command("reading"))
async def cmd_reading(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_readings_menu(message, state)


@router.message(Command("match"))
async def cmd_match(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await prompt_match(message, state)


@router.message(Command("subscription"))
async def cmd_subscription(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_subscription_menu(message, state)


@router.message(Command("about"))
async def cmd_about(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_about(message, state)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_admin_panel(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await safe_answer(message, "<b>Ок, шаг отменён.</b>", main_reply_keyboard())
    await send_main_menu(message, state)


@router.message(F.text == "📋 Меню")
async def menu_button(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await send_main_menu(message, state)


# ---------------------------
# Main menu callbacks
# ---------------------------

@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_main_menu(callback, state)


@router.callback_query(F.data == "menu:about")
async def menu_about(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_about(callback, state)


@router.callback_query(F.data == "menu:profile")
async def menu_profile(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_profile_menu(callback, state)


@router.callback_query(F.data == "menu:tokens")
async def menu_tokens(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_tokens_menu(callback, state)


@router.callback_query(F.data == "menu:schedule")
async def menu_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_schedule_menu(callback, state)


@router.callback_query(F.data == "menu:readings")
async def menu_readings(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_readings_menu(callback, state)


@router.callback_query(F.data == "menu:subscription")
async def menu_subscription(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_subscription_menu(callback, state)


@router.callback_query(F.data == "menu:match")
async def menu_match(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await prompt_match(callback, state)


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_admin_panel(callback, state)


@router.callback_query(F.data == "admin_menu")
async def admin_panel_legacy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_admin_panel(callback, state)


# ---------------------------
# Back buttons
# ---------------------------

@router.callback_query(F.data.startswith("back:"))
async def back_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target = callback.data.split(":", 1)[1]
    user = await get_user(callback.from_user.id)

    if target == "main":
        await send_main_menu(callback, state)
    elif target == "readings":
        await send_readings_menu(callback, state)
    elif target == "profile":
        await send_profile_menu(callback, state)
    elif target == "tokens":
        await send_tokens_menu(callback, state)
    elif target == "schedule":
        await send_schedule_menu(callback, state)
    elif target == "subscription":
        await send_subscription_menu(callback, state)
    elif target == "match":
        await prompt_match(callback, state)
    elif target == "birth_year":
        await state.clear()
        await start_profile_flow(callback.message, state, user)
    elif target == "birth_month":
        await state.set_state(Onboarding.birth_year)
        await render(callback, "Выбери год рождения:", year_keyboard())
        return
    elif target == "birth_day":
        data = await state.get_data()
        year = int(data.get("birth_year"))
        await state.set_state(Onboarding.birth_month)
        await render(callback, "Выбери месяц рождения:", month_keyboard())
        return
    elif target == "birth_hour":
        data = await state.get_data()
        year = int(data.get("birth_year"))
        month = int(data.get("birth_month"))
        await state.set_state(Onboarding.birth_day)
        await render(callback, f"Год: {year}\nМесяц: {month:02d}\n\nВыбери день:", days_keyboard(year, month))
        return
    elif target == "birth_minute":
        await state.set_state(Onboarding.birth_hour)
        await render(callback, "Выбери час рождения:", hours_keyboard("birth_hour", "back:birth_day"))
        return
    elif target == "schedule_hour":
        await state.set_state(ScheduleSetup.hour)
        await render(callback, "Выбери час рассылки:", hours_keyboard("schedule_hour", "back:schedule"))
        return
    elif target == "schedule_minute":
        await state.set_state(ScheduleSetup.minute)
        await render(callback, "Выбери минуты рассылки:", minutes_keyboard("schedule_minute", "back:schedule_hour"))
        return
    elif target == "full_pay":
        await send_readings_menu(callback, state)
    elif target == "match_pay":
        await prompt_match(callback, state)
    elif target == "sub_pay":
        await send_subscription_menu(callback, state)
    elif target == "sub_cancel":
        await send_subscription_menu(callback, state)
    else:
        await send_main_menu(callback, state)


# ---------------------------
# Profile callbacks
# ---------------------------

@router.callback_query(F.data == "profile:show")
async def profile_show(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        await render(callback, "Сначала нажми /start.", main_menu_keyboard(callback.from_user.id))
        return
    await render(callback, format_profile(user), profile_menu_keyboard(profile_complete(user)))


@router.callback_query(F.data == "profile:continue")
async def profile_continue(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    await start_profile_flow(callback.message, state, user)


@router.callback_query(F.data == "profile:reset")
async def profile_reset(callback: CallbackQuery):
    await callback.answer()
    await render(
        callback,
        "<b>Сбросить профиль?</b>\n\nВсе данные рождения будут очищены.",
        confirm_keyboard("profile:reset_yes", "back:profile", "Да, сбросить"),
    )


@router.callback_query(F.data == "profile:reset_yes")
async def profile_reset_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await reset_profile(callback.from_user.id)
    user = await get_user(callback.from_user.id)
    await start_profile_flow(callback.message, state, user)


# ---------------------------
# Tokens callbacks
# ---------------------------

@router.callback_query(F.data == "tokens:balance")
async def tokens_balance(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    tokens = int(user["tokens"] or 0) if user else 0
    link = referral_link(callback.from_user.id)
    text = f"<b>💰 Баланс:</b> {tokens}\n"
    if link:
        text += f"\n<b>Реферальная ссылка:</b>\n{e(link)}"
    await render(callback, text, tokens_menu_keyboard())


@router.callback_query(F.data.startswith("tokens:buy:"))
async def tokens_buy(callback: CallbackQuery):
    await callback.answer()
    amount_text = callback.data.split(":")[-1]
    try:
        amount = int(amount_text)
    except ValueError:
        amount = 0

    if amount <= 0:
        await render(callback, "Не удалось определить количество токенов.", tokens_menu_keyboard())
        return

    await add_tokens(callback.from_user.id, amount)
    user = await get_user(callback.from_user.id)
    total = int(user["tokens"] or 0) if user else amount
    await render(
        callback,
        f"<b>✅ Пакет активирован</b>\n\n• Добавлено: <b>{amount}</b>\n• Баланс: <b>{total}</b>\n\nТеперь у тебя больше свободы для раскладов и подписки.",
        tokens_menu_keyboard(),
    )


# ---------------------------
# Schedule callbacks
# ---------------------------

@router.callback_query(F.data == "schedule:time_info")
async def schedule_time_info(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    await render(
        callback,
        f"<b>⏰ Расписание</b>\n\nТекущее время: <b>{pretty_time(user['notify_time'])}</b>",
        schedule_menu_keyboard(user),
    )


@router.callback_query(F.data == "schedule:set_time")
async def schedule_set_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ScheduleSetup.hour)
    await render(callback, "<b>Выбери час рассылки:</b>", hours_keyboard("schedule_hour", "back:schedule"))


@router.callback_query(ScheduleSetup.hour, F.data.startswith("schedule_hour:"))
async def schedule_hour(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    hour = int(callback.data.split(":", 1)[1])
    await state.update_data(schedule_hour=hour)
    await state.set_state(ScheduleSetup.minute)
    await render(
        callback,
        f"<b>Час рассылки:</b> {hour:02d}\n\nВыбери минуты:",
        minutes_keyboard("schedule_minute", "back:schedule_hour"),
    )


@router.callback_query(ScheduleSetup.minute, F.data.startswith("schedule_minute:"))
async def schedule_minute(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    minute = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    hour = int(data["schedule_hour"])
    notify_time = f"{hour:02d}:{minute:02d}"

    await set_notify_time(callback.from_user.id, notify_time)
    await state.clear()

    user = await get_user(callback.from_user.id)
    await render(
        callback,
        f"<b>✅ Время сохранено</b>\n\n• Рассылка: <b>{notify_time}</b>",
        schedule_menu_keyboard(user),
    )


# ---------------------------
# Subscription callbacks
# ---------------------------

@router.callback_query(F.data == "sub:buy_prompt")
async def sub_buy_prompt(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    await render(
        callback,
        format_subscription_prompt(user),
        confirm_keyboard("sub:buy", "back:subscription", "✅ Оформить"),
    )


@router.callback_query(F.data == "sub:buy")
async def sub_buy(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        await render(callback, "Сначала нажми /start.", main_menu_keyboard(callback.from_user.id))
        return

    if not await spend_tokens(callback.from_user.id, SUBSCRIPTION_PRICE):
        tokens = int(user["tokens"] or 0)
        await render(
            callback,
            f"<b>Недостаточно токенов.</b>\n\nБаланс: <b>{tokens}</b>\nНужно: <b>{SUBSCRIPTION_PRICE}</b>\n\nОткрой баланс и вернись к подписке, когда будешь готов.",
            tokens_menu_keyboard(),
        )
        return

    await prepare_subscription_if_needed(callback.from_user.id)
    until = datetime.now(timezone.utc) + timedelta(days=SUBSCRIPTION_DAYS)
    await set_subscription_until(callback.from_user.id, until.isoformat())

    user = await get_user(callback.from_user.id)
    await render(
        callback,
        f"<b>🎁 Подписка активна</b>\n\nДо: <b>{pretty_iso_dt(user['subscription_until'])}</b>\n"
        f"Время рассылки: <b>{pretty_time(user['notify_time'])}</b>",
        subscription_menu_keyboard(user),
    )


@router.callback_query(F.data == "sub:cancel_prompt")
async def sub_cancel_prompt(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not subscription_active(user):
        await render(callback, "<b>Подписка уже не активна.</b>\n\nОформить новую можно в любой момент.", subscription_menu_keyboard(user))
        return

    await render(
        callback,
        "<b>Отменить подписку?</b>\n\nДоступ к ежедневному полному раскладу прекратится сразу.\nЕсли захочешь вернуться, оформить новую можно в любой момент.",
        confirm_keyboard("sub:cancel", "back:subscription", "✅ Отменить"),
    )


@router.callback_query(F.data == "sub:cancel")
async def sub_cancel(callback: CallbackQuery):
    await callback.answer()
    await set_subscription_until(callback.from_user.id, None)
    user = await get_user(callback.from_user.id)
    await render(
        callback,
        "<b>Подписка отменена.</b>\n\nОформить новую можно в любой момент.",
        subscription_menu_keyboard(user),
    )


# ---------------------------
# Readings callbacks
# ---------------------------

@router.callback_query(F.data == "reading:short")
async def reading_short(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user or not profile_complete(user):
        await render(callback, "Сначала заполни профиль.", main_menu_keyboard(callback.from_user.id))
        return

    local_date = current_local_date(user)
    reading = generate_daily_reading(user, local_date)
    text = format_short_reading(reading, local_date)
    await render(callback, text, readings_menu_keyboard(user))


@router.callback_query(F.data == "reading:daycode")
async def reading_daycode(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        await render(callback, "Сначала нажми /start.", main_menu_keyboard(callback.from_user.id))
        return

    local_date = current_local_date(user)
    await render(callback, format_day_code_text(local_date), readings_menu_keyboard(user))


@router.callback_query(F.data == "reading:personal")
async def reading_personal(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user or not profile_complete(user):
        await render(callback, "Сначала заполни профиль.", main_menu_keyboard(callback.from_user.id))
        return

    await render(callback, format_personal_matrix(user), readings_menu_keyboard(user))


@router.callback_query(F.data == "reading:full")
async def reading_full(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user or not profile_complete(user):
        await render(callback, "Сначала заполни профиль.", main_menu_keyboard(callback.from_user.id))
        return

    local_date = current_local_date(user)
    if subscription_active(user) or full_unlocked_today(user, local_date):
        reading = generate_daily_reading(user, local_date)
        await render(callback, format_full_reading(reading, local_date), readings_menu_keyboard(user))
        return

    await render(
        callback,
        format_full_pay_prompt(user, local_date),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=f"💎 Открыть полный расклад • {FULL_READING_PRICE}", callback_data="reading:full_pay"),
                ],
                [
                    InlineKeyboardButton(text=f"⭐ Подписка выгоднее • {SUBSCRIPTION_PRICE}", callback_data="menu:subscription"),
                ],
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back:readings"),
                ],
            ]
        ),
    )


@router.callback_query(F.data == "reading:full_pay")
async def reading_full_pay(callback: CallbackQuery):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user or not profile_complete(user):
        await render(callback, "Сначала заполни профиль.", main_menu_keyboard(callback.from_user.id))
        return

    local_date = current_local_date(user)

    if subscription_active(user) or full_unlocked_today(user, local_date):
        reading = generate_daily_reading(user, local_date)
        await render(callback, format_full_reading(reading, local_date), readings_menu_keyboard(user))
        return

    if not await spend_tokens(callback.from_user.id, FULL_READING_PRICE):
        tokens = int(user["tokens"] or 0)
        await render(
            callback,
            f"<b>Недостаточно токенов.</b>\n\nБаланс: <b>{tokens}</b>\nНужно: <b>{FULL_READING_PRICE}</b>\n\nЕсли берёшь полный расклад регулярно, подписка за 199 токенов обычно выгоднее.",
            tokens_menu_keyboard(),
        )
        return

    await set_paid_full_date(callback.from_user.id, local_date.isoformat())
    reading = generate_daily_reading(user, local_date)
    await render(
        callback,
        format_full_reading(reading, local_date),
        readings_menu_keyboard(await get_user(callback.from_user.id)),
    )


# ---------------------------
# Admin callbacks
# ---------------------------

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await render(callback, "⛔ Доступ запрещён.", main_menu_keyboard(callback.from_user.id))
        return

    users = await get_admin_users()
    await render(callback, admin_stats_text(users), admin_menu_keyboard())


@router.callback_query(F.data == "admin_stats")
async def admin_stats_legacy(callback: CallbackQuery):
    await admin_stats(callback)


@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await render(callback, "⛔ Доступ запрещён.", main_menu_keyboard(callback.from_user.id))
        return

    users = await get_admin_users()
    await render(callback, admin_users_text(users), admin_menu_keyboard())


@router.callback_query(F.data == "admin_users")
async def admin_users_legacy(callback: CallbackQuery):
    await admin_users(callback)


@router.callback_query(F.data == "admin:give_tokens")
async def admin_give_tokens(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await render(callback, "⛔ Доступ запрещён.", main_menu_keyboard(callback.from_user.id))
        return

    await state.set_state(AdminStates.waiting_for_user_id)
    await render(callback, "Введите <b>ID пользователя</b>:", admin_menu_keyboard())


@router.callback_query(F.data == "admin_give_tokens")
async def admin_give_tokens_legacy(callback: CallbackQuery, state: FSMContext):
    await admin_give_tokens(callback, state)


@router.message(AdminStates.waiting_for_user_id)
async def admin_receive_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        user_id = int(raw)
    except ValueError:
        await message.answer("Нужен числовой ID пользователя.")
        return

    await state.update_data(user_id=user_id)
    await state.set_state(AdminStates.waiting_for_tokens)
    await message.answer("Сколько токенов начислить?")


@router.message(AdminStates.waiting_for_tokens)
async def admin_receive_tokens(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    raw = (message.text or "").strip()
    try:
        tokens = int(raw)
    except ValueError:
        await message.answer("Нужна числовая сумма токенов.")
        return

    user = await get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        await state.clear()
        return

    await add_tokens(user_id, tokens)
    await message.answer(f"✅ Начислено {tokens} токенов пользователю <code>{user_id}</code>", parse_mode=ParseMode.HTML)
    await state.clear()


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await render(callback, "⛔ Доступ запрещён.", main_menu_keyboard(callback.from_user.id))
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await render(callback, "Введите текст <b>рассылки</b>:", admin_menu_keyboard())


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_legacy(callback: CallbackQuery, state: FSMContext):
    await admin_broadcast(callback, state)


@router.message(AdminStates.waiting_for_broadcast)
async def admin_send_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    users = await get_admin_users()
    success = 0
    failed = 0
    broadcast_text = message.html_text or message.text or ""

    for user in users:
        uid = user.get("telegram_id")
        if uid is None:
            continue
        try:
            await bot.send_message(chat_id=uid, text=broadcast_text, parse_mode=ParseMode.HTML)
            success += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ Отправлено: {success}\n❌ Ошибки: {failed}")
    await state.clear()


# ---------------------------
# Matching
# ---------------------------

async def prompt_match(target: Message | CallbackQuery, state: FSMContext) -> None:
    user = await get_user(target.from_user.id)
    if not user:
        await render(target, "Сначала нажми /start.", main_menu_keyboard(target.from_user.id))
        return
    if not profile_complete(user):
        await render(target, "Сначала заполни свой профиль полностью.", main_menu_keyboard(target.from_user.id))
        return

    await state.set_state(Onboarding.match_username)
    text = (
        "<b>👥 Совместимость</b>\n\n"
        "Отправь <b>@username</b> второго пользователя, который уже зарегистрирован в боте.\n\n"
        "Ты увидишь, как складывается ваша связка сегодня: где притяжение, где риск и как лучше говорить друг с другом."
    )
    await render(target, text, match_prompt_keyboard())


@router.message(Onboarding.match_username)
async def match_username(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    username = raw.lstrip("@")

    if len(username) < 5 or len(username) > 32 or not username.replace("_", "").isalnum():
        await message.answer("Нужен корректный @username.")
        return

    user = await get_user(message.from_user.id)
    if not user or not profile_complete(user):
        await state.clear()
        await message.answer("Сначала заполни свой профиль полностью.", reply_markup=main_reply_keyboard())
        return

    other = await get_user_by_username(username)
    if not other:
        link = referral_link(message.from_user.id)
        text = (
            f"<b>@{e(username)}</b> ещё не зарегистрирован в боте.\n\n"
            "Отправь ему свою реферальную ссылку:"
        )
        if link:
            text += f"\n\n{e(link)}\n"
            text += "За регистрацию по ссылке начисляются токены."
        await state.clear()
        await message.answer(text, reply_markup=main_menu_keyboard(message.from_user.id))
        return

    if not profile_complete(other):
        await state.clear()
        await message.answer(
            f"<b>@{e(username)}</b> уже в боте, но профиль заполнен не полностью.",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )
        return

    local_date = current_local_date(user)
    if match_unlocked_today(user, local_date):
        pair = generate_pair_reading(user, other, local_date)
        await state.clear()
        await message.answer(format_match_result(user, other, pair, local_date, username), reply_markup=main_menu_keyboard(message.from_user.id))
        return

    await state.clear()
    await message.answer(
        format_match_pay_prompt(user, username),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ Открыть за {MATCH_PRICE}", callback_data=f"match:pay:{other['telegram_id']}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:match")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("match:pay:"))
async def match_pay(callback: CallbackQuery):
    await callback.answer()
    other_id = int(callback.data.split(":")[-1])

    user = await get_user(callback.from_user.id)
    other = await get_user(other_id)

    if not user or not other:
        await render(callback, "Пользователь не найден.", main_menu_keyboard(callback.from_user.id))
        return

    if not profile_complete(user) or not profile_complete(other):
        await render(callback, "Для совместимости нужны заполненные профили.", main_menu_keyboard(callback.from_user.id))
        return

    local_date = current_local_date(user)
    if match_unlocked_today(user, local_date):
        pair = generate_pair_reading(user, other, local_date)
        await render(callback, format_match_result(user, other, pair, local_date, other["username"] or str(other_id)), main_menu_keyboard(callback.from_user.id))
        return

    if not await spend_tokens(callback.from_user.id, MATCH_PRICE):
        tokens = int(user["tokens"] or 0)
        await render(
            callback,
            f"<b>Недостаточно токенов.</b>\n\nБаланс: <b>{tokens}</b>\nНужно: <b>{MATCH_PRICE}</b>\n\nПополни баланс и вернись к совместимости позже.",
            tokens_menu_keyboard(),
        )
        return

    await set_paid_match_date(callback.from_user.id, local_date.isoformat())
    pair = generate_pair_reading(user, other, local_date)
    await render(
        callback,
        format_match_result(user, other, pair, local_date, other["username"] or str(other_id)),
        main_menu_keyboard(callback.from_user.id),
    )


# ---------------------------
# Onboarding: birth date / time / place
# ---------------------------

async def start_profile_flow(target: Message | CallbackQuery, state: FSMContext, user) -> None:
    if not user["birth_date"]:
        await state.set_state(Onboarding.birth_year)
        await render(target, "<b>Выбери год рождения:</b>", year_keyboard())
        return

    if not user["birth_time"]:
        await state.set_state(Onboarding.birth_hour)
        await render(target, "<b>Выбери час рождения:</b>", hours_keyboard("birth_hour", "back:birth_day"))
        return

    if not user["birth_place"]:
        await state.set_state(Onboarding.birth_place)
        await render(
            target,
            "<b>Напиши место рождения одним сообщением.</b>\n\nПример: <i>Казань, Россия</i>",
            birth_place_keyboard(),
        )
        return

    await state.clear()
    await send_main_menu(target, state)


@router.callback_query(Onboarding.birth_year, F.data.startswith("birth_year:"))
async def birth_year(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    year = int(callback.data.split(":", 1)[1])
    await state.update_data(birth_year=year)
    await state.set_state(Onboarding.birth_month)
    await render(callback, "<b>Выбери месяц рождения:</b>", month_keyboard())


@router.callback_query(Onboarding.birth_month, F.data.startswith("birth_month:"))
async def birth_month(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    month = int(callback.data.split(":", 1)[1])
    await state.update_data(birth_month=month)
    data = await state.get_data()
    year = int(data["birth_year"])
    await state.set_state(Onboarding.birth_day)
    await render(callback, f"<b>Год:</b> {year}\n<b>Месяц:</b> {month:02d}\n\n<b>Выбери день:</b>", days_keyboard(year, month))


@router.callback_query(Onboarding.birth_day, F.data.startswith("birth_day:"))
async def birth_day(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    day = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    year = int(data["birth_year"])
    month = int(data["birth_month"])

    try:
        birth_date = date_cls(year, month, day).isoformat()
    except ValueError:
        await render(callback, "Эта дата не существует.", days_keyboard(year, month))
        return

    await set_birth_date(callback.from_user.id, birth_date)
    await set_zodiac(callback.from_user.id, zodiac_sign(birth_date))
    await state.set_state(Onboarding.birth_hour)
    await render(callback, f"<b>Дата сохранена:</b> {birth_date}\n\n<b>Выбери час рождения:</b>", hours_keyboard("birth_hour", "back:birth_day"))


@router.callback_query(Onboarding.birth_hour, F.data.startswith("birth_hour:"))
async def birth_hour(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    hour = int(callback.data.split(":", 1)[1])
    await state.update_data(birth_hour=hour)
    await state.set_state(Onboarding.birth_minute)
    await render(callback, f"<b>Час рождения:</b> {hour:02d}\n\n<b>Выбери минуты:</b>", minutes_keyboard("birth_minute", "back:birth_hour"))


@router.callback_query(Onboarding.birth_minute, F.data.startswith("birth_minute:"))
async def birth_minute(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    minute = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    hour = int(data["birth_hour"])
    birth_time = f"{hour:02d}:{minute:02d}"

    await set_birth_time(callback.from_user.id, birth_time)
    await state.set_state(Onboarding.birth_place)
    await render(
        callback,
        f"<b>Время рождения сохранено:</b> {birth_time}\n\n<b>Напиши место рождения одним сообщением.</b>\n<i>Пример: Казань, Россия</i>",
        birth_place_keyboard(),
    )


@router.message(Onboarding.birth_place)
async def birth_place(message: Message, state: FSMContext):
    place = (message.text or "").strip()
    if len(place) < 2:
        await message.answer("Напиши место рождения ещё раз.")
        return

    await set_birth_place(message.from_user.id, place)
    await state.clear()
    await message.answer("<b>Профиль сохранён.</b>", reply_markup=main_reply_keyboard())
    await send_main_menu(message, state)


# ---------------------------
# Daily notifications
# ---------------------------

async def notification_loop():
    while True:
        try:
            users = await get_all_users_for_notifications()
            for user in users:
                if not subscription_active(user):
                    continue

                tz = tz_for_user(user)
                now_local = datetime.now(tz)
                today = now_local.date().isoformat()

                if user["last_daily_sent_date"] == today:
                    continue

                notify_time = user["notify_time"] or DEFAULT_NOTIFY_TIME
                target_hour, target_minute = map(int, notify_time.split(":"))
                now_minutes = now_local.hour * 60 + now_local.minute
                target_minutes = target_hour * 60 + target_minute

                if now_minutes < target_minutes:
                    continue

                reading_date = now_local.date()
                reading = generate_daily_reading(user, reading_date)
                text = format_full_reading(reading, reading_date)

                try:
                    await bot.send_message(
                        chat_id=user["telegram_id"],
                        text=text,
                        reply_markup=main_menu_keyboard(user["telegram_id"]),
                    )
                    await set_last_daily_sent_date(user["telegram_id"], today)
                    logging.info("Daily reading sent to %s", user["telegram_id"])
                except Exception as exc:
                    logging.exception("Failed to send daily reading to %s: %s", user["telegram_id"], exc)
        except Exception as exc:
            logging.exception("Notification loop error: %s", exc)

        await asyncio.sleep(30)


# ---------------------------
# Fallback
# ---------------------------

@router.message()
async def unknown_message(message: Message):
    if message.text and message.text.startswith("/"):
        return
    await message.answer("Открой <b>📋 Меню</b> или нажми <b>/menu</b>.", reply_markup=main_reply_keyboard())


# ---------------------------
# Main
# ---------------------------

async def main():
    global BOT_USERNAME
    await init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info("Bot username: %s", BOT_USERNAME)
    asyncio.create_task(notification_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
