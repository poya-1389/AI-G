import sqlite3
import time
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "bot_data.db")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini")
DEFAULT_MAX_HISTORY_MESSAGES = 20
DEFAULT_DAILY_MESSAGE_LIMIT = 200


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            preferred_model TEXT DEFAULT 'gemini',
            active_character_id INTEGER,
            is_banned INTEGER DEFAULT 0,
            msg_count_today INTEGER DEFAULT 0,
            last_msg_date TEXT,
            created_at REAL
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            character_id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            persona_prompt TEXT NOT NULL,
            is_public INTEGER DEFAULT 0,
            created_at REAL
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            character_id INTEGER,
            role TEXT,
            content TEXT,
            created_at REAL
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")

        defaults = {
            "default_model": DEFAULT_MODEL,
            "max_history_messages": str(DEFAULT_MAX_HISTORY_MESSAGES),
            "daily_message_limit": str(DEFAULT_DAILY_MESSAGE_LIMIT),
            "maintenance_mode": "0",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))


# ---------- settings ----------

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ---------- users ----------

def get_or_create_user(user_id: int, username: str) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return row
        conn.execute(
            "INSERT INTO users (user_id, username, preferred_model, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, get_setting("default_model", DEFAULT_MODEL), time.time()),
        )
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def set_user_model(user_id: int, model: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET preferred_model=? WHERE user_id=?", (model, user_id))


def set_active_character(user_id: int, character_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET active_character_id=? WHERE user_id=?", (character_id, user_id))


def set_ban_status(user_id: int, banned: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))


def is_user_banned(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row["is_banned"])


def count_all_users() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def list_all_user_ids():
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]


def check_and_increment_rate_limit(user_id: int) -> bool:
    today = time.strftime("%Y-%m-%d")
    limit = int(get_setting("daily_message_limit", str(DEFAULT_DAILY_MESSAGE_LIMIT)))
    with get_conn() as conn:
        row = conn.execute(
            "SELECT msg_count_today, last_msg_date FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            return True
        count = row["msg_count_today"] or 0
        last_date = row["last_msg_date"]
        if last_date != today:
            count = 0
        if count >= limit:
            return False
        conn.execute(
            "UPDATE users SET msg_count_today=?, last_msg_date=? WHERE user_id=?",
            (count + 1, today, user_id),
        )
        return True


# ---------- characters ----------

def create_character(owner_id: int, name: str, description: str, persona_prompt: str, is_public: bool = False) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO characters (owner_id, name, description, persona_prompt, is_public, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (owner_id, name, description, persona_prompt, 1 if is_public else 0, time.time()),
        )
        return cur.lastrowid


def get_character(character_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM characters WHERE character_id=?", (character_id,)).fetchone()


def list_user_characters(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM characters WHERE owner_id=? OR is_public=1 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def delete_character(character_id: int, requester_id: int, is_admin: bool) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT owner_id FROM characters WHERE character_id=?", (character_id,)).fetchone()
        if not row:
            return False
        if row["owner_id"] != requester_id and not is_admin:
            return False
        conn.execute("DELETE FROM characters WHERE character_id=?", (character_id,))
        conn.execute("DELETE FROM messages WHERE character_id=?", (character_id,))
        return True


def make_character_public(character_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE characters SET is_public=1 WHERE character_id=?", (character_id,))


def count_all_characters() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM characters").fetchone()["c"]


# ---------- chat history ----------

def add_message(user_id: int, character_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, character_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, character_id, role, content, time.time()),
        )


def get_history(user_id: int, character_id: int, limit: int = None):
    if limit is None:
        limit = int(get_setting("max_history_messages", str(DEFAULT_MAX_HISTORY_MESSAGES)))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE user_id=? AND character_id=? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, character_id, limit),
        ).fetchall()
        return list(reversed(rows))


def clear_history(user_id: int, character_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE user_id=? AND character_id=?", (user_id, character_id))
