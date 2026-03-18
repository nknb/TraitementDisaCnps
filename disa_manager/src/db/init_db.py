import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "disa.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def init_db() -> None:
    """Crée la base disa.db et la table utilisateurs avec admin et agent."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Migration légère AVANT d'appliquer le nouveau schema.sql :
        # 1) si la table traitement_disa existe déjà sans certaines colonnes, on les ajoute.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='traitement_disa'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(traitement_disa)")
            cols = [row[1] for row in cur.fetchall()]
            if "statut" not in cols:
                cur.execute("ALTER TABLE traitement_disa ADD COLUMN statut TEXT")
                cur.execute(
                    """
                    UPDATE traitement_disa
                    SET statut = CASE
                        WHEN date_de_validation IS NOT NULL THEN 'TRAITÉ'
                        ELSE 'NON TRAITÉ'
                    END
                    WHERE statut IS NULL
                    """
                )

            # nouvelle colonne ACTIONS MENÉES (actions_menees)
            if "actions_menees" not in cols:
                cur.execute("ALTER TABLE traitement_disa ADD COLUMN actions_menees TEXT")

        # 2) Migration pour la table identification_employeurs :
        # ajout des colonnes telephone_2, email_2 et email_3 si elles n'existent pas encore.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='identification_employeurs'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(identification_employeurs)")
            emp_cols = [row[1] for row in cur.fetchall()]

            if "telephone_2" not in emp_cols:
                cur.execute("ALTER TABLE identification_employeurs ADD COLUMN telephone_2 TEXT")

            if "email_2" not in emp_cols:
                cur.execute("ALTER TABLE identification_employeurs ADD COLUMN email_2 TEXT")

            if "email_3" not in emp_cols:
                cur.execute("ALTER TABLE identification_employeurs ADD COLUMN email_3 TEXT")

        # Puis on applique (ou ré-applique) le schéma complet
        with SCHEMA_PATH.open("r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
            # Les données métier ne seront pas supprimées pour conserver les imports persistants


if __name__ == "__main__":
    init_db()
    print(f"Base initialisée : {DB_PATH}")
