
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "study_workspace.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                extension TEXT NOT NULL,
                chunks_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS study_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)


def save_document(doc_id, name, path, extension, chunks):
    with connect() as db:
        db.execute("""
            INSERT INTO documents (id, name, path, extension, chunks_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            doc_id, name, path, extension, json.dumps(chunks)
        ))


def get_documents():
    with connect() as db:
        rows = db.execute("""
            SELECT id, name, extension, created_at
            FROM documents ORDER BY created_at DESC
        """).fetchall()
        return [dict(row) for row in rows]


def get_document(doc_id):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()

        if not row:
            return None

        result = dict(row)
        result["chunks"] = json.loads(result.pop("chunks_json"))
        return result


def get_all_chunks():
    with connect() as db:
        rows = db.execute(
            "SELECT id, name, chunks_json FROM documents"
        ).fetchall()

    all_chunks = []
    for row in rows:
        for chunk in json.loads(row["chunks_json"]):
            all_chunks.append({
                **chunk,
                "document_id": row["id"],
                "document_name": row["name"]
            })
    return all_chunks


def log_activity(activity, details):
    with connect() as db:
        db.execute(
            "INSERT INTO study_history (activity, details) VALUES (?, ?)",
            (activity, details)
        )


def get_history(limit=50):
    with connect() as db:
        rows = db.execute("""
            SELECT activity, details, created_at
            FROM study_history ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]