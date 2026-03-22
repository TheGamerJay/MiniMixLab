"""
History Manager — persists song generation history.
Uses Postgres when DATABASE_URL is set (Railway), falls back to local JSON file.
"""
import json
import logging
import os
from datetime import datetime

from config import HISTORY_FILE, MAX_HISTORY

log = logging.getLogger(__name__)

_DB_URL = os.environ.get("DATABASE_URL", "")


# ── Postgres helpers ───────────────────────────────────────────────────────────

def _get_conn():
    import psycopg2
    return psycopg2.connect(_DB_URL)


def _init_db():
    if not _DB_URL:
        return
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS song_history (
                    id        SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    prompt    TEXT,
                    genre     TEXT,
                    mood      TEXT,
                    duration  INTEGER,
                    voice     TEXT,
                    path      TEXT,
                    lyrics    TEXT
                )
            """)
        conn.commit()
        conn.close()
        log.info("[history] Postgres table ready")
    except Exception as e:
        log.warning("[history] DB init failed: %s", e)


_init_db()


# ── Public API ─────────────────────────────────────────────────────────────────

def add(entry: dict):
    """Save a new song entry."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if _DB_URL:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO song_history
                       (timestamp, prompt, genre, mood, duration, voice, path, lyrics)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        ts,
                        entry.get("prompt", ""),
                        entry.get("genre", ""),
                        entry.get("mood", ""),
                        entry.get("duration", 0),
                        entry.get("voice", ""),
                        entry.get("path", ""),
                        entry.get("lyrics", ""),
                    ),
                )
            conn.commit()
            conn.close()
            return
        except Exception as e:
            log.warning("[history] DB add failed: %s", e)

    # JSON fallback
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    history = _load_json()
    history.insert(0, {**entry, "timestamp": ts})
    history = history[:MAX_HISTORY]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load() -> list:
    """Return full history list, newest first."""
    if _DB_URL:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp,prompt,genre,mood,duration,voice,path,lyrics "
                    "FROM song_history ORDER BY id DESC LIMIT %s",
                    (MAX_HISTORY,),
                )
                rows = cur.fetchall()
            conn.close()
            return [
                dict(zip(
                    ["timestamp","prompt","genre","mood","duration","voice","path","lyrics"],
                    row,
                ))
                for row in rows
            ]
        except Exception as e:
            log.warning("[history] DB load failed: %s", e)

    return _load_json()


def clear():
    """Delete all history."""
    if _DB_URL:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM song_history")
            conn.commit()
            conn.close()
            return
        except Exception as e:
            log.warning("[history] DB clear failed: %s", e)

    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)


def to_rows(history: list) -> list:
    """Convert history list → list of rows for gr.Dataframe."""
    rows = []
    for e in history:
        path     = e.get("path", "")
        filename = os.path.basename(path) if path else "—"
        prompt   = e.get("prompt", "")
        display  = prompt[:55] + "…" if len(prompt) > 55 else prompt
        rows.append([
            e.get("timestamp", ""),
            display,
            e.get("genre", ""),
            f'{e.get("duration", "")}s',
            e.get("voice", ""),
            filename,
        ])
    return rows


# ── JSON fallback helpers ──────────────────────────────────────────────────────

def _load_json() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
