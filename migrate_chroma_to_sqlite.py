"""One-time migration from the existing Chroma copy to SQLite.

This reads the COPY at ./chroma_segment_existing_test and writes to
./study_vectors.db. It does not modify the original ./chroma_db folder.
"""

import json
import sqlite3
from pathlib import Path

import chromadb
from chromadb.config import Settings

SOURCE_PATH = Path("./chroma_segment_existing_test")
TARGET_PATH = Path("./study_vectors.db")
COLLECTION_NAME = "class10_maths"

if not SOURCE_PATH.exists():
    raise SystemExit(f"Source Chroma copy not found: {SOURCE_PATH.resolve()}")

settings = Settings(
    chroma_api_impl="chromadb.api.segment.SegmentAPI",
    is_persistent=True,
    persist_directory=str(SOURCE_PATH),
)
client = chromadb.Client(settings=settings)
collection = client.get_collection(name=COLLECTION_NAME)
print("Reading existing Chroma records...", flush=True)
data = collection.get(include=["documents", "metadatas", "embeddings"])

ids = data.get("ids") or []
documents = data.get("documents") or [""] * len(ids)
metadatas = data.get("metadatas") or [{} for _ in ids]
embeddings = data.get("embeddings")
if embeddings is None:
    raise SystemExit("Chroma did not return embeddings; migration stopped without changing the target database.")
if hasattr(embeddings, "tolist"):
    embeddings = embeddings.tolist()

TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
connection = sqlite3.connect(str(TARGET_PATH), timeout=30)
try:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS vectors (
            id TEXT PRIMARY KEY,
            document TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT NOT NULL
        )"""
    )
    rows = []
    skipped = 0
    for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings):
        # Exclude the diagnostic row added only to test the Chroma backend.
        if str(item_id).startswith("diagnostic_"):
            skipped += 1
            continue
        rows.append(
            (
                str(item_id),
                str(document or ""),
                json.dumps([float(value) for value in embedding], separators=(",", ":")),
                json.dumps(metadata or {}, ensure_ascii=False),
            )
        )
    connection.executemany(
        "INSERT OR REPLACE INTO vectors(id, document, embedding, metadata) VALUES (?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    count = connection.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
    print(f"MIGRATION SUCCESS: {len(rows)} records copied; {skipped} diagnostic record(s) skipped.", flush=True)
    print(f"SQLite record count: {count}", flush=True)
    print(f"SQLite database: {TARGET_PATH.resolve()}", flush=True)
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
