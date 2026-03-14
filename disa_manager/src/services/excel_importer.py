from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from db.connection import get_connection


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
) -> ImportResult:
    """Insère une série de lignes dans une table SQLite.

    - ``table_name`` : nom de la table cible
    - ``db_columns`` : liste des colonnes de la table à renseigner
    - ``rows`` : itérable de séquences de valeurs (même longueur que ``db_columns``)

    La fonction essaie d'insérer chaque ligne individuellement pour pouvoir
    continuer en cas d'erreur et renvoie le nombre de lignes insérées et d'erreurs.
    """

    if not table_name:
        raise ValueError("table_name manquant")
    if not db_columns:
        raise ValueError("Aucune colonne de base de données à insérer")

    placeholders = ",".join(["?"] * len(db_columns))
    columns_sql = ",".join(db_columns)
    sql = f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})"

    inserted = 0
    errors = 0
    error_messages: list[str] = []

    conn = get_connection()
    with conn:
        cur = conn.cursor()
        for row in rows:
            try:
                cur.execute(sql, tuple(row))
                inserted += 1
            except Exception as exc:  # pragma: no cover - dépend du schéma
                errors += 1
                # On garde les premiers messages d'erreur seulement pour l'UI
                if len(error_messages) < 20:
                    error_messages.append(str(exc))

    return ImportResult(inserted=inserted, errors=errors, error_messages=error_messages)
