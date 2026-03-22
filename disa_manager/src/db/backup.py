"""backup.py — Sauvegarde automatique de la base SQLite DisaManager.

Logique :
  - Copie `disa.db` dans <backup_dir>/disa_backup_YYYYMMDD_HHMMSS.db
  - Utilise sqlite3.Connection.backup() (copie cohérente même si la base est ouverte)
  - Conserve les N derniers fichiers, supprime les plus anciens
  - Silencieux si la base est inaccessible (ne bloque pas le démarrage)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_KEEP_DEFAULT = 5          # nombre de backups à conserver
_BACKUP_PREFIX = "disa_backup_"


def backup_db(
    db_path: Path,
    backup_dir: Path | None = None,
    keep: int = _KEEP_DEFAULT,
) -> Path | None:
    """Crée une copie de sauvegarde de ``db_path``.

    Paramètres
    ----------
    db_path    : chemin de la base source (disa.db)
    backup_dir : dossier de destination (défaut : <db_path.parent>/backups)
    keep       : nombre de sauvegardes à conserver (les plus récentes)

    Retourne le chemin du fichier créé, ou ``None`` en cas d'erreur.
    """
    if not db_path.exists():
        logger.warning("Backup ignoré : base introuvable (%s)", db_path)
        return None

    if backup_dir is None:
        backup_dir = db_path.parent / "backups"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Backup ignoré : impossible de créer %s — %s", backup_dir, exc)
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{_BACKUP_PREFIX}{stamp}.db"

    try:
        src_conn = sqlite3.connect(str(db_path), timeout=10)
        dst_conn = sqlite3.connect(str(dest))
        with src_conn, dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        logger.info("Backup créé : %s", dest)
    except Exception as exc:
        logger.warning("Backup échoué (%s) : %s", dest, exc)
        # Nettoyer le fichier partiel si créé
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    _purge_old_backups(backup_dir, keep)
    return dest


def _purge_old_backups(backup_dir: Path, keep: int) -> None:
    """Supprime les sauvegardes excédentaires (les plus anciennes)."""
    files = sorted(
        backup_dir.glob(f"{_BACKUP_PREFIX}*.db"),
        key=lambda p: p.stat().st_mtime,
    )
    to_delete = files[: max(0, len(files) - keep)]
    for f in to_delete:
        try:
            f.unlink()
            logger.info("Ancien backup supprimé : %s", f.name)
        except OSError as exc:
            logger.warning("Impossible de supprimer %s : %s", f.name, exc)
