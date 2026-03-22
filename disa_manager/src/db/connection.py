"""
connection.py — Connexion SQLite résiliente pour DisaManager
=============================================================

Architecture de résilience réseau :

  1. TIMEOUT DE CONNEXION (3 s)
     sqlite3.connect() peut bloquer plusieurs minutes sur un partage réseau
     Windows (SMB) indisponible.  Un thread dédié avec jointure à 3 s garantit
     que l'interface ne se fige jamais.

  2. MODE HORS LIGNE TRANSPARENT (_OfflineConn)
     Si la base réseau est inaccessible, get_connection() retourne un objet
     _OfflineConn qui :
       - Lectures  → retourne des résultats vides (l'UI affiche une table vide)
       - Écritures → sauvegarde dans la file d'attente persistante locale

  3. FILE D'ATTENTE D'ÉCRITURES (_WriteQueue)
     Les modifications effectuées hors ligne sont sauvegardées dans
     data/pending_writes.json et rejouées automatiquement dès que le réseau
     est rétabli (déclenché par NetworkMonitor).

  4. JOURNAL_MODE ADAPTATIF
     - Chemin réseau (\\\\serveur\\...) : journal_mode = DELETE (compatible SMB)
     - Chemin local                    : journal_mode = WAL   (optimal)

  5. FERMETURE AUTOMATIQUE (_AutoCloseConn)
     Tout bloc ``with get_connection() as conn:`` ferme la connexion à la
     sortie — aucune connexion fantôme ne traîne et ne verrouille la base.
"""

import json
import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Durée max pour établir la connexion (secondes) ───────────────────────────
_CONNECT_TIMEOUT = 3.0

# ── Résolution du répertoire racine ──────────────────────────────────────────

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "disa.db"


# ── Résolution du chemin de la base ──────────────────────────────────────────

def _resolve_db_path() -> Path:
    """Lit disa.conf (clé DB_PATH=) ; retourne le chemin local par défaut sinon."""
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


# ── Détection partage réseau ──────────────────────────────────────────────────

def _is_network_path(p: Path) -> bool:
    """True si le chemin pointe vers un partage réseau Windows (\\\\serveur\\...)."""
    s = str(p)
    return s.startswith("\\\\") or s.startswith("//")


# Résultat mis en cache au chargement du module : DB_PATH ne change pas en cours d'exécution
_IS_NETWORK: bool = _is_network_path(DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# FILE D'ATTENTE D'ÉCRITURES PERSISTANTE
# ─────────────────────────────────────────────────────────────────────────────

class _WriteQueue:
    """Sauvegarde les écritures échouées (réseau indisponible) dans un fichier
    JSON local et les rejoue automatiquement quand la connexion est rétablie.

    Emplacement : <exe_dir>/data/pending_writes.json
    Format      : [{"sql": "...", "params": [...]}, ...]
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._replay_lock = threading.Lock()  # anti-réentrance : un seul replay à la fois
        self._queue: list[dict] = []
        self._path: Path = PROJECT_ROOT / "data" / "pending_writes.json"
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._queue = json.loads(
                    self._path.read_text(encoding="utf-8")
                )
        except Exception:
            self._queue = []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._queue, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Impossible de sauvegarder la file d'attente : %s", e)

    def push(self, sql: str, params: list) -> None:
        """Ajoute une écriture à la file."""
        with self._lock:
            self._queue.append({"sql": sql, "params": list(params)})
            self._save()
        logger.info(
            "Écriture mise en attente [%d en queue] : %.60s",
            len(self._queue), sql,
        )

    def replay(self, conn: sqlite3.Connection) -> int:
        """Rejoue toutes les écritures en attente sur ``conn``.

        Retourne le nombre d'opérations rejouées avec succès.
        Les opérations réussies sont supprimées de la file.
        Un mutex dédié (_replay_lock) empêche deux threads de rejouer simultanément.
        """
        if not self._replay_lock.acquire(blocking=False):
            logger.debug("replay() déjà en cours dans un autre thread — saut.")
            return 0
        try:
            return self._do_replay(conn)
        finally:
            self._replay_lock.release()

    def _do_replay(self, conn: sqlite3.Connection) -> int:
        """Implémentation interne de replay(), appelée sous _replay_lock."""
        with self._lock:
            if not self._queue:
                return 0
            pending = list(self._queue)

        replayed = 0
        failed_from: Optional[int] = None

        for i, item in enumerate(pending):
            try:
                with conn:
                    conn.execute(item["sql"], item["params"])
                replayed += 1
                logger.info("Écriture rejouée : %.60s", item["sql"])
            except Exception as e:
                logger.warning("Replay échoué à l'opération %d : %s", i, e)
                failed_from = i
                break

        with self._lock:
            if failed_from is None:
                self._queue.clear()
            else:
                self._queue = self._queue[failed_from:]
            self._save()

        if replayed:
            logger.info("%d écriture(s) rejouée(s) depuis la file d'attente.", replayed)
        return replayed

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0


# Singleton global de la file d'attente
_WRITE_QUEUE = _WriteQueue()


def get_write_queue() -> _WriteQueue:
    """Retourne la file d'attente globale (pour NetworkMonitor)."""
    return _WRITE_QUEUE


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION HORS LIGNE (fallback réseau indisponible)
# ─────────────────────────────────────────────────────────────────────────────

class _OfflineCursor:
    """Curseur de substitution quand la base réseau est inaccessible.

    - SELECT / PRAGMA → résultats vides (pas d'exception)
    - INSERT / UPDATE / DELETE → ajout à la file d'attente locale
    """

    def __init__(self) -> None:
        self._rows: list = []
        self.rowcount: int = 0
        self.description = None
        self.lastrowid: Optional[int] = None

    def execute(self, sql: str, params=()) -> "_OfflineCursor":
        stripped = sql.strip().upper().lstrip("(")
        is_write = any(
            stripped.startswith(kw)
            for kw in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE")
        )
        if is_write:
            _WRITE_QUEUE.push(sql, list(params))
        self._rows = []
        return self

    def executemany(self, sql: str, seq_of_params) -> "_OfflineCursor":
        for params in seq_of_params:
            self.execute(sql, params)
        return self

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list:
        return []

    def __iter__(self):
        return iter([])


class _OfflineConn:
    """Connexion de substitution quand le réseau est indisponible.

    Toutes les opérations sont silencieuses :
    - Lectures  → résultats vides
    - Écritures → file d'attente persistante
    L'interface reste fonctionnelle sans se figer ni crasher.
    """

    def cursor(self) -> _OfflineCursor:
        return _OfflineCursor()

    def execute(self, sql: str, params=()) -> _OfflineCursor:
        return _OfflineCursor().execute(sql, params)

    def executemany(self, sql: str, seq_of_params) -> _OfflineCursor:
        return _OfflineCursor().executemany(sql, seq_of_params)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> "_OfflineConn":
        return self

    def __exit__(self, *args) -> bool:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# WRAPPER AUTO-FERMETURE (connexion normale)
# ─────────────────────────────────────────────────────────────────────────────

class _AutoCloseConn:
    """Wrapper sur sqlite3.Connection qui ferme la connexion à la sortie du with.

    Garantit qu'aucune connexion ne reste ouverte et ne verrouille la base
    partagée.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_conn"), name, value)

    def cursor(self) -> sqlite3.Cursor:
        return object.__getattribute__(self, "_conn").cursor()

    def execute(self, sql: str, parameters=(), /) -> sqlite3.Cursor:
        return object.__getattribute__(self, "_conn").execute(sql, parameters)

    def executemany(self, sql: str, parameters, /) -> sqlite3.Cursor:
        return object.__getattribute__(self, "_conn").executemany(sql, parameters)

    def executescript(self, sql: str, /) -> sqlite3.Cursor:
        return object.__getattribute__(self, "_conn").executescript(sql)

    def commit(self) -> None:
        object.__getattribute__(self, "_conn").commit()

    def rollback(self) -> None:
        object.__getattribute__(self, "_conn").rollback()

    def close(self) -> None:
        object.__getattribute__(self, "_conn").close()

    def __enter__(self) -> "_AutoCloseConn":
        object.__getattribute__(self, "_conn").__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = object.__getattribute__(self, "_conn")
        try:
            result = conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return result

    def __del__(self) -> None:
        try:
            object.__getattribute__(self, "_conn").close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION AVEC TIMEOUT STRICT
# ─────────────────────────────────────────────────────────────────────────────

def _raw_connect() -> sqlite3.Connection:
    """Ouvre une connexion SQLite brute avec timeout strict (thread).

    Sur Windows SMB, sqlite3.connect() peut bloquer plusieurs minutes si le
    serveur est inaccessible.  Ce wrapper lance la connexion dans un thread
    daemon et abandonne après _CONNECT_TIMEOUT secondes.

    Lève ``FileNotFoundError`` si le fichier DB n'existe pas afin d'éviter
    que sqlite3 en crée un vide automatiquement.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Base de données introuvable : {DB_PATH}\n"
            "Le fichier a peut-être été supprimé ou le partage réseau est déconnecté."
        )

    holder: list = [None, None]  # [connexion, erreur]

    def _worker() -> None:
        try:
            holder[0] = sqlite3.connect(
                str(DB_PATH),
                timeout=30,
                check_same_thread=False,
            )
        except Exception as exc:
            holder[1] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_CONNECT_TIMEOUT)

    if t.is_alive():
        raise TimeoutError(
            f"Connexion à la base impossible après {_CONNECT_TIMEOUT}s "
            f"(réseau indisponible : {DB_PATH})"
        )
    if holder[1] is not None:
        raise holder[1]
    return holder[0]  # type: ignore[return-value]


def _configure_conn(conn: sqlite3.Connection) -> None:
    """Applique les PRAGMAs de performance et de concurrence."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")   # 30 s d'attente sur verrou
    conn.execute("PRAGMA synchronous  = NORMAL")
    conn.execute("PRAGMA cache_size   = -4096")   # 4 Mo de cache

    if _IS_NETWORK:
        # WAL requiert .db-shm (mémoire partagée) → incompatible SMB/CIFS
        conn.execute("PRAGMA journal_mode = DELETE")
    else:
        conn.execute("PRAGMA journal_mode = WAL")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PUBLIC
# ─────────────────────────────────────────────────────────────────────────────

def get_connection() -> "_AutoCloseConn | _OfflineConn":
    """Retourne une connexion vers la base disa.db.

    Comportement selon la disponibilité du réseau :

    ┌─────────────────────┬──────────────────────────────────────────────┐
    │ Réseau disponible   │ Retourne _AutoCloseConn (connexion réelle)   │
    │                     │ + rejoue la file d'attente si non vide       │
    ├─────────────────────┼──────────────────────────────────────────────┤
    │ Réseau indisponible │ Retourne _OfflineConn (connexion de secours) │
    │                     │ → lectures vides, écritures en file d'attente│
    └─────────────────────┴──────────────────────────────────────────────┘

    **Utilisation recommandée :**
    ::

        with get_connection() as conn:
            rows = conn.execute("SELECT ...").fetchall()
        # connexion fermée automatiquement ici
    """
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = _raw_connect()
        _configure_conn(conn)

        # Si des écritures étaient en attente, on les rejoue maintenant
        if not _WRITE_QUEUE.is_empty:
            try:
                _WRITE_QUEUE.replay(conn)
            except Exception as e:
                logger.warning("Replay partiel de la file d'attente : %s", e)

        return _AutoCloseConn(conn)

    except Exception as exc:
        logger.warning(
            "Base inaccessible → mode hors ligne. Cause : %s", exc
        )
        return _OfflineConn()
