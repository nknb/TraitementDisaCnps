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

    conn = get_connection()

    if atomic:
        # Mode tout-ou-rien : une seule transaction, rollback au moindre problème
        with conn:
            cur = conn.cursor()
            for row in rows:
                cur.execute(sql, tuple(row))
                inserted += 1
        logger.info("Import atomique terminé : %d lignes insérées dans %s", inserted, table_name)
    else:
        # Mode tolérant aux erreurs : chaque ligne dans son propre savepoint
        with conn:
            cur = conn.cursor()
            for row in rows:
                try:
                    cur.execute(sql, tuple(row))
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
