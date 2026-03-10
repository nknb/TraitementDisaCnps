import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "disa.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"


def init_db() -> None:
    """Crée (ou recrée) la base disa.db à partir du script SQL."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        with SCHEMA_PATH.open("r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)


if __name__ == "__main__":
    init_db()
    print(f"Base initialisée : {DB_PATH}")
