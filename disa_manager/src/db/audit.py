"""audit.py — Traçabilité des opérations et historique des versions.

Deux fonctions publiques :
  - log_audit()               : insère une ligne dans audit_log
  - snapshot_traitement_disa(): copie la ligne actuelle dans traitement_disa_history

Les deux doivent être appelées DANS la même transaction (même ``with conn:``)
que l'opération principale afin de garantir l'atomicité.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# Colonnes de traitement_disa à exclure du snapshot (verrous transitoires + PK)
_EXCLUDE_FROM_SNAPSHOT = {"id", "locked_by", "locked_at"}


def log_audit(
    conn: sqlite3.Connection,
    user: str | None,
    action: str,
    table_name: str,
    record_id: int | None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
) -> None:
    """Insère une entrée dans ``audit_log``.

    Paramètres
    ----------
    conn        : connexion active (dans le bloc with)
    user        : username de l'opérateur
    action      : 'INSERT' | 'UPDATE' | 'DELETE'
    table_name  : nom de la table cible
    record_id   : id de l'enregistrement concerné (None si inconnu)
    old_values  : dict des anciennes valeurs (avant modification)
    new_values  : dict des nouvelles valeurs (après modification)
    """
    try:
        conn.execute(
            """
            INSERT INTO audit_log (user, action, table_name, record_id, old_values, new_values)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user,
                action,
                table_name,
                record_id,
                json.dumps(old_values, ensure_ascii=False, default=str) if old_values else None,
                json.dumps(new_values, ensure_ascii=False, default=str) if new_values else None,
            ),
        )
    except Exception as exc:
        # Ne jamais laisser l'audit bloquer l'opération principale
        logger.warning("audit_log : impossible d'écrire (%s)", exc)


def snapshot_traitement_disa(
    conn: sqlite3.Connection,
    td_id: int,
    version_by: str | None,
) -> None:
    """Copie la ligne ``traitement_disa`` id=td_id dans ``traitement_disa_history``.

    Doit être appelé **avant** le UPDATE, dans la même transaction,
    pour capturer l'état précédent.
    """
    try:
        row = conn.execute(
            "SELECT * FROM traitement_disa WHERE id = ?", (td_id,)
        ).fetchone()
        if row is None:
            return

        col_names = [d[0] for d in conn.execute(
            "SELECT * FROM traitement_disa WHERE 0"
        ).description]

        # Filtrer les colonnes exclues et mapper id → source_id
        hist_cols = ["source_id", "version_by"]
        hist_vals: list[Any] = [td_id, version_by]

        for col in col_names:
            if col in _EXCLUDE_FROM_SNAPSHOT:
                continue
            hist_cols.append(col)
            hist_vals.append(row[col_names.index(col)])

        placeholders = ", ".join("?" * len(hist_vals))
        cols_sql = ", ".join(hist_cols)
        conn.execute(
            f"INSERT INTO traitement_disa_history ({cols_sql}) VALUES ({placeholders})",
            hist_vals,
        )
    except Exception as exc:
        logger.warning("snapshot_traitement_disa : impossible de créer le snapshot (%s)", exc)
