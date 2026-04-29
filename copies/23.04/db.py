import random
from datetime import datetime, timezone

import aiosqlite

DB_NAME = 'users.db'


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    username = username.strip().lstrip('@').lower()
    return username or None


async def _rows_to_dicts(cursor) -> list[dict]:
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def _get_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f'PRAGMA table_info({table})')
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, ddl: str) -> None:
    columns = await _get_columns(db, table)
    if column not in columns:
        await db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


async def init_db() -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT NOT NULL,
                birth_date TEXT,
                birth_time TEXT,
                birth_place TEXT,
                timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
                zodiac TEXT,
                personal_arcana INTEGER,
                tokens INTEGER NOT NULL DEFAULT 0,
                referrer_id INTEGER,
                notify_time TEXT,
                subscription_until TEXT,
                paid_full_date TEXT,
                paid_match_date TEXT,
                last_daily_sent_date TEXT,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )

        await _ensure_column(db, 'users', 'username', 'TEXT')
        await _ensure_column(db, 'users', 'birth_time', 'TEXT')
        await _ensure_column(db, 'users', 'birth_place', 'TEXT')
        await _ensure_column(db, 'users', 'timezone', "TEXT NOT NULL DEFAULT 'Europe/Moscow'")
        await _ensure_column(db, 'users', 'zodiac', 'TEXT')
        await _ensure_column(db, 'users', 'personal_arcana', 'INTEGER')
        await _ensure_column(db, 'users', 'tokens', 'INTEGER NOT NULL DEFAULT 0')
        await _ensure_column(db, 'users', 'referrer_id', 'INTEGER')
        await _ensure_column(db, 'users', 'notify_time', 'TEXT')
        await _ensure_column(db, 'users', 'subscription_until', 'TEXT')
        await _ensure_column(db, 'users', 'paid_full_date', 'TEXT')
        await _ensure_column(db, 'users', 'paid_match_date', 'TEXT')
        await _ensure_column(db, 'users', 'last_daily_sent_date', 'TEXT')
        await _ensure_column(db, 'users', 'created_at', "TEXT NOT NULL DEFAULT ''")
        await _ensure_column(db, 'users', 'updated_at', "TEXT NOT NULL DEFAULT ''")
        await db.commit()


async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_by_username(username: str):
    username = normalize_username(username)
    if not username:
        return None

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE lower(username) = ?', (username,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users ORDER BY telegram_id ASC') as cursor:
            return await _rows_to_dicts(cursor)


async def get_all_users_for_notifications() -> list[dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT *
            FROM users
            WHERE subscription_until IS NOT NULL
              AND birth_date IS NOT NULL
              AND birth_time IS NOT NULL
              AND birth_place IS NOT NULL
              AND notify_time IS NOT NULL
            ORDER BY telegram_id ASC
            """
        ) as cursor:
            return await _rows_to_dicts(cursor)


async def upsert_user(
    telegram_id: int,
    name: str,
    username: str | None = None,
    referrer_id: int | None = None,
) -> bool:
    current = await get_user(telegram_id)
    username = normalize_username(username)
    ts = now_iso()

    async with aiosqlite.connect(DB_NAME) as db:
        if current is None:
            personal_arcana = random.randint(1, 22)
            await db.execute(
                """
                INSERT INTO users (
                    telegram_id,
                    username,
                    name,
                    personal_arcana,
                    tokens,
                    referrer_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (telegram_id, username, name, personal_arcana, referrer_id, ts, ts),
            )
            await db.commit()
            return True

        await db.execute(
            """
            UPDATE users
            SET name = ?,
                username = COALESCE(?, username),
                referrer_id = COALESCE(?, referrer_id),
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (name, username, referrer_id, ts, telegram_id),
        )
        await db.commit()
        return False


async def set_personal_arcana(telegram_id: int, personal_arcana: int) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET personal_arcana = ?, updated_at = ? WHERE telegram_id = ?',
            (personal_arcana, now_iso(), telegram_id),
        )
        await db.commit()


async def set_zodiac(telegram_id: int, zodiac: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET zodiac = ?, updated_at = ? WHERE telegram_id = ?',
            (zodiac, now_iso(), telegram_id),
        )
        await db.commit()


async def set_birth_date(telegram_id: int, birth_date: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET birth_date = ?, updated_at = ? WHERE telegram_id = ?',
            (birth_date, now_iso(), telegram_id),
        )
        await db.commit()


async def set_birth_time(telegram_id: int, birth_time: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET birth_time = ?, updated_at = ? WHERE telegram_id = ?',
            (birth_time, now_iso(), telegram_id),
        )
        await db.commit()


async def set_birth_place(telegram_id: int, birth_place: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET birth_place = ?, updated_at = ? WHERE telegram_id = ?',
            (birth_place.strip(), now_iso(), telegram_id),
        )
        await db.commit()


async def set_timezone(telegram_id: int, timezone_name: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET timezone = ?, updated_at = ? WHERE telegram_id = ?',
            (timezone_name, now_iso(), telegram_id),
        )
        await db.commit()


async def set_notify_time(telegram_id: int, notify_time: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET notify_time = ?, updated_at = ? WHERE telegram_id = ?',
            (notify_time, now_iso(), telegram_id),
        )
        await db.commit()


async def set_subscription_until(telegram_id: int, subscription_until: str | None) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET subscription_until = ?, updated_at = ? WHERE telegram_id = ?',
            (subscription_until, now_iso(), telegram_id),
        )
        await db.commit()


async def set_paid_full_date(telegram_id: int, paid_full_date: str | None) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET paid_full_date = ?, updated_at = ? WHERE telegram_id = ?',
            (paid_full_date, now_iso(), telegram_id),
        )
        await db.commit()


async def set_paid_match_date(telegram_id: int, paid_match_date: str | None) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET paid_match_date = ?, updated_at = ? WHERE telegram_id = ?',
            (paid_match_date, now_iso(), telegram_id),
        )
        await db.commit()


async def set_last_daily_sent_date(telegram_id: int, sent_date: str) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'UPDATE users SET last_daily_sent_date = ?, updated_at = ? WHERE telegram_id = ?',
            (sent_date, now_iso(), telegram_id),
        )
        await db.commit()


async def add_tokens(user_id: int, amount: int) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users
            SET tokens = COALESCE(tokens, 0) + ?,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (amount, now_iso(), user_id),
        )
        await db.commit()


async def spend_tokens(user_id: int, amount: int) -> bool:
    user = await get_user(user_id)
    current = int(user['tokens'] or 0) if user else 0
    if current < amount:
        return False

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users
            SET tokens = COALESCE(tokens, 0) - ?,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (amount, now_iso(), user_id),
        )
        await db.commit()
        return True


async def get_tokens(user_id: int) -> int:
    user = await get_user(user_id)
    if not user:
        return 0
    return int(user['tokens'] or 0)


async def reset_profile(telegram_id: int) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users
            SET birth_date = NULL,
                birth_time = NULL,
                birth_place = NULL,
                zodiac = NULL,
                notify_time = NULL,
                paid_full_date = NULL,
                paid_match_date = NULL,
                last_daily_sent_date = NULL,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (now_iso(), telegram_id),
        )
        await db.commit()
