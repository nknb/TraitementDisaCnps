import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    # Mode exécutable (PyInstaller) :
    #   - DB_PATH  : à côté de l'exe, hors bundle (modifiable par l'utilisateur)
    #   - SCHEMA_PATH : dans _MEIPASS (bundle en lecture seule)
    _EXE_DIR    = Path(sys.executable).parent
    _BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    _ROOT       = _EXE_DIR
    SCHEMA_PATH = _BUNDLE_DIR / "db" / "schema.sql"
else:
    _ROOT       = Path(__file__).resolve().parent.parent.parent
    SCHEMA_PATH = _ROOT / "db" / "schema.sql"


def _resolve_db_path() -> Path:
    """Lit disa.conf (clé DB_PATH=) ; retourne le chemin local par défaut sinon.

    Même logique que connection.py — garantit que init_db() et get_connection()
    ciblent toujours la même base de données (réseau ou locale).
    """
    conf_path = _ROOT / "disa.conf"
    if conf_path.exists():
        for line in conf_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DB_PATH="):
                if raw := line[len("DB_PATH="):].strip():
                    return Path(raw)
    return _ROOT / "data" / "disa.db"


DB_PATH: Path = _resolve_db_path()


# ---------------------------------------------------------------------------
# Migrations numérotées
# Chaque entrée : (numéro_version, description, liste de SQL à exécuter)
# NE JAMAIS modifier une migration déjà appliquée — ajouter une nouvelle.
# ---------------------------------------------------------------------------
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "Colonnes statut, actions_menees, traite_par, updated_at dans traitement_disa",
        [
            "ALTER TABLE traitement_disa ADD COLUMN statut TEXT",
            """UPDATE traitement_disa
               SET statut = CASE
                   WHEN date_de_validation IS NOT NULL THEN 'TRAITÉ'
                   ELSE 'NON TRAITÉ'
               END
               WHERE statut IS NULL""",
            "ALTER TABLE traitement_disa ADD COLUMN actions_menees TEXT",
            "ALTER TABLE traitement_disa ADD COLUMN traite_par TEXT",
            "ALTER TABLE traitement_disa ADD COLUMN updated_at TEXT",
            "UPDATE traitement_disa SET updated_at = created_at WHERE updated_at IS NULL",
        ],
    ),
    (
        2,
        "Colonnes telephone_2, email_2, email_3 dans identification_employeurs",
        [
            "ALTER TABLE identification_employeurs ADD COLUMN telephone_2 TEXT",
            "ALTER TABLE identification_employeurs ADD COLUMN email_2 TEXT",
            "ALTER TABLE identification_employeurs ADD COLUMN email_3 TEXT",
        ],
    ),
    (
        3,
        "Colonne is_suspended dans traitement_disa (suspension d'entreprise)",
        [
            "ALTER TABLE traitement_disa ADD COLUMN is_suspended INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        6,
        "Soft lock multi-utilisateurs sur traitement_disa (locked_by, locked_at)",
        [
            "ALTER TABLE traitement_disa ADD COLUMN locked_by TEXT",
            "ALTER TABLE traitement_disa ADD COLUMN locked_at TEXT",
        ],
    ),
    (
        5,
        "Colonne updated_at dans identification_employeurs (détection de conflits multi-utilisateurs)",
        [
            "ALTER TABLE identification_employeurs ADD COLUMN updated_at TEXT",
            "UPDATE identification_employeurs SET updated_at = datetime('now') WHERE updated_at IS NULL",
        ],
    ),
    (
        4,
        "Indexes de performance sur traitement_disa et identification_employeurs",
        [
            "CREATE INDEX IF NOT EXISTS idx_td_traite_par ON traitement_disa(traite_par)",
            "CREATE INDEX IF NOT EXISTS idx_td_statut ON traitement_disa(statut)",
            "CREATE INDEX IF NOT EXISTS idx_td_exercice ON traitement_disa(exercice)",
            "CREATE INDEX IF NOT EXISTS idx_td_employeur ON traitement_disa(employeur_id)",
            "CREATE INDEX IF NOT EXISTS idx_ie_localites ON identification_employeurs(localites)",
            "CREATE INDEX IF NOT EXISTS idx_ie_secteur ON identification_employeurs(secteur_activite)",
            "CREATE INDEX IF NOT EXISTS idx_ie_numero_cnps ON identification_employeurs(numero_cnps)",
        ],
    ),
]


def _get_applied_versions(cur: sqlite3.Cursor) -> set[int]:
    """Retourne l'ensemble des versions de migration déjà appliquées."""
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if not cur.fetchone():
        return set()
    cur.execute("SELECT version FROM schema_version")
    return {row[0] for row in cur.fetchall()}


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Applique les migrations en attente de façon idempotente."""
    cur = conn.cursor()
    applied = _get_applied_versions(cur)

    for version, description, statements in _MIGRATIONS:
        if version in applied:
            continue

        logger.info("Application de la migration v%d : %s", version, description)
        for stmt in statements:
            # Extraire la première colonne citée dans un ALTER TABLE ADD COLUMN
            # pour vérifier si elle existe déjà (idempotence).
            stmt_stripped = stmt.strip().upper()
            if stmt_stripped.startswith("ALTER TABLE") and "ADD COLUMN" in stmt_stripped:
                parts = stmt.split()
                # ALTER TABLE <table> ADD COLUMN <col> ...
                import contextlib
                with contextlib.suppress(ValueError, IndexError):
                    tbl_idx = parts.index("TABLE") + 1
                    col_idx = parts.index("COLUMN") + 1
                    tbl = parts[tbl_idx]
                    col = parts[col_idx]
                    if _table_exists(cur, tbl) and _column_exists(cur, tbl, col):
                        logger.debug("Colonne %s.%s déjà présente, saut", tbl, col)
                        continue

            try:
                cur.execute(stmt)
            except sqlite3.OperationalError as exc:
                # Certaines ALTER TABLE échouent si la colonne existe déjà
                if "duplicate column name" in str(exc).lower():
                    logger.debug("Migration v%d : colonne déjà présente (%s)", version, exc)
                else:
                    raise

        cur.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,)
        )
        logger.info("Migration v%d appliquée avec succès", version)

    conn.commit()


def _pbkdf2_hash(password: str) -> str:
    """Retourne un hash PBKDF2-SHA256 avec salt aléatoire.

    Format: ``pbkdf2:sha256:<iterations>:<salt_hex>:<hash_hex>``
    Compatible NIST 2023 (260 000 itérations minimum).
    """
    import hashlib, os
    iterations = 260_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}:{salt.hex()}:{dk.hex()}"


def _verify_pbkdf2(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre un hash PBKDF2-SHA256."""
    import hashlib
    import hmac
    try:
        _, _, iter_s, salt_hex, hash_hex = stored.split(":")
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre son hash stocké.

    Supporte trois formats (par ordre de priorité) :
    1. PBKDF2 direct   : pbkdf2:sha256:<iter>:<salt>:<hash>  (mot de passe en clair → PBKDF2)
    2. PBKDF2 indirect : pbkdf2:sha256:<iter>:<salt>:<hash>  (SHA-256 brut → PBKDF2, bug migration)
    3. SHA-256 brut    : 64 hex — ancienne version
    """
    import hashlib
    import hmac
    if stored.startswith("pbkdf2:sha256:"):
        # Cas 1 : PBKDF2 du mot de passe en clair (migration correcte)
        if _verify_pbkdf2(password, stored):
            return True
        # Cas 2 : PBKDF2 du SHA-256 brut (bug de double-hachage lors de la migration)
        legacy_hex = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return _verify_pbkdf2(legacy_hex, stored)
    # Cas 3 : ancien hash SHA-256 brut (sera migré au prochain démarrage)
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored)


def _hash_plain_passwords(conn: sqlite3.Connection) -> None:
    """Migre les mots de passe vers PBKDF2-SHA256 (texte clair direct).

    - Texte clair           → PBKDF2(texte_clair)
    - SHA-256 brut          → ignoré (impossible de retrouver le texte clair)
    - PBKDF2 double-haché   → ignoré (verify_password gère le fallback)
    - Déjà en PBKDF2 direct → ignoré (idempotent)
    """
    cur = conn.cursor()
    cur.execute("SELECT id, password FROM utilisateurs")
    updates: list[tuple[str, int]] = []
    for row_id, pwd in cur.fetchall():
        pwd_str = str(pwd) if pwd is not None else ""
        # Sauter les formats déjà sécurisés ou non-récupérables
        if pwd_str.startswith("pbkdf2:sha256:"):
            continue
        if len(pwd_str) == 64 and all(c in "0123456789abcdef" for c in pwd_str):
            continue  # SHA-256 brut : texte clair inconnu, on ne peut pas migrer
        hashed = _pbkdf2_hash(pwd_str)
        updates.append((hashed, row_id))

    if updates:
        cur.executemany(
            "UPDATE utilisateurs SET password = ? WHERE id = ?", updates
        )
        conn.commit()
        logger.info("Sécurité : %d mot(s) de passe migré(s) vers PBKDF2-SHA256", len(updates))


def init_db() -> None:
    """Crée la base disa.db, applique le schéma de base puis les migrations."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("Initialisation de la base : %s", DB_PATH)

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        # 1) Appliquer le schéma de base (CREATE TABLE IF NOT EXISTS — idempotent)
        with SCHEMA_PATH.open("r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # 2) Appliquer les migrations en attente
        _apply_migrations(conn)

        # 3) Hacher les mots de passe en clair (sécurité — idempotent)
        _hash_plain_passwords(conn)

    logger.info("Base de données prête : %s", DB_PATH)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    init_db()
    print(f"Base initialisée : {DB_PATH}")
