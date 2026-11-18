"""Backup and migrate the existing ZenTask database.
Run from the main project folder:
    .\\.venv\\Scripts\\python.exe migrate_database.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from database import DB_NAME, create_tables

db_path = Path(DB_NAME)
if db_path.exists():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}_backup_{stamp}{db_path.suffix}")
    source = sqlite3.connect(str(db_path))
    backup = sqlite3.connect(str(backup_path))
    try:
        source.backup(backup)
    finally:
        backup.close()
        source.close()
    print(f"Backup created: {backup_path}")
else:
    print("No existing database found; a new database will be created.")

create_tables()
print("Migration completed. Existing records were retained.")
