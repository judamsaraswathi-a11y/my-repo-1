"""ZenTask database schema with additive, backward-compatible migrations."""
import json
import sqlite3
from pathlib import Path

DB_NAME = Path("study_assistant.db")
DEFAULT_CLASSES = [
    "1st Class", "2nd Class", "3rd Class", "4th Class", "5th Class",
    "6th Class", "7th Class", "8th Class", "9th Class", "10th Class"
]

def connect_db():
    conn = sqlite3.connect(str(DB_NAME), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

def _add_column(conn, table, column, definition):
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def create_tables():
    conn = connect_db()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS classes (
            class_id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT NOT NULL, class_id INTEGER,
            FOREIGN KEY (class_id) REFERENCES classes(class_id)
        );
        CREATE TABLE IF NOT EXISTS study_materials (
            material_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, file_path TEXT NOT NULL,
            subject_id INTEGER, uploaded_by INTEGER,
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
            FOREIGN KEY (uploaded_by) REFERENCES users(user_id)
        );
        """)
        _add_column(conn, "users", "created_at", "TEXT")
        _add_column(conn, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "users", "class_id", "INTEGER")
        _add_column(conn, "study_materials", "material_type", "TEXT NOT NULL DEFAULT 'textbook'")
        _add_column(conn, "study_materials", "visibility", "TEXT NOT NULL DEFAULT 'shared'")
        _add_column(conn, "study_materials", "file_hash", "TEXT")
        _add_column(conn, "study_materials", "uploaded_at", "TEXT")
        _add_column(conn, "study_materials", "is_active", "INTEGER NOT NULL DEFAULT 1")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS login_history (
            login_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, session_id TEXT NOT NULL UNIQUE,
            login_at TEXT NOT NULL, logout_at TEXT,
            duration_seconds INTEGER, status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_login_user_time ON login_history(user_id, login_at);

        CREATE TABLE IF NOT EXISTS activity_logs (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, class_id INTEGER, subject_id INTEGER,
            activity_type TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (class_id) REFERENCES classes(class_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
        );
        CREATE INDEX IF NOT EXISTS idx_activity_user_time ON activity_logs(user_id, created_at);

        CREATE TABLE IF NOT EXISTS chat_sessions (
            chat_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, class_id INTEGER, subject_id INTEGER,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (class_id) REFERENCES classes(class_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at);

        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_session_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            role TEXT NOT NULL, message TEXT NOT NULL, source_type TEXT,
            sources_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
            FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(chat_session_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(chat_session_id, created_at);

        CREATE TABLE IF NOT EXISTS learning_progress (
            progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, class_id INTEGER, subject_id INTEGER,
            material_id INTEGER, last_chapter TEXT, last_page INTEGER,
            progress_percent REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
            UNIQUE(user_id, class_id, subject_id, material_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (class_id) REFERENCES classes(class_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
            FOREIGN KEY (material_id) REFERENCES study_materials(material_id)
        );
        CREATE INDEX IF NOT EXISTS idx_progress_user ON learning_progress(user_id, updated_at);

        CREATE TABLE IF NOT EXISTS quiz_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, class_id INTEGER, subject_id INTEGER,
            quiz_title TEXT, score REAL, total_questions INTEGER,
            answers_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT, completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (class_id) REFERENCES classes(class_id),
            FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
        );
        """)
        for class_name in DEFAULT_CLASSES:
            conn.execute(
                """INSERT INTO classes(class_name)
                   SELECT ? WHERE NOT EXISTS
                   (SELECT 1 FROM classes WHERE lower(class_name)=lower(?))""",
                (class_name, class_name),
            )
        conn.commit()
    finally:
        conn.close()

def log_activity(user_id, activity_type, class_id=None, subject_id=None, details=None):
    from datetime import datetime, timezone
    conn = connect_db()
    try:
        conn.execute(
            """INSERT INTO activity_logs
               (user_id, class_id, subject_id, activity_type, details_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, class_id, subject_id, activity_type,
             json.dumps(details or {}, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat(timespec="seconds"))
        )
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    create_tables()
    print("ZenTask database schema is ready. Existing records were preserved.")
