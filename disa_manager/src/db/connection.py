import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "disa.db"


def _resolve_db_path() -> Path:
    """Résout le chemin de la base de données.

    Priorité :
    1. Fichier ``disa.conf`` à la racine du projet (clé ``DB_PATH=``)
    2. Chemin par défaut local : data/disa.db

    Le fichier disa.conf permet de pointer tous les postes vers une base
    réseau partagée pour le travail multi-utilisateurs simultané.
    """
    conf_path = PROJECT_ROOT / "disa.conf"
    if conf_path.exists():
        for line in conf_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DB_PATH="):
                raw = line[len("DB_PATH="):].strip()
                if raw:
                    return Path(raw)
    return _DEFAULT_DB_PATH


DB_PATH: Path = _resolve_db_path()


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite vers la base disa.db.

    Paramètres appliqués pour le travail multi-utilisateurs :
    - WAL (Write-Ahead Logging) : plusieurs lecteurs simultanés pendant une écriture
    - busy_timeout 8 000 ms   : attend jusqu'à 8 s si un autre processus écrit,
                                 au lieu de lever immédiatement SQLITE_BUSY
    - foreign_keys ON          : intégrité référentielle activée
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys  = ON")
    conn.execute("PRAGMA journal_mode  = WAL")
    conn.execute("PRAGMA busy_timeout  = 8000")
    return conn
