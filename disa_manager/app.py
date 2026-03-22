import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication

# S'assurer que "src" est dans le PYTHONPATH pour les imports relatifs.
# En mode frozen (PyInstaller), _MEIPASS est déjà dans sys.path — rien à faire.
if not getattr(sys, "frozen", False):
    BASE_DIR = Path(__file__).resolve().parent
    SRC_DIR = BASE_DIR / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

from db.init_db import init_db, DB_PATH  # type: ignore  # noqa: E402
from db.backup import backup_db  # type: ignore  # noqa: E402
from ui.pages.login_dialog import LoginDialog  # type: ignore  # noqa: E402
from ui.main_window import MainWindow  # type: ignore  # noqa: E402


def _setup_logging() -> None:
    """Configure le logging applicatif avec rotation de fichiers."""
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "disa_manager.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Handler fichier avec rotation (5 × 1 Mo)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    # Handler console (WARNING et au-dessus uniquement)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Démarrage de l'application Traitement DiSA")

    app = QApplication(sys.argv)

    # Initialisation de la base (table utilisateurs avec admin et agent)
    try:
        init_db()
    except Exception:
        logger.exception("Échec de l'initialisation de la base de données")
        sys.exit(1)

    # Sauvegarde automatique au démarrage (silencieuse si erreur)
    backup_db(DB_PATH)

    login = LoginDialog()
    if login.exec() == LoginDialog.DialogCode.Accepted:
        window = MainWindow()
        window.show()
        logger.info("Fenêtre principale ouverte")
        sys.exit(app.exec())
    else:
        # Fermeture si l'utilisateur annule la connexion
        logger.info("Connexion annulée — fermeture")
        sys.exit(0)


if __name__ == "__main__":
    main()
