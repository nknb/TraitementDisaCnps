import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# S'assurer que "src" est dans le PYTHONPATH pour les imports relatifs
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.init_db import init_db  # type: ignore  # noqa: E402
from ui.pages.login_dialog import LoginDialog  # type: ignore  # noqa: E402
from ui.main_window import MainWindow  # type: ignore  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)

    # Initialisation de la base (table utilisateurs avec admin et agent)
    init_db()

    login = LoginDialog()
    if login.exec() == LoginDialog.DialogCode.Accepted:
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    else:
        # Fermeture si l'utilisateur annule la connexion
        sys.exit(0)


if __name__ == "__main__":
    main()
