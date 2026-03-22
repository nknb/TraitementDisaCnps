from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from db.connection import get_connection

logger = logging.getLogger(__name__)

# Tables autorisées pour l'import (whitelist contre injection SQL sur table_name)
_ALLOWED_TABLES = {"identification_employeurs", "traitement_disa", "utilisateurs"}


class ImportResult:
    """Résultat d'un import Excel -> SQLite."""

    def __init__(self, inserted: int, errors: int, error_messages: list[str] | None = None) -> None:
        self.inserted = inserted
        self.errors = errors
        self.error_messages = error_messages or []

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"ImportResult(inserted={self.inserted}, errors={self.errors})"


def insert_rows(
    table_name: str,
    db_columns: list[str],
    rows: Iterable[Iterable[Any]],
    atomic: bool = False,
) -> ImportResult:
    """Insère une série de lignes dans une table SQLite.

    - ``table_name`` : nom de la table cible (doit être dans _ALLOWED_TABLES)
    - ``db_columns`` : liste des colonnes de la table à renseigner
    - ``rows`` : itérable de séquences de valeurs (même longueur que ``db_columns``)
    - ``atomic`` : si True, toutes les lignes ou aucune (rollback sur la première erreur).
                   Si False (défaut), continue ligne par ligne et rapporte les erreurs.
    """

    if not table_name:
        raise ValueError("table_name manquant")
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Table non autorisée pour l'import : {table_name!r}")
    if not db_columns:
        raise ValueError("Aucune colonne de base de données à insérer")

    placeholders = ",".join(["?"] * len(db_columns))
    columns_sql = ",".join(db_columns)
    sql = f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})"

    inserted = 0
    errors = 0
    error_messages: list[str] = []

    # Matérialise l'itérable une seule fois (permet de le parcourir deux fois si fallback)
    all_rows = [tuple(r) for r in rows]

    if atomic:
        # Mode tout-ou-rien : executemany en une seule transaction (×10–100 vs boucle execute)
        conn = get_connection()
        with conn:
            cur = conn.cursor()
            cur.executemany(sql, all_rows)
            inserted = len(all_rows)
        logger.info("Import atomique terminé : %d lignes insérées dans %s", inserted, table_name)
    else:
        # Mode tolérant aux erreurs :
        # 1. Fast path  — executemany() sur données propres (O(1) appel SQL)
        # 2. Slow path  — row-by-row si executemany échoue (données avec erreurs)
        conn = get_connection()
        fast_ok = False
        try:
            with conn:
                cur = conn.cursor()
                cur.executemany(sql, all_rows)
                inserted = len(all_rows)
                fast_ok = True
        except Exception:
            pass  # _AutoCloseConn.__exit__ a déjà rollbacké et fermé la connexion

        if not fast_ok and all_rows:
            # Slow path : nouvelle connexion, exécution ligne par ligne
            conn2 = get_connection()
            with conn2:
                cur2 = conn2.cursor()
                for row in all_rows:
                    try:
                        cur2.execute(sql, row)
                        inserted += 1
                    except Exception as exc:
                        errors += 1
                        if len(error_messages) < 20:
                            error_messages.append(str(exc))
                        logger.debug("Erreur ligne %d dans %s : %s", inserted + errors, table_name, exc)

        if errors:
            logger.warning(
                "Import partiel dans %s : %d insérées, %d erreurs", table_name, inserted, errors
            )
        else:
            logger.info("Import terminé : %d lignes insérées dans %s", inserted, table_name)

    return ImportResult(inserted=inserted, errors=errors, error_messages=error_messages)
