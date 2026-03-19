"""Tests unitaires pour db/init_db.py — migrations versionnées."""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import db.init_db as init_mod  # noqa: E402
from db.init_db import _apply_migrations, _get_applied_versions  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_with_schema():
    """Crée une connexion SQLite en mémoire avec les tables de base."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS traitement_disa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employeur_id INTEGER NOT NULL,
            exercice INTEGER NOT NULL,
            date_de_reception TEXT,
            date_de_traitement TEXT,
            date_de_validation TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS identification_employeurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER,
            numero_cnps TEXT NOT NULL,
            raison_sociale TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Tests _get_applied_versions
# ---------------------------------------------------------------------------

class TestGetAppliedVersions:
    def test_retourne_set_vide_si_table_absente(self):
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        assert _get_applied_versions(cur) == set()

    def test_retourne_versions_existantes(self):
        conn = _make_conn_with_schema()
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.commit()
        cur = conn.cursor()
        assert _get_applied_versions(cur) == {1, 2}


# ---------------------------------------------------------------------------
# Tests _apply_migrations
# ---------------------------------------------------------------------------

class TestApplyMigrations:
    def test_migration_1_ajoute_colonnes_traitement_disa(self):
        conn = _make_conn_with_schema()
        _apply_migrations(conn)

        cur = conn.cursor()
        cur.execute("PRAGMA table_info(traitement_disa)")
        cols = [row[1] for row in cur.fetchall()]
        assert "statut" in cols
        assert "actions_menees" in cols
        assert "traite_par" in cols
        assert "updated_at" in cols

    def test_migration_2_ajoute_colonnes_identification_employeurs(self):
        conn = _make_conn_with_schema()
        _apply_migrations(conn)

        cur = conn.cursor()
        cur.execute("PRAGMA table_info(identification_employeurs)")
        cols = [row[1] for row in cur.fetchall()]
        assert "telephone_2" in cols
        assert "email_2" in cols
        assert "email_3" in cols

    def test_migrations_idempotentes(self):
        """Appliquer les migrations deux fois ne doit pas lever d'erreur."""
        conn = _make_conn_with_schema()
        _apply_migrations(conn)
        _apply_migrations(conn)   # deuxième appel — doit être sans effet

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM schema_version")
        count = cur.fetchone()[0]
        # Nombre de migrations unique en base == nombre de migrations définies
        assert count == len(init_mod._MIGRATIONS)

    def test_versions_enregistrees_apres_application(self):
        conn = _make_conn_with_schema()
        _apply_migrations(conn)

        cur = conn.cursor()
        applied = _get_applied_versions(cur)
        expected = {v for v, _, _ in init_mod._MIGRATIONS}
        assert applied == expected


# ---------------------------------------------------------------------------
# Test init_db (intégration légère)
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_init_db_cree_fichier_db(self, tmp_path):
        db_path = tmp_path / "data" / "test.db"
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

        with (
            patch.object(init_mod, "DB_PATH", db_path),
            patch.object(init_mod, "SCHEMA_PATH", schema_path),
        ):
            init_mod.init_db()

        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "utilisateurs" in tables
        assert "identification_employeurs" in tables
        assert "traitement_disa" in tables
        assert "schema_version" in tables
        conn.close()
