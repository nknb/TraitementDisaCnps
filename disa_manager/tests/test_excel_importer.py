"""Tests unitaires pour services/excel_importer.py."""
import sqlite3
import sys
from pathlib import Path

import pytest

# Ajouter src/ au path pour les imports
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from services.excel_importer import ImportResult, _ALLOWED_TABLES, insert_rows  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_conn(monkeypatch, tmp_path):
    """Crée une BDD SQLite en mémoire avec la table identification_employeurs."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE identification_employeurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER,
            numero_cnps TEXT NOT NULL,
            raison_sociale TEXT NOT NULL
        )
    """)
    conn.commit()

    # Patch get_connection pour pointer vers la connexion de test
    import db.connection as db_mod
    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests insert_rows
# ---------------------------------------------------------------------------

class TestInsertRows:
    def test_insere_lignes_correctes(self, db_conn):
        rows = [
            [1, "C001", "Société A"],
            [2, "C002", "Société B"],
        ]
        result = insert_rows(
            "identification_employeurs",
            ["numero", "numero_cnps", "raison_sociale"],
            rows,
        )
        assert result.inserted == 2
        assert result.errors == 0
        assert result.error_messages == []

    def test_rapport_erreur_partiel(self, db_conn):
        """Une ligne dupliquée provoque une erreur mais les autres passent."""
        # Insérer une première fois
        insert_rows(
            "identification_employeurs",
            ["numero", "numero_cnps", "raison_sociale"],
            [[1, "C001", "Société A"]],
        )
        # Réinsérer la même + une nouvelle — la première doit échouer (NOT NULL sur numero_cnps)
        rows = [
            [None, None, None],        # violera NOT NULL
            [3, "C003", "Société C"],  # valide
        ]
        result = insert_rows(
            "identification_employeurs",
            ["numero", "numero_cnps", "raison_sociale"],
            rows,
        )
        assert result.inserted == 1
        assert result.errors == 1
        assert len(result.error_messages) == 1

    def test_mode_atomique_rollback_sur_erreur(self, db_conn):
        """En mode atomic=True, une erreur doit provoquer un rollback complet."""
        rows = [
            [1, "C001", "Société A"],
            [None, None, None],   # violera NOT NULL → rollback
        ]
        with pytest.raises(Exception):
            insert_rows(
                "identification_employeurs",
                ["numero", "numero_cnps", "raison_sociale"],
                rows,
                atomic=True,
            )
        # Aucune ligne ne doit avoir été insérée
        count = db_conn.execute(
            "SELECT COUNT(*) FROM identification_employeurs"
        ).fetchone()[0]
        assert count == 0

    def test_table_non_autorisee(self, db_conn):
        with pytest.raises(ValueError, match="non autorisée"):
            insert_rows("sqlite_master", ["name"], [["test"]])

    def test_table_vide_leve_valuerror(self, db_conn):
        with pytest.raises(ValueError, match="table_name manquant"):
            insert_rows("", ["col"], [["val"]])

    def test_colonnes_vides_leve_valuerror(self, db_conn):
        with pytest.raises(ValueError, match="Aucune colonne"):
            insert_rows("identification_employeurs", [], [])

    def test_whitelist_contient_tables_metier(self):
        assert "identification_employeurs" in _ALLOWED_TABLES
        assert "traitement_disa" in _ALLOWED_TABLES
        assert "utilisateurs" in _ALLOWED_TABLES

    def test_import_result_repr(self):
        r = ImportResult(inserted=5, errors=2, error_messages=["err"])
        assert "inserted=5" in repr(r)
        assert "errors=2" in repr(r)
